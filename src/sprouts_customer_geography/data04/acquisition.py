"""Credential-free acquisition and exact-byte verification for DATA-04."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from sprouts_customer_geography.data03.acquisition import _assert_generated_path, _download_exact, download_pinned_exact
from sprouts_customer_geography.data03.contract import validate_metadata_documents
from sprouts_customer_geography.pipe01.canonical import write_json_exclusive
from sprouts_customer_geography.pipe01.errors import require

from .contract import Data04Authority


Progress = Callable[[str], None]


def _assert_ignored_public_path(path: Path, repository_root: Path, code: str) -> Path:
    resolved = path.resolve()
    root = repository_root.resolve()
    try:
        relative = resolved.relative_to(root).as_posix()
    except ValueError:
        return resolved
    allowed = any(relative == prefix or relative.startswith(prefix + "/") for prefix in ("data/raw", "data/cache", "data/local", "outputs"))
    require(allowed, code, "local public-source paths inside the repository must remain under ignored data/raw data/cache data/local or outputs")
    return resolved


def _require_exact(observation: dict[str, Any], expected_length: int, expected_sha: str, source_name: str) -> None:
    require(observation["byte_length"] == expected_length, "DATA04_SOURCE_LENGTH_MISMATCH", f"accepted byte length differs for {source_name}")
    require(observation["byte_sha256"] == expected_sha, "DATA04_SOURCE_CHECKSUM_MISMATCH", f"accepted checksum differs for {source_name}")


def acquire_sources(
    authority: Data04Authority,
    repository_root: Path,
    acs_raw_dir: Path,
    household_source: Path,
    tiger_raw_dir: Path,
    observation_output_dir: Path,
    progress: Progress = print,
) -> dict[str, Any]:
    """Recover or reacquire every exact public source without creating new authority."""
    acs_raw_dir = _assert_generated_path(acs_raw_dir, repository_root, "DATA04_ACS_RAW_PATH_NOT_IGNORED")
    household_source = _assert_ignored_public_path(household_source, repository_root, "DATA04_HOUSEHOLD_RAW_PATH_NOT_IGNORED")
    tiger_raw_dir = _assert_generated_path(tiger_raw_dir, repository_root, "DATA04_TIGER_RAW_PATH_NOT_IGNORED")
    observation_output_dir = _assert_generated_path(observation_output_dir, repository_root, "DATA04_OUTPUT_PATH_NOT_IGNORED")
    require(not observation_output_dir.exists(), "DATA04_OUTPUT_OVERWRITE_DENIED", "acquisition observation output already exists")

    contract = authority.contract
    base_url = contract["source_products"]["acs"]["table_file_base_url"]
    multivariate_observations: list[dict[str, Any]] = []
    metadata_documents: dict[str, dict[str, Any]] = {}
    for table, reference in zip(authority.data03_contract["tables"], contract["accepted_acs_national_authority"]["multivariate_tables"]):
        destination = acs_raw_dir / reference["source_filename"]
        observed = download_pinned_exact(
            f"{base_url}/{reference['source_filename']}",
            destination,
            reference["source_byte_length"],
            reference["source_byte_sha256"],
            progress,
        )
        _require_exact(observed, reference["source_byte_length"], reference["source_byte_sha256"], table["table_id"])
        multivariate_observations.append({"table_id": table["table_id"], **observed})
        metadata_destination = acs_raw_dir / f"{table['table_id'].lower()}.metadata.json"
        metadata_observed = _download_exact(table["metadata_url"], metadata_destination, progress)
        metadata_documents[table["table_id"]] = json.loads(metadata_destination.read_text(encoding="utf-8"))
        multivariate_observations[-1]["metadata_byte_sha256"] = metadata_observed["byte_sha256"]
    metadata_sha = validate_metadata_documents(authority.data03_contract, metadata_documents)

    household_reference = contract["accepted_acs_national_authority"]["household_manifest"]
    household_observation = download_pinned_exact(
        authority.household_manifest["source_reference"],
        household_source,
        household_reference["source_byte_length"],
        household_reference["source_byte_sha256"],
        progress,
    )
    _require_exact(household_observation, household_reference["source_byte_length"], household_reference["source_byte_sha256"], "B11001")

    tiger_destination = tiger_raw_dir / authority.tiger_manifest["source_filename"]
    tiger_observation = download_pinned_exact(
        authority.tiger_manifest["source_reference"],
        tiger_destination,
        authority.tiger_manifest["retrieval"]["expected_byte_length"],
        authority.tiger_manifest["byte_sha256"],
        progress,
    )
    _require_exact(tiger_observation, authority.tiger_manifest["retrieval"]["expected_byte_length"], authority.tiger_manifest["byte_sha256"], "Michigan TIGER")

    report = {
        "report_id": "DATA04_PUBLIC_SOURCE_ACQUISITION_OBSERVATIONS_V1",
        "state": "OBSERVED_EXACT_AUTHORITY_BYTES",
        "contract_id": contract["artifact_id"],
        "contract_content_sha256": contract["content_sha256"],
        "household_observation": household_observation,
        "multivariate_observations": multivariate_observations,
        "metadata_identity_sha256": metadata_sha,
        "tiger_observation": tiger_observation,
        "source_integrity": "Every observed source byte identity matches existing accepted ACS authority or the additive DATA-04 Michigan TIGER manifest; no bytes were repinned.",
    }
    observation_output_dir.mkdir(parents=True, exist_ok=False)
    write_json_exclusive(observation_output_dir / "acquisition_observations.json", report)
    return report
