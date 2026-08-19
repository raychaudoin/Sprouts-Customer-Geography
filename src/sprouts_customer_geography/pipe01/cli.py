"""Disclosure-safe PIPE-01 command-line boundary."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from .orchestration import execute_protected_freeze
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
    production = subparsers.add_parser("run-production", help="execute the authorized target-blind production freeze path")
    production.add_argument("--repository", default=Path.cwd(), type=Path)
    production.add_argument("--protected-root", required=True, type=Path)
    production.add_argument("--tiger-source-zip", required=True, type=Path)
    production.add_argument("--acs-source-file", required=True, type=Path)
    production.add_argument("--model04-package", required=True, type=Path)
    production.add_argument("--model04-nonce", required=True, type=Path)
    production.add_argument("--model04-commitment-evidence", required=True, type=Path)
    production.add_argument("--accepted-dependency-preflight", required=True, type=Path)
    production.add_argument("--code-identity", required=True)
    production.add_argument("--run-id")
    production.add_argument("--supersedes")
    args = parser.parse_args(argv)

    if args.command == "audit-dependencies":
        result = audit_dependency_package(_read_json(args.package))
        print(json.dumps(result, sort_keys=True))
        return 0 if result["state"] == "established" else 2
    if args.command == "run-production":
        result = execute_protected_freeze(
            repository_root=args.repository,
            protected_root=args.protected_root,
            tiger_source_zip=args.tiger_source_zip,
            acs_source_file=args.acs_source_file,
            model04_package_path=args.model04_package,
            model04_nonce_path=args.model04_nonce,
            model04_commitment_evidence_path=args.model04_commitment_evidence,
            accepted_dependency_preflight_path=args.accepted_dependency_preflight,
            code_identity=args.code_identity,
            run_id=args.run_id,
            supersedes=args.supersedes,
        )
        # The CLI returns only the disclosure-safe report. Protected paths,
        # context identities, memberships, totals, and predictions stay local.
        print(json.dumps(result.disclosure_safe_report, sort_keys=True))
        return 0
    tracked = subprocess.run(["git", "ls-files"], cwd=args.repository, check=True, capture_output=True, text=True).stdout.splitlines()
    assert_no_protected_tracked_paths(tracked)
    print(json.dumps({"state": "passed", "tracked_path_count": len(tracked)}, sort_keys=True))
    return 0
