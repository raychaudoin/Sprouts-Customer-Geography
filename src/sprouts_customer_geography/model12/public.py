"""Exact DATA-04, GEO-05, and MODEL-11 public feature application for Michigan."""

from __future__ import annotations

import csv
from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from sprouts_customer_geography.geo05.contract import load_authority as load_geo05_authority
from sprouts_customer_geography.geo05.materialization import (
    SupportPackage,
    evaluate_anchor_package,
    load_support_package,
    verify_data04_ready,
)
from sprouts_customer_geography.model11.features import _aggregate_measure
from sprouts_customer_geography.pipe01.canonical import file_sha256
from sprouts_customer_geography.pipe01.errors import ConformanceError, require

from .frozen import FrozenScoringState


RADII_M = (4828.032, 8046.72, 11265.408)
FIELD_ANCHOR_LINEAGE = "MODEL12_PROTECTED_LOCAL_ANCHOR_V1"


def _load_object(path: Path, code: str) -> dict[str, Any]:
    require(path.is_file(), code, "required accepted public JSON is absent")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        require(False, code, "required accepted public JSON is unreadable")
    require(isinstance(value, dict), code, "required accepted public JSON must be an object")
    return value


def _number(raw: str) -> float | None:
    if raw == "":
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


@dataclass(frozen=True)
class MichiganPublicSources:
    ordered_geoids: tuple[str, ...]
    households: Mapping[str, Mapping[str, Any]]
    components: Mapping[str, Mapping[str, Mapping[str, Any]]]
    model11_contract: Mapping[str, Any]
    lineage: Mapping[str, Any]


def _required_components(model11_contract: Mapping[str, Any]) -> set[str]:
    components = {component for item in model11_contract["candidate_measures"] for component in item.get("numerators", [])}
    components.update(item.get("denominator") for item in model11_contract["candidate_measures"] if item.get("denominator"))
    components.update(
        {
            "median_household_income",
            "per_capita_income",
            "median_home_value",
            "median_gross_rent",
            "average_household_size",
            "occupied_housing_units_total",
            "owner_occupied_housing_units",
        }
    )
    return {str(value) for value in components}


