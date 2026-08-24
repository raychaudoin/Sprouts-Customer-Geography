"""Protected target-conditioned MODEL-11 comparison and finalization."""

from __future__ import annotations

import copy
import json
import math
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from sprouts_customer_geography.model09.development import _target_rows
from sprouts_customer_geography.model09.features import verify_pipe04_binding
from sprouts_customer_geography.pipe01.canonical import content_digest, file_sha256, write_json_exclusive
from sprouts_customer_geography.pipe01.commitment import freeze_commitment, new_nonce
from sprouts_customer_geography.pipe01.errors import require
from sprouts_customer_geography.pipe02.resolver import _is_within

from .features import CONTRACT_ID, FREEZE_PACKAGE_ID, verify_repository_authority
from .modeling import ComparisonResult, FittedRegularizedModel, compare_candidates
from .resolver import ProtectedHandleResolver


PACKAGE_ID = "MODEL11_WISCONSIN_MULTIVARIATE_DEVELOPMENT_PACKAGE_V1"
PACKAGE_SCHEMA = "model11-wisconsin-multivariate-development-package-v1"


def _load_object(path: Path, code: str) -> dict[str, Any]:
    require(path.is_file(), code, "required protected JSON is absent")
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), code, "required protected JSON must be an object")
    return value


def load_feature_freeze(output_root: Path, freeze_run_id: str, contract: Mapping[str, Any]) -> dict[str, Any]:
    require(bool(re.fullmatch(r"m11freeze-[A-Za-z0-9_-]+", freeze_run_id)), "MODEL11_FREEZE_ID_INVALID", "exact feature-freeze identity is invalid")
    run_dir = (output_root / "model11-feature-freezes" / freeze_run_id).resolve()
    require(_is_within(run_dir, output_root.resolve()), "PROTECTED_PATH_CONTAINMENT_FAILED", "feature freeze escapes MODEL-11 output root")
    package_path = run_dir / "model11_target_blind_feature_freeze_package.json"
    package = _load_object(package_path, "MODEL11_FEATURE_FREEZE_UNRESOLVED")
    ready = _load_object(run_dir / "READY.json", "MODEL11_FEATURE_FREEZE_READY_UNRESOLVED")
    protected_hash = package.get("protected_content_sha256")
    semantic = dict(package)
    semantic.pop("protected_content_sha256", None)
    semantic.pop("stable_feature_freeze_identity", None)
    require(package.get("package_id") == FREEZE_PACKAGE_ID and package.get("freeze_run_id") == freeze_run_id and protected_hash == content_digest(semantic), "MODEL11_FEATURE_FREEZE_MISMATCH", "feature-freeze protected identity differs")
    require(ready.get("state") == "ready" and ready.get("target_accessed") is False and ready.get("freeze_run_id") == freeze_run_id and ready.get("protected_content_sha256") == protected_hash and ready.get("package_file_sha256") == file_sha256(package_path), "MODEL11_FEATURE_FREEZE_READY_MISMATCH", "feature-freeze READY marker differs")
    accounting = package.get("evidence_accounting", {})
    preparation = package.get("feature_preparation", {})
    require(accounting.get("eligible_observation_count") == contract["cohort"]["eligible_observation_count"] and accounting.get("physical_location_count") == contract["cohort"]["physical_location_count"] and accounting.get("target_values_accessed") == 0 and preparation.get("target_blind") is True and preparation.get("candidate_measure_count") == 13, "MODEL11_FEATURE_FREEZE_SCOPE_MISMATCH", "feature-freeze scope differs")
    return package


def _join_targets(feature_rows: list[Mapping[str, Any]], binding: Mapping[str, Any]) -> tuple[list[dict[str, Any]], dict[str, float]]:
    bound_rows = binding.get("eligible_wisconsin_cohort")
    require(isinstance(bound_rows, list), "PIPE04_COHORT_UNRESOLVED", "PIPE-04 eligible cohort is absent")
    by_observation = {str(row.get("source_observation_id")): row for row in bound_rows}
    require(len(by_observation) == len(bound_rows), "PIPE04_COHORT_IDENTITY_MISMATCH", "PIPE-04 cohort identity is duplicate")
    targets = _target_rows(binding)
    frozen_ids = {str(row["source_observation_id"]) for row in feature_rows}
    require(frozen_ids == set(by_observation) == set(targets), "COMPLETE_COHORT_ACCOUNTING_FAILED", "feature freeze binding and targets do not cover the same cohort")
    output: list[dict[str, Any]] = []
    for frozen in feature_rows:
        observation_id = str(frozen["source_observation_id"])
        bound = by_observation[observation_id]
        for field in ("successor_physical_location_id", "market", "forecast_vintage"):
            require(frozen.get(field) == bound.get(field), "TARGET_CONTENT_CHANGED_COHORT", "PIPE-04 lineage differs from target-blind freeze")
        output.append({**dict(frozen), "isolated_sales": targets[observation_id]})
    return output, targets


