"""PIPE-05 MODEL-12 cohort verification, target binding, and finalization."""

from __future__ import annotations

import copy
from dataclasses import dataclass
import hmac
import json
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

from sprouts_customer_geography.model12.materialization import FEATURE_PACKAGE_ID, SCORING_PACKAGE_ID
from sprouts_customer_geography.model12.source import IDENTITY_PACKAGE_ID, validate_identity_package
from sprouts_customer_geography.pipe01.canonical import content_digest, file_sha256
from sprouts_customer_geography.pipe01.commitment import DOMAIN_SEPARATOR, freeze_commitment
from sprouts_customer_geography.pipe01.errors import ConformanceError, require
from sprouts_customer_geography.pipe02.resolver import _is_within
from sprouts_customer_geography.pipe04.binding import ProtectedBindingRun as _AcceptedProtectedBindingRun

from .contract import (
    ACCEPTED_MODEL12_A,
    ACCEPTED_MODEL12_H,
    ACCEPTED_MODEL12_MERGE,
    CONTRACT_ID,
    CONTRACT_VERSION,
    MODEL12_EXECUTION_COMMITMENT_ID,
    MODEL12_PHYSICAL_LOCATION_COUNT,
    MODEL12_SOURCE_OBSERVATION_COUNT,
    load_model12_execution_commitment,
    verify_repository_authority,
)
from .resolver import ProtectedHandleResolver, STAGE_NAMES
from .xlsx_projection import MichiganIsolatedSalesProjectionPolicy, TargetAccessAudit, project_authorized_isolated_sales


BINDING_PACKAGE_ID = "PIPE05_MODEL12_MICHIGAN_ISOLATED_SALES_BINDING_V1"
BINDING_PACKAGE_VERSION = "1.0.0"
BINDING_SCHEMA_VERSION = "pipe05-model12-michigan-isolated-sales-binding-v1"
BINDING_FILENAME = "pipe05_model12_michigan_isolated_sales_binding.json"
EXECUTION_COMMITMENT_ID = "PIPE05_MICHIGAN_ISOLATED_SALES_BINDING_EXECUTION_COMMITMENT_V1"
PROJECTION_ID = MichiganIsolatedSalesProjectionPolicy.PROJECTION_ID
PROJECTION_VERSION = MichiganIsolatedSalesProjectionPolicy.VERSION
STAGE_PACKAGE_IDS = {"identity": IDENTITY_PACKAGE_ID, "public_features": FEATURE_PACKAGE_ID, "frozen_scoring": SCORING_PACKAGE_ID}
STAGE_KINDS = {
    "identity": "model12_identity",
    "public_features": "model12_public_features",
    "frozen_scoring": "model12_frozen_scoring",
}


def _load_object(path: Path, code: str) -> dict[str, Any]:
    require(path.is_file(), code, "required protected JSON is absent")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ConformanceError(code, "required protected JSON is unreadable") from exc
    require(isinstance(value, dict), code, "required protected JSON must be an object")
    return value


def _verify_stage(
    resolver: ProtectedHandleResolver,
    stage_name: str,
    handles: Mapping[str, Any],
    expected_commitment: str,
) -> dict[str, Any]:
    kind = STAGE_KINDS[stage_name]
    package = resolver.resolve(str(handles["package_handle"]), f"{kind}_package")
    ready_handle = resolver.resolve(str(handles["ready_marker_handle"]), f"{kind}_ready_marker")
    evidence_handle = resolver.resolve(str(handles["commitment_evidence_handle"]), f"{kind}_commitment_evidence")
    nonce_handle = resolver.resolve(str(handles["commitment_nonce_handle"]), f"{kind}_commitment_nonce")
    ready = _load_object(ready_handle.path, "MODEL12_STAGE_READY_UNRESOLVED")
    evidence = _load_object(evidence_handle.path, "MODEL12_STAGE_COMMITMENT_EVIDENCE_UNRESOLVED")
    try:
        nonce = nonce_handle.path.read_bytes()
    except OSError as exc:
        raise ConformanceError("MODEL12_STAGE_COMMITMENT_NONCE_UNRESOLVED", "MODEL-12 stage verification nonce is unreadable") from exc
    require(len(nonce) >= 16, "MODEL12_STAGE_COMMITMENT_NONCE_INVALID", "MODEL-12 stage verification nonce is invalid")
    package_file_hash = file_sha256(package.path)
    computed = freeze_commitment(package_file_hash, nonce)
    require(
        ready.get("stage") == stage_name
        and ready.get("state") == "ready"
        and ready.get("finalization_state") == "complete"
        and ready.get("package_id") == STAGE_PACKAGE_IDS[stage_name]
        and ready.get("package_version") == "1.0.0"
        and ready.get("package_file_sha256") == package_file_hash
        and ready.get("commitment_sha256") == expected_commitment
        and ready.get("ready_marker_written_last") is True
        and evidence.get("domain") == f"sprouts-customer-geography/model12/{stage_name}-commitment/v1"
        and evidence.get("commitment_sha256") == expected_commitment
        and evidence.get("protected_package_digest_disclosed") is False
        and evidence.get("nonce_disclosed") is False
        and evidence.get("protected_content_disclosed") is False
        and hmac.compare_digest(computed, expected_commitment),
        "MODEL12_PROTECTED_STAGE_AUTHORITY_MISMATCH",
        "protected MODEL-12 stage cannot be reconciled to accepted commitment authority",
    )
    return {
        "stage_name": stage_name,
        "package_handle": package.handle,
        "ready_marker_handle": ready_handle.handle,
        "commitment_evidence_handle": evidence_handle.handle,
        "commitment_nonce_handle": nonce_handle.handle,
        "package_path": package.path,
        "package_file_sha256": package_file_hash,
        "protected_content_sha256": ready.get("protected_content_sha256"),
        "commitment_sha256": expected_commitment,
    }


