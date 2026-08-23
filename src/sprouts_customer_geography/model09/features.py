"""Target-blind public feature construction for MODEL-09."""

from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
from zipfile import ZipFile

from shapely.geometry import Point

from sprouts_customer_geography.geo04 import _read_dbf_records
from sprouts_customer_geography.model10.binding import validate_successor_package
from sprouts_customer_geography.pipe01.canonical import content_digest, file_sha256
from sprouts_customer_geography.pipe01.errors import ConformanceError, require
from sprouts_customer_geography.pipe01.production import (
    ACS_GEOID_PATTERN,
    ACS_TRACT_PREFIX,
    TIGER_DBF_MEMBER,
    TIGER_SHP_MEMBER,
    Geo03ProductionTransformer,
    _read_shapefile_polygons,
    parse_acs_b11001_values,
)
from sprouts_customer_geography.pipe01.spatial import parse_internal_point, project_internal_point
from sprouts_customer_geography.pipe04.binding import validate_semantic_package


RADII_M = (4828.032, 8046.72, 11265.408)
PIPE04_PACKAGE_ID = "PIPE04_MODEL10_WISCONSIN_DEVELOPMENT_BINDING_V1"
MODEL10_PACKAGE_ID = "MODEL10_WISCONSIN_COHORT_IDENTITY_LINEAGE_PACKAGE_V1"


def _load_object(path: Path, code: str) -> dict[str, Any]:
    require(path.is_file(), code, "required JSON authority is absent")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ConformanceError(code, "required JSON authority is unreadable") from exc
    require(isinstance(value, dict), code, "required JSON authority must be an object")
    return value


def verify_pipe04_binding(binding_path: Path, ready_path: Path) -> dict[str, Any]:
    package = _load_object(binding_path, "PIPE04_BINDING_UNRESOLVED")
    ready = _load_object(ready_path, "PIPE04_READY_MARKER_UNRESOLVED")
    protected_hash = package.get("protected_content_sha256")
    stable = package.get("stable_binding_identity")
    semantic = dict(package)
    semantic.pop("protected_content_sha256", None)
    semantic.pop("stable_binding_identity", None)
    semantic.pop("protected_content_hash_semantics", None)
    validate_semantic_package(semantic)
    require(
        package.get("package_id") == PIPE04_PACKAGE_ID
        and isinstance(protected_hash, str)
        and protected_hash == content_digest(semantic)
        and stable == "pipe04-binding:sha256:" + protected_hash,
        "PIPE04_PROTECTED_CONTENT_MISMATCH",
        "PIPE-04 protected content identity differs",
    )
    require(
        ready.get("state") == "ready"
        and ready.get("finalization_state") == "complete"
        and ready.get("package_id") == PIPE04_PACKAGE_ID
        and ready.get("binding_run_id") == package.get("binding_run_id")
        and ready.get("protected_content_sha256") == protected_hash
        and ready.get("stable_binding_identity") == stable,
        "PIPE04_READY_MARKER_MISMATCH",
        "PIPE-04 READY marker differs from binding",
    )
    return package


def verify_model10_package(package_path: Path, ready_path: Path) -> dict[str, Any]:
    package = _load_object(package_path, "MODEL10_PACKAGE_UNRESOLVED")
    ready = _load_object(ready_path, "MODEL10_READY_MARKER_UNRESOLVED")
    validate_successor_package(package)
    protected_hash = package.get("protected_content_sha256")
    semantic = dict(package)
    semantic.pop("protected_content_sha256", None)
    semantic.pop("protected_content_hash_semantics", None)
    require(
        package.get("package_id") == MODEL10_PACKAGE_ID
        and package.get("state") == "ready"
        and isinstance(protected_hash, str)
        and protected_hash == content_digest(semantic),
        "MODEL10_PROTECTED_CONTENT_MISMATCH",
        "MODEL-10 protected content identity differs",
    )
    require(
        ready.get("state") == "ready"
        and ready.get("package_id") == MODEL10_PACKAGE_ID
        and ready.get("materialization_run_id") == package.get("materialization_run_id")
        and ready.get("protected_content_sha256") == protected_hash,
        "MODEL10_READY_MARKER_MISMATCH",
        "MODEL-10 READY marker differs from package",
    )
    return package


