"""Fail-closed validation for PBI-02 MODEL-13 and DATA-04 inputs."""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

from sprouts_customer_geography.pbi01.preflight import (
    Pbi01PreflightError,
    standard_local_paths as standard_model13_paths,
    validate_model13_inputs,
)


EXPECTED_DATA04_CONTRACT_ID = "DATA04_MICHIGAN_PUBLIC_DATA_PARITY_SOURCE_CONTRACT_V1"
EXPECTED_DATA04_CONTRACT_VERSION = "1.0.0"
EXPECTED_DATA04_CONTRACT_SHA256 = "4818c91e70d64119391aecf57f7306cd5dd2b3c0e174abb9fdfec6730676155d"
EXPECTED_DATA04_CANDIDATE_SHA256 = "adcc5ce6b08bb9973ccb5d76ac59162013d7db524e266d18585719581cca9198"
EXPECTED_TRACT_COUNT = 3_017
GEOID_RE = re.compile(r"^26[0-9]{9}$")
VALID_STATUSES = frozenset({"valid", "missing", "invalid", "inapplicable"})

MEASURE_IDS = (
    "median_household_income",
    "per_capita_income",
    "civilian_labor_force_share",
    "employment_rate",
    "bachelors_or_higher_share",
    "owner_occupancy_share",
    "vacancy_share",
    "median_home_value",
    "median_gross_rent",
    "average_household_size",
    "no_vehicle_household_share",
    "drive_alone_commuter_share",
    "work_from_home_commuter_share",
)
EXPECTED_CANDIDATE_COLUMNS = (
    "tract_geoid",
    "state_fips",
    "county_fips",
    "tract_code",
    *(
        field
        for measure_id in MEASURE_IDS
        for field in (
            f"{measure_id}_estimate",
            f"{measure_id}_moe",
            f"{measure_id}_status",
            f"{measure_id}_status_detail",
        )
    ),
)


class Pbi02PreflightError(ValueError):
    """Nondisclosing fail-closed PBI-02 input error."""


def _require(condition: bool, code: str, message: str) -> None:
    if not condition:
        raise Pbi02PreflightError(f"{code}: {message}")


def _load_json(path: Path, code: str) -> Mapping[str, Any]:
    _require(path.is_file(), code, "required local JSON artifact is absent")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise Pbi02PreflightError(f"{code}: required local JSON artifact is unreadable") from exc
    _require(isinstance(value, Mapping), code, "required local JSON artifact must be an object")
    return value


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_csv(path: Path, expected_columns: Sequence[str]) -> list[dict[str, str]]:
    _require(path.is_file(), "PBI02_DATA04_CANDIDATE_ABSENT", "accepted DATA-04 candidate CSV is absent")
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            _require(
                reader.fieldnames == list(expected_columns),
                "PBI02_DATA04_SCHEMA_MISMATCH",
                "DATA-04 candidate schema or ordered fields differ",
            )
            return list(reader)
    except (OSError, UnicodeError, csv.Error) as exc:
        raise Pbi02PreflightError("PBI02_DATA04_CANDIDATE_UNREADABLE: accepted DATA-04 candidate CSV is unreadable") from exc


def _finite_number(value: str) -> bool:
    try:
        return bool(value) and Decimal(value).is_finite()
    except InvalidOperation:
        return False


def _geometry_geoids(path: Path) -> list[str]:
    document = _load_json(path, "PBI02_GEOMETRY_INVALID")
    _require(document.get("type") == "FeatureCollection", "PBI02_GEOMETRY_INVALID", "presentation geometry must be a FeatureCollection")
    features = document.get("features")
    _require(isinstance(features, list), "PBI02_GEOMETRY_INVALID", "presentation geometry features are absent")
    geoids: list[str] = []
    for feature in features:
        properties = feature.get("properties") if isinstance(feature, Mapping) else None
        geoid = properties.get("GEOID") if isinstance(properties, Mapping) else None
        geometry = feature.get("geometry") if isinstance(feature, Mapping) else None
        _require(
            isinstance(geoid, str)
            and GEOID_RE.fullmatch(geoid) is not None
            and isinstance(geometry, Mapping)
            and geometry.get("type") in {"Polygon", "MultiPolygon"},
            "PBI02_GEOMETRY_INVALID",
            "presentation geometry feature or GEOID is malformed",
        )
        geoids.append(geoid)
    _require(len(geoids) == EXPECTED_TRACT_COUNT, "PBI02_GEOMETRY_COUNT_MISMATCH", "presentation geometry count differs")
    _require(len(set(geoids)) == EXPECTED_TRACT_COUNT, "PBI02_GEOMETRY_DUPLICATE_GEOID", "presentation geometry contains a duplicate GEOID")
    return sorted(geoids)


