"""Protected-local MODEL-09 registry bootstrap from explicitly authorized paths."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sprouts_customer_geography.pipe01.canonical import write_json_exclusive
from sprouts_customer_geography.pipe01.errors import ConformanceError, require
from sprouts_customer_geography.pipe02.resolver import _is_within


RESOURCE_ARGUMENTS = (
    ("pipe04_binding", "pipe04_binding", "pipe04_binding_handle"),
    ("pipe04_ready", "pipe04_ready_marker", "pipe04_ready_marker_handle"),
    ("model10_package", "model10_package", "model10_package_handle"),
    ("model10_ready", "model10_ready_marker", "model10_ready_marker_handle"),
    ("acs_source", "accepted_acs_b11001_source", "acs_source_handle"),
    ("tiger_source", "accepted_tiger_tract_source", "tiger_source_handle"),
)


def build_registry(*, repository_root: Path, registry_path: Path, output_root: Path, resources: dict[str, Path]) -> None:
    repository = repository_root.resolve()
    registry = registry_path.resolve()
    output = output_root.resolve()
    require(registry.is_absolute() and output.is_absolute() and not _is_within(registry, repository) and not _is_within(output, repository), "PROTECTED_PATH_INVALID", "registry and output must be absolute and outside Git")
    require(not registry.exists(), "PROTECTED_REGISTRY_IMMUTABLE", "MODEL-09 registry already exists")
    registry.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    roots: dict[str, str] = {}
    declarations: dict[str, dict[str, str]] = {}
    request: dict[str, str] = {}
    for index, (argument, kind, request_field) in enumerate(RESOURCE_ARGUMENTS, start=1):
        path = resources[argument].resolve()
        require(path.is_absolute() and path.is_file() and not _is_within(path, repository), "PROTECTED_FILE_UNRESOLVED", "one explicit protected input does not resolve")
        root_handle = f"proot-input-{index:02d}"
        resource_handle = f"phandle-{argument.replace('_', '-')}"
        roots[root_handle] = str(path.parent)
        declarations[resource_handle] = {"root_handle": root_handle, "relative_path": path.name, "kind": kind}
        request[request_field] = resource_handle
    roots["proot-model09-output"] = str(output.parent)
    declarations["phandle-model09-output"] = {"root_handle": "proot-model09-output", "relative_path": output.name, "kind": "model09_output_root"}
    request["model09_output_root_handle"] = "phandle-model09-output"
    document = {"registry_id": "MODEL09_PROTECTED_HANDLE_REGISTRY_V1", "version": "1.0.0", "protected_roots": roots, "resources": declarations, "development_request": request}
    write_json_exclusive(registry, document)


def main() -> int:
    parser = argparse.ArgumentParser(description="Create one exact protected MODEL-09 handle registry")
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    for argument, _, _ in RESOURCE_ARGUMENTS:
        parser.add_argument("--" + argument.replace("_", "-"), type=Path, required=True)
    arguments = parser.parse_args()
    try:
        build_registry(repository_root=arguments.repository_root, registry_path=arguments.registry, output_root=arguments.output_root, resources={argument: getattr(arguments, argument) for argument, _, _ in RESOURCE_ARGUMENTS})
        print(json.dumps({"state": "MODEL-09 protected registry ready", "explicit_handles": 7, "filesystem_discovery_performed": False, "protected_details_disclosed": False}, sort_keys=True))
        return 0
    except ConformanceError as exc:
        print(json.dumps({"state": "MODEL-09 protected registry blocked", "error_code": exc.code, "filesystem_discovery_performed": False, "protected_details_disclosed": False}, sort_keys=True))
        return 2
    except Exception:
        print(json.dumps({"state": "MODEL-09 protected registry blocked", "error_code": "UNEXPECTED_FAIL_CLOSED", "filesystem_discovery_performed": False, "protected_details_disclosed": False}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
