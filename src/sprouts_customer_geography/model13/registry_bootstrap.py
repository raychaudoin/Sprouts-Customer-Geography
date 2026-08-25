"""Build one MODEL-13 registry from exact accepted predecessor registries and run."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sprouts_customer_geography.model11.resolver import ProtectedHandleResolver as Model11Resolver
from sprouts_customer_geography.model12.resolver import ProtectedHandleResolver as Model12Resolver
from sprouts_customer_geography.pipe01.canonical import write_json_exclusive
from sprouts_customer_geography.pipe01.errors import ConformanceError, require
from sprouts_customer_geography.pipe02.resolver import _is_within
from sprouts_customer_geography.pipe05.resolver import ProtectedHandleResolver as Pipe05Resolver


def _declare(path: Path, index: int, kind: str, *, directory: bool = False) -> tuple[str, str, dict[str, str]]:
    resolved = path.resolve()
    require(resolved.is_dir() if directory else resolved.is_file(), "PROTECTED_RESOURCE_UNRESOLVED", "one exact MODEL-13 predecessor is absent")
    root_handle = f"proot-model13-{index:02d}"
    resource_handle = "phandle-" + kind.replace("_", "-")
    return root_handle, resource_handle, {"root_handle": root_handle, "relative_path": resolved.name, "kind": kind}


def build_registry(
    *,
    repository_root: Path,
    registry_path: Path,
    model11_registry_path: Path,
    model12_registry_path: Path,
    pipe05_registry_path: Path,
    pipe05_ready_run: Path,
    output_root: Path,
) -> None:
    repository = repository_root.resolve()
    registry = registry_path.resolve()
    output = output_root.resolve()
    require(not _is_within(registry, repository) and not _is_within(output, repository), "PROTECTED_PATH_INVALID", "MODEL-13 registry and output must remain outside Git")
    require(not registry.exists() and not output.exists(), "PROTECTED_REGISTRY_OR_OUTPUT_IMMUTABLE", "MODEL-13 registry or output already exists")
    Model11Resolver.load(model11_registry_path, repository)
    Model12Resolver.load(model12_registry_path, repository)
    pipe05 = Pipe05Resolver.load(pipe05_registry_path, repository)
    accepted_pipe05_output = pipe05.resolve(str(pipe05.binding_request["binding_output_root_handle"]), "pipe05_output_root").path.resolve()
    run = pipe05_ready_run.resolve()
    require(_is_within(run, accepted_pipe05_output / "pipe05-bindings") and (run / "READY.json").is_file(), "PIPE05_READY_RUN_INVALID", "explicit PIPE-05 run is not one accepted READY binding")
    registry.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True)
    exact = [
        (model11_registry_path, "model11_registry", False),
        (model12_registry_path, "model12_registry", False),
        (pipe05_registry_path, "pipe05_registry", False),
        (run, "pipe05_ready_run", True),
        (output, "model13_output_root", True),
    ]
    roots: dict[str, str] = {}
    resources: dict[str, dict[str, str]] = {}
    request: dict[str, str] = {}
    fields = ["model11_registry_handle", "model12_registry_handle", "pipe05_registry_handle", "pipe05_ready_run_handle", "model13_output_root_handle"]
    for index, ((raw_path, kind, directory), field) in enumerate(zip(exact, fields), start=1):
        path = raw_path.resolve()
        root_handle, resource_handle, declaration = _declare(path, index, kind, directory=directory)
        roots[root_handle] = str(path.parent)
        resources[resource_handle] = declaration
        request[field] = resource_handle
    write_json_exclusive(registry, {"registry_id": "MODEL13_PROTECTED_HANDLE_REGISTRY_V1", "version": "1.0.0", "protected_roots": roots, "resources": resources, "execution_request": request})


def main() -> int:
    parser = argparse.ArgumentParser(description="Create one exact protected MODEL-13 handle registry")
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--model11-registry", type=Path, required=True)
    parser.add_argument("--model12-registry", type=Path, required=True)
    parser.add_argument("--pipe05-registry", type=Path, required=True)
    parser.add_argument("--pipe05-ready-run", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    arguments = parser.parse_args()
    try:
        build_registry(repository_root=arguments.repository_root, registry_path=arguments.registry, model11_registry_path=arguments.model11_registry, model12_registry_path=arguments.model12_registry, pipe05_registry_path=arguments.pipe05_registry, pipe05_ready_run=arguments.pipe05_ready_run, output_root=arguments.output_root)
        print(json.dumps({"state": "MODEL-13 protected registry ready", "explicit_handle_count": 5, "filesystem_discovery_performed": False, "protected_details_disclosed": False}, sort_keys=True))
        return 0
    except ConformanceError as exc:
        print(json.dumps({"state": "MODEL-13 protected registry blocked", "error_code": exc.code, "filesystem_discovery_performed": False, "protected_details_disclosed": False}, sort_keys=True))
        return 2
    except Exception:
        print(json.dumps({"state": "MODEL-13 protected registry blocked", "error_code": "UNEXPECTED_FAIL_CLOSED", "filesystem_discovery_performed": False, "protected_details_disclosed": False}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
