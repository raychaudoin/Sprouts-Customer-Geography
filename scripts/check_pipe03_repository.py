"""Repository-safe PIPE-03 schema, source, and tracked-path guard."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def main() -> int:
    repository = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repository / "src"))
    from sprouts_customer_geography.pipe01.safeguards import (
        assert_no_protected_tracked_paths,
    )

    schemas = repository / "schemas" / "pipe03"
    expected = {
        "protected_handle_registry.schema.json",
        "wisconsin_development_target_access_binding.schema.json",
    }
    found = {path.name for path in schemas.glob("*.schema.json")}
    if found != expected:
        raise SystemExit(f"PIPE-03 schema inventory mismatch: {sorted(found)}")
    for path in schemas.glob("*.schema.json"):
        document = json.loads(path.read_text(encoding="utf-8"))
        if document.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
            raise SystemExit(f"invalid schema declaration: {path.name}")

    resolver_source = (
        repository / "src/sprouts_customer_geography/pipe03/resolver.py"
    ).read_text(encoding="utf-8").lower()
    prohibited_discovery = (".glob(", ".rglob(", ".iterdir(", "os.walk(")
    used = [operation for operation in prohibited_discovery if operation in resolver_source]
    if used:
        raise SystemExit(f"PIPE-03 resolver contains discovery operation(s): {used}")

    stageable = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    assert_no_protected_tracked_paths(stageable)
    print(
        json.dumps(
            {
                "state": "passed",
                "schema_count": len(found),
                "explicit_handle_only": True,
                "tracked_path_safeguard": "passed",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
