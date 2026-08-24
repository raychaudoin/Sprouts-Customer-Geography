"""Immutable protected MODEL-12 seed and field-scoring materialization."""

from __future__ import annotations

import copy
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import uuid
from typing import Any, Mapping, Sequence

from sprouts_customer_geography.pipe01.canonical import content_digest, file_sha256, write_json_exclusive
from sprouts_customer_geography.pipe01.commitment import freeze_commitment, new_nonce
from sprouts_customer_geography.pipe01.errors import require
from sprouts_customer_geography.pipe02.resolver import _is_within

from .contract import CONTRACT_ID, CONTRACT_VERSION, verify_repository_authority
from .frozen import FrozenScoringState, load_frozen_scoring_state
from .public import load_verified_public_dependencies, score_anchor_batch
from .resolver import ProtectedHandleResolver
from .source import IDENTITY_PACKAGE_ID, execute_identity_projection, validate_identity_package


FEATURE_PACKAGE_ID = "MODEL12_MICHIGAN_PUBLIC_FEATURE_PACKAGE_V1"
SCORING_PACKAGE_ID = "MODEL12_MICHIGAN_FROZEN_SCORING_PACKAGE_V1"
FIELD_PACKAGE_ID = "MODEL12_MICHIGAN_FIELD_SCORING_PACKAGE_V1"
PACKAGE_VERSION = "1.0.0"
STAGE_FILENAMES = {
    "identity": "model12_michigan_physical_location_identity_package.json",
    "public_features": "model12_michigan_public_feature_package.json",
    "frozen_scoring": "model12_michigan_frozen_scoring_package.json",
    "field_scoring": "model12_michigan_field_scoring_package.json",
}


