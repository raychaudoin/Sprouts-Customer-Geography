"""Production-form public source and GEO-03 adapters for PIPE-01B.

The adapters in this module consume only checksum-pinned Census artifacts and
accepted GEO authority documents.  Raw public source files remain local and
outside Git; protected anchors are handled by ``orchestration``.
"""

from __future__ import annotations

import csv
import math
import re
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
from zipfile import ZipFile

import pyproj
from pyproj import Transformer
from shapely.geometry import MultiPolygon, Point, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform as transform_geometry

from sprouts_customer_geography.geo04 import (
    MARKETS,
    _read_dbf_records,
    derive_ordered_geoids,
    validate_inventory_document,
)

from .canonical import content_digest, file_sha256
from .errors import require
from .spatial import parse_internal_point


ACCEPTED_GEO03_OPERATION_FINGERPRINT = "3c7421053e63df6e120d8aefd142399c9c53e6a1594ed23c37c644609a21bf14"
TIGER_DBF_MEMBER = "tl_2024_55_tract.dbf"
TIGER_SHP_MEMBER = "tl_2024_55_tract.shp"
ACS_TRACT_PREFIX = "1400000US55"
ACS_GEOID_PATTERN = re.compile(r"1400000US(55[0-9]{9})")


class Geo03ProductionTransformer:
    """Verified direct NAD83/EPSG:4269 to EPSG:5070 runtime."""

    source_crs = "EPSG:4269"
    target_crs = "EPSG:5070"

    def __init__(self, specification: Mapping[str, Any]):
        transformation = specification.get("transformation")
        require(isinstance(transformation, Mapping), "GEO03_TRANSFORMATION_MISSING", "accepted GEO-03 transformation is absent")
        operation = transformation.get("operation")
        require(isinstance(operation, Mapping), "GEO03_OPERATION_MISSING", "accepted GEO-03 operation is absent")
        fingerprint = transformation.get("operation_fingerprint_sha256")
        require(fingerprint == content_digest(operation), "GEO03_OPERATION_FINGERPRINT_MISMATCH", "accepted operation fingerprint does not bind the operation definition")
        require(fingerprint == ACCEPTED_GEO03_OPERATION_FINGERPRINT, "GEO03_OPERATION_FINGERPRINT_MISMATCH", "GEO-03 operation is not the accepted production operation")
        require(operation.get("source_crs") == self.source_crs, "GEO03_OPERATION_SOURCE_CRS_MISMATCH", "accepted GEO-03 source CRS changed")
        require(operation.get("target_crs") == self.target_crs, "GEO03_OPERATION_TARGET_CRS_MISMATCH", "accepted GEO-03 target CRS changed")
        require(operation.get("logical_input_axis_order") == ["longitude", "latitude"], "GEO03_OPERATION_AXIS_ORDER_MISMATCH", "accepted longitude/latitude order changed")
        require(operation.get("alternate_datum_transformation_permitted") is False, "GEO03_ALTERNATE_DATUM_OPERATION_REJECTED", "alternate datum transformation is not permitted")
        require(operation.get("grid_dependencies") == [], "GEO03_GRID_DEPENDENCY_REJECTED", "accepted direct operation has no grid dependency")

        runtime = Transformer.from_crs(
            self.source_crs,
            self.target_crs,
            always_xy=True,
            allow_ballpark=False,
            only_best=True,
        )
        # ``always_xy`` deliberately exposes normalized CRS84-style axis order;
        # the datum must still be NAD83 while the explicit operation list below
        # proves that the only added step is axis normalization.
        require(runtime.source_crs.datum.name == "North American Datum 1983", "GEO03_RUNTIME_SOURCE_CRS_MISMATCH", "runtime source datum is not NAD83/EPSG:4269")
        require(runtime.target_crs.to_epsg() == 5070, "GEO03_RUNTIME_TARGET_CRS_MISMATCH", "runtime target is not EPSG:5070")
        require(runtime.accuracy == 0.0, "GEO03_RUNTIME_OPERATION_MISMATCH", "runtime did not select the direct zero-datum-shift operation")
        operations = tuple(runtime.operations)
        require(len(operations) == 2, "GEO03_RUNTIME_OPERATION_MISMATCH", "runtime operation must contain only axis normalization and Conus Albers projection")
        require(operations[0].method_name == "Axis Order Reversal (2D)", "GEO03_RUNTIME_AXIS_OPERATION_MISMATCH", "runtime longitude/latitude normalization differs")
        require(operations[1].method_name == "Albers Equal Area" and operations[1].name == "Conus Albers", "GEO03_RUNTIME_PROJECTION_MISMATCH", "runtime projection is not the accepted Conus Albers conversion")
        require(all(not item.has_ballpark_transformation and not item.grids for item in operations), "GEO03_RUNTIME_DATUM_OPERATION_MISMATCH", "runtime introduced a ballpark or grid datum operation")
        definition = runtime.definition
        for token in (
            "proj=pipeline",
            "proj=unitconvert",
            "xy_in=deg",
            "xy_out=rad",
            "proj=aea",
            "lat_0=23",
            "lon_0=-96",
            "lat_1=29.5",
            "lat_2=45.5",
            "x_0=0",
            "y_0=0",
            "ellps=GRS80",
        ):
            require(token in definition, "GEO03_RUNTIME_OPERATION_MISMATCH", f"runtime definition is missing accepted operation token: {token}")

        self.operation_fingerprint = str(fingerprint)
        self._runtime = runtime
        self.runtime_provenance = {
            "implementation": "pyproj.Transformer",
            "pyproj_version": pyproj.__version__,
            "proj_version": pyproj.proj_version_str,
            "source_crs": self.source_crs,
            "target_crs": self.target_crs,
            "logical_input_axis_order": ["longitude", "latitude"],
            "runtime_description": runtime.description,
            "runtime_definition": definition,
            "operation_fingerprint_sha256": self.operation_fingerprint,
            "ballpark_operation_permitted": False,
            "grid_dependencies": [],
        }

    def transform(self, longitude: float, latitude: float) -> tuple[float, float]:
        # ``always_xy=True`` and this explicit call order implement the accepted
        # logical longitude/latitude normalization.
        x_value, y_value = self._runtime.transform(longitude, latitude, errcheck=True)
        require(math.isfinite(x_value) and math.isfinite(y_value), "GEO03_RUNTIME_NONFINITE_RESULT", "projection returned a nonfinite coordinate")
        return float(x_value), float(y_value)


