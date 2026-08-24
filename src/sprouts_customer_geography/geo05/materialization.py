"""Deterministic public-only Michigan spatial support for GEO-05."""

from __future__ import annotations

import csv
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
from typing import Any, Iterable, Mapping, Sequence
from zipfile import ZipFile

import shapely
from shapely import normalize, wkb
from shapely.geometry import Point
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform as transform_geometry
from shapely.ops import unary_union

from sprouts_customer_geography.geo04 import inventory_digest, tiger_rows_from_source_zip
from sprouts_customer_geography.pipe01.canonical import canonical_bytes, file_sha256, write_json_exclusive
from sprouts_customer_geography.pipe01.errors import ConformanceError, require
from sprouts_customer_geography.pipe01.production import Geo03ProductionTransformer, _read_shapefile_polygons
from sprouts_customer_geography.pipe01.spatial import (
    ordinary_membership,
    parse_internal_point,
    planar_distance_m,
    project_internal_point,
)

from .contract import (
    ANCHOR_EVIDENCE_SCHEMA_ID,
    DEFAULT_RADII_M,
    EXPECTED_INVENTORY_SHA256,
    EXPECTED_TRACT_COUNT,
    INVENTORY_ID,
    REPORT_ID,
    SPECIFICATION_ID,
    STATE_FIPS,
    Geo05Authority,
    load_authority,
)


PROJECTED_POINT_COLUMNS = [
    "tract_geoid",
    "state_fips",
    "county_fips",
    "tract_code",
    "intptlat_raw",
    "intptlon_raw",
    "intptlat_hex",
    "intptlon_hex",
    "internal_x_m_hex",
    "internal_y_m_hex",
    "coordinate_state",
    "projection_state",
    "source_crs",
    "target_crs",
    "source_manifest_id",
    "operation_fingerprint_sha256",
]
FOOTPRINT_QUAD_SEGS = 64


@dataclass(frozen=True)
class SpatialTract:
    geoid: str
    latitude: float
    longitude: float
    internal_x_m: float
    internal_y_m: float
    source_geometry: BaseGeometry


@dataclass(frozen=True)
class PreparedSpatialState:
    tracts: tuple[SpatialTract, ...]
    projected_support: BaseGeometry
    runtime_provenance: Mapping[str, Any]
    source_summary: Mapping[str, Any]


@dataclass(frozen=True)
class SupportPackage:
    authority: Geo05Authority
    tracts: tuple[SpatialTract, ...]
    projected_support: BaseGeometry
    runtime_provenance: Mapping[str, Any]
    verification_report: Mapping[str, Any]


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _load_object(path: Path, code: str) -> dict[str, Any]:
    require(path.is_file(), code, f"required JSON file is absent: {path.name}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ConformanceError(code, f"required JSON file is unreadable: {path.name}") from exc
    require(isinstance(value, dict), code, "required JSON document must be an object")
    return value


def _assert_output_path(path: Path, repository_root: Path) -> Path:
    resolved = path.resolve()
    root = repository_root.resolve()
    try:
        relative = resolved.relative_to(root).as_posix()
    except ValueError:
        return resolved
    require(
        relative == "outputs" or relative.startswith("outputs/"),
        "GEO05_OUTPUT_PATH_NOT_IGNORED",
        "generated output inside the repository must remain under ignored outputs",
    )
    return resolved


def _write_csv(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    with path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=PROJECTED_POINT_COLUMNS, lineterminator="\n", extrasaction="raise")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in PROJECTED_POINT_COLUMNS})
        handle.flush()
        os.fsync(handle.fileno())


