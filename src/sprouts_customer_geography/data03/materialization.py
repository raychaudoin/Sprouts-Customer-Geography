"""Fail-closed Wisconsin tract materialization for the DATA-03 source menu."""

from __future__ import annotations

from collections import Counter
import csv
from decimal import Decimal, InvalidOperation
import json
import math
from pathlib import Path
import re
from typing import Any, Iterable, Mapping

from sprouts_customer_geography.data03.contract import (
    EXPECTED_MEASURE_IDS,
    load_contract,
    load_source_manifests,
    validate_contract,
    validate_metadata_documents,
    validate_source_manifest,
)
from sprouts_customer_geography.geo04 import tiger_rows_from_pinned_zip
from sprouts_customer_geography.pipe01.canonical import content_digest, file_sha256, write_json_exclusive
from sprouts_customer_geography.pipe01.errors import require


STATUS_PRECEDENCE = {
    "valid": 0,
    "missing": 1,
    "special": 2,
    "inapplicable": 3,
    "suppressed": 4,
    "invalid": 5,
}


def _state_scope(contract: Mapping[str, Any], state_configuration: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Resolve state-specific extraction/output values without changing DATA-03 defaults."""
    configured = dict(state_configuration or {})
    geography = contract["geography"]
    state_fips = str(configured.get("state_fips", geography["state_fips"]))
    require(re.fullmatch(r"[0-9]{2}", state_fips) is not None, "DATA03_STATE_FIPS_INVALID", "state FIPS must contain two digits")
    state_name = str(configured.get("state_name", "Wisconsin" if state_fips == "55" else state_fips))
    state_slug = str(configured.get("state_slug", "wisconsin" if state_fips == "55" else state_name.lower().replace(" ", "_")))
    require(re.fullmatch(r"[a-z][a-z0-9_]*", state_slug) is not None, "DATA03_STATE_SLUG_INVALID", "state slug is invalid")
    prefix = str(configured.get("table_file_geo_id_prefix", geography["table_file_geo_id_prefix"]))
    require(prefix == f"1400000US{state_fips}", "DATA03_STATE_PREFIX_MISMATCH", "tract GEO_ID prefix differs from state FIPS")
    expected_count = int(configured.get("expected_tract_count", geography["expected_tract_count"]))
    require(expected_count > 0, "DATA03_STATE_TRACT_COUNT_INVALID", "state tract count must be positive")
    return {
        "state_fips": state_fips,
        "state_name": state_name,
        "state_slug": state_slug,
        "table_file_geo_id_prefix": prefix,
        "geoid_re": re.compile(rf"^1400000US({re.escape(state_fips)}[0-9]{{9}})$"),
        "tract_geoid_re": re.compile(rf"^{re.escape(state_fips)}[0-9]{{9}}$"),
        "expected_tract_count": expected_count,
        "normalized_filename": str(configured.get("normalized_filename", f"{state_slug}_tract_source_values.csv")),
        "candidate_filename": str(configured.get("candidate_filename", f"{state_slug}_tract_candidate_measures.csv")),
        "report_id": str(configured.get("report_id", "DATA03_WISCONSIN_MULTIVARIATE_ACS_MATERIALIZATION_REPORT_V1" if state_fips == "55" else f"DATA03_{state_fips}_MULTIVARIATE_ACS_MATERIALIZATION_REPORT_V1")),
    }


def _assert_generated_output(path: Path, repository_root: Path) -> Path:
    resolved = path.resolve()
    root = repository_root.resolve()
    try:
        relative = resolved.relative_to(root).as_posix()
    except ValueError:
        return resolved
    require(relative == "outputs" or relative.startswith("outputs/"), "DATA03_OUTPUT_PATH_NOT_IGNORED", "generated materialization output inside the repository must remain under ignored outputs")
    return resolved


def _format_number(value: int | float | None) -> str:
    if value is None:
        return ""
    if isinstance(value, int):
        return str(value)
    rendered = format(value, ".10f").rstrip("0").rstrip(".")
    return rendered if rendered not in {"", "-0"} else "0"


def _sentinel_map(contract: Mapping[str, Any]) -> dict[int, tuple[str, str]]:
    return {
        int(item["token"]): (str(item["status"]), str(item["meaning"]))
        for item in contract["special_value_contract"]["sentinels"]
    }


def _parse_scalar(
    raw_value: object,
    predicate_type: str,
    domain: str,
    role: str,
    sentinels: Mapping[int, tuple[str, str]],
) -> tuple[int | float | None, str, str]:
    raw = "" if raw_value is None else str(raw_value).strip()
    if not raw:
        return None, "missing", f"{role}_empty"
    try:
        decimal_value = Decimal(raw)
    except InvalidOperation:
        return None, "invalid", f"{role}_nonnumeric"
    if not decimal_value.is_finite():
        return None, "invalid", f"{role}_nonfinite"
    if decimal_value == decimal_value.to_integral_value():
        integer_value = int(decimal_value)
        if integer_value in sentinels:
            status, meaning = sentinels[integer_value]
            return None, status, f"{role}_{meaning.replace(' ', '_')}"
    if predicate_type == "int" and decimal_value != decimal_value.to_integral_value():
        return None, "invalid", f"{role}_noninteger"
    if decimal_value < 0:
        return None, "invalid", f"{role}_negative_unrecognized"
    if role == "estimate" and domain == "positive_average" and decimal_value <= 0:
        return None, "invalid", "estimate_nonpositive_average"
    value: int | float = int(decimal_value) if predicate_type == "int" else float(decimal_value)
    return value, "valid", f"{role}_published_{predicate_type}"


def parse_value_pair(raw_estimate: object, raw_moe: object, variable: Mapping[str, Any], contract: Mapping[str, Any]) -> dict[str, Any]:
    """Parse one estimate/MOE pair while preserving raw special evidence."""
    sentinels = _sentinel_map(contract)
    estimate, estimate_status, estimate_detail = _parse_scalar(raw_estimate, variable["predicate_type"], variable["domain"], "estimate", sentinels)
    moe, moe_status, moe_detail = _parse_scalar(raw_moe, variable["predicate_type"], variable["domain"], "moe", sentinels)
    status = max((estimate_status, moe_status), key=STATUS_PRECEDENCE.__getitem__)
    return {
        "estimate_raw": None if raw_estimate is None else str(raw_estimate),
        "moe_raw": None if raw_moe is None else str(raw_moe),
        "estimate": estimate,
        "moe": moe,
        "status": status,
        "status_detail": f"estimate={estimate_detail};moe={moe_detail}",
    }


def parse_table_file(
    source_file: Path,
    table: Mapping[str, Any],
    manifest: Mapping[str, Any],
    contract: Mapping[str, Any],
    enforce_contract_count: bool = True,
    state_configuration: Mapping[str, Any] | None = None,
) -> dict[str, dict[str, dict[str, Any]]]:
    """Verify and parse one exact table file into tract/component pairs."""
    table_id = table["table_id"]
    scope = _state_scope(contract, state_configuration)
    require(source_file.name == manifest.get("source_filename"), "DATA03_SOURCE_FILENAME_MISMATCH", f"local filename differs for {table_id}")
    require(source_file.is_file(), "DATA03_SOURCE_FILE_MISSING", f"source file is absent for {table_id}")
    require(source_file.stat().st_size == manifest.get("retrieval", {}).get("expected_byte_length"), "DATA03_SOURCE_LENGTH_MISMATCH", f"source length differs for {table_id}")
    require(file_sha256(source_file) == manifest.get("byte_sha256"), "DATA03_SOURCE_CHECKSUM_MISMATCH", f"source checksum differs for {table_id}")
    request = manifest["request_identity"]
    required_header = request["header_required"]
    by_geoid: dict[str, dict[str, dict[str, Any]]] = {}
    with source_file.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="|")
        require(reader.fieldnames is not None and set(required_header) <= set(reader.fieldnames), "DATA03_SOURCE_SCHEMA_CHANGED", f"required header differs for {table_id}")
        for source_row in reader:
            require(None not in source_row, "DATA03_SOURCE_ROW_MALFORMED", f"row has more fields than the header for {table_id}")
            geo_id = str(source_row.get("GEO_ID", ""))
            if not geo_id.startswith(scope["table_file_geo_id_prefix"]):
                continue
            match = scope["geoid_re"].fullmatch(geo_id)
            require(match is not None, "DATA03_TRACT_IDENTITY_INVALID", f"invalid {scope['state_name']} tract GEO_ID in {table_id}")
            geoid = match.group(1)
            require(geoid not in by_geoid, "DATA03_DUPLICATE_TRACT", f"duplicate tract {geoid} in {table_id}")
            components: dict[str, dict[str, Any]] = {}
            for variable in table["variables"]:
                component_id = variable["component_id"]
                components[component_id] = parse_value_pair(
                    source_row.get(variable["table_estimate_field"]),
                    source_row.get(variable["table_moe_field"]),
                    variable,
                    contract,
                )
            by_geoid[geoid] = components
    if enforce_contract_count:
        count_code = "DATA03_WISCONSIN_TRACT_COUNT_MISMATCH" if scope["state_fips"] == "55" else "DATA03_STATE_TRACT_COUNT_MISMATCH"
        require(len(by_geoid) == scope["expected_tract_count"], count_code, f"{scope['state_name']} tract count differs for {table_id}")
    return by_geoid


def derive_measure(measure: Mapping[str, Any], components: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    if measure["kind"] == "direct":
        source = components[measure["source_components"][0]]
        return {"estimate": source["estimate"], "moe": source["moe"], "status": source["status"], "status_detail": source["status_detail"]}

    required_components = [components[item] for item in measure["source_components"]]
    nonvalid = [item for item in required_components if item["status"] != "valid"]
    if nonvalid:
        worst = max(nonvalid, key=lambda item: STATUS_PRECEDENCE[item["status"]])
        return {"estimate": None, "moe": None, "status": worst["status"], "status_detail": "source_noncomputable"}

    numerator_items = [components[item] for item in measure["numerator_components"]]
    denominator_item = components[measure["denominator_component"]]
    numerator = sum(float(item["estimate"]) for item in numerator_items)
    numerator_moe = math.sqrt(sum(float(item["moe"]) ** 2 for item in numerator_items))
    denominator = float(denominator_item["estimate"])
    denominator_moe = float(denominator_item["moe"])
    if denominator <= 0:
        return {"estimate": None, "moe": None, "status": "invalid", "status_detail": "invalid_denominator"}
    if numerator < 0 or numerator > denominator:
        return {"estimate": None, "moe": None, "status": "invalid", "status_detail": "invalid_subset"}
    proportion = numerator / denominator
    radicand = numerator_moe ** 2 - proportion ** 2 * denominator_moe ** 2
    detail = "acs_subset_percentage"
    if radicand < 0:
        radicand = numerator_moe ** 2 + proportion ** 2 * denominator_moe ** 2
        detail = "acs_subset_percentage_conservative_fallback"
    estimate = 100.0 * proportion
    moe = 100.0 * math.sqrt(radicand) / denominator
    if not math.isfinite(estimate) or not math.isfinite(moe):
        return {"estimate": None, "moe": None, "status": "invalid", "status_detail": "nonfinite_derivation"}
    return {"estimate": estimate, "moe": moe, "status": "valid", "status_detail": detail}


def _write_csv(path: Path, columns: list[str], rows: Iterable[Mapping[str, Any]]) -> None:
    with path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n", extrasaction="raise")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})


def _status_counts(values: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    counts = Counter(str(value["status"]) for value in values)
    return dict(sorted(counts.items()))


def materialize_from_tables(
    contract: Mapping[str, Any],
    manifests: Mapping[str, Mapping[str, Any]],
    repository_root: Path,
    raw_dir: Path,
    expected_geoids: Iterable[str],
    output_dir: Path,
    *,
    enforce_contract_count: bool = True,
    validate_cached_metadata: bool = True,
    state_configuration: Mapping[str, Any] | None = None,
    allow_missing_source_rows: bool = False,
) -> dict[str, Any]:
    """Materialize verified source and candidate outputs against an explicit tract inventory."""
    validate_contract(contract)
    scope = _state_scope(contract, state_configuration)
    output_dir = _assert_generated_output(output_dir, repository_root)
    require(not output_dir.exists(), "DATA03_OUTPUT_OVERWRITE_DENIED", "materialization output already exists")
    ordered_geoids = list(expected_geoids)
    require(ordered_geoids == sorted(ordered_geoids) and len(ordered_geoids) == len(set(ordered_geoids)), "DATA03_TIGER_INVENTORY_INVALID", "expected GEOIDs must be unique and sorted")
    require(all(scope["tract_geoid_re"].fullmatch(geoid) for geoid in ordered_geoids), "DATA03_TIGER_INVENTORY_INVALID", f"expected GEOID is not a {scope['state_name']} tract")
    if enforce_contract_count:
        require(len(ordered_geoids) == scope["expected_tract_count"], "DATA03_TIGER_TRACT_COUNT_MISMATCH", "accepted TIGER tract count differs")

    if validate_cached_metadata:
        metadata_documents = {
            table["table_id"]: json.loads((raw_dir / f"{table['table_id'].lower()}.metadata.json").read_text(encoding="utf-8"))
            for table in contract["tables"]
        }
        metadata_sha = validate_metadata_documents(contract, metadata_documents)
    else:
        metadata_sha = contract["metadata_identity_sha256"]

    parsed_tables: dict[str, dict[str, dict[str, dict[str, Any]]]] = {}
    manifest_evidence: list[dict[str, Any]] = []
    source_row_reconciliation: dict[str, dict[str, Any]] = {}
    expected_set = set(ordered_geoids)
    for table in contract["tables"]:
        table_id = table["table_id"]
        manifest = manifests.get(table_id)
        require(isinstance(manifest, Mapping), "DATA03_MANIFEST_MISSING", f"manifest is absent for {table_id}")
        manifest_sha = validate_source_manifest(contract, table, manifest)
        parsed = parse_table_file(raw_dir / manifest["source_filename"], table, manifest, contract, enforce_contract_count=enforce_contract_count and not allow_missing_source_rows, state_configuration=scope)
        actual_set = set(parsed)
        missing_geoids = sorted(expected_set - actual_set)
        extra_geoids = sorted(actual_set - expected_set)
        require(not extra_geoids, "DATA03_COMPLETE_TRACT_COVERAGE_FAILED", f"{table_id} has {len(missing_geoids)} missing and {len(extra_geoids)} extra tract keys")
        require(allow_missing_source_rows or not missing_geoids, "DATA03_COMPLETE_TRACT_COVERAGE_FAILED", f"{table_id} has {len(missing_geoids)} missing and 0 extra tract keys")
        if missing_geoids:
            for geoid in missing_geoids:
                parsed[geoid] = {
                    variable["component_id"]: {
                        "estimate_raw": None,
                        "moe_raw": None,
                        "estimate": None,
                        "moe": None,
                        "status": "missing",
                        "status_detail": "source_row_missing",
                    }
                    for variable in table["variables"]
                }
        source_row_reconciliation[table_id] = {
            "expected_tract_count": len(expected_set),
            "present_source_row_count": len(actual_set),
            "missing_source_row_count": len(missing_geoids),
            "extra_source_row_count": len(extra_geoids),
            "missing_source_row_geoids": missing_geoids,
        }
        parsed_tables[table_id] = parsed
        manifest_evidence.append({
            "table_id": table_id,
            "manifest_id": manifest["manifest_id"],
            "manifest_content_sha256": manifest_sha,
            "source_byte_sha256": manifest["byte_sha256"],
            "source_byte_length": manifest["retrieval"]["expected_byte_length"],
        })

    normalized_rows: list[dict[str, Any]] = []
    components_by_geoid: dict[str, dict[str, Mapping[str, Any]]] = {geoid: {} for geoid in ordered_geoids}
    component_status: dict[str, list[Mapping[str, Any]]] = {}
    for table in contract["tables"]:
        table_id = table["table_id"]
        for variable in table["variables"]:
            component_id = variable["component_id"]
            component_status[component_id] = []
            for geoid in ordered_geoids:
                pair = parsed_tables[table_id][geoid][component_id]
                components_by_geoid[geoid][component_id] = pair
                component_status[component_id].append(pair)
                normalized_rows.append({
                    "tract_geoid": geoid,
                    "state_fips": geoid[:2],
                    "county_fips": geoid[2:5],
                    "tract_code": geoid[5:],
                    "table_id": table_id,
                    "component_id": component_id,
                    "estimate_variable_id": variable["estimate_variable"],
                    "moe_variable_id": variable["moe_variable"],
                    "estimate_raw": pair["estimate_raw"],
                    "moe_raw": pair["moe_raw"],
                    "estimate": _format_number(pair["estimate"]),
                    "moe": _format_number(pair["moe"]),
                    "status": pair["status"],
                    "status_detail": pair["status_detail"],
                })
    normalized_rows.sort(key=lambda row: (row["tract_geoid"], row["table_id"], row["component_id"]))

    wide_rows: list[dict[str, Any]] = []
    measure_status: dict[str, list[Mapping[str, Any]]] = {measure_id: [] for measure_id in EXPECTED_MEASURE_IDS}
    for geoid in ordered_geoids:
        wide: dict[str, Any] = {"tract_geoid": geoid, "state_fips": geoid[:2], "county_fips": geoid[2:5], "tract_code": geoid[5:]}
        for measure in contract["candidate_measures"]:
            measure_id = measure["measure_id"]
            result = derive_measure(measure, components_by_geoid[geoid])
            measure_status[measure_id].append(result)
            wide[f"{measure_id}_estimate"] = _format_number(result["estimate"])
            wide[f"{measure_id}_moe"] = _format_number(result["moe"])
            wide[f"{measure_id}_status"] = result["status"]
            wide[f"{measure_id}_status_detail"] = result["status_detail"]
        wide_rows.append(wide)

    output = contract["output_contract"]
    normalized_columns = list(output["normalized_source_columns"])
    wide_columns = list(output["wide_key_columns"])
    for measure_id in output["measure_order"]:
        wide_columns.extend(f"{measure_id}_{suffix}" for suffix in output["wide_measure_suffixes"])
    output_dir.mkdir(parents=True, exist_ok=False)
    normalized_path = output_dir / scope["normalized_filename"]
    wide_path = output_dir / scope["candidate_filename"]
    _write_csv(normalized_path, normalized_columns, normalized_rows)
    _write_csv(wide_path, wide_columns, wide_rows)

    component_coverage = {
        component_id: {"tract_count": len(values), "status_counts": _status_counts(values)}
        for component_id, values in sorted(component_status.items())
    }
    measure_coverage = {
        measure_id: {"tract_count": len(values), "status_counts": _status_counts(values)}
        for measure_id, values in measure_status.items()
    }
    report = {
        "report_id": scope["report_id"],
        "state": "VERIFIED",
        "contract_id": contract["artifact_id"],
        "contract_version": contract["version"],
        "contract_content_sha256": contract["content_sha256"],
        "source_release": contract["source_product"]["product"],
        "source_vintage": contract["source_product"]["vintage"],
        "state_fips": scope["state_fips"],
        "geography_level": contract["geography"]["level"],
        "tract_count": len(ordered_geoids),
        "ordered_tract_inventory_sha256": content_digest({"ordered_geoids": ordered_geoids}),
        "api_query_sha256": contract["api_query_sha256"],
        "metadata_identity_sha256": metadata_sha,
        "source_manifests": manifest_evidence,
        "component_coverage": component_coverage,
        "candidate_measure_coverage": measure_coverage,
        "normalized_output": {"filename": normalized_path.name, "columns": normalized_columns, "row_count": len(normalized_rows), "byte_sha256": file_sha256(normalized_path)},
        "candidate_output": {"filename": wide_path.name, "columns": wide_columns, "row_count": len(wide_rows), "byte_sha256": file_sha256(wide_path)},
        "missingness_policy": "preserved; no imputation or zero substitution",
        "candidate_authority_boundary": "source-safe candidate measures only; no final MODEL feature selection or scoring authority",
        "protected_characteristic_policy": "passed",
    }
    if allow_missing_source_rows:
        report["source_row_reconciliation"] = source_row_reconciliation
    report_path = output_dir / "verification_report.json"
    write_json_exclusive(report_path, report)
    ready = {
        "state": "READY",
        "report_filename": report_path.name,
        "report_sha256": file_sha256(report_path),
        "normalized_output_sha256": report["normalized_output"]["byte_sha256"],
        "candidate_output_sha256": report["candidate_output"]["byte_sha256"],
        "ready_marker_written_last": True,
    }
    write_json_exclusive(output_dir / "READY.json", ready)
    return report


def _statewide_tiger_geoids(tiger_rows: Iterable[Mapping[str, Any]], state_fips: str = "55") -> list[str]:
    geoids: list[str] = []
    for row in tiger_rows:
        state = str(row.get("STATEFP", ""))
        county = str(row.get("COUNTYFP", ""))
        tract = str(row.get("TRACTCE", ""))
        geoid = str(row.get("GEOID", ""))
        require(state == state_fips and re.fullmatch(r"[0-9]{3}", county) and re.fullmatch(r"[0-9]{6}", tract) and geoid == state + county + tract, "DATA03_TIGER_GEOID_INVALID", "TIGER tract identity is invalid")
        geoids.append(geoid)
    require(len(geoids) == len(set(geoids)), "DATA03_TIGER_DUPLICATE_TRACT", "TIGER contains a duplicate tract")
    return sorted(geoids)


def materialize_real(repository_root: Path, raw_dir: Path, output_dir: Path) -> dict[str, Any]:
    contract = load_contract(repository_root)
    manifests = load_source_manifests(repository_root, contract)
    tiger_manifest = json.loads((repository_root / contract["geography"]["tiger_manifest_path"]).read_text(encoding="utf-8"))
    tiger_zip = raw_dir / tiger_manifest["source_filename"]
    tiger_rows = tiger_rows_from_pinned_zip(tiger_zip, tiger_manifest)
    geoids = _statewide_tiger_geoids(tiger_rows)
    require(len(geoids) == contract["geography"]["expected_tract_count"], "DATA03_TIGER_TRACT_COUNT_MISMATCH", "TIGER statewide tract count differs")
    return materialize_from_tables(contract, manifests, repository_root, raw_dir, geoids, output_dir)


def compare_materializations(first: Path, second: Path, state_slug: str = "wisconsin") -> dict[str, str]:
    filenames = (f"{state_slug}_tract_source_values.csv", f"{state_slug}_tract_candidate_measures.csv", "verification_report.json", "READY.json")
    first_hashes = {filename: file_sha256(first / filename) for filename in filenames}
    second_hashes = {filename: file_sha256(second / filename) for filename in filenames}
    require(first_hashes == second_hashes, "DATA03_RERUN_NONDETERMINISTIC", "materialization outputs differ across reruns")
    return first_hashes