def _signed_ring_area(ring: list[tuple[float, float]]) -> float:
    return sum(
        left[0] * right[1] - right[0] * left[1]
        for left, right in zip(ring, ring[1:])
    ) / 2.0


def _polygon_from_shapefile_rings(rings: list[list[tuple[float, float]]]) -> BaseGeometry:
    require(bool(rings), "TIGER_SHP_RING_MISSING", "TIGER polygon has no rings")
    outers = [ring for ring in rings if _signed_ring_area(ring) < 0]
    holes = [ring for ring in rings if _signed_ring_area(ring) >= 0]
    require(bool(outers), "TIGER_SHP_RING_ORIENTATION_INVALID", "TIGER polygon has no clockwise exterior ring")
    assigned: list[list[list[tuple[float, float]]]] = [[] for _ in outers]
    outer_polygons = [Polygon(ring) for ring in outers]
    for hole in holes:
        probe = Point(hole[0])
        candidates = [index for index, outer in enumerate(outer_polygons) if outer.covers(probe)]
        require(bool(candidates), "TIGER_SHP_HOLE_UNASSIGNED", "TIGER interior ring is not within an exterior ring")
        selected = min(candidates, key=lambda index: outer_polygons[index].area)
        assigned[selected].append(hole)
    polygons = [Polygon(outer, assigned[index]) for index, outer in enumerate(outers)]
    require(all(item.is_valid and item.area > 0 for item in polygons), "TIGER_SHP_GEOMETRY_INVALID", "TIGER source polygon is structurally invalid")
    geometry: BaseGeometry = polygons[0] if len(polygons) == 1 else MultiPolygon(polygons)
    require(geometry.is_valid and not geometry.is_empty, "TIGER_SHP_GEOMETRY_INVALID", "TIGER multipart geometry is invalid")
    return geometry