def _write_geometry_jsonl(path: Path, tracts: Sequence[SpatialTract]) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        for tract in tracts:
            document = {
                "source_crs": "EPSG:4269",
                "source_geometry_wkb_hex": wkb.dumps(normalize(tract.source_geometry), hex=True, big_endian=True, output_dimension=2),
                "tract_geoid": tract.geoid,
            }
            handle.write(canonical_bytes(document).decode("utf-8"))
            handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def _write_binary_exclusive(path: Path, value: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(value)
        handle.flush()
        os.fsync(handle.fileno())


def verify_data04_ready(authority: Geo05Authority, ready_dir: Path) -> tuple[list[dict[str, str]], dict[str, Any]]:
    """Require one current accepted DATA-04 READY package without protected discovery."""
    contract = authority.data04.contract
    tiger_manifest = authority.data04.tiger_manifest
    require(ready_dir.is_dir(), "GEO05_DATA04_READY_UNRESOLVED", "accepted DATA-04 READY directory is absent")
    output_contract = contract["output_contract"]
    ready_path = ready_dir / output_contract["ready_filename"]
    report_path = ready_dir / output_contract["verification_report_filename"]
    tiger_path = ready_dir / output_contract["tiger_filename"]
    ready = _load_object(ready_path, "GEO05_DATA04_READY_UNRESOLVED")
    report = _load_object(report_path, "GEO05_DATA04_REPORT_UNRESOLVED")
    require(
        ready.get("state") == "READY"
        and ready.get("ready_marker_written_last") is True
        and ready.get("report_filename") == output_contract["verification_report_filename"]
        and ready.get("report_sha256") == file_sha256(report_path),
        "GEO05_DATA04_READY_MISMATCH",
        "DATA-04 READY marker does not bind its verification report",
    )
    require(
        report.get("state") == "VERIFIED"
        and report.get("report_id") == "DATA04_MICHIGAN_PUBLIC_DATA_PARITY_MATERIALIZATION_REPORT_V1"
        and report.get("contract_id") == contract.get("artifact_id")
        and report.get("contract_content_sha256") == contract.get("content_sha256")
        and report.get("state_fips") == STATE_FIPS
        and report.get("tract_count") == EXPECTED_TRACT_COUNT
        and report.get("ordered_tract_inventory_sha256") == EXPECTED_INVENTORY_SHA256,
        "GEO05_DATA04_REPORT_MISMATCH",
        "DATA-04 READY report does not bind the accepted complete Michigan inventory",
    )
    tiger_report = report.get("tiger_evidence", {})
    require(
        tiger_report.get("manifest_id") == tiger_manifest.get("manifest_id")
        and tiger_report.get("manifest_content_sha256") == tiger_manifest.get("manifest_content_sha256")
        and tiger_report.get("source_byte_sha256") == tiger_manifest.get("byte_sha256")
        and tiger_report.get("source_crs") == "EPSG:4269"
        and tiger_report.get("tract_count") == EXPECTED_TRACT_COUNT
        and tiger_report.get("unique_geoid_count") == EXPECTED_TRACT_COUNT
        and tiger_report.get("geometry_record_count") == EXPECTED_TRACT_COUNT
        and tiger_report.get("internal_point_status_counts") == {"valid": EXPECTED_TRACT_COUNT},
        "GEO05_DATA04_TIGER_EVIDENCE_MISMATCH",
        "DATA-04 READY TIGER evidence differs from accepted Michigan authority",
    )
    require(
        tiger_path.is_file()
        and ready.get("tiger_output_sha256") == file_sha256(tiger_path)
        and tiger_report.get("output", {}).get("byte_sha256") == file_sha256(tiger_path),
        "GEO05_DATA04_TIGER_OUTPUT_MISMATCH",
        "DATA-04 TIGER evidence output differs from READY lineage",
    )
    require(
        report.get("downstream_geo_source_readiness", {}).get("complete_statewide_key_set") is True
        and report.get("downstream_geo_source_readiness", {}).get("source_geometry_available") is True
        and report.get("downstream_geo_source_readiness", {}).get("internal_points_available_and_parseable") is True
        and report.get("downstream_geo_source_readiness", {}).get("authoritative_michigan_market_inventory_created") is False
        and report.get("protected_evidence_access", {}).get("sprouts_or_protected_evidence_accessed") is False,
        "GEO05_DATA04_READINESS_MISMATCH",
        "DATA-04 downstream readiness or public-only boundary differs",
    )

    rows: list[dict[str, str]] = []
    with tiger_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        require(reader.fieldnames == tiger_report.get("output", {}).get("columns"), "GEO05_DATA04_TIGER_OUTPUT_SCHEMA_MISMATCH", "DATA-04 TIGER output columns differ")
        for row in reader:
            rows.append(dict(row))
    ordered_geoids = [row.get("tract_geoid", "") for row in rows]
    require(
        len(rows) == EXPECTED_TRACT_COUNT
        and ordered_geoids == sorted(ordered_geoids)
        and len(set(ordered_geoids)) == EXPECTED_TRACT_COUNT
        and inventory_digest(ordered_geoids) == EXPECTED_INVENTORY_SHA256,
        "GEO05_DATA04_TIGER_OUTPUT_INVENTORY_MISMATCH",
        "DATA-04 TIGER output does not reproduce the accepted ordered inventory",
    )
    for row in rows:
        geoid = row["tract_geoid"]
        require(
            re.fullmatch(r"26[0-9]{9}", geoid) is not None
            and row.get("state_fips") == STATE_FIPS
            and geoid == row.get("state_fips", "") + row.get("county_fips", "") + row.get("tract_code", "")
            and row.get("internal_point_status") == "valid"
            and row.get("geometry_record_status") == "valid"
            and row.get("source_crs") == "EPSG:4269"
            and row.get("source_manifest_id") == tiger_manifest.get("manifest_id"),
            "GEO05_DATA04_TIGER_OUTPUT_ROW_MISMATCH",
            f"DATA-04 TIGER evidence row is invalid for {geoid}",
        )
    lineage = {
        "data04_contract_id": contract["artifact_id"],
        "data04_contract_content_sha256": contract["content_sha256"],
        "data04_report_sha256": file_sha256(report_path),
        "data04_ready_sha256": file_sha256(ready_path),
        "data04_tiger_evidence_sha256": file_sha256(tiger_path),
        "tiger_manifest_id": tiger_manifest["manifest_id"],
        "tiger_manifest_content_sha256": tiger_manifest["manifest_content_sha256"],
        "inventory_sha256": EXPECTED_INVENTORY_SHA256,
    }
    return rows, lineage


def _prepare_real_state(
    authority: Geo05Authority,
    tiger_source: Path,
    data04_rows: Sequence[Mapping[str, str]],
) -> PreparedSpatialState:
    specification = authority.specification
    source = specification["data04_source_authority"]
    tiger_identity = source["tiger_source"]
    tiger_manifest = authority.data04.tiger_manifest
    require(
        tiger_source.is_file()
        and tiger_source.name == tiger_identity["filename"]
        and tiger_source.stat().st_size == tiger_identity["byte_length"]
        and file_sha256(tiger_source) == tiger_identity["byte_sha256"],
        "GEO05_TIGER_SOURCE_IDENTITY_MISMATCH",
        "Michigan TIGER local bytes differ from exact accepted DATA-04 authority",
    )
    rows = tiger_rows_from_source_zip(tiger_source, tiger_manifest, STATE_FIPS)
    stem = tiger_identity["filename"].removesuffix(".zip")
    properties = tiger_manifest["expected_file_properties"]
    with ZipFile(tiger_source) as archive:
        names = set(archive.namelist())
        require(set(properties["required_entries"]) <= names, "GEO05_TIGER_ZIP_ENTRY_MISSING", "Michigan TIGER archive entries are incomplete")
        prj_bytes = archive.read(f"{stem}.prj")
        dbf_bytes = archive.read(f"{stem}.dbf")
        shp_bytes = archive.read(f"{stem}.shp")
        shx_bytes = archive.read(f"{stem}.shx")
        geometries = _read_shapefile_polygons(shp_bytes)
    source_geometry = source["source_geometry"]
    require(
        _sha256_bytes(prj_bytes) == source_geometry["projection_member_sha256"]
        and _sha256_bytes(dbf_bytes) == source_geometry["dbf_member_sha256"]
        and _sha256_bytes(shp_bytes) == source_geometry["shapefile_member_sha256"]
        and _sha256_bytes(shx_bytes) == source_geometry["shapefile_index_member_sha256"],
        "GEO05_TIGER_MEMBER_IDENTITY_MISMATCH",
        "Michigan TIGER geometry member bytes differ from accepted DATA-04 authority",
    )
    projection = prj_bytes.decode("ascii")
    require(
        "GCS_North_American_1983" in projection and "D_North_American_1983" in projection and "GRS_1980" in projection,
        "GEO05_TIGER_CRS_MISMATCH",
        "Michigan TIGER projection metadata is not NAD83/EPSG:4269",
    )
    require(
        len(rows) == len(geometries) == len(data04_rows) == EXPECTED_TRACT_COUNT,
        "GEO05_TIGER_ATTRIBUTE_GEOMETRY_COUNT_MISMATCH",
        "Michigan TIGER source, geometry, and DATA-04 evidence counts differ",
    )
    data04_by_geoid = {row["tract_geoid"]: row for row in data04_rows}
    require(len(data04_by_geoid) == EXPECTED_TRACT_COUNT, "GEO05_DATA04_DUPLICATE_GEOID", "DATA-04 TIGER evidence contains duplicate GEOIDs")

    transformer = Geo03ProductionTransformer(authority.geo03)
    tracts: list[SpatialTract] = []
    projected_geometries: dict[str, BaseGeometry] = {}
    seen: set[str] = set()
    for row, geometry in zip(rows, geometries):
        state = str(row.get("STATEFP", ""))
        county = str(row.get("COUNTYFP", ""))
        tract_code = str(row.get("TRACTCE", ""))
        geoid = str(row.get("GEOID", ""))
        require(
            state == STATE_FIPS
            and re.fullmatch(r"[0-9]{3}", county) is not None
            and re.fullmatch(r"[0-9]{6}", tract_code) is not None
            and geoid == state + county + tract_code
            and re.fullmatch(r"26[0-9]{9}", geoid) is not None,
            "GEO05_TIGER_GEOID_INVALID",
            "Michigan TIGER GEOID or components are invalid",
        )
        require(geoid not in seen and geoid in data04_by_geoid, "GEO05_TIGER_GEOID_COVERAGE_MISMATCH", "Michigan TIGER GEOID is duplicate or absent from DATA-04 READY evidence")
        seen.add(geoid)
        point = parse_internal_point(row.get("INTPTLAT"), row.get("INTPTLON"))
        require(point.coordinate_state == "valid", "GEO05_INTERNAL_POINT_NONCOMPUTABLE", f"Michigan TIGER internal point is invalid for {geoid}")
        projected_point = project_internal_point(point, transformer)
        require(projected_point is not None, "GEO05_INTERNAL_POINT_PROJECTION_FAILED", f"Michigan TIGER internal point projection failed for {geoid}")
        assert point.latitude is not None and point.longitude is not None
        data04_row = data04_by_geoid[geoid]
        require(
            float(data04_row["intptlat"]) == point.latitude
            and float(data04_row["intptlon"]) == point.longitude,
            "GEO05_DATA04_INTERNAL_POINT_MISMATCH",
            f"raw TIGER and DATA-04 internal-point evidence differ for {geoid}",
        )
        source_geometry_value = normalize(geometry)
        source_point = Point(point.longitude, point.latitude)
        require(
            source_geometry_value.is_valid
            and not source_geometry_value.is_empty
            and source_geometry_value.area > 0
            and source_geometry_value.covers(source_point),
            "GEO05_SOURCE_GEOMETRY_INVALID",
            f"Michigan source geometry is invalid or does not cover its official internal point for {geoid}",
        )
        projected_geometry = normalize(transform_geometry(transformer.transform, source_geometry_value))
        require(
            projected_geometry.is_valid
            and not projected_geometry.is_empty
            and projected_geometry.area > 0
            and projected_geometry.covers(Point(projected_point)),
            "GEO05_PROJECTED_GEOMETRY_INVALID",
            f"Michigan projected geometry is invalid or does not cover its projected internal point for {geoid}",
        )
        projected_geometries[geoid] = projected_geometry
        tracts.append(
            SpatialTract(
                geoid=geoid,
                latitude=float(point.latitude),
                longitude=float(point.longitude),
                internal_x_m=projected_point[0],
                internal_y_m=projected_point[1],
                source_geometry=source_geometry_value,
            )
        )
    tracts.sort(key=lambda value: value.geoid)
    ordered_geoids = [tract.geoid for tract in tracts]
    require(
        len(seen) == EXPECTED_TRACT_COUNT
        and set(data04_by_geoid) == seen
        and ordered_geoids == sorted(ordered_geoids)
        and inventory_digest(ordered_geoids) == EXPECTED_INVENTORY_SHA256,
        "GEO05_STATEWIDE_INVENTORY_MISMATCH",
        "Michigan source does not reproduce the exact accepted statewide inventory",
    )
    support = normalize(unary_union([projected_geometries[geoid] for geoid in ordered_geoids]))
    require(
        support.geom_type in {"Polygon", "MultiPolygon"}
        and support.is_valid
        and not support.is_empty
        and support.area > 0,
        "GEO05_STATE_SUPPORT_INVALID",
        "projected Michigan statewide support union is invalid",
    )
    require(
        all(support.covers(Point(tract.internal_x_m, tract.internal_y_m)) for tract in tracts),
        "GEO05_STATE_SUPPORT_COVERAGE_MISMATCH",
        "projected Michigan statewide support does not cover every projected internal point",
    )
    source_summary = {
        "source_filename": tiger_source.name,
        "source_byte_length": tiger_source.stat().st_size,
        "source_byte_sha256": file_sha256(tiger_source),
        "projection_member_sha256": _sha256_bytes(prj_bytes),
        "dbf_member_sha256": _sha256_bytes(dbf_bytes),
        "shapefile_member_sha256": _sha256_bytes(shp_bytes),
        "shapefile_index_member_sha256": _sha256_bytes(shx_bytes),
        "attribute_record_count": len(rows),
        "geometry_record_count": len(geometries),
        "unique_geoid_count": len(seen),
        "valid_internal_point_count": len(tracts),
        "projected_internal_point_count": len(tracts),
        "source_geometry_internal_point_coverage_count": len(tracts),
        "projected_geometry_internal_point_coverage_count": len(tracts),
        "source_crs": "EPSG:4269",
        "target_crs": "EPSG:5070",
    }
    return PreparedSpatialState(tuple(tracts), support, transformer.runtime_provenance, source_summary)


def _validated_radii(radii_m: Iterable[float] | None) -> tuple[float, ...]:
    values = list(DEFAULT_RADII_M if radii_m is None else radii_m)
    require(bool(values), "GEO05_RADIUS_INVALID", "at least one radius is required")
    require(
        all(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value)) and float(value) > 0 for value in values),
        "GEO05_RADIUS_INVALID",
        "radii must be finite positive metres",
    )
    ordered = tuple(sorted(float(value) for value in values))
    require(len(ordered) == len(set(ordered)), "GEO05_RADIUS_DUPLICATE", "radii must be unique")
    return ordered


