"""Fail-closed resolution and validation of accepted APP-01 local inputs."""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import re
from typing import Any, Iterable, Mapping, Sequence

from sprouts_customer_geography.data04.contract import load_authority
from sprouts_customer_geography.model13.resolver import load_authorized_registry
from sprouts_customer_geography.pbi01.preflight import (
    Pbi01PreflightError,
    Pbi01PreflightResult,
    validate_model13_inputs,
)
from sprouts_customer_geography.pipe01.errors import ConformanceError

from .errors import App01Error, require


EXPECTED_TRACT_COUNT = 3_017
EXPECTED_COMPUTABLE_COUNT = 2_973
EXPECTED_NONCOMPUTABLE_COUNT = 44
EXPECTED_SUPPORT_TRUNCATION_COUNT = 438
EXPECTED_GEOMETRY_SHA256 = "e0f32095d2e2307f5ad78c9545fc0d3c74fca2250bc866bea8db2368848786ad"
EXPECTED_DATA04_CANDIDATE_SHA256 = "adcc5ce6b08bb9973ccb5d76ac59162013d7db524e266d18585719581cca9198"
EXPECTED_MODEL13_CONTRACT_ID = "MODEL13_MICHIGAN_POWER_BI_OUTPUT_CONTRACT_V1"
EXPECTED_DATA04_CONTRACT_ID = "DATA04_MICHIGAN_PUBLIC_DATA_PARITY_SOURCE_CONTRACT_V1"
GEOID_RE = re.compile(r"^26[0-9]{9}$")
SETTINGS_KEYS = {"model13_candidates", "model13_registry", "data04_candidates"}
MODEL13_RUN_RE = re.compile(r"^m13run-[A-Za-z0-9_-]+$")
MODEL13_RUN_PACKAGE_ID = "MODEL13_PROTECTED_EXECUTION_RUN_V1"
MODEL13_STAGE_ORDER = ["benchmark", "feature_freeze", "transition", "development", "statewide"]
DATA04_STATUSES = {"valid", "missing", "special", "inapplicable", "suppressed", "invalid"}


def file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_object(path: Path, code: str) -> Mapping[str, Any]:
    require(path.is_file(), code, "required local JSON input is absent")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise App01Error(code, "required local JSON input is unreadable") from exc
    require(isinstance(value, Mapping), code, "required local JSON input must be an object")
    return value


def _strict_bool(value: str, code: str) -> bool:
    require(value in {"True", "False"}, code, "boolean input contains an unexpected token")
    return value == "True"


def _optional_number(value: str, code: str) -> float | None:
    if value == "":
        return None
    try:
        parsed = float(value)
    except ValueError as exc:
        raise App01Error(code, "numeric input contains an unexpected token") from exc
    require(math.isfinite(parsed), code, "numeric input must be finite")
    return parsed


def _unique_resolved(paths: Iterable[Path]) -> tuple[Path, ...]:
    by_key: dict[str, Path] = {}
    for path in paths:
        resolved = path.expanduser().resolve()
        by_key.setdefault(str(resolved).casefold(), resolved)
    return tuple(by_key[key] for key in sorted(by_key))


def _configured_paths(repository_root: Path, values: object, code: str) -> tuple[Path, ...]:
    require(isinstance(values, list), code, "local settings candidate list must be an array")
    paths: list[Path] = []
    for value in values:
        require(isinstance(value, str) and bool(value.strip()), code, "local settings candidates must be non-empty strings")
        candidate = Path(value)
        paths.append(candidate if candidate.is_absolute() else repository_root / candidate)
    return _unique_resolved(paths)


def _configured_path(repository_root: Path, value: object, code: str) -> Path | None:
    if value is None:
        return None
    require(isinstance(value, str) and bool(value.strip()), code, "local settings path must be a non-empty string")
    candidate = Path(value)
    return (candidate if candidate.is_absolute() else repository_root / candidate).expanduser().resolve()


