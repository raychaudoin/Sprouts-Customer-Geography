"""Ordered protected MODEL-13 benchmark, development, and statewide scoring workflow."""

from __future__ import annotations

import copy
import csv
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import re
import subprocess
import uuid
from typing import Any, Mapping, Sequence

from sprouts_customer_geography.model09.development import _target_rows
from sprouts_customer_geography.model09.features import verify_pipe04_binding
from sprouts_customer_geography.model09.modeling import grouped_metrics
from sprouts_customer_geography.model11.development import load_feature_freeze
from sprouts_customer_geography.model11.features import _pearson
from sprouts_customer_geography.model11.resolver import ProtectedHandleResolver as Model11Resolver
from sprouts_customer_geography.model12.frozen import load_frozen_scoring_state
from sprouts_customer_geography.model12.materialization import validate_feature_package, validate_scoring_package
from sprouts_customer_geography.model12.public import load_verified_public_dependencies, score_anchor_batch
from sprouts_customer_geography.model12.resolver import ProtectedHandleResolver as Model12Resolver
from sprouts_customer_geography.model12.source import validate_identity_package
from sprouts_customer_geography.pipe01.canonical import content_digest, file_sha256, write_json_exclusive
from sprouts_customer_geography.pipe01.commitment import freeze_commitment, new_nonce
from sprouts_customer_geography.pipe01.errors import ConformanceError, require
from sprouts_customer_geography.pipe02.resolver import _is_within
from sprouts_customer_geography.pipe05.binding import BINDING_FILENAME, verify_model12_protected_authority, verify_persisted_binding
from sprouts_customer_geography.pipe05.contract import verify_repository_authority as verify_pipe05_repository_authority
from sprouts_customer_geography.pipe05.resolver import ProtectedHandleResolver as Pipe05Resolver

from .modeling import FittedSuccessorModel, SPATIAL_TERMS, compare_and_refit
from .resolver import ProtectedHandleResolver


CONTRACT_ID = "MODEL13_MICHIGAN_BENCHMARK_POOLED_SUCCESSOR_STATEWIDE_SCORING_CONTRACT_V1"
OUTPUT_CONTRACT_ID = "MODEL13_MICHIGAN_POWER_BI_OUTPUT_CONTRACT_V1"
RUN_PACKAGE_ID = "MODEL13_PROTECTED_EXECUTION_RUN_V1"
STAGE_FILES = {
    "benchmark": "model13_michigan_frozen_benchmark.json",
    "feature_freeze": "model13_combined_target_blind_feature_freeze.json",
    "transition": "model13_michigan_development_role_transition.json",
    "development": "model13_pooled_successor_development.json",
    "statewide": "model13_michigan_statewide_tract_scoring.json",
}
STAGE_PACKAGE_IDS = {
    "benchmark": "MODEL13_MICHIGAN_FROZEN_BENCHMARK_V1",
    "feature_freeze": "MODEL13_COMBINED_TARGET_BLIND_FEATURE_FREEZE_V1",
    "transition": "MODEL13_MICHIGAN_DEVELOPMENT_ROLE_TRANSITION_V1",
    "development": "MODEL13_POOLED_SUCCESSOR_DEVELOPMENT_V1",
    "statewide": "MODEL13_MICHIGAN_STATEWIDE_TRACT_SCORING_V1",
}
ACCEPTED_COMMITS = (
    "ed5796e737c1c39671a081f78644577de00a17b2",
    "951476a2757d9063bd3dd6180fbbc924aec1794f",
    "b3bad006d0db922a7e82114dccf6636f4260119d",
    "f199624d16eb42e3e6c6b4d8eb73b8dcd3109dc8",
    "5b96203ac7849fdd48601dc0129d1bbbe1b91d0e",
    "085ab4f58b40325d6ce2515358363cf9d93d525e",
    "ed4e8196debee378fe49a53e3a4b133afe451eec",
    "124ce185eca23083273dc454ce39f450e7278f1f",
    "04a85783ef3f09c82cb0c38c79c225da888f3eb9",
)


def _load_object(path: Path, code: str) -> dict[str, Any]:
    require(path.is_file(), code, "required MODEL-13 JSON is absent")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ConformanceError(code, "required MODEL-13 JSON is unreadable") from exc
    require(isinstance(value, dict), code, "required MODEL-13 JSON must be an object")
    return value


def verify_repository_authority(repository_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    root = repository_root.resolve()
    contract = _load_object(root / "config/model/model13_michigan_benchmark_pooled_successor_statewide_scoring_contract.json", "MODEL13_CONTRACT_MISSING")
    output = _load_object(root / "config/model/model13_michigan_power_bi_output_contract.json", "MODEL13_OUTPUT_CONTRACT_MISSING")
    semantic = dict(contract)
    protected_hash = semantic.pop("content_sha256", None)
    require(contract.get("artifact_id") == CONTRACT_ID and contract.get("version") == "1.0.0" and contract.get("status") == "FROZEN_BEFORE_MICHIGAN_DEVELOPMENT_CONSUMPTION" and protected_hash == content_digest(semantic), "MODEL13_CONTRACT_MISMATCH", "MODEL-13 frozen contract identity or content differs")
    require(output.get("artifact_id") == OUTPUT_CONTRACT_ID and output.get("version") == "1.0.0" and output.get("protected_local_only") is True and output.get("tract_output", {}).get("row_count") == 3017, "MODEL13_OUTPUT_CONTRACT_MISMATCH", "MODEL-13 presentation contract differs")
    manifests = {
        "MODEL-10": "MODEL-10.wisconsin-successor-cohort-identity-lineage-authority.task.json",
        "PIPE-04": "PIPE-04.model10-wisconsin-development-binding-integration.task.json",
        "MODEL-11": "MODEL-11.multivariate-wisconsin-customer-fit-model-development.task.json",
        "MODEL-12": "MODEL-12.michigan-target-blind-seed-intake-frozen-scoring.task.json",
        "PIPE-05": "PIPE-05.michigan-isolated-sales-outcome-binding.task.json",
        "DATA-03": "DATA-03.wisconsin-multivariate-acs-feature-source-expansion.task.json",
        "DATA-04": "DATA-04.michigan-public-data-parity-foundation.task.json",
        "GEO-05": "GEO-05.michigan-statewide-geography-enablement.task.json",
    }
    for task_id, filename in manifests.items():
        manifest = _load_object(root / "governance/tasks" / filename, "MODEL13_ACCEPTED_PREDECESSOR_MISSING")
        require(manifest.get("task_id") == task_id and manifest.get("state") == "ACCEPTED_CLOSED" and manifest.get("completion_state", {}).get("capability_acceptance") == "ACCEPTED", "MODEL13_ACCEPTED_PREDECESSOR_MISMATCH", "one MODEL-13 predecessor is not accepted")
    for commit in ACCEPTED_COMMITS:
        present = subprocess.run(["git", "cat-file", "-e", commit + "^{commit}"], cwd=root, capture_output=True, text=True)
        require(present.returncode == 0, "MODEL13_ACCEPTED_GIT_LINEAGE_MISSING", "one MODEL-13 accepted commit is absent")
    ancestor = subprocess.run(["git", "merge-base", "--is-ancestor", contract["canonical_main_at_authorization"], "HEAD"], cwd=root, capture_output=True, text=True)
    require(ancestor.returncode == 0, "MODEL13_ACCEPTED_GIT_LINEAGE_MISSING", "MODEL-13 authorization base is not an ancestor of execution HEAD")
    candidate_ids = [item.get("candidate_id") for item in contract.get("candidate_family", [])]
    require(candidate_ids == ["successor_spatial_reference", "successor_model11_termset_elastic_net", "successor_combined_multivariate_ridge", "successor_combined_multivariate_elastic_net"] and contract["selection"]["primary_reference_candidate_id"] == "successor_model11_termset_elastic_net", "MODEL13_FROZEN_SELECTION_RULE_MISMATCH", "MODEL-13 frozen candidate or selection rule differs")
    return contract, output


@dataclass(frozen=True)
class StageResult:
    name: str
    package_path: Path
    ready_path: Path
    protected_content_sha256: str
    stable_identity: str


class ProtectedModel13Run:
    def __init__(self, output_root: Path, repository_root: Path, *, run_id: str | None = None, verification_of: str | None = None):
        self.output_root = output_root.resolve()
        repository = repository_root.resolve()
        require(self.output_root.is_dir() and not _is_within(self.output_root, repository), "MODEL13_PROTECTED_OUTPUT_INVALID", "MODEL-13 output root must exist outside Git")
        self.run_id = run_id or "m13run-" + str(uuid.uuid4())
        require(bool(re.fullmatch(r"m13run-[A-Za-z0-9_-]+", self.run_id)), "MODEL13_RUN_ID_INVALID", "MODEL-13 run identity is invalid")
        runs_root = self.output_root / "model13-runs"
        runs_root.mkdir(exist_ok=True)
        self.run_dir = runs_root / self.run_id
        require(not self.run_dir.exists(), "MODEL13_RUN_IMMUTABLE", "MODEL-13 run already exists")
        self.run_dir.mkdir()
        self.verification_of = verification_of
        self.stages: dict[str, StageResult] = {}
        write_json_exclusive(self.run_dir / "run_state.json", {"run_id": self.run_id, "state": "incomplete", "finalization_state": "not_ready", "verification_of": verification_of})

    def write_stage(self, name: str, semantic: Mapping[str, Any]) -> StageResult:
        require(name in STAGE_FILES and name not in self.stages, "MODEL13_STAGE_INVALID", "MODEL-13 stage is invalid or duplicate")
        directory = self.run_dir / name
        require(not directory.exists(), "MODEL13_STAGE_IMMUTABLE", "MODEL-13 stage already exists")
        directory.mkdir()
        write_json_exclusive(directory / "stage_state.json", {"stage": name, "state": "incomplete", "finalization_state": "not_ready"})
        protected_hash = content_digest(semantic)
        stable = f"model13-{name}:sha256:{protected_hash}"
        package = {**copy.deepcopy(dict(semantic)), "protected_content_sha256": protected_hash, "stable_package_identity": stable}
        package_path = directory / STAGE_FILES[name]
        write_json_exclusive(package_path, package)
        nonce = new_nonce()
        commitment = freeze_commitment(file_sha256(package_path), nonce)
        with (directory / "commitment_nonce.bin").open("xb") as handle:
            handle.write(nonce)
            handle.flush()
            os.fsync(handle.fileno())
        write_json_exclusive(directory / "commitment_evidence.json", {"domain": f"sprouts-customer-geography/model13/{name}-commitment/v1", "commitment_sha256": commitment, "protected_content_disclosed": False, "nonce_disclosed": False})
        write_json_exclusive(directory / "stage_manifest.json", {"stage": name, "package_id": STAGE_PACKAGE_IDS[name], "version": "1.0.0", "state": "ready", "finalization_state": "complete", "protected_content_sha256": protected_hash, "stable_package_identity": stable, "package_file_sha256": file_sha256(package_path)})
        ready_path = directory / "READY.json"
        write_json_exclusive(ready_path, {"stage": name, "package_id": STAGE_PACKAGE_IDS[name], "version": "1.0.0", "state": "ready", "finalization_state": "complete", "protected_content_sha256": protected_hash, "stable_package_identity": stable, "package_file_sha256": file_sha256(package_path), "commitment_sha256": commitment, "ready_marker_written_last": True})
        result = StageResult(name, package_path, ready_path, protected_hash, stable)
        self.stages[name] = result
        return result

    def require_ready(self, name: str) -> StageResult:
        require(name in self.stages and self.stages[name].ready_path.is_file(), "MODEL13_STAGE_NOT_READY", "required MODEL-13 stage is not READY")
        ready = _load_object(self.stages[name].ready_path, "MODEL13_STAGE_READY_UNRESOLVED")
        require(ready.get("state") == "ready" and ready.get("ready_marker_written_last") is True and ready.get("protected_content_sha256") == self.stages[name].protected_content_sha256, "MODEL13_STAGE_READY_MISMATCH", "MODEL-13 stage READY differs")
        return self.stages[name]

    def finalize(self, aggregate: Mapping[str, Any]) -> None:
        require(tuple(self.stages) == ("benchmark", "feature_freeze", "transition", "development", "statewide"), "MODEL13_STAGE_SEQUENCE_INVALID", "MODEL-13 stages did not complete in required order")
        write_json_exclusive(self.run_dir / "run_manifest.json", {"run_id": self.run_id, "package_id": RUN_PACKAGE_ID, "version": "1.0.0", "state": "ready", "finalization_state": "complete", "stages": {name: {"package_id": STAGE_PACKAGE_IDS[name], "protected_content_sha256": stage.protected_content_sha256, "stable_package_identity": stage.stable_identity} for name, stage in self.stages.items()}, "aggregate": dict(aggregate), "verification_of": self.verification_of})
        write_json_exclusive(self.run_dir / "READY.json", {"run_id": self.run_id, "package_id": RUN_PACKAGE_ID, "version": "1.0.0", "state": "ready", "finalization_state": "complete", "stage_order": list(self.stages), "aggregate": dict(aggregate), "ready_marker_written_last": True})


def _upstream_resolvers(root: Path, resolver: ProtectedHandleResolver) -> tuple[Model11Resolver, Model12Resolver, Pipe05Resolver, Path]:
    request = resolver.execution_request
    model11_path = resolver.resolve(str(request["model11_registry_handle"]), "model11_registry").path
    model12_path = resolver.resolve(str(request["model12_registry_handle"]), "model12_registry").path
    pipe05_path = resolver.resolve(str(request["pipe05_registry_handle"]), "pipe05_registry").path
    pipe05_run = resolver.resolve(str(request["pipe05_ready_run_handle"]), "pipe05_ready_run").path
    model11 = Model11Resolver.load(model11_path, root)
    model12 = Model12Resolver.load(model12_path, root)
    pipe05 = Pipe05Resolver.load(pipe05_path, root)
    require(model12.upstream_model11_registry_identity == model11.registry_identity, "MODEL13_MODEL11_REGISTRY_LINEAGE_MISMATCH", "MODEL-12 does not bind the exact accepted MODEL-11 registry")
    return model11, model12, pipe05, pipe05_run


def _accepted_model12_packages(root: Path, pipe05: Pipe05Resolver) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    pipe05_contract = verify_pipe05_repository_authority(root)
    identity, authority = verify_model12_protected_authority(repository_root=root, resolver=pipe05, contract=pipe05_contract)
    primary = pipe05.materialization_authorities[0]["stages"]
    feature_path = pipe05.resolve(str(primary["public_features"]["package_handle"]), "model12_public_features_package").path
    scoring_path = pipe05.resolve(str(primary["frozen_scoring"]["package_handle"]), "model12_frozen_scoring_package").path
    features = _load_object(feature_path, "MODEL13_MODEL12_FEATURE_PACKAGE_UNRESOLVED")
    scoring = _load_object(scoring_path, "MODEL13_MODEL12_SCORING_PACKAGE_UNRESOLVED")
    validate_identity_package(identity)
    validate_feature_package(features)
    validate_scoring_package(scoring)
    require(features.get("identity_package_id") == identity.get("package_id") and scoring.get("identity_package_id") == identity.get("package_id"), "MODEL13_MODEL12_PACKAGE_LINEAGE_MISMATCH", "accepted MODEL-12 package lineage differs")
    return identity, features, scoring, authority


def _benchmark_package(root: Path, pipe05: Pipe05Resolver, pipe05_run: Path, contract: Mapping[str, Any], *, verification_of: str | None) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    verification = verify_persisted_binding(repository_root=root, resolver=pipe05, run_dir=pipe05_run)
    require(verification.get("state") == "MATCH" and verification.get("valid_isolated_sales_binding_count") == 138 and verification.get("missing_isolated_sales_count") == 0 and verification.get("invalid_isolated_sales_count") == 0, "MODEL13_PIPE05_BINDING_VERIFICATION_FAILED", "accepted PIPE-05 binding did not reconcile")
    identity, features, scoring, authority = _accepted_model12_packages(root, pipe05)
    binding = _load_object(pipe05_run / BINDING_FILENAME, "MODEL13_PIPE05_BINDING_UNRESOLVED")
    physical_scores = {str(row["physical_location_id"]): row for row in scoring["physical_locations"]}
    feature_locations = {str(row["physical_location_id"]): row for row in features["physical_locations"]}
    groups: dict[str, dict[str, Any]] = {}
    for row in binding["source_observation_accounting"]:
        if row.get("target_binding_eligible") is not True:
            continue
        require(row.get("target_status") == "VALID" and row.get("isolated_sales") is not None, "MODEL13_BENCHMARK_TARGET_INVALID", "one benchmark-eligible PIPE-05 target is invalid")
        physical_id = str(row["physical_location_id"])
        score = physical_scores[physical_id]
        if score["score_computability_status"] != "MODEL_SCORE_COMPUTABLE":
            continue
        state = groups.setdefault(physical_id, {"actual": [], "prediction": [], "support_truncation": bool(score["any_support_truncation"])})
        state["actual"].append(float(row["isolated_sales"]))
        state["prediction"].append(float(score["modeled_target_mass"]))
    pairs: list[dict[str, Any]] = []
    metric_rows: list[dict[str, Any]] = []
    predicted: list[float] = []
    for physical_id in sorted(groups):
        state = groups[physical_id]
        require(max(state["prediction"]) - min(state["prediction"]) <= float(contract["frozen_michigan_benchmark"]["prediction_repeat_tolerance"]), "MODEL13_FROZEN_PREDICTION_REPEAT_MISMATCH", "repeated frozen predictions differ within a physical location")
        actual_mean = sum(state["actual"]) / len(state["actual"])
        prediction_mean = sum(state["prediction"]) / len(state["prediction"])
        pairs.append({"physical_location_id": physical_id, "mean_actual_level": actual_mean, "mean_frozen_prediction": prediction_mean, "observation_count": len(state["actual"]), "support_truncation": state["support_truncation"]})
        metric_rows.append({"successor_physical_location_id": physical_id, "isolated_sales": actual_mean})
        predicted.append(prediction_mean)
    expected = contract["frozen_michigan_benchmark"]
    aggregate = scoring["aggregate_conformance"]
    require(aggregate["physical_location_count"] == expected["expected_model12_physical_location_count"] and aggregate["quarantined_physical_location_count"] == expected["expected_model12_quarantine_count"] and aggregate["computable_frozen_score_physical_location_count"] == expected["expected_model12_computable_count"] and aggregate["noncomputable_frozen_score_physical_location_count"] == expected["expected_model12_noncomputable_count"] and len(pairs) == aggregate["computable_frozen_score_physical_location_count"], "MODEL13_BENCHMARK_PAIR_COUNT_MISMATCH", "clean benchmark pair count does not reconcile to protected lineage")
    metrics = grouped_metrics(metric_rows, predicted)
    stratification: dict[str, Any] = {}
    for flag in (False, True):
        selected = [(row, value, pair) for row, value, pair in zip(metric_rows, predicted, pairs) if pair["support_truncation"] is flag]
        stratification["support_truncated" if flag else "support_complete"] = {"physical_location_count": len(selected), "metrics": grouped_metrics([row for row, _, _ in selected], [value for _, value, _ in selected]) if len(selected) >= 2 else None}
    package = {
        "$schema": "model13-michigan-frozen-benchmark-package-v1",
        "package_id": "MODEL13_MICHIGAN_FROZEN_BENCHMARK_V1",
        "version": "1.0.0",
        "state": "ready",
        "authority": {"model13_contract_id": CONTRACT_ID, "model12_authority_verified": True, "pipe05_binding_verified": True, "model12_materialization_pair_verified": True},
        "chronology": {"evidence_role": "CLEAN_PRE_MICHIGAN_BENCHMARK" if verification_of is None else "DETERMINISTIC_VERIFICATION_OF_CLEAN_PRE_MICHIGAN_BENCHMARK", "michigan_development_consumed_before_benchmark": False, "benchmark_ready_before_development": True, "verification_of": verification_of},
        "pair_accounting": {"physical_location_count": len(pairs), "independence_unit": "unique accepted MODEL-12 physical location", "actual_reduction": "mean level", "prediction_reduction": "mean immutable prediction", "complete_eligible_pair_accounting": True},
        "aggregate_metrics": metrics,
        "support_stratification": stratification,
        "pairs": pairs,
        "execution_boundary": {"identity_changed": False, "cohort_changed": False, "frozen_model_changed": False, "features_changed": False, "coefficients_changed": False, "predictions_changed": False, "radii_changed": False, "missingness_changed": False, "support_treatment_changed": False, "grouping_changed": False, "metrics_changed": False, "exclusions_changed": False, "pass_fail_threshold_created": False, "impacted_sales_values_accessed": 0},
        "finalization": {"immutable_package": True, "incomplete_first": True, "ready_marker_written_last": True},
    }
    require(set(feature_locations) == set(physical_scores), "MODEL13_MODEL12_LOCATION_ACCOUNTING_MISMATCH", "MODEL-12 feature and scoring locations differ")
    return package, identity, features, scoring, binding


def _transformed_profile(profile: Mapping[str, Any], transform: str) -> float | None:
    value = profile.get("value")
    if profile.get("status") != "valid" or not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(float(value)) or float(value) < 0:
        return None
    return math.log1p(float(value)) if transform == "log1p" else float(value)


def _feature_freeze_package(root: Path, model11: Model11Resolver, model12: Model12Resolver, identity: Mapping[str, Any], michigan_features: Mapping[str, Any], contract: Mapping[str, Any]) -> tuple[dict[str, Any], Any]:
    model11_contract = _load_object(root / "config/model/model11_wisconsin_multivariate_model_contract.json", "MODEL13_MODEL11_CONTRACT_UNRESOLVED")
    model11_output = model11.resolve(str(model11.development_request["model11_output_root_handle"]), "model11_output_root").path
    freeze_path = model12.resolve(str(model12.materialization_request["model11_feature_freeze_package_handle"]), "model11_feature_freeze_package").path
    freeze_raw = _load_object(freeze_path, "MODEL13_MODEL11_FEATURE_FREEZE_UNRESOLVED")
    wisconsin_freeze = load_feature_freeze(model11_output, str(freeze_raw["freeze_run_id"]), model11_contract)
    frozen_model11 = load_frozen_scoring_state(root, model12)
    specs = {str(item["measure_id"]): item for item in model11_contract["candidate_measures"]}
    group_vectors: dict[str, dict[str, Any]] = {}
    observations: list[dict[str, Any]] = []
    for source in wisconsin_freeze["observations"]:
        original_group = str(source["successor_physical_location_id"])
        group = "WI:" + original_group
        vector = group_vectors.get(group)
        if vector is None:
            features = dict(source["features"])
            profiles = source["data03_feature_profiles"]
            for measure, spec in specs.items():
                features[measure] = _transformed_profile(profiles[measure], str(spec["transform"]))
            vector = {"state": "WI", "original_physical_location_id": original_group, "features": features, "profiles": profiles}
            group_vectors[group] = vector
        observations.append({"analytical_observation_id": "WI:" + str(source["source_observation_id"]), "source_observation_id": source["source_observation_id"], "state": "WI", "successor_physical_location_id": group, "original_physical_location_id": original_group, "features": vector["features"]})
    michigan_physical = {str(item["physical_location_id"]): item for item in michigan_features["physical_locations"] if item["quarantined"] is False}
    for physical_id, source in michigan_physical.items():
        features = dict(source["public_features"])
        group_vectors["MI:" + physical_id] = {"state": "MI", "original_physical_location_id": physical_id, "features": features, "profiles": source["data03_feature_profiles"], "coordinate": source["canonical_target_blind_coordinate"], "support_truncation": source["any_support_truncation"]}
    for source in michigan_features["source_observations"]:
        physical_id = str(source["physical_location_id"])
        if physical_id not in michigan_physical:
            continue
        vector = group_vectors["MI:" + physical_id]
        observations.append({"analytical_observation_id": "MI:" + str(source["source_observation_id"]), "source_observation_id": source["source_observation_id"], "state": "MI", "successor_physical_location_id": "MI:" + physical_id, "original_physical_location_id": physical_id, "features": vector["features"]})
    require(len(observations) == 201 and len(group_vectors) == 126 and sum(item["state"] == "WI" for item in observations) == 63 and sum(item["state"] == "MI" for item in observations) == 138, "MODEL13_COMBINED_COHORT_ACCOUNTING_FAILED", "target-blind combined cohort does not reconcile")
    measure_ids = [str(item["measure_id"]) for item in model11_contract["candidate_measures"]]
    exclusions: dict[str, str] = {}
    variable: list[str] = []
    for measure in measure_ids:
        values = [vector["features"].get(measure) for vector in group_vectors.values()]
        if not all(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value)) for value in values):
            exclusions[measure] = "incomplete_combined_cohort_public_evidence"
        elif max(float(value) for value in values) - min(float(value) for value in values) <= 1e-12:
            exclusions[measure] = "constant_across_combined_physical_locations"
        else:
            variable.append(measure)
    priority = list(contract["target_blind_feature_freeze"]["redundancy"]["priority_order"])
    threshold = float(contract["target_blind_feature_freeze"]["redundancy"]["threshold"])
    groups = sorted(group_vectors)
    retained: list[str] = []
    correlations: list[dict[str, Any]] = []
    for measure in priority:
        if measure not in variable:
            continue
        rejected: str | None = None
        for prior in retained:
            correlation = _pearson([float(group_vectors[group]["features"][prior]) for group in groups], [float(group_vectors[group]["features"][measure]) for group in groups])
            correlations.append({"left": prior, "right": measure, "pearson": correlation})
            if abs(correlation) >= threshold:
                rejected = prior
                break
        if rejected is None:
            retained.append(measure)
        else:
            exclusions[measure] = "redundant_with:" + rejected
    selected_model11_data03 = [term for term, coefficient in zip(frozen_model11.terms, frozen_model11.coefficients) if term not in SPATIAL_TERMS and abs(coefficient) > 1e-8]
    require(selected_model11_data03 and set(selected_model11_data03) <= set(retained), "MODEL13_MODEL11_REFERENCE_TERM_INELIGIBLE", "accepted MODEL-11 nonzero reference term is not complete in the combined cohort")
    frozen_observations: list[dict[str, Any]] = []
    required_features = ["households_5mi", *SPATIAL_TERMS, *retained]
    required_features = list(dict.fromkeys(required_features))
    for observation in sorted(observations, key=lambda row: str(row["analytical_observation_id"])):
        features = {term: observation["features"][term] for term in required_features}
        require(all(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value)) for value in features.values()), "MODEL13_FROZEN_FEATURE_NONCOMPUTABLE", "one retained combined feature is noncomputable")
        frozen_observations.append({**{key: observation[key] for key in ("analytical_observation_id", "source_observation_id", "state", "successor_physical_location_id", "original_physical_location_id")}, "features": features})
    package = {
        "$schema": "model13-combined-target-blind-feature-freeze-package-v1",
        "package_id": "MODEL13_COMBINED_TARGET_BLIND_FEATURE_FREEZE_V1",
        "version": "1.0.0",
        "state": "ready",
        "authority": {"model13_contract_id": CONTRACT_ID, "model11_feature_freeze_verified": True, "model12_identity_verified": True, "model12_public_features_verified": True, "data03_data04_geo05_reused": True},
        "evidence_accounting": {"observation_count": len(frozen_observations), "physical_location_count": len(group_vectors), "wisconsin_observation_count": 63, "wisconsin_physical_location_count": 41, "michigan_observation_count": 138, "michigan_physical_location_count": 85, "target_values_accessed": 0, "complete_cohort_accounted": True},
        "feature_preparation": {"target_blind": True, "candidate_measure_count": len(measure_ids), "eligible_combined_features": retained, "excluded_combined_features": exclusions, "pairwise_collinearity": correlations, "maximum_absolute_pairwise_correlation": max((abs(float(item["pearson"])) for item in correlations), default=0.0), "spatial_terms": list(SPATIAL_TERMS), "imputation": False, "row_dropping": False},
        "model11_reference_term_authority": {"accepted_preferred_candidate_id": frozen_model11.preferred_candidate_id, "reference_data03_terms": selected_model11_data03, "reference_terms": [*SPATIAL_TERMS, *selected_model11_data03], "nonzero_threshold": 1e-8},
        "observations": frozen_observations,
        "finalization": {"combined_targets_supplied_to_fitting_code": False, "target_correlation_screening": False, "market_state_or_vintage_predictor_created": False, "protected_characteristic_feature_created": False, "ready_marker_written_last": True},
    }
    return package, frozen_model11


