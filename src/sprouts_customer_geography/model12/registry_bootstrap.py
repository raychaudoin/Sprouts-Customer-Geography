"""Create one MODEL-12 registry from exact authorized inputs without broad discovery."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

from sprouts_customer_geography.model11.resolver import ProtectedHandleResolver as Model11Resolver
from sprouts_customer_geography.pipe01.canonical import content_digest, file_sha256, write_json_exclusive
from sprouts_customer_geography.pipe01.errors import ConformanceError, require
from sprouts_customer_geography.pipe02.resolver import _is_within

from .resolver import CANONICAL_PROJECTION_FIELDS, REGISTRY_ID, REGISTRY_VERSION, resolve_exact_basename


def _load_object(path: Path, code: str) -> dict[str, Any]:
    require(path.is_file(), code, "required protected JSON is absent")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        require(False, code, "required protected JSON is unreadable")
    require(isinstance(value, dict), code, "required protected JSON must be an object")
    return value


def _accepted_model11_state(model11_registry: Path, repository_root: Path) -> tuple[Model11Resolver, Path, Path, Path, Path, Path]:
    resolver = Model11Resolver.load(model11_registry, repository_root)
    output = resolver.resolve(str(resolver.development_request["model11_output_root_handle"]), "model11_output_root").path
    runs_root = output / "model11-development-runs"
    candidates: list[tuple[Path, Path, Path]] = []
    if runs_root.is_dir():
        for run_dir in runs_root.iterdir():
            package = run_dir / "model11_wisconsin_multivariate_development_package.json"
            ready = run_dir / "READY.json"
            manifest = run_dir / "development_manifest.json"
            if run_dir.is_dir() and package.is_file() and ready.is_file() and manifest.is_file():
                candidates.append((package, ready, manifest))
    require(len(candidates) == 1, "MODEL12_ACCEPTED_MODEL11_FINAL_STATE_AMBIGUOUS", "exactly one accepted MODEL-11 READY development state is required")
    package_path, ready_path, manifest_path = candidates[0]
    package = _load_object(package_path, "MODEL12_MODEL11_DEVELOPMENT_PACKAGE_UNRESOLVED")
    ready = _load_object(ready_path, "MODEL12_MODEL11_DEVELOPMENT_READY_UNRESOLVED")
    manifest = _load_object(manifest_path, "MODEL12_MODEL11_DEVELOPMENT_MANIFEST_UNRESOLVED")
    semantic = copy.deepcopy(package)
    protected_hash = semantic.pop("protected_content_sha256", None)
    stable = semantic.pop("stable_development_identity", None)
    require(
        package.get("package_id") == "MODEL11_WISCONSIN_MULTIVARIATE_DEVELOPMENT_PACKAGE_V1"
        and package.get("state") == "ready"
        and package.get("selection", {}).get("preferred_candidate_id") == "challenger_multivariate_elastic_net"
        and protected_hash == content_digest(semantic)
        and stable == "model11-development:sha256:" + str(protected_hash)
        and ready.get("state") == "ready"
        and ready.get("protected_content_sha256") == protected_hash
        and ready.get("stable_development_identity") == stable
        and manifest.get("state") == "ready"
        and manifest.get("protected_content_sha256") == protected_hash
        and manifest.get("package_file_sha256") == file_sha256(package_path),
        "MODEL12_MODEL11_FINAL_STATE_MISMATCH",
        "MODEL-11 final development package READY or manifest binding differs",
    )
    freeze_id = package.get("authority", {}).get("feature_freeze_run_id")
    require(isinstance(freeze_id, str) and re.fullmatch(r"m11freeze-[A-Za-z0-9_-]+", freeze_id), "MODEL12_MODEL11_FEATURE_FREEZE_ID_INVALID", "MODEL-11 feature-freeze identity is invalid")
    freeze_dir = (output / "model11-feature-freezes" / freeze_id).resolve()
    require(_is_within(freeze_dir, output.resolve()), "PROTECTED_PATH_CONTAINMENT_FAILED", "MODEL-11 feature freeze escapes its output root")
    freeze_package = freeze_dir / "model11_target_blind_feature_freeze_package.json"
    freeze_ready = freeze_dir / "READY.json"
    require(freeze_package.is_file() and freeze_ready.is_file(), "MODEL12_MODEL11_FEATURE_FREEZE_UNRESOLVED", "accepted MODEL-11 feature freeze is absent")
    return resolver, package_path, ready_path, manifest_path, freeze_package, freeze_ready


def build_registry(
    *,
    repository_root: Path,
    registry_path: Path,
    source_root: Path,
    source_basename: str,
    model11_registry: Path,
    data04_ready_dir: Path,
    geo05_support_dir: Path,
    output_root: Path,
    header_alias_overrides: Mapping[str, Sequence[str]] | None = None,
    source_authority_id: str = "PROTECTED_MI_AGGREGATED_SOURCE_V1",
) -> None:
    repository = repository_root.resolve()
    registry = registry_path.resolve()
    source_directory = source_root.resolve()
    output = output_root.resolve()
    require(not _is_within(registry, repository) and not _is_within(source_directory, repository) and not _is_within(output, repository), "PROTECTED_PATH_INVALID", "MODEL-12 registry source and output roots must remain outside Git")
    require(not registry.exists(), "PROTECTED_REGISTRY_IMMUTABLE", "MODEL-12 registry already exists")
    source = resolve_exact_basename(source_directory, source_basename)
    model11, development_package, development_ready, development_manifest, freeze_package, freeze_ready = _accepted_model11_state(model11_registry.resolve(), repository)
    model11_output = model11.resolve(str(model11.development_request["model11_output_root_handle"]), "model11_output_root").path
    public_data = data04_ready_dir.resolve()
    public_geo = geo05_support_dir.resolve()
    require(public_data.is_dir() and public_geo.is_dir(), "MODEL12_PUBLIC_DEPENDENCY_UNRESOLVED", "accepted DATA-04 or GEO-05 package is absent")
    output.mkdir(parents=True, exist_ok=True)
    registry.parent.mkdir(parents=True, exist_ok=True)

    overrides = {str(field): [str(value) for value in values] for field, values in (header_alias_overrides or {}).items()}
    require(
        set(overrides) <= CANONICAL_PROJECTION_FIELDS
        and all(values and all(value.strip() for value in values) for values in overrides.values()),
        "MODEL12_SOURCE_HEADER_ALIAS_OVERRIDE_INVALID",
        "source header alias overrides are invalid",
    )
    roots = {
        "proot-model12-source": str(source_directory),
        "proot-model11-output": str(model11_output),
        "proot-model12-output": str(output.parent),
    }
    resources = {
        "phandle-model12-source": {"root_handle": "proot-model12-source", "relative_path": source.name, "kind": "michigan_seed_source"},
        "phandle-model11-development-package": {"root_handle": "proot-model11-output", "relative_path": development_package.relative_to(model11_output).as_posix(), "kind": "model11_development_package"},
        "phandle-model11-development-ready": {"root_handle": "proot-model11-output", "relative_path": development_ready.relative_to(model11_output).as_posix(), "kind": "model11_development_ready_marker"},
        "phandle-model11-development-manifest": {"root_handle": "proot-model11-output", "relative_path": development_manifest.relative_to(model11_output).as_posix(), "kind": "model11_development_manifest"},
        "phandle-model11-feature-freeze-package": {"root_handle": "proot-model11-output", "relative_path": freeze_package.relative_to(model11_output).as_posix(), "kind": "model11_feature_freeze_package"},
        "phandle-model11-feature-freeze-ready": {"root_handle": "proot-model11-output", "relative_path": freeze_ready.relative_to(model11_output).as_posix(), "kind": "model11_feature_freeze_ready_marker"},
        "phandle-model12-output": {"root_handle": "proot-model12-output", "relative_path": output.name, "kind": "model12_output_root"},
    }
    request = {
        "michigan_source_handle": "phandle-model12-source",
        "model11_development_package_handle": "phandle-model11-development-package",
        "model11_development_ready_marker_handle": "phandle-model11-development-ready",
        "model11_development_manifest_handle": "phandle-model11-development-manifest",
        "model11_feature_freeze_package_handle": "phandle-model11-feature-freeze-package",
        "model11_feature_freeze_ready_marker_handle": "phandle-model11-feature-freeze-ready",
        "model12_output_root_handle": "phandle-model12-output",
    }
    document = {
        "registry_id": REGISTRY_ID,
        "version": REGISTRY_VERSION,
        "protected_roots": roots,
        "resources": resources,
        "source_authority": {
            "source_authority_id": source_authority_id,
            "source_root_handle": "proot-model12-source",
            "exact_basename": source_basename,
            "workbook_handle": "phandle-model12-source",
            "whole_workbook_hash_permitted": False,
            "expected_forecast_vintages": [2024, 2025, 2026],
            "header_alias_overrides": overrides,
        },
        "public_dependencies": {
            "data04_ready_dir": str(public_data),
            "geo05_support_dir": str(public_geo),
        },
        "materialization_request": request,
        "upstream_model11_registry_identity": model11.registry_identity,
    }
    write_json_exclusive(registry, document)


def _parse_alias_overrides(values: Sequence[str]) -> dict[str, list[str]]:
    output: dict[str, list[str]] = {}
    for raw in values:
        field, separator, alias = raw.partition("=")
        require(separator == "=" and field in CANONICAL_PROJECTION_FIELDS and bool(alias.strip()), "MODEL12_SOURCE_HEADER_ALIAS_OVERRIDE_INVALID", "header alias override must use canonical_field=alias")
        output.setdefault(field, []).append(alias)
    return output


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create one exact protected MODEL-12 handle registry")
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--source-basename", required=True)
    parser.add_argument("--model11-registry", type=Path, required=True)
    parser.add_argument("--data04-ready-dir", type=Path, required=True)
    parser.add_argument("--geo05-support-dir", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--header-alias-override", action="append", default=[])
    arguments = parser.parse_args(argv)
    try:
        build_registry(
            repository_root=arguments.repository_root,
            registry_path=arguments.registry,
            source_root=arguments.source_root,
            source_basename=arguments.source_basename,
            model11_registry=arguments.model11_registry,
            data04_ready_dir=arguments.data04_ready_dir,
            geo05_support_dir=arguments.geo05_support_dir,
            output_root=arguments.output_root,
            header_alias_overrides=_parse_alias_overrides(arguments.header_alias_override),
        )
        print(json.dumps({"state": "MODEL-12 protected registry ready", "exact_source_match_count": 1, "filesystem_discovery_performed": False, "protected_details_disclosed": False}, sort_keys=True))
        return 0
    except ConformanceError as exc:
        print(json.dumps({"state": "MODEL-12 protected registry blocked", "error_code": exc.code, "filesystem_discovery_performed": False, "protected_details_disclosed": False}, sort_keys=True))
        return 2
    except Exception:
        print(json.dumps({"state": "MODEL-12 protected registry blocked", "error_code": "UNEXPECTED_FAIL_CLOSED", "filesystem_discovery_performed": False, "protected_details_disclosed": False}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