def _registry_model_candidates(repository_root: Path, registry_path: Path) -> tuple[Path, ...]:
    """Resolve READY presentation packages only within one accepted MODEL-13 output root."""
    try:
        resolver = load_authorized_registry(registry_path, repository_root)
        request = resolver.execution_request
        output_root = resolver.resolve(str(request["model13_output_root_handle"]), "model13_output_root").path
    except (ConformanceError, KeyError, TypeError) as exc:
        raise App01Error("APP01_MODEL13_REGISTRY_INVALID", "the configured MODEL-13 protected registry did not resolve accepted authority") from exc

    runs_root = output_root / "model13-runs"
    require(runs_root.is_dir(), "APP01_MODEL13_REGISTRY_NO_RUNS", "the accepted MODEL-13 output root contains no execution runs")
    try:
        run_directories = sorted(
            (path for path in runs_root.iterdir() if path.is_dir() and MODEL13_RUN_RE.fullmatch(path.name)),
            key=lambda path: path.name,
        )
    except OSError as exc:
        raise App01Error("APP01_MODEL13_REGISTRY_UNREADABLE", "the accepted MODEL-13 run registry is unreadable") from exc

    observed_presentations = 0
    candidates: list[Path] = []
    for run_dir in run_directories:
        presentation = run_dir / "presentation"
        if not presentation.is_dir():
            continue
        observed_presentations += 1
        try:
            ready = _json_object(run_dir / "READY.json", "APP01_MODEL13_RUN_READY_INVALID")
            manifest = _json_object(run_dir / "run_manifest.json", "APP01_MODEL13_RUN_READY_INVALID")
            valid = (
                ready.get("run_id") == run_dir.name
                and ready.get("package_id") == MODEL13_RUN_PACKAGE_ID
                and ready.get("version") == "1.0.0"
                and ready.get("state") == "ready"
                and ready.get("finalization_state") == "complete"
                and ready.get("stage_order") == MODEL13_STAGE_ORDER
                and ready.get("ready_marker_written_last") is True
                and manifest.get("run_id") == run_dir.name
                and manifest.get("package_id") == MODEL13_RUN_PACKAGE_ID
                and manifest.get("version") == "1.0.0"
                and manifest.get("state") == "ready"
                and manifest.get("finalization_state") == "complete"
            )
            require(valid, "APP01_MODEL13_RUN_READY_INVALID", "one MODEL-13 presentation candidate is not bound to a complete READY run")
        except App01Error:
            continue
        candidates.append(presentation)

    require(observed_presentations > 0, "APP01_MODEL13_REGISTRY_NO_PRESENTATION", "the accepted MODEL-13 output root contains no presentation package")
    require(candidates, "APP01_MODEL13_REGISTRY_NO_READY_RUN", "no MODEL-13 presentation package is bound to a complete READY run")
    return tuple(candidates)


@dataclass(frozen=True)
class LocalSettings:
    model13_candidates: tuple[Path, ...]
    data04_candidates: tuple[Path, ...]
    settings_loaded: bool
    model13_registry_loaded: bool


def load_local_settings(repository_root: Path, settings_path: Path | None = None) -> LocalSettings:
    """Resolve ignored local settings plus accepted repository-relative defaults."""
    root = repository_root.resolve()
    default_model13 = root / "powerbi" / "pbi01" / "local" / "model13"
    path = settings_path or root / "presentation" / "app01" / "local" / "settings.json"
    configured_model: tuple[Path, ...] = ()
    configured_data: tuple[Path, ...] = ()
    registry_path: Path | None = None
    loaded = False
    if path.exists():
        document = _json_object(path, "APP01_SETTINGS_INVALID")
        require(set(document) <= SETTINGS_KEYS, "APP01_SETTINGS_INVALID", "local settings contain an unsupported field")
        configured_model = _configured_paths(root, document.get("model13_candidates", []), "APP01_SETTINGS_INVALID")
        configured_data = _configured_paths(root, document.get("data04_candidates", []), "APP01_SETTINGS_INVALID")
        registry_path = _configured_path(root, document.get("model13_registry"), "APP01_SETTINGS_INVALID")
        loaded = True
    elif settings_path is not None:
        raise App01Error("APP01_SETTINGS_ABSENT", "the requested local settings file is absent")

    if registry_path is None and os.environ.get("MODEL13_AUTHORITY_REGISTRY"):
        registry_path = Path(os.environ["MODEL13_AUTHORITY_REGISTRY"]).expanduser().resolve()
    registry_model = _registry_model_candidates(root, registry_path) if registry_path is not None else ()

    discovered_data: list[Path] = []
    outputs = root / "outputs"
    if outputs.is_dir():
        for candidate_file in outputs.rglob("michigan_tract_candidate_measures.csv"):
            if candidate_file.parent.name == "multivariate":
                discovered_data.append(candidate_file.parent.parent)

    return LocalSettings(
        model13_candidates=_unique_resolved((default_model13, *configured_model, *registry_model)),
        data04_candidates=_unique_resolved((*configured_data, *discovered_data)),
        settings_loaded=loaded,
        model13_registry_loaded=registry_path is not None,
    )


