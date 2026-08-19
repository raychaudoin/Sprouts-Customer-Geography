"""Disclosure-safe PIPE-01 command-line boundary."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from .run import audit_dependency_package
from .safeguards import assert_no_protected_tracked_paths


def _read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError("dependency package must be a JSON object")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PIPE-01 target-blind freeze safeguards")
    subparsers = parser.add_subparsers(dest="command", required=True)
    audit = subparsers.add_parser("audit-dependencies", help="report missing accepted dependency fields without echoing values")
    audit.add_argument("--package", required=True, type=Path)
    guard = subparsers.add_parser("guard-tracked", help="reject designated protected artifact classes in tracked paths")
    guard.add_argument("--repository", default=Path.cwd(), type=Path)
    args = parser.parse_args(argv)

    if args.command == "audit-dependencies":
        result = audit_dependency_package(_read_json(args.package))
        print(json.dumps(result, sort_keys=True))
        return 0 if result["state"] == "established" else 2
    tracked = subprocess.run(["git", "ls-files"], cwd=args.repository, check=True, capture_output=True, text=True).stdout.splitlines()
    assert_no_protected_tracked_paths(tracked)
    print(json.dumps({"state": "passed", "tracked_path_count": len(tracked)}, sort_keys=True))
    return 0
