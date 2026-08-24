"""GEO-04 authoritative public spatial dependency materialization.

The module deliberately contains no protected anchors, instances, predictions, or
target data.  It provides the reproducible public-source derivation used to
create the committed GEO authority artifacts.
"""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import struct
from typing import Any, Iterable, Mapping
from zipfile import ZipFile

from sprouts_customer_geography.pipe01.canonical import content_digest, file_sha256, write_json_exclusive
from sprouts_customer_geography.pipe01.data_contracts import (
    DATA_CONFIG_ID,
    TIGER_MANIFEST_ID,
    validate_data02_contract,
)
from sprouts_customer_geography.pipe01.errors import require


DERIVATION_ID = "GEO04_CANONICAL_TRACT_INVENTORY_DERIVATION_V1"
CONTEXT_SPEC_ID = "GEO02_VALIDATION_CONTEXT_SPATIAL_SPEC_V1"
MEMBERSHIP_SPEC_ID = "GEO03_INTERNAL_POINT_MEMBERSHIP_SPATIAL_SPEC_V1"
DISTANCE_SPEC_ID = "GEO03_EPSG5070_PLANAR_ANCHOR_TO_TRACT_INTPT_M_V1"
VERSION = "1.0.0"
TIGER_SHA256 = "313c378d7fa173bf653381d644d8ded7b4f6241b2065d2b890e1fccccaab5de5"

MARKETS: dict[str, dict[str, Any]] = {
    "milwaukee": {
        "artifact_id": "GEO04_CANONICAL_TRACT_INVENTORY_MILWAUKEE_V1",
        "county_allow_list": ["55079", "55089", "55131", "55133"],
        "qa_expected_count": 452,
    },
    "madison": {
        "artifact_id": "GEO04_CANONICAL_TRACT_INVENTORY_MADISON_V1",
        "county_allow_list": ["55021", "55025", "55045", "55049"],
        "qa_expected_count": 152,
    },
}


def _without(value: Mapping[str, Any], field: str) -> dict[str, Any]:
    result = deepcopy(dict(value))
    result.pop(field, None)
    return result


def _self_hash(document: Mapping[str, Any], field: str = "content_sha256") -> str:
    expected = document.get(field)
    require(isinstance(expected, str) and len(expected) == 64, "GEO04_CONTENT_HASH_MISSING", f"missing {field}")
    actual = content_digest(_without(document, field))
    require(actual == expected, "GEO04_CONTENT_HASH_MISMATCH", f"{field} does not match canonical JSON")
    return actual


def _required_text(value: object, name: str, length: int) -> str:
    parsed = str(value).strip()
    require(len(parsed) == length and parsed.isdigit(), "GEO04_SOURCE_COMPONENT_INVALID", f"invalid {name}")
    return parsed


def _read_dbf_records(data: bytes) -> list[dict[str, str]]:
    """Read the TIGER DBF attributes needed by GEO-04 without a GIS runtime."""
    require(len(data) >= 33, "GEO04_DBF_INVALID", "DBF is shorter than the required header")
    record_count = struct.unpack_from("<I", data, 4)[0]
    header_length = struct.unpack_from("<H", data, 8)[0]
    record_length = struct.unpack_from("<H", data, 10)[0]
    require(header_length >= 33 and record_length >= 2, "GEO04_DBF_INVALID", "DBF header lengths are invalid")
    require(len(data) >= header_length + record_count * record_length, "GEO04_DBF_TRUNCATED", "DBF records are truncated")
    fields: list[tuple[str, int]] = []
    offset = 32
    while offset < header_length:
        if data[offset] == 0x0D:
            break
        require(offset + 32 <= len(data), "GEO04_DBF_INVALID", "DBF field descriptor is truncated")
        name = data[offset : offset + 11].split(b"\x00", 1)[0].decode("ascii").strip()
        width = data[offset + 16]
        require(name and width > 0, "GEO04_DBF_INVALID", "DBF field descriptor is invalid")
        fields.append((name, width))
        offset += 32
    require(offset < header_length and data[offset] == 0x0D, "GEO04_DBF_INVALID", "DBF header terminator is absent")
    require(sum(width for _, width in fields) + 1 == record_length, "GEO04_DBF_INVALID", "DBF record width is inconsistent")
    output: list[dict[str, str]] = []
    for index in range(record_count):
        record = data[header_length + index * record_length : header_length + (index + 1) * record_length]
        require(record[:1] != b"*", "GEO04_DBF_DELETED_ROW", "deleted TIGER DBF rows are not permitted")
        values: dict[str, str] = {}
        position = 1
        for name, width in fields:
            values[name] = record[position : position + width].decode("latin-1").strip()
            position += width
        output.append(values)
    return output