@dataclass(frozen=True)
class AcceptedGeometry:
    canonical_bytes: bytes
    geoids: tuple[str, ...]


def load_accepted_geometry(repository_root: Path) -> AcceptedGeometry:
    path = repository_root / "powerbi" / "pbi01" / "presentation" / "michigan_2024_tracts.geojson"
    require(path.is_file(), "APP01_GEOMETRY_ABSENT", "accepted Michigan presentation geometry is absent")
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise App01Error("APP01_GEOMETRY_INVALID", "accepted Michigan presentation geometry is unreadable") from exc
    canonical = raw.replace(b"\r\n", b"\n")
    require(sha256(canonical).hexdigest() == EXPECTED_GEOMETRY_SHA256, "APP01_GEOMETRY_HASH_MISMATCH", "accepted Michigan presentation geometry bytes differ")
    try:
        document = json.loads(canonical)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise App01Error("APP01_GEOMETRY_INVALID", "accepted Michigan presentation geometry is unreadable") from exc
    require(isinstance(document, Mapping) and document.get("type") == "FeatureCollection", "APP01_GEOMETRY_INVALID", "accepted presentation geometry must be a GeoJSON FeatureCollection")
    features = document.get("features")
    require(isinstance(features, list), "APP01_GEOMETRY_INVALID", "accepted presentation geometry features are absent")
    geoids: list[str] = []
    for feature in features:
        require(isinstance(feature, Mapping) and feature.get("type") == "Feature", "APP01_GEOMETRY_INVALID", "presentation geometry contains a malformed feature")
        properties = feature.get("properties")
        geometry = feature.get("geometry")
        geoid = properties.get("GEOID") if isinstance(properties, Mapping) else None
        require(isinstance(geoid, str) and GEOID_RE.fullmatch(geoid) is not None, "APP01_GEOMETRY_GEOID_INVALID", "presentation geometry contains a malformed GEOID")
        require(isinstance(geometry, Mapping) and geometry.get("type") in {"Polygon", "MultiPolygon"}, "APP01_GEOMETRY_INVALID", "presentation geometry must contain polygonal features")
        geoids.append(geoid)
    require(len(geoids) == EXPECTED_TRACT_COUNT, "APP01_GEOMETRY_COUNT_MISMATCH", "presentation geometry tract count differs from accepted accounting")
    require(len(set(geoids)) == EXPECTED_TRACT_COUNT, "APP01_GEOMETRY_DUPLICATE_GEOID", "presentation geometry contains a duplicate GEOID")
    return AcceptedGeometry(canonical_bytes=canonical, geoids=tuple(sorted(geoids)))


def _model_candidate_paths(root: Path) -> dict[str, Path]:
    nested = {
        "tract": root / "tract" / "model13_michigan_tract_scores.csv",
        "seed": root / "seed-context" / "model13_michigan_seed_context.csv",
        "metadata": root / "metadata" / "model13_michigan_power_bi_metadata.json",
        "ready": root / "metadata" / "READY.json",
    }
    if any(path.exists() for path in nested.values()):
        return nested
    return {
        "tract": root / "model13_michigan_tract_scores.csv",
        "seed": root / "model13_michigan_seed_context.csv",
        "metadata": root / "model13_michigan_power_bi_metadata.json",
        "ready": root / "READY.json",
    }


def _read_csv(path: Path, expected_columns: Sequence[str], code: str) -> list[dict[str, str]]:
    require(path.is_file(), code, "required local CSV input is absent")
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            require(reader.fieldnames == list(expected_columns), code, "local CSV schema differs from accepted authority")
            return list(reader)
    except (OSError, UnicodeError, csv.Error) as exc:
        raise App01Error(code, "required local CSV input is unreadable") from exc


