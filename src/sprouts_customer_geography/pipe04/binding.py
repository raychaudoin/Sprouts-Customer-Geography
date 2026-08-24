"""PIPE-04 MODEL-10 cohort verification, target binding, and finalization."""

from __future__ import annotations

import copy
import hmac
import json
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePath
from typing import Any, Mapping

from sprouts_customer_geography.model10.binding import (
    COMMITMENT_ID as MODEL10_COMMITMENT_ID,
    COMMITMENT_VERSION as MODEL10_COMMITMENT_VERSION,
    PACKAGE_ID as MODEL10_PACKAGE_ID,
    PACKAGE_VERSION as MODEL10_PACKAGE_VERSION,
    validate_successor_package,
)
from sprouts_customer_geography.pipe01.canonical import content_digest, file_sha256, write_json_exclusive
from sprouts_customer_geography.pipe01.commitment import DOMAIN_SEPARATOR, freeze_commitment, new_nonce
from sprouts_customer_geography.pipe01.errors import ConformanceError, require
from sprouts_customer_geography.pipe02.resolver import _is_within

from .resolver import ProtectedHandleResolver
from .xlsx_projection import Model10WisconsinProjectionPolicy, TargetAccessAudit, project_authorized_isolated_sales


BINDING_PACKAGE_ID = "PIPE04_MODEL10_WISCONSIN_DEVELOPMENT_BINDING_V1"
BINDING_PACKAGE_VERSION = "1.0.0"
BINDING_SCHEMA_VERSION = "pipe04-model10-wisconsin-development-binding-v1"
CONTRACT_ID = "PIPE04_MODEL10_WISCONSIN_DEVELOPMENT_BINDING_CONTRACT_V1"
CONTRACT_VERSION = "1.0.0"
PROJECTION_ID = Model10WisconsinProjectionPolicy.PROJECTION_ID
PROJECTION_VERSION = Model10WisconsinProjectionPolicy.VERSION
MODEL10_COMMITMENT_DOCUMENT = "config/model/model10_wisconsin_cohort_identity_lineage_commitment.json"
PIPE04_CONTRACT_DOCUMENT = "config/pipe04/model10_wisconsin_development_binding_contract.json"
EXPECTED_MODEL10_COMMITMENT = "b0376662f8f01252f91cd7e0e259180a3cd87c542cdc4f18719cac626a440be6"
ACCEPTED_MODEL10_H = "f199624d16eb42e3e6c6b4d8eb73b8dcd3109dc8"
ACCEPTED_MODEL10_A = "4f4dbf8fdf1f5de9633baa9c088bfece2f44b9e2"
ACCEPTED_MODEL10_MERGE = "c9f97d2a3314a64db583ec9b0ea4f53aeb0b5c1b"


def _load_object(path: Path, code: str) -> dict[str, Any]:
    require(path.is_file(), code, "required JSON authority is absent")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ConformanceError(code, "required JSON authority is unreadable") from exc
    require(isinstance(value, dict), code, "required JSON authority must be an object")
    return value


