"""Validation for additive GEO-05 Michigan statewide spatial authority."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any, Mapping

from sprouts_customer_geography.data04.contract import Data04Authority, load_authority as load_data04_authority
from sprouts_customer_geography.geo04 import validate_membership_specification
from sprouts_customer_geography.pipe01.canonical import content_digest
from sprouts_customer_geography.pipe01.errors import ConformanceError, require


SPECIFICATION_ID = "GEO05_MICHIGAN_STATEWIDE_SPATIAL_SUPPORT_SPEC_V1"
INVENTORY_ID = "GEO05_MICHIGAN_STATEWIDE_SPATIAL_SUPPORT_INVENTORY_V1"
ANCHOR_EVIDENCE_SCHEMA_ID = "GEO05_ANCHOR_SPATIAL_EVIDENCE_V1"
REPORT_ID = "GEO05_MICHIGAN_STATEWIDE_SPATIAL_SUPPORT_MATERIALIZATION_REPORT_V1"
VERSION = "1.0.0"
EXPECTED_TRACT_COUNT = 3017
STATE_FIPS = "26"
DEFAULT_RADII_M = (4828.032, 8046.72, 11265.408)
EXPECTED_INVENTORY_SHA256 = "8b6698b55423911163f1a2330ad600218a3b8b452576cc9b3d3997ada19e6c9b"
SPECIFICATION_PATH = Path("config/geo/geo05_michigan_statewide_spatial_support_spec.json")
SPECIFICATION_SCHEMA_PATH = Path("schemas/geo05/michigan_statewide_spatial_support_spec.schema.json")
ANCHOR_SCHEMA_PATH = Path("schemas/geo05/anchor_spatial_evidence.schema.json")
REPORT_SCHEMA_PATH = Path("schemas/geo05/spatial_support_materialization_report.schema.json")
GEO02_PATH = Path("config/geo/geo02_validation_context_spatial_spec.json")
GEO03_PATH = Path("config/geo/geo03_internal_point_membership_spatial_spec.json")
MODEL11_PATH = Path("config/model/model11_wisconsin_multivariate_model_contract.json")


@dataclass(frozen=True)
class Geo05Authority:
    specification: Mapping[str, Any]
    specification_schema: Mapping[str, Any]
    anchor_schema: Mapping[str, Any]
    report_schema: Mapping[str, Any]
    data04: Data04Authority
    geo02: Mapping[str, Any]
    geo03: Mapping[str, Any]
    model11: Mapping[str, Any]


def _load_object(path: Path, code: str) -> dict[str, Any]:
    require(path.is_file(), code, f"required repository authority is absent: {path.as_posix()}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ConformanceError(code, "required repository authority is unreadable") from exc
    require(isinstance(value, dict), code, "required repository authority must be a JSON object")
    return value


def _without(value: Mapping[str, Any], field: str) -> dict[str, Any]:
    result = deepcopy(dict(value))
    result.pop(field, None)
    return result


def _verify_self_hash(document: Mapping[str, Any], field: str, code: str) -> str:
    expected = document.get(field)
    require(isinstance(expected, str) and re.fullmatch(r"[0-9a-f]{64}", expected) is not None, code, f"missing or invalid {field}")
    require(content_digest(_without(document, field)) == expected, code, f"{field} does not match canonical JSON")
    return expected


def validate_specification(
    specification: Mapping[str, Any],
    schema: Mapping[str, Any],
    anchor_schema: Mapping[str, Any],
    report_schema: Mapping[str, Any],
    data04: Data04Authority,
    geo02: Mapping[str, Any],
    geo03: Mapping[str, Any],
    model11: Mapping[str, Any],
) -> str:
    """Fail closed unless GEO-05 binds exact accepted public spatial authority."""
    require(
        specification.get("artifact_id") == SPECIFICATION_ID
        and specification.get("version") == VERSION
        and specification.get("status") in {"proposed_awaiting_acceptance", "accepted"},
        "GEO05_SPECIFICATION_IDENTITY_MISMATCH",
        "GEO-05 specification identity, version, or lifecycle state differs",
    )
    require(specification.get("controlling_task") == "GEO-05: Michigan Statewide Geography Enablement", "GEO05_AUTHORITY_MISMATCH", "GEO-05 controlling task differs")
    require(schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema", "GEO05_SCHEMA_INVALID", "GEO-05 schema draft differs")
    require(set(schema.get("required", [])) <= set(specification), "GEO05_SPECIFICATION_INCOMPLETE", "GEO-05 specification omits a required field")
    require(set(specification) <= set(schema.get("properties", {})), "GEO05_SPECIFICATION_FIELD_PROHIBITED", "GEO-05 specification contains an ungoverned field")

    scope = specification.get("state_scope", {})
    require(
        scope == {
            "state_name": "Michigan",
            "state_slug": "michigan",
            "state_fips": STATE_FIPS,
            "geography_level": "tract",
            "statewide": True,
            "tract_geoid_pattern": r"^26[0-9]{9}$",
            "tract_count": EXPECTED_TRACT_COUNT,
            "named_market_inventory": False,
        },
        "GEO05_STATE_SCOPE_MISMATCH",
        "complete statewide Michigan tract scope differs",
    )

    data04_contract = data04.contract
    tiger_manifest = data04.tiger_manifest
    source = specification.get("data04_source_authority", {})
    contract_ref = source.get("contract", {})
    manifest_ref = source.get("tiger_manifest", {})
    require(
        contract_ref.get("artifact_id") == data04_contract.get("artifact_id")
        and contract_ref.get("version") == data04_contract.get("version")
        and contract_ref.get("content_sha256") == data04_contract.get("content_sha256")
        and contract_ref.get("path") == "config/data/data04_michigan_public_data_parity_source_contract.json",
        "GEO05_DATA04_CONTRACT_MISMATCH",
        "accepted DATA-04 contract binding differs",
    )
    require(
        manifest_ref.get("artifact_id") == tiger_manifest.get("manifest_id")
        and manifest_ref.get("version") == tiger_manifest.get("manifest_version")
        and manifest_ref.get("content_sha256") == tiger_manifest.get("manifest_content_sha256")
        and manifest_ref.get("path") == "data/manifests/tiger_2024_michigan_tract.source_manifest.json",
        "GEO05_TIGER_MANIFEST_MISMATCH",
        "accepted Michigan TIGER manifest binding differs",
    )
    source_identity = source.get("tiger_source", {})
    require(
        source_identity
        == {
            "filename": tiger_manifest.get("source_filename"),
            "byte_length": tiger_manifest.get("retrieval", {}).get("expected_byte_length"),
            "byte_sha256": tiger_manifest.get("byte_sha256"),
        },
        "GEO05_TIGER_SOURCE_MISMATCH",
        "accepted Michigan TIGER source-byte identity differs",
    )
    source_geometry = source.get("source_geometry", {})
    properties = tiger_manifest.get("expected_file_properties", {})
    require(
        source_geometry
        == {
            "projection_member_sha256": properties.get("projection_member_sha256"),
            "dbf_member_sha256": properties.get("dbf_member_sha256"),
            "shapefile_member_sha256": properties.get("shapefile_member_sha256"),
            "shapefile_index_member_sha256": properties.get("shapefile_index_member_sha256"),
            "geometry_record_count": EXPECTED_TRACT_COUNT,
        },
        "GEO05_SOURCE_GEOMETRY_IDENTITY_MISMATCH",
        "accepted Michigan source geometry identity differs",
    )
    require(
        source.get("source_crs") == properties.get("expected_crs") == "EPSG:4269"
        and source.get("source_vintage") == tiger_manifest.get("accepted_vintage") == "2024"
        and source.get("required_fields") == ["STATEFP", "COUNTYFP", "TRACTCE", "GEOID", "INTPTLAT", "INTPTLON"],
        "GEO05_TIGER_SOURCE_SEMANTICS_MISMATCH",
        "Michigan TIGER CRS, vintage, or required fields differ",
    )

    inventory = specification.get("statewide_inventory", {})
    require(
        inventory.get("artifact_id") == INVENTORY_ID
        and inventory.get("support_kind") == "complete_statewide_spatial_support"
        and inventory.get("tract_count") == EXPECTED_TRACT_COUNT
        and inventory.get("inventory_sha256") == EXPECTED_INVENTORY_SHA256
        and inventory.get("ordering") == "lexicographically ascending full 11-character GEOID"
        and inventory.get("market_inventory") is False,
        "GEO05_STATEWIDE_INVENTORY_MISMATCH",
        "Michigan statewide spatial-support inventory authority differs",
    )

    validate_membership_specification(geo03, geo02)
    geo03_binding = specification.get("geo03_methodology", {})
    transformation = geo03.get("transformation", {})
    operation = transformation.get("operation", {}) if isinstance(transformation, Mapping) else {}
    geo03_ref = geo03_binding.get("specification", {})
    require(
        geo03_ref.get("artifact_id") == geo03.get("artifact_id")
        and geo03_ref.get("version") == geo03.get("version")
        and geo03_ref.get("content_sha256") == geo03.get("content_sha256")
        and geo03_ref.get("path") == GEO03_PATH.as_posix(),
        "GEO05_GEO03_SPECIFICATION_MISMATCH",
        "accepted GEO-03 specification binding differs",
    )
    require(
        geo03_binding.get("operation_id") == operation.get("operation_id")
        and geo03_binding.get("operation_fingerprint_sha256") == transformation.get("operation_fingerprint_sha256")
        and geo03_binding.get("source_crs") == operation.get("source_crs") == "EPSG:4269"
        and geo03_binding.get("target_crs") == operation.get("target_crs") == "EPSG:5070"
        and geo03_binding.get("logical_input_axis_order") == operation.get("logical_input_axis_order") == ["longitude", "latitude"]
        and geo03_binding.get("alternate_datum_transformation_permitted") is False
        and geo03_binding.get("grid_dependencies") == [],
        "GEO05_GEO03_OPERATION_MISMATCH",
        "accepted GEO-03 mathematical operation differs",
    )
    boundary = geo03.get("boundary_and_radius_binding", {})
    require(
        geo03_binding.get("distance_artifact_id") == geo03.get("validation_membership_distance", {}).get("artifact_id")
        and geo03_binding.get("membership_comparison") == boundary.get("comparison") == "distance_m <= radius_m"
        and geo03_binding.get("membership_rounding") == "none"
        and boundary.get("epsilon_or_snap_or_rounding_permitted") is False
        and geo03_binding.get("forced_containing_tract") is True
        and geo03_binding.get("one_contribution_per_tract") is True,
        "GEO05_GEO03_MEMBERSHIP_MISMATCH",
        "accepted GEO-03 distance or membership semantics differ",
    )

    downstream = specification.get("model_downstream_compatibility", {})
    model_ref = downstream.get("model11_contract", {})
    require(
        model11.get("artifact_id") == model_ref.get("artifact_id") == "MODEL11_WISCONSIN_MULTIVARIATE_MODEL_CONTRACT_V1"
        and model11.get("version") == model_ref.get("version") == VERSION
        and model_ref.get("path") == MODEL11_PATH.as_posix()
        and model_ref.get("content_sha256") == content_digest(model11),
        "GEO05_MODEL11_CONTRACT_MISMATCH",
        "accepted MODEL-11 downstream contract binding differs",
    )
    require(
        downstream.get("radius_owner") == boundary.get("owner") == "MODEL"
        and downstream.get("radii_m") == list(DEFAULT_RADII_M) == boundary.get("radii_m") == model11.get("phase1_feature_freeze", {}).get("reuse_model09_radii_m")
        and downstream.get("model_execution_performed") is False
        and downstream.get("scoring_authority_created") is False,
        "GEO05_MODEL_RADIUS_OR_EXECUTION_MISMATCH",
        "MODEL-owned radii or no-execution boundary differs",
    )

    completeness = specification.get("support_completeness_qa", {})
    require(
        completeness.get("analytical_support") == "union of all accepted Michigan tract geometries projected to EPSG:5070"
        and completeness.get("projected_crs") == "EPSG:5070"
        and completeness.get("footprint_quad_segs") == 64
        and completeness.get("threshold") is None
        and completeness.get("automatic_rejection") is False
        and completeness.get("other_state_or_canadian_demographics") is False,
        "GEO05_SUPPORT_COMPLETENESS_AUTHORITY_MISMATCH",
        "support-completeness QA scope or no-threshold boundary differs",
    )
    interface = specification.get("anchor_interface", {})
    require(
        interface.get("input_fields") == ["latitude", "longitude", "opaque_anchor_identity", "opaque_anchor_lineage"]
        and interface.get("output_schema_id") == ANCHOR_EVIDENCE_SCHEMA_ID
        and interface.get("output_schema_path") == ANCHOR_SCHEMA_PATH.as_posix()
        and interface.get("generic_radius_support") is True
        and interface.get("default_radii_m") == list(DEFAULT_RADII_M)
        and interface.get("output_instance_git_state") == "outside_tracked_git",
        "GEO05_ANCHOR_INTERFACE_MISMATCH",
        "later-anchor interface differs",
    )
    require(
        anchor_schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema"
        and anchor_schema.get("properties", {}).get("schema_id", {}).get("const") == ANCHOR_EVIDENCE_SCHEMA_ID
        and set(anchor_schema.get("required", [])) == {"schema_id", "state", "anchor", "containing_tract_geoid", "projected_anchor", "memberships", "support_completeness", "spatial_lineage"},
        "GEO05_ANCHOR_SCHEMA_INVALID",
        "anchor evidence schema differs",
    )
    require(
        report_schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema"
        and report_schema.get("properties", {}).get("report_id", {}).get("const") == REPORT_ID
        and report_schema.get("properties", {}).get("tract_count", {}).get("const") == EXPECTED_TRACT_COUNT,
        "GEO05_REPORT_SCHEMA_INVALID",
        "materialization report schema differs",
    )

    materialization = specification.get("materialization_contract", {})
    require(
        materialization.get("schema_version") == "geo05-michigan-statewide-spatial-support-v1"
        and materialization.get("overwrite") == "deny"
        and materialization.get("ready_marker_last") is True
        and materialization.get("raw_and_generated_git_state") == "outside_tracked_git",
        "GEO05_MATERIALIZATION_CONTRACT_MISMATCH",
        "GEO-05 immutable output safeguards differ",
    )
    protected = specification.get("protected_evidence_boundary", {})
    require(
        protected.get("public_data_only") is True
        and protected.get("protected_dependencies") == []
        and protected.get("protected_filesystem_discovery") == "prohibited and unnecessary"
        and protected.get("anchor_instances_created_by_geo05") is False,
        "GEO05_PROTECTED_BOUNDARY_MISMATCH",
        "GEO-05 public-only protected boundary differs",
    )
    require(specification.get("hash_algorithm") == "SHA-256" and specification.get("supersedes") is None, "GEO05_HASH_OR_SUCCESSION_MISMATCH", "GEO-05 hash or succession state differs")
    return _verify_self_hash(specification, "content_sha256", "GEO05_SPECIFICATION_HASH_MISMATCH")


def load_authority(repository_root: Path) -> Geo05Authority:
    root = repository_root.resolve()
    specification = _load_object(root / SPECIFICATION_PATH, "GEO05_SPECIFICATION_MISSING")
    schema = _load_object(root / SPECIFICATION_SCHEMA_PATH, "GEO05_SPECIFICATION_SCHEMA_MISSING")
    anchor_schema = _load_object(root / ANCHOR_SCHEMA_PATH, "GEO05_ANCHOR_SCHEMA_MISSING")
    report_schema = _load_object(root / REPORT_SCHEMA_PATH, "GEO05_REPORT_SCHEMA_MISSING")
    data04 = load_data04_authority(root)
    geo02 = _load_object(root / GEO02_PATH, "GEO02_AUTHORITY_MISSING")
    geo03 = _load_object(root / GEO03_PATH, "GEO03_AUTHORITY_MISSING")
    model11 = _load_object(root / MODEL11_PATH, "MODEL11_AUTHORITY_MISSING")
    validate_specification(specification, schema, anchor_schema, report_schema, data04, geo02, geo03, model11)
    return Geo05Authority(specification, schema, anchor_schema, report_schema, data04, geo02, geo03, model11)