def _development_rows(freeze: Mapping[str, Any], model11: Model11Resolver, pipe05_binding: Mapping[str, Any]) -> list[dict[str, Any]]:
    pipe04_path = model11.resolve(str(model11.development_request["pipe04_binding_handle"]), "pipe04_binding").path
    pipe04_ready = model11.resolve(str(model11.development_request["pipe04_ready_marker_handle"]), "pipe04_ready_marker").path
    pipe04 = verify_pipe04_binding(pipe04_path, pipe04_ready)
    wisconsin_targets = _target_rows(pipe04)
    michigan_targets: dict[str, float] = {}
    for row in pipe05_binding["source_observation_accounting"]:
        if row.get("target_binding_eligible") is not True:
            continue
        require(row.get("target_status") == "VALID" and row.get("isolated_sales") is not None, "MODEL13_MICHIGAN_TARGET_INVALID", "one pooled Michigan target is invalid")
        michigan_targets[str(row["source_observation_id"])] = float(row["isolated_sales"])
    require(len(wisconsin_targets) == 63 and len(michigan_targets) == 138, "MODEL13_TARGET_ACCOUNTING_FAILED", "pooled target counts differ")
    rows: list[dict[str, Any]] = []
    for frozen in freeze["observations"]:
        targets = wisconsin_targets if frozen["state"] == "WI" else michigan_targets
        source_id = str(frozen["source_observation_id"])
        require(source_id in targets, "MODEL13_TARGET_JOIN_FAILED", "one combined observation lacks its exact Isolated Sales target")
        rows.append({**copy.deepcopy(dict(frozen)), "isolated_sales": targets[source_id]})
    require(len(rows) == 201 and len({str(row["successor_physical_location_id"]) for row in rows}) == 126, "MODEL13_POOLED_DEVELOPMENT_ACCOUNTING_FAILED", "pooled development cohort differs")
    return rows