def _resolve_anchor_tract(tracts: Sequence[SpatialTract], longitude: float, latitude: float) -> SpatialTract:
    point = Point(longitude, latitude)
    covered = [tract for tract in tracts if tract.source_geometry.covers(point)]
    if len(covered) > 1:
        covered = [tract for tract in covered if tract.source_geometry.contains(point)]
    require(len(covered) == 1, "GEO05_ANCHOR_TRACT_MISSING_OR_AMBIGUOUS", "anchor does not resolve to exactly one Michigan tract")
    return covered[0]


def _support_completeness(projected_anchor: tuple[float, float], support: BaseGeometry, radius_m: float) -> dict[str, Any]:
    anchor = Point(projected_anchor)
    footprint = anchor.buffer(radius_m, quad_segs=FOOTPRINT_QUAD_SEGS)
    require(footprint.is_valid and not footprint.is_empty and footprint.area > 0, "GEO05_FOOTPRINT_INVALID", "projected metric circle is invalid")
    retained = footprint.intersection(support)
    outside = footprint.difference(support)
    require(retained.is_valid and outside.is_valid, "GEO05_SUPPORT_INTERSECTION_INVALID", "Michigan support intersection or difference is invalid")
    require(retained.area <= footprint.area * (1.0 + 1e-12), "GEO05_SUPPORT_COMPLETENESS_INVALID", "retained support area exceeds the full circle")
    completeness = min(retained.area, footprint.area) / footprint.area
    require(-1e-15 <= completeness <= 1.0 + 1e-15, "GEO05_SUPPORT_COMPLETENESS_INVALID", "support completeness is outside [0,1]")
    completeness = min(1.0, max(0.0, completeness))
    boundary_distance = anchor.distance(support.boundary)
    return {
        "radius_m": radius_m,
        "full_circle_area_m2": float(footprint.area),
        "area_inside_michigan_support_m2": float(retained.area),
        "support_completeness_ratio": float(completeness),
        "extends_outside_michigan_support": bool(not outside.is_empty and outside.area > 0.0),
        "outside_support_area_m2": float(outside.area),
        "anchor_to_support_boundary_m": float(boundary_distance),
        "footprint_edge_margin_m": float(boundary_distance - radius_m),
        "footprint_quad_segs": FOOTPRINT_QUAD_SEGS,
    }


