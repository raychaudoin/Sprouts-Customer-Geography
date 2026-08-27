"""Disclosure-safe command line for MODEL-14 public-feature work."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Sequence

from sprouts_customer_geography.pipe01.errors import ConformanceError

from .experiment import execute_protected_experiment
from .public import compare_public_freezes, load_contract, materialize_public_freeze


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Freeze MODEL-14 public features before any development-target access")
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("verify-contract", help="verify the frozen experimental public-feature contract")

    freeze = subparsers.add_parser("public-freeze", help="materialize one immutable public-only tract freeze")
    freeze.add_argument("--raw-root", type=Path, default=Path("data/raw/model14"))
    freeze.add_argument("--output", type=Path, required=True)

    compare = subparsers.add_parser("compare-public", help="require byte-identical independent public freezes")
    compare.add_argument("first", type=Path)
    compare.add_argument("second", type=Path)

    protected = subparsers.add_parser("protected-experiment", help="evaluate the frozen candidates through exact accepted MODEL-13 authority")
    protected.add_argument("--public-freeze", type=Path, required=True)
    protected.add_argument("--verification-freeze", type=Path, required=True)
    protected.add_argument("--output", type=Path, required=True)
    return parser


def _resolve(root: Path, value: Path) -> Path:
    return value.resolve() if value.is_absolute() else (root / value).resolve()


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    root = arguments.repository_root.resolve()
    try:
        if arguments.command == "verify-contract":
            contract = load_contract(root)
            result = {
                "state": "valid",
                "contract_id": contract["artifact_id"],
                "candidate_feature_count": len(contract["feature_catalog"]),
                "target_blind": contract["target_blind"],
            }
        elif arguments.command == "public-freeze":
            freeze = materialize_public_freeze(root, _resolve(root, arguments.raw_root), _resolve(root, arguments.output))
            result = {
                "state": freeze.report["state"],
                "tract_count": freeze.report["matrix"]["row_count"],
                "candidate_feature_count": freeze.report["candidate_feature_count"],
                "target_values_accessed": freeze.report["chronology"]["target_values_accessed"],
            }
        elif arguments.command == "compare-public":
            comparison = compare_public_freezes(_resolve(root, arguments.first), _resolve(root, arguments.second))
            result = {
                "state": comparison["state"],
                "file_count": comparison["file_count"],
                "target_values_accessed": comparison["target_values_accessed"],
            }
        else:
            registry = os.environ.get("MODEL13_AUTHORITY_REGISTRY")
            if not registry:
                raise ConformanceError("AUTHORITATIVE_ACCESS_REGISTRY_UNRESOLVED", "no MODEL-13 registry is configured for this executor")
            safe = execute_protected_experiment(
                repository_root=root,
                registry_path=Path(registry),
                public_freeze_dir=_resolve(root, arguments.public_freeze),
                verification_freeze_dir=_resolve(root, arguments.verification_freeze),
                output_dir=_resolve(root, arguments.output),
            )
            strongest = safe["strongest_expanded_candidate_id"]
            result = {
                "state": safe["state"],
                "baseline_reproduction": safe["accepted_predecessor"]["baseline_reproduction"]["state"],
                "strongest_expanded_candidate_id": strongest,
                "evidence_disposition": safe["evidence_disposition"],
                "pooled_spearman": safe["candidate_matrix"][strongest]["aggregate_oof"]["pooled"]["spearman"],
                "michigan_spearman": safe["candidate_matrix"][strongest]["aggregate_oof"]["michigan"]["spearman"],
                "wisconsin_spearman": safe["candidate_matrix"][strongest]["aggregate_oof"]["wisconsin"]["spearman"],
                "protected_details_disclosed": False,
            }
    except ConformanceError as exc:
        print(json.dumps({"state": "failed_closed", "code": exc.code}, sort_keys=True))
        return 2
    except Exception:
        print(json.dumps({"state": "failed_closed", "code": "MODEL14_UNEXPECTED_FAILURE"}, sort_keys=True))
        return 3
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
