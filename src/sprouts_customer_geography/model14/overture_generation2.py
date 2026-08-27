"""Target-blind Overture Places feature generation for exploratory MODEL-14 Generation 2."""

from __future__ import annotations

from collections import Counter
import copy
import csv
from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence
from zipfile import ZipFile

from shapely.geometry import Point
from shapely.geometry.base import BaseGeometry
from shapely.strtree import STRtree

from sprouts_customer_geography.pipe01.canonical import content_digest, file_sha256, write_json_exclusive
from sprouts_customer_geography.pipe01.errors import ConformanceError, require
from sprouts_customer_geography.pipe01.production import (
    Geo03ProductionTransformer,
    _read_dbf_records,
    _read_shapefile_polygons,
)
from sprouts_customer_geography.pipe02.resolver import _is_within

from .public import STATE_CONFIG, _five_mile_memberships, _json_object, _load_tract_inventory


CONTRACT_ID = "MODEL14_OVERTURE_GENERATION2_EXPERIMENTAL_PUBLIC_FEATURE_CONTRACT_V1"
COMMITMENT_ID = "MODEL14_OVERTURE_GENERATION2_TARGET_BLIND_PUBLIC_FEATURE_COMMITMENT_V1"
FREEZE_ID = "MODEL14_OVERTURE_GENERATION2_TARGET_BLIND_PUBLIC_FREEZE_V1"
CONTRACT_PATH = "config/model14/experimental_overture_generation2_contract.json"
COMMITMENT_PATH = "config/model14/target_blind_overture_generation2_commitment.json"
COMPONENT_FILENAME = "model14_overture_generation2_tract_components.csv"
MATRIX_FILENAME = "model14_overture_generation2_tract_feature_matrix.csv"
FREEZE_FILENAME = "model14_overture_generation2_target_blind_public_freeze.json"
READY_FILENAME = "READY.json"

COMPONENT_COUNT_FIELDS = (
    "commercial_place_count",
    "shopping_place_count",
    "food_and_drink_place_count",
    "restaurant_place_count",
    "grocery_place_count",
    "fitness_wellness_place_count",
    "health_care_place_count",
)

FEATURE_IDS = (
    "overture_log_commercial_places_tract",
    "overture_log_shopping_places_tract",
    "overture_log_food_and_drink_places_tract",
    "overture_log_grocery_places_tract",
    "overture_log_commercial_places_5mi",
    "overture_log_shopping_places_5mi",
    "overture_log_food_and_drink_places_5mi",
    "overture_log_restaurant_places_5mi",
    "overture_log_grocery_places_5mi",
    "overture_log_fitness_wellness_places_5mi",
    "overture_log_health_care_places_5mi",
    "overture_basic_category_gini_simpson_diversity_5mi",
    "overture_grocery_share_of_commercial_5mi",
    "overture_shopping_share_of_commercial_5mi",
    "overture_food_and_drink_share_of_commercial_5mi",
)

INTENSITY_FEATURES = FEATURE_IDS[:11]
MIX_DIVERSITY_FEATURES = FEATURE_IDS[11:]
FEATURE_SUBFAMILIES = {
    **{feature: "intensity_count" for feature in INTENSITY_FEATURES},
    **{feature: "mix_diversity" for feature in MIX_DIVERSITY_FEATURES},
}
UNIT_INTERVAL_FEATURES = frozenset(MIX_DIVERSITY_FEATURES)


def load_generation2_contract(repository_root: Path) -> dict[str, Any]:
    """Load and verify the separately frozen exploratory Generation-2 contract."""
    contract = _json_object(repository_root / CONTRACT_PATH, "MODEL14_G2_CONTRACT_MISSING")
    semantic = copy.deepcopy(contract)
    recorded = semantic.pop("content_sha256", None)
    catalog = tuple(str(item.get("feature_id")) for item in contract.get("feature_catalog", []))
    candidate_sets = contract.get("candidate_sets", {})
    require(
        contract.get("artifact_id") == CONTRACT_ID
        and contract.get("version") == "1.0.0"
        and contract.get("status") == "EXPLORATORY_GENERATION2_TARGET_BLIND_DEFINITIONS_FROZEN"
        and contract.get("generation") == 2
        and contract.get("exploratory") is True
        and contract.get("confirmatory") is False
        and contract.get("prior_generation_aggregate_results_known") is True
        and contract.get("production_source_authority") is False
        and recorded == content_digest(semantic)
        and catalog == FEATURE_IDS
        and contract.get("feature_count") == len(FEATURE_IDS)
        and tuple(candidate_sets) == (
            "A_model13_reproduced_generation2",
            "B_model13_plus_all_generation2_commercial",
            "C_model13_plus_generation2_intensity",
            "D_model13_plus_generation2_mix_diversity",
        )
        and contract.get("source", {}).get("release") == "2026-07-22.0"
        and contract.get("source", {}).get("schema_version") == "v1.18.0"
        and contract.get("source", {}).get("retrieval_date") == "2026-08-27"
        and contract.get("source", {}).get("query_identity")
        == "MODEL14_OVERTURE_PLACES_MI_WI_EXACT_POINT_ENVELOPE_V1"
        and contract.get("source", {}).get("deprecated_categories_field_used") is False
        and contract.get("geography", {}).get("source_point_crs") == "EPSG:4326"
        and contract.get("geography", {}).get("accepted_tract_polygon_crs") == "EPSG:4269"
        and contract.get("geography", {}).get("production_datum_authority_claimed") is False
        and contract.get("taxonomy_rules", {}).get("hierarchy_values_must_be_unique") is True,
        "MODEL14_G2_CONTRACT_INVALID",
        "MODEL-14 Generation-2 contract differs from its frozen exploratory authority",
    )
    return contract


