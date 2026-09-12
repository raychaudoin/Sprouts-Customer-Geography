"""Repository-safe conformance check for the GOV-16 readiness capability."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def main() -> int:
    repository = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repository / "src"))
    from sprouts_customer_geography.pipe01.safeguards import assert_no_protected_tracked_paths
    from sprouts_customer_geography.readiness.disclosure import (
        load_json_safely,
        validate_development_readiness,
        validate_development_readiness_schema,
    )

    schema_path = repository / "schemas" / "readiness" / "development_readiness.schema.json"
    schema = load_json_safely(schema_path, error_code="READINESS_SCHEMA_UNREADABLE")
    validate_development_readiness_schema(schema)
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    synthetic = {
        "schema_version": "1.0.0",
        "snapshot_id": "development-readiness-v1",
        "generated_at_utc": "2026-08-31T00:00:00Z",
        "repository": {
            "verified_commit": commit,
            "worktree_state": "CLEAN",
            "active_initiatives": [],
            "safe_work": [],
        },
        "protected_state": {
            "project_profile": "MISSING",
            "asset_catalog": "UNRESOLVED",
            "original_source_inventory": "UNRESOLVED",
            "evidence_ledger": "UNRESOLVED",
            "model13_authority": "NOT_VERIFIED",
            "app01_inputs": "NOT_VERIFIED",
        },
        "preservation": {"model14": "NOT_VERIFIED", "model15": "NOT_VERIFIED"},
        "recovery": {"fresh_session": "NOT_VERIFIED"},
        "prerequisites": [
            {"code": "REPOSITORY_READINESS", "status": "READY"},
            {"code": "PROTECTED_PROJECT_PROFILE", "status": "NEEDS_RUNWAY"},
            {"code": "PROTECTED_ASSET_CATALOG", "status": "NEEDS_RUNWAY"},
            {"code": "ORIGINAL_SOURCE_INVENTORY", "status": "NEEDS_RUNWAY"},
            {"code": "EVIDENCE_LEDGER", "status": "NEEDS_RUNWAY"},
            {"code": "MODEL13_AUTHORITY", "status": "NEEDS_RUNWAY"},
            {"code": "APP01_INPUT_PACKAGE", "status": "NEEDS_RUNWAY"},
            {"code": "MODEL14_PRESERVATION", "status": "NEEDS_RUNWAY"},
            {"code": "MODEL15_PRESERVATION", "status": "NEEDS_RUNWAY"},
            {"code": "FRESH_SESSION_RECOVERY", "status": "NEEDS_RUNWAY"},
        ],
    }
    validate_development_readiness(synthetic, schema=schema)
    stageable = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    assert_no_protected_tracked_paths(stageable)
    if any(Path(path).name.lower() == "development-readiness.json" for path in stageable):
        raise SystemExit("a readiness snapshot belongs only at the root of the dedicated readiness-mailbox branch")
    print(json.dumps({"readiness_schema": "passed", "synthetic_snapshot": "passed", "tracked_path_safeguard": "passed"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
