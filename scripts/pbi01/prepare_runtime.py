from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys


TRACT_TOKEN = "__PBI01_TRACT_CSV__"
SEED_TOKEN = "__PBI01_SEED_CSV__"


def _safe_remove_runtime(repository_root: Path, target: Path) -> None:
    allowed = (repository_root / "powerbi" / "pbi01" / "runtime").resolve()
    resolved = target.resolve()
    if allowed not in resolved.parents or target.name != "run":
        raise ValueError("refusing to replace a directory outside the governed PBI-01 runtime surface")
    shutil.rmtree(resolved)


def prepare_runtime(repository_root: Path, *, replace: bool = False) -> dict[str, object]:
    root = repository_root.resolve()
    sys.path.insert(0, str(root / "src"))
    from sprouts_customer_geography.pbi01.preflight import standard_local_paths, validate_model13_inputs

    preflight = validate_model13_inputs(root)
    paths = standard_local_paths(root)
    source = root / "powerbi" / "pbi01" / "project"
    target = root / "powerbi" / "pbi01" / "runtime" / "run"
    if target.exists():
        if not replace:
            raise FileExistsError("PBI-01 runtime copy exists; use --replace for a deterministic rebuild")
        _safe_remove_runtime(root, target)
    shutil.copytree(
        source,
        target,
        ignore=shutil.ignore_patterns("*.pbix", "*.pbit", ".pbi", "*.tmp", "~$*"),
    )

    replacements = {
        target / "MICustomerGeography.SemanticModel" / "definition" / "tables" / "Michigan Tracts.tmdl": (TRACT_TOKEN, paths["tract"].resolve().as_posix()),
        target / "MICustomerGeography.SemanticModel" / "definition" / "tables" / "Seed Context.tmdl": (SEED_TOKEN, paths["seed"].resolve().as_posix()),
    }
    for path, (token, value) in replacements.items():
        text = path.read_text(encoding="utf-8")
        if text.count(token) != 1:
            raise ValueError("tracked TMDL local-path token is absent or duplicated")
        path.write_text(text.replace(token, value), encoding="utf-8")

    remaining = []
    for path in target.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".tmdl", ".json", ".pbir", ".pbip"}:
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeError:
                continue
            if TRACT_TOKEN in text or SEED_TOKEN in text:
                remaining.append(path)
    if remaining:
        raise ValueError("runtime project still contains unresolved local-path tokens")

    return {
        "state": "READY",
        "preflight_state": preflight.state,
        "tract_count": preflight.tract_count,
        "geometry_geoid_count": preflight.geometry_geoid_count,
        "seed_context_ready": preflight.seed_context_ready,
        "runtime_pbip": "powerbi/pbi01/runtime/run/MICustomerGeography.pbip",
        "tracked_project_contains_protected_paths": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare the ignored local PBI-01 Desktop runtime project")
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    print(json.dumps(prepare_runtime(args.repository_root.resolve(), replace=args.replace), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
