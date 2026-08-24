"""Repository-safe MODEL-13 authority, execution, and disclosure conformance."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import re
import subprocess
import sys


AUTHORIZATION_BASE = "04a85783ef3f09c82cb0c38c79c225da888f3eb9"
COMMITMENT_PATH = "config/model/model13_execution_commitment.json"
REQUIRED = (
    "governance/tasks/MODEL-13.michigan-benchmark-pooled-successor-statewide-scoring.task.json",
    "docs/work_orders/MODEL_13_MICHIGAN_BENCHMARK_POOLED_SUCCESSOR_STATEWIDE_SCORING.md",
    "config/model/model13_michigan_benchmark_pooled_successor_statewide_scoring_contract.json",
    "config/model/model13_michigan_power_bi_output_contract.json",
    "schemas/model13/execution_commitment.schema.json",
    "schemas/model13/michigan_benchmark_pooled_successor_statewide_scoring_contract.schema.json",
    "schemas/model13/michigan_power_bi_output_contract.schema.json",
    "schemas/model13/protected_handle_registry.schema.json",
    "schemas/model13/michigan_frozen_benchmark_package.schema.json",
    "schemas/model13/combined_target_blind_feature_freeze_package.schema.json",
    "schemas/model13/pooled_successor_development_package.schema.json",
    "schemas/model13/michigan_statewide_tract_scoring_package.schema.json",
    "schemas/model13/michigan_power_bi_metadata.schema.json",
    "src/sprouts_customer_geography/model13/resolver.py",
    "src/sprouts_customer_geography/model13/registry_bootstrap.py",
    "src/sprouts_customer_geography/model13/modeling.py",
    "src/sprouts_customer_geography/model13/workflow.py",
    "src/sprouts_customer_geography/model13/cli.py",
    "tests/test_model13_workflow.py",
)
EXPECTED_SCHEMAS = {
    "combined_target_blind_feature_freeze_package.schema.json",
    "execution_commitment.schema.json",
    "michigan_benchmark_pooled_successor_statewide_scoring_contract.schema.json",
    "michigan_frozen_benchmark_package.schema.json",
    "michigan_power_bi_metadata.schema.json",
    "michigan_power_bi_output_contract.schema.json",
    "michigan_statewide_tract_scoring_package.schema.json",
    "pooled_successor_development_package.schema.json",
    "protected_handle_registry.schema.json",
}
CANDIDATE_IDS = [
    "successor_spatial_reference",
    "successor_model11_termset_elastic_net",
    "successor_combined_multivariate_ridge",
    "successor_combined_multivariate_elastic_net",
]


def _load(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SystemExit(f"MODEL-13 repository JSON is unreadable: {path.name}") from exc
    if not isinstance(value, dict):
        raise SystemExit(f"MODEL-13 repository JSON must be an object: {path.name}")
    return value


def main() -> int:
    repository = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repository / "src"))
    from sprouts_customer_geography.governance import load_and_validate_task_manifest
    from sprouts_customer_geography.model13.workflow import CONTRACT_ID, OUTPUT_CONTRACT_ID, verify_repository_authority
    from sprouts_customer_geography.pipe01.canonical import content_digest
    from sprouts_customer_geography.pipe01.safeguards import assert_no_protected_tracked_paths

    missing = [path for path in REQUIRED if not (repository / path).is_file()]
    if missing:
        raise SystemExit(f"MODEL-13 required repository files absent: {missing}")
    manifests = list((repository / "governance/tasks").glob("MODEL-13*.task.json"))
    work_orders = list((repository / "docs/work_orders").glob("MODEL_13*.md"))
    if len(manifests) != 1 or len(work_orders) != 1:
        raise SystemExit(f"MODEL-13 requires exactly one task manifest and one work order; found {len(manifests)} and {len(work_orders)}")
    task = load_and_validate_task_manifest(manifests[0], repository / "schemas/governance/task_manifest.schema.json")
    if task["task_id"] != "MODEL-13" or task["capability_owner"] != "MODEL: Customer-Fit Proxy Decisions & Acceptance":
        raise SystemExit("MODEL-13 task identity or capability owner differs")
    if task["implementation_branch"] != "task/model-13-michigan-benchmark-pooled-successor-statewide-scoring":
        raise SystemExit("MODEL-13 implementation branch differs")
    posture = (task["state"], task["completion_state"]["execution"], task["completion_state"]["capability_acceptance"])
    if posture not in {
        ("IN_PROGRESS", "IN_PROGRESS", "NOT_REVIEWED"),
        ("COMPLETED_AWAITING_ACCEPTANCE", "COMPLETED", "NOT_REVIEWED"),
        ("ACCEPTED_CLOSED", "COMPLETED", "ACCEPTED"),
    }:
        raise SystemExit(f"MODEL-13 task posture is invalid: {posture}")

    contract, output = verify_repository_authority(repository)
    if contract["artifact_id"] != CONTRACT_ID or output["artifact_id"] != OUTPUT_CONTRACT_ID:
        raise SystemExit("MODEL-13 contract identity differs")
    if contract["canonical_main_at_authorization"] != AUTHORIZATION_BASE:
        raise SystemExit("MODEL-13 authorization base differs")
    if contract["combined_cohort"] != {
        "wisconsin": {"observation_count": 63, "physical_location_count": 41, "target": "Isolated Sales"},
        "michigan": {"observation_count": 138, "physical_location_count": 85, "target": "Isolated Sales"},
        "pooled": {"observation_count": 201, "physical_location_count": 126},
        "analytical_group_namespace": "state-qualified accepted physical-location identity",
        "cross_state_identity_merge": False,
        "estimation_weighting": "inverse observation count within physical location",
        "impacted_sales_permitted": False,
    }:
        raise SystemExit("MODEL-13 pooled cohort authority differs")
    if [item["candidate_id"] for item in contract["candidate_family"]] != CANDIDATE_IDS:
        raise SystemExit("MODEL-13 candidate family differs")
    rule = contract["selection"]["challenger_qualification"]
    if rule != {"pooled_spearman_minimum_ratio_to_reference": 1.0, "pooled_log_rmse_maximum_ratio_to_reference": 1.05, "michigan_spearman_minimum_delta_to_reference": -0.01}:
        raise SystemExit("MODEL-13 frozen selection rule differs")
    if contract["grouped_validation"]["outer_fold_count"] != 5 or contract["grouped_validation"]["inner_fold_count"] != 4:
        raise SystemExit("MODEL-13 grouped validation differs")
    if output["tract_output"]["row_count"] != 3017 or len(output["tract_output"]["columns"]) != 24:
        raise SystemExit("MODEL-13 tract presentation contract differs")

    found_schemas = {path.name for path in (repository / "schemas/model13").glob("*.schema.json")}
    if found_schemas != EXPECTED_SCHEMAS:
        raise SystemExit(f"MODEL-13 schema inventory mismatch: {sorted(found_schemas)}")
    for path in (repository / "schemas/model13").glob("*.schema.json"):
        if _load(path).get("$schema") != "https://json-schema.org/draft/2020-12/schema":
            raise SystemExit(f"MODEL-13 schema declaration differs: {path.name}")

    workflow = (repository / ".github/workflows/repository-validation.yml").read_text(encoding="utf-8")
    if "python scripts/check_model13_repository.py" not in workflow or "MODEL13_TEST_TEMP_ROOT" not in workflow:
        raise SystemExit("MODEL-13 checker or test temp root is absent from Repository Validation")
    resolver_text = "\n".join((repository / path).read_text(encoding="utf-8").lower() for path in ("src/sprouts_customer_geography/model13/resolver.py", "src/sprouts_customer_geography/model13/registry_bootstrap.py"))
    used = [operation for operation in (".glob(", ".rglob(", ".iterdir(", "os.walk(") if operation in resolver_text]
    if used:
        raise SystemExit(f"MODEL-13 protected resolution contains broad discovery: {used}")

    commitment_path = repository / COMMITMENT_PATH
    if posture[0] != "IN_PROGRESS" and not commitment_path.is_file():
        raise SystemExit("completed MODEL-13 posture requires its disclosure-safe execution commitment")
    if commitment_path.is_file():
        commitment = _load(commitment_path)
        semantic = copy.deepcopy(commitment)
        expected_hash = semantic.pop("content_sha256", None)
        result = commitment.get("execution_result", {})
        gate = commitment.get("exact_h_gate", {})
        if commitment.get("artifact_id") != "MODEL13_EXECUTION_COMMITMENT_V1" or commitment.get("state") != "READY" or expected_hash != content_digest(semantic):
            raise SystemExit("MODEL-13 execution commitment identity or hash differs")
        if commitment.get("contract_authority", {}).get("content_sha256") != contract["content_sha256"]:
            raise SystemExit("MODEL-13 execution commitment contract binding differs")
        if result.get("frozen_michigan_benchmark_physical_location_count") != 82:
            raise SystemExit("MODEL-13 frozen benchmark pair count differs")
        if result.get("pooled_development_observation_count") != 201 or result.get("pooled_development_physical_location_count") != 126:
            raise SystemExit("MODEL-13 pooled execution counts differ")
        if result.get("target_blind_retained_feature_count", -1) + result.get("target_blind_excluded_feature_count", -1) != 13:
            raise SystemExit("MODEL-13 target-blind feature accounting differs")
        if [item.get("candidate_id") for item in result.get("candidate_metrics", [])] != CANDIDATE_IDS:
            raise SystemExit("MODEL-13 candidate execution evidence differs")
        if result.get("statewide_computable_count", -1) + result.get("statewide_noncomputable_count", -1) != 3017 or result.get("all_3017_tracts_accounted") is not True:
            raise SystemExit("MODEL-13 statewide tract accounting differs")
        if result.get("deterministic_rerun") != "MATCH" or result.get("impacted_sales_values_accessed") != 0 or result.get("power_bi_implemented") is not False or result.get("protected_details_disclosed") is not False:
            raise SystemExit("MODEL-13 deterministic, target, Power BI, or disclosure boundary differs")
        required_true = ("benchmark_ready_and_immutable", "benchmark_preceded_michigan_development", "target_blind_feature_freeze_ready", "development_role_transition_ready", "pooled_comparison_complete", "selected_refit_ready", "statewide_scoring_ready", "presentation_outputs_ready", "deterministic_match", "zero_impacted_sales_access", "all_repository_validation_required")
        if any(gate.get(field) is not True for field in required_true) or gate.get("independent_run_count") != 2 or gate.get("semantic_stage_count") != 5:
            raise SystemExit("MODEL-13 exact-H execution gate evidence differs")

    stageable = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=repository, check=True, capture_output=True, text=True).stdout.splitlines()
    assert_no_protected_tracked_paths(stageable)
    forbidden_paths = [path for path in stageable if path.replace("\\", "/").startswith(("outputs/", "data/raw/", "data/cache/", "data/local/"))]
    if forbidden_paths:
        raise SystemExit(f"MODEL-13 protected raw or generated paths became stageable: {forbidden_paths}")
    changed = set(subprocess.run(["git", "diff", "--name-only", AUTHORIZATION_BASE, "--"], cwd=repository, check=True, capture_output=True, text=True).stdout.splitlines())
    changed.update(subprocess.run(["git", "ls-files", "--others", "--exclude-standard"], cwd=repository, check=True, capture_output=True, text=True).stdout.splitlines())
    changed_files = [path for path in sorted(changed) if (repository / path).is_file()]
    public_text = "\n".join((repository / path).read_text(encoding="utf-8", errors="ignore") for path in changed_files)
    forbidden_fragments = ("Sprouts" + "-Protected", "C:" + "\\Users\\", "m13run-" + "primary", "m13run-" + "verification", "phandle-" + "model13")
    if any(fragment.lower() in public_text.lower() for fragment in forbidden_fragments):
        raise SystemExit("MODEL-13 protected-local path, handle, or run identity entered repository content")
    if re.search(r"(?i)\bmi[_ -]+seed[_ -]+forecasts\b|\bcity[0-9]+\b", public_text):
        raise SystemExit("MODEL-13 protected source basename or private header alias entered repository content")
    narrative = "\n".join((repository / path).read_text(encoding="utf-8", errors="ignore") for path in changed_files if path.replace("\\", "/").startswith(("config/", "docs/", "governance/")))
    if re.search(r"(?i)[A-Za-z0-9 _.-]+\.xlsx", narrative):
        raise SystemExit("MODEL-13 protected or reconstructable workbook filename entered repository narrative")

    print(json.dumps({"state": "passed", "contract_id": CONTRACT_ID, "task_posture": posture, "candidate_count": 4, "pooled_physical_location_count": 126, "statewide_tract_count": 3017, "nondisclosing_execution_commitment": commitment_path.is_file(), "protected_tracked_path_guard": "passed"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
