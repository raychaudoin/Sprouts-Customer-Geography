"""Deterministic public Michigan 2024 TIGER tract presentation geometry."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any, Mapping
from zipfile import ZipFile

from shapely.geometry import mapping, shape
from shapely.geometry.base import BaseGeometry

from sprouts_customer_geography.data04.contract import load_authority
from sprouts_customer_geography.data04.materialization import load_tiger_evidence
from sprouts_customer_geography.geo04 import tiger_rows_from_source_zip
from sprouts_customer_geography.pipe01.canonical import content_digest, file_sha256
from sprouts_customer_geography.pipe01.errors import require
from sprouts_customer_geography.pipe01.production import _read_shapefile_polygons


ARTIFACT_ID = "PBI01_MICHIGAN_2024_TIGER_TRACT_PRESENTATION_GEOMETRY_V1"
EXPECTED_SOURCE_SHA256 = "220c0a351d94c9de456d87c5db78f3e3864b3287370350f1e503a84565224e82"
EXPECTED_INVENTORY_SHA256 = "8b6698b55423911163f1a2330ad600218a3b8b452576cc9b3d3997ada19e6c9b"
EXPECTED_TRACT_COUNT = 3_017
DEFAULT_SIMPLIFY_TOLERANCE = 0.001
DEFAULT_COORDINATE_PRECISION = 5


def _rounded_coordinates(value: Any, precision: int) -> Any:
    if isinstance(value, (list, tuple)):
        if value and all(isinstance(item, (int, float)) for item in value):
            return [round(float(item), precision) for item in value]
        return [_rounded_coordinates(item, precision) for item in value]
    return value


def _presentation_geometry(geometry: BaseGeometry, tolerance: float, precision: int) -> Mapping[str, Any]:
    simplified = geometry.simplify(tolerance, preserve_topology=True)
    require(not simplified.is_empty and simplified.is_valid and simplified.geom_type in {"Polygon", "MultiPolygon"}, "PBI01_PRESENTATION_GEOMETRY_INVALID", "simplification produced invalid presentation geometry")
    document = mapping(simplified)
    rounded = {"type": document["type"], "coordinates": _rounded_coordinates(document["coordinates"], precision)}
    reconstructed = shape(rounded)
    require(not reconstructed.is_empty and reconstructed.is_valid and reconstructed.geom_type in {"Polygon", "MultiPolygon"}, "PBI01_PRESENTATION_GEOMETRY_ROUNDING_INVALID", "coordinate rounding produced invalid presentation geometry")
    return rounded


def build_geojson(
    repository_root: Path,
    source_zip: Path,
    *,
    simplify_tolerance: float = DEFAULT_SIMPLIFY_TOLERANCE,
    coordinate_precision: int = DEFAULT_COORDINATE_PRECISION,
) -> tuple[bytes, dict[str, Any]]:
    root = repository_root.resolve()
    require(simplify_tolerance > 0 and coordinate_precision >= 4, "PBI01_GEOMETRY_PARAMETER_INVALID", "presentation geometry parameters are invalid")
    authority = load_authority(root)
    require(file_sha256(source_zip) == EXPECTED_SOURCE_SHA256, "PBI01_TIGER_SOURCE_MISMATCH", "TIGER source bytes differ from accepted authority")
    evidence, _summary = load_tiger_evidence(source_zip, authority)
    rows = tiger_rows_from_source_zip(source_zip, authority.tiger_manifest, "26")
    stem = authority.tiger_manifest["source_filename"].removesuffix(".zip")
    with ZipFile(source_zip) as archive:
        geometries = _read_shapefile_polygons(archive.read(f"{stem}.shp"))
    require(len(evidence) == len(rows) == len(geometries) == EXPECTED_TRACT_COUNT, "PBI01_TIGER_GEOMETRY_COUNT_MISMATCH", "TIGER attributes and geometry do not reconcile")

    keyed: dict[str, BaseGeometry] = {}
    for row, geometry in zip(rows, geometries):
        geoid = str(row.get("GEOID", ""))
        require(re.fullmatch(r"26[0-9]{9}", geoid) is not None and geoid == f"{row.get('STATEFP', '')}{row.get('COUNTYFP', '')}{row.get('TRACTCE', '')}", "PBI01_TIGER_GEOID_INVALID", "TIGER GEOID identity differs")
        require(geoid not in keyed, "PBI01_TIGER_DUPLICATE_GEOID", "TIGER contains a duplicate GEOID")
        keyed[geoid] = geometry
    geoids = sorted(keyed)
    require(content_digest({"ordered_geoids": geoids}) == EXPECTED_INVENTORY_SHA256, "PBI01_TIGER_INVENTORY_MISMATCH", "TIGER inventory differs from accepted GEO-05 authority")

    features: list[dict[str, Any]] = []
    for geoid in geoids:
        features.append({
            "type": "Feature",
            "id": geoid,
            "properties": {"GEOID": geoid},
            "geometry": _presentation_geometry(keyed[geoid], simplify_tolerance, coordinate_precision),
        })
    document = {
        "type": "FeatureCollection",
        "name": "Michigan 2024 Census Tracts",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
        "features": features,
    }
    payload = (json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")
    payload_hash = sha256(payload).hexdigest()
    manifest = {
        "$schema": "pbi01-michigan-presentation-geometry-manifest-v1",
        "artifact_id": ARTIFACT_ID,
        "version": "1.0.0",
        "source_authority": {
            "publisher": "U.S. Census Bureau",
            "product": "2024 TIGER/Line Census Tracts",
            "state_fips": "26",
            "source_filename": "tl_2024_26_tract.zip",
            "source_byte_sha256": EXPECTED_SOURCE_SHA256,
            "source_crs": "EPSG:4269",
        },
        "presentation_only": True,
        "analytical_gis_logic_in_power_bi": False,
        "tract_count": len(features),
        "unique_geoid_count": len(geoids),
        "inventory_sha256": EXPECTED_INVENTORY_SHA256,
        "geoid_property": "GEOID",
        "output_format": "GeoJSON FeatureCollection",
        "output_crs": "OGC CRS84 longitude latitude",
        "simplify_tolerance_degrees": simplify_tolerance,
        "coordinate_precision_decimal_places": coordinate_precision,
        "output_byte_sha256": payload_hash,
        "protected_content": False,
        "attribution": "U.S. Census Bureau, 2024 TIGER/Line Shapefiles.",
    }
    return payload, manifest


def write_geometry(
    repository_root: Path,
    source_zip: Path,
    output_path: Path,
    manifest_path: Path,
    *,
    replace: bool = False,
) -> dict[str, Any]:
    payload, manifest = build_geojson(repository_root, source_zip)
    if not replace:
        require(not output_path.exists() and not manifest_path.exists(), "PBI01_GEOMETRY_OUTPUT_EXISTS", "presentation geometry output already exists")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(payload)
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest
