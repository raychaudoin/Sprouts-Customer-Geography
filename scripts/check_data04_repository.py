"""Repository-safe DATA-04 Michigan parity authority and disclosure conformance."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


REQUIRED = (
    "governance/tasks/DATA-04.michigan-public-data-parity-foundation.task.json",
    "docs/work_orders/DATA_04_MICHIGAN_PUBLIC_DATA_PARITY_FOUNDATION.md",
    "docs/DATA04_MICHIGAN_PUBLIC_DATA_PARITY_FOUNDATION.md",
    "config/data/data04_michigan_public_data_parity_source_contract.json",
    "data/manifests/tiger_2024_michigan_tract.source_manifest.json",
    "schemas/data04/michigan_public_data_parity_source_contract.schema.json",
    "schemas/data04/michigan_b11001_tract_evidence.schema.json",
    "schemas/data04/michigan_tiger_tract_evidence.schema.json",
    "schemas/data04/michigan_public_data_materialization_report.schema.json",
    "src/sprouts_customer_geography/data04/contract.py",
    "src/sprouts_customer_geography/data04/acquisition.py",
    "src/sprouts_customer_geography/data04/materialization.py",
    "tests/test_data04_source.py",
)
AUTHORIZATION_BASE = "0b0027691905e908990212ee7f5133454ab47b24"


def main() -> int:
    repository = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repository / "src"))
    from sprouts_customer_geography.data03.contract import EXPECTED_MEASURE_IDS, EXPECTED_TABLE_IDS
    from sprouts_customer_geography.data04.contract import EXPECTED_TRACT_COUNT, load_authority
    from sprouts_customer_geography.governance import load_and_validate_task_manifest
    from sprouts_customer_geography.pipe01.safeguards import assert_no_protected_tracked_paths

    missing = [path for path in REQUIRED if not (repository / path).is_file()]
    if missing:
        raise SystemExit(f"DATA-04 required repository files absent: {missing}")
    manifests = list((repository / "governance" / "tasks").glob("DATA-04*.task.json"))
    work_orders = list((repository / "docs" / "work_orders").glob("DATA_04*.md"))
    if len(manifests) != 1 or len(work_orders) != 1:
        raise SystemExit(f"DATA-04 requires exactly one task manifest and one work order; found {len(manifests)} and {len(work_orders)}")
    task = load_and_validate_task_manifest(manifests[0], repository / "schemas/governance/task_manifest.schema.json")
    if task["task_id"] != "DATA-04" or task["capability_owner"] != "DATA Public Data Sources":
        raise SystemExit("DATA-04 task identity or capability owner differs")
    if task["state"] not in {"IN_PROGRESS", "COMPLETED_AWAITING_ACCEPTANCE", "ACCEPTED_CLOSED"}:
        raise SystemExit("DATA-04 task state is not executable or acceptance-bearing")
    if task["state"] == "COMPLETED_AWAITING_ACCEPTANCE" and (task["completion_state"]["execution"] != "COMPLETED" or task["completion_state"]["capability_acceptance"] != "NOT_REVIEWED"):
        raise SystemExit("DATA-04 H state does not await independent DATA acceptance")

    authority = load_authority(repository)
    if authority.contract["state_scope"]["observed_tract_count"] != EXPECTED_TRACT_COUNT:
        raise SystemExit("DATA-04 Michigan tract count differs")
    if tuple(table["table_id"] for table in authority.data03_contract["tables"]) != EXPECTED_TABLE_IDS:
        raise SystemExit("DATA-04 accepted DATA-03 table identity differs")
    if tuple(measure["measure_id"] for measure in authority.data03_contract["candidate_measures"]) != EXPECTED_MEASURE_IDS:
        raise SystemExit("DATA-04 accepted DATA-03 measure identity differs")

    accepted_paths = [
        "config/data/data01_validation_source_contract.json",
        "config/data/data03_wisconsin_multivariate_acs_feature_source_contract.json",
        "data/manifests/acs_2024_acs5_b11001_wisconsin_tract.source_manifest.json",
        "data/manifests/tiger_2024_wisconsin_tract.source_manifest.json",
        *[reference["manifest_path"] for reference in authority.contract["accepted_acs_national_authority"]["multivariate_tables"]],
    ]
    changed_accepted = subprocess.run(["git", "diff", "--name-only", AUTHORIZATION_BASE, "--", *accepted_paths], cwd=repository, check=True, capture_output=True, text=True).stdout.splitlines()
    if changed_accepted:
        raise SystemExit(f"DATA-04 changed accepted Wisconsin contracts/manifests: {changed_accepted}")

    stageable = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=repository, check=True, capture_output=True, text=True).stdout.splitlines()
    assert_no_protected_tracked_paths(stageable)
    forbidden = [path for path in stageable if path.replace("\\", "/").startswith(("data/raw/", "data/cache/", "data/local/", "outputs/")) or path.lower().endswith((".dat", ".parquet", ".duckdb", ".shp", ".dbf"))]
    if forbidden:
        raise SystemExit(f"DATA-04 raw or generated data became stageable: {forbidden}")
    ignored = subprocess.run(["git", "check-ignore", "--no-index", "data/raw/data04/example.zip", "data/local/example.dat", "outputs/data04/example.csv"], cwd=repository, check=True, capture_output=True, text=True).stdout
    if not all(path in ignored for path in ("data/raw/data04/example.zip", "data/local/example.dat", "outputs/data04/example.csv")):
        raise SystemExit("DATA-04 raw/generated paths are not Git-ignored")

    variables = {variable["estimate_variable"] for table in authority.data03_contract["tables"] for variable in table["variables"]}
    if any(variable.startswith(("B01001_", "B02001_", "B03003_", "B05001_", "B18101_")) for variable in variables):
        raise SystemExit("DATA-04 protected-characteristic table entered the source menu")
    if authority.contract["protected_evidence_boundary"]["public_data_only"] is not True:
        raise SystemExit("DATA-04 public-data-only boundary differs")

    print(json.dumps({
        "state": "passed",
        "contract_id": authority.contract["artifact_id"],
        "state_fips": "26",
        "tract_count": EXPECTED_TRACT_COUNT,
        "household_source": "B11001",
        "multivariate_table_count": len(authority.multivariate_manifests),
        "component_pair_count": 22,
        "candidate_measure_count": 13,
        "accepted_wisconsin_authority_unchanged": True,
        "protected_boundary": "passed",
        "raw_git_exclusion": "passed",
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
