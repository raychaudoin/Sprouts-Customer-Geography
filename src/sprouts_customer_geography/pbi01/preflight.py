"""Fail-closed validation for protected-local MODEL-13 presentation inputs."""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any, Mapping, Sequence


EXPECTED_CONTRACT_ID = "MODEL13_MICHIGAN_POWER_BI_OUTPUT_CONTRACT_V1"
EXPECTED_METADATA_ID = "MODEL13_MICHIGAN_POWER_BI_METADATA_V1"
EXPECTED_TRACT_COUNT = 3_017
EXPECTED_COMPUTABLE_COUNT = 2_973
EXPECTED_NONCOMPUTABLE_COUNT = 44
EXPECTED_SUPPORT_TRUNCATION_COUNT = 438
COMPUTABLE_STATUS = "MODEL_SCORE_COMPUTABLE"
GEOID_RE = re.compile(r"^26[0-9]{9}$")


class Pbi01PreflightError(ValueError):
    """Nondisclosing fail-closed PBI-01 input error."""


def _require(condition: bool, code: str, message: str) -> None:
    if not condition:
        raise Pbi01PreflightError(f"{code}: {message}")


def _load_json(path: Path, code: str) -> Mapping[str, Any]:
    _require(path.is_file(), code, "required local JSON artifact is absent")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise Pbi01PreflightError(f"{code}: required local JSON artifact is unreadable") from exc
    _require(isinstance(value, Mapping), code, "required local JSON artifact must be an object")
    return value


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_csv(path: Path, expected_columns: Sequence[str], code: str) -> list[dict[str, str]]:
    _require(path.is_file(), code, "required local CSV artifact is absent")
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            _require(reader.fieldnames == list(expected_columns), code, "CSV schema differs from the accepted contract")
            rows = list(reader)
    except (OSError, UnicodeError, csv.Error) as exc:
        raise Pbi01PreflightError(f"{code}: required local CSV artifact is unreadable") from exc
    return rows


def _strict_bool(value: str, code: str) -> bool:
    _require(value in {"True", "False"}, code, "boolean field contains an unexpected token")
    return value == "True"


def _extract_geometry_geoids(path: Path) -> set[str]:
    document = _load_json(path, "PBI01_GEOMETRY_INVALID")
    _require(document.get("type") == "FeatureCollection", "PBI01_GEOMETRY_INVALID", "presentation geometry must be GeoJSON FeatureCollection")
    features = document.get("features")
    _require(isinstance(features, list), "PBI01_GEOMETRY_INVALID", "presentation geometry features are absent")
    geoids: list[str] = []
    for feature in features:
        _require(isinstance(feature, Mapping) and feature.get("type") == "Feature", "PBI01_GEOMETRY_INVALID", "presentation geometry feature is malformed")
        properties = feature.get("properties")
        geoid = properties.get("GEOID") if isinstance(properties, Mapping) else None
        _require(isinstance(geoid, str) and GEOID_RE.fullmatch(geoid) is not None, "PBI01_GEOMETRY_GEOID_INVALID", "presentation geometry GEOID is malformed")
        geometry = feature.get("geometry")
        _require(isinstance(geometry, Mapping) and geometry.get("type") in {"Polygon", "MultiPolygon"}, "PBI01_GEOMETRY_INVALID", "presentation geometry is not polygonal")
        geoids.append(geoid)
    _require(len(geoids) == len(set(geoids)), "PBI01_GEOMETRY_DUPLICATE_GEOID", "presentation geometry contains a duplicate GEOID")
    return set(geoids)


@dataclass(frozen=True)
class Pbi01PreflightResult:
    state: str
    contract_identity_verified: bool
    metadata_ready_verified: bool
    metadata_bound_hashes_verified: bool
    lineage_verified: bool
    tract_schema_verified: bool
    tract_count: int
    computable_count: int
    noncomputable_count: int
    support_truncation_count: int
    seed_schema_verified: bool
    seed_context_ready: bool
    geometry_reconciled: bool
    geometry_geoid_count: int

    def disclosure_safe_dict(self) -> dict[str, Any]:
        return asdict(self)


def standard_local_paths(repository_root: Path) -> dict[str, Path]:
    base = repository_root / "powerbi" / "pbi01" / "local" / "model13"
    return {
        "tract": base / "tract" / "model13_michigan_tract_scores.csv",
        "seed": base / "seed-context" / "model13_michigan_seed_context.csv",
        "metadata": base / "metadata" / "model13_michigan_power_bi_metadata.json",
        "ready": base / "metadata" / "READY.json",
    }


