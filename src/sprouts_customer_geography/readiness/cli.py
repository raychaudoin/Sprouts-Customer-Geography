"""Command-line entry points for protected-local recovery and safe publishing."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sprouts_customer_geography.pipe01.errors import ConformanceError
from sprouts_customer_geography.readiness.disclosure import load_and_validate_development_readiness
from sprouts_customer_geography.readiness.publisher import publish_readiness
from sprouts_customer_geography.readiness.repository import probe_repository
from sprouts_customer_geography.readiness.store import (
    bootstrap_from_app01_settings,
    recover_project_state,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage the Sprouts Customer Geography durable project profile and safe readiness mailbox.")
    subcommands = parser.add_subparsers(dest="command", required=True)

    bootstrap = subcommands.add_parser("bootstrap", help="Initialize durable state from one trusted APP-01 settings registration.")
    bootstrap.add_argument("--repository-root", type=Path, default=Path.cwd())
    bootstrap.add_argument("--state-root", type=Path)
    bootstrap.add_argument("--settings", type=Path)

    verify = subcommands.add_parser("verify", help="Verify automatic fresh-session recovery without revealing local paths.")
    verify.add_argument("--state-root", type=Path)
    verify.add_argument("--repository-root", type=Path, default=Path.cwd())

    publish = subcommands.add_parser("publish", help="Write one schema-bound Development Readiness Mailbox snapshot.")
    publish.add_argument("--repository-root", type=Path, default=Path.cwd())
    publish.add_argument("--state-root", type=Path)
    publish.add_argument("--output", type=Path, required=True)

    validate = subcommands.add_parser("validate", help="Validate one mailbox snapshot without printing its contents.")
    validate.add_argument("--repository-root", type=Path, default=Path.cwd())
    validate.add_argument("--input", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        if arguments.command == "bootstrap":
            store = bootstrap_from_app01_settings(
                arguments.repository_root,
                state_root=arguments.state_root,
                settings_path=arguments.settings,
            )
            facts = store.readiness_facts()
            result = {
                "asset_catalog": facts["asset_catalog"],
                "profile": facts["project_profile"],
                "state": "bootstrapped",
            }
        elif arguments.command == "verify":
            store = recover_project_state(arguments.state_root, repository_root=arguments.repository_root)
            store.verify()
            baseline = probe_repository(arguments.repository_root).verified_commit
            if arguments.state_root is None:
                store.record_recovery(baseline, "passed", fresh_session=True)
            result = {"profile": "ready", "state": "recovered"}
        elif arguments.command == "publish":
            document = publish_readiness(
                arguments.repository_root,
                arguments.output,
                state_root=arguments.state_root,
            )
            result = {
                "snapshot_id": document["snapshot_id"],
                "state": "published",
                "worktree_state": document["repository"]["worktree_state"],
            }
        else:
            repository = arguments.repository_root.resolve()
            schema = repository / "schemas" / "readiness" / "development_readiness.schema.json"
            load_and_validate_development_readiness(arguments.input, schema)
            result = {"snapshot": "valid", "state": "validated"}
    except ConformanceError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except OSError:
        print("READINESS_IO_FAILED: readiness operation could not access its bounded local state", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