def standard_data04_paths(repository_root: Path) -> dict[str, Path]:
    base = repository_root / "powerbi" / "pbi01" / "local" / "data04"
    return {
        "root": base,
        "candidate": base / "multivariate" / "michigan_tract_candidate_measures.csv",
        "report": base / "verification_report.json",
        "ready": base / "READY.json",
    }


def discover_data04_root(repository_root: Path) -> Path:
    """Resolve an exact accepted ignored DATA-04 package by byte identity."""
    root = repository_root.resolve()
    candidates = [standard_data04_paths(root)["root"]]
    outputs = root / "outputs"
    if outputs.is_dir():
        candidates.extend(sorted((path for path in outputs.glob("data04-run-*") if path.is_dir()), reverse=True))
    for candidate_root in candidates:
        candidate = candidate_root / "multivariate" / "michigan_tract_candidate_measures.csv"
        ready = candidate_root / "READY.json"
        if candidate.is_file() and ready.is_file() and _file_sha256(candidate) == EXPECTED_DATA04_CANDIDATE_SHA256:
            return candidate_root
    raise Pbi02PreflightError(
        "PBI02_DATA04_PACKAGE_UNRESOLVED: exact accepted DATA-04 package is absent; reconstruct it with accepted DATA-04 tooling"
    )


def _data04_paths(data04_root: Path) -> dict[str, Path]:
    return {
        "root": data04_root,
        "candidate": data04_root / "multivariate" / "michigan_tract_candidate_measures.csv",
        "report": data04_root / "verification_report.json",
        "ready": data04_root / "READY.json",
    }


