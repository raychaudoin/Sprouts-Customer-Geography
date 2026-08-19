"""Repository-safe PIPE-01 structural conformance check."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REQUIRED_SCHEMAS = {
    "source_manifest",
    "tract_inventory",
    "tract_internal_point_evidence",
    "context_membership",
    "context_spatial_evidence",
    "acs_b11001_evidence",
    "household_opportunity",
    "baseline_prediction",
    "eligibility_readiness",
    "run_manifest",
    "freeze_manifest",
    "conformance_report",
}


def main() -> int:
    repository = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repository / "src"))
    from sprouts_customer_geography.pipe01.safeguards import assert_no_protected_tracked_paths

    schemas = repository / "schemas" / "pipe01"
    found: set[str] = set()
    for path in sorted(schemas.glob("*.schema.json")):
        with path.open("r", encoding="utf-8") as handle:
            document = json.load(handle)
        if document.get("title"):
            found.add(path.name.removesuffix(".schema.json"))
        if document.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
            raise SystemExit(f"invalid schema declaration: {path}")
    missing = sorted(REQUIRED_SCHEMAS - found)
    if missing:
        raise SystemExit(f"missing PIPE-01 schemas: {missing}")
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=repository, check=True, capture_output=True, text=True
    ).stdout.splitlines()
    assert_no_protected_tracked_paths(tracked)
    print(json.dumps({"state": "passed", "schema_count": len(found), "tracked_path_safeguard": "passed"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