def load_generation2_commitment(repository_root: Path) -> dict[str, Any]:
    """Load and verify the disclosure-safe Generation-2 target-blind commitment."""
    root = repository_root.resolve()
    contract = load_generation2_contract(root)
    commitment = _json_object(root / COMMITMENT_PATH, "MODEL14_G2_COMMITMENT_MISSING")
    semantic = copy.deepcopy(commitment)
    recorded = semantic.pop("content_sha256", None)
    chronology = commitment.get("chronology", {})
    matrix = commitment.get("tract_matrix", {})
    source = commitment.get("source", {})
    catalog = commitment.get("feature_catalog", {})
    require(
        commitment.get("artifact_id") == COMMITMENT_ID
        and commitment.get("version") == "1.0.0"
        and commitment.get("state") == "EXPLORATORY_GENERATION2_TARGET_BLIND_PUBLIC_FEATURES_FROZEN"
        and commitment.get("controlling_task") == "MODEL-14"
        and commitment.get("generation") == 2
        and commitment.get("exploratory") is True
        and commitment.get("confirmatory") is False
        and commitment.get("prior_generation_aggregate_results_known") is True
        and commitment.get("generation1_checkpoint") == "b41f0e8d96c717654e861d1673d87d57cf42b0cf"
        and commitment.get("generation1_evidence_preserved_unchanged") is True
        and commitment.get("production_source_authority") is False
        and recorded == content_digest(semantic)
        and commitment.get("contract", {}).get("artifact_id") == CONTRACT_ID
        and commitment.get("contract", {}).get("content_sha256") == contract["content_sha256"]
        and chronology.get("generation2_definitions_frozen_before_generation2_target_access") is True
        and chronology.get("generation2_full_tract_matrix_frozen_before_generation2_target_access") is True
        and chronology.get("generation2_target_values_accessed") == 0
        and chronology.get("generation2_protected_anchor_rows_accessed") == 0
        and chronology.get("sealed_or_prospective_evidence_accessed") is False
        and source.get("release") == "2026-07-22.0"
        and source.get("schema_version") == "v1.18.0"
        and source.get("retrieval_date") == "2026-08-27"
        and source.get("query_identity") == "MODEL14_OVERTURE_PLACES_MI_WI_EXACT_POINT_ENVELOPE_V1"
        and source.get("duckdb_version") == "1.5.5"
        and source.get("deprecated_categories_field_used") is False
        and source.get("names_brands_providers_used") is False
        and catalog.get("feature_count") == len(FEATURE_IDS)
        and tuple(catalog.get("feature_order", [])) == FEATURE_IDS
        and matrix.get("tract_count") == 4559
        and matrix.get("michigan_tract_count") == 3017
        and matrix.get("wisconsin_tract_count") == 1542
        and matrix.get("accepted_tract_key_reconciliation") is True
        and matrix.get("tract_rows_dropped") is False
        and matrix.get("missing_to_zero") is False
        and matrix.get("independent_materialization_count") == 2
        and matrix.get("determinism_state") == "DETERMINISTIC_BYTE_IDENTICAL"
        and tuple(commitment.get("candidate_sets_frozen", []))
        == (
            "A_model13_reproduced_generation2",
            "B_model13_plus_all_generation2_commercial",
            "C_model13_plus_generation2_intensity",
            "D_model13_plus_generation2_mix_diversity",
        )
        and commitment.get("generation1_combination_included") is False
        and commitment.get("protected_characteristic_scoring_feature_used") is False,
        "MODEL14_G2_COMMITMENT_INVALID",
        "MODEL-14 Generation-2 target-blind commitment differs from its frozen semantics",
    )
    return commitment


@dataclass(frozen=True)
class AcceptedTractSupport:
    state: str
    inventory: Any
    geometries: Mapping[str, BaseGeometry]


@dataclass(frozen=True)
class Generation2Freeze:
    directory: Path
    report: Mapping[str, Any]
    components: Mapping[str, Mapping[str, Any]]
    rows: Mapping[str, Mapping[str, Any]]


def _accepted_tract_support(
    repository_root: Path,
    state: str,
    transformer: Geo03ProductionTransformer,
) -> AcceptedTractSupport:
    config = STATE_CONFIG[state]
    source = repository_root / str(config["tiger_source"])
    manifest = _json_object(
        repository_root / str(config["tiger_manifest"]),
        "MODEL14_G2_TIGER_MANIFEST_MISSING",
    )
    require(
        source.is_file() and file_sha256(source) == manifest.get("byte_sha256"),
        "MODEL14_G2_TIGER_SOURCE_MISMATCH",
        "accepted TIGER source bytes differ for Generation 2",
    )
    stem = str(manifest["source_filename"]).removesuffix(".zip")
    with ZipFile(source) as archive:
        projection = archive.read(f"{stem}.prj").decode("ascii")
        records = _read_dbf_records(archive.read(f"{stem}.dbf"))
        geometries = _read_shapefile_polygons(archive.read(f"{stem}.shp"))
    require(
        "GCS_North_American_1983" in projection
        and "GRS_1980" in projection
        and len(records) == len(geometries),
        "MODEL14_G2_TIGER_GEOMETRY_INVALID",
        "accepted TIGER tract geometry differs for Generation 2",
    )
    inventory = _load_tract_inventory(repository_root, state, transformer)
    mapped: dict[str, BaseGeometry] = {}
    for record, geometry in zip(records, geometries):
        geoid = str(record.get("GEOID", ""))
        require(
            geoid in inventory.rows and geoid not in mapped and geometry.is_valid and not geometry.is_empty,
            "MODEL14_G2_TIGER_GEOMETRY_INVALID",
            "one accepted TIGER tract geometry is invalid or duplicated",
        )
        mapped[geoid] = geometry
    require(
        set(mapped) == set(inventory.rows),
        "MODEL14_G2_TIGER_KEY_MISMATCH",
        "accepted TIGER tract geometry does not exactly reconcile",
    )
    return AcceptedTractSupport(state, inventory, dict(sorted(mapped.items())))


def _source_report(source_extract: Path, report_path: Path, contract: Mapping[str, Any]) -> dict[str, Any]:
    report = _json_object(report_path, "MODEL14_G2_SOURCE_REPORT_MISSING")
    expected_columns = [
        "id",
        "version",
        "longitude",
        "latitude",
        "bbox_xmin",
        "bbox_xmax",
        "bbox_ymin",
        "bbox_ymax",
        "confidence",
        "operating_status",
        "basic_category",
        "taxonomy_primary",
        "taxonomy_hierarchy",
    ]
    require(
        source_extract.is_file()
        and report.get("release") == contract["source"]["release"]
        and report.get("schema") == contract["source"]["schema_version"]
        and report.get("source") == contract["source"]["cloud_uri"]
        and report.get("retrieval_date") == contract["source"]["retrieval_date"]
        and report.get("query_identity") == contract["source"]["query_identity"]
        and report.get("extraction_predicate") == contract["source"]["extraction_predicate"]
        and report.get("duckdb_version") == "1.5.5"
        and report.get("selected_columns") == expected_columns
        and report.get("deprecated_category_field_selected") is False
        and report.get("names_brands_providers_selected") is False
        and source_extract.stat().st_size == int(report.get("byte_length", -1))
        and file_sha256(source_extract) == report.get("sha256")
        and int(report.get("row_count", 0)) > 0,
        "MODEL14_G2_SOURCE_EXTRACT_INVALID",
        "pinned Overture Generation-2 source extract differs",
    )
    return report