def tiger_rows_from_pinned_zip(source_zip: Path, tiger_manifest: Mapping[str, Any]) -> list[dict[str, str]]:
    """Verify DATA-02 source identity, then return Wisconsin TIGER attribute rows."""
    require(tiger_manifest.get("manifest_id") == TIGER_MANIFEST_ID, "GEO04_TIGER_MANIFEST_ID_MISMATCH", "DATA-02 TIGER manifest ID differs")
    require(tiger_manifest.get("byte_sha256") == TIGER_SHA256, "GEO04_TIGER_SOURCE_HASH_MISMATCH", "DATA-02 TIGER hash differs")
    require(file_sha256(source_zip) == TIGER_SHA256, "GEO04_TIGER_SOURCE_HASH_MISMATCH", "downloaded TIGER bytes do not match DATA-02")
    with ZipFile(source_zip) as archive:
        names = set(archive.namelist())
        required_entries = set(tiger_manifest["expected_file_properties"]["required_entries"])
        require(required_entries <= names, "GEO04_TIGER_ZIP_INCOMPLETE", "pinned TIGER ZIP entries are incomplete")
        rows = _read_dbf_records(archive.read("tl_2024_55_tract.dbf"))
    required_fields = {"STATEFP", "COUNTYFP", "TRACTCE", "GEOID"}
    require(rows and required_fields <= set(rows[0]), "GEO04_TIGER_FIELDS_MISSING", "TIGER derivation fields are missing")
    return rows


def tiger_rows_from_source_zip(
    source_zip: Path,
    tiger_manifest: Mapping[str, Any],
    state_fips: str,
) -> list[dict[str, str]]:
    """Verify one fixed-vintage state TIGER archive and return its DBF rows."""
    require(len(state_fips) == 2 and state_fips.isdigit(), "TIGER_STATE_FIPS_INVALID", "state FIPS must contain two digits")
    expected_filename = f"tl_2024_{state_fips}_tract.zip"
    require(source_zip.name == expected_filename == tiger_manifest.get("source_filename"), "TIGER_SOURCE_FILENAME_MISMATCH", "TIGER local filename differs from source authority")
    expected_length = tiger_manifest.get("retrieval", {}).get("expected_byte_length")
    require(source_zip.is_file() and source_zip.stat().st_size == expected_length, "TIGER_SOURCE_LENGTH_MISMATCH", "TIGER local byte length differs from source authority")
    expected_sha = str(tiger_manifest.get("byte_sha256", ""))
    require(file_sha256(source_zip) == expected_sha, "TIGER_SOURCE_CHECKSUM_MISMATCH", "TIGER local bytes differ from source authority")
    dbf_member = expected_filename.removesuffix(".zip") + ".dbf"
    with ZipFile(source_zip) as archive:
        names = set(archive.namelist())
        required_entries = set(tiger_manifest.get("expected_file_properties", {}).get("required_entries", []))
        require(required_entries <= names and dbf_member in names, "TIGER_ZIP_ENTRY_MISSING", "TIGER ZIP entries are incomplete")
        rows = _read_dbf_records(archive.read(dbf_member))
    required_fields = {"STATEFP", "COUNTYFP", "TRACTCE", "GEOID", "INTPTLAT", "INTPTLON"}
    require(rows and required_fields <= set(rows[0]), "TIGER_SOURCE_FIELD_MISSING", "TIGER source fields are absent")
    return rows


