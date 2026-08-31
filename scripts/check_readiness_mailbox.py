"""Validate the actual snapshot and single-file refresh on readiness-mailbox."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path


def _git(repository: Path, *arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *arguments],
        cwd=repository,
        check=False,
        capture_output=True,
        text=True,
    )
    if check and result.returncode != 0:
        raise SystemExit("READINESS_MAILBOX_GIT_INVALID: mailbox Git state could not be verified")
    return result


def main() -> int:
    repository = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repository / "src"))
    from sprouts_customer_geography.pipe01.errors import ConformanceError
    from sprouts_customer_geography.readiness.disclosure import load_and_validate_development_readiness
    from sprouts_customer_geography.readiness.mailbox_contract import (
        MAILBOX_BRANCH,
        MAILBOX_ENFORCEMENT_PATHS,
        MAILBOX_FILENAME,
    )

    branch = os.environ.get("GITHUB_REF_NAME") or _git(repository, "symbolic-ref", "--quiet", "--short", "HEAD").stdout.strip()
    if branch != MAILBOX_BRANCH:
        raise SystemExit("READINESS_MAILBOX_BRANCH_INVALID: actual-snapshot validation requires readiness-mailbox")

    snapshot = repository / MAILBOX_FILENAME
    schema = repository / "schemas" / "readiness" / "development_readiness.schema.json"
    if snapshot.is_symlink() or not snapshot.is_file():
        raise SystemExit("READINESS_MAILBOX_PATH_INVALID: the root snapshot must be a regular file")
    index_entry = _git(repository, "ls-files", "-s", "--", MAILBOX_FILENAME).stdout.splitlines()
    if len(index_entry) != 1 or not index_entry[0].startswith("100644 "):
        raise SystemExit("READINESS_MAILBOX_MODE_INVALID: the root snapshot must use the regular JSON file mode")
    try:
        document = load_and_validate_development_readiness(snapshot, schema)
    except ConformanceError as exc:
        raise SystemExit(str(exc)) from None

    tracked = _git(repository, "ls-files").stdout.splitlines()
    mailbox_paths = [path for path in tracked if Path(path).name.lower() == MAILBOX_FILENAME]
    if mailbox_paths != [MAILBOX_FILENAME]:
        raise SystemExit("READINESS_MAILBOX_PATH_INVALID: exactly one root snapshot must be tracked")

    changed = _git(repository, "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD").stdout.splitlines()
    if changed == [MAILBOX_FILENAME]:
        mode = "snapshot"
        baseline = document["repository"]["verified_commit"]
    elif changed and set(changed) <= set(MAILBOX_ENFORCEMENT_PATHS):
        mode = "maintenance"
        message = _git(repository, "log", "-1", "--format=%B").stdout
        match = re.search(r"^Readiness-Source-Commit: ([0-9a-f]{40})$", message, re.MULTILINE)
        if match is None:
            raise SystemExit("READINESS_MAILBOX_MAINTENANCE_INVALID: enforcement sync lacks an exact source baseline")
        baseline = match.group(1)
    else:
        raise SystemExit("READINESS_MAILBOX_COMMIT_INVALID: mailbox commits must be a snapshot refresh or bounded enforcement sync")

    exists = _git(repository, "cat-file", "-e", f"{baseline}^{{commit}}", check=False)
    if exists.returncode != 0:
        raise SystemExit("READINESS_MAILBOX_BASELINE_INVALID: the verified repository commit is unavailable")

    for enforcement_path in MAILBOX_ENFORCEMENT_PATHS:
        mailbox_blob = _git(repository, "rev-parse", f"HEAD:{enforcement_path}", check=False)
        source_blob = _git(repository, "rev-parse", f"{baseline}:{enforcement_path}", check=False)
        if (
            mailbox_blob.returncode != 0
            or source_blob.returncode != 0
            or mailbox_blob.stdout.strip() != source_blob.stdout.strip()
        ):
            raise SystemExit("READINESS_MAILBOX_ENFORCEMENT_STALE: mailbox validation differs from the verified source baseline")

    print(json.dumps({"actual_snapshot": "passed", "enforcement_binding": "passed", "mailbox_commit_scope": "passed", "mode": mode}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