class ProtectedDevelopmentRun:
    def __init__(self, output_root: Path, repository_root: Path, *, development_run_id: str | None = None, package_version: str = "1.0.0", supersedes: str | None = None):
        self.output_root = output_root.resolve()
        require(self.output_root.is_dir() and not _is_within(self.output_root, repository_root.resolve()), "PROTECTED_OUTPUT_INVALID", "MODEL-11 output root must exist outside Git")
        require(bool(re.fullmatch(r"1\.0\.[0-9]+", package_version)), "MODEL11_PACKAGE_VERSION_INVALID", "MODEL-11 package version must be 1.0.x")
        require(supersedes is None if package_version == "1.0.0" else bool(supersedes), "MODEL11_SUPERSESSION_REQUIRED", "corrected MODEL-11 runs require supersedes")
        self.development_run_id = development_run_id or "m11run-" + str(uuid.uuid4())
        require(bool(re.fullmatch(r"m11run-[A-Za-z0-9_-]+", self.development_run_id)), "MODEL11_RUN_ID_INVALID", "MODEL-11 run identity is invalid")
        runs_root = self.output_root / "model11-development-runs"
        runs_root.mkdir(exist_ok=True)
        self.run_dir = runs_root / self.development_run_id
        require(not self.run_dir.exists(), "MODEL11_RUN_IMMUTABLE", "MODEL-11 development run already exists")
        self.run_dir.mkdir()
        self.package_version = package_version
        self.supersedes = supersedes
        write_json_exclusive(self.run_dir / "development_state.json", {"development_run_id": self.development_run_id, "state": "incomplete", "finalization_state": "not_ready", "package_version": package_version, "supersedes": supersedes})

    def mark_target_reuse(self, observation_count: int) -> None:
        write_json_exclusive(self.run_dir / "development_consumption_state.json", {"development_run_id": self.development_run_id, "state": "DEVELOPMENT_CONSUMED_REUSED", "observation_count": observation_count, "new_independent_evidence": False, "independent_validation_eligibility": False})

    def finalize(self, semantic: Mapping[str, Any]) -> None:
        protected_hash = content_digest(semantic)
        stable = "model11-development:sha256:" + protected_hash
        package = {**copy.deepcopy(dict(semantic)), "protected_content_sha256": protected_hash, "stable_development_identity": stable}
        package_path = self.run_dir / "model11_wisconsin_multivariate_development_package.json"
        write_json_exclusive(package_path, package)
        nonce = new_nonce()
        commitment = freeze_commitment(protected_hash, nonce)
        with (self.run_dir / "development_nonce.bin").open("xb") as handle:
            handle.write(nonce)
            handle.flush()
            os.fsync(handle.fileno())
        write_json_exclusive(self.run_dir / "commitment_evidence.json", {"domain": "sprouts-customer-geography/model11/development-commitment/v1", "commitment_sha256": commitment})
        write_json_exclusive(self.run_dir / "development_manifest.json", {"development_run_id": self.development_run_id, "package_id": PACKAGE_ID, "package_version": self.package_version, "state": "ready", "finalization_state": "complete", "supersedes": self.supersedes, "protected_content_sha256": protected_hash, "stable_development_identity": stable, "package_file_sha256": file_sha256(package_path)})
        write_json_exclusive(self.run_dir / "READY.json", {"development_run_id": self.development_run_id, "package_id": PACKAGE_ID, "package_version": self.package_version, "state": "ready", "finalization_state": "complete", "protected_content_sha256": protected_hash, "stable_development_identity": stable, "commitment_sha256": commitment})