def load_data04_public_sources(repository_root: Path, ready_dir: Path) -> MichiganPublicSources:
    """Fully verify and load one accepted DATA-04 public materialization."""

    root = repository_root.resolve()
    directory = ready_dir.resolve()
    geo05 = load_geo05_authority(root)
    tiger_rows, geo_lineage = verify_data04_ready(geo05, directory)
    contract = geo05.data04.contract
    output = contract["output_contract"]
    report_path = directory / output["verification_report_filename"]
    ready_path = directory / output["ready_filename"]
    report = _load_object(report_path, "MODEL12_DATA04_REPORT_UNRESOLVED")
    ready = _load_object(ready_path, "MODEL12_DATA04_READY_UNRESOLVED")
    expected_files = {
        output["household_filename"],
        output["tiger_filename"],
        output["verification_report_filename"],
        output["ready_filename"],
        f"{output['multivariate_directory']}/{output['multivariate_normalized_filename']}",
        f"{output['multivariate_directory']}/{output['multivariate_candidate_filename']}",
        f"{output['multivariate_directory']}/verification_report.json",
        f"{output['multivariate_directory']}/READY.json",
    }
    actual_files = {path.relative_to(directory).as_posix() for path in directory.rglob("*") if path.is_file()}
    require(actual_files == expected_files, "MODEL12_DATA04_FILE_INVENTORY_MISMATCH", "accepted DATA-04 package contains a missing extra or nested file")

    household_path = directory / output["household_filename"]
    household_report = report.get("household_evidence", {})
    require(
        household_path.is_file()
        and ready.get("household_output_sha256") == file_sha256(household_path)
        and household_report.get("output", {}).get("byte_sha256") == file_sha256(household_path)
        and household_report.get("row_count") == contract["state_scope"]["observed_tract_count"],
        "MODEL12_DATA04_HOUSEHOLD_BINDING_MISMATCH",
        "accepted DATA-04 household output binding differs",
    )
    households: dict[str, dict[str, Any]] = {}
    with household_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        require(reader.fieldnames == household_report.get("output", {}).get("columns"), "MODEL12_DATA04_HOUSEHOLD_SCHEMA_MISMATCH", "DATA-04 household columns differ")
        for row in reader:
            geoid = str(row["tract_geoid"])
            require(geoid not in households, "MODEL12_DATA04_HOUSEHOLD_DUPLICATE", "DATA-04 household tract is duplicate")
            households[geoid] = {
                "estimate": _number(row["estimate"]),
                "moe": _number(row["moe"]),
                "status": row["status"],
                "status_detail": row["status_detail"],
            }

    multivariate_dir = directory / output["multivariate_directory"]
    subreport_path = multivariate_dir / "verification_report.json"
    subready_path = multivariate_dir / "READY.json"
    normalized_path = multivariate_dir / output["multivariate_normalized_filename"]
    candidate_path = multivariate_dir / output["multivariate_candidate_filename"]
    subreport = _load_object(subreport_path, "MODEL12_DATA04_MULTIVARIATE_REPORT_UNRESOLVED")
    subready = _load_object(subready_path, "MODEL12_DATA04_MULTIVARIATE_READY_UNRESOLVED")
    parent_multivariate = report.get("multivariate_evidence", {})
    require(
        subreport.get("state") == "VERIFIED"
        and subreport.get("report_id") == "DATA04_MICHIGAN_MULTIVARIATE_ACS_SUBREPORT_V1"
        and subreport.get("state_fips") == "26"
        and subreport.get("tract_count") == contract["state_scope"]["observed_tract_count"]
        and subreport.get("contract_id") == parent_multivariate.get("data03_contract_id")
        and subreport.get("contract_content_sha256") == parent_multivariate.get("data03_contract_content_sha256")
        and parent_multivariate.get("subreport_sha256") == file_sha256(subreport_path)
        and subready.get("state") == "READY"
        and subready.get("ready_marker_written_last") is True
        and subready.get("report_sha256") == file_sha256(subreport_path)
        and subready.get("normalized_output_sha256") == file_sha256(normalized_path)
        and subready.get("candidate_output_sha256") == file_sha256(candidate_path)
        and ready.get("multivariate_normalized_output_sha256") == file_sha256(normalized_path)
        and ready.get("multivariate_candidate_output_sha256") == file_sha256(candidate_path),
        "MODEL12_DATA04_MULTIVARIATE_BINDING_MISMATCH",
        "accepted DATA-04 multivariate report or READY binding differs",
    )
    expected_reconciliation = contract["multivariate_extraction"]["expected_source_row_reconciliation"]
    observed_reconciliation = subreport.get("source_row_reconciliation", {})
    require(set(observed_reconciliation) == set(expected_reconciliation), "MODEL12_DATA04_SOURCE_ROW_RECONCILIATION_MISMATCH", "DATA-04 table reconciliation identity differs")
    for table_id, expected in expected_reconciliation.items():
        observed = observed_reconciliation[table_id]
        require(
            {key: observed.get(key) for key in expected} == expected,
            "MODEL12_DATA04_SOURCE_ROW_RECONCILIATION_MISMATCH",
            "DATA-04 source-row missingness evidence differs",
        )

    model11_contract = _load_object(root / "config/model/model11_wisconsin_multivariate_model_contract.json", "MODEL12_MODEL11_CONTRACT_UNRESOLVED")
    expected_components = _required_components(model11_contract)
    components: dict[str, dict[str, dict[str, Any]]] = {}
    row_count = 0
    with normalized_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        normalized_report = subreport.get("normalized_output", {})
        require(reader.fieldnames == normalized_report.get("columns"), "MODEL12_DATA04_COMPONENT_SCHEMA_MISMATCH", "DATA-04 normalized component columns differ")
        for row in reader:
            row_count += 1
            component = str(row["component_id"])
            if component not in expected_components:
                continue
            geoid = str(row["tract_geoid"])
            values = components.setdefault(geoid, {})
            require(component not in values, "MODEL12_DATA04_COMPONENT_DUPLICATE", "DATA-04 tract component is duplicate")
            values[component] = {
                "estimate": _number(row["estimate"]),
                "moe": _number(row["moe"]),
                "status": row["status"],
                "status_detail": row["status_detail"],
            }
    require(row_count == subreport["normalized_output"]["row_count"], "MODEL12_DATA04_COMPONENT_ROW_COUNT_MISMATCH", "DATA-04 normalized row count differs")
    ordered_geoids = tuple(str(row["tract_geoid"]) for row in tiger_rows)
    require(
        set(households) == set(components) == set(ordered_geoids)
        and len(ordered_geoids) == 3017
        and all(expected_components <= set(values) for values in components.values()),
        "MODEL12_DATA04_COMPONENT_COVERAGE_MISMATCH",
        "DATA-04 household component and statewide tract coverage differ",
    )
    lineage = {
        **geo_lineage,
        "data04_household_evidence_sha256": file_sha256(household_path),
        "data04_multivariate_normalized_sha256": file_sha256(normalized_path),
        "data04_multivariate_report_sha256": file_sha256(subreport_path),
        "data03_contract_id": parent_multivariate["data03_contract_id"],
        "data03_contract_content_sha256": parent_multivariate["data03_contract_content_sha256"],
        "source_row_missing_evidence_preserved": True,
        "imputation_performed": False,
        "missing_to_zero_performed": False,
        "tract_rows_dropped": False,
    }
    return MichiganPublicSources(ordered_geoids, households, components, model11_contract, lineage)