@dataclass(frozen=True)
class Pbi02PreflightResult:
    state: str
    model13_ready: bool
    data04_contract_identity_verified: bool
    data04_ready_last_verified: bool
    data04_candidate_hash_verified: bool
    data04_schema_verified: bool
    data04_status_semantics_verified: bool
    tract_count: int
    public_context_unique_geoid_count: int
    geometry_unique_geoid_count: int
    model13_unique_geoid_count: int
    one_to_one_relationship_eligible: bool
    no_missing_to_zero_mutation: bool

    def disclosure_safe_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_pbi02_inputs(
    repository_root: Path,
    *,
    model13_paths: Mapping[str, Path] | None = None,
    data04_root: Path | None = None,
    geometry_path: Path | None = None,
    expected_candidate_sha256: str = EXPECTED_DATA04_CANDIDATE_SHA256,
) -> Pbi02PreflightResult:
    """Validate exact MODEL-13, DATA-04, and public geometry without exposing rows or paths."""
    root = repository_root.resolve()
    geometry = geometry_path or root / "powerbi" / "pbi01" / "presentation" / "michigan_2024_tracts.geojson"
    resolved_model13_paths = dict(model13_paths or standard_model13_paths(root))
    try:
        model13 = validate_model13_inputs(
            root,
            local_paths=resolved_model13_paths,
            geometry_path=geometry,
        )
    except Pbi01PreflightError as exc:
        raise Pbi02PreflightError(str(exc).replace("PBI01_", "PBI02_MODEL13_", 1)) from exc

    contract = _load_json(
        root / "config" / "data" / "data04_michigan_public_data_parity_source_contract.json",
        "PBI02_DATA04_CONTRACT_UNRESOLVED",
    )
    _require(
        contract.get("artifact_id") == EXPECTED_DATA04_CONTRACT_ID
        and contract.get("version") == EXPECTED_DATA04_CONTRACT_VERSION
        and contract.get("status") == "active"
        and contract.get("content_sha256") == EXPECTED_DATA04_CONTRACT_SHA256,
        "PBI02_DATA04_CONTRACT_IDENTITY_MISMATCH",
        "accepted DATA-04 contract identity, version, status, or content hash differs",
    )
    _require(
        contract.get("state_scope", {}).get("observed_tract_count") == EXPECTED_TRACT_COUNT
        and contract.get("multivariate_extraction", {}).get("accepted_candidate_measure_count") == len(MEASURE_IDS),
        "PBI02_DATA04_CONTRACT_ACCOUNTING_MISMATCH",
        "accepted DATA-04 tract or measure accounting differs",
    )

    resolved_data04_root = data04_root or discover_data04_root(root)
    paths = _data04_paths(resolved_data04_root.resolve())
    report = _load_json(paths["report"], "PBI02_DATA04_REPORT_UNRESOLVED")
    ready = _load_json(paths["ready"], "PBI02_DATA04_READY_UNRESOLVED")
    _require(
        report.get("state") == "VERIFIED"
        and report.get("contract_id") == EXPECTED_DATA04_CONTRACT_ID
        and report.get("contract_version") == EXPECTED_DATA04_CONTRACT_VERSION
        and report.get("contract_content_sha256") == EXPECTED_DATA04_CONTRACT_SHA256,
        "PBI02_DATA04_REPORT_IDENTITY_MISMATCH",
        "DATA-04 verification report does not bind exact accepted authority",
    )
    expected_ready_keys = {
        "household_output_sha256",
        "multivariate_candidate_output_sha256",
        "multivariate_normalized_output_sha256",
        "ready_marker_written_last",
        "report_filename",
        "report_sha256",
        "state",
        "tiger_output_sha256",
    }
    _require(set(ready) == expected_ready_keys, "PBI02_DATA04_READY_SCHEMA_MISMATCH", "DATA-04 READY marker fields differ")
    _require(
        ready.get("state") == "READY"
        and ready.get("ready_marker_written_last") is True
        and ready.get("report_filename") == "verification_report.json",
        "PBI02_DATA04_NOT_READY",
        "DATA-04 package is not finalized READY-last",
    )
    _require(
        _file_sha256(paths["report"]) == ready.get("report_sha256"),
        "PBI02_DATA04_REPORT_HASH_MISMATCH",
        "DATA-04 report does not match READY",
    )

    candidate_meta = report.get("multivariate_evidence", {}).get("candidate_output", {})
    _require(
        candidate_meta.get("filename") == "michigan_tract_candidate_measures.csv"
        and candidate_meta.get("row_count") == EXPECTED_TRACT_COUNT
        and candidate_meta.get("columns") == list(EXPECTED_CANDIDATE_COLUMNS),
        "PBI02_DATA04_REPORT_SCHEMA_MISMATCH",
        "DATA-04 report candidate identity or ordered schema differs",
    )
    candidate_hash = _file_sha256(paths["candidate"])
    _require(
        candidate_hash
        == expected_candidate_sha256
        == candidate_meta.get("byte_sha256")
        == ready.get("multivariate_candidate_output_sha256"),
        "PBI02_DATA04_CANDIDATE_HASH_MISMATCH",
        "DATA-04 candidate bytes do not match exact accepted identity",
    )

    rows = _read_csv(paths["candidate"], EXPECTED_CANDIDATE_COLUMNS)
    _require(len(rows) == EXPECTED_TRACT_COUNT, "PBI02_DATA04_ROW_COUNT_MISMATCH", "DATA-04 candidate row count differs")
    geoids = [row["tract_geoid"] for row in rows]
    _require(all(GEOID_RE.fullmatch(value) is not None for value in geoids), "PBI02_DATA04_GEOID_INVALID", "DATA-04 candidate GEOID is malformed")
    _require(geoids == sorted(geoids), "PBI02_DATA04_GEOID_ORDER_MISMATCH", "DATA-04 candidate GEOIDs are not in accepted order")
    _require(len(set(geoids)) == EXPECTED_TRACT_COUNT, "PBI02_DATA04_DUPLICATE_GEOID", "DATA-04 candidate contains a duplicate GEOID")
    _require(
        all(
            row["state_fips"] == "26"
            and row["tract_geoid"] == row["state_fips"] + row["county_fips"] + row["tract_code"]
            for row in rows
        ),
        "PBI02_DATA04_KEY_COMPONENT_MISMATCH",
        "DATA-04 key components do not reconcile",
    )

    for row in rows:
        for measure_id in MEASURE_IDS:
            status = row[f"{measure_id}_status"]
            estimate = row[f"{measure_id}_estimate"]
            moe = row[f"{measure_id}_moe"]
            detail = row[f"{measure_id}_status_detail"]
            _require(status in VALID_STATUSES, "PBI02_DATA04_STATUS_INVALID", "DATA-04 status token differs from accepted semantics")
            _require(bool(detail), "PBI02_DATA04_STATUS_DETAIL_ABSENT", "DATA-04 status detail is absent")
            if status == "valid":
                _require(
                    _finite_number(estimate) and _finite_number(moe),
                    "PBI02_DATA04_VALID_VALUE_INVALID",
                    "DATA-04 valid estimate or MOE is not finite numeric evidence",
                )

    geometry_geoids = _geometry_geoids(geometry)
    with resolved_model13_paths["tract"].open("r", encoding="utf-8", newline="") as handle:
        model13_geoids = [row["geoid"] for row in csv.DictReader(handle)]
    _require(
        geoids == model13_geoids == geometry_geoids,
        "PBI02_TRACT_RECONCILIATION_MISMATCH",
        "DATA-04, MODEL-13, and presentation geometry GEOID inventories differ",
    )

    return Pbi02PreflightResult(
        state="READY",
        model13_ready=model13.state == "READY",
        data04_contract_identity_verified=True,
        data04_ready_last_verified=True,
        data04_candidate_hash_verified=True,
        data04_schema_verified=True,
        data04_status_semantics_verified=True,
        tract_count=len(rows),
        public_context_unique_geoid_count=len(set(geoids)),
        geometry_unique_geoid_count=len(set(geometry_geoids)),
        model13_unique_geoid_count=len(set(model13_geoids)),
        one_to_one_relationship_eligible=True,
        no_missing_to_zero_mutation=True,
    )