@dataclass(frozen=True)
class ResolvedModel13:
    tract_rows: tuple[Mapping[str, str], ...]
    seed_rows: tuple[Mapping[str, str], ...]
    preflight: Pbi01PreflightResult
    candidate_count: int
    rejected_candidate_count: int

    def disclosure_safe_dict(self) -> dict[str, Any]:
        return {
            **asdict(self.preflight),
            "candidate_count": self.candidate_count,
            "rejected_candidate_count": self.rejected_candidate_count,
        }


def resolve_model13(
    repository_root: Path,
    geometry: AcceptedGeometry,
    candidates: Sequence[Path],
) -> ResolvedModel13:
    contract = _json_object(
        repository_root / "config" / "model" / "model13_michigan_power_bi_output_contract.json",
        "APP01_MODEL13_CONTRACT_INVALID",
    )
    require(contract.get("artifact_id") == EXPECTED_MODEL13_CONTRACT_ID and contract.get("version") == "1.0.0", "APP01_MODEL13_CONTRACT_INVALID", "accepted MODEL-13 presentation contract identity differs")
    valid: list[tuple[Path, dict[str, Path], Pbi01PreflightResult, tuple[str, ...]]] = []
    rejected = 0
    observed = 0
    for candidate in _unique_resolved(candidates):
        paths = _model_candidate_paths(candidate)
        if not any(path.exists() for path in paths.values()):
            continue
        observed += 1
        try:
            result = validate_model13_inputs(repository_root, local_paths=paths)
            metadata = _json_object(paths["metadata"], "APP01_MODEL13_METADATA_INVALID")
            ready = _json_object(paths["ready"], "APP01_MODEL13_READY_INVALID")
            signature = (
                str(metadata["model_lineage_id"]),
                str(metadata["public_lineage_id"]),
                str(ready["tract_csv_sha256"]),
                str(ready["seed_context_csv_sha256"]),
                str(ready["metadata_file_sha256"]),
            )
            valid.append((candidate, paths, result, signature))
        except (Pbi01PreflightError, App01Error, KeyError, TypeError):
            rejected += 1
    require(observed > 0, "APP01_MODEL13_PACKAGE_ABSENT", "accepted local MODEL-13 presentation inputs were not found")
    require(valid, "APP01_MODEL13_NO_VALID_PACKAGE", "no local MODEL-13 candidate satisfied accepted readiness and lineage authority")
    signatures = {item[3] for item in valid}
    require(len(signatures) == 1, "APP01_MODEL13_CANDIDATES_DISAGREE", "multiple valid MODEL-13 candidates disagree in authoritative contents")
    selected = sorted(valid, key=lambda item: str(item[0]).casefold())[0]
    paths = selected[1]
    tract_rows = _read_csv(paths["tract"], contract["tract_output"]["columns"], "APP01_MODEL13_TRACT_INVALID")
    seed_rows = _read_csv(paths["seed"], contract["seed_context_output"]["columns"], "APP01_MODEL13_SEED_INVALID")

    for row in tract_rows:
        require(GEOID_RE.fullmatch(row["geoid"]) is not None, "APP01_MODEL13_TRACT_INVALID", "MODEL-13 tract GEOID is malformed")
        for field in ("household_opportunity", "customer_fit_statewide_percentile", "modeled_target_mass_statewide_percentile"):
            _optional_number(row[field], "APP01_MODEL13_TRACT_INVALID")
        _strict_bool(row["support_truncation_5mi"], "APP01_MODEL13_TRACT_INVALID")
        _strict_bool(row["any_support_truncation"], "APP01_MODEL13_TRACT_INVALID")
    require(tuple(row["geoid"] for row in tract_rows) == geometry.geoids, "APP01_MODEL13_GEOMETRY_RECONCILIATION_MISMATCH", "MODEL-13 and public geometry keys do not reconcile exactly")

    numeric_seed_fields = (
        "latitude", "longitude", "mean_isolated_sales", "frozen_model12_prediction",
        "successor_oof_prediction", "successor_oof_absolute_log_error", "household_opportunity",
        "customer_fit_proxy", "modeled_target_mass",
    )
    for row in seed_rows:
        require(bool(row["protected_physical_location_id"]) and bool(row["qa_status"]), "APP01_MODEL13_SEED_INVALID", "Seed Context identity or QA is absent")
        parsed = {field: _optional_number(row[field], "APP01_MODEL13_SEED_INVALID") for field in numeric_seed_fields}
        require(all(value is not None for value in parsed.values()), "APP01_MODEL13_SEED_INVALID", "Seed Context numeric presentation field is unavailable")
        require(-90 <= parsed["latitude"] <= 90 and -180 <= parsed["longitude"] <= 180, "APP01_MODEL13_SEED_INVALID", "Seed Context coordinate is invalid")
        _strict_bool(row["support_truncation"], "APP01_MODEL13_SEED_INVALID")

    return ResolvedModel13(
        tract_rows=tuple(tract_rows),
        seed_rows=tuple(seed_rows),
        preflight=selected[2],
        candidate_count=len(valid),
        rejected_candidate_count=rejected,
    )