def _development_package(rows: list[dict[str, Any]], freeze: Mapping[str, Any], contract: Mapping[str, Any]) -> tuple[dict[str, Any], FittedSuccessorModel]:
    eligible = list(freeze["feature_preparation"]["eligible_combined_features"])
    reference_terms = list(freeze["model11_reference_term_authority"]["reference_terms"])
    all_terms = [*SPATIAL_TERMS, *eligible]
    terms_by_candidate = {
        "successor_spatial_reference": list(SPATIAL_TERMS),
        "successor_model11_termset_elastic_net": reference_terms,
        "successor_combined_multivariate_ridge": all_terms,
        "successor_combined_multivariate_elastic_net": all_terms,
    }
    comparison = compare_and_refit(rows, contract["candidate_family"], terms_by_candidate, outer_count=5, inner_count=4)
    selected_id = str(comparison.selection["selected_candidate_id"])
    model_identity = "model13-successor:sha256:" + content_digest(comparison.final_model.protected_parameters())
    protected_rows: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        final_scores = comparison.final_model.score_features(row["features"])
        oof = {candidate_id: values[index] for candidate_id, values in comparison.oof_predictions.items()}
        protected_rows.append({**copy.deepcopy(row), "candidate_oof_predictions": oof, "selected_oof_prediction": oof[selected_id], "selected_oof_absolute_log_error": abs(math.log1p(float(row["isolated_sales"])) - math.log1p(max(0.0, oof[selected_id]))), "final_refit_prediction": final_scores["modeled_target_mass"], "final_refit_residual": float(row["isolated_sales"]) - final_scores["modeled_target_mass"], **final_scores})
    package = {
        "$schema": "model13-pooled-successor-development-package-v1",
        "package_id": "MODEL13_POOLED_SUCCESSOR_DEVELOPMENT_V1",
        "version": "1.0.0",
        "state": "ready",
        "authority": {"model13_contract_id": CONTRACT_ID, "feature_freeze_identity": freeze["stable_package_identity"], "selection_rule_frozen_before_targets": True},
        "chronology": {"benchmark_ready_before_michigan_development": True, "feature_freeze_ready_before_targets": True, "development_role_transition_ready_before_first_fit": True, "michigan_evidence_role": "POOLED_DEVELOPMENT_NOT_PERMANENT_HOLDOUT"},
        "evidence_accounting": {"observation_count": 201, "physical_location_count": 126, "wisconsin_observation_count": 63, "wisconsin_physical_location_count": 41, "michigan_observation_count": 138, "michigan_physical_location_count": 85, "isolated_sales_values_accessed": 201, "impacted_sales_values_accessed": 0, "other_outcome_values_accessed": 0, "complete_cohort_accounted": True},
        "candidate_comparison": list(comparison.diagnostics),
        "selection": dict(comparison.selection),
        "final_refit": {"model_identity": model_identity, "selected_candidate_id": selected_id, "selected_parameters": comparison.final_model.protected_parameters(), "full_cohort_selected_hyperparameters": dict(comparison.final_parameters), "selected_candidate_refit_count_after_selection": 1, "post_selection_search_performed": False},
        "observations": protected_rows,
        "execution_boundary": {"row_level_folding_used": False, "state_market_or_vintage_predictor_used": False, "target_correlation_feature_screening_used": False, "black_box_model_used": False, "imputation_used": False, "observation_dropped": False, "household_opportunity_customer_fit_and_modeled_target_mass_separate": True, "impacted_sales_values_accessed": 0},
        "finalization": {"bounded_candidate_count": 4, "state_balanced_grouped_outer_validation": True, "state_balanced_grouped_inner_tuning": True, "final_refit_once": True, "ready_marker_written_last": True},
    }
    return package, comparison.final_model