def _empty_component(state: str, geoid: str) -> dict[str, Any]:
    return {
        "tract_geoid": geoid,
        "state": state,
        "state_fips": geoid[:2],
        **{field: 0 for field in COMPONENT_COUNT_FIELDS},
        "basic_category_eligible_count": 0,
        "basic_category_counts": {},
    }


def _parse_confidence(raw: str) -> float | None:
    if raw == "":
        return None
    try:
        value = float(raw)
    except ValueError as exc:
        raise ConformanceError("MODEL14_G2_CONFIDENCE_INVALID", "one Overture confidence value is invalid") from exc
    require(
        math.isfinite(value) and 0.0 <= value <= 1.0,
        "MODEL14_G2_CONFIDENCE_INVALID",
        "one Overture confidence value is outside [0, 1]",
    )
    return value


def _point_from_source(row: Mapping[str, str]) -> tuple[Point, bool]:
    try:
        longitude = float(row["longitude"])
        latitude = float(row["latitude"])
    except (KeyError, ValueError) as exc:
        raise ConformanceError("MODEL14_G2_PLACE_GEOMETRY_INVALID", "one Overture point geometry is invalid") from exc
    require(
        all(math.isfinite(value) for value in (longitude, latitude))
        and -180.0 <= longitude <= 180.0
        and -90.0 <= latitude <= 90.0,
        "MODEL14_G2_PLACE_GEOMETRY_INVALID",
        "one Overture point geometry is invalid",
    )
    raw_bbox = tuple(str(row.get(field, "")) for field in ("bbox_xmin", "bbox_xmax", "bbox_ymin", "bbox_ymax"))
    if all(value == "" for value in raw_bbox):
        return Point(longitude, latitude), False
    require(
        all(value != "" for value in raw_bbox),
        "MODEL14_G2_PLACE_BBOX_INVALID",
        "one optional Overture bbox is only partially populated",
    )
    try:
        xmin, xmax, ymin, ymax = (float(value) for value in raw_bbox)
    except ValueError as exc:
        raise ConformanceError("MODEL14_G2_PLACE_BBOX_INVALID", "one Overture bbox is invalid") from exc
    require(
        all(math.isfinite(value) for value in (xmin, xmax, ymin, ymax))
        and -180.0 <= xmin <= longitude <= xmax <= 180.0
        and -90.0 <= ymin <= latitude <= ymax <= 90.0,
        "MODEL14_G2_PLACE_BBOX_INVALID",
        "one present Overture bbox does not contain its point geometry",
    )
    return Point(longitude, latitude), True


def _assign_point(
    point: Point,
    tree: STRtree,
    geometries: Sequence[BaseGeometry],
) -> tuple[int | None, str]:
    candidate_indices = [int(value) for value in tree.query(point)]
    covered = [index for index in candidate_indices if geometries[index].covers(point)]
    if len(covered) == 1:
        return covered[0], "assigned"
    if len(covered) > 1:
        contained = [index for index in covered if geometries[index].contains(point)]
        if len(contained) == 1:
            return contained[0], "assigned_strict_contains"
        return None, "boundary_ambiguous"
    return None, "outside_accepted_support"