def _read_shapefile_polygons(data: bytes) -> list[BaseGeometry]:
    """Read Polygon/PolygonZ/PolygonM records without a broad GIS dependency."""
    require(len(data) >= 100, "TIGER_SHP_INVALID", "TIGER shapefile header is truncated")
    require(struct.unpack_from(">I", data, 0)[0] == 9994, "TIGER_SHP_INVALID", "TIGER shapefile code is invalid")
    declared_bytes = struct.unpack_from(">I", data, 24)[0] * 2
    require(declared_bytes == len(data), "TIGER_SHP_LENGTH_MISMATCH", "TIGER shapefile declared length differs from source bytes")
    require(struct.unpack_from("<I", data, 28)[0] == 1000, "TIGER_SHP_INVALID", "TIGER shapefile version is invalid")
    require(struct.unpack_from("<I", data, 32)[0] in {5, 15, 25}, "TIGER_SHP_TYPE_INVALID", "TIGER shapefile is not polygonal")
    output: list[BaseGeometry] = []
    offset = 100
    expected_record = 1
    while offset < len(data):
        require(offset + 8 <= len(data), "TIGER_SHP_RECORD_TRUNCATED", "TIGER record header is truncated")
        record_number, content_words = struct.unpack_from(">II", data, offset)
        require(record_number == expected_record and content_words > 0, "TIGER_SHP_RECORD_INVALID", "TIGER shapefile record numbering or length is invalid")
        content_start = offset + 8
        content_end = content_start + content_words * 2
        require(content_end <= len(data), "TIGER_SHP_RECORD_TRUNCATED", "TIGER polygon record is truncated")
        shape_type = struct.unpack_from("<I", data, content_start)[0]
        require(shape_type in {5, 15, 25}, "TIGER_SHP_RECORD_TYPE_INVALID", "null or nonpolygon TIGER geometry is not permitted")
        require(content_start + 44 <= content_end, "TIGER_SHP_RECORD_TRUNCATED", "TIGER polygon header is truncated")
        part_count, point_count = struct.unpack_from("<II", data, content_start + 36)
        require(part_count > 0 and point_count >= 4, "TIGER_SHP_RECORD_INVALID", "TIGER polygon part/point count is invalid")
        parts_start = content_start + 44
        points_start = parts_start + part_count * 4
        minimum_end = points_start + point_count * 16
        require(minimum_end <= content_end, "TIGER_SHP_RECORD_TRUNCATED", "TIGER polygon coordinates are truncated")
        part_offsets = list(struct.unpack_from(f"<{part_count}I", data, parts_start))
        require(part_offsets[0] == 0 and part_offsets == sorted(set(part_offsets)) and part_offsets[-1] < point_count, "TIGER_SHP_PART_INDEX_INVALID", "TIGER polygon part indexes are invalid")
        points = [struct.unpack_from("<dd", data, points_start + index * 16) for index in range(point_count)]
        require(all(math.isfinite(x_value) and math.isfinite(y_value) for x_value, y_value in points), "TIGER_SHP_COORDINATE_INVALID", "TIGER polygon contains a nonfinite coordinate")
        bounds = part_offsets + [point_count]
        rings: list[list[tuple[float, float]]] = []
        for start, stop in zip(bounds, bounds[1:]):
            ring = [(float(x_value), float(y_value)) for x_value, y_value in points[start:stop]]
            require(len(ring) >= 4 and ring[0] == ring[-1] and _signed_ring_area(ring) != 0, "TIGER_SHP_RING_INVALID", "TIGER ring is open or degenerate")
            rings.append(ring)
        output.append(_polygon_from_shapefile_rings(rings))
        offset = content_end
        expected_record += 1
    require(offset == len(data) and output, "TIGER_SHP_INVALID", "TIGER shapefile did not end at a complete record")
    return output


@dataclass(frozen=True)
class TigerMarketData:
    market_id: str
    rows: tuple[Mapping[str, Any], ...]
    source_geometries: Mapping[str, BaseGeometry]
    projected_geometries: Mapping[str, BaseGeometry]


@dataclass(frozen=True)
class TigerProductionBundle:
    markets: Mapping[str, TigerMarketData]
    source_sha256: str
    source_lineage: Mapping[str, Any]