def derive_ordered_geoids(rows: Iterable[Mapping[str, object]], county_allow_list: Iterable[str]) -> list[str]:
    """Apply the accepted GEO-04 canonical tract selection and order semantics."""
    counties = list(county_allow_list)
    require(counties == sorted(counties) or counties, "GEO04_COUNTY_CONFIG_INVALID", "county allow-list must be nonempty")
    require(len(counties) == len(set(counties)), "GEO04_COUNTY_CONFIG_INVALID", "county allow-list contains a duplicate")
    require(all(len(county) == 5 and county.startswith("55") and county.isdigit() for county in counties), "GEO04_COUNTY_CONFIG_INVALID", "county allow-list must contain Wisconsin five-digit county GEOIDs")
    selected: list[str] = []
    all_geoids: set[str] = set()
    observed_counties: set[str] = set()
    for row in rows:
        state = _required_text(row.get("STATEFP", ""), "STATEFP", 2)
        county = _required_text(row.get("COUNTYFP", ""), "COUNTYFP", 3)
        tract = _required_text(row.get("TRACTCE", ""), "TRACTCE", 6)
        geoid = _required_text(row.get("GEOID", ""), "GEOID", 11)
        require(state == "55", "GEO04_STATEFP_MISMATCH", "pinned Wisconsin source must contain STATEFP 55")
        require(geoid == state + county + tract, "GEO04_GEOID_COMPONENT_MISMATCH", "GEOID must equal STATEFP + COUNTYFP + TRACTCE")
        require(geoid not in all_geoids, "GEO04_DUPLICATE_CANONICAL_GEOID", "duplicate canonical GEOID in TIGER source")
        all_geoids.add(geoid)
        county_geoid = state + county
        if county_geoid in counties:
            observed_counties.add(county_geoid)
            selected.append(geoid)
    require(observed_counties == set(counties), "GEO04_COUNTY_RECONCILIATION_FAILED", "configured county membership is incomplete in the TIGER source")
    ordered = sorted(selected)
    require(len(ordered) == len(set(ordered)), "GEO04_DUPLICATE_CANONICAL_GEOID", "selected inventory contains duplicate GEOIDs")
    return ordered


def inventory_digest(geoids: Iterable[str]) -> str:
    ordered = list(geoids)
    return content_digest({"ordered_geoids": ordered})


def derivation_document() -> dict[str, Any]:
    artifact = {
        "$schema": "../../schemas/geo04/canonical_tract_inventory_derivation.schema.json",
        "artifact_id": DERIVATION_ID,
        "version": VERSION,
        "owning_capability": "GEO-04",
        "purpose": "Authoritative public-source derivation specification for canonical market tract inventories.",
        "data_authority": {
            "data_contract_id": DATA_CONFIG_ID,
            "data_contract_version": VERSION,
            "data_contract_content_sha256": "31f224e87bb20c9444a061b7d8a513e45b37928158744f562d2fe8a45fe8d6e3",
            "tiger_manifest_id": TIGER_MANIFEST_ID,
            "tiger_source_sha256": TIGER_SHA256,
        },
        "source_and_selection_semantics": {
            "source": "exact DATA-02-pinned Wisconsin 2024 TIGER tract ZIP after SHA-256 verification",
            "required_statefp": "55",
            "county_selection": "positive five-digit county GEOID allow-list by configured market",
            "geoid_semantics": "retain text GEOID; require GEOID = STATEFP + COUNTYFP + TRACTCE",
            "order": "lexicographically ascending complete 11-character GEOID",
            "geometry_authority": "full canonical TIGER polygon or multipolygon geometry remains controlling",
            "market_support": "union of complete canonical in-scope tract inventory",
        },
        "invariant_checks": [
            "DATA-02 TIGER manifest ID and source SHA-256 match exactly",
            "missing, malformed, duplicate, incompatible, or non-Wisconsin canonical GEOIDs fail closed",
            "configured counties reconcile completely",
            "inventory count is a QA expectation; ordered inventory and hash are authoritative",
        ],
        "failure_behavior": "Fail closed without an exact DATA-02 source identity, a complete county reconciliation, or a deterministic ordered inventory hash. Do not substitute another release, derivative, county configuration, or order.",
        "supersedes": None,
        "supersession_policy": "Never overwrite this accepted artifact. A correction creates a versioned successor with explicit supersedes lineage and a newly calculated content_sha256.",
    }
    artifact["content_sha256"] = content_digest(artifact)
    return artifact


