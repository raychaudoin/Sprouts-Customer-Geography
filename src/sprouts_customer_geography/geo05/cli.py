"""Command-line interface for GEO-05 public Michigan spatial support."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence

from sprouts_customer_geography.pipe01.canonical import write_json_exclusive
from sprouts_customer_geography.pipe01.errors import ConformanceError

from .contract import load_authority
from .materialization import (
    _assert_output_path,
    compare_materializations,
    evaluate_anchor,
    materialize_real,
    verify_data04_ready,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Materialize and consume GEO-05 public-only Michigan statewide spatial support")
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("verify-contract", help="validate exact GEO-05, DATA-04, GEO-03, and MODEL-11 public authority")

    verify_ready = subparsers.add_parser("verify-data04-ready", help="verify one current accepted DATA-04 public READY package")
    verify_ready.add_argument("--data04-ready-dir", type=Path, required=True)

    materialize = subparsers.add_parser("materialize", help="create one immutable complete Michigan spatial-support package")
    materialize.add_argument("--tiger-source", type=Path, default=Path("data/raw/data04/tl_2024_26_tract.zip"))
    materialize.add_argument("--data04-ready-dir", type=Path, required=True)
    materialize.add_argument("--output-dir", type=Path, required=True)

    compare = subparsers.add_parser("compare", help="require byte-identical files across two independent READY runs")
    compare.add_argument("first", type=Path)
    compare.add_argument("second", type=Path)
    compare.add_argument("--comparison-output", type=Path)

    evaluate = subparsers.add_parser("evaluate-anchor", help="produce target-blind public spatial evidence for a later supplied anchor")
    evaluate.add_argument("--materialization-dir", type=Path, required=True)
    evaluate.add_argument("--latitude", type=float, required=True)
    evaluate.add_argument("--longitude", type=float, required=True)
    evaluate.add_argument("--anchor-identity", required=True)
    evaluate.add_argument("--anchor-lineage", required=True)
    evaluate.add_argument("--radius-m", type=float, action="append", dest="radii_m")
    evaluate.add_argument("--output", type=Path, help="exclusive JSON output; inside the repository it must remain under ignored outputs")
    return parser


def _resolve(root: Path, path: Path) -> Path:
    return path if path.is_absolute() else root / path


def _run(args: argparse.Namespace) -> int:
    root = args.repository_root.resolve()
    authority = load_authority(root)
    if args.command == "verify-contract":
        print(
            json.dumps(
                {
                    "state": "valid",
                    "spatial_spec_id": authority.specification["artifact_id"],
                    "spatial_spec_content_sha256": authority.specification["content_sha256"],
                    "tract_count": authority.specification["state_scope"]["tract_count"],
                    "inventory_sha256": authority.specification["statewide_inventory"]["inventory_sha256"],
                },
                sort_keys=True,
            )
        )
        return 0
    if args.command == "verify-data04-ready":
        rows, lineage = verify_data04_ready(authority, _resolve(root, args.data04_ready_dir))
        print(json.dumps({"state": "valid", "tract_count": len(rows), **lineage}, sort_keys=True))
        return 0
    if args.command == "materialize":
        report = materialize_real(
            root,
            _resolve(root, args.tiger_source),
            _resolve(root, args.data04_ready_dir),
            _resolve(root, args.output_dir),
        )
        print(
            json.dumps(
                {
                    "state": report["state"],
                    "tract_count": report["tract_count"],
                    "inventory_sha256": report["inventory_sha256"],
                    "protected_evidence_accessed": report["protected_evidence_access"]["sprouts_or_protected_evidence_accessed"],
                },
                sort_keys=True,
            )
        )
        return 0
    if args.command == "compare":
        comparison_output = None if args.comparison_output is None else _assert_output_path(_resolve(root, args.comparison_output), root)
        report = compare_materializations(_resolve(root, args.first), _resolve(root, args.second), comparison_output)
        print(json.dumps({"state": report["state"], "file_count": report["file_count"]}, sort_keys=True))
        return 0
    evidence = evaluate_anchor(
        root,
        _resolve(root, args.materialization_dir),
        latitude=args.latitude,
        longitude=args.longitude,
        opaque_anchor_identity=args.anchor_identity,
        opaque_anchor_lineage=args.anchor_lineage,
        radii_m=args.radii_m,
    )
    if args.output is None:
        print(json.dumps(evidence, allow_nan=False, sort_keys=True, separators=(",", ":")))
    else:
        destination = _assert_output_path(_resolve(root, args.output), root)
        write_json_exclusive(destination, evidence)
        print(json.dumps({"state": evidence["state"], "containing_tract_geoid": evidence["containing_tract_geoid"], "radius_count": len(evidence["memberships"]), "output_written": True}, sort_keys=True))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return _run(args)
    except ConformanceError as exc:
        print(
            json.dumps(
                {
                    "state": "NONCOMPUTABLE",
                    "error_code": exc.code,
                    "error_message": exc.message,
                    "partial_membership_emitted": False,
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