class _ScoringAdapter:
    def __init__(self, model: FittedSuccessorModel, lineage: Mapping[str, Any]):
        self.model = model
        self.terms = model.terms
        self.lineage = dict(lineage)

    def score(self, features: Mapping[str, Any]) -> dict[str, float]:
        return self.model.score_features(features)


def _rank_values(rows: list[dict[str, Any]], field: str, rank_field: str, percentile_field: str) -> None:
    computable = [row for row in rows if isinstance(row.get(field), (int, float)) and not isinstance(row.get(field), bool)]
    computable_row_ids = {id(row) for row in computable}
    values = sorted(float(row[field]) for row in computable)
    denominator = max(1, len(values) - 1)
    first_rank: dict[float, int] = {}
    for index, value in enumerate(sorted(set(values), reverse=True), start=1):
        first_rank[value] = 1 + sum(candidate > value for candidate in values)
    for row in rows:
        if id(row) not in computable_row_ids:
            row[rank_field] = None
            row[percentile_field] = None
            continue
        value = float(row[field])
        row[rank_field] = first_rank[value]
        row[percentile_field] = 100.0 * sum(candidate < value for candidate in values) / denominator


def _write_csv_exclusive(path: Path, columns: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> None:
    with path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(columns), lineterminator="\n", extrasaction="raise")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column) for column in columns})
        handle.flush()
        os.fsync(handle.fileno())


