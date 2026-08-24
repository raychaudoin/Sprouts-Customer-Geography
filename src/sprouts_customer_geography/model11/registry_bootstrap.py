"""Create one MODEL-11 registry from exact authorized paths without discovery."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sprouts_customer_geography.pipe01.canonical import write_json_exclusive
from sprouts_customer_geography.pipe01.errors import ConformanceError, require
from sprouts_customer_geography.pipe02.resolver import _is_within


RESOURCES = (
    ("model10_package", "model10_package", "model10_package_handle"),
    ("model10_ready", "model10_ready_marker", "model10_ready_marker_handle"),
    ("pipe04_binding", "pipe04_binding", "pipe04_binding_handle"),
    ("pipe04_ready", "pipe04_ready_marker", "pipe04_ready_marker_handle"),
    ("acs_b11001_source", "accepted_acs_b11001_source", "acs_b11001_source_handle"),
    ("tiger_source", "accepted_tiger_tract_source", "tiger_source_handle"),
    ("data03_normalized_source", "data03_normalized_source", "data03_normalized_source_handle"),
    ("data03_verification_report", "data03_verification_report", "data03_verification_report_handle"),
    ("data03_ready", "data03_ready_marker", "data03_ready_marker_handle"),
)


def build_registry(*, repository_root: Path, registry_path: Path, output_root: Path, resources: dict[str, Path]) -> None:
    repository = repository_root.resolve()
    registry = registry_path.resolve()
    output = output_root.resolve()
    require(not _is_within(registry, repository) and not _is_within(output, repository), "PROTECTED_PATH_INVALID", "registry and output must remain outside Git")
    require(not registry.exists(), "PROTECTED_REGISTRY_IMMUTABLE", "MODEL-11 registry already exists")
    registry.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    roots: dict[str, str] = {}
    declarations: dict[str, dict[str, str]] = {}
    request: dict[str, str] = {}
    for index, (argument, kind, request_field) in enumerate(RESOURCES, start=1):
        path = resources[argument].resolve()
        require(path.is_file() and not _is_within(path, repository), "PROTECTED_FILE_UNRESOLVED", "one exact MODEL-11 input is absent or inside Git")
        root_handle = f"proot-input-{index:02d}"
        resource_handle = "phandle-" + argument.replace("_", "-")
        roots[root_handle] = str(path.parent)
        declarations[resource_handle] = {"root_handle": root_handle, "relative_path": path.name, "kind": kind}
        request[request_field] = resource_handle
    roots["proot-model11-output"] = str(output.parent)
    declarations["phandle-model11-output"] = {"root_handle": "proot-model11-output", "relative_path": output.name, "kind": "model11_output_root"}
    request["model11_output_root_handle"] = "phandle-model11-output"
    write_json_exclusive(registry, {"registry_id": "MODEL11_PROTECTED_HANDLE_REGISTRY_V1", "version": "1.0.0", "protected_roots": roots, "resources": declarations, "development_request": request})


def main() -> int:
    parser = argparse.ArgumentParser(description="Create one exact protected MODEL-11 handle registry")
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    for argument, _, _ in RESOURCES:
        parser.add_argument("--" + argument.replace("_", "-"), type=Path, required=True)
    arguments = parser.parse_args()
    try:
        build_registry(repository_root=arguments.repository_root, registry_path=arguments.registry, output_root=arguments.output_root, resources={argument: getattr(arguments, argument) for argument, _, _ in RESOURCES})
        print(json.dumps({"state": "MODEL-11 protected registry ready", "explicit_handles": 10, "filesystem_discovery_performed": False, "protected_details_disclosed": False}, sort_keys=True))
        return 0
    except ConformanceError as exc:
        print(json.dumps({"state": "MODEL-11 protected registry blocked", "error_code": exc.code, "filesystem_discovery_performed": False, "protected_details_disclosed": False}, sort_keys=True))
        return 2
    except Exception:
        print(json.dumps({"state": "MODEL-11 protected registry blocked", "error_code": "UNEXPECTED_FAIL_CLOSED", "filesystem_discovery_performed": False, "protected_details_disclosed": False}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