def verify_model12_protected_authority(
    *,
    repository_root: Path,
    resolver: ProtectedHandleResolver,
    contract: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Verify both accepted MODEL-12 runs without materializing predictions."""

    repository_commitment = load_model12_execution_commitment(repository_root, contract)
    expected_runs = {int(item["ordinal"]): item for item in repository_commitment["independent_materializations"]}
    aggregate = repository_commitment["aggregate_conformance"]
    verified_runs: list[dict[str, Any]] = []
    identity_packages: list[dict[str, Any]] = []
    for materialization in resolver.materialization_authorities:
        ordinal = int(materialization["ordinal"])
        expected = expected_runs.get(ordinal)
        require(isinstance(expected, Mapping) and expected.get("state") == "ready", "MODEL12_MATERIALIZATION_AUTHORITY_MISMATCH", "accepted MODEL-12 materialization ordinal is absent")
        root_ready_handle = resolver.resolve(str(materialization["run_ready_marker_handle"]), "model12_materialization_ready_marker")
        root_ready = _load_object(root_ready_handle.path, "MODEL12_RUN_READY_UNRESOLVED")
        stages: dict[str, dict[str, Any]] = {}
        for stage_name in STAGE_NAMES:
            stages[stage_name] = _verify_stage(resolver, stage_name, materialization["stages"][stage_name], str(expected["stage_commitments"][stage_name]))
        ready_stages = root_ready.get("stages")
        ready_aggregate = root_ready.get("aggregate_conformance")
        require(
            root_ready.get("state") == "ready"
            and root_ready.get("finalization_state") == "complete"
            and root_ready.get("package_id") == "MODEL12_MICHIGAN_TARGET_BLIND_FROZEN_SCORING_RUN_V1"
            and root_ready.get("package_version") == "1.0.0"
            and root_ready.get("ready_marker_written_last") is True
            and isinstance(ready_stages, Mapping)
            and all(ready_stages.get(stage, {}).get("commitment_sha256") == stages[stage]["commitment_sha256"] for stage in STAGE_NAMES)
            and isinstance(ready_aggregate, Mapping)
            and ready_aggregate.get("source_observation_count") == aggregate.get("source_observation_count")
            and ready_aggregate.get("physical_location_count") == aggregate.get("physical_location_count")
            and ready_aggregate.get("quarantined_physical_location_count") == aggregate.get("quarantined_physical_location_count")
            and ready_aggregate.get("computable_frozen_score_physical_location_count") == aggregate.get("computable_frozen_score_physical_location_count")
            and ready_aggregate.get("noncomputable_frozen_score_physical_location_count") == aggregate.get("noncomputable_frozen_score_physical_location_count"),
            "MODEL12_RUN_READY_AUTHORITY_MISMATCH",
            "protected MODEL-12 run READY accounting differs from accepted authority",
        )
        identity = _load_object(Path(stages["identity"]["package_path"]), "MODEL12_IDENTITY_PACKAGE_UNRESOLVED")
        validate_identity_package(identity)
        require(
            identity.get("protected_content_sha256") == stages["identity"]["protected_content_sha256"]
            and identity.get("stable_package_identity") == "model12-identity:sha256:" + str(stages["identity"]["protected_content_sha256"])
            and identity.get("contract_authority", {}).get("content_sha256") == contract["accepted_model12_authority"]["contract_content_sha256"],
            "MODEL12_IDENTITY_AUTHORITY_MISMATCH",
            "protected MODEL-12 identity package differs from accepted contract lineage",
        )
        identity_packages.append(identity)
        verified_runs.append({"ordinal": ordinal, "run_ready_marker_handle": root_ready_handle.handle, "stages": {stage: {key: stages[stage][key] for key in ("package_handle", "ready_marker_handle", "commitment_evidence_handle", "commitment_nonce_handle", "commitment_sha256")} for stage in STAGE_NAMES}})

    require(len(verified_runs) == 2 and [item["ordinal"] for item in verified_runs] == [1, 2], "MODEL12_MATERIALIZATION_AUTHORITY_MISMATCH", "exact accepted MODEL-12 materialization pair was not verified")
    for stage in STAGE_NAMES:
        hashes = [
            _verify_stage(
                resolver,
                stage,
                resolver.materialization_authorities[index]["stages"][stage],
                str(expected_runs[index + 1]["stage_commitments"][stage]),
            )["package_file_sha256"]
            for index in range(2)
        ]
        require(hashes[0] == hashes[1], "MODEL12_DETERMINISTIC_MATERIALIZATION_MISMATCH", "accepted MODEL-12 semantic stage packages are not byte-identical")
    require(identity_packages[0] == identity_packages[1], "MODEL12_DETERMINISTIC_MATERIALIZATION_MISMATCH", "accepted MODEL-12 identity packages differ")
    primary = identity_packages[0]
    require(
        primary.get("source_authority", {}).get("source_authority_id") == resolver.source_authority.get("source_authority_id")
        and primary.get("aggregate_conformance", {}).get("source_observation_count") == MODEL12_SOURCE_OBSERVATION_COUNT
        and primary.get("aggregate_conformance", {}).get("physical_location_count") == MODEL12_PHYSICAL_LOCATION_COUNT,
        "MODEL12_SOURCE_AUTHORITY_MISMATCH",
        "accepted MODEL-12 identity source or aggregate differs from PIPE-05 source authority",
    )
    authority = {
        "repository_contract_id": contract["accepted_model12_authority"]["contract_artifact_id"],
        "repository_execution_commitment_id": MODEL12_EXECUTION_COMMITMENT_ID,
        "substantive_h": ACCEPTED_MODEL12_H,
        "acceptance_record_a": ACCEPTED_MODEL12_A,
        "canonical_merge": ACCEPTED_MODEL12_MERGE,
        "identity_package_id": IDENTITY_PACKAGE_ID,
        "frozen_scoring_package_id": SCORING_PACKAGE_ID,
        "independent_materialization_count": 2,
        "semantic_stage_count": 3,
        "semantic_packages_byte_identical": True,
        "aggregate_conformance_identical": True,
        "protected_materializations": verified_runs,
        "prediction_body_materialized_by_pipe05": False,
        "identity_recomputed_or_reinterpreted": False,
    }
    return primary, authority


def derive_target_binding_cohort(identity: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Freeze every and only nonquarantined MODEL-12 source observation."""

    validate_identity_package(identity)
    observations = identity["source_observations"]
    locations = identity["physical_locations"]
    require(len(observations) == MODEL12_SOURCE_OBSERVATION_COUNT and len(locations) == MODEL12_PHYSICAL_LOCATION_COUNT, "MODEL12_COMPLETE_SOURCE_ACCOUNTING_FAILED", "accepted MODEL-12 aggregate differs")
    by_location = {str(item["physical_location_id"]): item for item in locations}
    eligible: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    seen_observations: set[str] = set()
    seen_rows: set[int] = set()
    for observation in observations:
        observation_id = observation.get("source_observation_id")
        physical_id = str(observation.get("physical_location_id"))
        location = by_location.get(physical_id)
        lineage = observation.get("source_observation_lineage")
        require(isinstance(observation_id, str) and observation_id.startswith("m12obs-") and observation_id not in seen_observations, "MODEL12_SOURCE_OBSERVATION_INVALID", "accepted MODEL-12 observation is missing or duplicate")
        require(isinstance(location, Mapping) and isinstance(lineage, Mapping), "MODEL12_IDENTITY_MEMBERSHIP_MISMATCH", "accepted MODEL-12 identity membership or lineage is absent")
        selected_lineage = {
            "source_authority_id": lineage.get("source_authority_id"),
            "source_projection_id": lineage.get("source_projection_id"),
            "source_projection_row": lineage.get("source_projection_row"),
            "source_seed_point_id": lineage.get("source_seed_point_id"),
            "forecast_vintage_original": lineage.get("forecast_vintage_original"),
        }
        row_number = selected_lineage["source_projection_row"]
        require(
            isinstance(selected_lineage["source_authority_id"], str) and bool(selected_lineage["source_authority_id"])
            and selected_lineage["source_projection_id"] == "MODEL12_TARGET_BLIND_IDENTITY_PROJECTION_V1"
            and isinstance(row_number, int) and row_number >= 2 and row_number not in seen_rows
            and isinstance(selected_lineage["source_seed_point_id"], str) and bool(selected_lineage["source_seed_point_id"])
            and isinstance(selected_lineage["forecast_vintage_original"], str) and bool(selected_lineage["forecast_vintage_original"]),
            "MODEL12_SOURCE_LINEAGE_INCOMPLETE",
            "accepted MODEL-12 source-observation lineage is incomplete or duplicate",
        )
        quarantined = location.get("quarantined") is True
        require((observation.get("quarantined") is True) == quarantined and observation.get("target_access_state") == "NOT_ACCESSED_BY_MODEL12", "MODEL12_QUARANTINE_OR_TARGET_STATE_MISMATCH", "accepted MODEL-12 quarantine or target state differs")
        item = {
            "source_observation_id": observation_id,
            "source_observation_lineage": selected_lineage,
            "physical_location_id": physical_id,
            "forecast_vintage": observation.get("forecast_vintage"),
            "source_market_lineage": observation.get("source_market_lineage"),
            "identity_state": observation.get("identity_state"),
            "quarantined": quarantined,
            "target_binding_eligible": not quarantined,
        }
        require(isinstance(item["forecast_vintage"], int) and isinstance(item["source_market_lineage"], str) and bool(item["source_market_lineage"]), "MODEL12_SOURCE_LINEAGE_INCOMPLETE", "accepted MODEL-12 vintage or market lineage is incomplete")
        (excluded if quarantined else eligible).append(item)
        seen_observations.add(observation_id)
        seen_rows.add(int(row_number))
    require(len(eligible) + len(excluded) == MODEL12_SOURCE_OBSERVATION_COUNT and eligible and excluded, "MODEL12_COMPLETE_SOURCE_ACCOUNTING_FAILED", "MODEL-12 eligible/quarantine partition is incomplete")
    physical_lineage = [
        {
            "physical_location_id": item["physical_location_id"],
            "quarantined": item["quarantined"],
            "quarantine_reason": item.get("quarantine_reason"),
            "canonical_anchor_source_observation_id": item.get("canonical_anchor_source_observation_id"),
            "source_observation_ids": copy.deepcopy(item["source_observation_ids"]),
            "source_vintages": copy.deepcopy(item["source_vintages"]),
            "source_market_lineage_values": copy.deepcopy(item["source_market_lineage_values"]),
        }
        for item in locations
    ]
    return eligible, excluded, physical_lineage


def _identity_only(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "source_observation_id": row["source_observation_id"],
            "source_observation_lineage": copy.deepcopy(row["source_observation_lineage"]),
            "physical_location_id": row["physical_location_id"],
            "forecast_vintage": row["forecast_vintage"],
            "source_market_lineage": row["source_market_lineage"],
            "identity_state": row["identity_state"],
            "quarantined": row["quarantined"],
            "target_binding_eligible": row["target_binding_eligible"],
        }
        for row in rows
        if row.get("target_binding_eligible") is True
    ]