def evaluate_anchor_package(
    package: SupportPackage,
    *,
    latitude: float,
    longitude: float,
    opaque_anchor_identity: str,
    opaque_anchor_lineage: str,
    radii_m: Iterable[float] | None = None,
) -> dict[str, Any]:
    """Construct target-blind public spatial evidence from one verified package."""
    require(isinstance(opaque_anchor_identity, str) and bool(opaque_anchor_identity.strip()), "GEO05_ANCHOR_IDENTITY_INVALID", "opaque anchor identity must be nonempty")
    require(isinstance(opaque_anchor_lineage, str) and bool(opaque_anchor_lineage.strip()), "GEO05_ANCHOR_LINEAGE_INVALID", "opaque anchor lineage must be nonempty")
    point = parse_internal_point(latitude, longitude)
    require(point.coordinate_state == "valid", "GEO05_ANCHOR_COORDINATE_INVALID", f"anchor coordinate state is {point.coordinate_state}")
    transformer = Geo03ProductionTransformer(package.authority.geo03)
    projected = project_internal_point(point, transformer)
    require(projected is not None, "GEO05_ANCHOR_PROJECTION_FAILED", "anchor projection is noncomputable")
    assert point.latitude is not None and point.longitude is not None
    anchor_tract = _resolve_anchor_tract(package.tracts, point.longitude, point.latitude)
    require(
        package.projected_support.covers(Point(projected)),
        "GEO05_ANCHOR_PROJECTED_SUPPORT_MISMATCH",
        "projected anchor is outside the accepted Michigan support union",
    )
    radii = _validated_radii(radii_m)
    distances = {
        tract.geoid: planar_distance_m(projected, (tract.internal_x_m, tract.internal_y_m))
        for tract in package.tracts
    }
    expected_tract_count = int(package.authority.specification["state_scope"]["tract_count"])
    require(
        len(distances) == len(package.tracts) == expected_tract_count
        and all(math.isfinite(value) and value >= 0 for value in distances.values()),
        "GEO05_MEMBERSHIP_DISTANCE_NONCOMPUTABLE",
        "one or more required tract distances are noncomputable",
    )
    memberships: list[dict[str, Any]] = []
    membership_sets: list[set[str]] = []
    for radius in radii:
        ordinary = [tract.geoid for tract in package.tracts if ordinary_membership(distances[tract.geoid], radius)]
        ordinary_set = set(ordinary)
        forced = anchor_tract.geoid not in ordinary_set
        final_set = set(ordinary_set)
        final_set.add(anchor_tract.geoid)
        ordered_members = sorted(final_set)
        require(len(ordered_members) == len(final_set), "GEO05_MEMBERSHIP_DUPLICATE", "final membership contains a duplicate tract")
        memberships.append(
            {
                "radius_m": radius,
                "ordinary_member_count": len(ordinary_set),
                "member_count": len(ordered_members),
                "containing_tract_forced": forced,
                "member_geoids": ordered_members,
            }
        )
        membership_sets.append(final_set)
    for inner, outer in zip(membership_sets, membership_sets[1:]):
        require(inner <= outer, "GEO05_MEMBERSHIP_NOT_NESTED", "ascending-radius tract membership is not nested")
    completeness = [_support_completeness(projected, package.projected_support, radius) for radius in radii]
    specification = package.authority.specification
    output = {
        "schema_id": ANCHOR_EVIDENCE_SCHEMA_ID,
        "state": "COMPUTABLE",
        "anchor": {
            "opaque_anchor_identity": opaque_anchor_identity,
            "opaque_anchor_lineage": opaque_anchor_lineage,
            "latitude": float(point.latitude),
            "longitude": float(point.longitude),
        },
        "containing_tract_geoid": anchor_tract.geoid,
        "projected_anchor": {"crs": "EPSG:5070", "x_m": projected[0], "y_m": projected[1]},
        "memberships": memberships,
        "support_completeness": completeness,
        "spatial_lineage": {
            "spatial_spec_id": specification["artifact_id"],
            "spatial_spec_content_sha256": specification["content_sha256"],
            "inventory_id": specification["statewide_inventory"]["artifact_id"],
            "inventory_sha256": specification["statewide_inventory"]["inventory_sha256"],
            "data04_contract_id": specification["data04_source_authority"]["contract"]["artifact_id"],
            "tiger_manifest_id": specification["data04_source_authority"]["tiger_manifest"]["artifact_id"],
            "tiger_source_sha256": specification["data04_source_authority"]["tiger_source"]["byte_sha256"],
            "source_crs": "EPSG:4269",
            "target_crs": "EPSG:5070",
            "operation_id": specification["geo03_methodology"]["operation_id"],
            "operation_fingerprint_sha256": specification["geo03_methodology"]["operation_fingerprint_sha256"],
            "runtime_provenance": dict(package.runtime_provenance),
        },
    }
    return output


