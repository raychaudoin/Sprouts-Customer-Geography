"""Fail-closed statewide Michigan public-data materialization for DATA-04."""

from __future__ import annotations

from collections import Counter
import csv
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping
from zipfile import ZipFile

from sprouts_customer_geography.data03.materialization import materialize_from_tables
from sprouts_customer_geography.geo04 import tiger_rows_from_source_zip
from sprouts_customer_geography.pipe01.canonical import content_digest, file_sha256, write_json_exclusive
from sprouts_customer_geography.pipe01.errors import require
from sprouts_customer_geography.pipe01.production import (
    _read_shapefile_polygons,
    load_statewide_acs_b11001_evidence,
)
from sprouts_customer_geography.pipe01.spatial import parse_internal_point

from .contract import Data04Authority, EXPECTED_TRACT_COUNT, load_authority


HOUSEHOLD_COLUMNS = [
    "tract_geoid",
    "state_fips",
    "county_fips",
    "tract_code",
    "estimate_variable_id",
    "moe_variable_id",
    "estimate_raw",
    "moe_raw",
    "estimate",
    "moe",
    "annotation",
    "status",
    "status_detail",
    "source_manifest_id",
]
TIGER_COLUMNS = [
    "tract_geoid",
    "state_fips",
    "county_fips",
    "tract_code",
    "intptlat_raw",
    "intptlon_raw",
    "intptlat",
    "intptlon",
    "internal_point_status",
    "geometry_record_status",
    "source_crs",
    "source_manifest_id",
]


def _assert_output_path(path: Path, repository_root: Path) -> Path:
    resolved = path.resolve()
    root = repository_root.resolve()
    try:
        relative = resolved.relative_to(root).as_posix()
    except ValueError:
        return resolved
    require(relative == "outputs" or relative.startswith("outputs/"), "DATA04_OUTPUT_PATH_NOT_IGNORED", "generated output inside the repository must remain under ignored outputs")
    return resolved


def _format_number(value: int | float | None) -> str:
    if value is None:
        return ""
    if isinstance(value, int):
        return str(value)
    rendered = format(value, ".10f").rstrip("0").rstrip(".")
    return rendered if rendered not in {"", "-0"} else "0"


def _write_csv(path: Path, columns: list[str], rows: Iterable[Mapping[str, Any]]) -> None:
    with path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n", extrasaction="raise")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})


def _status_counts(values: Iterable[str]) -> dict[str, int]:
    return dict(sorted(Counter(values).items()))


