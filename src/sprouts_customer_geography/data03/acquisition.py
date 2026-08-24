"""Credential-free acquisition observations from exact official DATA-03 sources."""

from __future__ import annotations

import hashlib
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
