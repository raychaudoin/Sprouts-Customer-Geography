"""Create one PIPE-05 registry from exact accepted MODEL-12 and source inputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from sprouts_customer_geography.model12.materialization import STAGE_FILENAMES
from sprouts_customer_geography.model12.resolver import ProtectedHandleResolver as Model12Resolver, resolve_exact_basename
from sprouts_customer_geography.pipe01.canonical import file_sha256, write_json_exclusive
from sprouts_customer_geography.pipe01.commitment import freeze_commitment
from sprouts_customer_geography.pipe01.errors import ConformanceError, require
from sprouts_customer_geography.pipe02.resolver import _is_within

from .contract import load_model12_execution_commitment, verify_repository_authority
from .resolver import REGISTRY_ID, REGISTRY_VERSION, STAGE_NAMES
from .xlsx_projection import inspect_minimum_projection_authority


def _verified_materializations(
    output_root: Path,
    supplied_run_dirs: Sequence[Path],
    expected_runs: Sequence[Mapping[str, Any]],
) -> list[tuple[int, Path]]:
    """Verify two explicitly supplied MODEL-12 runs against accepted commitments."""

    collection = (output_root.resolve() / "model12-materializations").resolve()
    require(collection.is_dir(), "MODEL12_MATERIALIZATION_COLLECTION_UNRESOLVED", "accepted MODEL-12 materialization collection is absent")
    require(len(supplied_run_dirs) == 2, "MODEL12_MATERIALIZATION_AUTHORITIES_INVALID", "exactly two explicit MODEL-12 materialization runs are required")
    expected = {int(item["ordinal"]): item for item in expected_runs}
    require(set(expected) == {1, 2}, "MODEL12_MATERIALIZATION_AUTHORITIES_INVALID", "accepted MODEL-12 materialization ordinals differ")
    verified: list[tuple[int, Path]] = []
    seen: set[Path] = set()
    for ordinal, raw_candidate in enumerate(supplied_run_dirs, start=1):
        candidate = raw_candidate.resolve()
        require(
            candidate.is_dir()
            and candidate.parent == collection
            and _is_within(candidate, collection)
            and candidate not in seen
            and (candidate / "READY.json").is_file(),
            "MODEL12_ACCEPTED_MATERIALIZATION_UNRESOLVED",
            "explicit accepted MODEL-12 materialization run is absent or outside its collection",
        )
        computed: dict[str, str] = {}
        for stage in STAGE_NAMES:
            package = candidate / stage / STAGE_FILENAMES[stage]
            nonce = candidate / stage / "commitment_nonce.bin"
            evidence = candidate / stage / "commitment_evidence.json"
            ready = candidate / stage / "READY.json"
            require(
                all(path.is_file() for path in (package, nonce, evidence, ready)),
                "MODEL12_ACCEPTED_MATERIALIZATION_UNRESOLVED",
                "explicit accepted MODEL-12 materialization stage is incomplete",
            )
            try:
                nonce_bytes = nonce.read_bytes()
            except OSError as exc:
                raise ConformanceError("MODEL12_ACCEPTED_MATERIALIZATION_UNRESOLVED", "explicit accepted MODEL-12 materialization nonce is unreadable") from exc
            require(len(nonce_bytes) >= 16, "MODEL12_ACCEPTED_MATERIALIZATION_UNRESOLVED", "explicit accepted MODEL-12 materialization nonce is invalid")
            computed[stage] = freeze_commitment(file_sha256(package), nonce_bytes)
        require(
            computed == expected[ordinal].get("stage_commitments"),
            "MODEL12_ACCEPTED_MATERIALIZATION_AUTHORITY_MISMATCH",
            "explicit MODEL-12 materialization does not match its accepted ordinal",
        )
        verified.append((ordinal, candidate))
        seen.add(candidate)
    return verified


def build_registry(
    *,
    repository_root: Path,
    registry_path: Path,
    model12_registry_path: Path,
    model12_materialization_dirs: Sequence[Path],
    source_root: Path,
    source_basename: str,
    output_root: Path,
) -> None:
    repository = repository_root.resolve()
    registry = registry_path.resolve()
    source_directory = source_root.resolve()
    output = output_root.resolve()
    require(not _is_within(registry, repository) and not _is_within(source_directory, repository) and not _is_within(output, repository), "PROTECTED_PATH_INVALID", "PIPE-05 registry source and output roots must remain outside Git")
    require(not registry.exists(), "PROTECTED_REGISTRY_IMMUTABLE", "PIPE-05 registry already exists")
    contract = verify_repository_authority(repository)
    repository_commitment = load_model12_execution_commitment(repository, contract)
    model12 = Model12Resolver.load(model12_registry_path.resolve(), repository)
    model12_output = model12.resolve(str(model12.materialization_request["model12_output_root_handle"]), "model12_output_root").path.resolve()
    accepted_runs = _verified_materializations(model12_output, model12_materialization_dirs, repository_commitment["independent_materializations"])
    source = resolve_exact_basename(source_directory, source_basename)
    accepted_source = model12.resolve_source()
    require(source == accepted_source.path and source_basename == model12.source_authority.get("exact_basename"), "PIPE05_SOURCE_NOT_ACCEPTED_MODEL12_SOURCE", "PIPE-05 target source differs from the exact accepted MODEL-12 source authority")
    output.mkdir(parents=True, exist_ok=True)
    registry.parent.mkdir(parents=True, exist_ok=True)

    roots = {
        "proot-pipe05-model12": str(model12_output),
        "proot-pipe05-source": str(source_directory),
        "proot-pipe05-output-parent": str(output.parent),
    }
    resources: dict[str, dict[str, str]] = {
        "phandle-pipe05-source": {"root_handle": "proot-pipe05-source", "relative_path": source.name, "kind": "michigan_isolated_sales_target_source"},
        "phandle-pipe05-output": {"root_handle": "proot-pipe05-output-parent", "relative_path": output.name, "kind": "pipe05_output_root"},
    }
    materializations: list[dict[str, Any]] = []
    for ordinal, run_dir in accepted_runs:
        relative_run = run_dir.relative_to(model12_output)
        root_ready_handle = f"phandle-model12-{ordinal}-run-ready"
        resources[root_ready_handle] = {"root_handle": "proot-pipe05-model12", "relative_path": (relative_run / "READY.json").as_posix(), "kind": "model12_materialization_ready_marker"}
        stages: dict[str, dict[str, str]] = {}
        for stage in STAGE_NAMES:
            prefix = f"phandle-model12-{ordinal}-{stage.replace('_', '-')}"
            kind = {"identity": "model12_identity", "public_features": "model12_public_features", "frozen_scoring": "model12_frozen_scoring"}[stage]
            stage_dir = relative_run / stage
            handles = {
                "package_handle": prefix + "-package",
                "ready_marker_handle": prefix + "-ready",
                "commitment_evidence_handle": prefix + "-evidence",
                "commitment_nonce_handle": prefix + "-nonce",
            }
            resources[handles["package_handle"]] = {"root_handle": "proot-pipe05-model12", "relative_path": (stage_dir / STAGE_FILENAMES[stage]).as_posix(), "kind": f"{kind}_package"}
            resources[handles["ready_marker_handle"]] = {"root_handle": "proot-pipe05-model12", "relative_path": (stage_dir / "READY.json").as_posix(), "kind": f"{kind}_ready_marker"}
            resources[handles["commitment_evidence_handle"]] = {"root_handle": "proot-pipe05-model12", "relative_path": (stage_dir / "commitment_evidence.json").as_posix(), "kind": f"{kind}_commitment_evidence"}
            resources[handles["commitment_nonce_handle"]] = {"root_handle": "proot-pipe05-model12", "relative_path": (stage_dir / "commitment_nonce.bin").as_posix(), "kind": f"{kind}_commitment_nonce"}
            stages[stage] = handles
        materializations.append({"ordinal": ordinal, "run_ready_marker_handle": root_ready_handle, "stages": stages})

    source_authority_id = str(model12.source_authority["source_authority_id"])
    projection = inspect_minimum_projection_authority(source, workbook_handle="phandle-pipe05-source", source_authority_id=source_authority_id, header_alias_overrides=model12.header_alias_overrides)
    document = {
        "registry_id": REGISTRY_ID,
        "version": REGISTRY_VERSION,
        "protected_roots": roots,
        "resources": resources,
        "model12_materialization_authorities": materializations,
        "source_authority": {
            "source_authority_id": source_authority_id,
            "source_root_handle": "proot-pipe05-source",
            "exact_basename": source_basename,
            "workbook_handle": "phandle-pipe05-source",
            "whole_workbook_hash_permitted": False,
            "projection": projection,
        },
        "binding_request": {
            "primary_identity_authority_ordinal": 1,
            "michigan_target_source_handle": "phandle-pipe05-source",
            "binding_output_root_handle": "phandle-pipe05-output",
        },
    }
    write_json_exclusive(registry, document)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create one exact protected PIPE-05 handle registry")
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--model12-registry", type=Path, required=True)
    parser.add_argument("--model12-materialization-one", type=Path, required=True)
    parser.add_argument("--model12-materialization-two", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--source-basename", required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    arguments = parser.parse_args(argv)
    try:
        build_registry(repository_root=arguments.repository_root, registry_path=arguments.registry, model12_registry_path=arguments.model12_registry, model12_materialization_dirs=(arguments.model12_materialization_one, arguments.model12_materialization_two), source_root=arguments.source_root, source_basename=arguments.source_basename, output_root=arguments.output_root)
        print(json.dumps({"state": "PIPE-05 protected registry ready", "accepted_model12_materialization_count": 2, "exact_source_match_count": 1, "target_body_values_accessed": 0, "filesystem_discovery_performed": False, "protected_details_disclosed": False}, sort_keys=True))
        return 0
    except ConformanceError as exc:
        print(json.dumps({"state": "PIPE-05 protected registry blocked", "error_code": exc.code, "target_body_values_accessed": 0, "filesystem_discovery_performed": False, "protected_details_disclosed": False}, sort_keys=True))
        return 2
    except Exception:
        print(json.dumps({"state": "PIPE-05 protected registry blocked", "error_code": "UNEXPECTED_FAIL_CLOSED", "target_body_values_accessed": 0, "filesystem_discovery_performed": False, "protected_details_disclosed": False}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
