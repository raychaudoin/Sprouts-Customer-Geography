"""PIPE-02 authority reconciliation and immutable protected binding finalization."""

from __future__ import annotations

import copy
import json
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from sprouts_customer_geography.constants import PIPE_SCHEMA_VERSION
from sprouts_customer_geography.model06 import (
    COMMITMENT_ID,
    COMMITMENT_VERSION,
    PACKAGE_ID as MODEL04_PACKAGE_ID,
    PACKAGE_VERSION as MODEL04_PACKAGE_VERSION,
    PREREGISTRATION_ID,
    PREREGISTRATION_VERSION,
)
from sprouts_customer_geography.pipe01.canonical import content_digest, content_id, file_sha256, write_json_exclusive
from sprouts_customer_geography.pipe01.commitment import DOMAIN_SEPARATOR, freeze_commitment, new_nonce
from sprouts_customer_geography.pipe01.errors import ConformanceError, require
from sprouts_customer_geography.pipe01.orchestration import Model04Binding, load_model04_binding, load_repository_authorities

from .resolver import (
    CURRENT_2026_TEMPORAL_SOURCE,
    PRIOR_VINTAGE_TEMPORAL_SOURCE,
    REQUIRED_TARGET_SOURCE_ROLES,
    ProtectedHandleResolver,
    _is_within,
)
from .xlsx_projection import MinimumTargetProjectionPolicy, TargetAccessAudit, project_target_addresses


BINDING_PACKAGE_ID = "PIPE02_PROTECTED_VALIDATION_ACCESS_BINDING_V1"
BINDING_PACKAGE_VERSION = "1.0.0"
BINDING_SCHEMA_VERSION = "pipe02-protected-validation-access-binding-v1.1"
EXPECTED_MODEL04_COMMITMENT = "b5db257f31a790d3ca72ed784d42d7db2e878c8fa6723b869f6c14234153bdfb"
EXPECTED_MODEL05_SHA256 = "a73b1c165e4ef26b3d0ee984af7cf8ca3ae917aeda003cb62dbb6e2ef4d28620"
EXPECTED_PIPE_RUN_ID = "prun-4b9d09f3-d485-4fb8-87a2-44118ad34e3f"
EXPECTED_PIPE_SCHEMA_VERSION = "pipe01-artifacts-v1"
EXPECTED_PIPE_FREEZE_COMMITMENT = "9156cc4d799560d534be9ac33aaf0f39010f79385fcdb99a1f43329a202f86f0"
EXPECTED_PIPE_EXECUTION_COMMIT = "9b355ae2e1ea913b45f86f2ffe1be09f52b3c934"


def _load_json_object(path: Path, code: str) -> dict[str, Any]:
    require(path.is_file(), code, "required protected JSON artifact is absent")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ConformanceError(code, "required protected JSON artifact is unreadable") from exc
    require(isinstance(value, dict), code, "required protected JSON artifact must be an object")
    return value


def _simple_filename(value: str) -> str:
    require(isinstance(value, str) and bool(value) and Path(value).name == value, "PIPE_ARTIFACT_NAME_INVALID", "protected artifact manifest contains a nonlocal filename")
    return value


def _artifact_reference(run_id: str, filename: str, declared_sha256: str, document: Mapping[str, Any] | None = None) -> dict[str, Any]:
    reference = {
        "handle": f"protected-run://{run_id}/artifacts/{filename}",
        "content_sha256": declared_sha256,
    }
    if document is not None and isinstance(document.get("artifact_id"), str):
        reference["artifact_id"] = document["artifact_id"]
    return reference


@dataclass(frozen=True)
class PipeFreezeBinding:
    run_reference: Mapping[str, Any]
    artifact_bindings: Mapping[str, Mapping[str, Mapping[str, Any]]]


def _context_ordinals(package: Mapping[str, Any]) -> dict[int, int]:
    ordinals: dict[int, int] = {}
    ordinal = 0
    for index, record in enumerate(package["records"]):
        if record["evidence_role"] == "DEVELOPMENT_REFERENCE":
            continue
        ordinal += 1
        ordinals[index] = ordinal
    return ordinals