def _write_bytes_exclusive(path: Path, value: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(value)
        handle.flush()
        os.fsync(handle.fileno())


def _load_object(path: Path, code: str) -> dict[str, Any]:
    require(path.is_file(), code, "required protected JSON is absent")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        require(False, code, "required protected JSON is unreadable")
    require(isinstance(value, dict), code, "required protected JSON must be an object")
    return value


@dataclass(frozen=True)
class StageResult:
    stage_name: str
    stage_dir: Path
    package_path: Path
    protected_content_sha256: str
    commitment_sha256: str


class ProtectedRun:
    """One immutable incomplete-first protected run with READY written last."""

    def __init__(
        self,
        output_root: Path,
        repository_root: Path,
        *,
        collection: str,
        run_id_prefix: str,
        run_id: str | None,
        supersedes: str | None = None,
    ):
        self.output_root = output_root.resolve()
        repository = repository_root.resolve()
        require(self.output_root.is_dir() and not _is_within(self.output_root, repository), "MODEL12_PROTECTED_OUTPUT_INVALID", "MODEL-12 output root must exist outside Git")
        self.run_id = run_id or run_id_prefix + str(uuid.uuid4())
        require(bool(re.fullmatch(re.escape(run_id_prefix) + r"[A-Za-z0-9_-]+", self.run_id)), "MODEL12_RUN_ID_INVALID", "MODEL-12 run identity is invalid")
        if supersedes is not None:
            require(isinstance(supersedes, str) and supersedes.startswith(run_id_prefix), "MODEL12_SUPERSESSION_INVALID", "MODEL-12 supersession identity is invalid")
        collection_root = self.output_root / collection
        collection_root.mkdir(exist_ok=True)
        self.run_dir = collection_root / self.run_id
        require(not self.run_dir.exists(), "MODEL12_RUN_IMMUTABLE", "never overwrite a MODEL-12 protected run")
        self.run_dir.mkdir()
        self.supersedes = supersedes
        self.stages: dict[str, StageResult] = {}
        write_json_exclusive(
            self.run_dir / "INCOMPLETE.json",
            {
                "state": "incomplete",
                "finalization_state": "not_ready",
                "package_version": PACKAGE_VERSION,
                "supersedes": supersedes,
            },
        )

    def write_stage(self, stage_name: str, semantic_package: Mapping[str, Any]) -> StageResult:
        require(stage_name in STAGE_FILENAMES and stage_name not in self.stages, "MODEL12_STAGE_INVALID", "MODEL-12 stage is invalid or duplicate")
        stage_dir = self.run_dir / stage_name
        require(not stage_dir.exists(), "MODEL12_STAGE_IMMUTABLE", "never overwrite a MODEL-12 protected stage")
        stage_dir.mkdir()
        write_json_exclusive(stage_dir / "INCOMPLETE.json", {"stage": stage_name, "state": "incomplete", "finalization_state": "not_ready"})
        protected_hash = content_digest(semantic_package)
        stable = f"model12-{stage_name}:sha256:{protected_hash}"
        package = {
            **copy.deepcopy(dict(semantic_package)),
            "protected_content_sha256": protected_hash,
            "stable_package_identity": stable,
        }
        package_path = stage_dir / STAGE_FILENAMES[stage_name]
        write_json_exclusive(package_path, package)
        nonce = new_nonce()
        nonce_path = stage_dir / "commitment_nonce.bin"
        _write_bytes_exclusive(nonce_path, nonce)
        commitment = freeze_commitment(file_sha256(package_path), nonce)
        write_json_exclusive(
            stage_dir / "commitment_evidence.json",
            {
                "domain": f"sprouts-customer-geography/model12/{stage_name}-commitment/v1",
                "commitment_sha256": commitment,
                "protected_package_digest_disclosed": False,
                "nonce_disclosed": False,
                "protected_content_disclosed": False,
            },
        )
        write_json_exclusive(
            stage_dir / "READY.json",
            {
                "stage": stage_name,
                "state": "ready",
                "finalization_state": "complete",
                "package_id": semantic_package.get("package_id"),
                "package_version": semantic_package.get("version"),
                "protected_content_sha256": protected_hash,
                "stable_package_identity": stable,
                "package_file_sha256": file_sha256(package_path),
                "commitment_sha256": commitment,
                "ready_marker_written_last": True,
            },
        )
        result = StageResult(stage_name, stage_dir, package_path, protected_hash, commitment)
        self.stages[stage_name] = result
        return result

    def finalize(self, *, package_id: str, aggregate: Mapping[str, Any], expected_stages: Sequence[str]) -> None:
        require(list(self.stages) == list(expected_stages), "MODEL12_STAGE_SEQUENCE_MISMATCH", "MODEL-12 protected stages are missing or out of order")
        write_json_exclusive(
            self.run_dir / "READY.json",
            {
                "state": "ready",
                "finalization_state": "complete",
                "package_id": package_id,
                "package_version": PACKAGE_VERSION,
                "stages": {
                    name: {
                        "package_id": _load_object(result.package_path, "MODEL12_STAGE_PACKAGE_UNRESOLVED")["package_id"],
                        "protected_content_sha256": result.protected_content_sha256,
                        "commitment_sha256": result.commitment_sha256,
                    }
                    for name, result in self.stages.items()
                },
                "aggregate_conformance": dict(aggregate),
                "supersedes": self.supersedes,
                "ready_marker_written_last": True,
            },
        )


def _contract_authority(contract: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "artifact_id": contract["artifact_id"],
        "version": contract["version"],
        "content_sha256": contract["content_sha256"],
    }


def _feature_package(identity: Mapping[str, Any], scored: Sequence[Mapping[str, Any]], contract: Mapping[str, Any], registry_identity: str) -> dict[str, Any]:
    by_location = {str(item["opaque_anchor_id"]): item for item in scored}
    physical: list[dict[str, Any]] = []
    for location in identity["physical_locations"]:
        physical_id = str(location["physical_location_id"])
        if location["quarantined"]:
            physical.append(
                {
                    "physical_location_id": physical_id,
                    "state": "IDENTITY_QUARANTINED",
                    "quarantined": True,
                    "quarantine_reason": location["quarantine_reason"],
                    "canonical_target_blind_coordinate": None,
                    "containing_tract_geoid": None,
                    "member_counts": None,
                    "public_features": None,
                    "data03_feature_profiles": None,
                    "required_frozen_feature_order": None,
                    "support_completeness": None,
                    "any_support_truncation": False,
                    "spatial_lineage": None,
                    "public_source_lineage": None,
                    "noncomputability_reasons": ["IDENTITY_QUARANTINED"],
                }
            )
            continue
        result = by_location[physical_id]
        physical.append(
            {
                "physical_location_id": physical_id,
                "state": result["state"],
                "quarantined": False,
                "quarantine_reason": None,
                "canonical_target_blind_coordinate": dict(location["canonical_target_blind_coordinate"]),
                "containing_tract_geoid": result["containing_tract_geoid"],
                "member_counts": result["member_counts"],
                "public_features": result["public_features"],
                "data03_feature_profiles": result["data03_feature_profiles"],
                "required_frozen_feature_order": result["required_frozen_feature_order"],
                "support_completeness": result["support_completeness"],
                "any_support_truncation": result["any_support_truncation"],
                "spatial_lineage": result["spatial_lineage"],
                "public_source_lineage": result["public_source_lineage"],
                "noncomputability_reasons": result["noncomputability_reasons"],
            }
        )
    observations = [
        {
            "source_observation_id": observation["source_observation_id"],
            "physical_location_id": observation["physical_location_id"],
            "public_feature_state": next(item["state"] for item in physical if item["physical_location_id"] == observation["physical_location_id"]),
        }
        for observation in identity["source_observations"]
    ]
    package = {
        "$schema": "model12-michigan-public-feature-package-v1",
        "package_id": FEATURE_PACKAGE_ID,
        "version": PACKAGE_VERSION,
        "state": "ready",
        "contract_authority": _contract_authority(contract),
        "identity_package_id": identity["package_id"],
        "physical_locations": physical,
        "source_observations": observations,
        "aggregate_conformance": {
            "source_observation_count": len(observations),
            "physical_location_count": len(physical),
            "quarantined_physical_location_count": sum(item["quarantined"] for item in physical),
            "nonquarantined_physical_location_count": sum(not item["quarantined"] for item in physical),
            "public_feature_noncomputable_physical_location_count": sum(item["state"] == "MODEL_SCORE_NONCOMPUTABLE" for item in physical),
            "any_support_truncation_physical_location_count": sum(item["any_support_truncation"] for item in physical),
            "complete_location_accounting": True,
        },
        "feature_construction": {
            "data04_reused_exactly": True,
            "geo05_reused_exactly": True,
            "model11_aggregation_reused_exactly": True,
            "michigan_redundancy_screen_performed": False,
            "michigan_feature_selection_performed": False,
            "imputation_performed": False,
            "member_tract_dropping_performed": False,
            "support_completeness_threshold_created": False,
        },
        "target_access": {"target_body_values_accessed": 0, "target_body_values_materialized": 0, "pipe_target_binding_created": False},
        "protected_handle_registry_identity": registry_identity,
    }
    validate_feature_package(package)
    return package


def validate_feature_package(package: Mapping[str, Any]) -> None:
    require(package.get("package_id") == FEATURE_PACKAGE_ID and package.get("version") == PACKAGE_VERSION and package.get("state") == "ready", "MODEL12_FEATURE_PACKAGE_MISMATCH", "MODEL-12 feature package identity or state differs")
    physical = package.get("physical_locations")
    observations = package.get("source_observations")
    require(isinstance(physical, list) and physical and isinstance(observations, list) and observations, "MODEL12_FEATURE_PACKAGE_SCHEMA_INVALID", "MODEL-12 feature locations or observations are absent")
    ids = [item.get("physical_location_id") for item in physical]
    require(len(ids) == len(set(ids)) and all(item.get("physical_location_id") in set(ids) for item in observations), "MODEL12_FEATURE_PACKAGE_ACCOUNTING_MISMATCH", "MODEL-12 feature identity accounting differs")
    aggregate = package.get("aggregate_conformance", {})
    require(
        aggregate.get("source_observation_count") == len(observations)
        and aggregate.get("physical_location_count") == len(physical)
        and aggregate.get("quarantined_physical_location_count") == sum(bool(item["quarantined"]) for item in physical)
        and aggregate.get("nonquarantined_physical_location_count") == sum(not bool(item["quarantined"]) for item in physical)
        and aggregate.get("complete_location_accounting") is True,
        "MODEL12_FEATURE_PACKAGE_ACCOUNTING_MISMATCH",
        "MODEL-12 feature aggregate accounting differs",
    )
    require(all(value in (0, False) for value in package.get("target_access", {}).values()), "MODEL12_TARGET_ACCESS_VIOLATION", "target evidence entered MODEL-12 public features")


def _scoring_package(identity: Mapping[str, Any], scored: Sequence[Mapping[str, Any]], frozen: FrozenScoringState, contract: Mapping[str, Any], registry_identity: str) -> dict[str, Any]:
    by_location = {str(item["opaque_anchor_id"]): item for item in scored}
    physical: list[dict[str, Any]] = []
    for location in identity["physical_locations"]:
        physical_id = str(location["physical_location_id"])
        if location["quarantined"]:
            physical.append(
                {
                    "physical_location_id": physical_id,
                    "score_computability_status": "IDENTITY_QUARANTINED",
                    "noncomputability_reasons": ["IDENTITY_QUARANTINED"],
                    "household_opportunity": None,
                    "customer_fit_proxy": None,
                    "modeled_target_mass": None,
                    "any_support_truncation": False,
                }
            )
        else:
            result = by_location[physical_id]
            physical.append(
                {
                    "physical_location_id": physical_id,
                    "score_computability_status": result["score_computability_status"],
                    "noncomputability_reasons": result["noncomputability_reasons"],
                    "household_opportunity": result["household_opportunity"],
                    "customer_fit_proxy": result["customer_fit_proxy"],
                    "modeled_target_mass": result["modeled_target_mass"],
                    "any_support_truncation": result["any_support_truncation"],
                }
            )
    by_physical = {str(item["physical_location_id"]): item for item in physical}
    observations = [
        {
            "source_observation_id": observation["source_observation_id"],
            "physical_location_id": observation["physical_location_id"],
            "score_computability_status": by_physical[str(observation["physical_location_id"])]["score_computability_status"],
            "household_opportunity": by_physical[str(observation["physical_location_id"])]["household_opportunity"],
            "customer_fit_proxy": by_physical[str(observation["physical_location_id"])]["customer_fit_proxy"],
            "modeled_target_mass": by_physical[str(observation["physical_location_id"])]["modeled_target_mass"],
        }
        for observation in identity["source_observations"]
    ]
    aggregate = {
        "source_observation_count": len(observations),
        "physical_location_count": len(physical),
        "quarantined_physical_location_count": sum(item["score_computability_status"] == "IDENTITY_QUARANTINED" for item in physical),
        "computable_frozen_score_physical_location_count": sum(item["score_computability_status"] == "MODEL_SCORE_COMPUTABLE" for item in physical),
        "noncomputable_frozen_score_physical_location_count": sum(item["score_computability_status"] == "MODEL_SCORE_NONCOMPUTABLE" for item in physical),
        "any_support_truncation_physical_location_count": sum(item["any_support_truncation"] for item in physical),
        "complete_location_accounting": True,
    }
    package = {
        "$schema": "model12-michigan-frozen-scoring-package-v1",
        "package_id": SCORING_PACKAGE_ID,
        "version": PACKAGE_VERSION,
        "state": "ready",
        "contract_authority": _contract_authority(contract),
        "identity_package_id": identity["package_id"],
        "public_feature_package_id": FEATURE_PACKAGE_ID,
        "model_lineage": frozen.lineage,
        "physical_locations": physical,
        "source_observations": observations,
        "aggregate_conformance": aggregate,
        "execution_boundary": {
            "michigan_target_body_values_accessed": 0,
            "model_refit_performed": False,
            "model_retraining_performed": False,
            "model_retuning_performed": False,
            "michigan_feature_selection_performed": False,
            "michigan_redundancy_screen_performed": False,
            "prediction_recalibration_performed": False,
            "michigan_distribution_used_to_modify_model": False,
            "household_opportunity_customer_fit_and_modeled_target_mass_separate": True,
        },
        "interpretation_boundary": dict(contract["interpretation_boundary"]),
        "protected_handle_registry_identity": registry_identity,
    }
    validate_scoring_package(package)
    return package


def validate_scoring_package(package: Mapping[str, Any]) -> None:
    require(package.get("package_id") == SCORING_PACKAGE_ID and package.get("version") == PACKAGE_VERSION and package.get("state") == "ready", "MODEL12_SCORING_PACKAGE_MISMATCH", "MODEL-12 scoring package identity or state differs")
    physical = package.get("physical_locations")
    observations = package.get("source_observations")
    require(isinstance(physical, list) and physical and isinstance(observations, list) and observations, "MODEL12_SCORING_PACKAGE_SCHEMA_INVALID", "MODEL-12 scoring locations or observations are absent")
    allowed = {"IDENTITY_QUARANTINED", "MODEL_SCORE_COMPUTABLE", "MODEL_SCORE_NONCOMPUTABLE"}
    require(all(item.get("score_computability_status") in allowed for item in physical), "MODEL12_SCORING_STATUS_INVALID", "MODEL-12 score status differs")
    for item in physical:
        values = (item.get("household_opportunity"), item.get("customer_fit_proxy"), item.get("modeled_target_mass"))
        if item["score_computability_status"] == "MODEL_SCORE_COMPUTABLE":
            require(all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in values), "MODEL12_SCORING_OUTPUT_SEMANTICS_MISMATCH", "computable score must preserve three numeric concepts")
        else:
            require(all(value is None for value in values), "MODEL12_SCORING_OUTPUT_SEMANTICS_MISMATCH", "noncomputable or quarantined score must not manufacture values")
    by_physical = {str(item["physical_location_id"]): item for item in physical}
    require(len(by_physical) == len(physical), "MODEL12_SCORING_PACKAGE_DUPLICATE", "MODEL-12 scoring physical location is duplicate")
    for observation in observations:
        physical_row = by_physical[str(observation["physical_location_id"])]
        require(
            observation["score_computability_status"] == physical_row["score_computability_status"]
            and observation["household_opportunity"] == physical_row["household_opportunity"]
            and observation["customer_fit_proxy"] == physical_row["customer_fit_proxy"]
            and observation["modeled_target_mass"] == physical_row["modeled_target_mass"],
            "MODEL12_REPEATED_LOCATION_SCORE_MISMATCH",
            "one repeated physical location has inconsistent observation scoring",
        )
    aggregate = package.get("aggregate_conformance", {})
    require(
        aggregate.get("source_observation_count") == len(observations)
        and aggregate.get("physical_location_count") == len(physical)
        and aggregate.get("quarantined_physical_location_count") + aggregate.get("computable_frozen_score_physical_location_count") + aggregate.get("noncomputable_frozen_score_physical_location_count") == len(physical)
        and aggregate.get("complete_location_accounting") is True,
        "MODEL12_SCORING_PACKAGE_ACCOUNTING_MISMATCH",
        "MODEL-12 scoring aggregate accounting differs",
    )
    boundary = package.get("execution_boundary", {})
    require(
        boundary.get("michigan_target_body_values_accessed") == 0
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
        )
        and boundary.get("household_opportunity_customer_fit_and_modeled_target_mass_separate") is True,
        "MODEL12_FROZEN_EXECUTION_BOUNDARY_MISMATCH",
        "MODEL-12 frozen execution boundary differs",
    )


