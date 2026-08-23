"""Disclosure-safe CLI for PIPE-04 protected binding."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from sprouts_customer_geography.pipe01.errors import ConformanceError

from .binding import build_disclosure_safe_result, execute_protected_binding
from .resolver import load_authorized_registry


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Materialize the protected PIPE-04 MODEL-10 Wisconsin development binding")
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--registry", type=Path, help="Exact protected registry; no discovery is performed")
    parser.add_argument("--binding-run-id")
    parser.add_argument("--package-version", default="1.0.0")
    parser.add_argument("--supersedes")
    return parser


def _registry_argument(explicit: Path | None) -> Path | None:
    if explicit is not None:
        return explicit
    configured = os.environ.get("PIPE04_AUTHORITY_REGISTRY")
    return Path(configured) if configured else None


def main() -> int:
    arguments = _parser().parse_args()
    try:
        resolver = load_authorized_registry(_registry_argument(arguments.registry), arguments.repository_root)
        result = execute_protected_binding(repository_root=arguments.repository_root, resolver=resolver, binding_run_id=arguments.binding_run_id, package_version=arguments.package_version, supersedes=arguments.supersedes)
        print(json.dumps(build_disclosure_safe_result(result), sort_keys=True))
        return 0
    except ConformanceError as exc:
        blockers = {"AUTHORITATIVE_ACCESS_REGISTRY_UNRESOLVED", "PROTECTED_HANDLE_UNRESOLVED", "PROTECTED_ROOTS_UNRESOLVED", "PROTECTED_RESOURCES_UNRESOLVED", "TARGET_SOURCE_AUTHORITIES_UNRESOLVED", "TARGET_SOURCE_COMPLETENESS_FAILED", "PROTECTED_DIRECTORY_UNRESOLVED", "PROTECTED_FILE_UNRESOLVED", "MODEL10_PACKAGE_UNRESOLVED", "MODEL10_COMMITMENT_EVIDENCE_UNRESOLVED", "MODEL10_COMMITMENT_NONCE_UNRESOLVED", "MODEL10_READY_MARKER_UNRESOLVED"}
        state = "PIPE-04 exact-source binding blocked" if exc.code in blockers else "PIPE-04 implementation/conformance failed"
        print(json.dumps({"completion_state": state, "error_code": exc.code, "isolated_sales_values_materialized": 0, "impacted_sales_values_materialized": 0, "non_wisconsin_target_values_materialized": 0, "filesystem_discovery_performed": False, "protected_details_disclosed": False}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