def verify_model10_authority(
    *,
    repository_root: Path,
    package_path: Path,
    commitment_evidence_path: Path,
    nonce_path: Path,
    ready_path: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Verify accepted repository authority and the exact protected MODEL-10 run."""
    commitment = _load_object(repository_root / MODEL10_COMMITMENT_DOCUMENT, "MODEL10_COMMITMENT_AUTHORITY_MISSING")
    require(
        commitment.get("artifact_id") == MODEL10_COMMITMENT_ID
        and commitment.get("version") == MODEL10_COMMITMENT_VERSION
        and commitment.get("protected_package_id") == MODEL10_PACKAGE_ID
        and commitment.get("protected_package_version") == MODEL10_PACKAGE_VERSION
        and commitment.get("domain") == DOMAIN_SEPARATOR.decode("utf-8")
        and commitment.get("commitment_sha256") == EXPECTED_MODEL10_COMMITMENT
        and commitment.get("protected_package_digest_disclosed") is False
        and commitment.get("nonce_disclosed") is False
        and commitment.get("observation_content_disclosed") is False,
        "MODEL10_COMMITMENT_AUTHORITY_MISMATCH",
        "repository MODEL-10 commitment differs from accepted authority",
    )
    contract = _load_object(repository_root / PIPE04_CONTRACT_DOCUMENT, "PIPE04_CONTRACT_AUTHORITY_MISSING")
    accepted = contract.get("accepted_model10_authority")
    require(
        contract.get("artifact_id") == CONTRACT_ID
        and contract.get("version") == CONTRACT_VERSION
        and isinstance(accepted, Mapping)
        and accepted.get("commitment_id") == MODEL10_COMMITMENT_ID
        and accepted.get("package_id") == MODEL10_PACKAGE_ID
        and accepted.get("substantive_h") == ACCEPTED_MODEL10_H
        and accepted.get("acceptance_record_a") == ACCEPTED_MODEL10_A
        and accepted.get("canonical_merge") == ACCEPTED_MODEL10_MERGE,
        "MODEL10_ACCEPTED_LINEAGE_MISMATCH",
        "PIPE-04 contract does not retain exact accepted MODEL-10 lineage",
    )
    evidence = _load_object(commitment_evidence_path, "MODEL10_COMMITMENT_EVIDENCE_UNRESOLVED")
    ready = _load_object(ready_path, "MODEL10_READY_MARKER_UNRESOLVED")
    package = _load_object(package_path, "MODEL10_PACKAGE_UNRESOLVED")
    try:
        nonce = nonce_path.read_bytes()
    except OSError as exc:
        raise ConformanceError("MODEL10_COMMITMENT_NONCE_UNRESOLVED", "MODEL-10 verification nonce is unreadable") from exc
    require(len(nonce) >= 16, "MODEL10_COMMITMENT_NONCE_INVALID", "MODEL-10 verification nonce is invalid")
    computed = freeze_commitment(file_sha256(package_path), nonce)
    require(
        evidence.get("artifact_id") == MODEL10_COMMITMENT_ID
        and evidence.get("version") == MODEL10_COMMITMENT_VERSION
        and evidence.get("protected_package_id") == MODEL10_PACKAGE_ID
        and evidence.get("protected_package_version") == MODEL10_PACKAGE_VERSION
        and evidence.get("domain") == DOMAIN_SEPARATOR.decode("utf-8")
        and hmac.compare_digest(str(evidence.get("commitment_sha256", "")), EXPECTED_MODEL10_COMMITMENT)
        and hmac.compare_digest(computed, EXPECTED_MODEL10_COMMITMENT),
        "MODEL10_PROTECTED_COMMITMENT_MISMATCH",
        "protected MODEL-10 commitment cannot be reconciled to accepted authority",
    )
    require(
        ready.get("state") == "ready"
        and ready.get("package_id") == MODEL10_PACKAGE_ID
        and ready.get("package_version") == MODEL10_PACKAGE_VERSION
        and ready.get("materialization_run_id") == package.get("materialization_run_id")
        and ready.get("commitment_sha256") == EXPECTED_MODEL10_COMMITMENT,
        "MODEL10_READY_MARKER_MISMATCH",
        "protected MODEL-10 READY marker differs from the verified package",
    )
    require(package.get("package_id") == MODEL10_PACKAGE_ID and package.get("version") == MODEL10_PACKAGE_VERSION and package.get("state") == "ready", "MODEL10_PACKAGE_IDENTITY_MISMATCH", "protected MODEL-10 package identity/state differs")
    validate_successor_package(package)
    protected_hash = package.get("protected_content_sha256")
    semantic = dict(package)
    semantic.pop("protected_content_sha256", None)
    semantic.pop("protected_content_hash_semantics", None)
    require(isinstance(protected_hash, str) and protected_hash == content_digest(semantic) and ready.get("protected_content_sha256") == protected_hash, "MODEL10_PROTECTED_CONTENT_MISMATCH", "MODEL-10 protected content hash differs")
    return package, {
        "commitment_artifact_id": MODEL10_COMMITMENT_ID,
        "commitment_artifact_version": MODEL10_COMMITMENT_VERSION,
        "package_id": MODEL10_PACKAGE_ID,
        "package_version": MODEL10_PACKAGE_VERSION,
        "substantive_h": ACCEPTED_MODEL10_H,
        "acceptance_record_a": ACCEPTED_MODEL10_A,
        "canonical_merge": ACCEPTED_MODEL10_MERGE,
        "commitment_reconciled": True,
        "ready_marker_reconciled": True,
    }


def derive_eligible_wisconsin_cohort(package: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    """Freeze membership exclusively from verified MODEL-10 eligibility authority."""
    records = package.get("records")
    require(isinstance(records, list) and records, "MODEL10_PACKAGE_SCHEMA_INVALID", "MODEL-10 records are absent")
    cohort: list[dict[str, Any]] = []
    projection_input: list[dict[str, Any]] = []
    quarantined_count = 0
    observation_ids: set[str] = set()
    source_rows: set[tuple[str, str, int]] = set()
    for record in records:
        quarantined = record.get("quarantined") is True
        eligible = record.get("model09_development_eligible") is True
        require(eligible is (not quarantined), "MODEL10_ELIGIBILITY_MISMATCH", "MODEL-10 eligibility and quarantine differ")
        if quarantined:
            require(record.get("identity_state") == "AMBIGUOUS_IDENTITY" and record.get("quarantine_reason"), "MODEL10_QUARANTINE_MISMATCH", "quarantine authority is inconsistent")
            quarantined_count += 1
            continue
        lineage = record.get("source_observation_lineage")
        require(isinstance(lineage, Mapping), "MODEL10_SOURCE_LINEAGE_INCOMPLETE", "successor source lineage is absent")
        selected_lineage = {
            "source_workbook_identity": lineage.get("source_workbook_identity"),
            "source_sheet": lineage.get("source_sheet"),
            "source_row": lineage.get("source_row"),
            "source_seed_point_id": lineage.get("source_seed_point_id"),
        }
        require(
            isinstance(selected_lineage["source_workbook_identity"], str) and selected_lineage["source_workbook_identity"]
            and isinstance(selected_lineage["source_sheet"], str) and selected_lineage["source_sheet"]
            and isinstance(selected_lineage["source_row"], int) and selected_lineage["source_row"] >= 2
            and isinstance(selected_lineage["source_seed_point_id"], str) and selected_lineage["source_seed_point_id"],
            "MODEL10_SOURCE_LINEAGE_INCOMPLETE",
            "successor source lineage is incomplete",
        )
        observation_id = record.get("source_observation_id")
        physical_id = record.get("successor_physical_location_id")
        market = record.get("market")
        vintage = record.get("forecast_vintage")
        require(isinstance(observation_id, str) and observation_id.startswith("sobs-") and observation_id not in observation_ids, "MODEL10_SOURCE_OBSERVATION_INVALID", "successor observation is missing or duplicate")
        require(isinstance(physical_id, str) and physical_id and isinstance(market, str) and market.strip() and isinstance(vintage, int), "MODEL10_ELIGIBLE_RECORD_INCOMPLETE", "eligible MODEL-10 identity or lineage is incomplete")
        source_key = (str(selected_lineage["source_workbook_identity"]), str(selected_lineage["source_sheet"]), int(selected_lineage["source_row"]))
        require(source_key not in source_rows, "MODEL10_SOURCE_ROW_DUPLICATE", "eligible successor source row is duplicate")
        observation_ids.add(observation_id)
        source_rows.add(source_key)
        item = {
            "source_observation_id": observation_id,
            "source_observation_lineage": selected_lineage,
            "successor_physical_location_id": physical_id,
            "historical_model04_physical_location_id": record.get("historical_model04_physical_location_id"),
            "market": market,
            "forecast_vintage": vintage,
            "identity_state": record.get("identity_state"),
            "historical_evidence_role_lineage": copy.deepcopy(record.get("historical_evidence_role_lineage", [])),
            "target_access_state": record.get("target_access_state"),
        }
        require(item["identity_state"] != "AMBIGUOUS_IDENTITY" and item["target_access_state"] == "NOT_ACCESSED_BY_MODEL10", "MODEL10_ELIGIBLE_RECORD_INVALID", "eligible record has invalid identity or target state")
        historical_id = item["historical_model04_physical_location_id"]
        require(historical_id is None or historical_id == physical_id, "MODEL10_HISTORICAL_LINKAGE_MISMATCH", "historical linkage was changed or forced")
        cohort.append(item)
        projection_input.append({**copy.deepcopy(item), "model09_development_eligible": True, "quarantined": False})
    aggregate = package.get("aggregate_conformance")
    require(cohort and isinstance(aggregate, Mapping) and aggregate.get("model09_development_eligible_observation_count") == len(cohort) and aggregate.get("quarantined_observation_count") == quarantined_count and len(records) == len(cohort) + quarantined_count, "MODEL10_COHORT_COMPLETENESS_FAILED", "complete MODEL-10 eligible/quarantine partition was not retained")
    return cohort, projection_input, quarantined_count


def _assert_default_deny(value: Any) -> None:
    forbidden = {"impacted_sales", "coordinates", "latitude", "longitude", "prediction_value", "forecast_value"}
    if isinstance(value, Mapping):
        for key, child in value.items():
            require(str(key).lower() not in forbidden, "PROTECTED_FIELD_IN_BINDING_REJECTED", "denied target or coordinate field entered PIPE-04")
            _assert_default_deny(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            _assert_default_deny(child)


def validate_semantic_package(package: Mapping[str, Any]) -> None:
    required = {"$schema", "package_id", "version", "binding_run_id", "state", "model10_authority", "eligible_wisconsin_cohort", "cohort_freeze", "target_source_authorities", "minimum_target_projection", "consumption_semantics", "protected_handle_registry_identity", "finalization", "supersedes", "supersession_policy"}
    require(set(package) == required, "BINDING_PACKAGE_SCHEMA_INVALID", "protected package fields differ from PIPE-04")
    require(package.get("$schema") == BINDING_SCHEMA_VERSION and package.get("package_id") == BINDING_PACKAGE_ID and bool(re.fullmatch(r"1\.0\.[0-9]+", str(package.get("version", "")))) and package.get("state") == "ready", "BINDING_IDENTITY_MISMATCH", "binding identity/version/state differs")
    authority = package.get("model10_authority")
    require(isinstance(authority, Mapping) and authority.get("package_id") == MODEL10_PACKAGE_ID and authority.get("package_version") == MODEL10_PACKAGE_VERSION and authority.get("commitment_artifact_id") == MODEL10_COMMITMENT_ID and authority.get("commitment_reconciled") is True and authority.get("ready_marker_reconciled") is True and authority.get("substantive_h") == ACCEPTED_MODEL10_H and authority.get("acceptance_record_a") == ACCEPTED_MODEL10_A and authority.get("canonical_merge") == ACCEPTED_MODEL10_MERGE, "MODEL10_BINDING_AUTHORITY_MISMATCH", "binding does not prove exact accepted MODEL-10 authority")
    cohort = package.get("eligible_wisconsin_cohort")
    require(isinstance(cohort, list) and cohort, "WISCONSIN_COHORT_EMPTY", "binding cohort is empty")
    cohort_by_id: dict[str, Mapping[str, Any]] = {}
    source_identities: set[str] = set()
    for row in cohort:
        lineage = row.get("source_observation_lineage") if isinstance(row, Mapping) else None
        observation_id = row.get("source_observation_id") if isinstance(row, Mapping) else None
        require(isinstance(lineage, Mapping) and isinstance(observation_id, str) and observation_id not in cohort_by_id and row.get("identity_state") != "AMBIGUOUS_IDENTITY" and row.get("target_access_state") == "NOT_ACCESSED_BY_MODEL10", "WISCONSIN_COHORT_POLICY_MISMATCH", "cohort contains duplicate ineligible or ambiguous identity")
        cohort_by_id[observation_id] = row
        source_identities.add(str(lineage.get("source_workbook_identity")))
    freeze = package.get("cohort_freeze")
    require(isinstance(freeze, Mapping) and freeze.get("established_from_model10_only") is True and freeze.get("frozen_before_target_projection") is True and freeze.get("eligible_observation_count") == len(cohort) and freeze.get("cohort_identity_sha256") == content_digest(cohort), "COHORT_FREEZE_MISMATCH", "cohort freeze proof differs")
    sources = package.get("target_source_authorities")
    require(isinstance(sources, list) and len(sources) == len(source_identities) and {str(source.get("source_workbook_identity")) for source in sources if isinstance(source, Mapping)} == source_identities and all(source.get("whole_workbook_hash_computed") is False for source in sources), "TARGET_SOURCE_COMPLETENESS_FAILED", "target sources do not cover the cohort exactly")
    projection = package.get("minimum_target_projection")
    require(isinstance(projection, Mapping) and projection.get("projection_id") == PROJECTION_ID and projection.get("version") == PROJECTION_VERSION and projection.get("default_deny") is True and set(projection.get("allowed_fields", [])) == Model10WisconsinProjectionPolicy.ALLOWED_FIELDS, "TARGET_PROJECTION_IDENTITY_MISMATCH", "projection identity or allowlist differs")
    rows = projection.get("rows")
    require(isinstance(rows, list) and len(rows) == len(cohort), "TARGET_PROJECTION_COMPLETENESS_FAILED", "target rows do not cover cohort")
    projected: set[str] = set()
    for row in rows:
        observation_id = row.get("source_observation_id") if isinstance(row, Mapping) else None
        require(isinstance(observation_id, str) and observation_id not in projected and observation_id in cohort_by_id and row.get("forecast_vintage") == cohort_by_id[observation_id].get("forecast_vintage") and isinstance(row.get("isolated_sales"), str) and row.get("isolated_sales"), "TARGET_SUCCESSOR_IDENTITY_MISMATCH", "target content changed or failed to resolve successor identity")
        projected.add(observation_id)
    require(projected == set(cohort_by_id), "TARGET_PROJECTION_COMPLETENESS_FAILED", "target observation membership differs from frozen cohort")
    audit = projection.get("target_access_audit")
    require(isinstance(audit, Mapping) and audit.get("authorized_row_count") == len(cohort) and audit.get("isolated_sales_materialized") is True and audit.get("impacted_sales_decode_calls") == 0 and audit.get("non_wisconsin_target_decode_calls") == 0 and audit.get("unrelated_target_values_materialized") is False, "TARGET_ACCESS_AUDIT_FAILED", "target access exceeded exact projection")
    consumption = package.get("consumption_semantics")
    require(isinstance(consumption, Mapping) and consumption.get("binding_marks_development_consumed") is False and consumption.get("prior_evidence_metadata_preserved") is True and consumption.get("analytical_influence_triggers_model09_consumption") is True, "EVIDENCE_CONSUMPTION_SEMANTICS_INVALID", "binding changed evidence consumption semantics")
    finalization = package.get("finalization")
    require(isinstance(finalization, Mapping) and finalization.get("cohort_established_before_target_projection") is True and finalization.get("target_content_invariant_to_identity_and_membership") is True and finalization.get("impacted_sales_accessed") is False and finalization.get("non_wisconsin_targets_accessed") is False and finalization.get("ready_marker_written_last") is True, "BINDING_FINALIZATION_CONFORMANCE_FAILED", "finalization proof is incomplete")
    _assert_default_deny(package)


class ProtectedBindingRun:
    """One immutable incomplete-first protected binding run.

    PIPE-04 remains the default specification.  Later governed PIPE bindings may
    reuse the exact writer/finalizer by supplying an additive specification;
    this keeps the accepted immutability and READY-last behavior centralized.
    """

    def __init__(
        self,
        protected_root: Path,
        repository_root: Path,
        *,
        binding_run_id: str | None = None,
        package_version: str = BINDING_PACKAGE_VERSION,
        supersedes: str | None = None,
        run_id_prefix: str = "p4bind-",
        collection: str = "pipe04-bindings",
        package_filename: str = "pipe04_model10_wisconsin_development_binding.json",
        package_id: str = BINDING_PACKAGE_ID,
        binding_schema_version: str = BINDING_SCHEMA_VERSION,
        stable_identity_prefix: str = "pipe04-binding",
        semantic_validator: Any = validate_semantic_package,
        task_label: str = "PIPE-04",
    ):
        self.protected_root = protected_root.resolve()
        self.repository_root = repository_root.resolve()
        require(not _is_within(self.protected_root, self.repository_root), "PROTECTED_ROOT_INSIDE_REPOSITORY", f"{task_label} output must remain outside Git")
        require(bool(re.fullmatch(r"[a-z0-9]+-", run_id_prefix)), "BINDING_RUN_ID_INVALID", "binding run prefix must be opaque and safe")
        require(bool(re.fullmatch(r"[a-z0-9-]+", collection)), "BINDING_COLLECTION_INVALID", "binding collection must be safe")
        require(PurePath(package_filename).name == package_filename, "BINDING_PACKAGE_FILENAME_INVALID", "binding package filename must be local")
        require(bool(package_id) and bool(binding_schema_version) and bool(stable_identity_prefix) and callable(semantic_validator), "BINDING_SPECIFICATION_INVALID", "binding specification is incomplete")
        self.binding_run_id = binding_run_id or run_id_prefix + str(uuid.uuid4())
        require(self.binding_run_id.startswith(run_id_prefix) and all(character.isalnum() or character in "-_" for character in self.binding_run_id), "BINDING_RUN_ID_INVALID", "binding run ID must be opaque and safe")
        require(bool(re.fullmatch(r"1\.0\.[0-9]+", package_version)), "BINDING_VERSION_INVALID", f"{task_label} version must remain in 1.0 patch line")
        if supersedes is not None:
            require(package_version != BINDING_PACKAGE_VERSION, "BINDING_SUPERSESSION_VERSION_REQUIRED", "correction requires a new patch version")
            require(supersedes.startswith(run_id_prefix), "BINDING_SUPERSESSION_INVALID", f"supersession must name an earlier {task_label} run")
        self.package_version = package_version
        self.supersedes = supersedes
        self.package_filename = package_filename
        self.package_id = package_id
        self.binding_schema_version = binding_schema_version
        self.stable_identity_prefix = stable_identity_prefix
        self.semantic_validator = semantic_validator
        self.task_label = task_label
        self.run_dir = self.protected_root / collection / self.binding_run_id
        require(not self.run_dir.exists(), "BINDING_ALREADY_EXISTS", f"never overwrite a {task_label} run")
        self.run_dir.mkdir(parents=True, exist_ok=False)
        write_json_exclusive(self.run_dir / "binding_state.json", {"binding_run_id": self.binding_run_id, "state": "incomplete", "finalization_state": "not_started", "package_version": package_version, "supersedes": supersedes})

    def finalize(self, semantic_package: Mapping[str, Any]) -> dict[str, str]:
        require(semantic_package.get("binding_run_id") == self.binding_run_id and semantic_package.get("version") == self.package_version and semantic_package.get("supersedes") == self.supersedes, "BINDING_IDENTITY_MISMATCH", "staged package differs from run")
        self.semantic_validator(semantic_package)
        protected_hash = content_digest(semantic_package)
        stable_identity = self.stable_identity_prefix + ":sha256:" + protected_hash
        package = {**copy.deepcopy(dict(semantic_package)), "protected_content_sha256": protected_hash, "stable_binding_identity": stable_identity, "protected_content_hash_semantics": "SHA-256 of canonical UTF-8 JSON before adding protected_content_sha256 stable_binding_identity and protected_content_hash_semantics."}
        package_path = self.run_dir / self.package_filename
        write_json_exclusive(package_path, package)
        manifest = {"binding_run_id": self.binding_run_id, "package_id": self.package_id, "package_version": self.package_version, "binding_schema_version": self.binding_schema_version, "state": "ready", "finalization_state": "complete", "supersedes": self.supersedes, "protected_content_sha256": protected_hash, "stable_binding_identity": stable_identity, "package_file_sha256": file_sha256(package_path)}
        write_json_exclusive(self.run_dir / "binding_manifest.json", manifest)
        nonce = new_nonce()
        commitment = freeze_commitment(content_digest(manifest), nonce)
        with (self.run_dir / "binding_nonce.bin").open("xb") as handle:
            handle.write(nonce)
            handle.flush()
            os.fsync(handle.fileno())
        write_json_exclusive(self.run_dir / "commitment_evidence.json", {"domain": DOMAIN_SEPARATOR.decode("utf-8"), "commitment_sha256": commitment})
        write_json_exclusive(self.run_dir / "READY.json", {"binding_run_id": self.binding_run_id, "package_id": self.package_id, "package_version": self.package_version, "state": "ready", "finalization_state": "complete", "protected_content_sha256": protected_hash, "stable_binding_identity": stable_identity, "commitment_sha256": commitment})
        return {"protected_content_sha256": protected_hash, "stable_binding_identity": stable_identity, "commitment_sha256": commitment}


def protected_binding_is_ready(run_dir: Path) -> bool:
    return (run_dir / "READY.json").is_file()


@dataclass(frozen=True)
class BindingResult:
    binding_run_id: str
    run_dir: Path
    protected_content_sha256: str
    stable_binding_identity: str
    commitment_sha256: str
    eligible_observation_count: int
    quarantined_observation_count: int
    source_authority_count: int
    target_access_audit: TargetAccessAudit


def execute_protected_binding(*, repository_root: Path, resolver: ProtectedHandleResolver, binding_run_id: str | None = None, package_version: str = BINDING_PACKAGE_VERSION, supersedes: str | None = None) -> BindingResult:
    root = repository_root.resolve()
    request = resolver.binding_request
    output = resolver.resolve(str(request["binding_output_root_handle"]), "pipe04_output_root")
    staged = ProtectedBindingRun(output.path, root, binding_run_id=binding_run_id, package_version=package_version, supersedes=supersedes)
    model10_package = resolver.resolve(str(request["model10_package_handle"]), "model10_package")
    model10_evidence = resolver.resolve(str(request["model10_commitment_evidence_handle"]), "model10_commitment_evidence")
    model10_nonce = resolver.resolve(str(request["model10_commitment_nonce_handle"]), "model10_commitment_nonce")
    model10_ready = resolver.resolve(str(request["model10_ready_marker_handle"]), "model10_ready_marker")
    package, authority = verify_model10_authority(repository_root=root, package_path=model10_package.path, commitment_evidence_path=model10_evidence.path, nonce_path=model10_nonce.path, ready_path=model10_ready.path)
    cohort, projection_input, quarantined_count = derive_eligible_wisconsin_cohort(package)
    frozen_cohort = copy.deepcopy(cohort)
    cohort_hash = content_digest(frozen_cohort)

    requested_by_source: dict[str, list[Mapping[str, Any]]] = {}
    for row in projection_input:
        source_identity = str(row["source_observation_lineage"]["source_workbook_identity"])
        requested_by_source.setdefault(source_identity, []).append(row)
    require(set(requested_by_source) == set(resolver.target_source_authorities), "TARGET_SOURCE_COMPLETENESS_FAILED", "target authorities must cover complete eligible cohort and only it")

    projected_rows: list[dict[str, Any]] = []
    bound_sources: list[dict[str, Any]] = []
    combined = TargetAccessAudit()
    for source_identity in sorted(requested_by_source):
        source = resolver.target_source_authorities[source_identity]
        workbook = resolver.resolve(str(source["workbook_handle"]), "wisconsin_development_target_workbook")
        policy = Model10WisconsinProjectionPolicy(source["projection"], workbook.handle, source_identity)
        values, audit = project_authorized_isolated_sales(workbook.path, policy, requested_by_source[source_identity])
        projected_rows.extend(values)
        for field in combined.__dataclass_fields__:
            setattr(combined, field, getattr(combined, field) + getattr(audit, field))
        bound_sources.append({"authority_id": source["authority_id"], "provenance_class": source["provenance_class"], "source_workbook_identity": source_identity, "workbook_handle": workbook.handle, "whole_workbook_hash_computed": False, "sheet_name": policy.sheet_name, "projection_id": policy.PROJECTION_ID, "projection_version": policy.VERSION})
    require(frozen_cohort == cohort and cohort_hash == content_digest(cohort), "TARGET_CONTENT_CHANGED_COHORT", "target access changed frozen MODEL-10 identity or membership")

    semantic = {
        "$schema": BINDING_SCHEMA_VERSION,
        "package_id": BINDING_PACKAGE_ID,
        "version": package_version,
        "binding_run_id": staged.binding_run_id,
        "state": "ready",
        "model10_authority": {**authority, "package_handle": model10_package.handle, "commitment_evidence_handle": model10_evidence.handle, "commitment_nonce_handle": model10_nonce.handle, "ready_marker_handle": model10_ready.handle, "eligibility_and_quarantine_authoritative": True, "identity_recomputed_or_reinterpreted": False},
        "eligible_wisconsin_cohort": frozen_cohort,
        "cohort_freeze": {"established_from_model10_only": True, "frozen_before_target_projection": True, "eligible_observation_count": len(frozen_cohort), "quarantined_observation_count": quarantined_count, "cohort_identity_sha256": cohort_hash, "target_content_may_change_membership_or_identity": False},
        "target_source_authorities": bound_sources,
        "minimum_target_projection": {"projection_id": PROJECTION_ID, "version": PROJECTION_VERSION, "default_deny": True, "allowed_fields": sorted(Model10WisconsinProjectionPolicy.ALLOWED_FIELDS), "denied_scope": ["Impacted Sales", "Michigan", "Detroit", "every non-Wisconsin target", "MODEL-10 quarantined observations", "unrelated workbook rows", "unrelated workbook fields", "broad workbook previews", "exploratory target access outside MODEL-09", "target-derived identity cohort quarantine or eligibility"], "rows": projected_rows, "target_access_audit": combined.disclosure_safe()},
        "consumption_semantics": {"binding_marks_development_consumed": False, "prior_evidence_metadata_preserved": True, "analytical_influence_triggers_model09_consumption": True, "consumed_evidence_cannot_regain_untouched_validation_status": True},
        "protected_handle_registry_identity": resolver.registry_identity,
        "finalization": {"cohort_established_before_target_projection": True, "target_content_invariant_to_identity_and_membership": True, "successor_source_observation_lineage_used": True, "historical_model04_source_equality_required": False, "mandatory_reconciliations_passed": True, "impacted_sales_accessed": False, "non_wisconsin_targets_accessed": False, "ready_marker_written_last": True},
        "supersedes": supersedes,
        "supersession_policy": "Never overwrite a PIPE-04 binding. A correction requires a new patch version opaque run ID and explicit supersedes lineage.",
    }
    finalized = staged.finalize(semantic)
    return BindingResult(staged.binding_run_id, staged.run_dir, finalized["protected_content_sha256"], finalized["stable_binding_identity"], finalized["commitment_sha256"], len(cohort), quarantined_count, len(bound_sources), combined)


def build_disclosure_safe_result(result: BindingResult) -> dict[str, Any]:
    report = {
        "completion_state": "PIPE-04 protected binding ready",
        "package_id": BINDING_PACKAGE_ID,
        "version": BINDING_PACKAGE_VERSION,
        "eligible_wisconsin_observation_count": result.eligible_observation_count,
        "quarantined_observation_count": result.quarantined_observation_count,
        "target_source_authority_count": result.source_authority_count,
        "isolated_sales_values_materialized": result.target_access_audit.authorized_isolated_sales_decode_calls,
        "impacted_sales_values_materialized": 0,
        "non_wisconsin_target_values_materialized": 0,
        "model10_commitment_verified": True,
        "cohort_selection_target_blind": True,
        "binding_marks_development_consumed": False,
        "protected_output_outside_git": True,
        "protected_details_disclosed": False,
    }
    serialized = json.dumps(report, sort_keys=True).lower()
    for forbidden in ("source_row", "seed_point", "physical_location_id", "cell_address", "nonce", "commitment_sha256", "protected_content_sha256", "stable_binding_identity", "latitude", "longitude", "\\\\", ":\\"):
        require(forbidden not in serialized, "DISCLOSURE_SAFE_REPORT_VIOLATION", "protected detail entered PIPE-04 report")
    return report