def _summarize_public_anchor_qa(evidence: Mapping[str, Any], selection: str) -> dict[str, Any]:
    return {
        "selection": selection,
        "anchor_tract_geoid": evidence["containing_tract_geoid"],
        "member_counts": [
            {"radius_m": item["radius_m"], "member_count": item["member_count"], "containing_tract_forced": item["containing_tract_forced"]}
            for item in evidence["memberships"]
        ],
        "support_completeness": [
            {
                "radius_m": item["radius_m"],
                "support_completeness_ratio": item["support_completeness_ratio"],
                "extends_outside_michigan_support": item["extends_outside_michigan_support"],
                "anchor_to_support_boundary_m": item["anchor_to_support_boundary_m"],
                "footprint_edge_margin_m": item["footprint_edge_margin_m"],
            }
            for item in evidence["support_completeness"]
        ],
    }


def materialize_real(
    repository_root: Path,
    tiger_source: Path,
    data04_ready_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Create one immutable complete Michigan spatial-support package."""
    root = repository_root.resolve()
    authority = load_authority(root)
    output = _assert_output_path(output_dir, root)
    require(not output.exists(), "GEO05_OUTPUT_OVERWRITE_DENIED", "GEO-05 materialization output already exists")
    output.mkdir(parents=True)

    data04_rows, data04_lineage = verify_data04_ready(authority, data04_ready_dir.resolve())
    state = _prepare_real_state(authority, tiger_source.resolve(), data04_rows)
    specification = authority.specification
    output_contract = specification["materialization_contract"]

    inventory = {
        "artifact_id": INVENTORY_ID,
        "version": "1.0.0",
        "support_kind": "complete_statewide_spatial_support",
        "state_name": "Michigan",
        "state_fips": STATE_FIPS,
        "tract_count": len(state.tracts),
        "ordering": "lexicographically ascending full 11-character GEOID",
        "ordered_geoids": [tract.geoid for tract in state.tracts],
        "inventory_sha256": EXPECTED_INVENTORY_SHA256,
        "market_inventory": False,
        "source_lineage": {
            "data04_contract_id": specification["data04_source_authority"]["contract"]["artifact_id"],
            "data04_contract_content_sha256": specification["data04_source_authority"]["contract"]["content_sha256"],
            "tiger_manifest_id": specification["data04_source_authority"]["tiger_manifest"]["artifact_id"],
            "tiger_manifest_content_sha256": specification["data04_source_authority"]["tiger_manifest"]["content_sha256"],
            "tiger_source_sha256": specification["data04_source_authority"]["tiger_source"]["byte_sha256"],
        },
    }
    inventory_path = output / output_contract["inventory_filename"]
    projected_path = output / output_contract["projected_internal_points_filename"]
    geometries_path = output / output_contract["source_geometries_filename"]
    support_path = output / output_contract["projected_support_geometry_filename"]
    runtime_path = output / output_contract["runtime_provenance_filename"]
    report_path = output / output_contract["verification_report_filename"]
    ready_path = output / output_contract["ready_filename"]

    write_json_exclusive(inventory_path, inventory)
    data04_by_geoid = {row["tract_geoid"]: row for row in data04_rows}
    _write_csv(
        projected_path,
        (
            {
                "tract_geoid": tract.geoid,
                "state_fips": tract.geoid[:2],
                "county_fips": tract.geoid[2:5],
                "tract_code": tract.geoid[5:],
                "intptlat_raw": data04_by_geoid[tract.geoid]["intptlat_raw"],
                "intptlon_raw": data04_by_geoid[tract.geoid]["intptlon_raw"],
                "intptlat_hex": tract.latitude.hex(),
                "intptlon_hex": tract.longitude.hex(),
                "internal_x_m_hex": tract.internal_x_m.hex(),
                "internal_y_m_hex": tract.internal_y_m.hex(),
                "coordinate_state": "valid",
                "projection_state": "valid",
                "source_crs": "EPSG:4269",
                "target_crs": "EPSG:5070",
                "source_manifest_id": specification["data04_source_authority"]["tiger_manifest"]["artifact_id"],
                "operation_fingerprint_sha256": specification["geo03_methodology"]["operation_fingerprint_sha256"],
            }
            for tract in state.tracts
        ),
    )
    _write_geometry_jsonl(geometries_path, state.tracts)
    support_wkb = wkb.dumps(normalize(state.projected_support), hex=False, big_endian=True, output_dimension=2)
    require(isinstance(support_wkb, bytes), "GEO05_STATE_SUPPORT_SERIALIZATION_FAILED", "projected support WKB serialization failed")
    _write_binary_exclusive(support_path, support_wkb)
    runtime_document = {
        "operation_id": specification["geo03_methodology"]["operation_id"],
        "operation_fingerprint_sha256": specification["geo03_methodology"]["operation_fingerprint_sha256"],
        "runtime_provenance": dict(state.runtime_provenance),
        "geometry_engine": f"shapely-{shapely.__version__}",
        "footprint_quad_segs": FOOTPRINT_QUAD_SEGS,
    }
    write_json_exclusive(runtime_path, runtime_document)

    provisional_package = SupportPackage(authority, state.tracts, state.projected_support, state.runtime_provenance, {})
    distances = [
        (Point(tract.internal_x_m, tract.internal_y_m).distance(state.projected_support.boundary), tract.geoid, tract)
        for tract in state.tracts
    ]
    edge_tract = min(distances, key=lambda item: (item[0], item[1]))[2]
    interior_tract = max(distances, key=lambda item: (item[0], item[1]))[2]
    edge_evidence = evaluate_anchor_package(
        provisional_package,
        latitude=edge_tract.latitude,
        longitude=edge_tract.longitude,
        opaque_anchor_identity="public-tiger-edge-internal-point-qa",
        opaque_anchor_lineage="official-2024-TIGER-internal-point-selected-by-minimum-projected-support-boundary-distance",
    )
    interior_evidence = evaluate_anchor_package(
        provisional_package,
        latitude=interior_tract.latitude,
        longitude=interior_tract.longitude,
        opaque_anchor_identity="public-tiger-interior-internal-point-qa",
        opaque_anchor_lineage="official-2024-TIGER-internal-point-selected-by-maximum-projected-support-boundary-distance",
    )
    require(
        any(item["extends_outside_michigan_support"] for item in edge_evidence["support_completeness"]),
        "GEO05_EDGE_QA_NOT_EXERCISED",
        "deterministic edge internal point did not exercise support truncation",
    )

    output_hashes = {
        output_contract["inventory_filename"]: file_sha256(inventory_path),
        output_contract["projected_internal_points_filename"]: file_sha256(projected_path),
        output_contract["source_geometries_filename"]: file_sha256(geometries_path),
        output_contract["projected_support_geometry_filename"]: file_sha256(support_path),
        output_contract["runtime_provenance_filename"]: file_sha256(runtime_path),
    }
    report = {
        "report_id": REPORT_ID,
        "schema_version": output_contract["schema_version"],
        "state": "VERIFIED",
        "spatial_spec_id": specification["artifact_id"],
        "spatial_spec_content_sha256": specification["content_sha256"],
        "state_name": "Michigan",
        "state_fips": STATE_FIPS,
        "tract_count": len(state.tracts),
        "inventory_id": INVENTORY_ID,
        "inventory_sha256": EXPECTED_INVENTORY_SHA256,
        "source_authority": {
            **dict(data04_lineage),
            **dict(state.source_summary),
        },
        "projection": {
            "source_crs": "EPSG:4269",
            "target_crs": "EPSG:5070",
            "logical_input_axis_order": ["longitude", "latitude"],
            "operation_id": specification["geo03_methodology"]["operation_id"],
            "operation_fingerprint_sha256": specification["geo03_methodology"]["operation_fingerprint_sha256"],
            "runtime_provenance": dict(state.runtime_provenance),
        },
        "spatial_evidence": {
            "ordered_unique_geoid_count": len(state.tracts),
            "statefp_26_count": len(state.tracts),
            "component_consistent_geoid_count": len(state.tracts),
            "valid_source_geometry_count": len(state.tracts),
            "valid_internal_point_count": len(state.tracts),
            "projected_internal_point_count": len(state.tracts),
            "source_internal_point_covered_by_keyed_geometry_count": len(state.tracts),
            "projected_internal_point_covered_by_keyed_geometry_count": len(state.tracts),
            "missing_tract_count": 0,
            "extra_tract_count": 0,
            "duplicate_tract_count": 0,
            "substituted_tract_count": 0,
        },
        "state_support": {
            "support_kind": "union of all accepted Michigan tract geometries projected to EPSG:5070",
            "geometry_type": state.projected_support.geom_type,
            "is_valid": bool(state.projected_support.is_valid),
            "area_m2": float(state.projected_support.area),
            "bounds_m": [float(value) for value in state.projected_support.bounds],
            "geometry_sha256": output_hashes[output_contract["projected_support_geometry_filename"]],
            "all_projected_internal_points_covered": True,
        },
        "public_anchor_qa": {
            "protected_anchor_used": False,
            "coordinates_disclosed_in_report": False,
            "default_radii_m": list(DEFAULT_RADII_M),
            "edge_internal_point": _summarize_public_anchor_qa(edge_evidence, "minimum projected distance from official internal point to Michigan support boundary"),
            "interior_internal_point": _summarize_public_anchor_qa(interior_evidence, "maximum projected distance from official internal point to Michigan support boundary"),
        },
        "output_files": output_hashes,
        "materialization_safeguards": {
            "output_directory_created_incomplete_first": True,
            "overwrite_denied": True,
            "ready_marker_written_last": True,
            "bulk_outputs_outside_tracked_git": True,
        },
        "model_downstream_compatibility": {
            "radii_owned_by_model": True,
            "default_radii_m": list(DEFAULT_RADII_M),
            "containing_tract_forced": True,
            "deterministic_member_order": True,
            "model_execution_performed": False,
            "scoring_authority_created": False,
        },
        "protected_evidence_access": {
            "public_census_data_only": True,
            "sprouts_or_protected_evidence_accessed": False,
            "protected_filesystem_discovery_performed": False,
            "protected_anchor_instance_created": False,
        },
    }
    write_json_exclusive(report_path, report)
    ready_files = {**output_hashes, output_contract["verification_report_filename"]: file_sha256(report_path)}
    ready = {
        "state": "READY",
        "schema_version": output_contract["schema_version"],
        "spatial_spec_id": specification["artifact_id"],
        "spatial_spec_content_sha256": specification["content_sha256"],
        "inventory_id": INVENTORY_ID,
        "inventory_sha256": EXPECTED_INVENTORY_SHA256,
        "tract_count": EXPECTED_TRACT_COUNT,
        "report_filename": output_contract["verification_report_filename"],
        "report_sha256": file_sha256(report_path),
        "files": ready_files,
        "ready_marker_written_last": True,
    }
    write_json_exclusive(ready_path, ready)
    return report


def _expected_package_filenames(authority: Geo05Authority) -> set[str]:
    output = authority.specification["materialization_contract"]
    return {
        output["inventory_filename"],
        output["projected_internal_points_filename"],
        output["source_geometries_filename"],
        output["projected_support_geometry_filename"],
        output["runtime_provenance_filename"],
        output["verification_report_filename"],
    }


def load_support_package(repository_root: Path, materialization_dir: Path) -> SupportPackage:
    """Load and fully verify one immutable public support package."""
    authority = load_authority(repository_root.resolve())
    directory = materialization_dir.resolve()
    require(directory.is_dir(), "GEO05_SUPPORT_PACKAGE_UNRESOLVED", "GEO-05 support package directory is absent")
    output = authority.specification["materialization_contract"]
    ready_path = directory / output["ready_filename"]
    ready = _load_object(ready_path, "GEO05_SUPPORT_READY_UNRESOLVED")
    expected = _expected_package_filenames(authority)
    actual_files = {
        path.relative_to(directory).as_posix()
        for path in directory.rglob("*")
        if path.is_file()
    }
    require(
        ready.get("state") == "READY"
        and ready.get("ready_marker_written_last") is True
        and ready.get("schema_version") == output["schema_version"]
        and ready.get("spatial_spec_id") == SPECIFICATION_ID
        and ready.get("spatial_spec_content_sha256") == authority.specification["content_sha256"]
        and ready.get("inventory_id") == INVENTORY_ID
        and ready.get("inventory_sha256") == EXPECTED_INVENTORY_SHA256
        and ready.get("tract_count") == EXPECTED_TRACT_COUNT
        and set(ready.get("files", {})) == expected,
        "GEO05_SUPPORT_READY_MISMATCH",
        "GEO-05 support READY identity or file inventory differs",
    )
    require(
        actual_files == expected | {output["ready_filename"]},
        "GEO05_SUPPORT_FILE_INVENTORY_MISMATCH",
        "GEO-05 support directory contains a missing, extra, or nested file",
    )
    for filename, expected_hash in ready["files"].items():
        path = directory / filename
        require(path.is_file() and file_sha256(path) == expected_hash, "GEO05_SUPPORT_FILE_HASH_MISMATCH", f"GEO-05 support file differs: {filename}")
    report_path = directory / output["verification_report_filename"]
    report = _load_object(report_path, "GEO05_SUPPORT_REPORT_UNRESOLVED")
    require(
        ready.get("report_filename") == output["verification_report_filename"]
        and ready.get("report_sha256") == file_sha256(report_path)
        and report.get("report_id") == REPORT_ID
        and report.get("state") == "VERIFIED"
        and report.get("spatial_spec_content_sha256") == authority.specification["content_sha256"]
        and report.get("tract_count") == EXPECTED_TRACT_COUNT
        and report.get("inventory_sha256") == EXPECTED_INVENTORY_SHA256
        and report.get("output_files") == {
            filename: ready["files"][filename]
            for filename in expected
            if filename != output["verification_report_filename"]
        }
        and report.get("protected_evidence_access", {}).get("sprouts_or_protected_evidence_accessed") is False,
        "GEO05_SUPPORT_REPORT_MISMATCH",
        "GEO-05 support verification report differs",
    )

    inventory = _load_object(directory / output["inventory_filename"], "GEO05_SUPPORT_INVENTORY_UNRESOLVED")
    ordered_geoids = inventory.get("ordered_geoids")
    require(
        inventory.get("artifact_id") == INVENTORY_ID
        and inventory.get("support_kind") == "complete_statewide_spatial_support"
        and inventory.get("market_inventory") is False
        and inventory.get("tract_count") == EXPECTED_TRACT_COUNT
        and inventory.get("inventory_sha256") == EXPECTED_INVENTORY_SHA256
        and isinstance(ordered_geoids, list)
        and ordered_geoids == sorted(ordered_geoids)
        and len(ordered_geoids) == len(set(ordered_geoids)) == EXPECTED_TRACT_COUNT
        and inventory_digest(ordered_geoids) == EXPECTED_INVENTORY_SHA256,
        "GEO05_SUPPORT_INVENTORY_MISMATCH",
        "GEO-05 materialized statewide inventory differs",
    )

    points: dict[str, dict[str, Any]] = {}
    with (directory / output["projected_internal_points_filename"]).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        require(reader.fieldnames == PROJECTED_POINT_COLUMNS, "GEO05_PROJECTED_POINT_SCHEMA_MISMATCH", "projected internal-point columns differ")
        for row in reader:
            geoid = row["tract_geoid"]
            require(geoid not in points, "GEO05_PROJECTED_POINT_DUPLICATE", "projected internal point is duplicate")
            try:
                latitude = float.fromhex(row["intptlat_hex"])
                longitude = float.fromhex(row["intptlon_hex"])
                x_value = float.fromhex(row["internal_x_m_hex"])
                y_value = float.fromhex(row["internal_y_m_hex"])
            except ValueError as exc:
                raise ConformanceError("GEO05_PROJECTED_POINT_NONCOMPUTABLE", f"projected internal-point encoding is invalid for {geoid}") from exc
            require(
                re.fullmatch(r"26[0-9]{9}", geoid) is not None
                and geoid == row["state_fips"] + row["county_fips"] + row["tract_code"]
                and row["state_fips"] == STATE_FIPS
                and row["coordinate_state"] == row["projection_state"] == "valid"
                and row["source_crs"] == "EPSG:4269"
                and row["target_crs"] == "EPSG:5070"
                and row["source_manifest_id"] == authority.specification["data04_source_authority"]["tiger_manifest"]["artifact_id"]
                and row["operation_fingerprint_sha256"] == authority.specification["geo03_methodology"]["operation_fingerprint_sha256"]
                and float(row["intptlat_raw"]) == latitude
                and float(row["intptlon_raw"]) == longitude
                and all(math.isfinite(value) for value in (latitude, longitude, x_value, y_value)),
                "GEO05_PROJECTED_POINT_MISMATCH",
                f"projected internal-point evidence differs for {geoid}",
            )
            points[geoid] = {"latitude": latitude, "longitude": longitude, "x": x_value, "y": y_value}
    require(list(points) == ordered_geoids, "GEO05_PROJECTED_POINT_ORDER_MISMATCH", "projected internal-point inventory or order differs")

    geometries: dict[str, BaseGeometry] = {}
    with (directory / output["source_geometries_filename"]).open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            try:
                row = json.loads(raw_line)
                geoid = row["tract_geoid"]
                geometry = wkb.loads(row["source_geometry_wkb_hex"], hex=True)
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                raise ConformanceError("GEO05_SOURCE_GEOMETRY_ENCODING_INVALID", "source geometry JSONL is unreadable") from exc
            require(
                row.get("source_crs") == "EPSG:4269"
                and geoid in points
                and geoid not in geometries
                and geometry.is_valid
                and not geometry.is_empty
                and geometry.area > 0
                and geometry.covers(Point(points[geoid]["longitude"], points[geoid]["latitude"])),
                "GEO05_SOURCE_GEOMETRY_MISMATCH",
                f"source geometry evidence differs for {geoid}",
            )
            geometries[geoid] = geometry
    require(list(geometries) == ordered_geoids, "GEO05_SOURCE_GEOMETRY_ORDER_MISMATCH", "source geometry inventory or order differs")
    tracts = tuple(
        SpatialTract(
            geoid=geoid,
            latitude=points[geoid]["latitude"],
            longitude=points[geoid]["longitude"],
            internal_x_m=points[geoid]["x"],
            internal_y_m=points[geoid]["y"],
            source_geometry=geometries[geoid],
        )
        for geoid in ordered_geoids
    )

    support_bytes = (directory / output["projected_support_geometry_filename"]).read_bytes()
    try:
        support = wkb.loads(support_bytes)
    except (TypeError, ValueError) as exc:
        raise ConformanceError("GEO05_STATE_SUPPORT_ENCODING_INVALID", "projected support WKB is unreadable") from exc
    require(
        support.geom_type in {"Polygon", "MultiPolygon"}
        and support.is_valid
        and not support.is_empty
        and support.area > 0
        and all(support.covers(Point(tract.internal_x_m, tract.internal_y_m)) for tract in tracts),
        "GEO05_STATE_SUPPORT_MISMATCH",
        "projected support geometry is invalid or incomplete",
    )
    runtime_document = _load_object(directory / output["runtime_provenance_filename"], "GEO05_RUNTIME_PROVENANCE_UNRESOLVED")
    require(
        runtime_document.get("operation_id") == authority.specification["geo03_methodology"]["operation_id"]
        and runtime_document.get("operation_fingerprint_sha256") == authority.specification["geo03_methodology"]["operation_fingerprint_sha256"]
        and runtime_document.get("footprint_quad_segs") == FOOTPRINT_QUAD_SEGS
        and isinstance(runtime_document.get("runtime_provenance"), dict),
        "GEO05_RUNTIME_PROVENANCE_MISMATCH",
        "GEO-03 runtime provenance differs",
    )
    transformer = Geo03ProductionTransformer(authority.geo03)
    require(
        runtime_document["runtime_provenance"] == transformer.runtime_provenance,
        "GEO05_RUNTIME_PROVENANCE_MISMATCH",
        "current runtime does not reproduce materialized GEO-03 provenance",
    )
    return SupportPackage(authority, tracts, support, runtime_document["runtime_provenance"], report)


def evaluate_anchor(
    repository_root: Path,
    materialization_dir: Path,
    *,
    latitude: float,
    longitude: float,
    opaque_anchor_identity: str,
    opaque_anchor_lineage: str,
    radii_m: Iterable[float] | None = None,
) -> dict[str, Any]:
    package = load_support_package(repository_root, materialization_dir)
    return evaluate_anchor_package(
        package,
        latitude=latitude,
        longitude=longitude,
        opaque_anchor_identity=opaque_anchor_identity,
        opaque_anchor_lineage=opaque_anchor_lineage,
        radii_m=radii_m,
    )


def compare_materializations(first: Path, second: Path, comparison_output: Path | None = None) -> dict[str, Any]:
    """Require byte-identical file inventories across independent READY runs."""
    first = first.resolve()
    second = second.resolve()
    require(first.is_dir() and second.is_dir(), "GEO05_RERUN_PACKAGE_UNRESOLVED", "both GEO-05 materialization directories are required")
    for directory in (first, second):
        ready = _load_object(directory / "READY.json", "GEO05_RERUN_READY_UNRESOLVED")
        require(ready.get("state") == "READY" and ready.get("ready_marker_written_last") is True, "GEO05_RERUN_READY_MISMATCH", "both GEO-05 materializations must be READY")
    first_files = sorted(path.relative_to(first).as_posix() for path in first.rglob("*") if path.is_file())
    second_files = sorted(path.relative_to(second).as_posix() for path in second.rglob("*") if path.is_file())
    require(first_files == second_files and bool(first_files), "GEO05_RERUN_FILE_INVENTORY_MISMATCH", "GEO-05 materialization file inventories differ")
    hashes: dict[str, str] = {}
    for relative in first_files:
        left = first / relative
        right = second / relative
        left_hash = file_sha256(left)
        require(left_hash == file_sha256(right), "GEO05_RERUN_NONDETERMINISTIC", f"GEO-05 rerun bytes differ for {relative}")
        hashes[relative] = left_hash
    report = {
        "comparison_id": "GEO05_MICHIGAN_STATEWIDE_SPATIAL_SUPPORT_DETERMINISM_V1",
        "state": "DETERMINISTIC_BYTE_IDENTICAL",
        "file_count": len(hashes),
        "file_sha256": hashes,
        "ready_markers_included": "READY.json" in hashes,
    }
    if comparison_output is not None:
        write_json_exclusive(comparison_output.resolve(), report)
    return report