@dataclass(frozen=True)
class ResolvedData04:
    rows: tuple[Mapping[str, str], ...]
    measure_ids: tuple[str, ...]
    candidate_count: int
    rejected_candidate_count: int

    def disclosure_safe_dict(self) -> dict[str, Any]:
        return {
            "state": "READY",
            "contract_identity_verified": True,
            "candidate_hash_verified": True,
            "schema_verified": True,
            "tract_count": len(self.rows),
            "unique_geoid_count": len({row["tract_geoid"] for row in self.rows}),
            "measure_count": len(self.measure_ids),
            "candidate_count": self.candidate_count,
            "rejected_candidate_count": self.rejected_candidate_count,
        }


def _expected_data04_columns(data03_contract: Mapping[str, Any]) -> tuple[str, ...]:
    output = data03_contract["output_contract"]
    columns = list(output["wide_key_columns"])
    for measure_id in output["measure_order"]:
        columns.extend(f"{measure_id}_{suffix}" for suffix in output["wide_measure_suffixes"])
    return tuple(columns)


def _validate_data04_candidate(
    root: Path,
    expected_columns: Sequence[str],
    measure_ids: Sequence[str],
    geometry: AcceptedGeometry,
) -> tuple[list[dict[str, str]], tuple[str, ...]]:
    candidate_path = root / "multivariate" / "michigan_tract_candidate_measures.csv"
    require(candidate_path.is_file(), "APP01_DATA04_CANDIDATE_ABSENT", "DATA-04 candidate materialization is absent")
    require(file_sha256(candidate_path) == EXPECTED_DATA04_CANDIDATE_SHA256, "APP01_DATA04_HASH_MISMATCH", "DATA-04 candidate materialization bytes differ from accepted authority")
    ready = _json_object(root / "READY.json", "APP01_DATA04_READY_INVALID")
    report = _json_object(root / "verification_report.json", "APP01_DATA04_REPORT_INVALID")
    subready = _json_object(root / "multivariate" / "READY.json", "APP01_DATA04_READY_INVALID")
    subreport = _json_object(root / "multivariate" / "verification_report.json", "APP01_DATA04_REPORT_INVALID")
    require(ready.get("state") == "READY" and ready.get("ready_marker_written_last") is True, "APP01_DATA04_READY_INVALID", "DATA-04 package is not READY-last")
    require(ready.get("multivariate_candidate_output_sha256") == EXPECTED_DATA04_CANDIDATE_SHA256, "APP01_DATA04_HASH_MISMATCH", "DATA-04 READY marker does not bind accepted candidate bytes")
    require(report.get("state") == "VERIFIED" and report.get("contract_id") == EXPECTED_DATA04_CONTRACT_ID and report.get("contract_version") == "1.0.0", "APP01_DATA04_REPORT_INVALID", "DATA-04 verification report identity differs")
    require(report.get("tract_count") == EXPECTED_TRACT_COUNT, "APP01_DATA04_COUNT_MISMATCH", "DATA-04 verification report tract count differs")
    require(subready.get("state") == "READY" and subready.get("ready_marker_written_last") is True and subready.get("candidate_output_sha256") == EXPECTED_DATA04_CANDIDATE_SHA256, "APP01_DATA04_READY_INVALID", "DATA-04 multivariate READY marker differs")
    require(subreport.get("state") == "VERIFIED" and subreport.get("tract_count") == EXPECTED_TRACT_COUNT, "APP01_DATA04_REPORT_INVALID", "DATA-04 multivariate report differs")
    rows = _read_csv(candidate_path, expected_columns, "APP01_DATA04_SCHEMA_DRIFT")
    require(len(rows) == EXPECTED_TRACT_COUNT, "APP01_DATA04_COUNT_MISMATCH", "DATA-04 candidate row count differs")
    geoids = [row["tract_geoid"] for row in rows]
    require(all(GEOID_RE.fullmatch(value) is not None for value in geoids), "APP01_DATA04_GEOID_INVALID", "DATA-04 candidate GEOID is malformed")
    require(geoids == sorted(geoids), "APP01_DATA04_ORDER_MISMATCH", "DATA-04 candidate GEOIDs are not in accepted order")
    require(len(set(geoids)) == EXPECTED_TRACT_COUNT, "APP01_DATA04_DUPLICATE_GEOID", "DATA-04 candidate contains a duplicate GEOID")
    require(tuple(geoids) == geometry.geoids, "APP01_DATA04_GEOMETRY_RECONCILIATION_MISMATCH", "DATA-04 and public geometry keys do not reconcile exactly")
    for row in rows:
        geoid = row["tract_geoid"]
        require(row["state_fips"] == geoid[:2] and row["county_fips"] == geoid[2:5] and row["tract_code"] == geoid[5:], "APP01_DATA04_GEOID_INVALID", "DATA-04 key components do not reconcile")
        for measure_id in measure_ids:
            estimate = _optional_number(row[f"{measure_id}_estimate"], "APP01_DATA04_VALUE_INVALID")
            moe = _optional_number(row[f"{measure_id}_moe"], "APP01_DATA04_VALUE_INVALID")
            status = row[f"{measure_id}_status"]
            detail = row[f"{measure_id}_status_detail"]
            require(status in DATA04_STATUSES and bool(detail), "APP01_DATA04_STATUS_INVALID", "DATA-04 measure status or status detail differs from accepted semantics")
            require(status != "valid" or (estimate is not None and moe is not None), "APP01_DATA04_MISSINGNESS_INVALID", "a valid DATA-04 measure lacks its estimate or margin of error")
            require(not (estimate is None and moe is not None), "APP01_DATA04_MISSINGNESS_INVALID", "DATA-04 contains an uncertainty value without an estimate")
            require(moe is None or moe >= 0, "APP01_DATA04_VALUE_INVALID", "DATA-04 margin of error is invalid")
    signature = (EXPECTED_DATA04_CONTRACT_ID, EXPECTED_DATA04_CANDIDATE_SHA256)
    return rows, signature


