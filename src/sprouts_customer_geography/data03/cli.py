"""Command line interface for credential-free DATA-03 acquisition and materialization."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from sprouts_customer_geography.data03.acquisition import acquire_sources
from sprouts_customer_geography.data03.contract import build_api_query_url, load_contract
from sprouts_customer_geography.data03.materialization import compare_materializations, materialize_real


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Acquire and materialize the pinned DATA-03 Wisconsin ACS source menu")
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    subparsers = parser.add_subparsers(dest="command", required=True)

    acquire = subparsers.add_parser("acquire", help="download exact official public source bytes and emit non-authoritative checksum observations")
    acquire.add_argument("--raw-dir", type=Path, default=Path("data/raw/data03"))
    acquire.add_argument("--observation-output-dir", type=Path, default=Path("outputs/data03-acquisition"))

    materialize = subparsers.add_parser("materialize", help="verify pinned source bytes and create a target-blind Wisconsin tract materialization")
    materialize.add_argument("--raw-dir", type=Path, default=Path("data/raw/data03"))
    materialize.add_argument("--output-dir", type=Path, required=True)

    query = subparsers.add_parser("api-query", help="print the deterministic credential-free API query identity URL")
    query.set_defaults(no_paths=True)

    compare = subparsers.add_parser("compare", help="verify byte-identical outputs from two independent materializations")
    compare.add_argument("first", type=Path)
    compare.add_argument("second", type=Path)
    return parser


def _resolve(repository_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else repository_root / path


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    repository_root = args.repository_root.resolve()
    contract = load_contract(repository_root)
    if args.command == "api-query":
        print(build_api_query_url(contract))
        return 0
    if args.command == "acquire":
        tiger_manifest = json.loads((repository_root / contract["geography"]["tiger_manifest_path"]).read_text(encoding="utf-8"))
        report = acquire_sources(
            contract,
            tiger_manifest,
            repository_root,
            _resolve(repository_root, args.raw_dir),
            _resolve(repository_root, args.observation_output_dir),
        )
        print(json.dumps({"state": report["state"], "table_count": len(report["table_observations"]), "metadata_identity_sha256": report["metadata_identity_sha256"]}, sort_keys=True))
        return 0
    if args.command == "materialize":
        report = materialize_real(repository_root, _resolve(repository_root, args.raw_dir), _resolve(repository_root, args.output_dir))
        print(json.dumps({"state": report["state"], "tract_count": report["tract_count"], "candidate_measure_count": len(report["candidate_measure_coverage"])}, sort_keys=True))
        return 0
    hashes = compare_materializations(_resolve(repository_root, args.first), _resolve(repository_root, args.second))
    print(json.dumps({"state": "deterministic", "files": hashes}, sort_keys=True))
    return 0
