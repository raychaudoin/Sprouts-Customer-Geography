from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys
from typing import Mapping


TRACT_TOKEN = "__PBI01_TRACT_CSV__"
SEED_TOKEN = "__PBI01_SEED_CSV__"
PUBLIC_CONTEXT_TOKEN = "__PBI02_PUBLIC_CONTEXT_CSV__"
MODEL13_FILENAMES = {
    "tract": "model13_michigan_tract_scores.csv",
    "seed": "model13_michigan_seed_context.csv",
    "metadata": "model13_michigan_power_bi_metadata.json",
    "ready": "READY.json",
}


def _safe_remove_runtime(repository_root: Path, target: Path) -> None:
    allowed = (repository_root / "powerbi" / "pbi01" / "runtime").resolve()
    resolved = target.resolve()
    if allowed not in resolved.parents or target.name != "pbi02-run":
        raise ValueError("refusing to replace a directory outside the governed PBI-02 runtime surface")
    shutil.rmtree(resolved)


def _model13_paths(model13_root: Path) -> dict[str, Path]:
    return {key: model13_root / filename for key, filename in MODEL13_FILENAMES.items()}


def prepare_runtime(
    repository_root: Path,
    *,
    replace: bool = False,
    model13_root: Path | None = None,
    data04_root: Path | None = None,
) -> dict[str, object]:
    root = repository_root.resolve()
    sys.path.insert(0, str(root / "src"))
    from sprouts_customer_geography.pbi01.preflight import standard_local_paths
    from sprouts_customer_geography.pbi02.preflight import discover_data04_root, validate_pbi02_inputs

    model13_paths: Mapping[str, Path] = _model13_paths(model13_root.resolve()) if model13_root else standard_local_paths(root)
    resolved_data04_root = data04_root.resolve() if data04_root else discover_data04_root(root)
    preflight = validate_pbi02_inputs(
        root,
        model13_paths=model13_paths,
        data04_root=resolved_data04_root,
    )

    source = root / "powerbi" / "pbi01" / "project"
    target = root / "powerbi" / "pbi01" / "runtime" / "pbi02-run"
    if target.exists():
        if not replace:
            raise FileExistsError("PBI-02 runtime copy exists; use --replace for a deterministic rebuild")
        _safe_remove_runtime(root, target)
    shutil.copytree(
        source,
        target,
        ignore=shutil.ignore_patterns("*.pbix", "*.pbit", ".pbi", "*.tmp", "~$*"),
    )

    table_root = target / "MICustomerGeography.SemanticModel" / "definition" / "tables"
    replacements = {
        table_root / "Michigan Tracts.tmdl": (TRACT_TOKEN, model13_paths["tract"].resolve().as_posix()),
        table_root / "Seed Context.tmdl": (SEED_TOKEN, model13_paths["seed"].resolve().as_posix()),
        table_root / "Michigan Public Context.tmdl": (
            PUBLIC_CONTEXT_TOKEN,
            (resolved_data04_root / "multivariate" / "michigan_tract_candidate_measures.csv").resolve().as_posix(),
        ),
    }
    for path, (token, value) in replacements.items():
        text = path.read_text(encoding="utf-8")
        if text.count(token) != 1:
            raise ValueError(f"tracked TMDL token is absent or duplicated: {token}")
        path.write_text(text.replace(token, value), encoding="utf-8")

    unresolved: list[str] = []
    for path in target.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".tmdl", ".json", ".pbir", ".pbip", ".pbism"}:
            text = path.read_text(encoding="utf-8", errors="ignore")
            if any(token in text for token in (TRACT_TOKEN, SEED_TOKEN, PUBLIC_CONTEXT_TOKEN)):
                unresolved.append(path.relative_to(target).as_posix())
    if unresolved:
        raise ValueError(f"runtime project still contains unresolved local-path tokens: {unresolved}")

    return {
        "state": "READY",
        "preflight_state": preflight.state,
        "tract_count": preflight.tract_count,
        "public_context_unique_geoid_count": preflight.public_context_unique_geoid_count,
        "geometry_unique_geoid_count": preflight.geometry_unique_geoid_count,
        "one_to_one_relationship_eligible": preflight.one_to_one_relationship_eligible,
        "runtime_pbip": "powerbi/pbi01/runtime/pbi02-run/MICustomerGeography.pbip",
        "tracked_project_contains_local_paths": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare the ignored local PBI-02 Desktop runtime project")
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--replace", action="store_true")
    parser.add_argument("--model13-root", type=Path)
    parser.add_argument("--data04-root", type=Path)
    args = parser.parse_args()
    print(
        json.dumps(
            prepare_runtime(
                args.repository_root.resolve(),
                replace=args.replace,
                model13_root=args.model13_root,
                data04_root=args.data04_root,
            ),
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