def _statewide_package(run: ProtectedModel13Run, root: Path, model12: Model12Resolver, model: FittedSuccessorModel, development: Mapping[str, Any], benchmark: Mapping[str, Any], michigan_features: Mapping[str, Any], output_contract: Mapping[str, Any]) -> dict[str, Any]:
    sources, support = load_verified_public_dependencies(root, model12.public_dependencies["data04_ready_dir"], model12.public_dependencies["geo05_support_dir"])
    model_identity = str(development["final_refit"]["model_identity"])
    public_identity = "model13-public-lineage:sha256:" + content_digest({"sources": sources.lineage, "spatial_spec": support.authority.specification["content_sha256"]})
    adapter = _ScoringAdapter(model, {"model13_contract_id": CONTRACT_ID, "selected_candidate_id": model.candidate_id, "model_identity": model_identity, "target_transformation": "log1p", "inverse_target_transformation": "max zero expm1"})
    anchors = [{"opaque_anchor_id": tract.geoid, "latitude": tract.latitude, "longitude": tract.longitude} for tract in support.tracts]
    scored = score_anchor_batch(anchors=anchors, support=support, sources=sources, frozen=adapter)
    by_geoid = {str(row["opaque_anchor_id"]): row for row in scored}
    require(len(scored) == len(by_geoid) == 3017 and set(by_geoid) == set(sources.ordered_geoids), "MODEL13_STATEWIDE_TRACT_ACCOUNTING_FAILED", "statewide scoring does not account for all accepted tracts")
    tract_rows: list[dict[str, Any]] = []
    protected_tracts: list[dict[str, Any]] = []
    for tract in support.tracts:
        result = by_geoid[tract.geoid]
        completeness = {round(float(item["radius_m"]), 3): item for item in result.get("support_completeness") or []}
        member_counts = result.get("member_counts") or {}
        qa = "OK" if result["score_computability_status"] == "MODEL_SCORE_COMPUTABLE" else "|".join(result.get("noncomputability_reasons") or ["MODEL_SCORE_NONCOMPUTABLE"])
        row = {
            "geoid": tract.geoid,
            "internal_point_latitude": tract.latitude,
            "internal_point_longitude": tract.longitude,
            "computability_status": result["score_computability_status"],
            "household_opportunity": result.get("household_opportunity"),
            "customer_fit_proxy": result.get("customer_fit_proxy"),
            "modeled_target_mass": result.get("modeled_target_mass"),
            "tract_member_count_3mi": member_counts.get("3mi"),
            "tract_member_count_5mi": member_counts.get("5mi"),
            "tract_member_count_7mi": member_counts.get("7mi"),
            "support_completeness_3mi": completeness.get(4828.032, {}).get("support_completeness_ratio"),
            "support_completeness_5mi": completeness.get(8046.72, {}).get("support_completeness_ratio"),
            "support_completeness_7mi": completeness.get(11265.408, {}).get("support_completeness_ratio"),
            "support_truncation_3mi": completeness.get(4828.032, {}).get("extends_outside_michigan_support"),
            "support_truncation_5mi": completeness.get(8046.72, {}).get("extends_outside_michigan_support"),
            "support_truncation_7mi": completeness.get(11265.408, {}).get("extends_outside_michigan_support"),
            "any_support_truncation": bool(result.get("any_support_truncation")),
            "qa_missingness_status": qa,
            "model_lineage_id": model_identity,
            "public_lineage_id": public_identity,
        }
        tract_rows.append(row)
        protected_tracts.append({**copy.deepcopy(result), "geoid": tract.geoid})
    _rank_values(tract_rows, "customer_fit_proxy", "customer_fit_statewide_rank", "customer_fit_statewide_percentile")
    _rank_values(tract_rows, "modeled_target_mass", "modeled_target_mass_statewide_rank", "modeled_target_mass_statewide_percentile")
    tract_rows.sort(key=lambda row: str(row["geoid"]))
    presentation_dir = run.run_dir / "presentation"
    presentation_dir.mkdir()
    write_json_exclusive(presentation_dir / "presentation_state.json", {"state": "incomplete", "finalization_state": "not_ready"})
    tract_path = presentation_dir / output_contract["tract_output"]["filename"]
    _write_csv_exclusive(tract_path, output_contract["tract_output"]["columns"], tract_rows)
    benchmark_pairs = {str(row["physical_location_id"]): row for row in benchmark["pairs"]}
    selected_id = str(development["selection"]["selected_candidate_id"])
    mi_observations: dict[str, list[Mapping[str, Any]]] = {}
    for row in development["observations"]:
        if row["state"] == "MI":
            mi_observations.setdefault(str(row["original_physical_location_id"]), []).append(row)
    mi_public = {str(row["physical_location_id"]): row for row in michigan_features["physical_locations"] if row["quarantined"] is False}
    seed_rows: list[dict[str, Any]] = []
    for physical_id in sorted(mi_observations):
        rows = mi_observations[physical_id]
        public = mi_public[physical_id]
        score = model.score_features(rows[0]["features"])
        mean_actual = sum(float(row["isolated_sales"]) for row in rows) / len(rows)
        mean_oof = sum(float(row["candidate_oof_predictions"][selected_id]) for row in rows) / len(rows)
        pair = benchmark_pairs.get(physical_id)
        seed_rows.append({
            "protected_physical_location_id": physical_id,
            "latitude": public["canonical_target_blind_coordinate"]["latitude"],
            "longitude": public["canonical_target_blind_coordinate"]["longitude"],
            "mean_isolated_sales": mean_actual,
            "frozen_model12_prediction": None if pair is None else pair["mean_frozen_prediction"],
            "successor_oof_prediction": mean_oof,
            "successor_oof_absolute_log_error": abs(math.log1p(mean_actual) - math.log1p(max(0.0, mean_oof))),
            **score,
            "support_truncation": public["any_support_truncation"],
            "qa_status": public["state"],
            "model_lineage_id": model_identity,
        })
    require(len(seed_rows) == 85, "MODEL13_SEED_CONTEXT_ACCOUNTING_FAILED", "Michigan seed-context rows do not reconcile")
    seed_path = presentation_dir / output_contract["seed_context_output"]["filename"]
    _write_csv_exclusive(seed_path, output_contract["seed_context_output"]["columns"], seed_rows)
    computable = sum(row["computability_status"] == "MODEL_SCORE_COMPUTABLE" for row in tract_rows)
    truncated = sum(bool(row["any_support_truncation"]) for row in tract_rows)
    metadata = {
        "metadata_id": "MODEL13_MICHIGAN_POWER_BI_METADATA_V1",
        "version": "1.0.0",
        "state": "ready",
        "output_contract_id": OUTPUT_CONTRACT_ID,
        "model_lineage_id": model_identity,
        "public_lineage_id": public_identity,
        "tract_output": {"filename": tract_path.name, "row_count": len(tract_rows), "computable_count": computable, "noncomputable_count": len(tract_rows) - computable, "support_truncation_count": truncated, "byte_sha256": file_sha256(tract_path)},
        "seed_context_output": {"filename": seed_path.name, "row_count": len(seed_rows), "byte_sha256": file_sha256(seed_path)},
        "ready_written_last": True,
    }
    metadata_path = presentation_dir / output_contract["metadata_output"]["filename"]
    write_json_exclusive(metadata_path, metadata)
    write_json_exclusive(presentation_dir / "READY.json", {"state": "ready", "finalization_state": "complete", "metadata_file_sha256": file_sha256(metadata_path), "tract_csv_sha256": file_sha256(tract_path), "seed_context_csv_sha256": file_sha256(seed_path), "ready_marker_written_last": True})
    return {
        "$schema": "model13-michigan-statewide-tract-scoring-package-v1",
        "package_id": "MODEL13_MICHIGAN_STATEWIDE_TRACT_SCORING_V1",
        "version": "1.0.0",
        "state": "ready",
        "authority": {"model13_contract_id": CONTRACT_ID, "selected_model_identity": model_identity, "data04_geo05_verified": True, "power_bi_output_contract_id": OUTPUT_CONTRACT_ID},
        "tract_accounting": {"tract_count": len(tract_rows), "computable_count": computable, "noncomputable_count": len(tract_rows) - computable, "support_truncation_count": truncated, "all_3017_accounted": True},
        "tracts": protected_tracts,
        "presentation_outputs": {"tract_csv_filename": tract_path.name, "tract_csv_row_count": len(tract_rows), "seed_context_csv_filename": seed_path.name, "seed_context_row_count": len(seed_rows), "metadata_filename": metadata_path.name, "presentation_ready": True},
        "execution_boundary": {"imputation_performed": False, "tract_dropped": False, "unsupported_demographics_fetched": False, "support_truncation_corrected": False, "impacted_sales_values_accessed": 0, "power_bi_implemented": False},
        "finalization": {"tract_csv_ready": True, "seed_context_csv_ready": True, "metadata_ready": True, "ready_marker_written_last": True},
    }