def validate_model13_inputs(
    repository_root: Path,
    *,
    local_paths: Mapping[str, Path] | None = None,
    geometry_path: Path | None = None,
) -> Pbi01PreflightResult:
    """Validate the three protected MODEL-13 inputs without disclosing rows or paths."""
    root = repository_root.resolve()
    paths = dict(local_paths or standard_local_paths(root))
    _require(set(paths) == {"tract", "seed", "metadata", "ready"}, "PBI01_LOCAL_PATH_SET_INVALID", "local input path set differs")

    contract = _load_json(root / "config" / "model" / "model13_michigan_power_bi_output_contract.json", "PBI01_CONTRACT_UNRESOLVED")
    _require(contract.get("artifact_id") == EXPECTED_CONTRACT_ID and contract.get("version") == "1.0.0", "PBI01_CONTRACT_IDENTITY_MISMATCH", "accepted MODEL-13 presentation contract identity differs")
    _require(contract.get("protected_local_only") is True, "PBI01_CONTRACT_BOUNDARY_MISMATCH", "accepted presentation inputs are not marked protected-local")
    _require(contract.get("tract_output", {}).get("row_count") == EXPECTED_TRACT_COUNT, "PBI01_CONTRACT_ACCOUNTING_MISMATCH", "accepted tract accounting differs")
    _require(
        paths["tract"].name == contract.get("tract_output", {}).get("filename")
        and paths["seed"].name == contract.get("seed_context_output", {}).get("filename")
        and paths["metadata"].name == contract.get("metadata_output", {}).get("filename")
        and paths["ready"].name == "READY.json",
        "PBI01_LOCAL_FILENAME_MISMATCH",
        "local input filenames differ from the accepted contract convention",
    )

    metadata = _load_json(paths["metadata"], "PBI01_METADATA_UNRESOLVED")
    expected_metadata_keys = {
        "metadata_id", "version", "state", "output_contract_id", "model_lineage_id",
        "public_lineage_id", "tract_output", "seed_context_output", "ready_written_last",
    }
    _require(set(metadata) == expected_metadata_keys, "PBI01_METADATA_SCHEMA_DRIFT", "metadata fields differ from the accepted MODEL-13 output")
    _require(metadata.get("metadata_id") == EXPECTED_METADATA_ID and metadata.get("version") == "1.0.0", "PBI01_METADATA_IDENTITY_MISMATCH", "MODEL-13 metadata identity differs")
    _require(metadata.get("state") == "ready" and metadata.get("ready_written_last") is True, "PBI01_METADATA_NOT_READY", "MODEL-13 metadata is not READY")
    _require(metadata.get("output_contract_id") == EXPECTED_CONTRACT_ID, "PBI01_METADATA_CONTRACT_MISMATCH", "metadata does not bind the accepted output contract")
    model_lineage = metadata.get("model_lineage_id")
    public_lineage = metadata.get("public_lineage_id")
    _require(isinstance(model_lineage, str) and model_lineage and isinstance(public_lineage, str) and public_lineage, "PBI01_METADATA_LINEAGE_INVALID", "metadata lineage is absent")

    tract_meta = metadata.get("tract_output")
    seed_meta = metadata.get("seed_context_output")
    _require(isinstance(tract_meta, Mapping) and set(tract_meta) == {"filename", "row_count", "computable_count", "noncomputable_count", "support_truncation_count", "byte_sha256"}, "PBI01_METADATA_SCHEMA_DRIFT", "tract metadata fields differ")
    _require(isinstance(seed_meta, Mapping) and set(seed_meta) == {"filename", "row_count", "fitting_eligible_count", "fitting_excluded_count", "byte_sha256"}, "PBI01_METADATA_SCHEMA_DRIFT", "seed metadata fields differ")
    _require(tract_meta.get("filename") == contract["tract_output"]["filename"] and seed_meta.get("filename") == contract["seed_context_output"]["filename"], "PBI01_FILENAME_MISMATCH", "protected input filename differs from the accepted contract")

    ready = _load_json(paths["ready"], "PBI01_READY_MARKER_UNRESOLVED")
    _require(set(ready) == {"state", "finalization_state", "metadata_file_sha256", "tract_csv_sha256", "seed_context_csv_sha256", "ready_marker_written_last"}, "PBI01_READY_MARKER_SCHEMA_DRIFT", "READY marker fields differ")
    _require(ready.get("state") == "ready" and ready.get("finalization_state") == "complete" and ready.get("ready_marker_written_last") is True, "PBI01_READY_MARKER_INVALID", "presentation READY marker is incomplete")

    tract_hash = _file_sha256(paths["tract"])
    seed_hash = _file_sha256(paths["seed"])
    metadata_hash = _file_sha256(paths["metadata"])
    _require(tract_hash == tract_meta.get("byte_sha256") == ready.get("tract_csv_sha256"), "PBI01_TRACT_HASH_MISMATCH", "tract input does not match metadata-bound bytes")
    _require(seed_hash == seed_meta.get("byte_sha256") == ready.get("seed_context_csv_sha256"), "PBI01_SEED_HASH_MISMATCH", "seed input does not match metadata-bound bytes")
    _require(metadata_hash == ready.get("metadata_file_sha256"), "PBI01_METADATA_HASH_MISMATCH", "metadata does not match the READY marker")

    tract_rows = _read_csv(paths["tract"], contract["tract_output"]["columns"], "PBI01_TRACT_INPUT_INVALID")
    _require(len(tract_rows) == EXPECTED_TRACT_COUNT == tract_meta.get("row_count"), "PBI01_TRACT_COUNT_MISMATCH", "tract row count differs from accepted accounting")
    geoids = [row["geoid"] for row in tract_rows]
    _require(all(GEOID_RE.fullmatch(value) is not None for value in geoids), "PBI01_TRACT_GEOID_INVALID", "tract GEOID is malformed")
    _require(geoids == sorted(geoids), "PBI01_TRACT_ORDER_MISMATCH", "tract GEOIDs are not in accepted order")
    _require(len(set(geoids)) == EXPECTED_TRACT_COUNT, "PBI01_TRACT_DUPLICATE_GEOID", "tract input contains a duplicate GEOID")
    computable = sum(row["computability_status"] == COMPUTABLE_STATUS for row in tract_rows)
    noncomputable = len(tract_rows) - computable
    truncated = sum(_strict_bool(row["any_support_truncation"], "PBI01_TRACT_BOOLEAN_INVALID") for row in tract_rows)
    _require((computable, noncomputable, truncated) == (EXPECTED_COMPUTABLE_COUNT, EXPECTED_NONCOMPUTABLE_COUNT, EXPECTED_SUPPORT_TRUNCATION_COUNT), "PBI01_TRACT_ACCOUNTING_MISMATCH", "tract computability or support accounting differs")
    _require((tract_meta.get("computable_count"), tract_meta.get("noncomputable_count"), tract_meta.get("support_truncation_count")) == (computable, noncomputable, truncated), "PBI01_METADATA_ACCOUNTING_MISMATCH", "metadata tract accounting differs")
    _require(all(row["model_lineage_id"] == model_lineage and row["public_lineage_id"] == public_lineage for row in tract_rows), "PBI01_TRACT_LINEAGE_MISMATCH", "tract lineage differs from metadata")

    seed_rows = _read_csv(paths["seed"], contract["seed_context_output"]["columns"], "PBI01_SEED_INPUT_INVALID")
    seed_row_count = seed_meta.get("row_count")
    eligible_count = seed_meta.get("fitting_eligible_count")
    excluded_count = seed_meta.get("fitting_excluded_count")
    _require(
        isinstance(seed_row_count, int)
        and seed_row_count > 0
        and isinstance(eligible_count, int)
        and eligible_count >= 0
        and isinstance(excluded_count, int)
        and excluded_count >= 0,
        "PBI01_SEED_ACCOUNTING_MISMATCH",
        "seed-context accounting is malformed",
    )
    _require(len(seed_rows) == seed_row_count, "PBI01_SEED_COUNT_MISMATCH", "seed-context row count differs from accepted accounting")
    seed_ids = [row["protected_physical_location_id"] for row in seed_rows]
    _require(all(seed_ids) and len(seed_ids) == len(set(seed_ids)), "PBI01_SEED_IDENTITY_MISMATCH", "seed-context identities are absent or duplicated")
    _require(all(row["model_lineage_id"] == model_lineage and row["qa_status"] for row in seed_rows), "PBI01_SEED_LINEAGE_OR_QA_MISMATCH", "seed-context lineage or QA differs")
    _require(eligible_count + excluded_count == seed_row_count, "PBI01_SEED_ACCOUNTING_MISMATCH", "seed-context eligibility accounting differs")

    geometry = geometry_path or root / "powerbi" / "pbi01" / "presentation" / "michigan_2024_tracts.geojson"
    geometry_geoids = _extract_geometry_geoids(geometry)
    _require(len(geometry_geoids) == EXPECTED_TRACT_COUNT, "PBI01_GEOMETRY_COUNT_MISMATCH", "presentation geometry tract count differs")
    _require(geometry_geoids == set(geoids), "PBI01_GEOMETRY_RECONCILIATION_MISMATCH", "presentation geometry and tract input GEOIDs differ")

    return Pbi01PreflightResult(
        state="READY",
        contract_identity_verified=True,
        metadata_ready_verified=True,
        metadata_bound_hashes_verified=True,
        lineage_verified=True,
        tract_schema_verified=True,
        tract_count=len(tract_rows),
        computable_count=computable,
        noncomputable_count=noncomputable,
        support_truncation_count=truncated,
        seed_schema_verified=True,
        seed_context_ready=True,
        geometry_reconciled=True,
        geometry_geoid_count=len(geometry_geoids),
    )
