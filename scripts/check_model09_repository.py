"""Repository-safe MODEL-09 authority and disclosure conformance."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REQUIRED = (
    "governance/tasks/MODEL-09.wisconsin-full-cohort-experimental-model-development.task.json",
    "docs/work_orders/MODEL_09_WISCONSIN_FULL_COHORT_EXPERIMENTAL_MODEL_DEVELOPMENT.md",
    "docs/MODEL09_WISCONSIN_EXPERIMENTAL_DEVELOPMENT.md",
    "config/model/model09_wisconsin_experimental_model_contract.json",
    "schemas/model09/wisconsin_experimental_model_contract.schema.json",
    "schemas/model09/protected_handle_registry.schema.json",
    "schemas/model09/wisconsin_experimental_development_package.schema.json",
)


def main() -> int:
    repository = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repository / "src"))
    from sprouts_customer_geography.model09.development import CONTRACT_ID
    from sprouts_customer_geography.pipe01.safeguards import assert_no_protected_tracked_paths

    missing = [path for path in REQUIRED if not (repository / path).is_file()]
    if missing:
        raise SystemExit(f"MODEL-09 required repository files absent: {missing}")
    contract = json.loads((repository / REQUIRED[3]).read_text(encoding="utf-8"))
    if contract.get("artifact_id") != CONTRACT_ID or contract.get("version") != "1.0.0":
        raise SystemExit("MODEL-09 contract identity/version mismatch")
    candidates = contract.get("candidates")
    if not isinstance(candidates, list) or len(candidates) != 4 or len({item.get("candidate_id") for item in candidates}) != 4:
        raise SystemExit("MODEL-09 bounded candidate set differs")
    if contract.get("target", {}).get("allowed_field") != "Isolated Sales" or "Impacted Sales" not in contract.get("target", {}).get("denied_fields", []):
        raise SystemExit("MODEL-09 target allow/deny contract differs")
    if contract.get("development_diagnostics", {}).get("row_level_folding_denied") is not True:
        raise SystemExit("MODEL-09 physical-location leakage guard differs")
    if contract.get("development_diagnostics", {}).get("metric_weighting") != "aggregate actual and predicted levels to one mean pair per MODEL-10 physical location before metric calculation":
        raise SystemExit("MODEL-09 equal physical-location metric weighting differs")
    if "contributes total weight one" not in contract.get("development_diagnostics", {}).get("estimation_weighting", ""):
        raise SystemExit("MODEL-09 equal physical-location estimation weighting differs")
    if "excluding every physical-location group" not in contract.get("development_diagnostics", {}).get("market_sensitivity", ""):
        raise SystemExit("MODEL-09 market-holdout physical-location guard differs")
    if contract.get("output_semantics", {}).get("concepts_must_remain_separate") is not True:
        raise SystemExit("MODEL-09 output concept separation differs")
    stageable = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=repository, check=True, capture_output=True, text=True).stdout.splitlines()
    assert_no_protected_tracked_paths(stageable)
    public_text = "\n".join((repository / path).read_text(encoding="utf-8", errors="ignore") for path in stageable if (repository / path).is_file())
    forbidden = ("Sprouts" + "-Protected", "p4bind-model10" + "-wisconsin-v1", "m10run-wisconsin" + "-successor-v1")
    if any(value.lower() in public_text.lower() for value in forbidden):
        raise SystemExit("MODEL-09 protected-local execution detail entered stageable repository content")
    print(json.dumps({"state": "passed", "contract_id": CONTRACT_ID, "candidate_count": len(candidates), "target_scope": "Isolated Sales only", "protected_path_guard": "passed"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