def inventory_document(market_id: str, geoids: Iterable[str], derivation: Mapping[str, Any]) -> dict[str, Any]:
    require(market_id in MARKETS, "GEO04_MARKET_UNKNOWN", "unknown GEO-04 market configuration")
    config = MARKETS[market_id]
    ordered = list(geoids)
    artifact = {
        "$schema": "../../schemas/geo04/canonical_tract_inventory.schema.json",
        "artifact_id": config["artifact_id"],
        "version": VERSION,
        "owning_capability": "GEO-04",
        "derivation_specification": {
            "artifact_id": derivation["artifact_id"],
            "version": derivation["version"],
            "content_sha256": derivation["content_sha256"],
        },
        "market_configuration": {
            "market_id": market_id,
            "version": VERSION,
            "ordered_county_allow_list": config["county_allow_list"],
        },
        "data_authority": derivation["data_authority"],
        "ordered_geoids": ordered,
        "inventory_sha256": inventory_digest(ordered),
        "tract_count": len(ordered),
        "qa_expected_count": config["qa_expected_count"],
        "qa_count_matches": len(ordered) == config["qa_expected_count"],
        "selection_and_order_semantics": "STATEFP 55; configured county allow-list; full 11-character GEOID text; lexicographically ascending full GEOID",
        "invariant_checks": ["unique 11-character GEOIDs", "GEOID component identity", "complete county reconciliation", "deterministic canonical inventory SHA-256"],
        "failure_behavior": "Fail closed on source identity, county configuration, GEOID, ordering, count, or inventory hash mismatch. No missing, extra, duplicate, or substituted row is neutral.",
        "supersedes": None,
        "supersession_policy": "Never overwrite this frozen inventory. A correction creates a versioned successor with explicit supersedes lineage and newly calculated hashes.",
    }
    artifact["content_sha256"] = content_digest(artifact)
    return artifact


def context_specification_document(inventories: Mapping[str, Mapping[str, Any]], derivation: Mapping[str, Any]) -> dict[str, Any]:
    artifact = {
        "$schema": "../../schemas/geo04/geo02_context_spatial_spec.schema.json",
        "artifact_id": CONTEXT_SPEC_ID,
        "version": VERSION,
        "owning_capability": "GEO-02",
        "purpose": "Repository-safe immutable GEO-02 spatial-method specification for later protected PIPE context execution.",
        "canonical_geography": {
            "tract_vintage": "2020 Census tracts",
            "geometry_representation": "2024 TIGER full canonical tract polygons or multipolygons",
            "inventory_derivation": {"artifact_id": derivation["artifact_id"], "version": derivation["version"], "content_sha256": derivation["content_sha256"]},
            "market_inventories": [{"market_id": market, "artifact_id": value["artifact_id"], "version": value["version"], "content_sha256": value["content_sha256"], "inventory_sha256": value["inventory_sha256"]} for market, value in sorted(inventories.items())],
        },
        "projected_context_space": "EPSG:5070",
        "validation_anchor_lineage_requirement": "A protected context instance must record target-blind validation-anchor lineage and one anchor_tract_geoid without committing anchor identifiers or coordinates to this specification.",
        "context_family_semantics": {
            "footprint": "metric radius footprint constructed in EPSG:5070 from protected anchor coordinates",
            "radius_parameter_owner": "MODEL",
            "tract_intersection": "positive-area intersection of full canonical tract polygon or multipolygon and metric footprint",
            "zero_area_tangency": "excluded from membership",
            "market_clipping_and_support": "market analytical support is the union of complete canonical in-scope tract inventory; clipping and edge state are explicit",
            "edge_distance_and_margin": "record metric distance and margin from footprint to market support boundary in EPSG:5070; do not infer absence of truncation from a rounded display",
            "geometric_truncation": "record whether the metric footprint extends beyond market support",
            "geometric_completeness": "record the geometry-derived completeness of retained footprint relative to full footprint",
            "geometric_jaccard": "continuous geometric overlap is the controlling Jaccard measure",
            "spatial_components": "preserve GEO spatial-component semantics and component lineage",
        },
        "quality_and_lineage": {
            "fail_closed": "missing or incompatible context, geometry, inventory, configuration, lineage, or quality evidence is noncomputable rather than neutral or favorable",
            "identity_distinction": "context specification, protected context instance, market configuration, and resulting spatial outputs are distinct immutable identities",
            "provenance": "context instances require target-blind provenance, exact specification hash, market inventory hash, CRS identity, and execution provenance",
        },
        "protected_content_boundary": "This specification contains no protected seeds, anchor coordinates, anchor IDs, identifiable context instances, predictions, targets, or residuals.",
        "supersedes": None,
        "supersession_policy": "Never overwrite this immutable specification. A correction creates a versioned successor with explicit supersedes lineage and newly calculated content_sha256.",
    }
    artifact["content_sha256"] = content_digest(artifact)
    return artifact


