"""Disclosure-safe CLI for MODEL-10 protected materialization."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from sprouts_customer_geography.pipe01.errors import ConformanceError

from .binding import build_disclosure_safe_result, execute_protected_materialization
from .resolver import load_authorized_registry


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="MODEL-10 target-blind Wisconsin successor identity materialization")
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--registry", type=Path)
    parser.add_argument("--run-id")
    parser.add_argument("--package-version", default="1.0.0")
    parser.add_argument("--supersedes")
    return parser


def main() -> int:
    args = _parser().parse_args()
    configured = os.environ.get("MODEL10_AUTHORITY_REGISTRY")
    registry_path = args.registry or (Path(configured) if configured else None)
    try:
        resolver = load_authorized_registry(registry_path, args.repository_root)
        result = execute_protected_materialization(
            repository_root=args.repository_root,
            resolver=resolver,
            materialization_run_id=args.run_id,
            package_version=args.package_version,
            supersedes=args.supersedes,
        )
        print(json.dumps(build_disclosure_safe_result(result), sort_keys=True))
        return 0
    except ConformanceError as exc:
        print(
            json.dumps(
                {
                    "completion_state": "BLOCKED_FAIL_CLOSED",
                    "error_code": exc.code,
                    "filesystem_discovery_performed": False,
                    "target_values_materialized": 0,
                    "protected_details_disclosed": False,
                },
                sort_keys=True,
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