@dataclass(frozen=True)
class MaterializationResult:
    run_dir: Path
    source_observation_count: int
    physical_location_count: int
    quarantine_count: int
    computable_score_count: int
    noncomputable_score_count: int
    support_truncation_count: int
    stage_commitments: Mapping[str, str]


def execute_protected_materialization(
    *,
    repository_root: Path,
    resolver: ProtectedHandleResolver,
    run_id: str | None = None,
    supersedes: str | None = None,
) -> MaterializationResult:
    root = repository_root.resolve()
    contract = verify_repository_authority(root)
    output = resolver.resolve(str(resolver.materialization_request["model12_output_root_handle"]), "model12_output_root").path
    staged = ProtectedRun(output, root, collection="model12-materializations", run_id_prefix="m12run-", run_id=run_id, supersedes=supersedes)
    identity = execute_identity_projection(resolver, _contract_authority(contract))
    validate_identity_package(identity)
    staged.write_stage("identity", identity)

    frozen = load_frozen_scoring_state(root, resolver)
    sources, support = load_verified_public_dependencies(
        root,
        resolver.public_dependencies["data04_ready_dir"],
        resolver.public_dependencies["geo05_support_dir"],
    )
    anchors = [
        {
            "opaque_anchor_id": location["physical_location_id"],
            "latitude": location["canonical_target_blind_coordinate"]["latitude"],
            "longitude": location["canonical_target_blind_coordinate"]["longitude"],
        }
        for location in identity["physical_locations"]
        if not location["quarantined"]
    ]
    scored = score_anchor_batch(anchors=anchors, support=support, sources=sources, frozen=frozen)
    feature_package = _feature_package(identity, scored, contract, resolver.registry_identity)
    staged.write_stage("public_features", feature_package)
    scoring_package = _scoring_package(identity, scored, frozen, contract, resolver.registry_identity)
    validate_scoring_package(scoring_package)
    staged.write_stage("frozen_scoring", scoring_package)
    aggregate = scoring_package["aggregate_conformance"]
    staged.finalize(package_id="MODEL12_MICHIGAN_TARGET_BLIND_FROZEN_SCORING_RUN_V1", aggregate=aggregate, expected_stages=("identity", "public_features", "frozen_scoring"))
    return MaterializationResult(
        run_dir=staged.run_dir,
        source_observation_count=int(aggregate["source_observation_count"]),
        physical_location_count=int(aggregate["physical_location_count"]),
        quarantine_count=int(aggregate["quarantined_physical_location_count"]),
        computable_score_count=int(aggregate["computable_frozen_score_physical_location_count"]),
        noncomputable_score_count=int(aggregate["noncomputable_frozen_score_physical_location_count"]),
        support_truncation_count=int(aggregate["any_support_truncation_physical_location_count"]),
        stage_commitments={name: result.commitment_sha256 for name, result in staged.stages.items()},
    )


