"""PIPE-01B production authority binding and protected-freeze orchestration."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import shapely
from shapely.geometry import Point
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from sprouts_customer_geography.constants import JACCARD_STRESS_THRESHOLD, RADIUS_5_M, TARGET_CRS
from sprouts_customer_geography.geo04 import (
    CONTEXT_SPEC_ID,
    _self_hash,
    derivation_document,
    validate_context_specification,
    validate_inventory_document,
    validate_membership_specification,
)
from sprouts_customer_geography.model06 import (
    COMMITMENT_ID,
    COMMITMENT_VERSION,
    PACKAGE_ID,
    PACKAGE_VERSION,
    PREREGISTRATION_ID,
    PREREGISTRATION_VERSION,
    validate_identity_package,
    validate_preregistration,
    verify_commitment,
)

from .canonical import content_id
from .data_contracts import validate_data02_contract
from .errors import require
from .pipeline import PretargetPipeline, reject_target_inputs
from .production import (
    Geo03ProductionTransformer,
    TigerProductionBundle,
    load_acs_b11001_production_bundle,
    load_tiger_production_bundle,
)
from .reporting import build_disclosure_safe_report
from .run import MANDATORY_DEPENDENCIES, ProtectedRun, audit_dependency_package
from .spatial import parse_internal_point


FOOTPRINT_QUAD_SEGS = 64
MODEL05_BASELINE_SPEC_ID = "BASELINE_HOUSEHOLD"


def _load_json_object(path: Path, code: str) -> dict[str, Any]:
    require(path.is_file(), code, f"required JSON artifact is absent: {path.name}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{code}: unreadable JSON artifact: {path.name}") from exc
    require(isinstance(value, dict), code, f"JSON artifact must be an object: {path.name}")
    return value


@dataclass(frozen=True)
class RepositoryAuthorities:
    data_config: Mapping[str, Any]
    tiger_manifest: Mapping[str, Any]
    acs_manifest: Mapping[str, Any]
    derivation: Mapping[str, Any]
    inventories: Mapping[str, Mapping[str, Any]]
    context_specification: Mapping[str, Any]
    membership_specification: Mapping[str, Any]
    preregistration: Mapping[str, Any]
    public_dependency_values: Mapping[str, str]

    @property
    def model_spec(self) -> dict[str, Any]:
        candidate_state = self.preregistration["prospective_candidate_state"]
        return {
            "model_spec_id": MODEL05_BASELINE_SPEC_ID,
            "model_spec_version": self.preregistration["version"],
            "preregistration_id": self.preregistration["artifact_id"],
            "preregistration_version": self.preregistration["version"],
            "prediction_semantics": candidate_state["prediction_semantics"],
            "accepted": True,
        }


def load_repository_authorities(repository_root: Path) -> RepositoryAuthorities:
    """Load and cross-validate every repository-safe DATA/GEO/MODEL authority."""
    root = repository_root.resolve()
    data_config = _load_json_object(root / "config/data/data01_validation_source_contract.json", "DATA_CONFIG_MISSING")
    tiger_manifest = _load_json_object(root / "data/manifests/tiger_2024_wisconsin_tract.source_manifest.json", "TIGER_MANIFEST_MISSING")
    acs_manifest = _load_json_object(root / "data/manifests/acs_2024_acs5_b11001_wisconsin_tract.source_manifest.json", "ACS_MANIFEST_MISSING")
    data_values = validate_data02_contract(data_config, tiger_manifest, acs_manifest)

    derivation = _load_json_object(root / "config/geo/canonical_tract_inventory_derivation.json", "GEO04_DERIVATION_MISSING")
    _self_hash(derivation)
    require(derivation == derivation_document(), "GEO04_DERIVATION_AUTHORITY_MISMATCH", "repository derivation differs from the accepted deterministic authority")
    inventories = {
        market: _load_json_object(root / f"config/geo/canonical_tract_inventory_{market}.json", "GEO04_INVENTORY_MISSING")
        for market in ("milwaukee", "madison")
    }
    for inventory in inventories.values():
        validate_inventory_document(inventory, derivation)
    context_specification = _load_json_object(root / "config/geo/geo02_validation_context_spatial_spec.json", "GEO02_SPECIFICATION_MISSING")
    validate_context_specification(context_specification, inventories, derivation)
    membership_specification = _load_json_object(root / "config/geo/geo03_internal_point_membership_spatial_spec.json", "GEO03_SPECIFICATION_MISSING")
    validate_membership_specification(membership_specification, context_specification)

    preregistration = _load_json_object(root / "config/model/model05_prospective_validation_preregistration.json", "MODEL05_PREREGISTRATION_MISSING")
    validate_preregistration(preregistration)
    eligible = preregistration.get("prospective_candidate_state", {}).get("eligible_candidates")
    require(eligible == [MODEL05_BASELINE_SPEC_ID], "MODEL05_CANDIDATE_AUTHORITY_MISMATCH", "only BASELINE_HOUSEHOLD may enter the freeze")
    require(preregistration.get("artifact_id") == PREREGISTRATION_ID and preregistration.get("version") == PREREGISTRATION_VERSION, "MODEL05_PREREGISTRATION_IDENTITY_MISMATCH", "MODEL-05 preregistration identity differs")

    expected_data_dependency = {
        "artifact_id": data_values["data01_config_id"],
        "version": data_values["data01_config_version"],
        "content_sha256": data_values["data01_artifact_sha256"],
    }
    require(expected_data_dependency in preregistration.get("dependencies", {}).get("data", []), "MODEL05_DATA_DEPENDENCY_MISMATCH", "MODEL-05 does not bind the accepted DATA artifact")
    geo_dependencies = preregistration.get("dependencies", {}).get("geo", [])
    expected_geo = {
        (derivation["artifact_id"], derivation["content_sha256"]),
        *{(value["artifact_id"], value["content_sha256"]) for value in inventories.values()},
        (context_specification["artifact_id"], context_specification["content_sha256"]),
        (membership_specification["artifact_id"], membership_specification["content_sha256"]),
    }
    actual_geo = {(value.get("artifact_id"), value.get("content_sha256")) for value in geo_dependencies if isinstance(value, Mapping)}
    require(expected_geo <= actual_geo, "MODEL05_GEO_DEPENDENCY_MISMATCH", "MODEL-05 does not bind every accepted GEO artifact")

    public_values = {
        **data_values,
        "geo02_context_spec_id": str(context_specification["artifact_id"]),
        "geo02_context_artifact_sha256": str(context_specification["content_sha256"]),
        "geo03_transform_fingerprint": str(membership_specification["transformation"]["operation_fingerprint_sha256"]),
        "geo03_artifact_sha256": str(membership_specification["content_sha256"]),
        "model05_model_spec_id": MODEL05_BASELINE_SPEC_ID,
        "model05_model_spec_version": str(preregistration["version"]),
        "model05_artifact_sha256": str(preregistration["content_sha256"]),
        "model05_preregistration_id": str(preregistration["artifact_id"]),
        "model05_preregistration_version": str(preregistration["version"]),
        "canonical_inventory_derivation_spec_id": str(derivation["artifact_id"]),
    }
    return RepositoryAuthorities(
        data_config,
        tiger_manifest,
        acs_manifest,
        derivation,
        inventories,
        context_specification,
        membership_specification,
        preregistration,
        public_values,
    )


@dataclass(frozen=True)
class Model04Binding:
    package: Mapping[str, Any]
    protected_content_sha256: str
    validation_summary: Mapping[str, Any]


def load_model04_binding(package_path: Path, nonce_path: Path, commitment_evidence_path: Path) -> Model04Binding:
    package = _load_json_object(package_path, "MODEL04_PACKAGE_MISSING")
    evidence = _load_json_object(commitment_evidence_path, "MODEL04_COMMITMENT_EVIDENCE_MISSING")
    require(nonce_path.is_file(), "MODEL04_NONCE_MISSING", "MODEL-04 protected commitment nonce is absent")
    nonce = nonce_path.read_bytes()
    require(len(nonce) == 32, "MODEL04_NONCE_INVALID", "MODEL-04 commitment nonce must be exactly 32 bytes")
    require(evidence.get("artifact_id") == COMMITMENT_ID and evidence.get("version") == COMMITMENT_VERSION, "MODEL04_COMMITMENT_IDENTITY_MISMATCH", "MODEL-04 commitment evidence identity differs")
    require(evidence.get("protected_package_id") == PACKAGE_ID and evidence.get("protected_package_version") == PACKAGE_VERSION, "MODEL04_COMMITMENT_PACKAGE_MISMATCH", "MODEL-04 commitment references another package")
    verify_commitment(package_path, nonce, evidence)
    validation = validate_identity_package(package)
    reject_target_inputs(package)
    projection = package.get("target_blind_projection")
    require(isinstance(projection, Mapping) and projection.get("sealed_targets_supplied_or_used") is False, "SEALED_TARGETS_PROHIBITED", "MODEL-04 materialization did not prove its target-blind projection")
    return Model04Binding(package, str(package["protected_content_sha256"]), validation)


def bind_authoritative_dependencies(
    authorities: RepositoryAuthorities,
    model04: Model04Binding,
    accepted_preflight: Mapping[str, Any],
) -> dict[str, Any]:
    """Require the accepted preflight to equal the runtime authorities exactly."""
    audit = audit_dependency_package(accepted_preflight)
    require(audit["state"] == "established", "ACCEPTED_DEPENDENCY_PREFLIGHT_INVALID", "accepted dependency preflight is incomplete or contains unexpected fields")
    runtime_values = {
        **authorities.public_dependency_values,
        "model04_package_id": str(model04.package["package_id"]),
        "model04_package_version": str(model04.package["package_version"]),
        "model04_package_sha256": model04.protected_content_sha256,
    }
    require(set(runtime_values) == MANDATORY_DEPENDENCIES, "RUNTIME_DEPENDENCY_CONTRACT_INVALID", "runtime dependency builder does not cover the accepted PIPE contract")
    mismatches = sorted(key for key in MANDATORY_DEPENDENCIES if accepted_preflight.get(key) != runtime_values.get(key))
    require(not mismatches, "AUTHORITATIVE_DEPENDENCY_MISMATCH", f"accepted dependency preflight differs at field name(s): {mismatches}")
    return runtime_values


@dataclass(frozen=True)
class PreparedContext:
    ordinal: int
    context_instance_id: str
    context: Mapping[str, Any] | None
    protected_lineage: Mapping[str, Any]
    quarantined: bool


def _context_identity(package: Mapping[str, Any], record: Mapping[str, Any], context_specification: Mapping[str, Any]) -> str:
    identity = {
        "domain": "pipe01b-geo02-protected-context-instance-v1",
        "model04_package_id": package["package_id"],
        "model04_package_version": package["package_version"],
        "model04_protected_content_sha256": package["protected_content_sha256"],
        "source_workbook_identity": record["source_workbook_identity"],
        "source_sheet": record["source_sheet"],
        "source_row": record["source_row"],
        "source_seed_point_id": record["source_seed_point_id"],
        "context_specification_id": context_specification["artifact_id"],
        "context_specification_sha256": context_specification["content_sha256"],
    }
    return content_id("geo02_context_instance", identity)


def build_protected_contexts(
    model04: Model04Binding,
    authorities: RepositoryAuthorities,
    tiger: TigerProductionBundle,
) -> tuple[PreparedContext, ...]:
    """Instantiate GEO-02 contexts from frozen MODEL-04 anchors only.

    Anchor tract binding uses exact official polygon containment.  There is no
    nearest-tract, centroid, snapping, averaging, or other fallback.
    """
    prepared: list[PreparedContext] = []
    for record in model04.package["records"]:
        if record["evidence_role"] == "DEVELOPMENT_REFERENCE":
            continue
        require(record["target_view_state"] == "SEALED", "MODEL04_ROLE_TARGET_STATE_MISMATCH", "nondevelopment MODEL-04 evidence must remain sealed")
        ordinal = len(prepared) + 1
        instance_id = _context_identity(model04.package, record, authorities.context_specification)
        lineage = {
            "model04_package_id": model04.package["package_id"],
            "model04_package_version": model04.package["package_version"],
            "physical_location_id": record["physical_location_id"],
            "source_workbook_identity": record["source_workbook_identity"],
            "source_sheet": record["source_sheet"],
            "source_row": record["source_row"],
            "source_seed_point_id": record["source_seed_point_id"],
            "identity_state": record["identity_state"],
            "evidence_role": record["evidence_role"],
            "evidence_subrole": record["evidence_subrole"],
            "canonical_anchor_state": record["canonical_anchor_state"],
        }
        if record["quarantined"]:
            require(record["canonical_anchor"] is None, "MODEL04_QUARANTINE_ANCHOR_CONFLICT", "quarantined identity must not carry an anchor")
            prepared.append(PreparedContext(ordinal, instance_id, None, lineage, True))
            continue

        anchor = record.get("canonical_anchor")
        require(isinstance(anchor, Mapping), "MODEL04_CANONICAL_ANCHOR_MISSING", "nonquarantined MODEL-04 evidence requires its frozen canonical anchor")
        point = parse_internal_point(anchor.get("latitude"), anchor.get("longitude"))
        require(point.coordinate_state == "valid", "MODEL04_CANONICAL_ANCHOR_INVALID", "MODEL-04 canonical anchor coordinate is invalid")
        market_id = str(record.get("market", "")).lower()
        market = tiger.markets.get(market_id)
        require(market is not None and market_id in authorities.inventories, "MODEL04_MARKET_AUTHORITY_MISMATCH", "MODEL-04 market has no accepted GEO authority")
        source_point = Point(float(point.longitude), float(point.latitude))
        matches = [geoid for geoid, geometry in market.source_geometries.items() if geometry.covers(source_point)]
        require(len(matches) == 1, "GEO02_ANCHOR_TRACT_BINDING_AMBIGUOUS", "canonical anchor must be covered by exactly one official in-market tract polygon")
        anchor_geoid = matches[0]
        context = {
            "market_id": market_id,
            "context_spec_id": authorities.context_specification["artifact_id"],
            "context_instance_id": instance_id,
            "anchor_tract_geoid": anchor_geoid,
            "anchor_latitude": anchor.get("latitude"),
            "anchor_longitude": anchor.get("longitude"),
        }
        reject_target_inputs(context)
        prepared.append(PreparedContext(ordinal, instance_id, context, lineage, False))
    require(bool(prepared), "MODEL04_NO_FREEZE_CONTEXTS", "MODEL-04 contains no nondevelopment freeze evidence")
    require(len({item.context_instance_id for item in prepared}) == len(prepared), "GEO02_CONTEXT_INSTANCE_DUPLICATE", "protected context instance identity is duplicate")
    return tuple(prepared)


class Geo02ProductionSpatialAdapter:
    """Accepted projected footprints, market support, overlap, and components."""

    def __init__(
        self,
        authorities: RepositoryAuthorities,
        tiger: TigerProductionBundle,
        transformer: Geo03ProductionTransformer,
    ):
        require(authorities.context_specification["artifact_id"] == CONTEXT_SPEC_ID, "GEO02_CONTEXT_SPECIFICATION_MISMATCH", "GEO-02 context authority changed")
        require(authorities.context_specification["projected_context_space"] == TARGET_CRS, "GEO02_CONTEXT_CRS_MISMATCH", "GEO-02 context space is not EPSG:5070")
        self.authorities = authorities
        self.tiger = tiger
        self.transformer = transformer
        self._market_support: dict[str, BaseGeometry] = {}
        for market_id, market in tiger.markets.items():
            support = unary_union(list(market.projected_geometries.values()))
            require(support.is_valid and not support.is_empty and support.area > 0, "GEO02_MARKET_SUPPORT_INVALID", f"market support is invalid for {market_id}")
            self._market_support[market_id] = support

    def execute(self, contexts: tuple[PreparedContext, ...]) -> dict[str, dict[str, Any]]:
        active = [item for item in contexts if item.context is not None]
        footprints: dict[str, BaseGeometry] = {}
        retained: dict[str, BaseGeometry] = {}
        basics: dict[str, dict[str, Any]] = {}
        for item in active:
            context = item.context
            assert context is not None
            market_id = str(context["market_id"])
            support = self._market_support[market_id]
            projected_anchor = self.transformer.transform(float(context["anchor_longitude"]), float(context["anchor_latitude"]))
            anchor_point = Point(projected_anchor)
            footprint = anchor_point.buffer(RADIUS_5_M, quad_segs=FOOTPRINT_QUAD_SEGS)
            require(footprint.is_valid and footprint.area > 0, "GEO02_CONTEXT_FOOTPRINT_INVALID", "projected context footprint is invalid")
            clipped = footprint.intersection(support)
            require(clipped.is_valid, "GEO02_CONTEXT_INTERSECTION_INVALID", "market-clipped context footprint is invalid")
            require(clipped.area <= footprint.area * (1.0 + 1e-12), "GEO02_COMPLETENESS_INVALID", "clipped footprint area exceeds full footprint beyond floating-point representation")
            completeness = min(clipped.area, footprint.area) / footprint.area
            require(math_is_probability(completeness), "GEO02_COMPLETENESS_INVALID", "geometry-derived completeness is outside [0,1]")
            outside = footprint.difference(support)
            truncated = not outside.is_empty and outside.area > 0
            edge_distance = anchor_point.distance(support.boundary)
            margin = edge_distance - RADIUS_5_M
            positive_area_tracts = sum(
                geometry.intersection(footprint).area > 0
                for geometry in self.tiger.markets[market_id].projected_geometries.values()
            )
            require(positive_area_tracts > 0, "GEO02_CONTEXT_TRACT_INTERSECTION_EMPTY", "context has no positive-area canonical tract intersections")
            footprints[item.context_instance_id] = footprint
            retained[item.context_instance_id] = clipped
            basics[item.context_instance_id] = {
                "market_id": market_id,
                "geometric_completeness": float(completeness),
                "market_edge_state": "truncated" if truncated else "not_truncated",
                "anchor_to_market_boundary_m": float(edge_distance),
                "footprint_edge_margin_m": float(margin),
                "truncated_area_m2": float(outside.area),
                "positive_area_tract_count": int(positive_area_tracts),
            }

        pairwise: dict[str, list[dict[str, Any]]] = {item.context_instance_id: [] for item in active}
        adjacency: dict[str, set[str]] = {item.context_instance_id: set() for item in active}
        for left_index, left in enumerate(active):
            for right in active[left_index + 1 :]:
                if basics[left.context_instance_id]["market_id"] != basics[right.context_instance_id]["market_id"]:
                    continue
                left_geometry = retained[left.context_instance_id]
                right_geometry = retained[right.context_instance_id]
                union_area = left_geometry.union(right_geometry).area
                require(union_area > 0, "GEO02_JACCARD_UNION_INVALID", "in-market footprint union has zero area")
                intersection_area = left_geometry.intersection(right_geometry).area
                require(intersection_area <= union_area * (1.0 + 1e-12), "GEO02_JACCARD_INVALID", "intersection area exceeds union beyond floating-point representation")
                jaccard = min(intersection_area, union_area) / union_area
                require(math_is_probability(jaccard), "GEO02_JACCARD_INVALID", "geometric Jaccard is outside [0,1]")
                pairwise[left.context_instance_id].append({"peer_context_instance_id": right.context_instance_id, "geometric_jaccard": float(jaccard)})
                pairwise[right.context_instance_id].append({"peer_context_instance_id": left.context_instance_id, "geometric_jaccard": float(jaccard)})
                if jaccard >= JACCARD_STRESS_THRESHOLD:
                    adjacency[left.context_instance_id].add(right.context_instance_id)
                    adjacency[right.context_instance_id].add(left.context_instance_id)

        components: dict[str, tuple[str, ...]] = {}
        unvisited = set(adjacency)
        while unvisited:
            seed = min(unvisited)
            stack = [seed]
            members: set[str] = set()
            while stack:
                current = stack.pop()
                if current in members:
                    continue
                members.add(current)
                stack.extend(sorted(adjacency[current] - members))
            ordered = tuple(sorted(members))
            for member in ordered:
                components[member] = ordered
            unvisited -= members

        output: dict[str, dict[str, Any]] = {}
        for item in active:
            context = item.context
            assert context is not None
            instance_id = item.context_instance_id
            inventory = self.authorities.inventories[str(context["market_id"])]
            overlaps = sorted(pairwise[instance_id], key=lambda value: value["peer_context_instance_id"])
            maximum = max((value["geometric_jaccard"] for value in overlaps), default=0.0)
            component = components[instance_id]
            spatial_components = {
                "method": "undirected_threshold_graph_transitive_connected_components",
                "geometric_jaccard_threshold": JACCARD_STRESS_THRESHOLD,
                "component_id": content_id("geo02_spatial_component", list(component)),
                "component_size": len(component),
                "threshold_neighbor_count": len(adjacency[instance_id]),
                "pairwise_in_market_geometric_jaccard": overlaps,
                "primary_radius_m": RADIUS_5_M,
                "positive_area_tract_count": basics[instance_id]["positive_area_tract_count"],
                "anchor_to_market_boundary_m": basics[instance_id]["anchor_to_market_boundary_m"],
                "footprint_edge_margin_m": basics[instance_id]["footprint_edge_margin_m"],
                "truncated_area_m2": basics[instance_id]["truncated_area_m2"],
            }
            output[instance_id] = {
                "context_spec_id": context["context_spec_id"],
                "context_instance_id": instance_id,
                "market_edge_state": basics[instance_id]["market_edge_state"],
                "geometric_completeness": basics[instance_id]["geometric_completeness"],
                "geometric_jaccard": float(maximum),
                "spatial_components": spatial_components,
                "geo02_lineage": {
                    "context_specification_sha256": self.authorities.context_specification["content_sha256"],
                    "inventory_artifact_id": inventory["artifact_id"],
                    "inventory_content_sha256": inventory["content_sha256"],
                    "inventory_sha256": inventory["inventory_sha256"],
                    "tiger_source_sha256": self.tiger.source_sha256,
                    "projected_context_space": TARGET_CRS,
                    "footprint_geometry": "EPSG:5070 metric buffer",
                    "footprint_quad_segs": FOOTPRINT_QUAD_SEGS,
                    "market_support": "union of complete canonical in-scope tract geometries",
                    "tract_intersection": "positive_area_only_zero_area_tangency_excluded",
                    "jaccard_geometry": "in_market_clipped_primary_context_footprints",
                    "geometry_engine": f"shapely-{shapely.__version__}",
                    "transformation_provenance": dict(self.transformer.runtime_provenance),
                },
            }
        return output


def math_is_probability(value: float) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and 0.0 <= value <= 1.0


def _quarantined_readiness(item: PreparedContext) -> dict[str, Any]:
    artifact = {
        "context_instance_id": item.context_instance_id,
        "eligibility_status": "quarantined",
        "primary_statistic_eligible": False,
        "secondary_truncated_stratum": False,
        "qa_only": False,
        "quarantined": True,
        "noncomputable": False,
        "reason_codes": ["MODEL04_QUARANTINE", "ANCHOR_UNAVAILABLE_AMBIGUOUS_IDENTITY"],
    }
    return {**artifact, "artifact_id": content_id("eligibility_readiness", artifact)}


@dataclass(frozen=True)
class ProductionFreezeResult:
    run_id: str
    run_dir: Path
    commitment_sha256: str
    disclosure_safe_report: Mapping[str, Any]
    context_count: int
    prediction_count: int


def execute_protected_freeze(
    *,
    repository_root: Path,
    protected_root: Path,
    tiger_source_zip: Path,
    acs_source_file: Path,
    model04_package_path: Path,
    model04_nonce_path: Path,
    model04_commitment_evidence_path: Path,
    accepted_dependency_preflight_path: Path,
    code_identity: str,
    run_id: str | None = None,
    supersedes: str | None = None,
) -> ProductionFreezeResult:
    """Execute the production path without accepting or opening sealed targets."""
    authorities = load_repository_authorities(repository_root)
    transformer = Geo03ProductionTransformer(authorities.membership_specification)
    tiger = load_tiger_production_bundle(
        tiger_source_zip,
        authorities.tiger_manifest,
        authorities.inventories,
        authorities.derivation,
        transformer,
    )
    acs = load_acs_b11001_production_bundle(acs_source_file, authorities.acs_manifest, authorities.inventories)
    model04 = load_model04_binding(model04_package_path, model04_nonce_path, model04_commitment_evidence_path)
    accepted_preflight = _load_json_object(accepted_dependency_preflight_path, "ACCEPTED_DEPENDENCY_PREFLIGHT_MISSING")
    dependencies = bind_authoritative_dependencies(authorities, model04, accepted_preflight)
    contexts = build_protected_contexts(model04, authorities, tiger)
    spatial_by_context = Geo02ProductionSpatialAdapter(authorities, tiger, transformer).execute(contexts)

    pipeline = PretargetPipeline(transformer.operation_fingerprint, transformer)
    active_markets = sorted({str(item.context["market_id"]) for item in contexts if item.context is not None})
    market_artifacts: dict[str, dict[str, Mapping[str, Any]]] = {}
    for market_id in active_markets:
        authority = authorities.inventories[market_id]
        inventory = pipeline.build_inventory(
            market_id,
            authority["ordered_geoids"],
            {
                "authoritative_inventory_artifact_id": authority["artifact_id"],
                "authoritative_inventory_content_sha256": authority["content_sha256"],
                "authoritative_inventory_sha256": authority["inventory_sha256"],
            },
            qa_expected_count=authority["tract_count"],
        )
        require(inventory["qa_count_matches"] is True, "PIPE_INVENTORY_COUNT_MISMATCH", "PIPE inventory count differs from accepted authority")
        internal_points = pipeline.build_internal_point_evidence(inventory, tiger.markets[market_id].rows)
        acs_evidence = pipeline.build_acs_evidence(inventory, acs.markets[market_id], acs.source_lineage)
        market_artifacts[market_id] = {"inventory": inventory, "internal_points": internal_points, "acs": acs_evidence}

    protected_run = ProtectedRun(protected_root, repository_root, run_id=run_id, supersedes=supersedes)
    for market_id, artifacts in market_artifacts.items():
        protected_run.write_artifact(f"market-{market_id}-tract-inventory.json", artifacts["inventory"])
        protected_run.write_artifact(f"market-{market_id}-internal-point-evidence.json", artifacts["internal_points"])
        protected_run.write_artifact(f"market-{market_id}-acs-b11001-evidence.json", artifacts["acs"])

    eligibility_counts: Counter[str] = Counter()
    prediction_count = 0
    for item in contexts:
        prefix = f"context-{item.ordinal:04d}"
        protected_run.write_artifact(
            f"{prefix}-model04-lineage.json",
            {"context_instance_id": item.context_instance_id, **dict(item.protected_lineage)},
        )
        if item.context is None:
            readiness = _quarantined_readiness(item)
            protected_run.write_artifact(f"{prefix}-eligibility-readiness.json", readiness)
            eligibility_counts[readiness["eligibility_status"]] += 1
            continue

        market_id = str(item.context["market_id"])
        artifacts = market_artifacts[market_id]
        membership = pipeline.build_membership(artifacts["inventory"], artifacts["internal_points"], item.context)
        spatial_contract = spatial_by_context[item.context_instance_id]
        spatial_internal = pipeline.validate_spatial_evidence(spatial_contract)
        household = pipeline.aggregate_households(membership, artifacts["acs"])
        readiness = pipeline.build_eligibility(spatial_internal, household, item.quarantined)
        protected_run.write_artifact(f"{prefix}-context-membership.json", membership)
        protected_run.write_artifact(f"{prefix}-context-spatial-evidence.json", spatial_contract)
        protected_run.write_artifact(f"{prefix}-household-opportunity.json", household)
        protected_run.write_artifact(f"{prefix}-eligibility-readiness.json", readiness)
        eligibility_counts[readiness["eligibility_status"]] += 1
        primary = next(row for row in household["rows"] if row["radius_m"] == RADIUS_5_M)
        if primary["calculation_state"] == "complete":
            prediction = pipeline.build_baseline_prediction(household, authorities.model_spec)
            protected_run.write_artifact(f"{prefix}-baseline-prediction.json", prediction)
            prediction_count += 1

    conformance_checks = {
        "authoritative_dependencies_exact": True,
        "geo03_operation_fingerprint_exact": True,
        "tiger_source_checksum_exact": True,
        "canonical_inventories_exact": True,
        "geo02_spatial_execution_complete": True,
        "acs_source_checksum_exact": True,
        "model04_commitment_verified": True,
        "model05_preregistration_exact": True,
        "sealed_targets_supplied": False,
        "membership_nesting_validated": True,
    }
    conformance_results = {
        "mandatory_passed": all(value is True for key, value in conformance_checks.items() if key != "sealed_targets_supplied") and conformance_checks["sealed_targets_supplied"] is False,
        "check_count": len(conformance_checks),
        "checks": conformance_checks,
        "context_count": len(contexts),
        "prediction_count": prediction_count,
        "quarantine_count": eligibility_counts["quarantined"],
    }
    finalized = protected_run.finalize(
        dependencies,
        code_identity,
        {
            "data01": f"{authorities.data_config['artifact_id']}@{authorities.data_config['version']}",
            "geo02": f"{authorities.context_specification['artifact_id']}@{authorities.context_specification['version']}",
            "geo03": f"{authorities.membership_specification['artifact_id']}@{authorities.membership_specification['version']}",
            "model04": f"{model04.package['package_id']}@{model04.package['package_version']}",
            "model05": f"{authorities.preregistration['artifact_id']}@{authorities.preregistration['version']}",
        },
        conformance_results,
        sealed_targets_supplied=False,
    )
    report = build_disclosure_safe_report(
        run_state="frozen",
        mandatory_passed=True,
        check_counts={"passed": len(conformance_checks), "failed": 0},
        dependency_states={key: "exact" for key in ("DATA", "GEO-02", "GEO-03", "MODEL-04", "MODEL-05")},
        source_checksum_states={"TIGER": "accepted", "ACS_B11001": "accepted"},
        inventory_counts={market: int(value["tract_count"]) for market, value in authorities.inventories.items()},
        eligibility_summary=dict(sorted(eligibility_counts.items())),
        commitment=finalized["commitment_sha256"],
    )
    return ProductionFreezeResult(
        finalized["run_id"],
        protected_run.run_dir,
        finalized["commitment_sha256"],
        report,
        len(contexts),
        prediction_count,
    )