def _load_tract_components(
    source_extract: Path,
    supports: Mapping[str, AcceptedTractSupport],
    contract: Mapping[str, Any],
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    ordered_geoids = [
        geoid
        for state in ("MI", "WI")
        for geoid in sorted(supports[state].geometries)
    ]
    geometries = [supports["MI"].geometries[geoid] if geoid.startswith("26") else supports["WI"].geometries[geoid] for geoid in ordered_geoids]
    tree = STRtree(geometries)
    components = {
        geoid: _empty_component("MI" if geoid.startswith("26") else "WI", geoid)
        for geoid in ordered_geoids
    }
    rules = contract["taxonomy_rules"]
    commercial_l0 = frozenset(str(value) for value in rules["commercial_top_level_categories"])
    fitness_ancestors = frozenset(str(value) for value in rules["fitness_wellness_ancestors"])
    counters: Counter[str] = Counter()
    assigned_by_state: Counter[str] = Counter()
    top_level_counts: Counter[str] = Counter()
    previous_id = ""
    expected_header = [
        "id",
        "version",
        "longitude",
        "latitude",
        "bbox_xmin",
        "bbox_xmax",
        "bbox_ymin",
        "bbox_ymax",
        "confidence",
        "operating_status",
        "basic_category",
        "taxonomy_primary",
        "taxonomy_hierarchy",
    ]
    with source_extract.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        require(reader.fieldnames == expected_header, "MODEL14_G2_SOURCE_SCHEMA_INVALID", "Overture extract columns differ")
        for row in reader:
            counters["source_envelope_row_count"] += 1
            place_id = str(row["id"])
            require(
                bool(place_id) and (not previous_id or place_id > previous_id),
                "MODEL14_G2_PLACE_ID_DUPLICATE_OR_UNSORTED",
                "Overture GERS ids are duplicated or non-monotonic",
            )
            previous_id = place_id
            try:
                version = int(row["version"])
            except ValueError as exc:
                raise ConformanceError("MODEL14_G2_PLACE_VERSION_INVALID", "one Overture version is invalid") from exc
            require(version >= 0, "MODEL14_G2_PLACE_VERSION_INVALID", "one Overture version is negative")
            point, bbox_present = _point_from_source(row)
            counters["source_present_bbox_count"] += bbox_present
            counters["source_null_bbox_count"] += not bbox_present
            confidence = _parse_confidence(str(row["confidence"]))
            status = str(row["operating_status"])
            require(
                status in {"", "open", "temporarily_closed", "permanently_closed"},
                "MODEL14_G2_OPERATING_STATUS_INVALID",
                "one Overture operating status differs from schema v1.18.0",
            )
            if status in {"temporarily_closed", "permanently_closed"}:
                counters["excluded_known_closed_status"] += 1
                counters["permanently_closed_nonzero_confidence"] += (
                    status == "permanently_closed" and confidence not in {None, 0.0}
                )
                continue
            if confidence is None or confidence <= 0.7:
                counters["excluded_confidence_not_above_0_7"] += 1
                continue
            counters["eligible_open_status"] += status == "open"
            counters["eligible_unknown_status"] += status == ""
            raw_hierarchy = str(row["taxonomy_hierarchy"])
            primary = str(row["taxonomy_primary"])
            if not raw_hierarchy or not primary:
                counters["excluded_missing_taxonomy"] += 1
                continue
            try:
                hierarchy = json.loads(raw_hierarchy)
            except json.JSONDecodeError as exc:
                raise ConformanceError("MODEL14_G2_TAXONOMY_INVALID", "one Overture hierarchy is not JSON") from exc
            if not (
                isinstance(hierarchy, list)
                and hierarchy
                and all(isinstance(value, str) and value for value in hierarchy)
                and len(hierarchy) == len(set(hierarchy))
            ):
                counters["excluded_invalid_taxonomy_structure"] += 1
                continue
            if hierarchy[-1] != primary:
                counters["excluded_taxonomy_primary_hierarchy_mismatch"] += 1
                continue
            top_level = hierarchy[0]
            top_level_counts[top_level] += 1
            if top_level not in commercial_l0:
                counters["excluded_noncommercial_top_level"] += 1
                continue
            assigned_index, assignment = _assign_point(point, tree, geometries)
            if assigned_index is None:
                counters[assignment] += 1
                continue
            geoid = ordered_geoids[assigned_index]
            target = components[geoid]
            counters["assigned_commercial_place_count"] += 1
            counters[assignment] += 1
            assigned_by_state[str(target["state"])] += 1
            target["commercial_place_count"] += 1
            if top_level == str(rules["shopping_top_level"]):
                target["shopping_place_count"] += 1
            if top_level == str(rules["food_and_drink_top_level"]):
                target["food_and_drink_place_count"] += 1
            if top_level == str(rules["health_care_top_level"]):
                target["health_care_place_count"] += 1
            hierarchy_set = set(hierarchy)
            if str(rules["restaurant_ancestor"]) in hierarchy_set:
                target["restaurant_place_count"] += 1
            if str(rules["grocery_ancestor"]) in hierarchy_set:
                target["grocery_place_count"] += 1
            if hierarchy_set & fitness_ancestors:
                target["fitness_wellness_place_count"] += 1
            basic_category = str(row["basic_category"])
            if basic_category:
                basic_counts = target["basic_category_counts"]
                basic_counts[basic_category] = int(basic_counts.get(basic_category, 0)) + 1
                target["basic_category_eligible_count"] += 1
                counters["assigned_with_basic_category"] += 1
                counters["basic_category_not_in_primary_hierarchy"] += basic_category not in hierarchy_set
            else:
                counters["assigned_missing_basic_category"] += 1

    require(
        counters["source_envelope_row_count"] > 0
        and counters["assigned_commercial_place_count"] == sum(assigned_by_state.values())
        and len(components) == 4559
        and sum(row["state"] == "MI" for row in components.values()) == 3017
        and sum(row["state"] == "WI" for row in components.values()) == 1542,
        "MODEL14_G2_COMPONENT_ACCOUNTING_FAILED",
        "Overture tract component accounting differs",
    )
    return dict(sorted(components.items())), {
        **{key: int(value) for key, value in sorted(counters.items())},
        "assigned_commercial_place_count_by_state": dict(sorted(assigned_by_state.items())),
        "quality_status_taxonomy_top_level_counts": dict(sorted(top_level_counts.items())),
        "unique_gers_id_rule": "strictly increasing canonical extract; duplicate fails",
        "provider_identity_used": False,
        "name_brand_identity_used": False,
    }


def _ratio(numerator: int, denominator: int) -> float | None:
    return None if denominator == 0 else numerator / denominator


def aggregate_commercial_features(
    component_rows: Mapping[str, Mapping[str, Any]],
    member_geoids: Sequence[str],
    anchor_tract_geoid: str,
) -> dict[str, float | None]:
    """Aggregate frozen tract components under the accepted five-mile semantics."""
    members = list(member_geoids)
    require(
        members
        and len(members) == len(set(members))
        and anchor_tract_geoid in members
        and all(geoid in component_rows for geoid in members),
        "MODEL14_G2_CONTEXT_GEOID_INVALID",
        "Generation-2 context GEOIDs are invalid",
    )
    selected = [component_rows[geoid] for geoid in members]
    states = {str(row["state"]) for row in selected}
    require(
        len(states) == 1 and str(component_rows[anchor_tract_geoid]["state"]) in states,
        "MODEL14_G2_CONTEXT_STATE_MISMATCH",
        "Generation-2 five-mile context crosses state support",
    )
    totals = {
        field: sum(int(row[field]) for row in selected)
        for field in COMPONENT_COUNT_FIELDS
    }
    basic_counts: Counter[str] = Counter()
    for row in selected:
        basic_counts.update({str(key): int(value) for key, value in row["basic_category_counts"].items()})
    basic_total = sum(basic_counts.values())
    diversity = None
    if basic_total > 0:
        diversity = 1.0 - sum((value / basic_total) ** 2 for value in basic_counts.values())
    anchor = component_rows[anchor_tract_geoid]
    features: dict[str, float | None] = {
        "overture_log_commercial_places_tract": math.log1p(int(anchor["commercial_place_count"])),
        "overture_log_shopping_places_tract": math.log1p(int(anchor["shopping_place_count"])),
        "overture_log_food_and_drink_places_tract": math.log1p(int(anchor["food_and_drink_place_count"])),
        "overture_log_grocery_places_tract": math.log1p(int(anchor["grocery_place_count"])),
        "overture_log_commercial_places_5mi": math.log1p(totals["commercial_place_count"]),
        "overture_log_shopping_places_5mi": math.log1p(totals["shopping_place_count"]),
        "overture_log_food_and_drink_places_5mi": math.log1p(totals["food_and_drink_place_count"]),
        "overture_log_restaurant_places_5mi": math.log1p(totals["restaurant_place_count"]),
        "overture_log_grocery_places_5mi": math.log1p(totals["grocery_place_count"]),
        "overture_log_fitness_wellness_places_5mi": math.log1p(totals["fitness_wellness_place_count"]),
        "overture_log_health_care_places_5mi": math.log1p(totals["health_care_place_count"]),
        "overture_basic_category_gini_simpson_diversity_5mi": diversity,
        "overture_grocery_share_of_commercial_5mi": _ratio(totals["grocery_place_count"], totals["commercial_place_count"]),
        "overture_shopping_share_of_commercial_5mi": _ratio(totals["shopping_place_count"], totals["commercial_place_count"]),
        "overture_food_and_drink_share_of_commercial_5mi": _ratio(totals["food_and_drink_place_count"], totals["commercial_place_count"]),
    }
    require(
        tuple(features) == FEATURE_IDS
        and all(value is None or (math.isfinite(value) and (feature not in UNIT_INTERVAL_FEATURES or 0.0 <= value <= 1.0)) for feature, value in features.items()),
        "MODEL14_G2_FEATURE_VALUE_INVALID",
        "one Generation-2 commercial feature is invalid",
    )
    return features


def _numeric_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, int):
        return str(value)
    return format(float(value), ".17g")


