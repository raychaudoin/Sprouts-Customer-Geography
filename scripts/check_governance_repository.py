"""Repository-safe GOV-02 manifest, schema, and tracked-path conformance check."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def main() -> int:
    repository = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repository / "src"))
    from sprouts_customer_geography.governance import load_and_validate_task_manifest
    from sprouts_customer_geography.pipe01.safeguards import assert_no_protected_tracked_paths

    schema = repository / "schemas" / "governance" / "task_manifest.schema.json"
    manifests = sorted((repository / "governance" / "tasks").glob("*.task.json"))
    if not manifests:
        raise SystemExit("no governance task manifests found")
    documents = [load_and_validate_task_manifest(manifest, schema) for manifest in manifests]
    stageable = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    assert_no_protected_tracked_paths(stageable)
    print(json.dumps({"state": "passed", "task_ids": [document["task_id"] for document in documents], "tracked_path_safeguard": "passed"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
