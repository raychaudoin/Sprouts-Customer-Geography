"""Disclosure-safe PIPE-02 command-line surface."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from sprouts_customer_geography.pipe01.errors import ConformanceError

from .binding import build_disclosure_safe_result, execute_protected_binding
from .resolver import load_authorized_registry


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Materialize the protected PIPE-02 validation access binding")
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--registry", type=Path, help="Exact protected-local authority registry; no discovery is performed")
    parser.add_argument("--binding-run-id")
    return parser


def _registry_argument(explicit: Path | None) -> Path | None:
    if explicit is not None:
        return explicit
    configured = os.environ.get("PIPE02_AUTHORITY_REGISTRY")
    return Path(configured) if configured else None


def main() -> int:
    arguments = _parser().parse_args()
    try:
        resolver = load_authorized_registry(_registry_argument(arguments.registry), arguments.repository_root)
        result = execute_protected_binding(
            repository_root=arguments.repository_root,
            resolver=resolver,
            binding_run_id=arguments.binding_run_id,
        )
        print(json.dumps(build_disclosure_safe_result(result), sort_keys=True))
        return 0
    except ConformanceError as exc:
        dependency_blockers = {
            "AUTHORITATIVE_ACCESS_REGISTRY_UNRESOLVED",
            "PROTECTED_HANDLE_UNRESOLVED",
            "PROTECTED_ROOTS_UNRESOLVED",
            "PROTECTED_RESOURCES_UNRESOLVED",
            "TARGET_SOURCE_AUTHORITY_UNRESOLVED",
            "TARGET_PROJECTION_AUTHORITY_UNRESOLVED",
            "PROTECTED_DIRECTORY_UNRESOLVED",
            "PROTECTED_FILE_UNRESOLVED",
        }
        state = (
            "Binding blocked: authoritative access dependency unresolved"
            if exc.code in dependency_blockers
            else "Binding implementation/conformance failed"
        )
        print(
            json.dumps(
                {
                    "completion_state": state,
                    "error_code": exc.code,
                    "target_values_accessed": False,
                    "protected_details_disclosed": False,
                },
                sort_keys=True,
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
