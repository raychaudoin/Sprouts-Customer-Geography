"""Bounded nested physical-location-grouped MODEL-11 development."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping

from sprouts_customer_geography.model09.modeling import (
    _market_holdout as model09_market_holdout,
    _oof_predictions as model09_oof_predictions,
    _solve,
    fit_candidate as fit_model09_candidate,
    grouped_folds,
    grouped_metrics,
)
from sprouts_customer_geography.pipe01.errors import require


BASE_TERMS = ("log_households_5mi", "inner_household_share_3mi_of_7mi", "log_inner_outer_household_density_gradient")
OPPORTUNITY_TERM = "log_households_5mi"


def _soft_threshold(value: float, threshold: float) -> float:
    if value > threshold:
        return value - threshold
    if value < -threshold:
        return value + threshold
    return 0.0


def _group_weights(rows: list[Mapping[str, Any]]) -> list[float]:
    counts: dict[str, int] = {}
    for row in rows:
        group = str(row["successor_physical_location_id"])
        counts[group] = counts.get(group, 0) + 1
    return [1.0 / counts[str(row["successor_physical_location_id"])] for row in rows]


@dataclass(frozen=True)
class FittedRegularizedModel:
    candidate_id: str
    architecture: str
    terms: tuple[str, ...]
    means: Mapping[str, float]
    scales: Mapping[str, float]
    intercept: float
    coefficients: tuple[float, ...]
    alpha: float
    l1_ratio: float

    def standardized(self, row: Mapping[str, Any]) -> list[float]:
        return [(float(row["features"][term]) - self.means[term]) / self.scales[term] for term in self.terms]

    def predict_log(self, row: Mapping[str, Any]) -> float:
        return self.intercept + sum(value * coefficient for value, coefficient in zip(self.standardized(row), self.coefficients))

    def predict(self, row: Mapping[str, Any]) -> float:
        return max(0.0, math.expm1(self.predict_log(row)))

    def customer_fit_factor(self, row: Mapping[str, Any]) -> float:
        standardized = self.standardized(row)
        contribution = sum(value * coefficient for term, value, coefficient in zip(self.terms, standardized, self.coefficients) if term != OPPORTUNITY_TERM)
        return math.exp(contribution)

    def effective_degrees_of_freedom(self) -> int:
        return sum(abs(value) > 1e-8 for value in self.coefficients)

    def protected_parameters(self) -> dict[str, Any]:
        return {"candidate_id": self.candidate_id, "architecture": self.architecture, "terms": list(self.terms), "means": dict(self.means), "scales": dict(self.scales), "intercept": self.intercept, "coefficients": list(self.coefficients), "alpha": self.alpha, "l1_ratio": self.l1_ratio, "estimation_weighting": "inverse physical-location observation count"}


def fit_regularized(rows: list[Mapping[str, Any]], candidate_id: str, architecture: str, terms: list[str], *, alpha: float, l1_ratio: float = 0.0) -> FittedRegularizedModel:
    require(rows and terms and architecture in ("ridge", "elastic_net") and alpha >= 0, "MODEL_TRAINING_CONFIG_INVALID", "regularized training configuration is invalid")
    weights = _group_weights(rows)
    total_weight = sum(weights)
    means = {term: sum(weight * float(row["features"][term]) for row, weight in zip(rows, weights)) / total_weight for term in terms}
    scales = {term: math.sqrt(sum(weight * (float(row["features"][term]) - means[term]) ** 2 for row, weight in zip(rows, weights)) / total_weight) for term in terms}
    require(all(math.isfinite(value) and value > 1e-12 for value in scales.values()), "MODEL_FEATURE_CONSTANT", "training feature is constant")
    design = [[(float(row["features"][term]) - means[term]) / scales[term] for term in terms] for row in rows]
    target = [math.log1p(float(row["isolated_sales"])) for row in rows]
    intercept = sum(weight * value for weight, value in zip(weights, target)) / total_weight
    centered = [value - intercept for value in target]
    if architecture == "ridge":
        width = len(terms)
        gram = [[sum(weight * row[left] * row[right] for row, weight in zip(design, weights)) for right in range(width)] for left in range(width)]
        cross = [sum(weight * row[column] * value for row, value, weight in zip(design, centered, weights)) for column in range(width)]
        for index in range(width):
            gram[index][index] += alpha
        coefficients = tuple(_solve(gram, cross))
    else:
        require(0 < l1_ratio <= 1, "MODEL_TRAINING_CONFIG_INVALID", "elastic-net l1 ratio is invalid")
        coefficients_list = [0.0] * len(terms)
        fitted = [0.0] * len(rows)
        previous_objective = math.inf
        for _ in range(5000):
            maximum_change = 0.0
            for column in range(len(terms)):
                old = coefficients_list[column]
                residual = [centered[index] - fitted[index] + design[index][column] * old for index in range(len(rows))]
                rho = sum(weights[index] * design[index][column] * residual[index] for index in range(len(rows)))
                norm = sum(weights[index] * design[index][column] ** 2 for index in range(len(rows)))
                new = _soft_threshold(rho, alpha * l1_ratio) / (norm + alpha * (1.0 - l1_ratio))
                delta = new - old
                if delta:
                    for index in range(len(rows)):
                        fitted[index] += design[index][column] * delta
                coefficients_list[column] = new
                maximum_change = max(maximum_change, abs(delta))
            objective = 0.5 * sum(weight * (value - prediction) ** 2 for weight, value, prediction in zip(weights, centered, fitted))
            objective += alpha * (l1_ratio * sum(abs(value) for value in coefficients_list) + 0.5 * (1.0 - l1_ratio) * sum(value**2 for value in coefficients_list))
            require(objective <= previous_objective + 1e-7 * (1.0 + abs(previous_objective)) if math.isfinite(previous_objective) else True, "ELASTIC_NET_OBJECTIVE_INCREASED", "elastic-net objective increased")
            if maximum_change < 1e-6 or (math.isfinite(previous_objective) and previous_objective - objective <= 1e-8 * (1.0 + abs(previous_objective))):
                break
            previous_objective = objective
        else:
            require(False, "ELASTIC_NET_DID_NOT_CONVERGE", "elastic-net coordinate descent did not converge")
        coefficients = tuple(coefficients_list)
    require(all(math.isfinite(value) for value in coefficients), "MODEL_COEFFICIENT_NONFINITE", "regularized coefficient is nonfinite")
    return FittedRegularizedModel(candidate_id, architecture, tuple(terms), means, scales, intercept, coefficients, alpha, l1_ratio)


def _parameter_grid(candidate: Mapping[str, Any]) -> list[dict[str, float]]:
    if candidate["architecture"] == "ridge":
        return [{"alpha": float(alpha), "l1_ratio": 0.0} for alpha in candidate["alpha_grid"]]
    return [{"alpha": float(alpha), "l1_ratio": float(ratio)} for alpha in candidate["alpha_grid"] for ratio in candidate["l1_ratio_grid"]]


def _fixed_terms(candidate: Mapping[str, Any], eligible_data03: list[str]) -> list[str]:
    terms = list(BASE_TERMS)
    if "eligible_frozen_data03_features" in candidate["terms"]:
        terms.extend(eligible_data03)
    require(len(terms) == len(set(terms)) and not any(term.startswith("market=") or term.startswith("vintage_") for term in terms), "MODEL11_PREDICTOR_SCOPE_VIOLATION", "market vintage or duplicate terms entered MODEL-11")
    return terms


def _cv_predictions(rows: list[Mapping[str, Any]], candidate: Mapping[str, Any], terms: list[str], parameters: Mapping[str, float], fold_count: int) -> list[float]:
    assignment = grouped_folds(rows, min(fold_count, len({str(row["successor_physical_location_id"]) for row in rows})))
    predictions: dict[str, float] = {}
    for fold in sorted(set(assignment.values())):
        train = [row for row in rows if assignment[str(row["successor_physical_location_id"])] != fold]
        test = [row for row in rows if assignment[str(row["successor_physical_location_id"])] == fold]
        require(not ({str(row["successor_physical_location_id"]) for row in train} & {str(row["successor_physical_location_id"]) for row in test}), "PHYSICAL_LOCATION_LEAKAGE", "one physical location crossed a nested fold")
        fitted = fit_regularized(train, str(candidate["candidate_id"]), str(candidate["architecture"]), terms, alpha=parameters["alpha"], l1_ratio=parameters["l1_ratio"])
        for row in test:
            predictions[str(row["source_observation_id"])] = fitted.predict(row)
    require(len(predictions) == len(rows), "NESTED_PREDICTION_INCOMPLETE", "nested predictions do not cover training rows")
    return [predictions[str(row["source_observation_id"])] for row in rows]


def tune_parameters(rows: list[Mapping[str, Any]], candidate: Mapping[str, Any], terms: list[str], inner_fold_count: int) -> dict[str, float]:
    scored: list[tuple[float, float, int, dict[str, float]]] = []
    for index, parameters in enumerate(_parameter_grid(candidate)):
        predicted = _cv_predictions(rows, candidate, terms, parameters, inner_fold_count)
        metric = grouped_metrics(rows, predicted)
        scored.append((-metric["spearman"], metric["log_rmse"], index, parameters))
    scored.sort(key=lambda item: (item[0], item[1], item[2]))
    return scored[0][3]


def _stability(models: list[FittedRegularizedModel]) -> dict[str, Any]:
    terms = models[0].terms
    require(all(model.terms == terms for model in models), "MODEL_TERM_INSTABILITY", "fold model terms differ")
    selection_frequency: dict[str, float] = {}
    sign_stability: dict[str, float] = {}
    coefficient_instability: dict[str, float] = {}
    for index, term in enumerate(terms):
        values = [model.coefficients[index] for model in models]
        nonzero = [value for value in values if abs(value) > 1e-8]
        selection_frequency[term] = len(nonzero) / len(values)
        if nonzero:
            positive = sum(value > 0 for value in nonzero)
            sign_stability[term] = max(positive, len(nonzero) - positive) / len(nonzero)
        else:
            sign_stability[term] = 0.0
        mean = sum(values) / len(values)
        coefficient_instability[term] = math.sqrt(sum((value - mean) ** 2 for value in values) / len(values))
    return {"selection_frequency": selection_frequency, "coefficient_sign_stability": sign_stability, "coefficient_standard_deviation": coefficient_instability}


def _nested_outer(rows: list[Mapping[str, Any]], candidate: Mapping[str, Any], terms: list[str], outer_count: int, inner_count: int) -> tuple[list[float], list[dict[str, float]], list[FittedRegularizedModel], list[dict[str, float]]]:
    assignment = grouped_folds(rows, outer_count)
    predictions: dict[str, float] = {}
    fold_metrics: list[dict[str, float]] = []
    models: list[FittedRegularizedModel] = []
    selected_parameters: list[dict[str, float]] = []
    for fold in range(outer_count):
        train = [row for row in rows if assignment[str(row["successor_physical_location_id"])] != fold]
        test = [row for row in rows if assignment[str(row["successor_physical_location_id"])] == fold]
        parameters = tune_parameters(train, candidate, terms, inner_count)
        fitted = fit_regularized(train, str(candidate["candidate_id"]), str(candidate["architecture"]), terms, alpha=parameters["alpha"], l1_ratio=parameters["l1_ratio"])
        predicted = [fitted.predict(row) for row in test]
        fold_metrics.append(grouped_metrics(test, predicted))
        models.append(fitted)
        selected_parameters.append(dict(parameters))
        for row, value in zip(test, predicted):
            predictions[str(row["source_observation_id"])] = value
    require(len(predictions) == len(rows), "OOF_PREDICTION_INCOMPLETE", "outer predictions do not cover the complete cohort")
    return [predictions[str(row["source_observation_id"])] for row in rows], fold_metrics, models, selected_parameters


def _nested_market_holdout(rows: list[Mapping[str, Any]], candidate: Mapping[str, Any], terms: list[str], inner_count: int) -> dict[str, Any]:
    predictions: dict[str, float] = {}
    evaluated = 0
    for market in sorted({str(row["market"]) for row in rows}):
        test = [row for row in rows if str(row["market"]) == market]
        test_groups = {str(row["successor_physical_location_id"]) for row in test}
        train = [row for row in rows if str(row["successor_physical_location_id"]) not in test_groups]
        require(train and test and not ({str(row["successor_physical_location_id"]) for row in train} & test_groups), "PHYSICAL_LOCATION_LEAKAGE", "one physical location crossed market holdout")
        parameters = tune_parameters(train, candidate, terms, inner_count)
        fitted = fit_regularized(train, str(candidate["candidate_id"]), str(candidate["architecture"]), terms, alpha=parameters["alpha"], l1_ratio=parameters["l1_ratio"])
        evaluated += 1
        for row in test:
            predictions[str(row["source_observation_id"])] = fitted.predict(row)
    require(len(predictions) == len(rows), "MARKET_HOLDOUT_INCOMPLETE", "market holdout does not cover the complete cohort")
    return {"market_count": evaluated, **grouped_metrics(rows, [predictions[str(row["source_observation_id"])] for row in rows])}


def _outer_heldout_group_sensitivity(rows: list[Mapping[str, Any]], predicted: list[float]) -> dict[str, Any]:
    require(len(rows) == len(predicted), "MODEL_SENSITIVITY_INPUT_INVALID", "group sensitivity inputs differ")
    grouped: dict[str, tuple[list[float], list[float]]] = {}
    for row, value in zip(rows, predicted):
        actual_values, predicted_values = grouped.setdefault(str(row["successor_physical_location_id"]), ([], []))
        actual_values.append(float(row["isolated_sales"]))
        predicted_values.append(float(value))
    group_errors: dict[str, float] = {}
    for group, (actual_values, predicted_values) in grouped.items():
        actual_level = sum(actual_values) / len(actual_values)
        predicted_level = sum(predicted_values) / len(predicted_values)
        group_errors[group] = abs(math.log1p(actual_level) - math.log1p(max(0.0, predicted_level)))
    return {"group_count": len(group_errors), "grouped_metrics": grouped_metrics(rows, predicted), "maximum_absolute_log_error": max(group_errors.values()), "per_group_absolute_log_error": group_errors, "semantics": "strict outer-fold held-out error for each physical-location group"}


def _reference_diagnostics(rows: list[Mapping[str, Any]], contract: Mapping[str, Any]) -> tuple[dict[str, Any], Any, list[float]]:
    candidate = {"candidate_id": "model09_spatial_concentration_reference", "terms": list(BASE_TERMS), "ridge_penalty": 0.1}
    assignment = grouped_folds(rows, int(contract["development_diagnostics"]["outer_grouped_fold_count"]))
    all_markets = sorted({str(row["market"]) for row in rows})
    predicted, folds = model09_oof_predictions(rows, candidate, assignment, all_markets)
    fitted = fit_model09_candidate(rows, candidate, all_markets)
    aggregate = grouped_metrics(rows, predicted)
    reference = contract["reference_reproduction"]
    tolerance = float(reference["rounded_metric_tolerance"])
    for metric, key in (("spearman", "grouped_spearman"), ("kendall_tau_b", "grouped_kendall_tau_b"), ("log_rmse", "grouped_log_rmse")):
        require(abs(round(aggregate[metric], 4) - float(reference[key])) <= tolerance, "MODEL09_REFERENCE_REPRODUCTION_FAILED", "locked MODEL-09 aggregate metric was not reproduced")
    diagnostic = {
        "candidate_id": candidate["candidate_id"],
        "complexity_rank": 0,
        "grouped_oof": aggregate,
        "fold_metric_ranges": {name: {"minimum": min(fold[name] for fold in folds), "maximum": max(fold[name] for fold in folds)} for name in aggregate},
        "leave_one_market_out": model09_market_holdout(rows, candidate, all_markets),
        "individual_physical_location_sensitivity": _outer_heldout_group_sensitivity(rows, predicted),
        "effective_degrees_of_freedom": len(BASE_TERMS),
        "reference_reproduced": True,
    }
    return diagnostic, fitted, predicted


@dataclass(frozen=True)
class ComparisonResult:
    comparison: tuple[Mapping[str, Any], ...]
    selection: Mapping[str, Any]
    fitted_models: Mapping[str, Any]
    oof_predictions: Mapping[str, list[float]]


def compare_candidates(rows: list[Mapping[str, Any]], contract: Mapping[str, Any], eligible_data03: list[str]) -> ComparisonResult:
    candidates = contract.get("candidates")
    require(isinstance(candidates, list) and len(candidates) == 3 and [item["candidate_id"] for item in candidates] == ["model09_spatial_concentration_reference", "challenger_multivariate_ridge", "challenger_multivariate_elastic_net"], "BOUNDED_CANDIDATE_CONFIG_INVALID", "MODEL-11 exact three-candidate contract differs")
    reference_diagnostic, reference_fit, reference_oof = _reference_diagnostics(rows, contract)
    comparison: list[dict[str, Any]] = [reference_diagnostic]
    fitted_models: dict[str, Any] = {"model09_spatial_concentration_reference": reference_fit}
    oof: dict[str, list[float]] = {"model09_spatial_concentration_reference": reference_oof}
    outer_count = int(contract["development_diagnostics"]["outer_grouped_fold_count"])
    inner_count = int(contract["development_diagnostics"]["inner_grouped_fold_count"])
    for candidate in candidates[1:]:
        terms = _fixed_terms(candidate, eligible_data03)
        predicted, folds, fold_models, selected_parameters = _nested_outer(rows, candidate, terms, outer_count, inner_count)
        aggregate = grouped_metrics(rows, predicted)
        full_parameters = tune_parameters(rows, candidate, terms, inner_count)
        full_model = fit_regularized(rows, str(candidate["candidate_id"]), str(candidate["architecture"]), terms, alpha=full_parameters["alpha"], l1_ratio=full_parameters["l1_ratio"])
        comparison.append({
            "candidate_id": candidate["candidate_id"],
            "complexity_rank": candidate["complexity_rank"],
            "terms": terms,
            "grouped_oof": aggregate,
            "fold_metric_ranges": {name: {"minimum": min(fold[name] for fold in folds), "maximum": max(fold[name] for fold in folds)} for name in aggregate},
            "nested_outer_selected_parameters": selected_parameters,
            "full_cohort_nested_selected_parameters": full_parameters,
            "effective_degrees_of_freedom": full_model.effective_degrees_of_freedom(),
            "stability": _stability(fold_models),
            "leave_one_market_out": _nested_market_holdout(rows, candidate, terms, inner_count),
            "individual_physical_location_sensitivity": _outer_heldout_group_sensitivity(rows, predicted),
        })
        fitted_models[str(candidate["candidate_id"])] = full_model
        oof[str(candidate["candidate_id"])] = predicted
    reference = comparison[0]
    rule = contract["selection"]
    qualifiers = [item for item in comparison[1:] if item["grouped_oof"]["spearman"] >= reference["grouped_oof"]["spearman"] + float(rule["minimum_spearman_improvement_over_reference"]) and item["grouped_oof"]["log_rmse"] <= reference["grouped_oof"]["log_rmse"] * float(rule["maximum_log_rmse_ratio_to_reference"])]
    qualifiers.sort(key=lambda item: (-item["grouped_oof"]["spearman"], item["grouped_oof"]["log_rmse"], item["effective_degrees_of_freedom"]))
    preferred = qualifiers[0]["candidate_id"] if qualifiers else "model09_spatial_concentration_reference"
    selection = {"reference_candidate_id": "model09_spatial_concentration_reference", "qualifying_challenger_ids": [item["candidate_id"] for item in qualifiers], "preferred_candidate_id": preferred, "challenger_selected": bool(qualifiers), "conclusion": "PREFERRED_MULTIVARIATE_EXPERIMENTAL_FORMULATION_SELECTED" if qualifiers else rule["no_qualifying_challenger"], "selection_rule_applied_without_post_target_change": True}
    return ComparisonResult(tuple(comparison), selection, fitted_models, oof)