def load_verified_public_dependencies(repository_root: Path, data04_ready_dir: Path, geo05_support_dir: Path) -> tuple[MichiganPublicSources, SupportPackage]:
    sources = load_data04_public_sources(repository_root, data04_ready_dir)
    support = load_support_package(repository_root.resolve(), geo05_support_dir.resolve())
    require(
        tuple(tract.geoid for tract in support.tracts) == sources.ordered_geoids,
        "MODEL12_DATA04_GEO05_INVENTORY_MISMATCH",
        "accepted DATA-04 and GEO-05 inventories differ",
    )
    return sources, support


def _valid_household(value: Mapping[str, Any]) -> bool:
    return (
        value.get("status") == "valid"
        and isinstance(value.get("estimate"), (int, float))
        and isinstance(value.get("moe"), (int, float))
        and math.isfinite(float(value["estimate"]))
        and math.isfinite(float(value["moe"]))
        and float(value["estimate"]) >= 0
        and float(value["moe"]) >= 0
    )


def build_anchor_public_features(
    *,
    support: SupportPackage,
    sources: MichiganPublicSources,
    opaque_anchor_id: str,
    latitude: float,
    longitude: float,
    required_frozen_terms: Sequence[str],
) -> dict[str, Any]:
    spatial = evaluate_anchor_package(
        support,
        latitude=latitude,
        longitude=longitude,
        opaque_anchor_identity=opaque_anchor_id,
        opaque_anchor_lineage=FIELD_ANCHOR_LINEAGE,
        radii_m=RADII_M,
    )
    memberships = {float(item["radius_m"]): item for item in spatial["memberships"]}
    require(tuple(sorted(memberships)) == RADII_M, "MODEL12_GEO05_RADIUS_MISMATCH", "GEO-05 membership radii differ from the frozen MODEL radii")
    totals: list[float] = []
    moes: list[float] = []
    member_counts: list[int] = []
    for radius in RADII_M:
        member_geoids = list(memberships[radius]["member_geoids"])
        selected = [sources.households[geoid] for geoid in member_geoids]
        require(selected and all(_valid_household(value) for value in selected), "MODEL12_HOUSEHOLD_MEMBER_NONCOMPUTABLE", "one exact radius member lacks valid B11001 household evidence")
        totals.append(sum(float(value["estimate"]) for value in selected))
        moes.append(math.sqrt(sum(float(value["moe"]) ** 2 for value in selected)))
        member_counts.append(len(member_geoids))
    h3, h5, h7 = totals
    require(0 < h3 <= h5 <= h7, "MODEL12_HOUSEHOLD_FEATURE_NONCOMPUTABLE", "nested household opportunity is invalid")
    area3 = math.pi * 3.0**2
    outer_area = math.pi * (7.0**2 - 3.0**2)
    outer_households = h7 - h3
    features: dict[str, Any] = {
        "households_3mi": h3,
        "households_5mi": h5,
        "households_7mi": h7,
        "households_3mi_moe": moes[0],
        "households_5mi_moe": moes[1],
        "households_7mi_moe": moes[2],
        "relative_moe_5mi": moes[1] / h5,
        "tract_member_count_3mi": member_counts[0],
        "tract_member_count_5mi": member_counts[1],
        "tract_member_count_7mi": member_counts[2],
        "log_households_5mi": math.log1p(h5),
        "inner_household_share_3mi_of_7mi": h3 / h7,
        "log_inner_outer_household_density_gradient": math.log1p(h3 / area3) - math.log1p(outer_households / outer_area),
        "anchor_tract_geoid": spatial["containing_tract_geoid"],
    }
    five_mile_geoids = list(memberships[8046.72]["member_geoids"])
    household_weights = {geoid: float(sources.households[geoid]["estimate"]) for geoid in five_mile_geoids}
    profiles: dict[str, dict[str, Any]] = {}
    transformed: dict[str, float | None] = {}
    for spec in sources.model11_contract["candidate_measures"]:
        measure = str(spec["measure_id"])
        profile = _aggregate_measure(spec, five_mile_geoids, sources.components, household_weights)
        profiles[measure] = profile
        value = profile.get("value")
        if value is None:
            transformed[measure] = None
        else:
            numeric = float(value)
            require(math.isfinite(numeric) and numeric >= 0, "MODEL12_MULTIVARIATE_FEATURE_NONCOMPUTABLE", "one multivariate profile is invalid")
            transformed[measure] = math.log1p(numeric) if spec["transform"] == "log1p" else numeric
        features[measure] = transformed[measure]
    missing_required = [term for term in required_frozen_terms if not isinstance(features.get(term), (int, float)) or isinstance(features.get(term), bool) or not math.isfinite(float(features[term]))]
    completeness = list(spatial["support_completeness"])
    return {
        "opaque_anchor_id": opaque_anchor_id,
        "state": "PUBLIC_FEATURES_COMPUTABLE" if not missing_required else "MODEL_SCORE_NONCOMPUTABLE",
        "noncomputability_reasons": ["FROZEN_MODEL_INPUT_NONCOMPUTABLE:" + term for term in missing_required],
        "anchor": {"latitude": float(latitude), "longitude": float(longitude)},
        "containing_tract_geoid": spatial["containing_tract_geoid"],
        "member_counts": {
            "3mi": member_counts[0],
            "5mi": member_counts[1],
            "7mi": member_counts[2],
        },
        "public_features": features,
        "data03_feature_profiles": profiles,
        "required_frozen_feature_order": list(required_frozen_terms),
        "support_completeness": completeness,
        "any_support_truncation": any(item["extends_outside_michigan_support"] for item in completeness),
        "spatial_lineage": spatial["spatial_lineage"],
        "public_source_lineage": dict(sources.lineage),
        "imputation_performed": False,
        "member_tract_dropping_performed": False,
        "michigan_feature_selection_performed": False,
        "michigan_redundancy_screen_performed": False,
    }