def membership_specification_document(context_specification: Mapping[str, Any]) -> dict[str, Any]:
    operation_definition = {
        "operation_id": "GEO03_EPSG4269_TO_EPSG5070_DIRECT_NAD83_CONUS_ALBERS_V1",
        "source_crs": "EPSG:4269",
        "target_crs": "EPSG:5070",
        "logical_input_axis_order": ["longitude", "latitude"],
        "datum_semantics": "direct NAD83 geographic to NAD83 / Conus Albers conversion; no datum transformation",
        "projection_method": {"authority": "EPSG", "code": "9822", "name": "Albers Equal Area"},
        "conversion": {"name": "Conus Albers", "latitude_of_false_origin_degrees": 23, "longitude_of_false_origin_degrees": -96, "first_standard_parallel_degrees": 29.5, "second_standard_parallel_degrees": 45.5, "false_easting_m": 0, "false_northing_m": 0},
        "canonical_pipeline": [
            {"step": "axis_normalization", "input": "longitude_latitude_degrees", "output": "EPSG:4269 geographic coordinates"},
            {"step": "direct_projection", "method": "EPSG:9822 Albers Equal Area", "output": "EPSG:5070 Cartesian metres"},
        ],
        "alternate_datum_transformation_permitted": False,
        "grid_dependencies": [],
        "runtime_provenance_requirement": "Later execution records runtime/PROJ software provenance and verifies this fingerprint; incidental runtime version is not this methodological authority.",
    }
    artifact = {
        "$schema": "../../schemas/geo04/geo03_internal_point_membership_spatial_spec.schema.json",
        "artifact_id": MEMBERSHIP_SPEC_ID,
        "version": VERSION,
        "owning_capability": "GEO-03",
        "purpose": "Repository-safe GEO-03 transformation, internal-point distance, and membership-method specification subordinate to GEO-02 contexts.",
        "source_coordinate_authority": {"source": "official 2024 TIGER INTPTLAT and INTPTLON", "source_crs": "EPSG:4269", "logical_input_axis_order": ["longitude", "latitude"], "raw_value_provenance": "retain raw TIGER source values, parse state, source manifest identity, and canonical tract GEOID; invalid or absent values are explicit noncomputable evidence"},
        "data_authority": {"tiger_manifest_id": TIGER_MANIFEST_ID, "tiger_source_sha256": TIGER_SHA256},
        "transformation": {"operation": operation_definition, "operation_fingerprint_sha256": content_digest(operation_definition)},
        "validation_membership_distance": {"artifact_id": DISTANCE_SPEC_ID, "semantics": "EPSG:5070 Euclidean planar distance from protected validation-anchor projected coordinate to official tract internal-point projected coordinate", "unit": "metre", "membership_value": "full unrounded distance", "separate_from": "GEO-01 generic descriptive geodesic or ellipsoidal location distance", "noncomputability": "missing, invalid, or failed anchor or tract projection is explicit noncomputable evidence; a non-anchor failure must not silently become nonmembership"},
        "boundary_and_radius_binding": {"comparison": "distance_m <= radius_m", "epsilon_or_snap_or_rounding_permitted": False, "owner": "MODEL", "model_reference": "MODEL-05", "radii_m": [4828.032, 8046.72, 11265.408], "nesting_invariant": "3-mile membership is a subset of 5-mile membership, which is a subset of 7-mile membership"},
        "anchor_override": {"anchor_identity_source": "GEO-02 protected context instance anchor_tract_geoid", "ordinary_and_forced_are_distinct": True, "forced_inclusion_by_radius": True, "no_duplicate_contribution": True, "valid_anchor_internal_point_evidence_gap": "valid anchor tract may be final-member through explicit MODEL-05 override only when its official internal-point distance evidence is unavailable; preserve explicit evidence-gap status", "prohibited_repair": "override must not repair structural source, inventory, anchor, context, or configuration failure"},
        "deduplication": {"membership_state_key": "membership_specification × GEO-02 context_instance_id × radius_m × tract_GEOID", "one_final_state_per_key": True, "context_identity_rule": "radius_m is an immutable MODEL-bound context-radius state and does not create a competing GEO-02 context-ID system"},
        "geo02_lineage": {"subordinate_to_context_specification": {"artifact_id": context_specification["artifact_id"], "version": context_specification["version"], "content_sha256": context_specification["content_sha256"]}, "context_instance_requirement": "later protected membership output references the GEO-02 context_instance_id; no new context identity system is permitted", "jaccard_rule": "GEO-02 geometric Jaccard remains controlling; no internal-point membership Jaccard is authorized"},
        "failure_behavior": "Fail closed on version, context lineage, source identity, operation fingerprint, CRS, coordinate-order, radius binding, inventory, or membership-state mismatch.",
        "supersedes": None,
        "supersession_policy": "Never overwrite this immutable specification. A correction creates a versioned successor with explicit supersedes lineage and newly calculated hashes.",
    }
    artifact["content_sha256"] = content_digest(artifact)
    return artifact