@dataclass(frozen=True)
class Model13Result:
    run_dir: Path
    benchmark_count: int
    benchmark_metrics: Mapping[str, float]
    retained_feature_count: int
    excluded_feature_count: int
    comparison: tuple[Mapping[str, Any], ...]
    selected_candidate_id: str
    statewide_computable_count: int
    statewide_noncomputable_count: int
    statewide_support_truncation_count: int


def execute_model13(*, repository_root: Path, resolver: ProtectedHandleResolver, run_id: str | None = None, verification_of: str | None = None) -> Model13Result:
    root = repository_root.resolve()
    contract, output_contract = verify_repository_authority(root)
    output_root = resolver.resolve(str(resolver.execution_request["model13_output_root_handle"]), "model13_output_root").path
    run = ProtectedModel13Run(output_root, root, run_id=run_id, verification_of=verification_of)
    model11, model12, pipe05, pipe05_run = _upstream_resolvers(root, resolver)

    benchmark_semantic, identity, michigan_features, _michigan_scoring, pipe05_binding = _benchmark_package(root, pipe05, pipe05_run, contract, verification_of=verification_of)
    run.write_stage("benchmark", benchmark_semantic)
    run.require_ready("benchmark")

    freeze_semantic, _frozen_model11 = _feature_freeze_package(root, model11, model12, identity, michigan_features, contract)
    run.write_stage("feature_freeze", freeze_semantic)
    run.require_ready("feature_freeze")

    transition = {
        "$schema": "model13-michigan-development-role-transition-v1",
        "package_id": "MODEL13_MICHIGAN_DEVELOPMENT_ROLE_TRANSITION_V1",
        "version": "1.0.0",
        "state": "ready",
        "benchmark_identity": run.stages["benchmark"].stable_identity,
        "feature_freeze_identity": run.stages["feature_freeze"].stable_identity,
        "prior_evidence_role": "CLEAN_PRE_MICHIGAN_BENCHMARK",
        "new_evidence_role": "POOLED_WISCONSIN_MICHIGAN_DEVELOPMENT",
        "pipe05_binding_alone_marked_development_consumed": False,
        "first_target_conditioned_operation": "bounded state-balanced grouped successor comparison",
        "michigan_permanent_holdout": False,
        "finalization": {"benchmark_ready_verified": True, "feature_freeze_ready_verified": True, "written_before_first_target_conditioned_fit": True, "ready_marker_written_last": True},
    }
    run.write_stage("transition", transition)
    run.require_ready("transition")

    rows = _development_rows(freeze_semantic, model11, pipe05_binding)
    development_semantic, final_model = _development_package(rows, {**freeze_semantic, "stable_package_identity": run.stages["feature_freeze"].stable_identity}, contract)
    run.write_stage("development", development_semantic)
    run.require_ready("development")

    statewide_semantic = _statewide_package(run, root, model12, final_model, development_semantic, benchmark_semantic, michigan_features, output_contract)
    run.write_stage("statewide", statewide_semantic)
    run.require_ready("statewide")
    aggregate = {"benchmark_physical_location_count": benchmark_semantic["pair_accounting"]["physical_location_count"], "pooled_observation_count": 201, "pooled_physical_location_count": 126, "selected_candidate_id": development_semantic["selection"]["selected_candidate_id"], **statewide_semantic["tract_accounting"], "deterministic_verification_run": verification_of is not None, "impacted_sales_values_accessed": 0}
    run.finalize(aggregate)
    tract = statewide_semantic["tract_accounting"]
    return Model13Result(run.run_dir, int(benchmark_semantic["pair_accounting"]["physical_location_count"]), benchmark_semantic["aggregate_metrics"], len(freeze_semantic["feature_preparation"]["eligible_combined_features"]), len(freeze_semantic["feature_preparation"]["excluded_combined_features"]), tuple(development_semantic["candidate_comparison"]), str(development_semantic["selection"]["selected_candidate_id"]), int(tract["computable_count"]), int(tract["noncomputable_count"]), int(tract["support_truncation_count"]))