def _validate_anchor_inputs(anchors: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    require(isinstance(anchors, Sequence) and not isinstance(anchors, (str, bytes)) and bool(anchors), "MODEL12_ANCHOR_INPUT_INVALID", "at least one local anchor is required")
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in anchors:
        require(isinstance(raw, Mapping) and set(raw) == {"opaque_anchor_id", "latitude", "longitude"}, "MODEL12_ANCHOR_INPUT_SCHEMA_INVALID", "anchor input fields must be exactly opaque_anchor_id latitude and longitude")
        anchor_id = raw.get("opaque_anchor_id")
        latitude = raw.get("latitude")
        longitude = raw.get("longitude")
        require(isinstance(anchor_id, str) and bool(anchor_id.strip()) and anchor_id not in seen, "MODEL12_ANCHOR_ID_INVALID", "opaque anchor identity is missing or duplicate")
        require(all(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value)) for value in (latitude, longitude)), "MODEL12_ANCHOR_COORDINATE_INVALID", "anchor coordinate is absent or nonfinite")
        seen.add(anchor_id)
        output.append({"opaque_anchor_id": anchor_id, "latitude": float(latitude), "longitude": float(longitude)})
    return output


def score_anchor_batch(
    *,
    anchors: Sequence[Mapping[str, Any]],
    support: SupportPackage,
    sources: MichiganPublicSources,
    frozen: FrozenScoringState,
) -> list[dict[str, Any]]:
    """Apply one common target-free public-feature and frozen-score path."""

    validated = _validate_anchor_inputs(anchors)
    output: list[dict[str, Any]] = []
    for anchor in validated:
        anchor_id = str(anchor["opaque_anchor_id"])
        try:
            evidence = build_anchor_public_features(
                support=support,
                sources=sources,
                opaque_anchor_id=anchor_id,
                latitude=float(anchor["latitude"]),
                longitude=float(anchor["longitude"]),
                required_frozen_terms=frozen.terms,
            )
            if evidence["state"] == "MODEL_SCORE_NONCOMPUTABLE":
                scores = None
            else:
                scores = frozen.score(evidence["public_features"])
            output.append(
                {
                    **evidence,
                    "score_computability_status": "MODEL_SCORE_COMPUTABLE" if scores is not None else "MODEL_SCORE_NONCOMPUTABLE",
                    "household_opportunity": None if scores is None else scores["household_opportunity"],
                    "customer_fit_proxy": None if scores is None else scores["customer_fit_proxy"],
                    "modeled_target_mass": None if scores is None else scores["modeled_target_mass"],
                    "model_lineage": frozen.lineage,
                }
            )
        except ConformanceError as exc:
            output.append(
                {
                    "opaque_anchor_id": anchor_id,
                    "state": "MODEL_SCORE_NONCOMPUTABLE",
                    "score_computability_status": "MODEL_SCORE_NONCOMPUTABLE",
                    "noncomputability_reasons": [exc.code],
                    "anchor": {"latitude": float(anchor["latitude"]), "longitude": float(anchor["longitude"])},
                    "containing_tract_geoid": None,
                    "member_counts": None,
                    "public_features": None,
                    "data03_feature_profiles": None,
                    "required_frozen_feature_order": list(frozen.terms),
                    "support_completeness": None,
                    "any_support_truncation": False,
                    "spatial_lineage": None,
                    "public_source_lineage": dict(sources.lineage),
                    "household_opportunity": None,
                    "customer_fit_proxy": None,
                    "modeled_target_mass": None,
                    "model_lineage": frozen.lineage,
                    "imputation_performed": False,
                    "member_tract_dropping_performed": False,
                    "michigan_feature_selection_performed": False,
                    "michigan_redundancy_screen_performed": False,
                }
            )
    require(len(output) == len(validated), "MODEL12_ANCHOR_ACCOUNTING_FAILED", "anchor scoring output does not account for every input")
    return output
