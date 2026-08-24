"""Repository-safe PIPE-05 authority, scope, execution, and disclosure guard."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import re
import subprocess
import sys


REQUIRED = (
    "governance/tasks/PIPE-05.michigan-isolated-sales-outcome-binding.task.json",
    "docs/work_orders/PIPE_05_MICHIGAN_ISOLATED_SALES_OUTCOME_BINDING.md",
    "docs/PIPE05_MICHIGAN_ISOLATED_SALES_OUTCOME_BINDING.md",
    "config/pipe05/michigan_isolated_sales_binding_contract.json",
    "schemas/pipe05/michigan_isolated_sales_binding_contract.schema.json",
    "schemas/pipe05/michigan_isolated_sales_binding_execution_commitment.schema.json",
    "schemas/pipe05/model12_michigan_isolated_sales_binding.schema.json",
    "schemas/pipe05/protected_handle_registry.schema.json",
    "src/sprouts_customer_geography/pipe05/contract.py",
    "src/sprouts_customer_geography/pipe05/resolver.py",
    "src/sprouts_customer_geography/pipe05/registry_bootstrap.py",
    "src/sprouts_customer_geography/pipe05/xlsx_projection.py",
    "src/sprouts_customer_geography/pipe05/binding.py",
    "src/sprouts_customer_geography/pipe05/cli.py",
    "tests/test_pipe05_binding.py",
)
COMMITMENT_PATH = "config/pipe05/michigan_isolated_sales_binding_execution_commitment.json"
AUTHORIZATION_BASE = "ebebe414a56e27612e42b7f78554b513bdefebc8"
EXPECTED_SCHEMAS = {
    "michigan_isolated_sales_binding_contract.schema.json",
    "michigan_isolated_sales_binding_execution_commitment.schema.json",
    "model12_michigan_isolated_sales_binding.schema.json",
    "protected_handle_registry.schema.json",
}


def _load(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SystemExit(f"PIPE-05 repository JSON is unreadable: {path.name}") from exc
    if not isinstance(value, dict):
        raise SystemExit(f"PIPE-05 repository JSON must be an object: {path.name}")
    return value


def main() -> int:
    repository = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repository / "src"))
    from sprouts_customer_geography.governance import load_and_validate_task_manifest
    from sprouts_customer_geography.pipe01.canonical import content_digest
    from sprouts_customer_geography.pipe01.safeguards import assert_no_protected_tracked_paths
    from sprouts_customer_geography.pipe05.binding import EXECUTION_COMMITMENT_ID
    from sprouts_customer_geography.pipe05.contract import CONTRACT_ID, verify_repository_authority

    missing = [path for path in REQUIRED if not (repository / path).is_file()]
    if missing:
        raise SystemExit(f"PIPE-05 required repository files absent: {missing}")
    manifests = list((repository / "governance/tasks").glob("PIPE-05*.task.json"))
    work_orders = list((repository / "docs/work_orders").glob("PIPE_05*.md"))
    if len(manifests) != 1 or len(work_orders) != 1:
        raise SystemExit(f"PIPE-05 requires exactly one task manifest and one work order; found {len(manifests)} and {len(work_orders)}")
    task = load_and_validate_task_manifest(manifests[0], repository / "schemas/governance/task_manifest.schema.json")
    if task["task_id"] != "PIPE-05" or task["capability_owner"] != "PIPE: Analytical Pipeline Decisions & Acceptance":
        raise SystemExit("PIPE-05 task identity or capability owner differs")
    if task["implementation_branch"] != "task/pipe-05-michigan-isolated-sales-outcome-binding":
        raise SystemExit("PIPE-05 implementation branch identity differs")
    allowed_postures = {
        ("IN_PROGRESS", "IN_PROGRESS", "NOT_REVIEWED"),
        ("COMPLETED_AWAITING_ACCEPTANCE", "COMPLETED", "NOT_REVIEWED"),
        ("ACCEPTED_CLOSED", "COMPLETED", "ACCEPTED"),
    }
    posture = (task["state"], task["completion_state"]["execution"], task["completion_state"]["capability_acceptance"])
    if posture not in allowed_postures:
        raise SystemExit(f"PIPE-05 task posture is not executable or acceptance-bearing: {posture}")

    contract = verify_repository_authority(repository)
    if contract["artifact_id"] != CONTRACT_ID:
        raise SystemExit("PIPE-05 exact contract identity differs")
    if contract["accepted_model12_authority"]["canonical_merge"] != AUTHORIZATION_BASE:
        raise SystemExit("PIPE-05 canonical authorization base differs")
    if contract["cohort_rule"]["eligible_when"] != "accepted MODEL-12 physical-location identity is nonquarantined" or contract["cohort_rule"]["frozen_score_computability_required"] is not False:
        raise SystemExit("PIPE-05 binding cohort semantics differ")
    if contract["target_projection"]["allowed_target_field"] != "Isolated Sales" or contract["target_projection"]["denied_target_field"] != "Impacted Sales":
        raise SystemExit("PIPE-05 target allowlist differs")
    if contract["clean_benchmark_boundary"]["benchmark_evaluation"] is not False or contract["evidence_role"]["binding_marks_development_consumed"] is not False:
        raise SystemExit("PIPE-05 benchmark or evidence-role boundary differs")

    schema_dir = repository / "schemas/pipe05"
    found_schemas = {path.name for path in schema_dir.glob("*.schema.json")}
    if found_schemas != EXPECTED_SCHEMAS:
        raise SystemExit(f"PIPE-05 schema inventory mismatch: {sorted(found_schemas)}")
    for path in schema_dir.glob("*.schema.json"):
        if _load(path).get("$schema") != "https://json-schema.org/draft/2020-12/schema":
            raise SystemExit(f"PIPE-05 schema declaration differs: {path.name}")

    commitment_path = repository / COMMITMENT_PATH
    if posture[0] != "IN_PROGRESS" and not commitment_path.is_file():
        raise SystemExit("completed PIPE-05 posture requires its nondisclosing execution commitment")
    if commitment_path.is_file():
        commitment = _load(commitment_path)
        semantic = copy.deepcopy(commitment)
        expected_hash = semantic.pop("content_sha256", None)
        aggregate = commitment.get("aggregate_conformance", {})
        boundary = commitment.get("execution_boundary", {})
        disclosure = commitment.get("disclosure_boundary", {})
        verification = commitment.get("deterministic_binding_verification", {})
        protected_commitment = commitment.get("protected_binding_commitment", {})
        if commitment.get("artifact_id") != EXECUTION_COMMITMENT_ID or commitment.get("contract_authority", {}).get("content_sha256") != contract["content_sha256"] or expected_hash != content_digest(semantic):
            raise SystemExit("PIPE-05 execution commitment identity or content hash differs")
        if aggregate.get("source_observation_count") != 139 or aggregate.get("complete_source_observation_accounting") is not True or aggregate.get("complete_target_binding_accounting") is not True:
            raise SystemExit("PIPE-05 execution commitment lacks complete 139-observation accounting")
        if aggregate.get("target_binding_eligible_source_observation_count") + aggregate.get("quarantine_excluded_source_observation_count") != aggregate.get("source_observation_count"):
            raise SystemExit("PIPE-05 eligible and quarantine observation counts do not partition MODEL-12")
        if aggregate.get("valid_isolated_sales_binding_count") + aggregate.get("missing_or_invalid_isolated_sales_count") != aggregate.get("target_binding_eligible_source_observation_count"):
            raise SystemExit("PIPE-05 target status counts do not partition the eligible cohort")
        if verification.get("state") != "MATCH" or any(verification.get(field) is not True for field in ("source_observation_accounting_identical", "eligible_cohort_identity_identical", "minimum_target_projection_identical", "protected_content_verified", "ready_commitment_verified")):
            raise SystemExit("PIPE-05 deterministic verification evidence differs")
        if boundary.get("impacted_sales_body_values_accessed") != 0 or boundary.get("other_outcome_body_values_accessed") != 0 or boundary.get("quarantined_target_body_values_accessed") != 0:
            raise SystemExit("PIPE-05 denied or quarantine target-access boundary differs")
        if any(boundary.get(field) is not False for field in ("benchmark_evaluation_performed", "prediction_values_modified", "prediction_values_materialized", "residuals_ranks_correlations_or_error_metrics_calculated", "model_fitting_training_tuning_refitting_or_scoring_performed", "development_consumption_marked")):
            raise SystemExit("PIPE-05 benchmark model prediction or consumption boundary differs")
        if any(value is not False for value in disclosure.values()):
            raise SystemExit("PIPE-05 protected execution disclosure boundary differs")
        if protected_commitment.get("protected_package_digest_disclosed") is not False or protected_commitment.get("nonce_disclosed") is not False or protected_commitment.get("binding_content_disclosed") is not False:
            raise SystemExit("PIPE-05 protected commitment disclosure posture differs")

    resolver_source = (repository / "src/sprouts_customer_geography/pipe05/resolver.py").read_text(encoding="utf-8").lower()
    bootstrap_source = (repository / "src/sprouts_customer_geography/pipe05/registry_bootstrap.py").read_text(encoding="utf-8").lower()
    prohibited_discovery = (".glob(", ".rglob(", ".iterdir(", "os.walk(")
    used = [operation for operation in prohibited_discovery if operation in resolver_source or operation in bootstrap_source]
    if used:
        raise SystemExit(f"PIPE-05 exact protected resolver or bootstrap contains discovery operation(s): {used}")
    projection_source = (repository / "src/sprouts_customer_geography/pipe05/xlsx_projection.py").read_text(encoding="utf-8").lower()
    if "file_sha256" in projection_source or "read_bytes()" in projection_source:
        raise SystemExit("PIPE-05 target projection exposes broad source hashing or byte loading")
    workflow = (repository / ".github/workflows/repository-validation.yml").read_text(encoding="utf-8")
    if "python scripts/check_pipe05_repository.py" not in workflow:
        raise SystemExit("PIPE-05 conformance checker is absent from required Repository Validation")

    stageable = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=repository, check=True, capture_output=True, text=True).stdout.splitlines()
    assert_no_protected_tracked_paths(stageable)
    forbidden_paths = [path for path in stageable if path.replace("\\", "/").startswith(("outputs/", "data/raw/", "data/cache/", "data/local/"))]
    if forbidden_paths:
        raise SystemExit(f"PIPE-05 protected raw or generated paths became stageable: {forbidden_paths}")
    changed = set(subprocess.run(["git", "diff", "--name-only", AUTHORIZATION_BASE, "--"], cwd=repository, check=True, capture_output=True, text=True).stdout.splitlines())
    changed.update(subprocess.run(["git", "ls-files", "--others", "--exclude-standard"], cwd=repository, check=True, capture_output=True, text=True).stdout.splitlines())
    changed_files = [path for path in sorted(changed) if (repository / path).is_file()]
    public_text = "\n".join((repository / path).read_text(encoding="utf-8", errors="ignore") for path in changed_files)
    forbidden_fragments = ("Sprouts" + "-Protected", "C:" + "\\Users\\", "m12run-" + "wisconsin", "p5bind-" + "real")
    if any(fragment.lower() in public_text.lower() for fragment in forbidden_fragments):
        raise SystemExit("PIPE-05 protected-local path or run detail entered stageable repository content")
    if re.search(r"(?i)\bmi[_ -]+seed[_ -]+forecasts\b|\bcity[0-9]+\b", public_text):
        raise SystemExit("PIPE-05 protected source basename or private header alias entered stageable repository content")
    narrative = "\n".join((repository / path).read_text(encoding="utf-8", errors="ignore") for path in changed_files if path.replace("\\", "/").startswith(("config/", "docs/", "governance/")))
    if re.search(r"(?i)[A-Za-z0-9 _.-]+\.xlsx", narrative):
        raise SystemExit("PIPE-05 protected or reconstructable workbook filename entered repository-safe narrative")

    print(json.dumps({"state": "passed", "contract_id": CONTRACT_ID, "task_posture": posture, "model12_exact_authority": True, "source_observation_invariant": 139, "isolated_sales_only": True, "benchmark_evaluation_authorized": False, "schema_count": len(found_schemas), "nondisclosing_execution_commitment": commitment_path.is_file(), "protected_tracked_path_guard": "passed"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