def reconcile_fixed_cohort(binding: Mapping[str, Any], model10: Mapping[str, Any]) -> list[dict[str, Any]]:
    binding_rows = binding.get("eligible_wisconsin_cohort")
    model10_rows = model10.get("records")
    require(isinstance(binding_rows, list) and isinstance(model10_rows, list), "COHORT_AUTHORITY_UNRESOLVED", "cohort records are absent")
    eligible = {row.get("source_observation_id"): row for row in model10_rows if row.get("model09_development_eligible") is True and row.get("quarantined") is False}
    require(len(eligible) == len(binding_rows) and len(eligible) > 0, "COMPLETE_COHORT_ACCOUNTING_FAILED", "PIPE-04 and MODEL-10 eligible counts differ")
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    group_anchors: dict[str, tuple[float, float]] = {}
    for bound in binding_rows:
        observation_id = bound.get("source_observation_id")
        require(isinstance(observation_id, str) and observation_id not in seen and observation_id in eligible, "COHORT_IDENTITY_MISMATCH", "PIPE-04 observation identity differs from MODEL-10")
        source = eligible[observation_id]
        for field in ("successor_physical_location_id", "historical_model04_physical_location_id", "market", "forecast_vintage", "identity_state"):
            require(bound.get(field) == source.get(field), "TARGET_CONTENT_CHANGED_COHORT", "target binding differs from fixed MODEL-10 identity or lineage")
        require(bound.get("source_observation_lineage") == {key: source.get("source_observation_lineage", {}).get(key) for key in ("source_workbook_identity", "source_sheet", "source_row", "source_seed_point_id")}, "TARGET_CONTENT_CHANGED_COHORT", "target binding differs from fixed source-observation lineage")
        anchor = source.get("successor_canonical_anchor")
        coordinate = anchor.get("observed_coordinate") if isinstance(anchor, Mapping) else None
        require(isinstance(coordinate, Mapping), "MODEL10_CANONICAL_ANCHOR_MISSING", "fixed MODEL-10 canonical anchor is absent")
        latitude = coordinate.get("latitude")
        longitude = coordinate.get("longitude")
        require(all(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) for value in (latitude, longitude)), "MODEL10_CANONICAL_ANCHOR_INVALID", "fixed MODEL-10 canonical anchor is invalid")
        physical_id = str(bound["successor_physical_location_id"])
        coordinate_pair = (float(latitude), float(longitude))
        require(physical_id not in group_anchors or group_anchors[physical_id] == coordinate_pair, "REPEATED_LOCATION_ANCHOR_MISMATCH", "one MODEL-10 physical location has inconsistent canonical anchors")
        group_anchors[physical_id] = coordinate_pair
        output.append({**dict(bound), "canonical_latitude": coordinate_pair[0], "canonical_longitude": coordinate_pair[1]})
        seen.add(observation_id)
    require(seen == set(eligible), "COMPLETE_COHORT_ACCOUNTING_FAILED", "not every eligible MODEL-10 observation is accounted for")
    return sorted(output, key=lambda row: str(row["source_observation_id"]))


@dataclass(frozen=True)
class TractEvidence:
    geoid: str
    internal_x_m: float
    internal_y_m: float
    source_geometry: Any
    households: int
    household_moe: int