def load_tiger_production_bundle(
    source_zip: Path,
    manifest: Mapping[str, Any],
    inventories: Mapping[str, Mapping[str, Any]],
    derivation: Mapping[str, Any],
    transformer: Geo03ProductionTransformer,
) -> TigerProductionBundle:
    require(source_zip.name == manifest.get("source_filename"), "TIGER_SOURCE_FILENAME_MISMATCH", "TIGER local filename differs from accepted source identity")
    expected_length = manifest.get("retrieval", {}).get("expected_byte_length")
    require(source_zip.is_file() and source_zip.stat().st_size == expected_length, "TIGER_SOURCE_LENGTH_MISMATCH", "TIGER local byte length differs from accepted source")
    expected_sha = str(manifest.get("byte_sha256", ""))
    require(file_sha256(source_zip) == expected_sha, "TIGER_SOURCE_CHECKSUM_MISMATCH", "TIGER local bytes differ from the accepted checksum")
    with ZipFile(source_zip) as archive:
        names = set(archive.namelist())
        required_entries = set(manifest.get("expected_file_properties", {}).get("required_entries", []))
        require(required_entries <= names and {TIGER_DBF_MEMBER, TIGER_SHP_MEMBER} <= names, "TIGER_ZIP_ENTRY_MISSING", "accepted TIGER ZIP entries are incomplete")
        records = _read_dbf_records(archive.read(TIGER_DBF_MEMBER))
        geometries = _read_shapefile_polygons(archive.read(TIGER_SHP_MEMBER))
    require(len(records) == len(geometries), "TIGER_ATTRIBUTE_GEOMETRY_COUNT_MISMATCH", "TIGER DBF and shapefile record counts differ")
    required_fields = {"STATEFP", "COUNTYFP", "TRACTCE", "GEOID", "INTPTLAT", "INTPTLON"}
    require(records and required_fields <= set(records[0]), "TIGER_SOURCE_FIELD_MISSING", "TIGER production fields are absent")

    records_by_geoid: dict[str, Mapping[str, str]] = {}
    source_geometries: dict[str, BaseGeometry] = {}
    for record, geometry in zip(records, geometries):
        geoid = str(record.get("GEOID", ""))
        require(len(geoid) == 11 and geoid.isdigit(), "TIGER_GEOID_INVALID", "TIGER GEOID is structurally invalid")
        require(geoid == f"{record.get('STATEFP', '')}{record.get('COUNTYFP', '')}{record.get('TRACTCE', '')}", "TIGER_GEOID_COMPONENT_MISMATCH", "TIGER GEOID does not match its components")
        require(geoid not in records_by_geoid, "TIGER_DUPLICATE_GEOID", "TIGER source contains a duplicate GEOID")
        records_by_geoid[geoid] = record
        source_geometries[geoid] = geometry

    source_lineage = {
        "tiger_manifest_id": manifest.get("manifest_id"),
        "tiger_manifest_version": manifest.get("manifest_version"),
        "tiger_source_sha256": expected_sha,
        "tiger_vintage": manifest.get("accepted_vintage"),
        "source_filename": manifest.get("source_filename"),
    }
    market_data: dict[str, TigerMarketData] = {}
    for market_id, inventory in inventories.items():
        validate_inventory_document(inventory, derivation)
        derived = derive_ordered_geoids(records, MARKETS[market_id]["county_allow_list"])
        ordered = inventory.get("ordered_geoids")
        require(derived == ordered, "TIGER_CANONICAL_INVENTORY_MISMATCH", f"TIGER rows do not reproduce the accepted {market_id} inventory")
        require(isinstance(ordered, list), "TIGER_CANONICAL_INVENTORY_MISMATCH", "accepted inventory rows are absent")
        rows: list[Mapping[str, Any]] = []
        selected_source: dict[str, BaseGeometry] = {}
        selected_projected: dict[str, BaseGeometry] = {}
        for geoid in ordered:
            record = records_by_geoid.get(geoid)
            geometry = source_geometries.get(geoid)
            require(record is not None and geometry is not None, "TIGER_CANONICAL_TRACT_MISSING", f"accepted tract evidence is absent for {geoid}")
            point = parse_internal_point(record.get("INTPTLAT"), record.get("INTPTLON"))
            rows.append(
                {
                    "market_id": market_id,
                    "tract_geoid": geoid,
                    "INTPTLAT": record.get("INTPTLAT"),
                    "INTPTLON": record.get("INTPTLON"),
                    "coordinate_state": point.coordinate_state,
                    "source_lineage": {**source_lineage, "inventory_artifact_id": inventory.get("artifact_id"), "inventory_sha256": inventory.get("inventory_sha256")},
                }
            )
            projected = transform_geometry(transformer.transform, geometry)
            require(projected.is_valid and not projected.is_empty and projected.area > 0, "TIGER_PROJECTED_GEOMETRY_INVALID", f"projected TIGER geometry is invalid for {geoid}")
            selected_source[geoid] = geometry
            selected_projected[geoid] = projected
        market_data[market_id] = TigerMarketData(market_id, tuple(rows), selected_source, selected_projected)
    return TigerProductionBundle(market_data, expected_sha, source_lineage)