def derive_temporal_mapping(model04: Model04Binding) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    """Derive the cohort and row join pairs exclusively from frozen MODEL-04."""
    package = model04.package
    records = package["records"]
    temporal_indices = [index for index, record in enumerate(records) if record["evidence_role"] == "TEMPORAL_VALIDATION"]
    require(bool(temporal_indices), "TEMPORAL_COHORT_EMPTY", "MODEL-04 has no accepted temporal-validation records")
    ordinals = _context_ordinals(package)
    locations: list[dict[str, Any]] = []
    requested_pairs: dict[str, list[dict[str, Any]]] = {
        PRIOR_VINTAGE_TEMPORAL_SOURCE: [],
        CURRENT_2026_TEMPORAL_SOURCE: [],
    }
    seen_locations: set[str] = set()
    for index in temporal_indices:
        current = records[index]
        location_id = str(current["physical_location_id"])
        require(location_id not in seen_locations, "TEMPORAL_LOCATION_DUPLICATE", "MODEL-04 has multiple current temporal records for one physical location")
        seen_locations.add(location_id)
        require(
            current["market"] == "milwaukee"
            and current["identity_state"] in {"SAME_UNDERLYING_LOCATION", "PROBABLE_SAME_LOCATION"}
            and current["linked_prior_physical_location_id"] == current["physical_location_id"]
            and current["quarantined"] is False
            and current["target_view_state"] == "SEALED",
            "TEMPORAL_ROLE_AUTHORITY_INVALID",
            "MODEL-04 temporal role does not satisfy the frozen repeated-Milwaukee authority",
        )
        require(int(current["vintage_year"]) == 2026, "TEMPORAL_CURRENT_VINTAGE_INVALID", "MODEL-04 temporal record is not the corresponding 2026 member")
        members = [record for record in records if record["physical_location_id"] == location_id]
        prior_members = [
            record
            for record in members
            if int(record["vintage_year"]) < 2026
            and record["market"] == "milwaukee"
            and record["evidence_role"] == "DEVELOPMENT_REFERENCE"
            and record["target_view_state"] == "DEVELOPMENT_CONSUMED"
            and not record["quarantined"]
        ]
        require(bool(prior_members), "TEMPORAL_PRIOR_MEMBER_UNRESOLVED", "MODEL-04 temporal location has no eligible prior-vintage member")
        latest_year = max(int(record["vintage_year"]) for record in prior_members)
        latest = [record for record in prior_members if int(record["vintage_year"]) == latest_year]
        require(len(latest) == 1, "TEMPORAL_PRIOR_MEMBER_AMBIGUOUS", "MODEL-04 has multiple latest eligible prior-vintage members")
        prior = latest[0]
        require(str(prior["physical_location_id"]) == location_id, "TEMPORAL_PHYSICAL_LINEAGE_MISMATCH", "prior and 2026 records do not share frozen physical-location identity")
        require(index in ordinals, "PIPE_CONTEXT_ORDINAL_UNRESOLVED", "temporal record has no frozen PIPE context ordinal")
        mapping = {
            "physical_location_id": location_id,
            "pipe_context_ordinal": ordinals[index],
            "role": "TEMPORAL_VALIDATION",
            "market": "milwaukee",
            "identity_state": current["identity_state"],
            "prior": {
                "source_workbook_identity": prior["source_workbook_identity"],
                "source_sheet": prior["source_sheet"],
                "source_row": prior["source_row"],
                "source_seed_point_id": prior["source_seed_point_id"],
                "vintage_year": latest_year,
            },
            "current_2026": {
                "source_workbook_identity": current["source_workbook_identity"],
                "source_sheet": current["source_sheet"],
                "source_row": current["source_row"],
                "source_seed_point_id": current["source_seed_point_id"],
                "vintage_year": 2026,
            },
        }
        locations.append(mapping)
        for source_role, pair_role, record in (
            (PRIOR_VINTAGE_TEMPORAL_SOURCE, "most_recent_eligible_prior", prior),
            (CURRENT_2026_TEMPORAL_SOURCE, "corresponding_2026", current),
        ):
            requested_pairs[source_role].append(
                {
                    "source_role": source_role,
                    "pair_role": pair_role,
                    "physical_location_id": location_id,
                    "lineage_key": str(record["source_seed_point_id"]),
                    "vintage_year": int(record["vintage_year"]),
                }
            )
    pair_keys = [
        (item["lineage_key"], item["vintage_year"])
        for role_pairs in requested_pairs.values()
        for item in role_pairs
    ]
    require(len(pair_keys) == len(set(pair_keys)), "TEMPORAL_TARGET_JOIN_DUPLICATE", "MODEL-04 minimum target join pairs are not unique")
    return locations, requested_pairs