def load_tiger_evidence(source_zip: Path, authority: Data04Authority) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Verify Michigan TIGER attributes, geometry, CRS, internal points, and key identity."""
    manifest = authority.tiger_manifest
    rows = tiger_rows_from_source_zip(source_zip, manifest, "26")
    stem = manifest["source_filename"].removesuffix(".zip")
    properties = manifest["expected_file_properties"]
    with ZipFile(source_zip) as archive:
        prj_bytes = archive.read(f"{stem}.prj")
        dbf_bytes = archive.read(f"{stem}.dbf")
        shp_bytes = archive.read(f"{stem}.shp")
        shx_bytes = archive.read(f"{stem}.shx")
        geometries = _read_shapefile_polygons(shp_bytes)
    require(file_sha256_bytes(prj_bytes) == properties["projection_member_sha256"], "DATA04_TIGER_MEMBER_CHECKSUM_MISMATCH", "TIGER projection member checksum differs")
    require(file_sha256_bytes(dbf_bytes) == properties["dbf_member_sha256"], "DATA04_TIGER_MEMBER_CHECKSUM_MISMATCH", "TIGER DBF member checksum differs")
    require(file_sha256_bytes(shp_bytes) == properties["shapefile_member_sha256"], "DATA04_TIGER_MEMBER_CHECKSUM_MISMATCH", "TIGER shapefile member checksum differs")
    require(file_sha256_bytes(shx_bytes) == properties["shapefile_index_member_sha256"], "DATA04_TIGER_MEMBER_CHECKSUM_MISMATCH", "TIGER shapefile index checksum differs")
    require(len(rows) == len(geometries) == EXPECTED_TRACT_COUNT, "DATA04_TIGER_ATTRIBUTE_GEOMETRY_COUNT_MISMATCH", "Michigan TIGER attribute and geometry counts differ")
    projection = prj_bytes.decode("ascii")
    require("GCS_North_American_1983" in projection and "D_North_American_1983" in projection and "GRS_1980" in projection, "DATA04_TIGER_CRS_MISMATCH", "Michigan TIGER projection metadata is not NAD83/EPSG:4269")

    evidence: list[dict[str, Any]] = []
    observed: set[str] = set()
    for row, geometry in zip(rows, geometries):
        state = str(row.get("STATEFP", ""))
        county = str(row.get("COUNTYFP", ""))
        tract = str(row.get("TRACTCE", ""))
        geoid = str(row.get("GEOID", ""))
        require(state == "26" and re.fullmatch(r"[0-9]{3}", county) is not None and re.fullmatch(r"[0-9]{6}", tract) is not None, "DATA04_TIGER_GEOID_INVALID", "Michigan TIGER GEOID components are invalid")
        require(geoid == state + county + tract and re.fullmatch(r"26[0-9]{9}", geoid) is not None, "DATA04_TIGER_GEOID_INVALID", "Michigan TIGER GEOID does not equal its components")
        require(geoid not in observed, "DATA04_TIGER_DUPLICATE_GEOID", "Michigan TIGER contains a duplicate GEOID")
        observed.add(geoid)
        point = parse_internal_point(row.get("INTPTLAT"), row.get("INTPTLON"))
        require(geometry.is_valid and not geometry.is_empty and geometry.area > 0, "DATA04_TIGER_GEOMETRY_INVALID", "Michigan TIGER geometry is invalid")
        evidence.append({
            "tract_geoid": geoid,
            "state_fips": state,
            "county_fips": county,
            "tract_code": tract,
            "intptlat_raw": point.raw_latitude,
            "intptlon_raw": point.raw_longitude,
            "intptlat": _format_number(point.latitude),
            "intptlon": _format_number(point.longitude),
            "internal_point_status": point.coordinate_state,
            "geometry_record_status": "valid",
            "source_crs": "EPSG:4269",
            "source_manifest_id": manifest["manifest_id"],
        })
    evidence.sort(key=lambda row: row["tract_geoid"])
    require(len(evidence) == EXPECTED_TRACT_COUNT, "DATA04_TIGER_TRACT_COUNT_MISMATCH", "Michigan TIGER tract count differs")
    summary = {
        "source_filename": source_zip.name,
        "source_byte_length": source_zip.stat().st_size,
        "source_byte_sha256": file_sha256(source_zip),
        "tract_count": len(evidence),
        "unique_geoid_count": len(observed),
        "geometry_record_count": len(geometries),
        "geometry_status_counts": _status_counts(row["geometry_record_status"] for row in evidence),
        "internal_point_status_counts": _status_counts(row["internal_point_status"] for row in evidence),
        "source_crs": "EPSG:4269",
        "projection_member_sha256": properties["projection_member_sha256"],
    }
    return evidence, summary


def file_sha256_bytes(value: bytes) -> str:
    import hashlib

    return hashlib.sha256(value).hexdigest()


def _household_rows(
    evidence: Mapping[str, Mapping[str, Any]],
    ordered_geoids: list[str],
    manifest_id: str,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for geoid in ordered_geoids:
        value = evidence[geoid]
        output.append({
            "tract_geoid": geoid,
            "state_fips": geoid[:2],
            "county_fips": geoid[2:5],
            "tract_code": geoid[5:],
            "estimate_variable_id": "B11001_001E",
            "moe_variable_id": "B11001_001M",
            "estimate_raw": value["raw_estimate"],
            "moe_raw": value["raw_moe"],
            "estimate": _format_number(value["estimate"]),
            "moe": _format_number(value["moe"]),
            "annotation": "" if value["annotation"] is None else value["annotation"],
            "status": value["status"],
            "status_detail": json.dumps(value["status_detail"], sort_keys=True, separators=(",", ":")),
            "source_manifest_id": manifest_id,
        })
    return output


def _require_expected_source_row_reconciliation(
    actual: Mapping[str, Mapping[str, Any]],
    expected: Mapping[str, Mapping[str, Any]],
) -> None:
    """Require real fixed-byte table coverage to match the pinned aggregate authority."""
    require(tuple(actual) == tuple(expected), "DATA04_SOURCE_ROW_RECONCILIATION_MISMATCH", "multivariate table reconciliation identity or order differs")
    for table_id, expected_counts in expected.items():
        actual_counts = actual[table_id]
        observed = {
            "expected_tract_count": actual_counts["expected_tract_count"],
            "present_source_row_count": actual_counts["present_source_row_count"],
            "missing_source_row_count": actual_counts["missing_source_row_count"],
            "extra_source_row_count": actual_counts["extra_source_row_count"],
        }
        require(observed == expected_counts, "DATA04_SOURCE_ROW_RECONCILIATION_MISMATCH", f"source-row coverage differs for {table_id}")


def materialize_real(
    repository_root: Path,
    acs_raw_dir: Path,
    household_source: Path,
    tiger_source: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Create an immutable statewide Michigan public-source package and READY marker."""
    authority = load_authority(repository_root)
    contract = authority.contract
    output_dir = _assert_output_path(output_dir, repository_root)
    require(not output_dir.exists(), "DATA04_OUTPUT_OVERWRITE_DENIED", "DATA-04 materialization output already exists")

    tiger_rows, tiger_summary = load_tiger_evidence(tiger_source, authority)
    ordered_geoids = [row["tract_geoid"] for row in tiger_rows]
    ordered_set = set(ordered_geoids)
    household_evidence, household_lineage = load_statewide_acs_b11001_evidence(household_source, authority.household_manifest, "26", EXPECTED_TRACT_COUNT)
    household_set = set(household_evidence)
    require(household_set == ordered_set, "DATA04_B11001_TRACT_RECONCILIATION_FAILED", f"B11001 has {len(ordered_set - household_set)} missing and {len(household_set - ordered_set)} extra Michigan tract rows")

    state_configuration = {
        "state_name": "Michigan",
        "state_slug": "michigan",
        "state_fips": "26",
        "table_file_geo_id_prefix": "1400000US26",
        "expected_tract_count": EXPECTED_TRACT_COUNT,
        "normalized_filename": contract["output_contract"]["multivariate_normalized_filename"],
        "candidate_filename": contract["output_contract"]["multivariate_candidate_filename"],
        "report_id": "DATA04_MICHIGAN_MULTIVARIATE_ACS_SUBREPORT_V1",
    }
    multivariate_dir = output_dir / contract["output_contract"]["multivariate_directory"]
    multivariate_report = materialize_from_tables(
        authority.data03_contract,
        authority.multivariate_manifests,
        repository_root,
        acs_raw_dir,
        ordered_geoids,
        multivariate_dir,
        state_configuration=state_configuration,
        allow_missing_source_rows=True,
    )
    require(multivariate_report["tract_count"] == EXPECTED_TRACT_COUNT, "DATA04_MULTIVARIATE_TRACT_RECONCILIATION_FAILED", "multivariate tract count differs")

    household_rows = _household_rows(household_evidence, ordered_geoids, authority.household_manifest["manifest_id"])
    household_path = output_dir / contract["output_contract"]["household_filename"]
    tiger_path = output_dir / contract["output_contract"]["tiger_filename"]
    _write_csv(household_path, HOUSEHOLD_COLUMNS, household_rows)
    _write_csv(tiger_path, TIGER_COLUMNS, tiger_rows)

    household_status = _status_counts(row["status"] for row in household_rows)
    internal_point_ready = tiger_summary["internal_point_status_counts"] == {"valid": EXPECTED_TRACT_COUNT}
    geometry_ready = tiger_summary["geometry_status_counts"] == {"valid": EXPECTED_TRACT_COUNT}
    measure_ids = list(multivariate_report["candidate_measure_coverage"])
    model_public_ready = len(measure_ids) == 13 and multivariate_report["tract_count"] == EXPECTED_TRACT_COUNT
    source_row_reconciliation = multivariate_report["source_row_reconciliation"]
    _require_expected_source_row_reconciliation(
        source_row_reconciliation,
        contract["multivariate_extraction"]["expected_source_row_reconciliation"],
    )
    report = {
        "report_id": "DATA04_MICHIGAN_PUBLIC_DATA_PARITY_MATERIALIZATION_REPORT_V1",
        "state": "VERIFIED",
        "contract_id": contract["artifact_id"],
        "contract_version": contract["version"],
        "contract_content_sha256": contract["content_sha256"],
        "state_name": "Michigan",
        "state_fips": "26",
        "geography_level": "tract",
        "tract_count": EXPECTED_TRACT_COUNT,
        "ordered_tract_inventory_sha256": content_digest({"ordered_geoids": ordered_geoids}),
        "source_products": {"acs": "2020-2024 ACS 5-Year Detailed Tables", "tiger": "2024 TIGER/Line Census Tracts"},
        "household_evidence": {
            "extraction_id": contract["household_extraction"]["extraction_id"],
            "source_lineage": household_lineage,
            "row_count": len(household_rows),
            "status_counts": household_status,
            "output": {"filename": household_path.name, "columns": HOUSEHOLD_COLUMNS, "byte_sha256": file_sha256(household_path)},
        },
        "multivariate_evidence": {
            "extraction_id": contract["multivariate_extraction"]["extraction_id"],
            "data03_contract_id": authority.data03_contract["artifact_id"],
            "data03_contract_content_sha256": authority.data03_contract["content_sha256"],
            "table_count": 11,
            "component_pair_count": 22,
            "candidate_measure_count": 13,
            "candidate_measure_ids": measure_ids,
            "component_coverage": multivariate_report["component_coverage"],
            "candidate_measure_coverage": multivariate_report["candidate_measure_coverage"],
            "subreport_sha256": file_sha256(multivariate_dir / "verification_report.json"),
            "normalized_output": multivariate_report["normalized_output"],
            "candidate_output": multivariate_report["candidate_output"],
        },
        "tiger_evidence": {
            "manifest_id": authority.tiger_manifest["manifest_id"],
            "manifest_content_sha256": authority.tiger_manifest["manifest_content_sha256"],
            **tiger_summary,
            "output": {"filename": tiger_path.name, "columns": TIGER_COLUMNS, "byte_sha256": file_sha256(tiger_path)},
        },
        "tract_reconciliation": {
            "tiger_key_count": len(ordered_set),
            "b11001_missing_source_rows": 0,
            "b11001_extra_source_rows": 0,
            "multivariate_table_missing_source_rows": {table_id: value["missing_source_row_count"] for table_id, value in source_row_reconciliation.items()},
            "multivariate_table_extra_source_rows": {table_id: value["extra_source_row_count"] for table_id, value in source_row_reconciliation.items()},
            "multivariate_missing_source_row_geoids": {table_id: value["missing_source_row_geoids"] for table_id, value in source_row_reconciliation.items() if value["missing_source_row_count"]},
            "all_required_output_keys_retained": True,
            "present_noncomputable_values_retained": True,
            "row_dropping": False,
        },
        "downstream_geo_source_readiness": {
            "tiger_manifest_available": True,
            "complete_statewide_key_set": True,
            "source_geometry_available": geometry_ready,
            "internal_points_available_and_parseable": internal_point_ready,
            "source_crs": "EPSG:4269",
            "target_crs_authority_unchanged": "EPSG:5070",
            "source_vintage": "2024",
            "authoritative_michigan_market_inventory_created": False,
        },
        "downstream_model11_public_source_readiness": {
            "b11001_available": len(household_rows) == EXPECTED_TRACT_COUNT,
            "all_data03_components_available": len(multivariate_report["component_coverage"]) == 22,
            "all_data03_measures_available": model_public_ready,
            "all_required_public_source_families_available": model_public_ready and len(household_rows) == EXPECTED_TRACT_COUNT,
            "model_execution_performed": False,
        },
        "missingness_policy": "Raw tokens, parsed values, and explicit statuses are preserved; no imputation, zero substitution, or tract deletion.",
        "protected_characteristic_policy": "DATA-03 exclusion preserved and passed.",
        "protected_evidence_access": {"sprouts_or_protected_evidence_accessed": False, "public_census_data_only": True},
    }
    report_path = output_dir / contract["output_contract"]["verification_report_filename"]
    write_json_exclusive(report_path, report)
    ready = {
        "state": "READY",
        "report_filename": report_path.name,
        "report_sha256": file_sha256(report_path),
        "household_output_sha256": report["household_evidence"]["output"]["byte_sha256"],
        "tiger_output_sha256": report["tiger_evidence"]["output"]["byte_sha256"],
        "multivariate_normalized_output_sha256": multivariate_report["normalized_output"]["byte_sha256"],
        "multivariate_candidate_output_sha256": multivariate_report["candidate_output"]["byte_sha256"],
        "ready_marker_written_last": True,
    }
    write_json_exclusive(output_dir / contract["output_contract"]["ready_filename"], ready)
    return report


