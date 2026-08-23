"""Protected MODEL-09 authority verification, development, and finalization."""

from __future__ import annotations

import copy
import json
import math
import os
import re
import subprocess
import uuid
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping

from sprouts_customer_geography.pipe01.canonical import content_digest, file_sha256, write_json_exclusive
from sprouts_customer_geography.pipe01.commitment import freeze_commitment, new_nonce
from sprouts_customer_geography.pipe01.errors import require
from sprouts_customer_geography.pipe02.resolver import _is_within

from .features import (
    build_public_features,
    load_public_tract_evidence,
    reconcile_fixed_cohort,
    verify_model10_package,
    verify_pipe04_binding,
)
from .modeling import FittedCandidate, compare_candidates
from .resolver import ProtectedHandleResolver


PACKAGE_ID = "MODEL09_WISCONSIN_EXPERIMENTAL_DEVELOPMENT_PACKAGE_V1"
PACKAGE_VERSION = "1.0.0"
PACKAGE_SCHEMA = "model09-wisconsin-experimental-development-package-v1"
CONTRACT_ID = "MODEL09_WISCONSIN_EXPERIMENTAL_MODEL_CONTRACT_V1"
ACCEPTED_PIPE04_H = "5b96203ac7849fdd48601dc0129d1bbbe1b91d0e"
ACCEPTED_PIPE04_A = "195e1f9e9599e4812417954b57356327b80c5051"
ACCEPTED_PIPE04_MERGE = "0bc3a6c159d8672254f552f93d18265e539eb10e"


def _load_object(path: Path, code: str) -> dict[str, Any]:
    require(path.is_file(), code, "required JSON authority is absent")
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), code, "required JSON authority must be an object")
    return value


