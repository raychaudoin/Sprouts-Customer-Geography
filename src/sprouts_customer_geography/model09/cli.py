"""Disclosure-safe CLI for protected MODEL-09 development."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from sprouts_customer_geography.pipe01.errors import ConformanceError

from .development import build_disclosure_safe_result, execute_protected_development
from .resolver import load_authorized_registry


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run protected MODEL-09 Wisconsin experimental development")
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--registry", type=Path, help="Exact protected MODEL-09 registry; no discovery is performed")
    parser.add_argument("--development-run-id")
    parser.add_argument("--package-version", default="1.0.0")
    parser.add_argument("--supersedes")
    return parser


def main() -> int:
    arguments = _parser().parse_args()
    registry_path = arguments.registry or (Path(os.environ["MODEL09_AUTHORITY_REGISTRY"]) if os.environ.get("MODEL09_AUTHORITY_REGISTRY") else None)
    try:
        resolver = load_authorized_registry(registry_path, arguments.repository_root)
        result = execute_protected_development(repository_root=arguments.repository_root, resolver=resolver, development_run_id=arguments.development_run_id, package_version=arguments.package_version, supersedes=arguments.supersedes)
        print(json.dumps(build_disclosure_safe_result(result), sort_keys=True))
        return 0
    except ConformanceError as exc:
        print(json.dumps({"completion_state": "MODEL-09 blocked fail closed", "error_code": exc.code, "development_consumption_state": "CHECK_PROTECTED_INCOMPLETE_RUN", "impacted_sales_values_accessed": 0, "non_wisconsin_target_values_accessed": 0, "filesystem_discovery_performed": False, "protected_details_disclosed": False}, sort_keys=True))
        return 2
    except Exception:
        print(json.dumps({"completion_state": "MODEL-09 blocked fail closed", "error_code": "UNEXPECTED_FAIL_CLOSED", "development_consumption_state": "CHECK_PROTECTED_INCOMPLETE_RUN", "filesystem_discovery_performed": False, "protected_details_disclosed": False}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
