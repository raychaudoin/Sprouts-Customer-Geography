"""Repository-safe authority verification for PIPE-05."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
from typing import Any, Mapping

from sprouts_customer_geography.model12.contract import verify_repository_authority as verify_model12_repository_authority
from sprouts_customer_geography.pipe01.canonical import content_digest, file_sha256
from sprouts_customer_geography.pipe01.errors import require


CONTRACT_ID = "PIPE05_MICHIGAN_ISOLATED_SALES_BINDING_CONTRACT_V1"
CONTRACT_VERSION = "1.0.0"
CONTRACT_PATH = "config/pipe05/michigan_isolated_sales_binding_contract.json"
MODEL12_EXECUTION_COMMITMENT_ID = "MODEL12_MICHIGAN_TARGET_BLIND_EXECUTION_COMMITMENT_V1"
MODEL12_SOURCE_OBSERVATION_COUNT = 139
MODEL12_PHYSICAL_LOCATION_COUNT = 86
MODEL12_QUARANTINED_PHYSICAL_LOCATION_COUNT = 1
ACCEPTED_MODEL12_H = "ed4e8196debee378fe49a53e3a4b133afe451eec"
ACCEPTED_MODEL12_A = "4cf6ed16d1ab41757684f65ef587ece7819ac89b"
ACCEPTED_MODEL12_MERGE = "ebebe414a56e27612e42b7f78554b513bdefebc8"


def _load_object(path: Path, code: str) -> dict[str, Any]:
    require(path.is_file(), code, "required repository authority is absent")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        require(False, code, "required repository authority is unreadable")
    require(isinstance(value, dict), code, "required repository authority must be an object")
    return value


def _canonical_digest(document: Mapping[str, Any]) -> str:
    semantic = copy.deepcopy(dict(document))
    semantic.pop("content_sha256", None)
    return content_digest(semantic)


def _require_commit(repository_root: Path, commit: str) -> None:
    present = subprocess.run(["git", "cat-file", "-e", f"{commit}^{{commit}}"], cwd=repository_root, capture_output=True, text=True)
    require(present.returncode == 0, "PIPE05_ACCEPTED_GIT_LINEAGE_MISSING", "accepted predecessor commit is absent")
    ancestor = subprocess.run(["git", "merge-base", "--is-ancestor", commit, "HEAD"], cwd=repository_root, capture_output=True, text=True)
    require(ancestor.returncode == 0, "PIPE05_ACCEPTED_GIT_LINEAGE_MISSING", "accepted predecessor commit is not an ancestor of execution HEAD")


def load_model12_execution_commitment(repository_root: Path, contract: Mapping[str, Any]) -> dict[str, Any]:
    accepted = contract["accepted_model12_authority"]
    path = repository_root / str(accepted["execution_commitment_path"])
    commitment = _load_object(path, "PIPE05_MODEL12_EXECUTION_COMMITMENT_MISSING")
    aggregate = commitment.get("aggregate_conformance")
    require(
        commitment.get("artifact_id") == MODEL12_EXECUTION_COMMITMENT_ID
        and commitment.get("version") == accepted.get("execution_commitment_version")
        and commitment.get("content_sha256") == accepted.get("execution_commitment_content_sha256")
        and commitment.get("content_sha256") == _canonical_digest(commitment)
        and isinstance(aggregate, Mapping)
        and aggregate.get("source_observation_count") == MODEL12_SOURCE_OBSERVATION_COUNT
        and aggregate.get("physical_location_count") == MODEL12_PHYSICAL_LOCATION_COUNT
        and aggregate.get("quarantined_physical_location_count") == MODEL12_QUARANTINED_PHYSICAL_LOCATION_COUNT
        and aggregate.get("complete_source_observation_accounting") is True
        and aggregate.get("complete_location_accounting") is True,
        "PIPE05_MODEL12_EXECUTION_COMMITMENT_MISMATCH",
        "accepted MODEL-12 execution commitment identity or aggregate differs",
    )
    comparison = commitment.get("deterministic_comparison")
    boundary = commitment.get("execution_boundary")
    require(
        comparison == {"semantic_stage_count": 3, "semantic_packages_byte_identical": True, "aggregate_conformance_identical": True}
        and isinstance(boundary, Mapping)
        and boundary.get("michigan_target_body_values_accessed") == 0
        and all(
            boundary.get(field) is False
            for field in (
                "model_refit_performed",
                "model_retraining_performed",
                "model_retuning_performed",
                "michigan_feature_selection_performed",
                "michigan_redundancy_screen_performed",
                "prediction_recalibration_performed",
                "michigan_distribution_used_to_modify_model",
            )
        ),
        "PIPE05_MODEL12_FROZEN_AUTHORITY_MISMATCH",
        "accepted MODEL-12 deterministic or frozen execution boundary differs",
    )
    return commitment


def verify_repository_authority(repository_root: Path) -> dict[str, Any]:
    """Require exact accepted MODEL-12, MODEL-10/11, and PIPE-04 authority."""

    root = repository_root.resolve()
    contract = _load_object(root / CONTRACT_PATH, "PIPE05_CONTRACT_MISSING")
    require(
        contract.get("artifact_id") == CONTRACT_ID
        and contract.get("version") == CONTRACT_VERSION
        and contract.get("content_sha256") == _canonical_digest(contract),
        "PIPE05_CONTRACT_IDENTITY_MISMATCH",
        "PIPE-05 contract identity version or content hash differs",
    )
    accepted = contract.get("accepted_model12_authority")
    require(isinstance(accepted, Mapping), "PIPE05_MODEL12_AUTHORITY_INVALID", "accepted MODEL-12 authority is absent")
    model12 = verify_model12_repository_authority(root)
    require(
        model12.get("artifact_id") == accepted.get("contract_artifact_id")
        and model12.get("version") == accepted.get("contract_version")
        and model12.get("content_sha256") == accepted.get("contract_content_sha256")
        and accepted.get("identity_package_id") == "MODEL12_MICHIGAN_PHYSICAL_LOCATION_IDENTITY_PACKAGE_V1"
        and accepted.get("frozen_scoring_package_id") == "MODEL12_MICHIGAN_FROZEN_SCORING_PACKAGE_V1"
        and accepted.get("substantive_h") == ACCEPTED_MODEL12_H
        and accepted.get("acceptance_record_a") == ACCEPTED_MODEL12_A
        and accepted.get("canonical_merge") == ACCEPTED_MODEL12_MERGE,
        "PIPE05_MODEL12_AUTHORITY_MISMATCH",
        "PIPE-05 does not retain exact accepted MODEL-12 repository authority",
    )
    for commit in (ACCEPTED_MODEL12_H, ACCEPTED_MODEL12_A, ACCEPTED_MODEL12_MERGE):
        _require_commit(root, commit)
    load_model12_execution_commitment(root, contract)

    inherited = contract.get("inherited_authority")
    require(isinstance(inherited, Mapping), "PIPE05_INHERITED_AUTHORITY_INVALID", "PIPE-05 inherited authority is absent")
    pipe04_path = root / str(inherited.get("pipe04_contract_path"))
    pipe04 = _load_object(pipe04_path, "PIPE05_PIPE04_AUTHORITY_MISSING")
    require(
        pipe04.get("artifact_id") == inherited.get("pipe04_contract_id")
        and file_sha256(pipe04_path) == inherited.get("pipe04_contract_file_sha256")
        and pipe04.get("target_projection", {}).get("allowed_target_field") == "Isolated Sales"
        and pipe04.get("target_projection", {}).get("denied_target_field") == "Impacted Sales"
        and inherited.get("identity_version") == "MODEL04_TARGET_BLIND_PHYSICAL_LOCATION_IDENTITY_V1",
        "PIPE05_INHERITED_AUTHORITY_MISMATCH",
        "accepted identity target or PIPE-04 authority differs",
    )
    for commit in (str(inherited.get("pipe04_substantive_h")), str(inherited.get("pipe04_acceptance_record_a")), str(inherited.get("pipe04_canonical_merge"))):
        _require_commit(root, commit)

    cohort = contract.get("cohort_rule", {})
    target = contract.get("target_projection", {})
    missing = contract.get("missing_invalid_targets", {})
    benchmark = contract.get("clean_benchmark_boundary", {})
    consumption = contract.get("evidence_role", {})
    protected = contract.get("protected_execution", {})
    require(
        cohort.get("all_model12_source_observations_accounted") is True
        and cohort.get("frozen_score_computability_required") is False
        and cohort.get("quarantined_excluded_before_target_access") is True
        and cohort.get("cohort_frozen_before_target_body_access") is True
        and cohort.get("target_content_may_change_membership_or_identity") is False,
        "PIPE05_COHORT_CONTRACT_MISMATCH",
        "PIPE-05 target-binding cohort authority differs",
    )
    require(
        target.get("default_deny") is True
        and target.get("allowed_state") == "michigan"
        and target.get("allowed_target_field") == "Isolated Sales"
        and target.get("denied_target_field") == "Impacted Sales"
        and target.get("other_outcome_fields_denied") is True
        and target.get("whole_workbook_hash_permitted") is False,
        "PIPE05_TARGET_CONTRACT_MISMATCH",
        "PIPE-05 target projection boundary differs",
    )
    require(
        missing == {"explicit_status_required": True, "imputation": False, "zero_substitution": False, "silent_drop": False, "model_eligibility_decision": False}
        and benchmark.get("accepted_frozen_predictions_immutable") is True
        and benchmark.get("prediction_body_materialized_by_pipe05") is False
        and all(benchmark.get(field) is False for field in ("benchmark_evaluation", "residuals", "ranks", "correlations", "rmse_or_mae", "model_fitting_training_tuning_refitting_or_scoring"))
        and consumption.get("binding_marks_development_consumed") is False
        and protected.get("registry_id") == "PIPE05_PROTECTED_HANDLE_REGISTRY_V1"
        and protected.get("binding_package_id") == "PIPE05_MODEL12_MICHIGAN_ISOLATED_SALES_BINDING_V1",
        "PIPE05_EXECUTION_BOUNDARY_MISMATCH",
        "PIPE-05 missing target benchmark evidence role or protected execution boundary differs",
    )
    return contract