@dataclass(frozen=True)
class DevelopmentResult:
    eligible_observation_count: int
    quarantined_observation_count: int
    physical_location_count: int
    market_count: int
    eligible_data03_feature_count: int
    comparison: tuple[Mapping[str, Any], ...]
    selection: Mapping[str, Any]


def _predict_customer_fit(model: Any, row: Mapping[str, Any]) -> float:
    if isinstance(model, FittedRegularizedModel):
        return model.customer_fit_factor(row)
    return model.fit_proxy_factor(row)


def execute_protected_development(*, repository_root: Path, resolver: ProtectedHandleResolver, feature_freeze_run_id: str, development_run_id: str | None = None, package_version: str = "1.0.0", supersedes: str | None = None) -> DevelopmentResult:
    root = repository_root.resolve()
    contract = verify_repository_authority(root)
    request = resolver.development_request
    output_resource = resolver.resolve(str(request["model11_output_root_handle"]), "model11_output_root")
    freeze = load_feature_freeze(output_resource.path, feature_freeze_run_id, contract)
    staged = ProtectedDevelopmentRun(output_resource.path, root, development_run_id=development_run_id, package_version=package_version, supersedes=supersedes)
    pipe04_resource = resolver.resolve(str(request["pipe04_binding_handle"]), "pipe04_binding")
    pipe04_ready_resource = resolver.resolve(str(request["pipe04_ready_marker_handle"]), "pipe04_ready_marker")
    binding = verify_pipe04_binding(pipe04_resource.path, pipe04_ready_resource.path)
    feature_rows = freeze.get("observations")
    require(isinstance(feature_rows, list), "MODEL11_FEATURE_ROWS_UNRESOLVED", "frozen feature rows are absent")
    rows, targets = _join_targets(feature_rows, binding)
    staged.mark_target_reuse(len(targets))
    eligible_data03 = list(freeze["feature_preparation"]["eligible_data03_features"])
    result: ComparisonResult = compare_candidates(rows, contract, eligible_data03)
    preferred_id = str(result.selection["preferred_candidate_id"])
    preferred = result.fitted_models[preferred_id]
    protected_observations: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        candidate_predictions = {candidate_id: model.predict(row) for candidate_id, model in result.fitted_models.items()}
        protected_observations.append({
            **dict(row),
            "development_consumption_state": "DEVELOPMENT_CONSUMED_REUSED",
            "candidate_oof_predictions": {candidate_id: predictions[index] for candidate_id, predictions in result.oof_predictions.items()},
            "candidate_full_cohort_predictions": candidate_predictions,
            "candidate_full_cohort_residuals": {candidate_id: float(row["isolated_sales"]) - prediction for candidate_id, prediction in candidate_predictions.items()},
            "household_opportunity": row["features"]["households_5mi"],
            "preferred_customer_fit_proxy_factor": _predict_customer_fit(preferred, row),
            "preferred_modeled_target_mass": preferred.predict(row),
        })
    fitted_parameters = {candidate_id: model.protected_parameters() for candidate_id, model in result.fitted_models.items()}
    semantic = {
        "$schema": PACKAGE_SCHEMA,
        "package_id": PACKAGE_ID,
        "version": package_version,
        "development_run_id": staged.development_run_id,
        "state": "ready",
        "authority": {"model11_contract_id": CONTRACT_ID, "feature_freeze_run_id": feature_freeze_run_id, "feature_freeze_ready_verified": True, "pipe04_ready_verified": True, "protected_registry_identity": resolver.registry_identity},
        "evidence_accounting": {"eligible_observation_count": len(rows), "target_observation_count": len(targets), "quarantined_observation_count": contract["cohort"]["quarantined_observation_count"], "physical_location_count": len({row["successor_physical_location_id"] for row in rows}), "market_count": len({str(row["market"]) for row in rows}), "isolated_sales_values_reused": len(targets), "impacted_sales_values_accessed": 0, "non_wisconsin_target_values_accessed": 0, "new_independent_evidence": False, "complete_cohort_accounted": True},
        "target_blind_feature_preparation": freeze["feature_preparation"],
        "candidate_comparison": list(result.comparison),
        "selection": dict(result.selection),
        "preferred_model_artifact": {"preferred_candidate_id": preferred_id, "model09_retained": not bool(result.selection["challenger_selected"]), "parameters": fitted_parameters[preferred_id]},
        "fitted_models": fitted_parameters,
        "observations": protected_observations,
        "consumption": {"state": "DEVELOPMENT_CONSUMED_REUSED", "observation_count": len(rows), "historical_model09_record_rewritten": False, "new_independent_evidence": False},
        "finalization": {"bounded_candidate_count": len(result.comparison), "nested_physical_location_grouped_tuning": True, "row_level_folding_used": False, "market_or_vintage_used_as_customer_fit_predictor": False, "household_opportunity_customer_fit_and_modeled_mass_separate": True, "independent_validation_claimed": False, "market_transport_claimed": False, "production_authority_claimed": False, "proprietary_model_equivalence_claimed": False, "ready_marker_written_last": True},
        "supersedes": supersedes,
    }
    staged.finalize(semantic)
    return DevelopmentResult(len(rows), contract["cohort"]["quarantined_observation_count"], contract["cohort"]["physical_location_count"], len({str(row["market"]) for row in rows}), len(eligible_data03), result.comparison, result.selection)


