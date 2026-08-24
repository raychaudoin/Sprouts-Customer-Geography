"""Disclosure-safe CLI for protected MODEL-12 scoring."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Sequence

from sprouts_customer_geography.pipe01.errors import ConformanceError

from .contract import verify_repository_authority
from .materialization import (
    build_disclosure_safe_field_result,
    build_disclosure_safe_result,
    compare_materializations,
    execute_field_scoring,
    execute_protected_materialization,
)
from .resolver import load_authorized_registry


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run protected target-blind Michigan frozen MODEL-11 scoring")
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("verify-contract", help="verify exact accepted MODEL-12 predecessor authority")

    materialize = subparsers.add_parser("materialize-seeds", help="materialize complete target-blind Michigan identity features and frozen scores")
    materialize.add_argument("--registry", type=Path)
    materialize.add_argument("--run-id")
    materialize.add_argument("--supersedes")

    field = subparsers.add_parser("score-anchors", help="score explicit local opaque Michigan anchors without opening the seed source")
    field.add_argument("--registry", type=Path)
    field.add_argument("--input", type=Path, required=True)
    field.add_argument("--run-id")

    compare = subparsers.add_parser("compare", help="require deterministic semantic equality across two protected seed runs")
    compare.add_argument("first", type=Path)
    compare.add_argument("second", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    root = arguments.repository_root.resolve()
    try:
        if arguments.command == "verify-contract":
            contract = verify_repository_authority(root)
            print(json.dumps({"state": "valid", "contract_id": contract["artifact_id"], "target_body_access_authorized": False, "frozen_candidate_id": contract["frozen_scoring"]["preferred_candidate_id"]}, sort_keys=True))
            return 0
        if arguments.command == "compare":
            print(json.dumps(compare_materializations(arguments.first, arguments.second), sort_keys=True))
            return 0
        registry_path = arguments.registry or (Path(os.environ["MODEL12_AUTHORITY_REGISTRY"]) if os.environ.get("MODEL12_AUTHORITY_REGISTRY") else None)
        resolver = load_authorized_registry(registry_path, root)
        if arguments.command == "materialize-seeds":
            result = execute_protected_materialization(repository_root=root, resolver=resolver, run_id=arguments.run_id, supersedes=arguments.supersedes)
            print(json.dumps(build_disclosure_safe_result(result), sort_keys=True))
        else:
            result = execute_field_scoring(repository_root=root, resolver=resolver, input_path=arguments.input, run_id=arguments.run_id)
            print(json.dumps(build_disclosure_safe_field_result(result), sort_keys=True))
        return 0
    except ConformanceError as exc:
        print(
            json.dumps(
                {
                    "completion_state": "MODEL-12 blocked fail closed",
                    "command": arguments.command,
                    "error_code": exc.code,
                    "michigan_target_body_values_accessed": 0,
                    "filesystem_discovery_performed": False,
                    "protected_details_disclosed": False,
                },
                sort_keys=True,
            )
        )
        return 2
    except Exception:
        print(
            json.dumps(
                {
                    "completion_state": "MODEL-12 blocked fail closed",
                    "command": arguments.command,
                    "error_code": "UNEXPECTED_FAIL_CLOSED",
                    "michigan_target_body_values_accessed": 0,
                    "filesystem_discovery_performed": False,
                    "protected_details_disclosed": False,
                },
                sort_keys=True,
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