def build_disclosure_safe_result(result: MaterializationResult) -> dict[str, Any]:
    return {
        "completion_state": "MODEL-12 protected Michigan frozen scoring ready",
        "source_observation_count": result.source_observation_count,
        "physical_location_count": result.physical_location_count,
        "quarantine_count": result.quarantine_count,
        "computable_frozen_score_count": result.computable_score_count,
        "noncomputable_frozen_score_count": result.noncomputable_score_count,
        "any_support_truncation_location_count": result.support_truncation_count,
        "michigan_target_body_values_accessed": 0,
        "model_refit_performed": False,
        "model_retuning_performed": False,
        "michigan_feature_selection_performed": False,
        "protected_output_outside_git": True,
        "protected_details_disclosed": False,
    }


def compare_materializations(first: Path, second: Path) -> dict[str, Any]:
    """Require byte-identical semantic packages across independent immutable runs."""

    first_dir = first.resolve()
    second_dir = second.resolve()
    require(first_dir != second_dir and first_dir.is_dir() and second_dir.is_dir(), "MODEL12_COMPARISON_INPUT_INVALID", "two distinct materialization directories are required")
    first_ready = _load_object(first_dir / "READY.json", "MODEL12_READY_UNRESOLVED")
    second_ready = _load_object(second_dir / "READY.json", "MODEL12_READY_UNRESOLVED")
    require(first_ready.get("state") == second_ready.get("state") == "ready", "MODEL12_READY_MISMATCH", "one MODEL-12 materialization is not READY")
    matches: dict[str, bool] = {}
    for stage in ("identity", "public_features", "frozen_scoring"):
        first_stage_ready = _load_object(first_dir / stage / "READY.json", "MODEL12_STAGE_READY_UNRESOLVED")
        second_stage_ready = _load_object(second_dir / stage / "READY.json", "MODEL12_STAGE_READY_UNRESOLVED")
        first_package = first_dir / stage / STAGE_FILENAMES[stage]
        second_package = second_dir / stage / STAGE_FILENAMES[stage]
        require(
            first_stage_ready.get("state") == second_stage_ready.get("state") == "ready"
            and first_stage_ready.get("package_file_sha256") == file_sha256(first_package)
            and second_stage_ready.get("package_file_sha256") == file_sha256(second_package),
            "MODEL12_STAGE_READY_MISMATCH",
            "one MODEL-12 stage READY binding differs",
        )
        matches[stage] = first_package.read_bytes() == second_package.read_bytes()
    aggregate_match = first_ready.get("aggregate_conformance") == second_ready.get("aggregate_conformance")
    require(all(matches.values()) and aggregate_match, "MODEL12_DETERMINISTIC_RERUN_MISMATCH", "independent MODEL-12 semantic outputs differ")
    return {
        "state": "MATCH",
        "semantic_stage_count": len(matches),
        "semantic_packages_byte_identical": True,
        "aggregate_conformance_identical": True,
        "target_body_values_accessed": 0,
        "protected_details_disclosed": False,
    }