def _load_acs(source: Path, manifest: Mapping[str, Any]) -> dict[str, tuple[int, int]]:
    require(source.name == manifest.get("source_filename") and source.is_file(), "ACS_SOURCE_IDENTITY_MISMATCH", "ACS source identity differs")
    require(source.stat().st_size == manifest.get("retrieval", {}).get("expected_byte_length") and file_sha256(source) == manifest.get("byte_sha256"), "ACS_SOURCE_CHECKSUM_MISMATCH", "ACS bytes differ from accepted authority")
    request = manifest.get("request_identity")
    require(isinstance(request, Mapping) and content_digest(request) == manifest.get("request_sha256"), "ACS_REQUEST_IDENTITY_MISMATCH", "ACS request identity differs")
    values: dict[str, tuple[int, int]] = {}
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="|")
        require(reader.fieldnames is not None and set(request.get("header_required", [])) <= set(reader.fieldnames), "ACS_SOURCE_HEADER_MISMATCH", "ACS required fields are absent")
        for row in reader:
            geo_identity = str(row.get("GEO_ID", ""))
            if not geo_identity.startswith(ACS_TRACT_PREFIX):
                continue
            match = ACS_GEOID_PATTERN.fullmatch(geo_identity)
            require(match is not None, "ACS_TRACT_IDENTITY_INVALID", "Wisconsin ACS tract identity is invalid")
            parsed = parse_acs_b11001_values(row.get("B11001_E001"), row.get("B11001_M001"))
            require(parsed["status"] == "valid" and isinstance(parsed["estimate"], int) and isinstance(parsed["moe"], int), "ACS_MEMBER_EVIDENCE_INVALID", "accepted B11001 tract evidence is noncomputable")
            geoid = match.group(1)
            require(geoid not in values, "ACS_DUPLICATE_TRACT_GEOID", "ACS contains duplicate Wisconsin tract")
            values[geoid] = (parsed["estimate"], parsed["moe"])
    require(len(values) == manifest.get("expected_file_properties", {}).get("expected_wisconsin_tract_row_count_at_retrieval"), "ACS_WISCONSIN_TRACT_COUNT_MISMATCH", "ACS Wisconsin tract count differs")
    return values


def load_public_tract_evidence(*, tiger_source: Path, acs_source: Path, tiger_manifest: Mapping[str, Any], acs_manifest: Mapping[str, Any], geo03_spec: Mapping[str, Any]) -> list[TractEvidence]:
    require(tiger_source.name == tiger_manifest.get("source_filename") and tiger_source.is_file(), "TIGER_SOURCE_IDENTITY_MISMATCH", "TIGER source identity differs")
    require(tiger_source.stat().st_size == tiger_manifest.get("retrieval", {}).get("expected_byte_length") and file_sha256(tiger_source) == tiger_manifest.get("byte_sha256"), "TIGER_SOURCE_CHECKSUM_MISMATCH", "TIGER bytes differ from accepted authority")
    with ZipFile(tiger_source) as archive:
        names = set(archive.namelist())
        require(set(tiger_manifest.get("expected_file_properties", {}).get("required_entries", [])) <= names, "TIGER_ZIP_ENTRY_MISSING", "TIGER archive is incomplete")
        records = _read_dbf_records(archive.read(TIGER_DBF_MEMBER))
        geometries = _read_shapefile_polygons(archive.read(TIGER_SHP_MEMBER))
    require(len(records) == len(geometries), "TIGER_ATTRIBUTE_GEOMETRY_COUNT_MISMATCH", "TIGER record and geometry counts differ")
    acs = _load_acs(acs_source, acs_manifest)
    transformer = Geo03ProductionTransformer(geo03_spec)
    evidence: list[TractEvidence] = []
    seen: set[str] = set()
    for record, geometry in zip(records, geometries):
        geoid = str(record.get("GEOID", ""))
        require(geoid in acs and geoid not in seen, "PUBLIC_TRACT_COVERAGE_MISMATCH", "TIGER and ACS Wisconsin tract coverage differs")
        point = parse_internal_point(record.get("INTPTLAT"), record.get("INTPTLON"))
        projected = project_internal_point(point, transformer)
        require(projected is not None, "TIGER_INTERNAL_POINT_NONCOMPUTABLE", "TIGER internal point is noncomputable")
        households, moe = acs[geoid]
        evidence.append(TractEvidence(geoid, projected[0], projected[1], geometry, households, moe))
        seen.add(geoid)
    require(seen == set(acs), "PUBLIC_TRACT_COVERAGE_MISMATCH", "TIGER and ACS Wisconsin tract coverage differs")
    return evidence