def verify_repository_authority(repository_root: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    contract = _load_object(repository_root / "config/model/model09_wisconsin_experimental_model_contract.json", "MODEL09_CONTRACT_MISSING")
    require(contract.get("artifact_id") == CONTRACT_ID and contract.get("version") == "1.0.0" and len(contract.get("candidates", [])) == 4, "MODEL09_CONTRACT_MISMATCH", "MODEL-09 bounded comparison contract differs")
    pipe04_manifest = _load_object(repository_root / "governance/tasks/PIPE-04.model10-wisconsin-development-binding-integration.task.json", "PIPE04_ACCEPTED_AUTHORITY_MISSING")
    require(
        pipe04_manifest.get("state") == "ACCEPTED_CLOSED"
        and pipe04_manifest.get("implementation_commit") == ACCEPTED_PIPE04_H
        and pipe04_manifest.get("completion_state", {}).get("capability_acceptance") == "ACCEPTED",
        "PIPE04_ACCEPTED_AUTHORITY_MISMATCH",
        "accepted PIPE-04 authority differs",
    )
    for commit in (ACCEPTED_PIPE04_H, ACCEPTED_PIPE04_A, ACCEPTED_PIPE04_MERGE):
        present = subprocess.run(["git", "cat-file", "-e", commit + "^{commit}"], cwd=repository_root, capture_output=True, text=True)
        require(present.returncode == 0, "PIPE04_ACCEPTED_GIT_LINEAGE_MISSING", "accepted PIPE-04 commit lineage is absent")
    ancestor = subprocess.run(["git", "merge-base", "--is-ancestor", ACCEPTED_PIPE04_MERGE, "HEAD"], cwd=repository_root, capture_output=True, text=True)
    require(ancestor.returncode == 0, "PIPE04_ACCEPTED_GIT_LINEAGE_MISSING", "accepted PIPE-04 canonical merge is not an ancestor of execution HEAD")
    binding_contract = _load_object(repository_root / "config/pipe04/model10_wisconsin_development_binding_contract.json", "PIPE04_CONTRACT_MISSING")
    acs_manifest = _load_object(repository_root / "data/manifests/acs_2024_acs5_b11001_wisconsin_tract.source_manifest.json", "ACS_MANIFEST_MISSING")
    tiger_manifest = _load_object(repository_root / "data/manifests/tiger_2024_wisconsin_tract.source_manifest.json", "TIGER_MANIFEST_MISSING")
    geo03 = _load_object(repository_root / "config/geo/geo03_internal_point_membership_spatial_spec.json", "GEO03_AUTHORITY_MISSING")
    require(contract["public_sources"]["acs_manifest_id"] == acs_manifest.get("manifest_id") and contract["public_sources"]["tiger_manifest_id"] == tiger_manifest.get("manifest_id"), "PUBLIC_SOURCE_AUTHORITY_MISMATCH", "MODEL-09 public source identity differs")
    return contract, binding_contract, acs_manifest, tiger_manifest | {"_geo03": geo03}


def _target_rows(binding: Mapping[str, Any]) -> dict[str, float]:
    projection = binding.get("minimum_target_projection")
    require(
        isinstance(projection, Mapping)
        and projection.get("default_deny") is True
        and set(projection.get("allowed_fields", [])) == {"source_observation_lineage", "forecast_vintage", "isolated_sales"},
        "TARGET_SCOPE_MISMATCH",
        "PIPE-04 minimum projection differs from Isolated Sales plus required join lineage",
    )
    denied = {str(value).lower() for value in projection.get("denied_scope", [])}
    require(any("impacted sales" in value for value in denied) and any("non-wisconsin" in value for value in denied), "TARGET_DENIAL_MISSING", "PIPE-04 denied target scope is incomplete")
    rows = projection.get("rows")
    require(isinstance(rows, list), "TARGET_PROJECTION_UNRESOLVED", "PIPE-04 target rows are absent")
    output: dict[str, float] = {}
    for row in rows:
        require(isinstance(row, Mapping) and set(row) == {"source_observation_id", "forecast_vintage", "isolated_sales"}, "TARGET_PROJECTION_SCOPE_VIOLATION", "target row contains fields outside Isolated Sales projection")
        observation_id = row.get("source_observation_id")
        require(isinstance(observation_id, str) and observation_id not in output, "TARGET_OBSERVATION_DUPLICATE", "target observation is missing or duplicate")
        try:
            decimal_value = Decimal(str(row.get("isolated_sales")))
        except InvalidOperation:
            require(False, "TARGET_VALUE_INVALID", "Isolated Sales target is not numeric")
        require(decimal_value.is_finite() and decimal_value >= 0, "TARGET_VALUE_INVALID", "Isolated Sales target must be finite and nonnegative")
        output[observation_id] = float(decimal_value)
    return output


class ProtectedDevelopmentRun:
    """Immutable incomplete-first protected MODEL-09 output run."""

    def __init__(self, protected_root: Path, repository_root: Path, *, development_run_id: str | None = None, package_version: str = PACKAGE_VERSION, supersedes: str | None = None):
        self.protected_root = protected_root.resolve()
        self.repository_root = repository_root.resolve()
        require(not _is_within(self.protected_root, self.repository_root), "PROTECTED_OUTPUT_INSIDE_REPOSITORY", "MODEL-09 output must remain outside Git")
        require(self.protected_root.is_dir(), "PROTECTED_DIRECTORY_UNRESOLVED", "MODEL-09 output root is absent")
        require(bool(re.fullmatch(r"1\.0\.[0-9]+", package_version)), "MODEL09_PACKAGE_VERSION_INVALID", "MODEL-09 package version must be 1.0.x")
        require(supersedes is None if package_version == "1.0.0" else bool(supersedes), "MODEL09_SUPERSESSION_REQUIRED", "corrected MODEL-09 versions require supersedes")
        self.development_run_id = development_run_id or "m09run-" + str(uuid.uuid4())
        require(bool(re.fullmatch(r"m09run-[A-Za-z0-9_-]+", self.development_run_id)), "MODEL09_RUN_ID_INVALID", "MODEL-09 run identity is invalid")
        runs_root = self.protected_root / "model09-runs"
        runs_root.mkdir(exist_ok=True)
        self.run_dir = runs_root / self.development_run_id
        require(not self.run_dir.exists(), "MODEL09_RUN_IMMUTABLE", "MODEL-09 run already exists")
        self.run_dir.mkdir()
        self.package_version = package_version
        self.supersedes = supersedes
        write_json_exclusive(self.run_dir / "development_state.json", {"development_run_id": self.development_run_id, "state": "incomplete", "finalization_state": "not_ready", "package_version": package_version, "supersedes": supersedes})

    def mark_development_consumed(self, observation_count: int) -> None:
        require(observation_count > 0, "DEVELOPMENT_CONSUMPTION_INVALID", "development consumption count must be positive")
        write_json_exclusive(self.run_dir / "development_consumption_state.json", {"development_run_id": self.development_run_id, "state": "DEVELOPMENT_CONSUMED", "observation_count": observation_count, "independent_validation_eligibility": False})

    def finalize(self, semantic_package: Mapping[str, Any]) -> dict[str, str]:
        require(not (self.run_dir / "READY.json").exists(), "MODEL09_RUN_IMMUTABLE", "MODEL-09 run is already ready")
        semantic = copy.deepcopy(dict(semantic_package))
        protected_hash = content_digest(semantic)
        stable = "model09-development:sha256:" + protected_hash
        package = {**semantic, "protected_content_sha256": protected_hash, "stable_development_identity": stable, "protected_content_hash_semantics": "SHA-256 of canonical UTF-8 JSON before adding protected_content_sha256 stable_development_identity and protected_content_hash_semantics."}
        package_path = self.run_dir / "model09_wisconsin_experimental_development_package.json"
        write_json_exclusive(package_path, package)
        nonce = new_nonce()
        commitment = freeze_commitment(protected_hash, nonce)
        nonce_path = self.run_dir / "development_nonce.bin"
        with nonce_path.open("xb") as handle:
            handle.write(nonce)
            handle.flush()
            os.fsync(handle.fileno())
        write_json_exclusive(self.run_dir / "commitment_evidence.json", {"domain": "sprouts-customer-geography/model09/development-commitment/v1", "commitment_sha256": commitment})
        write_json_exclusive(self.run_dir / "development_manifest.json", {"development_run_id": self.development_run_id, "package_id": PACKAGE_ID, "package_version": self.package_version, "state": "ready", "finalization_state": "complete", "supersedes": self.supersedes, "protected_content_sha256": protected_hash, "stable_development_identity": stable, "package_file_sha256": file_sha256(package_path)})
        write_json_exclusive(self.run_dir / "READY.json", {"development_run_id": self.development_run_id, "package_id": PACKAGE_ID, "package_version": self.package_version, "state": "ready", "finalization_state": "complete", "protected_content_sha256": protected_hash, "stable_development_identity": stable, "commitment_sha256": commitment})
        return {"protected_content_sha256": protected_hash, "stable_development_identity": stable, "commitment_sha256": commitment}


@dataclass(frozen=True)
class DevelopmentResult:
    development_run_id: str
    eligible_observation_count: int
    quarantined_observation_count: int
    physical_location_count: int
    repeated_physical_location_count: int
    market_count: int
    candidate_comparison: tuple[Mapping[str, Any], ...]
    selection: Mapping[str, Any]
    max_relative_moe_5mi: float


def execute_protected_development(*, repository_root: Path, resolver: ProtectedHandleResolver, development_run_id: str | None = None, package_version: str = PACKAGE_VERSION, supersedes: str | None = None) -> DevelopmentResult:
    root = repository_root.resolve()
    contract, binding_contract, acs_manifest, tiger_with_geo = verify_repository_authority(root)
    geo03 = tiger_with_geo.pop("_geo03")
    tiger_manifest = tiger_with_geo
    request = resolver.development_request
    pipe04_binding_resource = resolver.resolve(str(request["pipe04_binding_handle"]), "pipe04_binding")
    pipe04_ready_resource = resolver.resolve(str(request["pipe04_ready_marker_handle"]), "pipe04_ready_marker")
    model10_resource = resolver.resolve(str(request["model10_package_handle"]), "model10_package")
    model10_ready_resource = resolver.resolve(str(request["model10_ready_marker_handle"]), "model10_ready_marker")
    acs_resource = resolver.resolve(str(request["acs_source_handle"]), "accepted_acs_b11001_source")
    tiger_resource = resolver.resolve(str(request["tiger_source_handle"]), "accepted_tiger_tract_source")
    output_resource = resolver.resolve(str(request["model09_output_root_handle"]), "model09_output_root")
    staged = ProtectedDevelopmentRun(output_resource.path, root, development_run_id=development_run_id, package_version=package_version, supersedes=supersedes)

    binding = verify_pipe04_binding(pipe04_binding_resource.path, pipe04_ready_resource.path)
    model10 = verify_model10_package(model10_resource.path, model10_ready_resource.path)
    cohort = reconcile_fixed_cohort(binding, model10)
    targets = _target_rows(binding)
    require(set(targets) == {str(row["source_observation_id"]) for row in cohort}, "COMPLETE_COHORT_ACCOUNTING_FAILED", "targets do not cover the complete fixed cohort")
    staged.mark_development_consumed(len(targets))
    public_tracts = load_public_tract_evidence(tiger_source=tiger_resource.path, acs_source=acs_resource.path, tiger_manifest=tiger_manifest, acs_manifest=acs_manifest, geo03_spec=geo03)
    featured = build_public_features(cohort, public_tracts, geo03)
    rows = [{**row, "isolated_sales": targets[str(row["source_observation_id"])]} for row in featured]
    comparison, fitted, selection, oof = compare_candidates(rows, contract)
    preferred_id = selection["preferred_candidate_id"]
    fitted_by_id: dict[str, FittedCandidate] = {model.candidate_id: model for model in fitted}
    observations: list[dict[str, Any]] = []
    for row_index, row in enumerate(rows):
        observation_id = str(row["source_observation_id"])
        full_predictions = {model.candidate_id: model.predict(row) for model in fitted}
        preferred = fitted_by_id.get(str(preferred_id)) if preferred_id is not None else None
        observations.append(
            {
                **dict(row),
                "development_consumption_state": "DEVELOPMENT_CONSUMED",
                "candidate_oof_predictions": {candidate_id: values[row_index] for candidate_id, values in oof.items()},
                "candidate_full_cohort_predictions": full_predictions,
                "candidate_full_cohort_residuals": {candidate_id: float(row["isolated_sales"]) - value for candidate_id, value in full_predictions.items()},
                "preferred_customer_fit_proxy_factor": None if preferred is None else preferred.fit_proxy_factor(row),
                "preferred_modeled_target_mass": None if preferred is None else preferred.predict(row),
                "household_opportunity": row["features"]["households_5mi"],
            }
        )
    physical_counts: dict[str, int] = {}
    for row in rows:
        key = str(row["successor_physical_location_id"])
        physical_counts[key] = physical_counts.get(key, 0) + 1
    quarantined_count = int(binding.get("cohort_freeze", {}).get("quarantined_observation_count", 0))
    semantic = {
        "$schema": PACKAGE_SCHEMA,
        "package_id": PACKAGE_ID,
        "version": package_version,
        "development_run_id": staged.development_run_id,
        "state": "ready",
        "authority": {
            "model09_contract_id": CONTRACT_ID,
            "pipe04_contract_id": binding_contract.get("artifact_id"),
            "pipe04_substantive_h": ACCEPTED_PIPE04_H,
            "pipe04_acceptance_record_a": ACCEPTED_PIPE04_A,
            "pipe04_canonical_merge": ACCEPTED_PIPE04_MERGE,
            "pipe04_ready_verified": True,
            "model10_ready_verified": True,
            "protected_handle_registry_identity": resolver.registry_identity,
        },
        "evidence_accounting": {
            "eligible_observation_count": len(rows),
            "target_observation_count": len(targets),
            "quarantined_observation_count": quarantined_count,
            "physical_location_count": len(physical_counts),
            "repeated_physical_location_count": sum(count > 1 for count in physical_counts.values()),
            "market_count": len({str(row["market"]) for row in rows}),
            "isolated_sales_values_consumed": len(targets),
            "impacted_sales_values_accessed": 0,
            "non_wisconsin_target_values_accessed": 0,
            "identity_or_membership_changed_by_target": False,
            "complete_cohort_accounted": True,
        },
        "feature_authority": {
            "acs_manifest_id": acs_manifest.get("manifest_id"),
            "acs_source_sha256": acs_manifest.get("byte_sha256"),
            "tiger_manifest_id": tiger_manifest.get("manifest_id"),
            "tiger_source_sha256": tiger_manifest.get("byte_sha256"),
            "geo03_operation_fingerprint": geo03.get("transformation", {}).get("operation_fingerprint_sha256"),
            "target_blind": True,
            "complete_feature_rows": len(rows),
        },
        "candidate_comparison": comparison,
        "selection": selection,
        "fitted_models": [model.protected_parameters() for model in fitted],
        "observations": observations,
        "consumption": {
            "state": "DEVELOPMENT_CONSUMED",
            "observation_count": len(rows),
            "historical_records_rewritten": False,
            "eligible_for_untouched_independent_validation_of_this_version": False,
        },
        "finalization": {
            "bounded_candidate_search_preserved": True,
            "physical_location_grouped_diagnostics": True,
            "row_level_folding_used": False,
            "household_opportunity_customer_fit_and_modeled_mass_separate": True,
            "protected_observation_outputs_outside_git": True,
            "independent_validation_claimed": False,
            "ready_marker_written_last": True,
        },
        "supersedes": supersedes,
        "supersession_policy": "Never overwrite a MODEL-09 development run. A correction requires a new patch version opaque run ID and explicit supersedes lineage.",
    }
    staged.finalize(semantic)
    return DevelopmentResult(
        staged.development_run_id,
        len(rows),
        quarantined_count,
        len(physical_counts),
        sum(count > 1 for count in physical_counts.values()),
        len({str(row["market"]) for row in rows}),
        tuple(comparison),
        selection,
        max(float(row["features"]["relative_moe_5mi"]) for row in rows),
    )


def build_disclosure_safe_result(result: DevelopmentResult) -> dict[str, Any]:
    report = {
        "completion_state": "MODEL-09 protected development ready",
        "evidence_role": "DEVELOPMENT_ONLY_NOT_INDEPENDENT_VALIDATION",
        "eligible_observation_count": result.eligible_observation_count,
        "quarantined_observation_count": result.quarantined_observation_count,
        "physical_location_count": result.physical_location_count,
        "repeated_physical_location_count": result.repeated_physical_location_count,
        "market_count": result.market_count,
        "isolated_sales_values_consumed": result.eligible_observation_count,
        "impacted_sales_values_accessed": 0,
        "non_wisconsin_target_values_accessed": 0,
        "candidate_metrics": [
            {
                "candidate_id": item["candidate_id"],
                "grouped_spearman": round(item["grouped_oof"]["spearman"], 4),
                "grouped_kendall_tau_b": round(item["grouped_oof"]["kendall_tau_b"], 4),
                "grouped_log_rmse": round(item["grouped_oof"]["log_rmse"], 4),
                "market_holdout_spearman": round(item["leave_one_market_out"]["spearman"], 4),
            }
            for item in result.candidate_comparison
        ],
        "preferred_candidate_id": result.selection["preferred_candidate_id"],
        "selection_conclusion": result.selection["conclusion"],
        "maximum_relative_moe_5mi": round(result.max_relative_moe_5mi, 4),
        "complete_cohort_accounted": True,
        "development_consumption_applied": True,
        "identity_or_membership_changed_by_target": False,
        "protected_output_outside_git": True,
        "protected_details_disclosed": False,
    }
    serialized = json.dumps(report, sort_keys=True).lower()
    for forbidden in ("source_observation", "physical_location_id", "latitude", "longitude", "isolated_sales\":", "residual", "coefficient", "nonce", "sha256", "\\\\", ":\\"):
        require(forbidden not in serialized, "DISCLOSURE_SAFE_REPORT_VIOLATION", "protected detail entered MODEL-09 report")
    return report
