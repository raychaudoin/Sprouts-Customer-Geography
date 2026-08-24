"""Repository-safe MODEL-11 authority, scope, and disclosure conformance."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REQUIRED = (
    "governance/tasks/MODEL-11.multivariate-wisconsin-customer-fit-model-development.task.json",
    "docs/work_orders/MODEL_11_MULTIVARIATE_WISCONSIN_CUSTOMER_FIT_MODEL_DEVELOPMENT.md",
    "docs/MODEL11_WISCONSIN_MULTIVARIATE_DEVELOPMENT.md",
    "config/model/model11_wisconsin_multivariate_model_contract.json",
    "schemas/model11/wisconsin_multivariate_model_contract.schema.json",
    "schemas/model11/protected_handle_registry.schema.json",
    "schemas/model11/target_blind_feature_freeze_package.schema.json",
    "schemas/model11/wisconsin_multivariate_development_package.schema.json",
)


def main() -> int:
    repository = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repository / "src"))
    from sprouts_customer_geography.model11.features import CONTRACT_ID, verify_repository_authority
    from sprouts_customer_geography.pipe01.safeguards import assert_no_protected_tracked_paths

    missing = [path for path in REQUIRED if not (repository / path).is_file()]
    if missing:
        raise SystemExit(f"MODEL-11 required repository files absent: {missing}")
    contract = verify_repository_authority(repository)
    if contract.get("artifact_id") != CONTRACT_ID or len(contract.get("candidate_measures", [])) != 13 or len(contract.get("candidates", [])) != 3:
        raise SystemExit("MODEL-11 exact contract identity/menu/candidate bound differs")
    if contract.get("target", {}).get("allowed_field") != "Isolated Sales" or "Impacted Sales" not in contract.get("target", {}).get("denied_fields", []):
        raise SystemExit("MODEL-11 Isolated Sales allow/deny boundary differs")
    if contract.get("phase1_feature_freeze", {}).get("target_access_permitted") is not False or contract.get("protected_execution", {}).get("feature_freeze_precedes_target_access") is not True:
        raise SystemExit("MODEL-11 target-blind freeze boundary differs")
    if contract.get("development_diagnostics", {}).get("nested_tuning_required") is not True or contract.get("development_diagnostics", {}).get("row_level_folding_denied") is not True:
        raise SystemExit("MODEL-11 nested grouped diagnostic boundary differs")
    if contract.get("development_diagnostics", {}).get("market_and_vintage_predictors_denied") is not True:
        raise SystemExit("MODEL-11 market/vintage predictor denial differs")
    if contract.get("selection", {}).get("minimum_spearman_improvement_over_reference") != 0.03 or contract.get("selection", {}).get("maximum_log_rmse_ratio_to_reference") != 1.05:
        raise SystemExit("MODEL-11 fixed selection gate differs")
    stageable = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=repository, check=True, capture_output=True, text=True).stdout.splitlines()
    assert_no_protected_tracked_paths(stageable)
    public_text = "\n".join((repository / path).read_text(encoding="utf-8", errors="ignore") for path in stageable if (repository / path).is_file())
    forbidden = ("p4bind-model10" + "-wisconsin-v1", "m10run-wisconsin" + "-successor-v1", "m09run-wisconsin" + "-full-cohort")
    if any(value.lower() in public_text.lower() for value in forbidden):
        raise SystemExit("MODEL-11 protected-local execution detail entered stageable repository content")
    print(json.dumps({"state": "passed", "contract_id": CONTRACT_ID, "candidate_measure_count": 13, "candidate_count": 3, "target_scope": "Isolated Sales only", "protected_path_guard": "passed"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