def _load_anchor_file(path: Path, repository_root: Path) -> list[dict[str, Any]]:
    resolved = path.resolve()
    require(resolved.is_file() and not _is_within(resolved, repository_root.resolve()), "MODEL12_FIELD_INPUT_INVALID", "field scorer input must be an explicit local file outside Git")
    try:
        value = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        require(False, "MODEL12_FIELD_INPUT_INVALID", "field scorer input is unreadable")
    require(isinstance(value, list) and value, "MODEL12_FIELD_INPUT_INVALID", "field scorer input must be a nonempty JSON array")
    return [dict(item) if isinstance(item, Mapping) else item for item in value]


@dataclass(frozen=True)
class FieldScoringResult:
    run_dir: Path
    anchor_count: int
    computable_score_count: int
    noncomputable_score_count: int
    support_truncation_count: int


def execute_field_scoring(
    *,
    repository_root: Path,
    resolver: ProtectedHandleResolver,
    input_path: Path,
    run_id: str | None = None,
) -> FieldScoringResult:
    """Score explicit opaque Michigan anchors without opening the seed source."""

    root = repository_root.resolve()
    contract = verify_repository_authority(root)
    output = resolver.resolve(str(resolver.materialization_request["model12_output_root_handle"]), "model12_output_root").path
    staged = ProtectedRun(output, root, collection="model12-field-scorer-runs", run_id_prefix="m12field-", run_id=run_id)
    anchors = _load_anchor_file(input_path, root)
    frozen = load_frozen_scoring_state(root, resolver)
    sources, support = load_verified_public_dependencies(root, resolver.public_dependencies["data04_ready_dir"], resolver.public_dependencies["geo05_support_dir"])
    scored = score_anchor_batch(anchors=anchors, support=support, sources=sources, frozen=frozen)
    aggregate = {
        "anchor_count": len(scored),
        "computable_frozen_score_count": sum(item["score_computability_status"] == "MODEL_SCORE_COMPUTABLE" for item in scored),
        "noncomputable_frozen_score_count": sum(item["score_computability_status"] == "MODEL_SCORE_NONCOMPUTABLE" for item in scored),
        "any_support_truncation_anchor_count": sum(item["any_support_truncation"] for item in scored),
        "complete_anchor_accounting": True,
    }
    semantic = {
        "$schema": "model12-michigan-field-scoring-package-v1",
        "package_id": FIELD_PACKAGE_ID,
        "version": PACKAGE_VERSION,
        "state": "ready",
        "contract_authority": _contract_authority(contract),
        "input_schema": {"fields": ["opaque_anchor_id", "latitude", "longitude"], "additional_fields_permitted": False},
        "anchors": scored,
        "aggregate_conformance": aggregate,
        "model_lineage": frozen.lineage,
        "execution_boundary": {
            "seed_source_opened": False,
            "target_required": False,
            "target_body_values_accessed": 0,
            "model_refit_performed": False,
            "model_retuning_performed": False,
            "michigan_feature_selection_performed": False,
            "deployment_performed": False,
        },
        "interpretation_boundary": dict(contract["interpretation_boundary"]),
        "protected_handle_registry_identity": resolver.registry_identity,
    }
    staged.write_stage("field_scoring", semantic)
    staged.finalize(package_id=FIELD_PACKAGE_ID, aggregate=aggregate, expected_stages=("field_scoring",))
    return FieldScoringResult(staged.run_dir, len(scored), int(aggregate["computable_frozen_score_count"]), int(aggregate["noncomputable_frozen_score_count"]), int(aggregate["any_support_truncation_anchor_count"]))


def build_disclosure_safe_field_result(result: FieldScoringResult) -> dict[str, Any]:
    return {
        "completion_state": "MODEL-12 protected local field scoring ready",
        "anchor_count": result.anchor_count,
        "computable_frozen_score_count": result.computable_score_count,
        "noncomputable_frozen_score_count": result.noncomputable_score_count,
        "any_support_truncation_anchor_count": result.support_truncation_count,
        "seed_source_opened": False,
        "target_body_values_accessed": 0,
        "model_refit_performed": False,
        "protected_output_outside_git": True,
        "protected_details_disclosed": False,
    }
