"""Rebind an explicitly fictional ignored MODEL-13 fixture after canary edits."""

from __future__ import annotations

import argparse
import csv
from hashlib import sha256
import json
from pathlib import Path
import shutil


FILES = (
    "model13_michigan_tract_scores.csv",
    "model13_michigan_seed_context.csv",
    "model13_michigan_power_bi_metadata.json",
    "READY.json",
)


def _sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def prepare_fixture(repository_root: Path, source: Path, target: Path, *, replace: bool = False) -> dict[str, object]:
    root = repository_root.resolve()
    allowed = (root / "powerbi" / "pbi01" / "local").resolve()
    source = source.resolve()
    target = target.resolve()
    if allowed not in source.parents or allowed not in target.parents:
        raise ValueError("synthetic fixture source and target must remain under ignored powerbi/pbi01/local")
    metadata = json.loads((source / FILES[2]).read_text(encoding="utf-8"))
    if metadata.get("model_lineage_id") != "fictional-model-lineage" or metadata.get("public_lineage_id") != "fictional-public-lineage":
        raise ValueError("source fixture is not explicitly fictional")
    if target.exists():
        if not replace:
            raise FileExistsError("synthetic fixture target exists; use --replace")
        if target.name != "pbi02-synthetic-validation":
            raise ValueError("refusing to replace an unexpected local directory")
        shutil.rmtree(target)
    target.mkdir(parents=True)
    with (source / FILES[0]).open("r", encoding="utf-8", newline="") as source_handle:
        reader = csv.DictReader(source_handle)
        if reader.fieldnames is None:
            raise ValueError("synthetic tract fixture has no header")
        rows = list(reader)
    sentinel_rows = [row for row in rows if row["computability_status"] == "PBI02_COLOR_CANARY_7F3A91"]
    if len(sentinel_rows) != 1:
        raise ValueError("synthetic tract fixture does not contain exactly one known canary sentinel row")
    sentinel = sentinel_rows[0]
    sentinel.update(
        {
            "computability_status": "MODEL_SCORE_COMPUTABLE",
            "support_truncation_3mi": "True",
            "support_truncation_5mi": "True",
            "support_truncation_7mi": "True",
            "any_support_truncation": "True",
            "qa_missingness_status": "OK",
            "model_lineage_id": "fictional-model-lineage",
            "public_lineage_id": "fictional-public-lineage",
        }
    )
    with (target / FILES[0]).open("w", encoding="utf-8", newline="") as target_handle:
        writer = csv.DictWriter(target_handle, fieldnames=reader.fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    shutil.copyfile(source / FILES[1], target / FILES[1])

    tract_hash = _sha(target / FILES[0])
    seed_hash = _sha(target / FILES[1])
    metadata["tract_output"]["byte_sha256"] = tract_hash
    metadata["seed_context_output"]["byte_sha256"] = seed_hash
    _write_json(target / FILES[2], metadata)
    ready = {
        "state": "ready",
        "finalization_state": "complete",
        "metadata_file_sha256": _sha(target / FILES[2]),
        "tract_csv_sha256": tract_hash,
        "seed_context_csv_sha256": seed_hash,
        "ready_marker_written_last": True,
    }
    _write_json(target / FILES[3], ready)
    return {
        "state": "READY",
        "synthetic_only": True,
        "tract_count": metadata["tract_output"]["row_count"],
        "seed_row_count": metadata["seed_context_output"]["row_count"],
        "protected_rows_written": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare a hash-bound fictional MODEL-13 fixture for ignored PBI-02 validation")
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    print(json.dumps(prepare_fixture(args.repository_root.resolve(), args.source, args.target, replace=args.replace), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
