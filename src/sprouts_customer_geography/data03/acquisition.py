"""Credential-free acquisition observations from exact official DATA-03 sources."""

from __future__ import annotations

import hashlib
from http.client import HTTPException
import json
import os
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.request import Request, urlopen

from sprouts_customer_geography.data03.contract import validate_metadata_documents
from sprouts_customer_geography.pipe01.canonical import file_sha256, write_json_exclusive
from sprouts_customer_geography.pipe01.errors import require


Progress = Callable[[str], None]
USER_AGENT = "Sprouts-Customer-Geography-DATA03/1.0 public-source-reproducibility"


def _assert_generated_path(path: Path, repository_root: Path, code: str) -> Path:
    resolved = path.resolve()
    root = repository_root.resolve()
    try:
        relative = resolved.relative_to(root)
    except ValueError:
        return resolved
    normalized = relative.as_posix()
    allowed = normalized == "outputs" or normalized.startswith("outputs/") or normalized.startswith("data/raw/") or normalized.startswith("data/cache/")
    require(allowed, code, "generated acquisition paths inside the repository must remain under ignored data/raw data/cache or outputs")
    return resolved


def _observe_file(path: Path, reused: bool) -> dict[str, Any]:
    return {
        "filename": path.name,
        "byte_length": path.stat().st_size,
        "byte_sha256": file_sha256(path),
        "reused_existing": reused,
    }