def _write_components(path: Path, rows: Mapping[str, Mapping[str, Any]]) -> None:
    header = [
        "tract_geoid",
        "state",
        "state_fips",
        *COMPONENT_COUNT_FIELDS,
        "basic_category_eligible_count",
        "basic_category_counts_json",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header, lineterminator="\n")
        writer.writeheader()
        for geoid in sorted(rows):
            row = rows[geoid]
            writer.writerow({
                "tract_geoid": geoid,
                "state": row["state"],
                "state_fips": row["state_fips"],
                **{field: int(row[field]) for field in COMPONENT_COUNT_FIELDS},
                "basic_category_eligible_count": int(row["basic_category_eligible_count"]),
                "basic_category_counts_json": json.dumps(
                    row["basic_category_counts"],
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=True,
                ),
            })


def _write_matrix(path: Path, rows: Mapping[str, Mapping[str, Any]]) -> None:
    header = ["tract_geoid", "state", "state_fips", *FEATURE_IDS]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header, lineterminator="\n")
        writer.writeheader()
        for geoid in sorted(rows):
            row = rows[geoid]
            writer.writerow({
                "tract_geoid": geoid,
                "state": row["state"],
                "state_fips": row["state_fips"],
                **{feature: _numeric_text(row.get(feature)) for feature in FEATURE_IDS},
            })