def _semantic_package(path: Path) -> Any:
    value = json.loads(path.read_text(encoding="utf-8"))
    def strip(item: Any) -> Any:
        if isinstance(item, dict):
            return {key: strip(value) for key, value in item.items() if key not in {"protected_content_sha256", "stable_package_identity", "verification_of"}}
        if isinstance(item, list):
            return [strip(value) for value in item]
        return item
    return strip(value)


def compare_runs(first: Path, second: Path) -> dict[str, Any]:
    first = first.resolve()
    second = second.resolve()
    require(first != second and first.is_dir() and second.is_dir(), "MODEL13_RERUN_INPUT_INVALID", "two distinct MODEL-13 run directories are required")
    require((first / "READY.json").is_file() and (second / "READY.json").is_file(), "MODEL13_RERUN_NOT_READY", "one MODEL-13 run is not READY")
    matches: dict[str, bool] = {}
    for stage, filename in STAGE_FILES.items():
        matches[stage] = _semantic_package(first / stage / filename) == _semantic_package(second / stage / filename)
    first_presentation = first / "presentation"
    second_presentation = second / "presentation"
    presentation_files = ("model13_michigan_tract_scores.csv", "model13_michigan_seed_context.csv")
    presentation = {name: (first_presentation / name).read_bytes() == (second_presentation / name).read_bytes() for name in presentation_files}
    require(all(matches.values()) and all(presentation.values()), "MODEL13_DETERMINISTIC_RERUN_MISMATCH", "independent MODEL-13 semantic outputs differ")
    return {"state": "MATCH", "semantic_stage_count": len(matches), "semantic_packages_equal": True, "presentation_csvs_byte_identical": True, "tract_count": 3017, "impacted_sales_values_accessed": 0, "protected_details_disclosed": False}


def _rounded_metrics(metrics: Mapping[str, Any]) -> dict[str, Any]:
    return {"spearman": round(float(metrics["spearman"]), 4), "kendall_tau_b": round(float(metrics["kendall_tau_b"]), 4), "log_rmse": round(float(metrics["log_rmse"]), 4), "level_mae": round(float(metrics["level_mae"]), 2)}


def build_disclosure_safe_result(result: Model13Result, rerun: Mapping[str, Any] | None = None) -> dict[str, Any]:
    report = {
        "completion_state": "MODEL-13 protected execution ready",
        "frozen_michigan_benchmark_physical_location_count": result.benchmark_count,
        "frozen_michigan_benchmark_metrics": _rounded_metrics(result.benchmark_metrics),
        "pooled_development_observation_count": 201,
        "pooled_development_physical_location_count": 126,
        "target_blind_retained_feature_count": result.retained_feature_count,
        "target_blind_excluded_feature_count": result.excluded_feature_count,
        "candidate_metrics": [{"candidate_id": item["candidate_id"], "pooled": _rounded_metrics(item["aggregate_oof"]["pooled"]), "michigan": _rounded_metrics(item["aggregate_oof"]["michigan"]), "wisconsin": _rounded_metrics(item["aggregate_oof"]["wisconsin"]), "stability_score": round(float(item["stability"]["stability_score"]), 4), "mean_outer_effective_degrees_of_freedom": round(float(item["mean_outer_effective_degrees_of_freedom"]), 2), "maximum_physical_location_absolute_log_error": round(float(item["maximum_physical_location_absolute_log_error"]), 4)} for item in result.comparison],
        "selected_successor_formulation": result.selected_candidate_id,
        "statewide_tract_count": 3017,
        "statewide_computable_count": result.statewide_computable_count,
        "statewide_noncomputable_count": result.statewide_noncomputable_count,
        "statewide_support_truncation_count": result.statewide_support_truncation_count,
        "all_3017_tracts_accounted": result.statewide_computable_count + result.statewide_noncomputable_count == 3017,
        "power_bi_ready_tract_output_ready": True,
        "power_bi_ready_seed_context_output_ready": True,
        "deterministic_rerun": None if rerun is None else rerun.get("state"),
        "impacted_sales_values_accessed": 0,
        "power_bi_implemented": False,
        "protected_output_outside_git": True,
        "protected_details_disclosed": False,
    }
    serialized = json.dumps(report, sort_keys=True).lower()
    for forbidden in ("physical_location_id", "source_observation", "latitude", "longitude", "coefficient", "intercept", "nonce", "sha256", "protected-handle", "\\", ":\\"):
        require(forbidden not in serialized, "MODEL13_DISCLOSURE_SAFE_REPORT_VIOLATION", "protected MODEL-13 detail entered disclosure-safe report")
    return report