def _anchor_tract(tracts: list[TractEvidence], longitude: float, latitude: float) -> TractEvidence:
    point = Point(longitude, latitude)
    covered = [tract for tract in tracts if tract.source_geometry.covers(point)]
    if len(covered) > 1:
        contained = [tract for tract in covered if tract.source_geometry.contains(point)]
        covered = contained
    require(len(covered) == 1, "ANCHOR_TRACT_MISSING_OR_AMBIGUOUS", "MODEL-10 canonical anchor does not resolve to exactly one Wisconsin tract")
    return covered[0]


def build_public_features(cohort: list[Mapping[str, Any]], tracts: list[TractEvidence], geo03_spec: Mapping[str, Any]) -> list[dict[str, Any]]:
    transformer = Geo03ProductionTransformer(geo03_spec)
    by_group: dict[str, dict[str, Any]] = {}
    output: list[dict[str, Any]] = []
    for row in cohort:
        physical_id = str(row["successor_physical_location_id"])
        if physical_id not in by_group:
            latitude = float(row["canonical_latitude"])
            longitude = float(row["canonical_longitude"])
            anchor_point = parse_internal_point(latitude, longitude)
            projected = project_internal_point(anchor_point, transformer)
            require(projected is not None, "ANCHOR_TRANSFORM_FAILED", "MODEL-10 canonical anchor cannot be transformed")
            anchor_tract = _anchor_tract(tracts, longitude, latitude)
            totals: list[int] = []
            moes: list[float] = []
            members: list[int] = []
            for radius in RADII_M:
                selected = [tract for tract in tracts if math.hypot(tract.internal_x_m - projected[0], tract.internal_y_m - projected[1]) <= radius]
                if anchor_tract not in selected:
                    selected.append(anchor_tract)
                require(selected, "HOUSEHOLD_FEATURE_NONCOMPUTABLE", "no tract membership resolved")
                totals.append(sum(tract.households for tract in selected))
                moes.append(math.sqrt(sum(tract.household_moe ** 2 for tract in selected)))
                members.append(len(selected))
            h3, h5, h7 = totals
            require(0 < h3 <= h5 <= h7, "HOUSEHOLD_FEATURE_NONCOMPUTABLE", "nested household opportunity is invalid")
            area3 = math.pi * 3.0**2
            outer_area = math.pi * (7.0**2 - 3.0**2)
            outer_households = h7 - h3
            features = {
                "households_3mi": h3,
                "households_5mi": h5,
                "households_7mi": h7,
                "households_3mi_moe": moes[0],
                "households_5mi_moe": moes[1],
                "households_7mi_moe": moes[2],
                "relative_moe_5mi": moes[1] / h5,
                "tract_member_count_3mi": members[0],
                "tract_member_count_5mi": members[1],
                "tract_member_count_7mi": members[2],
                "log_households_5mi": math.log1p(h5),
                "inner_household_share_3mi_of_7mi": h3 / h7,
                "log_inner_outer_household_density_gradient": math.log1p(h3 / area3) - math.log1p(outer_households / outer_area),
                "anchor_tract_geoid": anchor_tract.geoid,
            }
            by_group[physical_id] = features
        output.append({**dict(row), "features": dict(by_group[physical_id])})
    require(len(output) == len(cohort), "COMPLETE_COHORT_ACCOUNTING_FAILED", "feature rows do not cover the complete cohort")
    return output