ACS_SPECIAL_VALUES: dict[int, tuple[str, str]] = {
    -999_999_999: ("suppressed", "N_INSUFFICIENT_SAMPLE_CASES"),
    -888_888_888: ("inapplicable", "X_NOT_APPLICABLE_OR_AVAILABLE"),
    -777_777_777: ("invalid", "Z_SPECIAL_VALUE_UNAUTHORIZED_FOR_B11001"),
    -666_666_666: ("missing", "INSUFFICIENT_SAMPLE_OBSERVATIONS"),
    -555_555_555: ("inapplicable", "CONTROLLED_ESTIMATE_MOE_NOT_APPLICABLE"),
    -333_333_333: ("inapplicable", "OPEN_INTERVAL_MEDIAN_MOE_NOT_APPLICABLE"),
    -222_222_222: ("missing", "MOE_INSUFFICIENT_SAMPLE_OBSERVATIONS"),
}
ACS_STATUS_PRECEDENCE = {"valid": 0, "missing": 1, "inapplicable": 2, "suppressed": 3, "invalid": 4}


def _parse_acs_token(raw_value: object, field: str) -> tuple[int | None, str, str]:
    raw = "" if raw_value is None else str(raw_value)
    if raw == "":
        return None, "missing", f"{field}_EMPTY"
    if not re.fullmatch(r"-?[0-9]+", raw):
        return None, "invalid", f"{field}_NONINTEGER"
    value = int(raw)
    if value in ACS_SPECIAL_VALUES:
        status, detail = ACS_SPECIAL_VALUES[value]
        return None, status, f"{field}_{detail}"
    if value < 0:
        return None, "invalid", f"{field}_NEGATIVE_UNRECOGNIZED"
    return value, "valid", f"{field}_PUBLISHED_INTEGER"


def parse_acs_b11001_values(raw_estimate: object, raw_moe: object) -> dict[str, Any]:
    """Parse B11001 estimate/MOE without converting special evidence to zero."""
    estimate, estimate_status, estimate_detail = _parse_acs_token(raw_estimate, "estimate")
    moe, moe_status, moe_detail = _parse_acs_token(raw_moe, "moe")
    status = max((estimate_status, moe_status), key=ACS_STATUS_PRECEDENCE.__getitem__)
    return {
        "raw_estimate": None if raw_estimate is None else str(raw_estimate),
        "raw_moe": None if raw_moe is None else str(raw_moe),
        "estimate": estimate,
        "moe": moe,
        "annotation": None,
        "status": status,
        "status_detail": {"estimate": estimate_detail, "moe": moe_detail},
    }


@dataclass(frozen=True)
class AcsProductionBundle:
    markets: Mapping[str, tuple[Mapping[str, Any], ...]]
    wisconsin_tract_count: int
    source_lineage: Mapping[str, Any]