def reconcile_pipe_freeze(run_dir: Path, run_handle: str, temporal_mapping: Sequence[Mapping[str, Any]]) -> PipeFreezeBinding:
    require(run_dir.name == EXPECTED_PIPE_RUN_ID, "PIPE_RUN_ID_MISMATCH", "protected run-directory handle resolves to another run")
    marker_path = run_dir / "FROZEN.json"
    evidence_path = run_dir / "commitment_evidence.json"
    nonce_path = run_dir / "freeze_nonce.bin"
    freeze_manifest_path = run_dir / "freeze_manifest.json"
    run_manifest_path = run_dir / "run_manifest.json"
    marker = _load_json_object(marker_path, "PIPE_FINAL_MARKER_MISSING")
    evidence = _load_json_object(evidence_path, "PIPE_COMMITMENT_EVIDENCE_MISSING")
    freeze_manifest = _load_json_object(freeze_manifest_path, "PIPE_FREEZE_MANIFEST_MISSING")
    run_manifest = _load_json_object(run_manifest_path, "PIPE_RUN_MANIFEST_MISSING")
    require(nonce_path.is_file(), "PIPE_FREEZE_NONCE_MISSING", "PIPE-01 freeze verification material is absent")
    nonce = nonce_path.read_bytes()
    require(len(nonce) >= 32, "PIPE_FREEZE_NONCE_INVALID", "PIPE-01 freeze verification material is invalid")
    require(marker == {"run_id": EXPECTED_PIPE_RUN_ID, "state": "frozen", "finalization_state": "complete", "commitment_sha256": EXPECTED_PIPE_FREEZE_COMMITMENT}, "PIPE_FINAL_MARKER_MISMATCH", "PIPE-01 final marker identity/state/commitment mismatch")
    require(evidence.get("domain") == DOMAIN_SEPARATOR.decode("utf-8") and evidence.get("commitment_sha256") == EXPECTED_PIPE_FREEZE_COMMITMENT, "PIPE_FREEZE_COMMITMENT_MISMATCH", "PIPE-01 commitment evidence differs from the accepted freeze")
    require(freeze_commitment(content_digest(freeze_manifest), nonce) == EXPECTED_PIPE_FREEZE_COMMITMENT, "PIPE_FREEZE_COMMITMENT_MISMATCH", "PIPE-01 freeze manifest does not reconcile to the accepted commitment")
    require(freeze_manifest.get("run_id") == EXPECTED_PIPE_RUN_ID and freeze_manifest.get("state") == "frozen" and freeze_manifest.get("finalization_state") == "complete", "PIPE_FREEZE_MANIFEST_MISMATCH", "PIPE-01 freeze manifest state differs")
    require(run_manifest.get("run_id") == EXPECTED_PIPE_RUN_ID and run_manifest.get("run_state") == "frozen" and run_manifest.get("finalization_state") == "complete", "PIPE_RUN_MANIFEST_MISMATCH", "PIPE-01 immutable run manifest state differs")
    require(run_manifest.get("pipe_schema_version") == EXPECTED_PIPE_SCHEMA_VERSION == PIPE_SCHEMA_VERSION, "PIPE_SCHEMA_VERSION_MISMATCH", "PIPE-01 protected schema version differs")
    require(freeze_manifest.get("code_identity") == EXPECTED_PIPE_EXECUTION_COMMIT and run_manifest.get("code_identity") == EXPECTED_PIPE_EXECUTION_COMMIT, "PIPE_EXECUTION_COMMIT_MISMATCH", "PIPE-01 execution identity differs from the accepted commit")
    require(freeze_manifest.get("supersedes") == run_manifest.get("supersedes"), "PIPE_SUPERSESSION_LINEAGE_MISMATCH", "PIPE-01 supersession lineage differs between immutable manifests")
    require(not (run_dir / "SUPERSEDED.json").exists(), "PIPE_RUN_SUPERSEDED", "accepted PIPE-01 run is marked as superseded")
    require(file_sha256(run_manifest_path) == freeze_manifest.get("run_manifest_sha256"), "PIPE_RUN_MANIFEST_HASH_MISMATCH", "PIPE-01 run-manifest content hash differs")
    artifact_hashes = freeze_manifest.get("protected_artifact_sha256")
    require(isinstance(artifact_hashes, Mapping) and artifact_hashes == run_manifest.get("artifact_ids"), "PIPE_ARTIFACT_MANIFEST_MISMATCH", "PIPE-01 artifact manifests differ")
    artifact_dir = run_dir / "artifacts"
    for raw_name, expected_hash in artifact_hashes.items():
        name = _simple_filename(str(raw_name))
        path = artifact_dir / name
        require(path.is_file(), "PIPE_FROZEN_ARTIFACT_MISSING", "a manifest-declared PIPE-01 artifact is absent")
        require(file_sha256(path) == expected_hash, "PIPE_FROZEN_ARTIFACT_HASH_MISMATCH", "a manifest-declared PIPE-01 artifact is corrupted")

    artifact_bindings: dict[str, dict[str, Mapping[str, Any]]] = {}
    for location in temporal_mapping:
        ordinal = int(location["pipe_context_ordinal"])
        prefix = f"context-{ordinal:04d}"
        filenames = {
            "model04_lineage": f"{prefix}-model04-lineage.json",
            "frozen_prediction": f"{prefix}-baseline-prediction.json",
            "readiness": f"{prefix}-eligibility-readiness.json",
            "geometric_completeness": f"{prefix}-context-spatial-evidence.json",
            "dependence_geometric_jaccard": f"{prefix}-context-spatial-evidence.json",
        }
        refs: dict[str, Mapping[str, Any]] = {}
        for semantic, filename in filenames.items():
            require(filename in artifact_hashes, "PIPE_REQUIRED_FROZEN_ARTIFACT_MISSING", "a MODEL-05-required frozen PIPE-01 artifact is absent")
            path = artifact_dir / filename
            document = _load_json_object(path, "PIPE_REQUIRED_FROZEN_ARTIFACT_INVALID")
            refs[semantic] = _artifact_reference(EXPECTED_PIPE_RUN_ID, filename, str(artifact_hashes[filename]), document)
        lineage = _load_json_object(artifact_dir / filenames["model04_lineage"], "PIPE_MODEL04_LINEAGE_INVALID")
        require(
            lineage.get("physical_location_id") == location["physical_location_id"]
            and lineage.get("evidence_role") == "TEMPORAL_VALIDATION",
            "PIPE_MODEL04_LINEAGE_MISMATCH",
            "frozen PIPE-01 context lineage differs from the MODEL-04 temporal authority",
        )
        artifact_bindings[str(location["physical_location_id"])] = refs

    run_reference = {
        "run_id": EXPECTED_PIPE_RUN_ID,
        "run_directory_handle": run_handle,
        "pipe_schema_version": EXPECTED_PIPE_SCHEMA_VERSION,
        "freeze_commitment": EXPECTED_PIPE_FREEZE_COMMITMENT,
        "run_manifest": {
            "handle": f"protected-run://{EXPECTED_PIPE_RUN_ID}/run_manifest.json",
            "content_sha256": file_sha256(run_manifest_path),
            "identity": content_id("pipe01_run_manifest", run_manifest),
        },
        "freeze_manifest": {
            "handle": f"protected-run://{EXPECTED_PIPE_RUN_ID}/freeze_manifest.json",
            "content_sha256": file_sha256(freeze_manifest_path),
            "identity": content_id("pipe01_freeze_manifest", freeze_manifest),
        },
        "completion_marker": {
            "handle": f"protected-run://{EXPECTED_PIPE_RUN_ID}/FROZEN.json",
            "content_sha256": file_sha256(marker_path),
            "identity": content_id("pipe01_final_marker", marker),
        },
    }
    return PipeFreezeBinding(run_reference, artifact_bindings)