def _stability_summary(item: Mapping[str, Any]) -> dict[str, Any] | None:
    stability = item.get("stability")
    if not isinstance(stability, Mapping):
        return None
    frequencies = list(stability["selection_frequency"].values())
    signs = list(stability["coefficient_sign_stability"].values())
    deviations = list(stability["coefficient_standard_deviation"].values())
    return {"selection_frequency_range": [round(min(frequencies), 3), round(max(frequencies), 3)], "coefficient_sign_stability_range": [round(min(signs), 3), round(max(signs), 3)], "maximum_standardized_coefficient_sd": round(max(deviations), 4)}


def build_disclosure_safe_result(result: DevelopmentResult) -> dict[str, Any]:
    report = {
        "completion_state": "MODEL-11 protected development ready",
        "evidence_role": "DEVELOPMENT_ONLY_NOT_INDEPENDENT_VALIDATION",
        "eligible_observation_count": result.eligible_observation_count,
        "quarantined_observation_count": result.quarantined_observation_count,
        "physical_location_count": result.physical_location_count,
        "market_count": result.market_count,
        "eligible_data03_feature_count": result.eligible_data03_feature_count,
        "isolated_sales_values_reused": result.eligible_observation_count,
        "impacted_sales_values_accessed": 0,
        "non_wisconsin_target_values_accessed": 0,
        "candidate_metrics": [
            {
                "candidate_id": item["candidate_id"],
                "grouped_spearman": round(item["grouped_oof"]["spearman"], 4),
                "grouped_kendall_tau_b": round(item["grouped_oof"]["kendall_tau_b"], 4),
                "grouped_log_rmse": round(item["grouped_oof"]["log_rmse"], 4),
                "grouped_level_mae": round(item["grouped_oof"]["level_mae"], 2),
                "fold_spearman_range": [round(item["fold_metric_ranges"]["spearman"]["minimum"], 4), round(item["fold_metric_ranges"]["spearman"]["maximum"], 4)],
                "market_holdout_spearman": round(item["leave_one_market_out"]["spearman"], 4),
                "outer_heldout_location_spearman": round(item["individual_physical_location_sensitivity"]["grouped_metrics"]["spearman"], 4),
                "effective_degrees_of_freedom": item["effective_degrees_of_freedom"],
                "stability": _stability_summary(item),
            }
            for item in result.comparison
        ],
        "preferred_candidate_id": result.selection["preferred_candidate_id"],
        "challenger_selected": result.selection["challenger_selected"],
        "selection_conclusion": result.selection["conclusion"],
        "model09_reference_reproduced": True,
        "complete_cohort_accounted": True,
        "new_independent_evidence": False,
        "market_transport_established": False,
        "production_or_operational_authority": False,
        "proprietary_model_equivalence_claimed": False,
        "protected_output_outside_git": True,
        "protected_details_disclosed": False,
    }
    serialized = json.dumps(report, sort_keys=True).lower()
    for forbidden in ("source_observation", "physical_location_id", "latitude", "longitude", "isolated_sales\":", "residual", "coefficient\":", "nonce", "sha256", "\\\\", ":\\"):
        require(forbidden not in serialized, "DISCLOSURE_SAFE_REPORT_VIOLATION", "protected detail entered MODEL-11 report")
    return report