def _download_exact(url: str, destination: Path, progress: Progress) -> dict[str, Any]:
    if destination.is_file():
        progress(f"reuse {destination.name}")
        return _observe_file(destination, True)
    require(not destination.exists(), "DATA03_ACQUISITION_DESTINATION_INVALID", f"destination is not a regular file: {destination}")
    partial = destination.with_name(destination.name + ".partial")
    require(not partial.exists(), "DATA03_ACQUISITION_INCOMPLETE_EXISTS", f"incomplete download exists: {partial.name}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    progress(f"download {destination.name}")
    request = Request(url, headers={"User-Agent": USER_AGENT})
    digest = hashlib.sha256()
    length = 0
    try:
        with urlopen(request, timeout=180) as response, partial.open("xb") as handle:
            while True:
                block = response.read(1024 * 1024)
                if not block:
                    break
                handle.write(block)
                digest.update(block)
                length += len(block)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(partial, destination)
    except BaseException:
        # Preserve the .partial evidence for explicit retry handling; never publish it as complete.
        raise
    progress(f"observed {destination.name} bytes={length} sha256={digest.hexdigest()}")
    return {"filename": destination.name, "byte_length": length, "byte_sha256": digest.hexdigest(), "reused_existing": False}


def download_pinned_exact(
    url: str,
    destination: Path,
    expected_length: int,
    expected_sha256: str,
    progress: Progress,
    max_attempts: int = 3,
) -> dict[str, Any]:
    """Retry safely while promoting only bytes that match an existing pinned identity."""
    require(expected_length > 0, "PINNED_SOURCE_LENGTH_INVALID", "pinned source length must be positive")
    require(len(expected_sha256) == 64 and all(character in "0123456789abcdef" for character in expected_sha256), "PINNED_SOURCE_CHECKSUM_INVALID", "pinned source checksum must be lowercase SHA-256")
    require(max_attempts > 0, "PINNED_SOURCE_RETRY_COUNT_INVALID", "pinned source retry count must be positive")

    def require_expected(observation: Mapping[str, Any]) -> None:
        require(observation["byte_length"] == expected_length, "PINNED_SOURCE_LENGTH_MISMATCH", f"pinned byte length differs for {destination.name}")
        require(observation["byte_sha256"] == expected_sha256, "PINNED_SOURCE_CHECKSUM_MISMATCH", f"pinned checksum differs for {destination.name}")

    if destination.is_file():
        observation = _observe_file(destination, True)
        require_expected(observation)
        progress(f"reuse {destination.name}")
        return observation
    require(not destination.exists(), "PINNED_SOURCE_DESTINATION_INVALID", f"destination is not a regular file: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)

    last_error: OSError | HTTPException | None = None
    for attempt in range(1, max_attempts + 1):
        suffix = ".partial" if attempt == 1 else f".partial.{attempt}"
        partial = destination.with_name(destination.name + suffix)
        if partial.exists():
            require(partial.is_file(), "PINNED_SOURCE_PARTIAL_INVALID", f"partial attempt is not a regular file: {partial.name}")
            observation = _observe_file(partial, True)
            if observation["byte_length"] == expected_length and observation["byte_sha256"] == expected_sha256:
                os.replace(partial, destination)
                progress(f"promote verified {partial.name}")
                return _observe_file(destination, True)
            progress(f"preserve incomplete {partial.name}; use next bounded attempt")
            continue

        progress(f"download {destination.name} attempt={attempt}/{max_attempts}")
        request = Request(url, headers={"User-Agent": USER_AGENT})
        digest = hashlib.sha256()
        length = 0
        try:
            with urlopen(request, timeout=180) as response, partial.open("xb") as handle:
                while True:
                    block = response.read(1024 * 1024)
                    if not block:
                        break
                    handle.write(block)
                    digest.update(block)
                    length += len(block)
                handle.flush()
                os.fsync(handle.fileno())
        except (OSError, HTTPException) as error:
            last_error = error
            progress(f"preserve failed {partial.name}; retry remains bounded")
            continue

        observation = {"filename": destination.name, "byte_length": length, "byte_sha256": digest.hexdigest(), "reused_existing": False}
        require_expected(observation)
        os.replace(partial, destination)
        progress(f"verified {destination.name} bytes={length} sha256={digest.hexdigest()}")
        return observation

    if last_error is not None:
        raise last_error
    require(False, "PINNED_SOURCE_RETRY_EXHAUSTED", f"all preserved partial attempt slots are occupied for {destination.name}")
    raise AssertionError("unreachable")


def acquire_sources(
    contract: Mapping[str, Any],
    tiger_manifest: Mapping[str, Any],
    repository_root: Path,
    raw_dir: Path,
    observation_output_dir: Path,
    progress: Progress = print,
) -> dict[str, Any]:
    """Download exact public bytes and record observations without creating authority."""
    raw_dir = _assert_generated_path(raw_dir, repository_root, "DATA03_RAW_PATH_NOT_IGNORED")
    observation_output_dir = _assert_generated_path(observation_output_dir, repository_root, "DATA03_OUTPUT_PATH_NOT_IGNORED")
    require(not observation_output_dir.exists(), "DATA03_OUTPUT_OVERWRITE_DENIED", "acquisition observation output already exists")

    table_observations: list[dict[str, Any]] = []
    metadata_documents: dict[str, Mapping[str, Any]] = {}
    metadata_observations: list[dict[str, Any]] = []
    for table in contract["tables"]:
        table_id = table["table_id"]
        filename = f"acsdt5y2024-{table_id.lower()}.dat"
        source_url = f"{contract['source_product']['table_file_base_url']}/{filename}"
        observed = _download_exact(source_url, raw_dir / filename, progress)
        table_observations.append({"table_id": table_id, "source_reference": source_url, **observed})

        metadata_filename = f"{table_id.lower()}.metadata.json"
        metadata_observed = _download_exact(table["metadata_url"], raw_dir / metadata_filename, progress)
        metadata_observations.append({"table_id": table_id, "source_reference": table["metadata_url"], **metadata_observed})
        metadata_documents[table_id] = json.loads((raw_dir / metadata_filename).read_text(encoding="utf-8"))

    metadata_identity_sha256 = validate_metadata_documents(contract, metadata_documents)
    tiger_filename = str(tiger_manifest.get("source_filename", ""))
    tiger_url = str(tiger_manifest.get("source_reference", ""))
    require(tiger_filename == "tl_2024_55_tract.zip" and tiger_url == "https://www2.census.gov/geo/tiger/TIGER2024/TRACT/tl_2024_55_tract.zip", "DATA03_TIGER_AUTHORITY_MISMATCH", "accepted TIGER identity differs")
    tiger_observation = _download_exact(tiger_url, raw_dir / tiger_filename, progress)
    require(tiger_observation["byte_length"] == tiger_manifest.get("retrieval", {}).get("expected_byte_length") and tiger_observation["byte_sha256"] == tiger_manifest.get("byte_sha256"), "DATA03_TIGER_CHECKSUM_MISMATCH", "downloaded TIGER bytes differ from accepted DATA-02 authority")

    report = {
        "report_id": "DATA03_ACQUISITION_OBSERVATIONS_V1",
        "state": "OBSERVED_NOT_AUTHORITY",
        "contract_id": contract["artifact_id"],
        "contract_version": contract["version"],
        "retrieval_date": contract["source_product"]["retrieval_date"],
        "access_surface": contract["source_product"]["materialization_access_surface"],
        "table_observations": table_observations,
        "metadata_observations": metadata_observations,
        "metadata_identity_sha256": metadata_identity_sha256,
        "tiger_observation": {"manifest_id": tiger_manifest["manifest_id"], **tiger_observation},
        "authority_boundary": "Observed checksums become accepted only when recorded in repository source manifests and accepted through the governed DATA-03 H/A lifecycle.",
    }
    observation_output_dir.mkdir(parents=True, exist_ok=False)
    write_json_exclusive(observation_output_dir / "acquisition_observations.json", report)
    progress("acquisition observations complete; no source authority was inferred")
    return report