def compare_materializations(first: Path, second: Path, comparison_output: Path | None = None) -> dict[str, Any]:
    """Require identical relative files and bytes across two independent immutable runs."""
    require((first / "READY.json").is_file() and (second / "READY.json").is_file(), "DATA04_RUN_NOT_READY", "both DATA-04 runs must be READY")
    first_files = sorted(path.relative_to(first).as_posix() for path in first.rglob("*") if path.is_file())
    second_files = sorted(path.relative_to(second).as_posix() for path in second.rglob("*") if path.is_file())
    require(first_files == second_files, "DATA04_RERUN_FILESET_MISMATCH", "materialization file sets differ")
    first_hashes = {name: file_sha256(first / name) for name in first_files}
    second_hashes = {name: file_sha256(second / name) for name in second_files}
    require(first_hashes == second_hashes, "DATA04_RERUN_NONDETERMINISTIC", "materialization bytes differ across independent runs")
    report = {
        "report_id": "DATA04_MICHIGAN_DETERMINISTIC_MATERIALIZATION_COMPARISON_V1",
        "state": "DETERMINISTIC_BYTE_IDENTICAL",
        "file_count": len(first_files),
        "file_sha256": first_hashes,
    }
    if comparison_output is not None:
        require(not comparison_output.exists(), "DATA04_COMPARISON_OVERWRITE_DENIED", "comparison output already exists")
        write_json_exclusive(comparison_output, report)
    return report