def resolve_data04(
    repository_root: Path,
    geometry: AcceptedGeometry,
    candidates: Sequence[Path],
) -> ResolvedData04:
    try:
        authority = load_authority(repository_root)
    except Exception as exc:  # Existing authority emits repository-safe conformance errors.
        raise App01Error("APP01_DATA04_CONTRACT_INVALID", "accepted DATA-04 authority could not be verified") from exc
    contract = authority.contract
    require(contract.get("artifact_id") == EXPECTED_DATA04_CONTRACT_ID and contract.get("version") == "1.0.0", "APP01_DATA04_CONTRACT_INVALID", "accepted DATA-04 contract identity differs")
    expected_columns = _expected_data04_columns(authority.data03_contract)
    measure_ids = tuple(authority.data03_contract["output_contract"]["measure_order"])
    valid: list[tuple[Path, list[dict[str, str]], tuple[str, ...]]] = []
    rejected = 0
    observed = 0
    for candidate in _unique_resolved(candidates):
        expected_file = candidate / "multivariate" / "michigan_tract_candidate_measures.csv"
        if not expected_file.exists():
            continue
        observed += 1
        try:
            rows, signature = _validate_data04_candidate(candidate, expected_columns, measure_ids, geometry)
            valid.append((candidate, rows, signature))
        except App01Error:
            rejected += 1
    require(observed > 0, "APP01_DATA04_PACKAGE_ABSENT", "accepted local DATA-04 materialization was not found")
    require(valid, "APP01_DATA04_NO_VALID_PACKAGE", "no local DATA-04 candidate satisfied accepted readiness and byte authority")
    signatures = {item[2] for item in valid}
    require(len(signatures) == 1, "APP01_DATA04_CANDIDATES_DISAGREE", "multiple valid DATA-04 candidates disagree in authoritative contents")
    selected = sorted(valid, key=lambda item: str(item[0]).casefold())[0]
    return ResolvedData04(
        rows=tuple(selected[1]),
        measure_ids=measure_ids,
        candidate_count=len(valid),
        rejected_candidate_count=rejected,
    )
