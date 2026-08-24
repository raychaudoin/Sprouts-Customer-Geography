"""Command-line interface for DATA-04 public source acquisition and materialization."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .acquisition import acquire_sources
from .contract import load_authority
from .materialization import compare_materializations, materialize_real


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Acquire and materialize exact statewide Michigan DATA-04 public sources")
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("verify-contract", help="validate exact DATA-04, accepted DATA-02/DATA-03, and Michigan TIGER authority")

    acquire = subparsers.add_parser("acquire", help="recover or download exact fixed public bytes and emit checksum observations")
    acquire.add_argument("--acs-raw-dir", type=Path, default=Path("data/raw/data03"))
    acquire.add_argument("--household-source", type=Path, default=Path("data/local/acsdt5y2024-b11001.dat"))
    acquire.add_argument("--tiger-raw-dir", type=Path, default=Path("data/raw/data04"))
    acquire.add_argument("--observation-output-dir", type=Path, default=Path("outputs/data04-acquisition"))

    materialize = subparsers.add_parser("materialize", help="create one immutable statewide Michigan public-data package")
    materialize.add_argument("--acs-raw-dir", type=Path, default=Path("data/raw/data03"))
    materialize.add_argument("--household-source", type=Path, default=Path("data/local/acsdt5y2024-b11001.dat"))
    materialize.add_argument("--tiger-source", type=Path, default=Path("data/raw/data04/tl_2024_26_tract.zip"))
    materialize.add_argument("--output-dir", type=Path, required=True)

    compare = subparsers.add_parser("compare", help="require byte-identical files across two independent READY runs")
    compare.add_argument("first", type=Path)
    compare.add_argument("second", type=Path)
    compare.add_argument("--comparison-output", type=Path)
    return parser


def _resolve(root: Path, path: Path) -> Path:
    return path if path.is_absolute() else root / path


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    root = args.repository_root.resolve()
    authority = load_authority(root)
    if args.command == "verify-contract":
        print(json.dumps({"state": "valid", "contract_id": authority.contract["artifact_id"], "tract_count": authority.contract["state_scope"]["observed_tract_count"]}, sort_keys=True))
        return 0
    if args.command == "acquire":
        report = acquire_sources(authority, root, _resolve(root, args.acs_raw_dir), _resolve(root, args.household_source), _resolve(root, args.tiger_raw_dir), _resolve(root, args.observation_output_dir))
        print(json.dumps({"state": report["state"], "multivariate_table_count": len(report["multivariate_observations"])}, sort_keys=True))
        return 0
    if args.command == "materialize":
        report = materialize_real(root, _resolve(root, args.acs_raw_dir), _resolve(root, args.household_source), _resolve(root, args.tiger_source), _resolve(root, args.output_dir))
        print(json.dumps({"state": report["state"], "tract_count": report["tract_count"], "candidate_measure_count": report["multivariate_evidence"]["candidate_measure_count"]}, sort_keys=True))
        return 0
    comparison_output = None if args.comparison_output is None else _resolve(root, args.comparison_output)
    report = compare_materializations(_resolve(root, args.first), _resolve(root, args.second), comparison_output)
    print(json.dumps({"state": report["state"], "file_count": report["file_count"]}, sort_keys=True))
    return 0
