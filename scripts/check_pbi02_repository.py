"""Repository-safe PBI-02 authority and fail-closed canary conformance."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


TASK_BRANCH = "task/pbi-02-michigan-map-first-scouting-public-context-redesign"
CAPABILITY_OWNER = "PBI: Power BI Decisions & Acceptance"
PBI01_ACCEPTED_BASE = "499cd611605380a3f2abca1e3e1d2f27cc56301c"
PBI01_MANIFEST_PATH = "governance/tasks/PBI-01.michigan-customer-geography-power-bi-mvp.task.json"
PBI01_MANIFEST_BLOB_ID = "23ecf6512e310d151ffdf1b43d555e13faab3efb"
REQUIRED = (
    "governance/tasks/PBI-02.michigan-map-first-scouting-public-context-redesign.task.json",
    "docs/work_orders/PBI_02_MICHIGAN_MAP_FIRST_SCOUTING_PUBLIC_CONTEXT_REDESIGN.md",
    "docs/pbi02/AZURE_MAPS_CANARY.md",
)


def main() -> int:
    repository = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repository / "src"))
    from sprouts_customer_geography.governance import load_and_validate_task_manifest
    from sprouts_customer_geography.pipe01.safeguards import assert_no_protected_tracked_paths

    missing = [path for path in REQUIRED if not (repository / path).is_file()]
    if missing:
        raise SystemExit(f"PBI-02 required repository files absent: {missing}")

    manifests = list((repository / "governance/tasks").glob("PBI-02*.task.json"))
    work_orders = list((repository / "docs/work_orders").glob("PBI_02*.md"))
    if (len(manifests), len(work_orders)) != (1, 1):
        raise SystemExit("PBI-02 requires exactly one task manifest and one work order")

    task = load_and_validate_task_manifest(
        manifests[0], repository / "schemas/governance/task_manifest.schema.json"
    )
    if (
        task["task_id"] != "PBI-02"
        or task["implementation_branch"] != TASK_BRANCH
        or task["capability_owner"] != CAPABILITY_OWNER
        or task["acceptance_destination"] != CAPABILITY_OWNER
        or task["exact_next_destination"] != CAPABILITY_OWNER
    ):
        raise SystemExit("PBI-02 identity, branch, or destination differs")
    posture = (
        task["state"],
        task["completion_state"]["execution"],
        task["completion_state"]["capability_acceptance"],
    )
    if posture != ("BLOCKED_FAIL_CLOSED", "BLOCKED", "NOT_REVIEWED"):
        raise SystemExit(f"PBI-02 fail-closed posture differs: {posture}")
    if task.get("implementation_commit") or task.get("acceptance_disposition") or task.get("acceptance_metadata"):
        raise SystemExit("PBI-02 blocker must not claim implementation H or acceptance")

    pbi01_blob_id = subprocess.run(
        ["git", "rev-parse", f"HEAD:{PBI01_MANIFEST_PATH}"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    pbi01_diff = subprocess.run(
        ["git", "diff", "--quiet", PBI01_ACCEPTED_BASE, "--", PBI01_MANIFEST_PATH],
        cwd=repository,
        check=False,
    ).returncode
    if pbi01_blob_id != PBI01_MANIFEST_BLOB_ID or pbi01_diff != 0:
        raise SystemExit("PBI-01 accepted manifest bytes changed")

    canary = (repository / "docs/pbi02/AZURE_MAPS_CANARY.md").read_text(encoding="utf-8")
    required_canary = (
        "BLOCKED_FAIL_CLOSED",
        "SYNTHETIC_ONLY",
        "To display Azure Maps visuals, sign in.",
        "Protected MODEL-13 values",
        "never connected to Azure Maps",
        "outbound-request inspection remains required",
    )
    if any(value not in canary for value in required_canary):
        raise SystemExit("PBI-02 canary blocker evidence is incomplete")
    if "canary is **not established**" not in canary:
        raise SystemExit("PBI-02 must not imply the canary passed")

    stageable = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    assert_no_protected_tracked_paths(stageable)
    normalized = [path.replace("\\", "/") for path in stageable]
    forbidden = [
        path for path in normalized
        if path.startswith(("powerbi/pbi01/local/", "powerbi/pbi01/runtime/"))
        or path.lower().endswith((".pbix", ".pbit", ".pcap", ".pcapng", ".har"))
    ]
    if forbidden:
        raise SystemExit(f"PBI-02 local/protected artifacts became stageable: {forbidden}")

    workflow = (repository / ".github/workflows/repository-validation.yml").read_text(encoding="utf-8")
    if "python scripts/check_pbi02_repository.py" not in workflow:
        raise SystemExit("PBI-02 checker is absent from Repository Validation")

    print(json.dumps({
        "state": "passed",
        "task_posture": posture,
        "azure_maps_access": "BLOCKED_SIGN_IN_REQUIRED",
        "synthetic_only": True,
        "protected_values_connected_to_azure_maps": False,
        "pbi01_acceptance_history_unchanged": True,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
