"""Load and apply the exact accepted protected MODEL-11 final scoring state."""

from __future__ import annotations

import copy
from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Any, Mapping

from sprouts_customer_geography.model11.modeling import BASE_TERMS, OPPORTUNITY_TERM
from sprouts_customer_geography.pipe01.canonical import content_digest, file_sha256
from sprouts_customer_geography.pipe01.errors import require

from .contract import verify_repository_authority
from .resolver import ProtectedHandleResolver


DEVELOPMENT_PACKAGE_ID = "MODEL11_WISCONSIN_MULTIVARIATE_DEVELOPMENT_PACKAGE_V1"
FREEZE_PACKAGE_ID = "MODEL11_TARGET_BLIND_FEATURE_FREEZE_PACKAGE_V1"
PREFERRED_CANDIDATE_ID = "challenger_multivariate_elastic_net"


def _load_object(path: Path, code: str) -> dict[str, Any]:
    require(path.is_file(), code, "required protected JSON is absent")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        require(False, code, "required protected JSON is unreadable")
    require(isinstance(value, dict), code, "required protected JSON must be an object")
    return value


def _protected_semantic_hash(package: Mapping[str, Any], stable_field: str) -> tuple[str, str]:
    semantic = copy.deepcopy(dict(package))
    protected_hash = semantic.pop("protected_content_sha256", None)
    stable = semantic.pop(stable_field, None)
    require(isinstance(protected_hash, str) and protected_hash == content_digest(semantic), "MODEL12_MODEL11_PROTECTED_HASH_MISMATCH", "protected MODEL-11 semantic identity differs")
    require(isinstance(stable, str), "MODEL12_MODEL11_STABLE_IDENTITY_MISSING", "protected MODEL-11 stable identity is absent")
    return protected_hash, stable


@dataclass(frozen=True)
class FrozenScoringState:
    model_contract_id: str
    preferred_candidate_id: str
    architecture: str
    terms: tuple[str, ...]
    means: Mapping[str, float]
    scales: Mapping[str, float]
    intercept: float
    coefficients: tuple[float, ...]
    alpha: float
    l1_ratio: float
    target_transformation: str
    inverse_target_transformation: str
    stable_development_identity: str
    stable_feature_freeze_identity: str
    protected_registry_identity: str

    def _standardized(self, features: Mapping[str, Any]) -> tuple[float, ...]:
        values: list[float] = []
        for term in self.terms:
            raw = features.get(term)
            require(isinstance(raw, (int, float)) and not isinstance(raw, bool) and math.isfinite(float(raw)), "MODEL_SCORE_INPUT_NONCOMPUTABLE", "one exact frozen-model input is absent or nonfinite")
            value = (float(raw) - float(self.means[term])) / float(self.scales[term])
            require(math.isfinite(value), "MODEL_SCORE_INPUT_NONCOMPUTABLE", "one standardized frozen-model input is nonfinite")
            values.append(value)
        return tuple(values)

    def score(self, features: Mapping[str, Any]) -> dict[str, float]:
        """Apply fitted state only; no fit, tuning, selection, or recalibration occurs."""

        standardized = self._standardized(features)
        log_prediction = self.intercept + sum(value * coefficient for value, coefficient in zip(standardized, self.coefficients))
        non_opportunity = sum(
            value * coefficient
            for term, value, coefficient in zip(self.terms, standardized, self.coefficients)
            if term != OPPORTUNITY_TERM
        )
        require(math.isfinite(log_prediction) and math.isfinite(non_opportunity), "MODEL_SCORE_NONFINITE", "frozen linear predictor is nonfinite")
        try:
            customer_fit = math.exp(non_opportunity)
            modeled_target = max(0.0, math.expm1(log_prediction))
        except OverflowError:
            require(False, "MODEL_SCORE_NONFINITE", "frozen inverse transform overflowed")
        opportunity = features.get("households_5mi")
        require(isinstance(opportunity, (int, float)) and not isinstance(opportunity, bool) and math.isfinite(float(opportunity)) and float(opportunity) >= 0, "MODEL_SCORE_INPUT_NONCOMPUTABLE", "household opportunity is absent or invalid")
        require(math.isfinite(customer_fit) and customer_fit > 0 and math.isfinite(modeled_target), "MODEL_SCORE_NONFINITE", "frozen score is nonfinite")
        return {
            "household_opportunity": float(opportunity),
            "customer_fit_proxy": float(customer_fit),
            "modeled_target_mass": float(modeled_target),
        }

    @property
    def lineage(self) -> dict[str, Any]:
        return {
            "model_contract_id": self.model_contract_id,
            "preferred_candidate_id": self.preferred_candidate_id,
            "final_feature_order": list(self.terms),
            "target_transformation": self.target_transformation,
            "inverse_target_transformation": self.inverse_target_transformation,
            "stable_development_identity": self.stable_development_identity,
            "stable_feature_freeze_identity": self.stable_feature_freeze_identity,
            "protected_registry_identity": self.protected_registry_identity,
            "fitted_preprocessing_reused": True,
            "fitted_parameters_reused": True,
            "michigan_refit_performed": False,
            "michigan_tuning_performed": False,
            "michigan_feature_selection_performed": False,
            "michigan_recalibration_performed": False,
        }