def _feature_coverage(rows: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    coverage: dict[str, Any] = {}
    for state in ("MI", "WI"):
        state_rows = [row for row in rows.values() if row["state"] == state]
        coverage[state] = {
            "tract_count": len(state_rows),
            "features": {
                feature: {
                    "observed_count": sum(row[feature] is not None for row in state_rows),
                    "missing_count": sum(row[feature] is None for row in state_rows),
                    "minimum": min((float(row[feature]) for row in state_rows if row[feature] is not None), default=None),
                    "maximum": max((float(row[feature]) for row in state_rows if row[feature] is not None), default=None),
                }
                for feature in FEATURE_IDS
            },
        }
    return coverage


def _assert_public_paths(
    repository_root: Path,
    source_extract: Path,
    source_report_path: Path,
    output_dir: Path,
) -> tuple[Path, Path, Path, Path]:
    root = repository_root.resolve()
    outputs = (root / "outputs").resolve()
    extract = source_extract.resolve()
    report = source_report_path.resolve()
    output = output_dir.resolve()
    require(
        _is_within(extract, outputs)
        and _is_within(report, outputs)
        and _is_within(output, outputs)
        and output != outputs
        and not output.exists(),
        "MODEL14_G2_PUBLIC_PATH_INVALID",
        "Generation-2 public inputs and output must use bounded ignored output paths",
    )
    return root, extract, report, output


def materialize_generation2_public_freeze(
    *,
    repository_root: Path,
    source_extract: Path,
    source_report_path: Path,
    output_dir: Path,
) -> Generation2Freeze:
    """Materialize one immutable, target-blind Generation-2 public tract freeze."""
    root, extract, source_report_file, output = _assert_public_paths(
        repository_root,
        source_extract,
        source_report_path,
        output_dir,
    )
    contract = load_generation2_contract(root)
    source_report = _source_report(extract, source_report_file, contract)
    geo03 = _json_object(
        root / "config/geo/geo03_internal_point_membership_spatial_spec.json",
        "MODEL14_G2_GEO03_AUTHORITY_MISSING",
    )
    transformer = Geo03ProductionTransformer(geo03)
    supports = {
        state: _accepted_tract_support(root, state, transformer)
        for state in ("MI", "WI")
    }
    components, assignment = _load_tract_components(extract, supports, contract)
    require(
        assignment["source_envelope_row_count"] == int(source_report["row_count"]),
        "MODEL14_G2_SOURCE_ROW_ACCOUNTING_FAILED",
        "Generation-2 source extract row accounting differs",
    )
    matrix: dict[str, dict[str, Any]] = {}
    membership_reports: dict[str, Any] = {}
    for state in ("MI", "WI"):
        memberships, membership_report = _five_mile_memberships(
            supports[state].inventory,
            float(contract["geography"]["model_context_radius_m"]),
        )
        membership_reports[state] = membership_report
        for geoid in sorted(supports[state].inventory.rows):
            matrix[geoid] = {
                "tract_geoid": geoid,
                "state": state,
                "state_fips": geoid[:2],
                **aggregate_commercial_features(components, memberships[geoid], geoid),
            }
    require(
        set(matrix) == set(components)
        and len(matrix) == int(contract["freeze"]["expected_tract_row_count"])
        and sum(row["state"] == "MI" for row in matrix.values()) == int(contract["freeze"]["expected_michigan_row_count"])
        and sum(row["state"] == "WI" for row in matrix.values()) == int(contract["freeze"]["expected_wisconsin_row_count"]),
        "MODEL14_G2_MATRIX_KEY_RECONCILIATION_FAILED",
        "Generation-2 matrix does not exactly reconcile to accepted tract keys",
    )
    output.mkdir(parents=True)
    component_path = output / COMPONENT_FILENAME
    matrix_path = output / MATRIX_FILENAME
    _write_components(component_path, components)
    _write_matrix(matrix_path, matrix)
    freeze: dict[str, Any] = {
        "artifact_id": FREEZE_ID,
        "version": "1.0.0",
        "state": "TARGET_BLIND_GENERATION2_PUBLIC_FEATURES_FROZEN",
        "controlling_task": "MODEL-14",
        "generation": 2,
        "exploratory": True,
        "confirmatory": False,
        "prior_generation_aggregate_results_known": True,
        "production_source_authority": False,
        "contract": {
            "artifact_id": CONTRACT_ID,
            "content_sha256": contract["content_sha256"],
        },
        "chronology": {
            "generation2_definitions_frozen_before_generation2_target_access": True,
            "generation2_matrix_frozen_before_generation2_target_access": True,
            "generation2_target_values_accessed": 0,
            "generation2_protected_anchor_rows_accessed": 0,
            "sealed_or_prospective_evidence_accessed": False,
        },
        "source": {
            "publisher": contract["source"]["publisher"],
            "release": contract["source"]["release"],
            "schema_version": contract["source"]["schema_version"],
            "extract_row_count": int(source_report["row_count"]),
            "extract_byte_length": int(source_report["byte_length"]),
            "extract_sha256": source_report["sha256"],
            "deprecated_categories_field_used": False,
            "names_brands_providers_used": False,
        },
        "quality_status_identity_rules": copy.deepcopy(contract["quality_status_identity_rules"]),
        "taxonomy_rules": copy.deepcopy(contract["taxonomy_rules"]),
        "source_and_assignment_accounting": assignment,
        "geography": {
            "tract_count": len(matrix),
            "michigan_tract_count": sum(row["state"] == "MI" for row in matrix.values()),
            "wisconsin_tract_count": sum(row["state"] == "WI" for row in matrix.values()),
            "accepted_tract_key_reconciliation": True,
            "membership": membership_reports,
        },
        "features": {
            "feature_count": len(FEATURE_IDS),
            "feature_order": list(FEATURE_IDS),
            "subfamily_feature_count": {
                "intensity_count": len(INTENSITY_FEATURES),
                "mix_diversity": len(MIX_DIVERSITY_FEATURES),
            },
            "coverage": _feature_coverage(matrix),
            "missing_to_zero": False,
        },
        "files": {
            COMPONENT_FILENAME: {
                "byte_length": component_path.stat().st_size,
                "sha256": file_sha256(component_path),
            },
            MATRIX_FILENAME: {
                "byte_length": matrix_path.stat().st_size,
                "sha256": file_sha256(matrix_path),
            },
        },
        "outside_tracked_git": True,
        "ready_marker_written_last": True,
    }
    freeze["content_sha256"] = content_digest(freeze)
    freeze_path = output / FREEZE_FILENAME
    write_json_exclusive(freeze_path, freeze)
    write_json_exclusive(output / READY_FILENAME, {
        "state": "READY",
        "artifact_id": FREEZE_ID,
        "freeze_file_sha256": file_sha256(freeze_path),
        "freeze_semantic_content_sha256": freeze["content_sha256"],
        "component_file_sha256": freeze["files"][COMPONENT_FILENAME]["sha256"],
        "matrix_file_sha256": freeze["files"][MATRIX_FILENAME]["sha256"],
        "generation2_target_values_accessed": 0,
        "generation2_protected_anchor_rows_accessed": 0,
        "ready_marker_written_last": True,
    })
    return Generation2Freeze(output, freeze, components, matrix)


def _load_components(path: Path) -> dict[str, dict[str, Any]]:
    expected_header = [
        "tract_geoid",
        "state",
        "state_fips",
        *COMPONENT_COUNT_FIELDS,
        "basic_category_eligible_count",
        "basic_category_counts_json",
    ]
    output: dict[str, dict[str, Any]] = {}
    previous = ""
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        require(reader.fieldnames == expected_header, "MODEL14_G2_COMPONENT_SCHEMA_INVALID", "Generation-2 component columns differ")
        for source in reader:
            geoid = str(source["tract_geoid"])
            require(
                len(geoid) == 11
                and geoid.isdigit()
                and (not previous or geoid > previous),
                "MODEL14_G2_COMPONENT_KEY_INVALID",
                "Generation-2 component key is invalid, duplicated, or unsorted",
            )
            previous = geoid
            try:
                counts = {field: int(source[field]) for field in COMPONENT_COUNT_FIELDS}
                basic_total = int(source["basic_category_eligible_count"])
                basic_counts = json.loads(source["basic_category_counts_json"])
            except (ValueError, json.JSONDecodeError) as exc:
                raise ConformanceError("MODEL14_G2_COMPONENT_VALUE_INVALID", "one Generation-2 component value is invalid") from exc
            require(
                source["state"] in {"MI", "WI"}
                and source["state_fips"] == geoid[:2]
                and ((source["state"] == "MI" and geoid.startswith("26")) or (source["state"] == "WI" and geoid.startswith("55")))
                and all(value >= 0 for value in counts.values())
                and isinstance(basic_counts, dict)
                and all(isinstance(key, str) and key and isinstance(value, int) and value > 0 for key, value in basic_counts.items())
                and basic_total == sum(basic_counts.values())
                and counts["shopping_place_count"] <= counts["commercial_place_count"]
                and counts["food_and_drink_place_count"] <= counts["commercial_place_count"]
                and counts["health_care_place_count"] <= counts["commercial_place_count"]
                and counts["restaurant_place_count"] <= counts["food_and_drink_place_count"]
                and counts["grocery_place_count"] <= counts["shopping_place_count"],
                "MODEL14_G2_COMPONENT_VALUE_INVALID",
                "one Generation-2 component row violates frozen count semantics",
            )
            output[geoid] = {
                "tract_geoid": geoid,
                "state": source["state"],
                "state_fips": source["state_fips"],
                **counts,
                "basic_category_eligible_count": basic_total,
                "basic_category_counts": dict(sorted(basic_counts.items())),
            }
    return output


def _load_matrix(path: Path) -> dict[str, dict[str, Any]]:
    expected_header = ["tract_geoid", "state", "state_fips", *FEATURE_IDS]
    output: dict[str, dict[str, Any]] = {}
    previous = ""
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        require(reader.fieldnames == expected_header, "MODEL14_G2_MATRIX_SCHEMA_INVALID", "Generation-2 matrix columns differ")
        for source in reader:
            geoid = str(source["tract_geoid"])
            require(
                len(geoid) == 11
                and geoid.isdigit()
                and (not previous or geoid > previous),
                "MODEL14_G2_MATRIX_KEY_INVALID",
                "Generation-2 matrix key is invalid, duplicated, or unsorted",
            )
            previous = geoid
            row: dict[str, Any] = {
                "tract_geoid": geoid,
                "state": source["state"],
                "state_fips": source["state_fips"],
            }
            for feature in FEATURE_IDS:
                raw = source[feature]
                if raw == "":
                    row[feature] = None
                    continue
                try:
                    value = float(raw)
                except ValueError as exc:
                    raise ConformanceError("MODEL14_G2_MATRIX_VALUE_INVALID", "one Generation-2 feature is nonnumeric") from exc
                require(
                    math.isfinite(value)
                    and (feature not in UNIT_INTERVAL_FEATURES or 0.0 <= value <= 1.0),
                    "MODEL14_G2_MATRIX_VALUE_INVALID",
                    "one Generation-2 feature is invalid",
                )
                row[feature] = value
            output[geoid] = row
    return output


def load_generation2_public_freeze(directory: Path) -> Generation2Freeze:
    """Verify and load a complete outside-Git Generation-2 public freeze."""
    root = directory.resolve()
    report = _json_object(root / FREEZE_FILENAME, "MODEL14_G2_FREEZE_MISSING")
    ready = _json_object(root / READY_FILENAME, "MODEL14_G2_READY_MISSING")
    semantic = copy.deepcopy(report)
    recorded = semantic.pop("content_sha256", None)
    component_path = root / COMPONENT_FILENAME
    matrix_path = root / MATRIX_FILENAME
    require(
        report.get("artifact_id") == FREEZE_ID
        and report.get("state") == "TARGET_BLIND_GENERATION2_PUBLIC_FEATURES_FROZEN"
        and report.get("generation") == 2
        and report.get("exploratory") is True
        and report.get("confirmatory") is False
        and report.get("prior_generation_aggregate_results_known") is True
        and report.get("production_source_authority") is False
        and recorded == content_digest(semantic)
        and report.get("chronology", {}).get("generation2_target_values_accessed") == 0
        and report.get("chronology", {}).get("generation2_protected_anchor_rows_accessed") == 0
        and report.get("chronology", {}).get("sealed_or_prospective_evidence_accessed") is False
        and tuple(report.get("features", {}).get("feature_order", [])) == FEATURE_IDS
        and component_path.is_file()
        and matrix_path.is_file()
        and component_path.stat().st_size == int(report["files"][COMPONENT_FILENAME]["byte_length"])
        and matrix_path.stat().st_size == int(report["files"][MATRIX_FILENAME]["byte_length"])
        and file_sha256(component_path) == report["files"][COMPONENT_FILENAME]["sha256"]
        and file_sha256(matrix_path) == report["files"][MATRIX_FILENAME]["sha256"]
        and ready.get("state") == "READY"
        and ready.get("artifact_id") == FREEZE_ID
        and ready.get("freeze_file_sha256") == file_sha256(root / FREEZE_FILENAME)
        and ready.get("freeze_semantic_content_sha256") == recorded
        and ready.get("component_file_sha256") == report["files"][COMPONENT_FILENAME]["sha256"]
        and ready.get("matrix_file_sha256") == report["files"][MATRIX_FILENAME]["sha256"]
        and ready.get("generation2_target_values_accessed") == 0
        and ready.get("generation2_protected_anchor_rows_accessed") == 0
        and ready.get("ready_marker_written_last") is True,
        "MODEL14_G2_FREEZE_INVALID",
        "Generation-2 public freeze or READY marker differs",
    )
    components = _load_components(component_path)
    rows = _load_matrix(matrix_path)
    require(
        set(components) == set(rows)
        and len(rows) == 4559
        and sum(row["state"] == "MI" for row in rows.values()) == 3017
        and sum(row["state"] == "WI" for row in rows.values()) == 1542,
        "MODEL14_G2_FREEZE_KEY_RECONCILIATION_FAILED",
        "Generation-2 frozen tract keys do not reconcile",
    )
    return Generation2Freeze(root, report, components, rows)


def compare_generation2_public_freezes(first: Path, second: Path) -> dict[str, Any]:
    """Require byte-identical independent Generation-2 public materializations."""
    load_generation2_public_freeze(first)
    load_generation2_public_freeze(second)
    left = first.resolve()
    right = second.resolve()
    files = sorted(path.name for path in left.iterdir() if path.is_file())
    require(
        files == sorted(path.name for path in right.iterdir() if path.is_file())
        and files == sorted((COMPONENT_FILENAME, MATRIX_FILENAME, FREEZE_FILENAME, READY_FILENAME)),
        "MODEL14_G2_FREEZE_FILESET_MISMATCH",
        "Generation-2 freeze file sets differ",
    )
    left_hashes = {name: file_sha256(left / name) for name in files}
    right_hashes = {name: file_sha256(right / name) for name in files}
    require(
        left_hashes == right_hashes,
        "MODEL14_G2_FREEZE_NONDETERMINISTIC",
        "Generation-2 public freeze bytes differ across independent runs",
    )
    return {
        "report_id": "MODEL14_OVERTURE_GENERATION2_PUBLIC_FREEZE_DETERMINISM_V1",
        "state": "DETERMINISTIC_BYTE_IDENTICAL",
        "file_count": len(files),
        "file_sha256": left_hashes,
        "generation2_target_values_accessed": 0,
        "generation2_protected_anchor_rows_accessed": 0,
    }


def verify_generation2_commitment_against_freezes(
    *,
    repository_root: Path,
    first: Path,
    second: Path,
) -> dict[str, Any]:
    """Bind the tracked semantic commitment to two independent public freezes."""
    commitment = load_generation2_commitment(repository_root)
    comparison = compare_generation2_public_freezes(first, second)
    freeze = load_generation2_public_freeze(first)
    matrix = commitment["tract_matrix"]
    source = commitment["source"]
    accounting = commitment["source_quality_and_assignment_accounting"]
    frozen_accounting = freeze.report["source_and_assignment_accounting"]
    coverage = freeze.report["features"]["coverage"]
    require(
        source["source_envelope_row_count"] == freeze.report["source"]["extract_row_count"]
        and source["source_extract_byte_sha256"] == freeze.report["source"]["extract_sha256"]
        and freeze.report["contract"] == commitment["contract"]
        and matrix["component_matrix_byte_sha256"] == freeze.report["files"][COMPONENT_FILENAME]["sha256"]
        and matrix["feature_matrix_byte_sha256"] == freeze.report["files"][MATRIX_FILENAME]["sha256"]
        and matrix["freeze_semantic_content_sha256"] == freeze.report["content_sha256"]
        and accounting["excluded_known_closed_status"] == frozen_accounting["excluded_known_closed_status"]
        and accounting["permanently_closed_nonzero_confidence_reported"]
        == frozen_accounting["permanently_closed_nonzero_confidence"]
        and accounting["excluded_confidence_not_above_0_7"]
        == frozen_accounting["excluded_confidence_not_above_0_7"]
        and accounting["eligible_open_status"] == frozen_accounting["eligible_open_status"]
        and accounting["eligible_unknown_status"] == frozen_accounting["eligible_unknown_status"]
        and accounting["excluded_missing_taxonomy"] == frozen_accounting["excluded_missing_taxonomy"]
        and accounting["excluded_taxonomy_primary_hierarchy_mismatch"]
        == frozen_accounting["excluded_taxonomy_primary_hierarchy_mismatch"]
        and accounting["excluded_noncommercial_top_level"]
        == frozen_accounting["excluded_noncommercial_top_level"]
        and accounting["outside_accepted_support"] == frozen_accounting["outside_accepted_support"]
        and accounting["boundary_ambiguous"] == frozen_accounting["boundary_ambiguous"]
        and accounting["assigned_commercial_place_count"]
        == frozen_accounting["assigned_commercial_place_count"]
        and accounting["assigned_commercial_place_count_by_state"]
        == frozen_accounting["assigned_commercial_place_count_by_state"]
        and accounting["assigned_with_basic_category"] == frozen_accounting["assigned_with_basic_category"]
        and accounting["assigned_missing_basic_category"] == frozen_accounting["assigned_missing_basic_category"]
        and all(
            coverage[state]["features"][feature]["missing_count"] == 0
            for state in ("MI", "WI")
            for feature in INTENSITY_FEATURES
        )
        and max(
            coverage["MI"]["features"][feature]["missing_count"]
            for feature in MIX_DIVERSITY_FEATURES
        )
        == matrix["mix_diversity_maximum_missing_tract_count_by_state"]["MI"]
        and max(
            coverage["WI"]["features"][feature]["missing_count"]
            for feature in MIX_DIVERSITY_FEATURES
        )
        == matrix["mix_diversity_maximum_missing_tract_count_by_state"]["WI"],
        "MODEL14_G2_COMMITMENT_FREEZE_MISMATCH",
        "Generation-2 tracked commitment does not bind the independently reproduced public freeze",
    )
    return {
        "state": "GENERATION2_TARGET_BLIND_COMMITMENT_VERIFIED",
        "generation": 2,
        "exploratory": True,
        "tract_count": matrix["tract_count"],
        "candidate_feature_count": commitment["feature_catalog"]["feature_count"],
        "determinism_state": comparison["state"],
        "generation2_target_values_accessed": 0,
        "generation2_protected_anchor_rows_accessed": 0,
    }


def extract_generation2_source(
    *,
    repository_root: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Acquire the pinned minimal MI/WI Overture envelope extract using optional DuckDB."""
    root = repository_root.resolve()
    output = output_dir.resolve()
    outputs = (root / "outputs").resolve()
    require(
        _is_within(output, outputs) and output != outputs and not output.exists(),
        "MODEL14_G2_SOURCE_OUTPUT_INVALID",
        "Overture source output must be a new bounded ignored output directory",
    )
    contract = load_generation2_contract(root)
    try:
        import duckdb  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ConformanceError(
            "MODEL14_G2_DUCKDB_REQUIRED",
            "install the scoped model14-overture optional dependency to acquire Overture GeoParquet",
        ) from exc
    geo03 = _json_object(
        root / "config/geo/geo03_internal_point_membership_spatial_spec.json",
        "MODEL14_G2_GEO03_AUTHORITY_MISSING",
    )
    transformer = Geo03ProductionTransformer(geo03)
    supports = {state: _accepted_tract_support(root, state, transformer) for state in ("MI", "WI")}
    bounds = {
        state: [
            min(geometry.bounds[0] for geometry in support.geometries.values()),
            min(geometry.bounds[1] for geometry in support.geometries.values()),
            max(geometry.bounds[2] for geometry in support.geometries.values()),
            max(geometry.bounds[3] for geometry in support.geometries.values()),
        ]
        for state, support in supports.items()
    }
    output.mkdir(parents=True)
    extract = output / "overture_places_mi_wi_envelopes.csv"
    destination = extract.as_posix().replace("'", "''")
    source = str(contract["source"]["cloud_uri"]).replace("'", "''")
    clauses = []
    for state in ("MI", "WI"):
        xmin, ymin, xmax, ymax = bounds[state]
        xmin_text = format(xmin, ".17g")
        ymin_text = format(ymin, ".17g")
        xmax_text = format(xmax, ".17g")
        ymax_text = format(ymax, ".17g")
        clauses.append(
            "((bbox.xmin IS NULL OR "
            f"(bbox.xmax >= {xmin_text} AND bbox.xmin <= {xmax_text} "
            f"AND bbox.ymax >= {ymin_text} AND bbox.ymin <= {ymax_text})) "
            f"AND ST_X(geometry) BETWEEN {xmin_text} AND {xmax_text} "
            f"AND ST_Y(geometry) BETWEEN {ymin_text} AND {ymax_text})"
        )
    connection = duckdb.connect()
    connection.execute("INSTALL spatial")
    connection.execute("LOAD spatial")
    connection.execute("SET s3_region = 'us-west-2'")
    connection.execute(
        f"""
        COPY (
            SELECT
                id,
                version,
                ST_X(geometry) AS longitude,
                ST_Y(geometry) AS latitude,
                bbox.xmin AS bbox_xmin,
                bbox.xmax AS bbox_xmax,
                bbox.ymin AS bbox_ymin,
                bbox.ymax AS bbox_ymax,
                confidence,
                operating_status,
                basic_category,
                taxonomy.primary AS taxonomy_primary,
                CAST(taxonomy.hierarchy AS JSON) AS taxonomy_hierarchy
            FROM read_parquet('{source}')
            WHERE {" OR ".join(clauses)}
            ORDER BY id
        ) TO '{destination}' (FORMAT CSV, HEADER TRUE)
        """
    )
    row_count = int(connection.execute(f"SELECT COUNT(*) FROM read_csv_auto('{destination}', header = true)").fetchone()[0])
    report = {
        "release": contract["source"]["release"],
        "schema": contract["source"]["schema_version"],
        "source": contract["source"]["cloud_uri"],
        "retrieval_date": contract["source"]["retrieval_date"],
        "query_identity": contract["source"]["query_identity"],
        "extraction_predicate": contract["source"]["extraction_predicate"],
        "duckdb_version": str(duckdb.__version__),
        "selected_columns": [
            "id",
            "version",
            "longitude",
            "latitude",
            "bbox_xmin",
            "bbox_xmax",
            "bbox_ymin",
            "bbox_ymax",
            "confidence",
            "operating_status",
            "basic_category",
            "taxonomy_primary",
            "taxonomy_hierarchy",
        ],
        "row_count": row_count,
        "byte_length": extract.stat().st_size,
        "sha256": file_sha256(extract),
        "deprecated_category_field_selected": False,
        "names_brands_providers_selected": False,
    }
    write_json_exclusive(output / "source_extract_report.json", report)
    return {"state": "complete", "row_count": row_count, "byte_length": extract.stat().st_size}