def validate_inventory_document(document: Mapping[str, Any], derivation: Mapping[str, Any]) -> str:
    _self_hash(document)
    market = document.get("market_configuration", {}).get("market_id")
    require(market in MARKETS, "GEO04_MARKET_UNKNOWN", "inventory market is unknown")
    config = MARKETS[str(market)]
    require(document.get("artifact_id") == config["artifact_id"] and document.get("version") == VERSION, "GEO04_INVENTORY_IDENTITY_MISMATCH", "inventory ID/version mismatch")
    require(document.get("derivation_specification", {}).get("artifact_id") == derivation.get("artifact_id") and document.get("derivation_specification", {}).get("content_sha256") == derivation.get("content_sha256"), "GEO04_DERIVATION_LINEAGE_MISMATCH", "inventory derivation lineage mismatch")
    require(document.get("data_authority") == derivation.get("data_authority"), "GEO04_DATA_LINEAGE_MISMATCH", "inventory DATA authority mismatch")
    require(document.get("market_configuration", {}).get("ordered_county_allow_list") == config["county_allow_list"], "GEO04_COUNTY_CONFIG_INVALID", "inventory county configuration mismatch")
    geoids = document.get("ordered_geoids")
    require(isinstance(geoids, list) and geoids == sorted(geoids), "GEO04_INVENTORY_ORDER_MISMATCH", "inventory must be lexicographically sorted")
    require(all(isinstance(geoid, str) and len(geoid) == 11 and geoid.isdigit() for geoid in geoids), "GEO04_GEOID_INVALID", "inventory GEOID is invalid")
    require(len(geoids) == len(set(geoids)), "GEO04_DUPLICATE_CANONICAL_GEOID", "inventory GEOIDs are duplicate")
    require(all(geoid[:5] in config["county_allow_list"] for geoid in geoids), "GEO04_COUNTY_RECONCILIATION_FAILED", "inventory contains GEOID outside configured counties")
    require(document.get("inventory_sha256") == inventory_digest(geoids), "GEO04_INVENTORY_HASH_MISMATCH", "inventory SHA-256 mismatch")
    require(document.get("tract_count") == len(geoids) == config["qa_expected_count"] and document.get("qa_count_matches") is True, "GEO04_INVENTORY_COUNT_MISMATCH", "inventory count does not match accepted QA expectation")
    return str(document["content_sha256"])


def validate_context_specification(document: Mapping[str, Any], inventories: Mapping[str, Mapping[str, Any]], derivation: Mapping[str, Any]) -> str:
    _self_hash(document)
    require(document.get("artifact_id") == CONTEXT_SPEC_ID and document.get("version") == VERSION, "GEO02_CONTEXT_VERSION_MISMATCH", "GEO-02 context ID/version mismatch")
    geography = document.get("canonical_geography")
    require(isinstance(geography, Mapping) and geography.get("inventory_derivation", {}).get("content_sha256") == derivation.get("content_sha256"), "GEO02_CONTEXT_DERIVATION_MISMATCH", "GEO-02 derivation lineage mismatch")
    references = geography.get("market_inventories", []) if isinstance(geography, Mapping) else []
    expected = {(market, value["content_sha256"], value["inventory_sha256"]) for market, value in inventories.items()}
    actual = {(value.get("market_id"), value.get("content_sha256"), value.get("inventory_sha256")) for value in references if isinstance(value, Mapping)}
    require(actual == expected, "GEO02_CONTEXT_INVENTORY_MISMATCH", "GEO-02 market inventory lineage mismatch")
    semantics = document.get("context_family_semantics", {})
    require(isinstance(semantics, Mapping) and semantics.get("tract_intersection", "").startswith("positive-area") and semantics.get("zero_area_tangency") == "excluded from membership" and semantics.get("geometric_jaccard", "").endswith("controlling Jaccard measure"), "GEO02_CONTEXT_SEMANTICS_MISMATCH", "GEO-02 spatial semantics mismatch")
    require(document.get("projected_context_space") == "EPSG:5070" and semantics.get("radius_parameter_owner") == "MODEL", "GEO02_CONTEXT_PARAMETER_OWNERSHIP_MISMATCH", "GEO-02 CRS or parameter owner mismatch")
    return str(document["content_sha256"])