def load_frozen_scoring_state(repository_root: Path, resolver: ProtectedHandleResolver) -> FrozenScoringState:
    """Verify exact accepted lineage and recover the sole fitted scoring artifact."""

    root = repository_root.resolve()
    model12_contract = verify_repository_authority(root)
    model11_authority = model12_contract["accepted_authority"]["model11"]
    model11_contract = _load_object(root / model11_authority["path"], "MODEL12_MODEL11_CONTRACT_UNRESOLVED")
    request = resolver.materialization_request
    package_path = resolver.resolve(str(request["model11_development_package_handle"]), "model11_development_package").path
    ready_path = resolver.resolve(str(request["model11_development_ready_marker_handle"]), "model11_development_ready_marker").path
    manifest_path = resolver.resolve(str(request["model11_development_manifest_handle"]), "model11_development_manifest").path
    freeze_path = resolver.resolve(str(request["model11_feature_freeze_package_handle"]), "model11_feature_freeze_package").path
    freeze_ready_path = resolver.resolve(str(request["model11_feature_freeze_ready_marker_handle"]), "model11_feature_freeze_ready_marker").path

    package = _load_object(package_path, "MODEL12_MODEL11_DEVELOPMENT_PACKAGE_UNRESOLVED")
    ready = _load_object(ready_path, "MODEL12_MODEL11_DEVELOPMENT_READY_UNRESOLVED")
    manifest = _load_object(manifest_path, "MODEL12_MODEL11_DEVELOPMENT_MANIFEST_UNRESOLVED")
    protected_hash, stable = _protected_semantic_hash(package, "stable_development_identity")
    require(
        package.get("package_id") == DEVELOPMENT_PACKAGE_ID
        and package.get("version") == "1.0.0"
        and package.get("state") == "ready"
        and stable == "model11-development:sha256:" + protected_hash
        and ready.get("package_id") == DEVELOPMENT_PACKAGE_ID
        and ready.get("state") == "ready"
        and ready.get("finalization_state") == "complete"
        and ready.get("protected_content_sha256") == protected_hash
        and ready.get("stable_development_identity") == stable
        and manifest.get("package_id") == DEVELOPMENT_PACKAGE_ID
        and manifest.get("state") == "ready"
        and manifest.get("finalization_state") == "complete"
        and manifest.get("protected_content_sha256") == protected_hash
        and manifest.get("stable_development_identity") == stable
        and manifest.get("package_file_sha256") == file_sha256(package_path),
        "MODEL12_MODEL11_FINAL_STATE_MISMATCH",
        "accepted MODEL-11 development package READY or manifest binding differs",
    )
    authority = package.get("authority", {})
    accounting = package.get("evidence_accounting", {})
    finalization = package.get("finalization", {})
    require(
        authority.get("model11_contract_id") == model11_authority["artifact_id"]
        and authority.get("feature_freeze_ready_verified") is True
        and authority.get("pipe04_ready_verified") is True
        and authority.get("protected_registry_identity") == resolver.upstream_model11_registry_identity
        and accounting.get("eligible_observation_count") == model11_contract["cohort"]["eligible_observation_count"]
        and accounting.get("physical_location_count") == model11_contract["cohort"]["physical_location_count"]
        and accounting.get("impacted_sales_values_accessed") == 0
        and accounting.get("non_wisconsin_target_values_accessed") == 0
        and accounting.get("complete_cohort_accounted") is True
        and finalization.get("nested_physical_location_grouped_tuning") is True
        and finalization.get("household_opportunity_customer_fit_and_modeled_mass_separate") is True
        and finalization.get("market_transport_claimed") is False
        and finalization.get("production_authority_claimed") is False,
        "MODEL12_MODEL11_LINEAGE_MISMATCH",
        "protected MODEL-11 authority accounting or finalization differs",
    )

    freeze = _load_object(freeze_path, "MODEL12_MODEL11_FEATURE_FREEZE_UNRESOLVED")
    freeze_ready = _load_object(freeze_ready_path, "MODEL12_MODEL11_FEATURE_FREEZE_READY_UNRESOLVED")
    freeze_hash, freeze_stable = _protected_semantic_hash(freeze, "stable_feature_freeze_identity")
    require(
        freeze.get("package_id") == FREEZE_PACKAGE_ID
        and freeze.get("state") == "ready"
        and freeze_stable == "model11-feature-freeze:sha256:" + freeze_hash
        and freeze_ready.get("package_id") == FREEZE_PACKAGE_ID
        and freeze_ready.get("state") == "ready"
        and freeze_ready.get("finalization_state") == "complete"
        and freeze_ready.get("target_accessed") is False
        and freeze_ready.get("protected_content_sha256") == freeze_hash
        and freeze_ready.get("package_file_sha256") == file_sha256(freeze_path)
        and freeze.get("evidence_accounting", {}).get("target_values_accessed") == 0
        and freeze.get("feature_preparation", {}).get("target_blind") is True
        and freeze.get("feature_preparation", {}).get("candidate_measure_count") == 13,
        "MODEL12_MODEL11_FEATURE_FREEZE_MISMATCH",
        "accepted MODEL-11 target-blind feature freeze differs",
    )
    require(
        authority.get("feature_freeze_run_id") == freeze.get("freeze_run_id"),
        "MODEL12_MODEL11_FEATURE_FREEZE_MISMATCH",
        "development package does not bind the exact feature freeze",
    )

    selection = package.get("selection", {})
    preferred = package.get("preferred_model_artifact", {})
    fitted_models = package.get("fitted_models", {})
    require(
        selection.get("preferred_candidate_id") == PREFERRED_CANDIDATE_ID
        and selection.get("challenger_selected") is True
        and selection.get("selection_rule_applied_without_post_target_change") is True
        and preferred.get("preferred_candidate_id") == PREFERRED_CANDIDATE_ID
        and preferred.get("model09_retained") is False
        and isinstance(preferred.get("parameters"), Mapping)
        and preferred.get("parameters") == fitted_models.get(PREFERRED_CANDIDATE_ID),
        "MODEL12_MODEL11_PREFERRED_ARTIFACT_MISMATCH",
        "accepted preferred MODEL-11 final artifact differs",
    )
    parameters = dict(preferred["parameters"])
    required_parameter_fields = {"candidate_id", "architecture", "terms", "means", "scales", "intercept", "coefficients", "alpha", "l1_ratio", "estimation_weighting"}
    require(set(parameters) == required_parameter_fields, "MODEL12_MODEL11_PARAMETER_SCHEMA_MISMATCH", "preferred fitted parameter fields differ")
    terms = parameters.get("terms")
    means = parameters.get("means")
    scales = parameters.get("scales")
    coefficients = parameters.get("coefficients")
    eligible = freeze.get("feature_preparation", {}).get("eligible_data03_features")
    expected_terms = list(BASE_TERMS) + list(eligible or [])
    require(
        parameters.get("candidate_id") == PREFERRED_CANDIDATE_ID
        and parameters.get("architecture") == "elastic_net"
        and parameters.get("estimation_weighting") == "inverse physical-location observation count"
        and isinstance(terms, list) and terms == expected_terms and len(terms) == len(set(terms))
        and isinstance(means, Mapping) and set(means) == set(terms)
        and isinstance(scales, Mapping) and set(scales) == set(terms)
        and isinstance(coefficients, list) and len(coefficients) == len(terms)
        and all(isinstance(means[term], (int, float)) and math.isfinite(float(means[term])) for term in terms)
        and all(isinstance(scales[term], (int, float)) and math.isfinite(float(scales[term])) and float(scales[term]) > 0 for term in terms)
        and all(isinstance(value, (int, float)) and math.isfinite(float(value)) for value in coefficients)
        and isinstance(parameters.get("intercept"), (int, float)) and math.isfinite(float(parameters["intercept"]))
        and isinstance(parameters.get("alpha"), (int, float)) and float(parameters["alpha"]) >= 0
        and isinstance(parameters.get("l1_ratio"), (int, float)) and 0 < float(parameters["l1_ratio"]) <= 1,
        "MODEL12_MODEL11_PARAMETER_INVALID",
        "preferred fitted preprocessing parameter or exact feature order is invalid",
    )
    comparison = next((item for item in package.get("candidate_comparison", []) if item.get("candidate_id") == PREFERRED_CANDIDATE_ID), None)
    require(
        isinstance(comparison, Mapping)
        and comparison.get("terms") == terms
        and comparison.get("full_cohort_nested_selected_parameters")
        == {"alpha": parameters["alpha"], "l1_ratio": parameters["l1_ratio"]},
        "MODEL12_MODEL11_PARAMETER_LINEAGE_MISMATCH",
        "preferred final parameters do not match the accepted nested selection",
    )
    require(
        model11_contract["target"]["transformation"] == "log1p"
        and model12_contract["frozen_scoring"]["inverse_target_transformation"] == "max zero expm1",
        "MODEL12_TARGET_TRANSFORM_MISMATCH",
        "accepted target transform or inverse semantics differ",
    )
    return FrozenScoringState(
        model_contract_id=str(authority["model11_contract_id"]),
        preferred_candidate_id=PREFERRED_CANDIDATE_ID,
        architecture="elastic_net",
        terms=tuple(str(term) for term in terms),
        means={str(term): float(means[term]) for term in terms},
        scales={str(term): float(scales[term]) for term in terms},
        intercept=float(parameters["intercept"]),
        coefficients=tuple(float(value) for value in coefficients),
        alpha=float(parameters["alpha"]),
        l1_ratio=float(parameters["l1_ratio"]),
        target_transformation="log1p",
        inverse_target_transformation="max zero expm1",
        stable_development_identity=stable,
        stable_feature_freeze_identity=freeze_stable,
        protected_registry_identity=resolver.upstream_model11_registry_identity,
    )