def load_statewide_acs_b11001_evidence(
    source_file: Path,
    manifest: Mapping[str, Any],
    state_fips: str,
    expected_tract_count: int,
) -> tuple[dict[str, Mapping[str, Any]], dict[str, Any]]:
    """Verify the accepted national B11001 bytes and extract one configured state."""
    require(len(state_fips) == 2 and state_fips.isdigit(), "ACS_STATE_FIPS_INVALID", "state FIPS must contain two digits")
    require(expected_tract_count > 0, "ACS_STATE_TRACT_COUNT_INVALID", "state tract count must be positive")
    require(source_file.name == manifest.get("source_filename"), "ACS_SOURCE_FILENAME_MISMATCH", "ACS local filename differs from accepted source identity")
    expected_length = manifest.get("retrieval", {}).get("expected_byte_length")
    require(source_file.is_file() and source_file.stat().st_size == expected_length, "ACS_SOURCE_LENGTH_MISMATCH", "ACS local byte length differs from accepted source")
    expected_sha = str(manifest.get("byte_sha256", ""))
    require(file_sha256(source_file) == expected_sha, "ACS_SOURCE_CHECKSUM_MISMATCH", "ACS local bytes differ from the accepted checksum")
    request = manifest.get("request_identity")
    require(isinstance(request, Mapping) and content_digest(request) == manifest.get("request_sha256"), "ACS_REQUEST_IDENTITY_MISMATCH", "ACS request identity hash differs")
    required_header = set(request.get("header_required", []))
    prefix = f"1400000US{state_fips}"
    geoid_pattern = re.compile(rf"1400000US({re.escape(state_fips)}[0-9]{{9}})")
    state_name = "Wisconsin" if state_fips == "55" else "Michigan" if state_fips == "26" else f"state {state_fips}"
    by_geoid: dict[str, Mapping[str, Any]] = {}
    with source_file.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="|")
        require(reader.fieldnames is not None and required_header <= set(reader.fieldnames), "ACS_SOURCE_HEADER_MISMATCH", "accepted ACS B11001 fields are absent")
        for source_row in reader:
            require(None not in source_row, "ACS_SOURCE_ROW_MALFORMED", "ACS row has more fields than its header")
            geo_identity = str(source_row.get("GEO_ID", ""))
            if not geo_identity.startswith(prefix):
                continue
            match = geoid_pattern.fullmatch(geo_identity)
            require(match is not None, "ACS_TRACT_IDENTITY_INVALID", f"{state_name} tract GEO_ID is structurally invalid")
            geoid = match.group(1)
            require(geoid not in by_geoid, "ACS_DUPLICATE_TRACT_GEOID", f"ACS source contains a duplicate {state_name} tract GEOID")
            parsed = parse_acs_b11001_values(source_row.get("B11001_E001"), source_row.get("B11001_M001"))
            by_geoid[geoid] = {"tract_geoid": geoid, **parsed}
    count_code = "ACS_WISCONSIN_TRACT_COUNT_MISMATCH" if state_fips == "55" else "ACS_STATE_TRACT_COUNT_MISMATCH"
    count_message = "ACS Wisconsin tract row count differs from accepted source evidence" if state_fips == "55" else "ACS state tract row count differs from source authority"
    require(len(by_geoid) == expected_tract_count, count_code, count_message)
    source_lineage = {
        "acs_manifest_id": manifest.get("manifest_id"),
        "acs_manifest_version": manifest.get("manifest_version"),
        "acs_source_id": manifest.get("source_id"),
        "acs_source_sha256": expected_sha,
        "acs_vintage": manifest.get("accepted_vintage"),
        "request_sha256": manifest.get("request_sha256"),
        "estimate_source_field": "B11001_E001",
        "moe_source_field": "B11001_M001",
        "estimate_contract_field": "B11001_001E",
        "moe_contract_field": "B11001_001M",
        "annotation_source_state": "not_present_in_pinned_table_based_source",
        "state_fips": state_fips,
        "table_file_geo_id_prefix": prefix,
    }
    return by_geoid, source_lineage


def load_acs_b11001_production_bundle(
    source_file: Path,
    manifest: Mapping[str, Any],
    inventories: Mapping[str, Mapping[str, Any]],
) -> AcsProductionBundle:
    expected_count = manifest.get("expected_file_properties", {}).get("expected_wisconsin_tract_row_count_at_retrieval")
    require(isinstance(expected_count, int), "ACS_WISCONSIN_TRACT_COUNT_MISMATCH", "accepted Wisconsin tract count is absent")
    by_geoid, source_lineage = load_statewide_acs_b11001_evidence(source_file, manifest, "55", expected_count)
    source_lineage = {key: value for key, value in source_lineage.items() if key not in {"state_fips", "table_file_geo_id_prefix"}}
    markets: dict[str, tuple[Mapping[str, Any], ...]] = {}
    for market_id, inventory in inventories.items():
        ordered = inventory.get("ordered_geoids")
        require(isinstance(ordered, list), "ACS_CANONICAL_INVENTORY_MISMATCH", "accepted inventory rows are absent")
        missing = [geoid for geoid in ordered if geoid not in by_geoid]
        require(not missing, "ACS_CANONICAL_TRACT_MISSING", f"ACS evidence is absent for {len(missing)} accepted {market_id} tract(s)")
        markets[market_id] = tuple(by_geoid[geoid] for geoid in ordered)
    return AcsProductionBundle(markets, len(by_geoid), source_lineage)
