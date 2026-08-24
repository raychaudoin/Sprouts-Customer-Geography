"""Repository-safe GEO-05 Michigan statewide spatial conformance."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


REQUIRED = (
    "governance/tasks/GEO-05.michigan-statewide-geography-enablement.task.json",
    "docs/work_orders/GEO_05_MICHIGAN_STATEWIDE_GEOGRAPHY_ENABLEMENT.md",
    "docs/GEO05_MICHIGAN_STATEWIDE_GEOGRAPHY_ENABLEMENT.md",
    "config/geo/geo05_michigan_statewide_spatial_support_spec.json",
    "schemas/geo05/michigan_statewide_spatial_support_spec.schema.json",
    "schemas/geo05/anchor_spatial_evidence.schema.json",
    "schemas/geo05/spatial_support_materialization_report.schema.json",
    "src/sprouts_customer_geography/geo05/contract.py",
    "src/sprouts_customer_geography/geo05/materialization.py",
    "src/sprouts_customer_geography/geo05/cli.py",
    "tests/test_geo05_spatial_support.py",
)
AUTHORIZATION_BASE = "431e2f2a1aefcf877b7312bd4e7d16dccecb3da5"


def main() -> int:
    repository = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repository / "src"))
    from sprouts_customer_geography.geo05.contract import EXPECTED_INVENTORY_SHA256, EXPECTED_TRACT_COUNT, load_authority
    from sprouts_customer_geography.governance import load_and_validate_task_manifest
    from sprouts_customer_geography.pipe01.safeguards import assert_no_protected_tracked_paths

    missing = [path for path in REQUIRED if not (repository / path).is_file()]
    if missing:
        raise SystemExit(f"GEO-05 required repository files absent: {missing}")
    manifests = list((repository / "governance" / "tasks").glob("GEO-05*.task.json"))
    work_orders = list((repository / "docs" / "work_orders").glob("GEO_05*.md"))
    if len(manifests) != 1 or len(work_orders) != 1:
        raise SystemExit(f"GEO-05 requires exactly one task manifest and one work order; found {len(manifests)} and {len(work_orders)}")
    task = load_and_validate_task_manifest(manifests[0], repository / "schemas/governance/task_manifest.schema.json")
    if task["task_id"] != "GEO-05" or task["capability_owner"] != "GEO Decisions Acceptance":
        raise SystemExit("GEO-05 task identity or capability owner differs")
    if task["implementation_branch"] != "task/geo-05-michigan-statewide-geography-enablement":
        raise SystemExit("GEO-05 branch identity differs")
    allowed_states = {
        ("IN_PROGRESS", "IN_PROGRESS", "NOT_REVIEWED"),
        ("COMPLETED_AWAITING_ACCEPTANCE", "COMPLETED", "NOT_REVIEWED"),
        ("ACCEPTED_CLOSED", "COMPLETED", "ACCEPTED"),
    }
    posture = (task["state"], task["completion_state"]["execution"], task["completion_state"]["capability_acceptance"])
    if posture not in allowed_states:
        raise SystemExit(f"GEO-05 task posture is not executable or acceptance-bearing: {posture}")

    authority = load_authority(repository)
    specification = authority.specification
    if specification["state_scope"]["state_fips"] != "26" or specification["state_scope"]["tract_count"] != EXPECTED_TRACT_COUNT:
        raise SystemExit("GEO-05 Michigan statewide scope differs")
    if specification["statewide_inventory"]["inventory_sha256"] != EXPECTED_INVENTORY_SHA256 or specification["statewide_inventory"]["market_inventory"] is not False:
        raise SystemExit("GEO-05 statewide inventory identity or no-market boundary differs")
    if specification["geo03_methodology"]["operation_fingerprint_sha256"] != authority.geo03["transformation"]["operation_fingerprint_sha256"]:
        raise SystemExit("GEO-05 GEO-03 operation fingerprint differs")
    if tuple(specification["model_downstream_compatibility"]["radii_m"]) != (4828.032, 8046.72, 11265.408):
        raise SystemExit("GEO-05 MODEL-owned 3/5/7-mile radii differ")
    if specification["support_completeness_qa"]["threshold"] is not None or specification["support_completeness_qa"]["automatic_rejection"] is not False:
        raise SystemExit("GEO-05 invented a support-completeness threshold or rejection rule")
    if specification["protected_evidence_boundary"]["public_data_only"] is not True or specification["protected_evidence_boundary"]["protected_dependencies"]:
        raise SystemExit("GEO-05 public-only protected boundary differs")

    accepted_paths = [
        "config/geo/geo02_validation_context_spatial_spec.json",
        "config/geo/geo03_internal_point_membership_spatial_spec.json",
        "config/geo/canonical_tract_inventory_derivation.json",
        "config/geo/canonical_tract_inventory_milwaukee.json",
        "config/geo/canonical_tract_inventory_madison.json",
        "src/sprouts_customer_geography/pipe01/production.py",
        "src/sprouts_customer_geography/model09/features.py",
        "src/sprouts_customer_geography/model11/features.py",
    ]
    changed_accepted = subprocess.run(["git", "diff", "--name-only", AUTHORIZATION_BASE, "--", *accepted_paths], cwd=repository, check=True, capture_output=True, text=True).stdout.splitlines()
    if changed_accepted:
        raise SystemExit(f"GEO-05 changed accepted Wisconsin GEO/MODEL public spatial behavior: {changed_accepted}")

    michigan_market_paths = [path.as_posix() for path in (repository / "config" / "markets").glob("*") if "michigan" in path.name.lower()]
    michigan_market_paths.extend(path.as_posix() for path in (repository / "config" / "geo").glob("*canonical*inventory*michigan*"))
    if michigan_market_paths:
        raise SystemExit(f"GEO-05 created a prohibited Michigan market inventory: {michigan_market_paths}")

    stageable = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=repository, check=True, capture_output=True, text=True).stdout.splitlines()
    assert_no_protected_tracked_paths(stageable)
    forbidden = [
        path
        for path in stageable
        if path.replace("\\", "/").startswith(("data/raw/", "data/cache/", "data/local/", "outputs/"))
        or path.lower().endswith((".zip", ".shp", ".dbf", ".shx", ".wkb", ".parquet", ".duckdb"))
    ]
    if forbidden:
        raise SystemExit(f"GEO-05 raw, bulk geometry, or generated data became stageable: {forbidden}")
    ignored = subprocess.run(["git", "check-ignore", "--no-index", "data/raw/data04/example.zip", "outputs/geo05/example.wkb"], cwd=repository, check=True, capture_output=True, text=True).stdout
    if not all(path in ignored for path in ("data/raw/data04/example.zip", "outputs/geo05/example.wkb")):
        raise SystemExit("GEO-05 raw/generated paths are not Git-ignored")

    print(
        json.dumps(
            {
                "state": "passed",
                "spatial_spec_id": specification["artifact_id"],
                "state_fips": "26",
                "tract_count": EXPECTED_TRACT_COUNT,
                "inventory_sha256": EXPECTED_INVENTORY_SHA256,
                "geo03_operation_fingerprint": specification["geo03_methodology"]["operation_fingerprint_sha256"],
                "support_completeness_qa": "no_threshold",
                "accepted_wisconsin_behavior_unchanged": True,
                "protected_boundary": "passed",
                "raw_git_exclusion": "passed",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