def validate_membership_specification(document: Mapping[str, Any], context: Mapping[str, Any]) -> str:
    _self_hash(document)
    require(document.get("artifact_id") == MEMBERSHIP_SPEC_ID and document.get("version") == VERSION, "GEO03_MEMBERSHIP_VERSION_MISMATCH", "GEO-03 membership ID/version mismatch")
    transformation = document.get("transformation", {})
    operation = transformation.get("operation", {}) if isinstance(transformation, Mapping) else {}
    require(isinstance(operation, Mapping) and operation.get("source_crs") == "EPSG:4269" and operation.get("target_crs") == "EPSG:5070" and operation.get("logical_input_axis_order") == ["longitude", "latitude"], "GEO03_OPERATION_SEMANTICS_MISMATCH", "GEO-03 operation CRS or axis order mismatch")
    require(transformation.get("operation_fingerprint_sha256") == content_digest(operation), "GEO03_OPERATION_FINGERPRINT_MISMATCH", "GEO-03 operation fingerprint mismatch")
    boundary = document.get("boundary_and_radius_binding", {})
    require(isinstance(boundary, Mapping) and boundary.get("comparison") == "distance_m <= radius_m" and boundary.get("epsilon_or_snap_or_rounding_permitted") is False and boundary.get("owner") == "MODEL" and boundary.get("radii_m") == [4828.032, 8046.72, 11265.408], "GEO03_MEMBERSHIP_BOUNDARY_MISMATCH", "GEO-03 boundary or MODEL radius binding mismatch")
    distance = document.get("validation_membership_distance", {})
    require(isinstance(distance, Mapping) and distance.get("artifact_id") == DISTANCE_SPEC_ID and distance.get("unit") == "metre", "GEO03_DISTANCE_SEMANTICS_MISMATCH", "GEO-03 distance semantics mismatch")
    lineage = document.get("geo02_lineage", {})
    parent = lineage.get("subordinate_to_context_specification", {}) if isinstance(lineage, Mapping) else {}
    require(isinstance(parent, Mapping) and parent.get("artifact_id") == context.get("artifact_id") and parent.get("content_sha256") == context.get("content_sha256"), "GEO03_CONTEXT_LINEAGE_MISMATCH", "GEO-03 must be subordinate to GEO-02 context authority")
    require("membership_jaccard" not in json.dumps(document, sort_keys=True).lower(), "GEO03_COMPETING_JACCARD", "a second membership Jaccard is prohibited")
    return str(document["content_sha256"])


def materialize(source_zip: Path, repository_root: Path, output_root: Path) -> dict[str, Any]:
    """Create the five GEO-04 authority artifacts with exclusive writes."""
    config = json.loads((repository_root / "config/data/data01_validation_source_contract.json").read_text(encoding="utf-8"))
    tiger = json.loads((repository_root / "data/manifests/tiger_2024_wisconsin_tract.source_manifest.json").read_text(encoding="utf-8"))
    acs = json.loads((repository_root / "data/manifests/acs_2024_acs5_b11001_wisconsin_tract.source_manifest.json").read_text(encoding="utf-8"))
    validate_data02_contract(config, tiger, acs)
    rows = tiger_rows_from_pinned_zip(source_zip, tiger)
    derivation = derivation_document()
    inventories = {market: inventory_document(market, derive_ordered_geoids(rows, settings["county_allow_list"]), derivation) for market, settings in MARKETS.items()}
    context = context_specification_document(inventories, derivation)
    membership = membership_specification_document(context)
    artifacts = {
        "canonical_tract_inventory_derivation.json": derivation,
        "canonical_tract_inventory_milwaukee.json": inventories["milwaukee"],
        "canonical_tract_inventory_madison.json": inventories["madison"],
        "geo02_validation_context_spatial_spec.json": context,
        "geo03_internal_point_membership_spatial_spec.json": membership,
    }
    for filename, artifact in artifacts.items():
        write_json_exclusive(output_root / filename, artifact)
    return artifacts
