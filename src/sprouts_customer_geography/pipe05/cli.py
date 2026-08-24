"""Disclosure-safe CLI for PIPE-05 protected binding."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from sprouts_customer_geography.pipe01.errors import ConformanceError

from .binding import build_disclosure_safe_result, execute_protected_binding, verify_persisted_binding
from .resolver import load_authorized_registry


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Materialize the protected PIPE-05 MODEL-12 Michigan Isolated Sales binding")
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--registry", type=Path, help="Exact protected registry; no discovery is performed")
    parser.add_argument("--binding-run-id")
    parser.add_argument("--package-version", default="1.0.0")
    parser.add_argument("--supersedes")
    return parser


def _registry_argument(explicit: Path | None) -> Path | None:
    if explicit is not None:
        return explicit
    configured = os.environ.get("PIPE05_AUTHORITY_REGISTRY")
    return Path(configured) if configured else None


def main() -> int:
    arguments = _parser().parse_args()
    try:
        resolver = load_authorized_registry(_registry_argument(arguments.registry), arguments.repository_root)
        result = execute_protected_binding(repository_root=arguments.repository_root, resolver=resolver, binding_run_id=arguments.binding_run_id, package_version=arguments.package_version, supersedes=arguments.supersedes)
        verification = verify_persisted_binding(repository_root=arguments.repository_root, resolver=resolver, run_dir=result.run_dir)
        print(json.dumps(build_disclosure_safe_result(result, verification), sort_keys=True))
        return 0
    except ConformanceError as exc:
        blockers = {"AUTHORITATIVE_ACCESS_REGISTRY_UNRESOLVED", "PROTECTED_HANDLE_UNRESOLVED", "PROTECTED_ROOTS_UNRESOLVED", "PROTECTED_RESOURCES_UNRESOLVED", "PROTECTED_RESOURCE_UNRESOLVED", "MODEL12_MATERIALIZATION_AUTHORITIES_INVALID", "MODEL12_IDENTITY_PACKAGE_UNRESOLVED", "PIPE05_SOURCE_RESOURCE_MISMATCH", "MODEL12_SOURCE_AUTHORITY_MISMATCH"}
        state = "PIPE-05 exact-source binding blocked" if exc.code in blockers else "PIPE-05 implementation/conformance failed"
        print(json.dumps({"completion_state": state, "error_code": exc.code, "isolated_sales_values_materialized": 0, "impacted_sales_body_values_accessed": 0, "other_outcome_body_values_accessed": 0, "benchmark_evaluation_performed": False, "model_work_performed": False, "filesystem_discovery_performed": False, "protected_details_disclosed": False}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