def validate_semantic_package(package: Mapping[str, Any]) -> None:
    required = {"$schema", "package_id", "version", "binding_run_id", "state", "contract_authority", "model12_authority", "source_observation_accounting", "physical_location_lineage", "cohort_freeze", "target_source_authority", "minimum_target_projection", "evidence_role", "execution_boundary", "protected_handle_registry_identity", "finalization", "supersedes", "supersession_policy"}
    require(set(package) == required, "BINDING_PACKAGE_SCHEMA_INVALID", "protected package fields differ from PIPE-05")
    require(package.get("$schema") == BINDING_SCHEMA_VERSION and package.get("package_id") == BINDING_PACKAGE_ID and bool(re.fullmatch(r"1\.0\.[0-9]+", str(package.get("version", "")))) and package.get("state") == "ready", "BINDING_IDENTITY_MISMATCH", "binding identity version or state differs")
    authority = package.get("model12_authority")
    require(
        isinstance(authority, Mapping)
        and authority.get("repository_contract_id") == "MODEL12_MICHIGAN_TARGET_BLIND_FROZEN_SCORING_CONTRACT_V1"
        and authority.get("repository_execution_commitment_id") == MODEL12_EXECUTION_COMMITMENT_ID
        and authority.get("substantive_h") == ACCEPTED_MODEL12_H
        and authority.get("acceptance_record_a") == ACCEPTED_MODEL12_A
        and authority.get("canonical_merge") == ACCEPTED_MODEL12_MERGE
        and authority.get("identity_package_id") == IDENTITY_PACKAGE_ID
        and authority.get("frozen_scoring_package_id") == SCORING_PACKAGE_ID
        and authority.get("independent_materialization_count") == 2
        and authority.get("semantic_packages_byte_identical") is True
        and authority.get("prediction_body_materialized_by_pipe05") is False
        and authority.get("identity_recomputed_or_reinterpreted") is False,
        "MODEL12_BINDING_AUTHORITY_MISMATCH",
        "binding does not prove exact accepted MODEL-12 authority",
    )
    rows = package.get("source_observation_accounting")
    physical = package.get("physical_location_lineage")
    require(isinstance(rows, list) and len(rows) == MODEL12_SOURCE_OBSERVATION_COUNT and isinstance(physical, list) and len(physical) == MODEL12_PHYSICAL_LOCATION_COUNT, "MODEL12_COMPLETE_SOURCE_ACCOUNTING_FAILED", "binding does not account for every accepted observation and location")
    observation_ids: set[str] = set()
    eligible_count = valid_count = missing_count = invalid_count = quarantine_count = 0
    for row in rows:
        expected_fields = {"source_observation_id", "source_observation_lineage", "physical_location_id", "forecast_vintage", "source_market_lineage", "identity_state", "quarantined", "target_binding_eligible", "target_status", "isolated_sales", "target_status_reason"}
        require(isinstance(row, Mapping) and set(row) == expected_fields, "BINDING_OBSERVATION_SCHEMA_INVALID", "binding observation fields differ")
        observation_id = row.get("source_observation_id")
        require(isinstance(observation_id, str) and observation_id not in observation_ids, "MODEL12_SOURCE_OBSERVATION_INVALID", "binding observation identity is missing or duplicate")
        observation_ids.add(observation_id)
        if row.get("target_binding_eligible") is True:
            eligible_count += 1
            require(row.get("quarantined") is False and row.get("target_status") in {"VALID", "MISSING", "INVALID"}, "TARGET_BINDING_STATUS_INVALID", "eligible observation has an invalid target status")
            if row["target_status"] == "VALID":
                valid_count += 1
                require(isinstance(row.get("isolated_sales"), str) and bool(re.fullmatch(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?", row["isolated_sales"])) and row.get("target_status_reason") is None, "TARGET_BINDING_STATUS_INVALID", "valid target lacks canonical decimal value")
            elif row["target_status"] == "MISSING":
                missing_count += 1
                require(row.get("isolated_sales") is None and row.get("target_status_reason") in {"SOURCE_CELL_ABSENT", "SOURCE_CELL_BLANK"}, "TARGET_BINDING_STATUS_INVALID", "missing target status differs")
            else:
                invalid_count += 1
                require(row.get("isolated_sales") is None and isinstance(row.get("target_status_reason"), str), "TARGET_BINDING_STATUS_INVALID", "invalid target status differs")
        else:
            quarantine_count += 1
            require(row.get("quarantined") is True and row.get("target_status") == "QUARANTINED_EXCLUDED_BEFORE_TARGET_ACCESS" and row.get("isolated_sales") is None and row.get("target_status_reason") == "ACCEPTED_MODEL12_IDENTITY_QUARANTINE", "QUARANTINE_ACCOUNTING_INVALID", "quarantined observation was not excluded before target access")
    freeze = package.get("cohort_freeze")
    require(
        isinstance(freeze, Mapping)
        and freeze.get("established_from_verified_model12_identity_only") is True
        and freeze.get("frozen_before_target_body_access") is True
        and freeze.get("all_source_observation_count") == len(rows)
        and freeze.get("eligible_source_observation_count") == eligible_count
        and freeze.get("quarantine_excluded_source_observation_count") == quarantine_count
        and freeze.get("eligible_cohort_identity_sha256") == content_digest(_identity_only(rows))
        and freeze.get("frozen_score_computability_used_for_eligibility") is False
        and freeze.get("target_content_may_change_identity_or_membership") is False,
        "COHORT_FREEZE_MISMATCH",
        "target-binding cohort freeze proof differs",
    )
    projection = package.get("minimum_target_projection")
    audit = projection.get("target_access_audit") if isinstance(projection, Mapping) else None
    require(
        isinstance(projection, Mapping)
        and projection.get("projection_id") == PROJECTION_ID
        and projection.get("version") == PROJECTION_VERSION
        and projection.get("default_deny") is True
        and set(projection.get("allowed_fields", [])) == MichiganIsolatedSalesProjectionPolicy.ALLOWED_FIELDS
        and isinstance(audit, Mapping)
        and audit.get("authorized_row_count") == eligible_count
        and audit.get("valid_isolated_sales_binding_count") == valid_count
        and audit.get("missing_isolated_sales_count") == missing_count
        and audit.get("invalid_isolated_sales_count") == invalid_count
        and audit.get("impacted_sales_body_decode_calls") == 0
        and audit.get("other_outcome_body_decode_calls") == 0
        and audit.get("quarantined_target_body_decode_calls") == 0
        and audit.get("non_michigan_target_decode_calls") == 0
        and audit.get("broad_preview_performed") is False
        and audit.get("whole_workbook_hash_computed") is False,
        "TARGET_ACCESS_AUDIT_FAILED",
        "target access exceeded the exact permitted projection",
    )
    role = package.get("evidence_role")
    require(isinstance(role, Mapping) and role.get("bound_for_separately_authorized_frozen_benchmark") is True and role.get("binding_marks_development_consumed") is False and role.get("development_consumption_begins_only_on_later_authorized_analytical_use") is True and role.get("permanent_holdout_designation_created") is False, "EVIDENCE_CONSUMPTION_SEMANTICS_INVALID", "binding changed Michigan evidence role")
    boundary = package.get("execution_boundary")
    require(
        isinstance(boundary, Mapping)
        and boundary.get("impacted_sales_body_values_accessed") == 0
        and boundary.get("other_outcome_body_values_accessed") == 0
        and boundary.get("quarantined_target_body_values_accessed") == 0
        and boundary.get("prediction_values_materialized") is False
        and all(boundary.get(field) is False for field in ("benchmark_evaluation_performed", "residuals_calculated", "ranks_calculated", "correlations_calculated", "error_metrics_calculated", "model_fitting_performed", "model_training_performed", "model_tuning_performed", "model_refitting_performed", "model_scoring_performed", "development_consumption_marked")),
        "PIPE05_ANALYTICAL_BOUNDARY_VIOLATION",
        "benchmark model or denied target work entered PIPE-05",
    )
    finalization = package.get("finalization")
    require(isinstance(finalization, Mapping) and finalization.get("cohort_established_before_target_body_access") is True and finalization.get("target_content_invariant_to_identity_and_membership") is True and finalization.get("exact_source_observation_join_complete") is True and finalization.get("quarantine_excluded_before_target_access") is True and finalization.get("ready_marker_written_last") is True, "BINDING_FINALIZATION_CONFORMANCE_FAILED", "binding finalization proof is incomplete")


class ProtectedBindingRun(_AcceptedProtectedBindingRun):
    """PIPE-05 specialization of the accepted PIPE-04 immutable finalizer."""

    def __init__(self, protected_root: Path, repository_root: Path, *, binding_run_id: str | None = None, package_version: str = BINDING_PACKAGE_VERSION, supersedes: str | None = None):
        super().__init__(
            protected_root,
            repository_root,
            binding_run_id=binding_run_id,
            package_version=package_version,
            supersedes=supersedes,
            run_id_prefix="p5bind-",
            collection="pipe05-bindings",
            package_filename=BINDING_FILENAME,
            package_id=BINDING_PACKAGE_ID,
            binding_schema_version=BINDING_SCHEMA_VERSION,
            stable_identity_prefix="pipe05-binding",
            semantic_validator=validate_semantic_package,
            task_label="PIPE-05",
        )


def protected_binding_is_ready(run_dir: Path) -> bool:
    return (run_dir / "READY.json").is_file()


@dataclass(frozen=True)
class BindingResult:
    binding_run_id: str
    run_dir: Path
    protected_content_sha256: str
    stable_binding_identity: str
    commitment_sha256: str
    source_observation_count: int
    eligible_observation_count: int
    unique_bound_physical_location_count: int
    quarantine_excluded_observation_count: int
    target_access_audit: TargetAccessAudit


def _accounting_rows(eligible: Sequence[Mapping[str, Any]], excluded: Sequence[Mapping[str, Any]], projected: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    values = {str(item["source_observation_id"]): item for item in projected}
    require(len(values) == len(projected) == len(eligible), "TARGET_PROJECTION_COMPLETENESS_FAILED", "target rows do not cover the eligible cohort exactly")
    output: list[dict[str, Any]] = []
    for item in [*eligible, *excluded]:
        row = copy.deepcopy(dict(item))
        if row["target_binding_eligible"]:
            target = values.get(str(row["source_observation_id"]))
            require(isinstance(target, Mapping) and target.get("forecast_vintage") == row.get("forecast_vintage"), "TARGET_SOURCE_OBSERVATION_MISMATCH", "target value attached to the wrong accepted observation")
            row.update({"target_status": target["target_status"], "isolated_sales": target["isolated_sales"], "target_status_reason": target["target_status_reason"]})
        else:
            row.update({"target_status": "QUARANTINED_EXCLUDED_BEFORE_TARGET_ACCESS", "isolated_sales": None, "target_status_reason": "ACCEPTED_MODEL12_IDENTITY_QUARANTINE"})
        output.append(row)
    return output


def execute_protected_binding(
    *,
    repository_root: Path,
    resolver: ProtectedHandleResolver,
    binding_run_id: str | None = None,
    package_version: str = BINDING_PACKAGE_VERSION,
    supersedes: str | None = None,
) -> BindingResult:
    root = repository_root.resolve()
    contract = verify_repository_authority(root)
    output = resolver.resolve(str(resolver.binding_request["binding_output_root_handle"]), "pipe05_output_root")
    staged = ProtectedBindingRun(output.path, root, binding_run_id=binding_run_id, package_version=package_version, supersedes=supersedes)
    identity, authority = verify_model12_protected_authority(repository_root=root, resolver=resolver, contract=contract)
    eligible, excluded, physical_lineage = derive_target_binding_cohort(identity)
    frozen_eligible = copy.deepcopy(eligible)
    frozen_excluded = copy.deepcopy(excluded)
    cohort_hash = content_digest(_identity_only(frozen_eligible))

    source = resolver.resolve_source()
    policy = MichiganIsolatedSalesProjectionPolicy(resolver.source_authority["projection"], source.handle, str(resolver.source_authority["source_authority_id"]))
    projected, audit = project_authorized_isolated_sales(source.path, policy, frozen_eligible, frozen_excluded)
    require(frozen_eligible == eligible and frozen_excluded == excluded and cohort_hash == content_digest(_identity_only(eligible)), "TARGET_CONTENT_CHANGED_COHORT", "target access changed frozen MODEL-12 identity or membership")
    accounting = _accounting_rows(frozen_eligible, frozen_excluded, projected)
    unique_bound_locations = len({str(item["physical_location_id"]) for item in frozen_eligible})
    semantic = {
        "$schema": BINDING_SCHEMA_VERSION,
        "package_id": BINDING_PACKAGE_ID,
        "version": package_version,
        "binding_run_id": staged.binding_run_id,
        "state": "ready",
        "contract_authority": {"artifact_id": contract["artifact_id"], "version": contract["version"], "content_sha256": contract["content_sha256"]},
        "model12_authority": authority,
        "source_observation_accounting": accounting,
        "physical_location_lineage": physical_lineage,
        "cohort_freeze": {
            "established_from_verified_model12_identity_only": True,
            "frozen_before_target_body_access": True,
            "all_source_observation_count": len(accounting),
            "eligible_source_observation_count": len(frozen_eligible),
            "quarantine_excluded_source_observation_count": len(frozen_excluded),
            "unique_bound_physical_location_count": unique_bound_locations,
            "eligible_cohort_identity_sha256": cohort_hash,
            "frozen_score_computability_used_for_eligibility": False,
            "target_content_may_change_identity_or_membership": False,
        },
        "target_source_authority": {
            "source_authority_id": resolver.source_authority["source_authority_id"],
            "workbook_handle": source.handle,
            "exact_basename_resolved": True,
            "whole_workbook_hash_computed": False,
            "projection_id": PROJECTION_ID,
            "projection_version": PROJECTION_VERSION,
        },
        "minimum_target_projection": {
            "projection_id": PROJECTION_ID,
            "version": PROJECTION_VERSION,
            "default_deny": True,
            "allowed_fields": sorted(MichiganIsolatedSalesProjectionPolicy.ALLOWED_FIELDS),
            "denied_scope": ["Impacted Sales", "every other outcome or forecast field", "non-Michigan rows", "accepted quarantined observations", "unrelated rows and columns", "candidate or proprietary site scores", "broad worksheet or row previews", "whole-workbook hashing", "target-derived identity cohort quarantine computability or prediction changes"],
            "target_access_audit": audit.disclosure_safe(len(frozen_eligible)),
        },
        "evidence_role": {
            "bound_for_separately_authorized_frozen_benchmark": True,
            "binding_marks_development_consumed": False,
            "development_consumption_begins_only_on_later_authorized_analytical_use": True,
            "permanent_holdout_designation_created": False,
        },
        "execution_boundary": {
            "impacted_sales_body_values_accessed": 0,
            "other_outcome_body_values_accessed": 0,
            "quarantined_target_body_values_accessed": 0,
            "prediction_values_materialized": False,
            "benchmark_evaluation_performed": False,
            "residuals_calculated": False,
            "ranks_calculated": False,
            "correlations_calculated": False,
            "error_metrics_calculated": False,
            "model_fitting_performed": False,
            "model_training_performed": False,
            "model_tuning_performed": False,
            "model_refitting_performed": False,
            "model_scoring_performed": False,
            "development_consumption_marked": False,
        },
        "protected_handle_registry_identity": resolver.registry_identity,
        "finalization": {
            "cohort_established_before_target_body_access": True,
            "target_content_invariant_to_identity_and_membership": True,
            "exact_source_observation_join_complete": True,
            "quarantine_excluded_before_target_access": True,
            "missing_invalid_status_explicit": True,
            "imputation_or_zero_substitution_performed": False,
            "ready_marker_written_last": True,
        },
        "supersedes": supersedes,
        "supersession_policy": "Never overwrite a PIPE-05 binding. A correction requires a new patch version opaque run identity and explicit supersedes lineage.",
    }
    finalized = staged.finalize(semantic)
    return BindingResult(
        staged.binding_run_id,
        staged.run_dir,
        finalized["protected_content_sha256"],
        finalized["stable_binding_identity"],
        finalized["commitment_sha256"],
        len(accounting),
        len(frozen_eligible),
        unique_bound_locations,
        len(frozen_excluded),
        audit,
    )


def verify_persisted_binding(*, repository_root: Path, resolver: ProtectedHandleResolver, run_dir: Path) -> dict[str, Any]:
    """Independently reproject and reconcile one immutable PIPE-05 run."""

    root = repository_root.resolve()
    output = resolver.resolve(str(resolver.binding_request["binding_output_root_handle"]), "pipe05_output_root").path.resolve()
    resolved_run = run_dir.resolve()
    require(_is_within(resolved_run, output / "pipe05-bindings"), "BINDING_VERIFICATION_PATH_INVALID", "PIPE-05 verification run escapes its output root")
    contract = verify_repository_authority(root)
    identity, _authority = verify_model12_protected_authority(repository_root=root, resolver=resolver, contract=contract)
    eligible, excluded, _physical = derive_target_binding_cohort(identity)
    package_path = resolved_run / BINDING_FILENAME
    package = _load_object(package_path, "PIPE05_BINDING_PACKAGE_UNRESOLVED")
    semantic = copy.deepcopy(package)
    protected_hash = semantic.pop("protected_content_sha256", None)
    stable = semantic.pop("stable_binding_identity", None)
    semantic.pop("protected_content_hash_semantics", None)
    validate_semantic_package(semantic)
    require(protected_hash == content_digest(semantic) and stable == "pipe05-binding:sha256:" + str(protected_hash), "PIPE05_PROTECTED_CONTENT_MISMATCH", "persisted PIPE-05 semantic content differs")
    manifest = _load_object(resolved_run / "binding_manifest.json", "PIPE05_BINDING_MANIFEST_UNRESOLVED")
    ready = _load_object(resolved_run / "READY.json", "PIPE05_BINDING_READY_UNRESOLVED")
    evidence = _load_object(resolved_run / "commitment_evidence.json", "PIPE05_BINDING_COMMITMENT_UNRESOLVED")
    try:
        nonce = (resolved_run / "binding_nonce.bin").read_bytes()
    except OSError as exc:
        raise ConformanceError("PIPE05_BINDING_NONCE_UNRESOLVED", "PIPE-05 verification nonce is unreadable") from exc
    commitment = freeze_commitment(content_digest(manifest), nonce)
    require(
        manifest.get("package_id") == BINDING_PACKAGE_ID
        and manifest.get("protected_content_sha256") == protected_hash
        and manifest.get("package_file_sha256") == file_sha256(package_path)
        and ready.get("state") == "ready"
        and ready.get("package_id") == BINDING_PACKAGE_ID
        and ready.get("protected_content_sha256") == protected_hash
        and ready.get("commitment_sha256") == commitment
        and evidence.get("domain") == DOMAIN_SEPARATOR.decode("utf-8")
        and evidence.get("commitment_sha256") == commitment,
        "PIPE05_BINDING_FINALIZATION_MISMATCH",
        "PIPE-05 manifest commitment or READY binding differs",
    )
    source = resolver.resolve_source()
    policy = MichiganIsolatedSalesProjectionPolicy(resolver.source_authority["projection"], source.handle, str(resolver.source_authority["source_authority_id"]))
    projected, audit = project_authorized_isolated_sales(source.path, policy, eligible, excluded)
    persisted = {
        str(row["source_observation_id"]): (row["forecast_vintage"], row["target_status"], row["isolated_sales"], row["target_status_reason"])
        for row in package["source_observation_accounting"]
        if row["target_binding_eligible"] is True
    }
    reprojection = {str(row["source_observation_id"]): (row["forecast_vintage"], row["target_status"], row["isolated_sales"], row["target_status_reason"]) for row in projected}
    require(persisted == reprojection, "PIPE05_DETERMINISTIC_BINDING_MISMATCH", "persisted binding differs from independent minimum reprojection")
    return {
        "state": "MATCH",
        "source_observation_accounting_identical": True,
        "eligible_cohort_identity_identical": package["cohort_freeze"]["eligible_cohort_identity_sha256"] == content_digest(_identity_only(eligible)),
        "minimum_target_projection_identical": True,
        "protected_content_verified": True,
        "ready_commitment_verified": True,
        "valid_isolated_sales_binding_count": audit.valid_isolated_sales_decode_calls,
        "missing_isolated_sales_count": audit.missing_isolated_sales_count,
        "invalid_isolated_sales_count": audit.invalid_isolated_sales_count,
        "impacted_sales_body_values_accessed": 0,
        "other_outcome_body_values_accessed": 0,
        "quarantined_target_body_values_accessed": 0,
        "benchmark_evaluation_performed": False,
        "model_work_performed": False,
        "protected_details_disclosed": False,
    }


def build_disclosure_safe_result(result: BindingResult, verification: Mapping[str, Any]) -> dict[str, Any]:
    report = {
        "completion_state": "PIPE-05 protected Michigan Isolated Sales binding ready",
        "source_observation_count": result.source_observation_count,
        "target_binding_eligible_source_observation_count": result.eligible_observation_count,
        "unique_bound_physical_location_count": result.unique_bound_physical_location_count,
        "quarantine_excluded_source_observation_count": result.quarantine_excluded_observation_count,
        "valid_isolated_sales_binding_count": result.target_access_audit.valid_isolated_sales_decode_calls,
        "missing_or_invalid_isolated_sales_count": result.target_access_audit.missing_isolated_sales_count + result.target_access_audit.invalid_isolated_sales_count,
        "deterministic_binding_verification": verification.get("state") == "MATCH",
        "impacted_sales_body_values_accessed": 0,
        "other_outcome_body_values_accessed": 0,
        "benchmark_evaluation_performed": False,
        "model_fitting_training_tuning_or_scoring_performed": False,
        "development_consumption_marked": False,
        "protected_output_outside_git": True,
        "protected_details_disclosed": False,
    }
    serialized = json.dumps(report, sort_keys=True).lower()
    for forbidden in ("source_row", "seed_point", "physical_location_id", "cell_address", "nonce", "commitment_sha256", "protected_content_sha256", "stable_binding_identity", "latitude", "longitude", "\\", ":\\"):
        require(forbidden not in serialized, "DISCLOSURE_SAFE_REPORT_VIOLATION", "protected detail entered PIPE-05 report")
    return report


def build_repository_execution_commitment(result: BindingResult, verification: Mapping[str, Any], contract: Mapping[str, Any]) -> dict[str, Any]:
    """Build nondisclosing aggregate exact-H evidence from one verified run."""

    semantic: dict[str, Any] = {
        "$schema": "../../schemas/pipe05/michigan_isolated_sales_binding_execution_commitment.schema.json",
        "artifact_id": EXECUTION_COMMITMENT_ID,
        "version": "1.0.0",
        "status": "completed_awaiting_acceptance",
        "contract_authority": {"artifact_id": CONTRACT_ID, "version": CONTRACT_VERSION, "content_sha256": contract["content_sha256"]},
        "accepted_model12_authority": {
            "repository_contract_id": "MODEL12_MICHIGAN_TARGET_BLIND_FROZEN_SCORING_CONTRACT_V1",
            "repository_execution_commitment_id": MODEL12_EXECUTION_COMMITMENT_ID,
            "substantive_h": ACCEPTED_MODEL12_H,
            "acceptance_record_a": ACCEPTED_MODEL12_A,
            "canonical_merge": ACCEPTED_MODEL12_MERGE,
            "source_observation_count": MODEL12_SOURCE_OBSERVATION_COUNT,
            "physical_location_count": MODEL12_PHYSICAL_LOCATION_COUNT,
            "independent_materialization_count": 2,
            "protected_identity_and_frozen_scoring_lineage_verified": True,
            "individual_predictions_materialized_by_pipe05": False,
        },
        "aggregate_conformance": {
            "source_observation_count": result.source_observation_count,
            "target_binding_eligible_source_observation_count": result.eligible_observation_count,
            "unique_bound_physical_location_count": result.unique_bound_physical_location_count,
            "quarantine_excluded_source_observation_count": result.quarantine_excluded_observation_count,
            "valid_isolated_sales_binding_count": result.target_access_audit.valid_isolated_sales_decode_calls,
            "missing_isolated_sales_count": result.target_access_audit.missing_isolated_sales_count,
            "invalid_isolated_sales_count": result.target_access_audit.invalid_isolated_sales_count,
            "missing_or_invalid_isolated_sales_count": result.target_access_audit.missing_isolated_sales_count + result.target_access_audit.invalid_isolated_sales_count,
            "complete_source_observation_accounting": True,
            "complete_target_binding_accounting": True,
        },
        "deterministic_binding_verification": {
            "state": verification["state"],
            "source_observation_accounting_identical": verification["source_observation_accounting_identical"],
            "eligible_cohort_identity_identical": verification["eligible_cohort_identity_identical"],
            "minimum_target_projection_identical": verification["minimum_target_projection_identical"],
            "protected_content_verified": verification["protected_content_verified"],
            "ready_commitment_verified": verification["ready_commitment_verified"],
        },
        "execution_boundary": {
            "cohort_frozen_before_target_body_access": True,
            "quarantine_excluded_before_target_access": True,
            "impacted_sales_body_values_accessed": 0,
            "other_outcome_body_values_accessed": 0,
            "quarantined_target_body_values_accessed": 0,
            "benchmark_evaluation_performed": False,
            "prediction_values_modified": False,
            "prediction_values_materialized": False,
            "residuals_ranks_correlations_or_error_metrics_calculated": False,
            "model_fitting_training_tuning_refitting_or_scoring_performed": False,
            "development_consumption_marked": False,
            "protected_output_outside_git": True,
        },
        "disclosure_boundary": {
            "protected_package_digest_disclosed": False,
            "commitment_nonce_disclosed": False,
            "protected_paths_or_filenames_disclosed": False,
            "workbook_or_sheet_structure_disclosed": False,
            "observation_or_location_identity_disclosed": False,
            "coordinates_or_market_lineage_disclosed": False,
            "target_values_disclosed": False,
            "predictions_or_model_parameters_disclosed": False,
        },
        "protected_binding_commitment": {
            "domain": DOMAIN_SEPARATOR.decode("utf-8"),
            "commitment_sha256": result.commitment_sha256,
            "protected_package_digest_disclosed": False,
            "nonce_disclosed": False,
            "binding_content_disclosed": False,
        },
        "hash_algorithm": "SHA-256",
        "content_hash_semantics": "SHA-256 of canonical UTF-8 JSON after removing content_sha256: recursively sorted object keys, compact separators, Unicode preserved, no NaN.",
    }
    semantic["content_sha256"] = content_digest(semantic)
    return semantic


def build_repository_execution_commitment_from_run(
    *, repository_root: Path, resolver: ProtectedHandleResolver, run_dir: Path
) -> dict[str, Any]:
    """Reconstruct only disclosure-safe completion evidence from a verified run."""

    verification = verify_persisted_binding(repository_root=repository_root, resolver=resolver, run_dir=run_dir)
    package = _load_object(run_dir.resolve() / BINDING_FILENAME, "PIPE05_BINDING_PACKAGE_UNRESOLVED")
    ready = _load_object(run_dir.resolve() / "READY.json", "PIPE05_BINDING_READY_UNRESOLVED")
    freeze = package["cohort_freeze"]
    audit_document = package["minimum_target_projection"]["target_access_audit"]
    audit = TargetAccessAudit(
        authorized_isolated_sales_cell_examinations=int(audit_document["isolated_sales_cells_examined"]),
        valid_isolated_sales_decode_calls=int(audit_document["valid_isolated_sales_binding_count"]),
        missing_isolated_sales_count=int(audit_document["missing_isolated_sales_count"]),
        invalid_isolated_sales_count=int(audit_document["invalid_isolated_sales_count"]),
        impacted_sales_body_decode_calls=int(audit_document["impacted_sales_body_decode_calls"]),
        other_outcome_body_decode_calls=int(audit_document["other_outcome_body_decode_calls"]),
        quarantined_target_body_decode_calls=int(audit_document["quarantined_target_body_decode_calls"]),
        non_michigan_target_decode_calls=int(audit_document["non_michigan_target_decode_calls"]),
    )
    result = BindingResult(
        binding_run_id=str(package["binding_run_id"]),
        run_dir=run_dir.resolve(),
        protected_content_sha256=str(ready["protected_content_sha256"]),
        stable_binding_identity=str(ready["stable_binding_identity"]),
        commitment_sha256=str(ready["commitment_sha256"]),
        source_observation_count=int(freeze["all_source_observation_count"]),
        eligible_observation_count=int(freeze["eligible_source_observation_count"]),
        unique_bound_physical_location_count=int(freeze["unique_bound_physical_location_count"]),
        quarantine_excluded_observation_count=int(freeze["quarantine_excluded_source_observation_count"]),
        target_access_audit=audit,
    )
    contract = verify_repository_authority(repository_root.resolve())
    return build_repository_execution_commitment(result, verification, contract)