def _assert_no_value_payloads(value: Any) -> None:
    forbidden = {"target_value", "forecast_value", "isolated_sales", "impacted_sales", "prediction_candidate", "prediction_value"}
    if isinstance(value, Mapping):
        for key, child in value.items():
            require(str(key).strip().lower() not in forbidden, "PROTECTED_VALUE_IN_BINDING_REJECTED", "a target or prediction value field entered the PIPE-02 package")
            _assert_no_value_payloads(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            _assert_no_value_payloads(child)


def _validate_semantic_package(package: Mapping[str, Any]) -> None:
    required = {
        "$schema",
        "package_id",
        "version",
        "binding_run_id",
        "state",
        "model_authority",
        "model05_authority",
        "pipe01_authority",
        "target_source_authorities",
        "temporal_eligibility_mapping",
        "minimum_target_projection",
        "protected_handle_registry_identity",
        "finalization",
        "supersedes",
        "supersession_policy",
    }
    require(set(package) == required, "BINDING_PACKAGE_SCHEMA_INVALID", "protected binding package fields differ from the exact schema contract")
    require(package.get("$schema") == BINDING_SCHEMA_VERSION and package.get("package_id") == BINDING_PACKAGE_ID and package.get("version") == BINDING_PACKAGE_VERSION, "BINDING_IDENTITY_MISMATCH", "protected binding schema, package identity, or version differs")
    require(package.get("state") == "ready", "BINDING_STATE_INVALID", "only a completely reconciled binding may enter finalization")
    model = package.get("model_authority")
    require(isinstance(model, Mapping) and model.get("package_id") == MODEL04_PACKAGE_ID and model.get("package_version") == MODEL04_PACKAGE_VERSION, "MODEL04_BINDING_IDENTITY_MISMATCH", "binding does not reference the exact accepted MODEL-04 package")
    require(model.get("commitment_sha256") == EXPECTED_MODEL04_COMMITMENT and model.get("commitment_reconciled") is True, "MODEL04_COMMITMENT_MISMATCH", "binding does not prove the accepted MODEL-04 commitment")
    model05 = package.get("model05_authority")
    require(isinstance(model05, Mapping) and model05.get("preregistration_id") == PREREGISTRATION_ID and model05.get("version") == PREREGISTRATION_VERSION and model05.get("content_sha256") == EXPECTED_MODEL05_SHA256, "MODEL05_BINDING_IDENTITY_MISMATCH", "binding does not reference the exact accepted MODEL-05 preregistration")
    pipe = package.get("pipe01_authority")
    require(isinstance(pipe, Mapping) and pipe.get("run_id") == EXPECTED_PIPE_RUN_ID and pipe.get("freeze_commitment") == EXPECTED_PIPE_FREEZE_COMMITMENT, "PIPE_BINDING_IDENTITY_MISMATCH", "binding does not reference the exact accepted PIPE-01 freeze")
    require(pipe.get("upstream_frozen_artifacts_regenerated") is False, "PIPE_FROZEN_ARTIFACT_REGENERATION_REJECTED", "binding must not regenerate upstream PIPE artifacts")
    target_sources = package.get("target_source_authorities")
    require(isinstance(target_sources, list) and len(target_sources) == 2, "TARGET_SOURCE_AUTHORITIES_UNRESOLVED", "binding must represent exactly two target-source authorities")
    source_roles: set[str] = set()
    source_handles: set[str] = set()
    for target_source in target_sources:
        require(isinstance(target_source, Mapping), "TARGET_SOURCE_AUTHORITY_INVALID", "each binding target-source authority must be an object")
        source_role = str(target_source.get("source_role"))
        require(source_role in REQUIRED_TARGET_SOURCE_ROLES and source_role not in source_roles, "TARGET_SOURCE_ROLE_INVALID", "binding target-source roles must be exact and unique")
        source_roles.add(source_role)
        workbook_handle = target_source.get("workbook_handle")
        require(isinstance(workbook_handle, str) and workbook_handle not in source_handles, "TARGET_SOURCE_HANDLE_REUSED", "binding target-source handles must be distinct")
        source_handles.add(workbook_handle)
        require(bool(target_source.get("authority_id")) and bool(target_source.get("provenance_class")), "TARGET_SOURCE_AUTHORITY_UNRESOLVED", "binding target-source identity/provenance is incomplete")
        require(target_source.get("whole_workbook_hash_computed") is False, "TARGET_SOURCE_HASH_POLICY_INVALID", "binding must not compute a new whole-workbook target digest")
    require(source_roles == REQUIRED_TARGET_SOURCE_ROLES, "TARGET_SOURCE_ROLES_INCOMPLETE", "binding target-source roles are incomplete")
    locations = package.get("temporal_eligibility_mapping")
    require(isinstance(locations, list) and bool(locations), "TEMPORAL_COHORT_EMPTY", "binding must contain a frozen MODEL-04 temporal cohort")
    projection = package.get("minimum_target_projection")
    require(isinstance(projection, Mapping) and projection.get("projection_id") == MinimumTargetProjectionPolicy.PROJECTION_ID and projection.get("version") == MinimumTargetProjectionPolicy.VERSION and projection.get("default_deny") is True, "TARGET_PROJECTION_IDENTITY_MISMATCH", "binding minimum projection identity/default-deny state differs")
    target_cells = projection.get("target_cells")
    require(isinstance(target_cells, list) and len(target_cells) == len(locations), "TARGET_PAIR_COMPLETENESS_FAILED", "binding target-address pairs do not cover the temporal cohort exactly")
    source_projections = projection.get("source_projections")
    require(isinstance(source_projections, list) and len(source_projections) == 2, "TARGET_SOURCE_PROJECTION_INCOMPLETE", "binding must retain one projection identity per target-source role")
    projection_roles = {str(item.get("source_role")) for item in source_projections if isinstance(item, Mapping)}
    require(projection_roles == REQUIRED_TARGET_SOURCE_ROLES, "TARGET_SOURCE_PROJECTION_INCOMPLETE", "binding source projections must cover both target-source roles")
    source_by_role = {str(item["source_role"]): item for item in target_sources}
    for source_projection in source_projections:
        require(isinstance(source_projection, Mapping), "TARGET_SOURCE_PROJECTION_INCOMPLETE", "each binding source projection must be an object")
        role = str(source_projection.get("source_role"))
        require(source_projection.get("workbook_handle") == source_by_role[role].get("workbook_handle"), "TARGET_SOURCE_HANDLE_MISMATCH", "binding source projection references another role's handle")
        require(set(source_projection.get("allowed_fields", [])) == MinimumTargetProjectionPolicy.ALLOWED_FIELDS, "TARGET_FIELD_ALLOWLIST_MISMATCH", "binding source projection does not retain the exact minimum field allowlist")
        require(isinstance(source_projection.get("denied_scope"), list) and bool(source_projection.get("denied_scope")), "TARGET_DENY_SCOPE_INCOMPLETE", "binding source projection does not retain its default-deny evidence")
    audits = projection.get("target_access_audits")
    require(isinstance(audits, Mapping) and set(audits) == REQUIRED_TARGET_SOURCE_ROLES, "TARGET_ACCESS_AUDITS_INCOMPLETE", "binding must retain one access audit per target-source role")
    for audit in audits.values():
        require(isinstance(audit, Mapping) and audit.get("target_payload_decode_calls") == 0 and audit.get("target_values_materialized") is False, "TARGET_VALUE_ACCESS_DETECTED", "binding finalization detected target payload access")
    seen_locations: set[str] = set()
    for row in target_cells:
        require(isinstance(row, Mapping), "TARGET_PAIR_COMPLETENESS_FAILED", "binding target-address pair must be an object")
        location_id = str(row.get("physical_location_id"))
        require(location_id not in seen_locations, "TARGET_PAIR_DUPLICATE_LOCATION", "binding target-address pairs duplicate a physical location")
        seen_locations.add(location_id)
        prior = row.get("prior")
        current = row.get("current_2026")
        require(isinstance(prior, Mapping) and prior.get("source_role") == PRIOR_VINTAGE_TEMPORAL_SOURCE, "TARGET_PRIOR_SOURCE_ROLE_MISMATCH", "prior target evidence is not bound to the prior-vintage source role")
        require(isinstance(current, Mapping) and current.get("source_role") == CURRENT_2026_TEMPORAL_SOURCE, "TARGET_CURRENT_SOURCE_ROLE_MISMATCH", "2026 target evidence is not bound to the 2026 source role")
    mapping_locations = {str(location.get("physical_location_id")) for location in locations if isinstance(location, Mapping)}
    require(seen_locations == mapping_locations, "TARGET_PAIR_LOCATION_MISMATCH", "binding target-address pairs differ from the frozen MODEL-04 cohort")
    finalization = package.get("finalization")
    require(isinstance(finalization, Mapping) and finalization.get("mandatory_reconciliations_passed") is True and finalization.get("target_values_accessed") is False and finalization.get("ready_marker_written_last") is True, "BINDING_FINALIZATION_CONFORMANCE_FAILED", "binding finalization assertions are incomplete")
    _assert_no_value_payloads(package)


class ProtectedBindingRun:
    """One immutable protected PIPE-02 binding run."""

    def __init__(
        self,
        protected_root: Path,
        repository_root: Path,
        *,
        binding_run_id: str | None = None,
        package_version: str = BINDING_PACKAGE_VERSION,
        supersedes: str | None = None,
    ):
        self.protected_root = protected_root.resolve()
        self.repository_root = repository_root.resolve()
        require(not _is_within(self.protected_root, self.repository_root), "PROTECTED_ROOT_INSIDE_REPOSITORY", "PIPE-02 output root must remain outside Git")
        self.binding_run_id = binding_run_id or f"pbind-{uuid.uuid4()}"
        require(self.binding_run_id.startswith("pbind-") and all(character.isalnum() or character in "-_" for character in self.binding_run_id), "BINDING_RUN_ID_INVALID", "binding run ID must be opaque and filesystem-safe")
        require(bool(package_version), "BINDING_VERSION_INVALID", "binding package version is required")
        if supersedes is not None:
            require(package_version != BINDING_PACKAGE_VERSION, "BINDING_SUPERSESSION_VERSION_REQUIRED", "a correction must use a new package version")
            require(supersedes.startswith("pbind-"), "BINDING_SUPERSESSION_INVALID", "supersession must name an earlier binding run")
        self.package_version = package_version
        self.supersedes = supersedes
        self.run_dir = self.protected_root / "bindings" / self.binding_run_id
        require(not self.run_dir.exists(), "BINDING_ALREADY_EXISTS", "never overwrite an incomplete or finalized protected binding")
        self.run_dir.mkdir(parents=True, exist_ok=False)
        write_json_exclusive(
            self.run_dir / "binding_state.json",
            {
                "binding_run_id": self.binding_run_id,
                "state": "incomplete",
                "finalization_state": "not_started",
                "package_version": package_version,
                "supersedes": supersedes,
            },
        )

    def finalize(self, semantic_package: Mapping[str, Any]) -> dict[str, Any]:
        require(self.package_version == semantic_package.get("version"), "BINDING_VERSION_MISMATCH", "staged binding version differs from package version")
        require(semantic_package.get("package_id") == BINDING_PACKAGE_ID, "BINDING_IDENTITY_MISMATCH", "binding package identity mismatch")
        require(semantic_package.get("supersedes") == self.supersedes, "BINDING_SUPERSESSION_MISMATCH", "binding supersession lineage mismatch")
        _validate_semantic_package(semantic_package)
        semantic = copy.deepcopy(dict(semantic_package))
        protected_hash = content_digest(semantic)
        stable_identity = f"pipe02-binding:sha256:{protected_hash}"
        package = {
            **semantic,
            "protected_content_sha256": protected_hash,
            "stable_binding_identity": stable_identity,
            "protected_content_hash_semantics": "SHA-256 of canonical UTF-8 JSON before adding protected_content_sha256, stable_binding_identity, and protected_content_hash_semantics; recursively sorted keys, compact separators, Unicode preserved, no NaN.",
        }
        package_path = self.run_dir / "pipe02_protected_validation_access_binding.json"
        write_json_exclusive(package_path, package)
        manifest = {
            "binding_run_id": self.binding_run_id,
            "package_id": BINDING_PACKAGE_ID,
            "package_version": self.package_version,
            "binding_schema_version": BINDING_SCHEMA_VERSION,
            "state": "ready",
            "finalization_state": "complete",
            "supersedes": self.supersedes,
            "protected_content_sha256": protected_hash,
            "stable_binding_identity": stable_identity,
            "package_file_sha256": file_sha256(package_path),
            "upstream": {
                "model04": f"{MODEL04_PACKAGE_ID}@{MODEL04_PACKAGE_VERSION}",
                "model05": f"{PREREGISTRATION_ID}@{PREREGISTRATION_VERSION}",
                "pipe01_run": EXPECTED_PIPE_RUN_ID,
                "pipe01_freeze_commitment": EXPECTED_PIPE_FREEZE_COMMITMENT,
            },
        }
        write_json_exclusive(self.run_dir / "binding_manifest.json", manifest)
        nonce = new_nonce()
        commitment = freeze_commitment(content_digest(manifest), nonce)
        nonce_path = self.run_dir / "binding_nonce.bin"
        with nonce_path.open("xb") as handle:
            handle.write(nonce)
            handle.flush()
            os.fsync(handle.fileno())
        write_json_exclusive(
            self.run_dir / "commitment_evidence.json",
            {"domain": DOMAIN_SEPARATOR.decode("utf-8"), "commitment_sha256": commitment},
        )
        # The ready marker is deliberately the final write.
        write_json_exclusive(
            self.run_dir / "READY.json",
            {
                "binding_run_id": self.binding_run_id,
                "package_id": BINDING_PACKAGE_ID,
                "package_version": self.package_version,
                "state": "ready",
                "finalization_state": "complete",
                "protected_content_sha256": protected_hash,
                "stable_binding_identity": stable_identity,
                "commitment_sha256": commitment,
            },
        )
        return {
            "binding_run_id": self.binding_run_id,
            "protected_content_sha256": protected_hash,
            "stable_binding_identity": stable_identity,
            "commitment_sha256": commitment,
            "state": "ready",
            "run_dir": self.run_dir,
        }


def protected_binding_is_ready(run_dir: Path) -> bool:
    return (run_dir / "READY.json").is_file()


@dataclass(frozen=True)
class BindingResult:
    binding_run_id: str
    protected_content_sha256: str
    stable_binding_identity: str
    commitment_sha256: str
    run_dir: Path
    temporal_location_count: int
    target_address_count: int
    target_access_audits: Mapping[str, TargetAccessAudit]


def execute_protected_binding(
    *,
    repository_root: Path,
    resolver: ProtectedHandleResolver,
    binding_run_id: str | None = None,
    package_version: str = BINDING_PACKAGE_VERSION,
    supersedes: str | None = None,
) -> BindingResult:
    """Build and finalize one exact protected binding after all checks pass."""
    root = repository_root.resolve()
    request = resolver.binding_request
    required_request_fields = {
        "model04_package_handle",
        "model04_verification_material_handle",
        "pipe01_run_directory_handle",
        "prior_vintage_target_workbook_handle",
        "current_2026_target_workbook_handle",
        "binding_output_root_handle",
    }
    missing = sorted(required_request_fields - set(request))
    unexpected = sorted(set(request) - required_request_fields)
    require(not missing and not unexpected, "BINDING_REQUEST_INVALID", "binding request must contain exactly the required protected handles")
    output = resolver.resolve(str(request["binding_output_root_handle"]), "pipe02_output_root")
    staged = ProtectedBindingRun(output.path, root, binding_run_id=binding_run_id, package_version=package_version, supersedes=supersedes)

    model04_package = resolver.resolve(str(request["model04_package_handle"]), "model04_package")
    model04_verification = resolver.resolve(str(request["model04_verification_material_handle"]), "model04_verification_material")
    commitment_path = root / "config/model/model04_validation_identity_role_anchor_commitment.json"
    commitment = _load_json_object(commitment_path, "MODEL04_COMMITMENT_AUTHORITY_MISSING")
    require(commitment.get("artifact_id") == COMMITMENT_ID and commitment.get("version") == COMMITMENT_VERSION, "MODEL04_COMMITMENT_IDENTITY_MISMATCH", "MODEL-04 repository-safe commitment identity differs")
    require(commitment.get("commitment_sha256") == EXPECTED_MODEL04_COMMITMENT, "MODEL04_COMMITMENT_AUTHORITY_MISMATCH", "MODEL-04 accepted commitment differs")
    model04 = load_model04_binding(model04_package.path, model04_verification.path, commitment_path)
    temporal_mapping, requested_pairs_by_role = derive_temporal_mapping(model04)

    authorities = load_repository_authorities(root)
    require(
        authorities.preregistration["artifact_id"] == PREREGISTRATION_ID
        and authorities.preregistration["version"] == PREREGISTRATION_VERSION
        and authorities.preregistration["content_sha256"] == EXPECTED_MODEL05_SHA256,
        "MODEL05_AUTHORITY_MISMATCH",
        "MODEL-05 preregistration identity/version/hash differs",
    )

    pipe_run = resolver.resolve(str(request["pipe01_run_directory_handle"]), "pipe01_run_directory")
    pipe_binding = reconcile_pipe_freeze(pipe_run.path, pipe_run.handle, temporal_mapping)

    request_field_by_role = {
        PRIOR_VINTAGE_TEMPORAL_SOURCE: "prior_vintage_target_workbook_handle",
        CURRENT_2026_TEMPORAL_SOURCE: "current_2026_target_workbook_handle",
    }
    resource_kind_by_role = {
        PRIOR_VINTAGE_TEMPORAL_SOURCE: "prior_vintage_temporal_workbook",
        CURRENT_2026_TEMPORAL_SOURCE: "current_2026_temporal_workbook",
    }
    target_workbooks = {
        role: resolver.resolve(str(request[field]), resource_kind_by_role[role])
        for role, field in request_field_by_role.items()
    }
    require(len({workbook.handle for workbook in target_workbooks.values()}) == 2, "TARGET_SOURCE_HANDLE_REUSED", "one workbook handle cannot implicitly satisfy both target-source roles")
    target_authorities = resolver.target_source_authorities
    policies: dict[str, MinimumTargetProjectionPolicy] = {}
    target_addresses_by_role: dict[str, list[dict[str, Any]]] = {}
    audits: dict[str, TargetAccessAudit] = {}
    for role in (PRIOR_VINTAGE_TEMPORAL_SOURCE, CURRENT_2026_TEMPORAL_SOURCE):
        target_workbook = target_workbooks[role]
        target_authority = target_authorities[role]
        require(target_authority.get("authority_id") and target_authority.get("provenance_class"), "TARGET_SOURCE_AUTHORITY_UNRESOLVED", "target-source identity/provenance is incomplete")
        require(target_authority.get("workbook_handle") == target_workbook.handle, "TARGET_SOURCE_HANDLE_MISMATCH", "target-source authority references another role or handle")
        require(target_authority.get("byte_hash_permitted") is False, "TARGET_SOURCE_HASH_POLICY_INVALID", "PIPE-02 target source must prohibit new whole-workbook hashing")
        projection_document = target_authority.get("projection")
        require(isinstance(projection_document, Mapping), "TARGET_PROJECTION_AUTHORITY_UNRESOLVED", "minimum target projection authority is absent")
        policy = MinimumTargetProjectionPolicy(projection_document, target_workbook.handle, role)
        target_addresses, audit = project_target_addresses(target_workbook.path, policy, requested_pairs_by_role[role])
        require(audit.target_payload_decode_calls == 0, "TARGET_VALUE_ACCESS_DETECTED", "target payload decoder was invoked")
        policies[role] = policy
        target_addresses_by_role[role] = target_addresses
        audits[role] = audit

    target_addresses = [
        item
        for role in (PRIOR_VINTAGE_TEMPORAL_SOURCE, CURRENT_2026_TEMPORAL_SOURCE)
        for item in target_addresses_by_role[role]
    ]

    addresses_by_location: dict[str, list[Mapping[str, Any]]] = {}
    for item in target_addresses:
        addresses_by_location.setdefault(str(item["physical_location_id"]), []).append(item)
    projection_rows: list[dict[str, Any]] = []
    for location in temporal_mapping:
        location_id = str(location["physical_location_id"])
        pairs = addresses_by_location.get(location_id, [])
        require(len(pairs) == 2, "TARGET_PAIR_COMPLETENESS_FAILED", "each temporal location must resolve exactly two independently sourced target addresses")
        by_role = {str(pair["source_role"]): pair for pair in pairs}
        require(len(by_role) == 2, "TARGET_PAIR_SOURCE_DUPLICATE", "each temporal location must resolve one address from each target-source role")
        require(set(by_role) == REQUIRED_TARGET_SOURCE_ROLES, "TARGET_PAIR_COMPLETENESS_FAILED", "each temporal location must resolve exactly one prior and one 2026 target address")
        projection_rows.append(
            {
                "physical_location_id": location_id,
                "prior": {
                    "source_role": PRIOR_VINTAGE_TEMPORAL_SOURCE,
                    "lineage_key": by_role[PRIOR_VINTAGE_TEMPORAL_SOURCE]["lineage_key"],
                    "forecast_vintage": by_role[PRIOR_VINTAGE_TEMPORAL_SOURCE]["vintage_year"],
                    "isolated_sales_cell_address": by_role[PRIOR_VINTAGE_TEMPORAL_SOURCE]["isolated_sales_cell_address"],
                },
                "current_2026": {
                    "source_role": CURRENT_2026_TEMPORAL_SOURCE,
                    "lineage_key": by_role[CURRENT_2026_TEMPORAL_SOURCE]["lineage_key"],
                    "forecast_vintage": 2026,
                    "isolated_sales_cell_address": by_role[CURRENT_2026_TEMPORAL_SOURCE]["isolated_sales_cell_address"],
                },
            }
        )
    require(set(addresses_by_location) == {str(location["physical_location_id"]) for location in temporal_mapping}, "TARGET_PAIR_LOCATION_MISMATCH", "target-source location evidence differs from the frozen MODEL-04 cohort")

    denied_scope = [
        "Impacted Sales",
        "PROSPECTIVE_MILWAUKEE_HOLDOUT",
        "Madison",
        "AMBIGUOUS_QUARANTINE",
        "unrelated rows",
        "unrelated columns",
        "unknown fields",
        "non-preregistered target measures",
        "target values",
    ]
    semantic_package = {
        "$schema": BINDING_SCHEMA_VERSION,
        "package_id": BINDING_PACKAGE_ID,
        "version": package_version,
        "binding_run_id": staged.binding_run_id,
        "state": "ready",
        "model_authority": {
            "package_id": MODEL04_PACKAGE_ID,
            "package_version": MODEL04_PACKAGE_VERSION,
            "package_handle": model04_package.handle,
            "verification_material_handle": model04_verification.handle,
            "commitment_artifact_id": COMMITMENT_ID,
            "commitment_artifact_version": COMMITMENT_VERSION,
            "commitment_sha256": EXPECTED_MODEL04_COMMITMENT,
            "commitment_reconciled": True,
        },
        "model05_authority": {
            "preregistration_id": PREREGISTRATION_ID,
            "version": PREREGISTRATION_VERSION,
            "content_sha256": EXPECTED_MODEL05_SHA256,
        },
        "pipe01_authority": {
            **dict(pipe_binding.run_reference),
            "artifacts_by_temporal_location": dict(pipe_binding.artifact_bindings),
            "upstream_frozen_artifacts_regenerated": False,
        },
        "target_source_authorities": [
            {
                "source_role": role,
                "authority_id": target_authorities[role]["authority_id"],
                "provenance_class": target_authorities[role]["provenance_class"],
                "workbook_handle": target_workbooks[role].handle,
                "whole_workbook_hash_computed": False,
                "sheet_name": policies[role].sheet_name,
            }
            for role in (PRIOR_VINTAGE_TEMPORAL_SOURCE, CURRENT_2026_TEMPORAL_SOURCE)
        ],
        "temporal_eligibility_mapping": temporal_mapping,
        "minimum_target_projection": {
            "projection_id": MinimumTargetProjectionPolicy.PROJECTION_ID,
            "version": MinimumTargetProjectionPolicy.VERSION,
            "default_deny": True,
            "source_projections": [
                {
                    "source_role": role,
                    "workbook_handle": target_workbooks[role].handle,
                    "projection_id": policies[role].PROJECTION_ID,
                    "version": policies[role].VERSION,
                    "permitted_pair_role": policies[role].permitted_pair_role,
                    "sheet_name": policies[role].sheet_name,
                    "allowed_fields": sorted(policies[role].ALLOWED_FIELDS),
                    "denied_scope": denied_scope,
                }
                for role in (PRIOR_VINTAGE_TEMPORAL_SOURCE, CURRENT_2026_TEMPORAL_SOURCE)
            ],
            "allowed_scope": {
                "market": "milwaukee",
                "role": "TEMPORAL_VALIDATION",
                "row_scope": "frozen_model04_repeated_physical_locations_only",
                "fields": ["minimum_lineage_join_key", "forecast_vintage", "isolated_sales_cell_address"],
                "vintage_pair": ["most_recent_eligible_prior", 2026],
            },
            "denied_scope": denied_scope,
            "target_cells": projection_rows,
            "target_access_audits": {role: audits[role].disclosure_safe() for role in sorted(audits)},
        },
        "protected_handle_registry_identity": resolver.registry_identity,
        "finalization": {
            "mandatory_reconciliations_passed": True,
            "target_values_accessed": False,
            "ready_marker_written_last": True,
        },
        "supersedes": supersedes,
        "supersession_policy": "Never overwrite a finalized binding. A correction requires a new version and opaque binding run with explicit supersedes lineage.",
    }
    finalized = staged.finalize(semantic_package)
    return BindingResult(
        finalized["binding_run_id"],
        finalized["protected_content_sha256"],
        finalized["stable_binding_identity"],
        finalized["commitment_sha256"],
        finalized["run_dir"],
        len(temporal_mapping),
        len(target_addresses),
        audits,
    )


def build_disclosure_safe_result(result: BindingResult) -> dict[str, Any]:
    report = {
        "completion_state": "Dual-source correction complete and ready for PIPE acceptance review",
        "acceptance_recommendation": "Support PIPE-02 acceptance review; recommendation is evidence only and does not self-accept or resume MODEL-07.",
        "package_id": BINDING_PACKAGE_ID,
        "version": BINDING_PACKAGE_VERSION,
        "protected_content_sha256": result.protected_content_sha256,
        "stable_binding_identity": result.stable_binding_identity,
        "pipe_run_id": EXPECTED_PIPE_RUN_ID,
        "model04_commitment_reconciled": True,
        "pipe01_freeze_reconciled": True,
        "target_source_authorities_resolved": 2,
        "temporal_location_count": result.temporal_location_count,
        "target_address_count": result.target_address_count,
        "target_values_accessed": False,
        "protected_output_outside_git": True,
    }
    serialized = json.dumps(report, sort_keys=True)
    for forbidden in ("source_row", "cell_address", "nonce", "physical_location_id", "latitude", "longitude", "prediction_candidate", "\\\\", ":\\"):
        require(forbidden not in serialized, "DISCLOSURE_SAFE_REPORT_VIOLATION", "protected detail entered the disclosure-safe PIPE-02 report")
    return report
