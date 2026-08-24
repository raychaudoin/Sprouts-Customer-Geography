"""Repository-safe DATA-03 authority, provenance, and disclosure conformance."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


REQUIRED = (
    "governance/tasks/DATA-03.wisconsin-multivariate-acs-feature-source-expansion.task.json",
    "docs/work_orders/DATA_03_WISCONSIN_MULTIVARIATE_ACS_FEATURE_SOURCE_EXPANSION.md",
    "docs/DATA03_WISCONSIN_MULTIVARIATE_ACS_FEATURE_SOURCE.md",
    "config/data/data03_wisconsin_multivariate_acs_feature_source_contract.json",
    "schemas/data03/wisconsin_multivariate_acs_feature_source_contract.schema.json",
    "src/sprouts_customer_geography/data03/contract.py",
    "src/sprouts_customer_geography/data03/acquisition.py",
    "src/sprouts_customer_geography/data03/materialization.py",
    "tests/test_data03_source.py",
)


def main() -> int:
    repository = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repository / "src"))
    from sprouts_customer_geography.data03.contract import EXPECTED_MEASURE_IDS, EXPECTED_TABLE_IDS, load_contract, load_source_manifests
    from sprouts_customer_geography.governance import load_and_validate_task_manifest
    from sprouts_customer_geography.pipe01.safeguards import assert_no_protected_tracked_paths

    missing = [path for path in REQUIRED if not (repository / path).is_file()]
    if missing:
        raise SystemExit(f"DATA-03 required repository files absent: {missing}")
    task_manifests = list((repository / "governance" / "tasks").glob("DATA-03*.task.json"))
    work_orders = list((repository / "docs" / "work_orders").glob("DATA_03*.md"))
    if len(task_manifests) != 1 or len(work_orders) != 1:
        raise SystemExit(f"DATA-03 requires exactly one task manifest and one work order; found {len(task_manifests)} and {len(work_orders)}")
    task = load_and_validate_task_manifest(task_manifests[0], repository / "schemas/governance/task_manifest.schema.json")
    if task["task_id"] != "DATA-03" or task["capability_owner"] != "DATA Public Data Sources":
        raise SystemExit("DATA-03 task identity or Lane B capability owner differs")
    if task["state"] not in {"IN_PROGRESS", "COMPLETED_AWAITING_ACCEPTANCE", "ACCEPTED_CLOSED"}:
        raise SystemExit("DATA-03 task state is not executable or acceptance-bearing")
    if task["state"] == "COMPLETED_AWAITING_ACCEPTANCE" and (task["completion_state"]["execution"] != "COMPLETED" or task["completion_state"]["capability_acceptance"] != "NOT_REVIEWED"):
        raise SystemExit("DATA-03 H state does not await independent capability acceptance")

    contract = load_contract(repository)
    manifests = load_source_manifests(repository, contract)
    if tuple(manifests) != EXPECTED_TABLE_IDS or tuple(contract["output_contract"]["measure_order"]) != EXPECTED_MEASURE_IDS:
        raise SystemExit("DATA-03 table or candidate-measure allowlist differs")
    if len(list((repository / "data" / "manifests").glob("acs_2024_acs5_*_wisconsin_tract_data03.source_manifest.json"))) != 11:
        raise SystemExit("DATA-03 requires exactly 11 additive ACS table source manifests")
    source_manifest_schema = json.loads((repository / "schemas/pipe01/source_manifest.schema.json").read_text(encoding="utf-8"))
    allowed_manifest_fields = set(source_manifest_schema["properties"])
    required_manifest_fields = set(source_manifest_schema["required"])
    for table_id, manifest in manifests.items():
        if manifest.get("$schema") != "../../schemas/pipe01/source_manifest.schema.json":
            raise SystemExit(f"{table_id} does not reuse the accepted source-manifest schema")
        if set(manifest) - allowed_manifest_fields or not required_manifest_fields <= set(manifest):
            raise SystemExit(f"{table_id} manifest differs from the accepted source-manifest field contract")

    stageable = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    assert_no_protected_tracked_paths(stageable)
    forbidden_stageable = [path for path in stageable if path.replace("\\", "/").startswith(("data/raw/", "data/cache/", "outputs/")) or path.lower().endswith((".dat", ".parquet", ".duckdb"))]
    if forbidden_stageable:
        raise SystemExit(f"DATA-03 raw or generated data became stageable: {forbidden_stageable}")
    ignored = subprocess.run(
        ["git", "check-ignore", "--no-index", "data/raw/data03/example.dat", "outputs/data03/example.csv"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    if "data/raw/data03/example.dat" not in ignored or "outputs/data03/example.csv" not in ignored:
        raise SystemExit("DATA-03 raw/generated paths are not Git-ignored")

    variables = {variable["estimate_variable"] for table in contract["tables"] for variable in table["variables"]}
    forbidden_prefixes = ("B01001_", "B02001_", "B03003_", "B05001_", "B18101_")
    if any(variable.startswith(forbidden_prefixes) for variable in variables):
        raise SystemExit("DATA-03 protected-characteristic table entered the candidate menu")
    if any(measure.get("protected_characteristic_basis") is not False or measure.get("target_blind") is not True or measure.get("final_model_feature_authority") is not False for measure in contract["candidate_measures"]):
        raise SystemExit("DATA-03 candidate analytical boundary differs")

    print(json.dumps({
        "state": "passed",
        "contract_id": contract["artifact_id"],
        "table_count": len(manifests),
        "estimate_moe_pair_count": sum(len(table["variables"]) for table in contract["tables"]),
        "candidate_measure_count": len(contract["candidate_measures"]),
        "protected_characteristic_guard": "passed",
        "raw_git_exclusion": "passed",
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
