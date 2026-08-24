"""Disclosure-safe MODEL-13 command line interface."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from sprouts_customer_geography.pipe01.errors import ConformanceError

from .resolver import load_authorized_registry
from .workflow import build_disclosure_safe_result, compare_runs, execute_model13


def main() -> int:
    parser = argparse.ArgumentParser(description="Execute protected MODEL-13")
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run")
    run.add_argument("--registry", type=Path)
    run.add_argument("--run-id")
    run.add_argument("--verification-of")
    compare = subparsers.add_parser("compare")
    compare.add_argument("--first", type=Path, required=True)
    compare.add_argument("--second", type=Path, required=True)
    arguments = parser.parse_args()
    root = arguments.repository_root.resolve()
    try:
        if arguments.command == "run":
            configured = arguments.registry or (Path(os.environ["MODEL13_AUTHORITY_REGISTRY"]) if os.environ.get("MODEL13_AUTHORITY_REGISTRY") else None)
            resolver = load_authorized_registry(configured, root)
            result = execute_model13(repository_root=root, resolver=resolver, run_id=arguments.run_id, verification_of=arguments.verification_of)
            print(json.dumps(build_disclosure_safe_result(result), sort_keys=True))
        else:
            print(json.dumps(compare_runs(arguments.first, arguments.second), sort_keys=True))
        return 0
    except ConformanceError as exc:
        print(json.dumps({"completion_state": "MODEL-13 blocked fail closed", "error_code": exc.code, "impacted_sales_values_accessed": 0, "protected_details_disclosed": False}, sort_keys=True))
        return 2
    except Exception:
        print(json.dumps({"completion_state": "MODEL-13 blocked fail closed", "error_code": "UNEXPECTED_FAIL_CLOSED", "impacted_sales_values_accessed": 0, "protected_details_disclosed": False}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
