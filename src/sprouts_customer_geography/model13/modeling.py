"""Bounded state-balanced physical-location-grouped successor modeling."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from sprouts_customer_geography.model09.modeling import _solve, grouped_metrics
from sprouts_customer_geography.pipe01.errors import require


OPPORTUNITY_TERM = "log_households_5mi"
SPATIAL_TERMS = ("log_households_5mi", "inner_household_share_3mi_of_7mi", "log_inner_outer_household_density_gradient")
GROUP_FIELD = "successor_physical_location_id"


def _soft_threshold(value: float, threshold: float) -> float:
    if value > threshold:
        return value - threshold
    if value < -threshold:
        return value + threshold
    return 0.0


def _group_weights(rows: Sequence[Mapping[str, Any]]) -> list[float]:
    counts: dict[str, int] = {}
    for row in rows:
        group = str(row[GROUP_FIELD])
        counts[group] = counts.get(group, 0) + 1
    return [1.0 / counts[str(row[GROUP_FIELD])] for row in rows]


@dataclass(frozen=True)
class FittedSuccessorModel:
    candidate_id: str
    architecture: str
    terms: tuple[str, ...]
    means: Mapping[str, float]
    scales: Mapping[str, float]
    intercept: float
    coefficients: tuple[float, ...]
    alpha: float
    l1_ratio: float

    def standardized(self, features: Mapping[str, Any]) -> list[float]:
        return [(float(features[term]) - self.means[term]) / self.scales[term] for term in self.terms]

    def predict_log_features(self, features: Mapping[str, Any]) -> float:
        return self.intercept + sum(value * coefficient for value, coefficient in zip(self.standardized(features), self.coefficients))

    def predict_features(self, features: Mapping[str, Any]) -> float:
        return max(0.0, math.expm1(self.predict_log_features(features)))

    def predict(self, row: Mapping[str, Any]) -> float:
        return self.predict_features(row["features"])

    def score_features(self, features: Mapping[str, Any]) -> dict[str, float]:
        standardized = self.standardized(features)
        contribution = sum(value * coefficient for term, value, coefficient in zip(self.terms, standardized, self.coefficients) if term != OPPORTUNITY_TERM)
        return {
            "household_opportunity": float(features["households_5mi"]),
            "customer_fit_proxy": math.exp(contribution),
            "modeled_target_mass": self.predict_features(features),
        }

    def effective_degrees_of_freedom(self) -> int:
        return sum(abs(value) > 1e-8 for value in self.coefficients)

    def protected_parameters(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "architecture": self.architecture,
            "terms": list(self.terms),
            "means": dict(self.means),
            "scales": dict(self.scales),
            "intercept": self.intercept,
            "coefficients": list(self.coefficients),
            "alpha": self.alpha,
            "l1_ratio": self.l1_ratio,
            "estimation_weighting": "inverse physical-location observation count",
        }


def fit_regularized(rows: Sequence[Mapping[str, Any]], candidate_id: str, architecture: str, terms: Sequence[str], *, alpha: float, l1_ratio: float = 0.0) -> FittedSuccessorModel:
    rows = list(rows)
    terms = list(terms)
    require(rows and terms and len(terms) == len(set(terms)) and architecture in ("ridge", "elastic_net") and alpha >= 0, "MODEL13_TRAINING_CONFIG_INVALID", "MODEL-13 training configuration is invalid")
    weights = _group_weights(rows)
    total_weight = sum(weights)
    means = {term: sum(weight * float(row["features"][term]) for row, weight in zip(rows, weights)) / total_weight for term in terms}
    scales = {term: math.sqrt(sum(weight * (float(row["features"][term]) - means[term]) ** 2 for row, weight in zip(rows, weights)) / total_weight) for term in terms}
    require(all(math.isfinite(value) and value > 1e-12 for value in scales.values()), "MODEL13_TRAINING_FEATURE_CONSTANT", "one MODEL-13 training feature is constant")
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
        require(0 < l1_ratio <= 1, "MODEL13_TRAINING_CONFIG_INVALID", "MODEL-13 elastic-net l1 ratio is invalid")
        coefficient_values = [0.0] * len(terms)
        fitted = [0.0] * len(rows)
        previous = math.inf
        for _ in range(5000):
            maximum_change = 0.0
            for column in range(len(terms)):
                old = coefficient_values[column]
                residual = [centered[index] - fitted[index] + design[index][column] * old for index in range(len(rows))]
                rho = sum(weights[index] * design[index][column] * residual[index] for index in range(len(rows)))
                norm = sum(weights[index] * design[index][column] ** 2 for index in range(len(rows)))
                new = _soft_threshold(rho, alpha * l1_ratio) / (norm + alpha * (1.0 - l1_ratio))
                delta = new - old
                if delta:
                    for index in range(len(rows)):
                        fitted[index] += design[index][column] * delta
                coefficient_values[column] = new
                maximum_change = max(maximum_change, abs(delta))
            objective = 0.5 * sum(weight * (value - prediction) ** 2 for weight, value, prediction in zip(weights, centered, fitted))
            objective += alpha * (l1_ratio * sum(abs(value) for value in coefficient_values) + 0.5 * (1.0 - l1_ratio) * sum(value**2 for value in coefficient_values))
            require(not math.isfinite(previous) or objective <= previous + 1e-7 * (1.0 + abs(previous)), "MODEL13_ELASTIC_NET_OBJECTIVE_INCREASED", "MODEL-13 elastic-net objective increased")
            if maximum_change < 1e-6 or (math.isfinite(previous) and previous - objective <= 1e-8 * (1.0 + abs(previous))):
                break
            previous = objective
        else:
            require(False, "MODEL13_ELASTIC_NET_DID_NOT_CONVERGE", "MODEL-13 elastic-net did not converge")
        coefficients = tuple(coefficient_values)
    require(all(math.isfinite(value) for value in coefficients), "MODEL13_COEFFICIENT_NONFINITE", "MODEL-13 coefficient is nonfinite")
    return FittedSuccessorModel(candidate_id, architecture, tuple(terms), means, scales, intercept, coefficients, float(alpha), float(l1_ratio))


def state_balanced_grouped_folds(rows: Sequence[Mapping[str, Any]], fold_count: int) -> dict[str, int]:
    require(fold_count >= 2, "MODEL13_FOLD_COUNT_INVALID", "MODEL-13 grouped fold count is invalid")
    states: dict[str, set[str]] = {}
    group_state: dict[str, str] = {}
    for row in rows:
        group = str(row[GROUP_FIELD])
        state = str(row["state"])
        require(group not in group_state or group_state[group] == state, "MODEL13_CROSS_STATE_GROUP_COLLISION", "one analytical group crosses states")
        group_state[group] = state
        states.setdefault(state, set()).add(group)
    assignment: dict[str, int] = {}
    for state in sorted(states):
        ordered = sorted(states[state], key=lambda group: (hashlib.sha256(group.encode("utf-8")).hexdigest(), group))
        require(len(ordered) >= fold_count, "MODEL13_STATE_FOLD_SUPPORT_INSUFFICIENT", "one state lacks physical-location groups for requested folds")
        for index, group in enumerate(ordered):
            assignment[group] = index % fold_count
    require(set(assignment) == set(group_state) and set(assignment.values()) == set(range(fold_count)), "MODEL13_FOLD_ASSIGNMENT_INCOMPLETE", "MODEL-13 state-balanced fold assignment is incomplete")
    return assignment


def _parameter_grid(candidate: Mapping[str, Any]) -> list[dict[str, float]]:
    if "fixed_alpha" in candidate:
        return [{"alpha": float(candidate["fixed_alpha"]), "l1_ratio": 0.0}]
    if candidate["architecture"] == "ridge":
        return [{"alpha": float(alpha), "l1_ratio": 0.0} for alpha in candidate["alpha_grid"]]
    return [{"alpha": float(alpha), "l1_ratio": float(ratio)} for alpha in candidate["alpha_grid"] for ratio in candidate["l1_ratio_grid"]]


def _cv_predictions(rows: Sequence[Mapping[str, Any]], candidate: Mapping[str, Any], terms: Sequence[str], parameters: Mapping[str, float], fold_count: int) -> list[float]:
    rows = list(rows)
    assignment = state_balanced_grouped_folds(rows, fold_count)
    predictions: dict[str, float] = {}
    for fold in range(fold_count):
        train = [row for row in rows if assignment[str(row[GROUP_FIELD])] != fold]
        test = [row for row in rows if assignment[str(row[GROUP_FIELD])] == fold]
        require(not ({str(row[GROUP_FIELD]) for row in train} & {str(row[GROUP_FIELD]) for row in test}), "MODEL13_PHYSICAL_LOCATION_LEAKAGE", "one physical location crossed an inner fold")
        fitted = fit_regularized(train, str(candidate["candidate_id"]), str(candidate["architecture"]), terms, alpha=parameters["alpha"], l1_ratio=parameters["l1_ratio"])
        for row in test:
            predictions[str(row["analytical_observation_id"])] = fitted.predict(row)
    require(len(predictions) == len(rows), "MODEL13_INNER_PREDICTION_INCOMPLETE", "MODEL-13 inner predictions are incomplete")
    return [predictions[str(row["analytical_observation_id"])] for row in rows]


def tune_parameters(rows: Sequence[Mapping[str, Any]], candidate: Mapping[str, Any], terms: Sequence[str], fold_count: int) -> dict[str, float]:
    grid = _parameter_grid(candidate)
    if len(grid) == 1:
        return grid[0]
    scored: list[tuple[float, float, int, dict[str, float]]] = []
    for index, parameters in enumerate(grid):
        predicted = _cv_predictions(rows, candidate, terms, parameters, fold_count)
        metrics = grouped_metrics(list(rows), predicted)
        scored.append((-float(metrics["spearman"]), float(metrics["log_rmse"]), index, parameters))
    scored.sort(key=lambda item: (item[0], item[1], item[2]))
    return scored[0][3]


def _domain_metrics(rows: Sequence[Mapping[str, Any]], predictions: Sequence[float], state: str | None = None) -> dict[str, float]:
    selected = [(row, value) for row, value in zip(rows, predictions) if state is None or str(row["state"]) == state]
    require(selected, "MODEL13_METRIC_DOMAIN_EMPTY", "MODEL-13 metric domain is empty")
    return grouped_metrics([row for row, _ in selected], [value for _, value in selected])


def _stability(models: Sequence[FittedSuccessorModel]) -> dict[str, Any]:
    require(models and all(model.terms == models[0].terms for model in models), "MODEL13_TERM_INSTABILITY", "MODEL-13 fold model terms differ")
    terms = models[0].terms
    selection: dict[str, float] = {}
    signs: dict[str, float] = {}
    deviations: dict[str, float] = {}
    for index, term in enumerate(terms):
        values = [model.coefficients[index] for model in models]
        nonzero = [value for value in values if abs(value) > 1e-8]
        selection[term] = len(nonzero) / len(values)
        if nonzero:
            positive = sum(value > 0 for value in nonzero)
            signs[term] = max(positive, len(nonzero) - positive) / len(nonzero)
        else:
            signs[term] = 0.0
        mean = sum(values) / len(values)
        deviations[term] = math.sqrt(sum((value - mean) ** 2 for value in values) / len(values))
    active = [term for term in terms if selection[term] > 0]
    score = 0.0 if not active else sum((selection[term] + signs[term]) / 2.0 for term in active) / len(active)
    return {"selection_frequency": selection, "coefficient_sign_stability": signs, "coefficient_standard_deviation": deviations, "stability_score": score}


def _maximum_group_error(rows: Sequence[Mapping[str, Any]], predictions: Sequence[float]) -> float:
    grouped: dict[str, tuple[list[float], list[float]]] = {}
    for row, prediction in zip(rows, predictions):
        actual, predicted = grouped.setdefault(str(row[GROUP_FIELD]), ([], []))
        actual.append(float(row["isolated_sales"]))
        predicted.append(float(prediction))
    return max(abs(math.log1p(sum(actual) / len(actual)) - math.log1p(max(0.0, sum(predicted) / len(predicted)))) for actual, predicted in grouped.values())


def _state_holdout(rows: Sequence[Mapping[str, Any]], candidate: Mapping[str, Any], terms: Sequence[str], inner_count: int) -> dict[str, Any]:
    output: dict[str, Any] = {}
    states = sorted({str(row["state"]) for row in rows})
    require(states == ["MI", "WI"], "MODEL13_STATE_SCOPE_INVALID", "MODEL-13 pooled state scope differs")
    for held in states:
        train = [row for row in rows if str(row["state"]) != held]
        test = [row for row in rows if str(row["state"]) == held]
        parameters = tune_parameters(train, candidate, terms, inner_count)
        fitted = fit_regularized(train, str(candidate["candidate_id"]), str(candidate["architecture"]), terms, alpha=parameters["alpha"], l1_ratio=parameters["l1_ratio"])
        output[f"train_{'wisconsin' if held == 'MI' else 'michigan'}_test_{'michigan' if held == 'MI' else 'wisconsin'}"] = {"heldout_state": held, "metrics": grouped_metrics(test, [fitted.predict(row) for row in test]), "diagnostic_only": True}
    return output


@dataclass(frozen=True)
class ComparisonResult:
    diagnostics: tuple[Mapping[str, Any], ...]
    selection: Mapping[str, Any]
    oof_predictions: Mapping[str, tuple[float, ...]]
    final_model: FittedSuccessorModel
    final_parameters: Mapping[str, float]


def compare_and_refit(rows: Sequence[Mapping[str, Any]], candidates: Sequence[Mapping[str, Any]], terms_by_candidate: Mapping[str, Sequence[str]], *, outer_count: int = 5, inner_count: int = 4) -> ComparisonResult:
    rows = list(rows)
    require(len(candidates) == 4 and [str(item["candidate_id"]) for item in candidates] == ["successor_spatial_reference", "successor_model11_termset_elastic_net", "successor_combined_multivariate_ridge", "successor_combined_multivariate_elastic_net"], "MODEL13_CANDIDATE_FAMILY_INVALID", "MODEL-13 candidate family differs")
    assignment = state_balanced_grouped_folds(rows, outer_count)
    diagnostics: list[dict[str, Any]] = []
    oof_by_candidate: dict[str, tuple[float, ...]] = {}
    for candidate in candidates:
        candidate_id = str(candidate["candidate_id"])
        terms = list(terms_by_candidate[candidate_id])
        require(tuple(terms[:3]) == SPATIAL_TERMS and len(terms) == len(set(terms)), "MODEL13_CANDIDATE_TERMS_INVALID", "MODEL-13 candidate term order or uniqueness differs")
        predictions: dict[str, float] = {}
        fold_models: list[FittedSuccessorModel] = []
        selected_parameters: list[dict[str, float]] = []
        fold_domains: dict[str, list[dict[str, float]]] = {"pooled": [], "michigan": [], "wisconsin": []}
        for fold in range(outer_count):
            train = [row for row in rows if assignment[str(row[GROUP_FIELD])] != fold]
            test = [row for row in rows if assignment[str(row[GROUP_FIELD])] == fold]
            parameters = tune_parameters(train, candidate, terms, inner_count)
            model = fit_regularized(train, candidate_id, str(candidate["architecture"]), terms, alpha=parameters["alpha"], l1_ratio=parameters["l1_ratio"])
            predicted = [model.predict(row) for row in test]
            fold_models.append(model)
            selected_parameters.append(dict(parameters))
            fold_domains["pooled"].append(_domain_metrics(test, predicted))
            fold_domains["michigan"].append(_domain_metrics(test, predicted, "MI"))
            fold_domains["wisconsin"].append(_domain_metrics(test, predicted, "WI"))
            for row, value in zip(test, predicted):
                predictions[str(row["analytical_observation_id"])] = value
        require(len(predictions) == len(rows), "MODEL13_OOF_PREDICTION_INCOMPLETE", "MODEL-13 OOF predictions are incomplete")
        ordered = tuple(predictions[str(row["analytical_observation_id"])] for row in rows)
        oof_by_candidate[candidate_id] = ordered
        aggregate = {"pooled": _domain_metrics(rows, ordered), "michigan": _domain_metrics(rows, ordered, "MI"), "wisconsin": _domain_metrics(rows, ordered, "WI")}
        ranges = {domain: {metric: {"minimum": min(fold[metric] for fold in values), "maximum": max(fold[metric] for fold in values)} for metric in ("spearman", "kendall_tau_b", "log_rmse", "level_mae")} for domain, values in fold_domains.items()}
        stability = _stability(fold_models)
        degrees = [model.effective_degrees_of_freedom() for model in fold_models]
        diagnostics.append({
            "candidate_id": candidate_id,
            "architecture": candidate["architecture"],
            "terms": terms,
            "aggregate_oof": aggregate,
            "outer_fold_metric_ranges": ranges,
            "outer_selected_parameters": selected_parameters,
            "stability": stability,
            "mean_outer_effective_degrees_of_freedom": sum(degrees) / len(degrees),
            "outer_effective_degrees_of_freedom_range": [min(degrees), max(degrees)],
            "maximum_physical_location_absolute_log_error": _maximum_group_error(rows, ordered),
            "state_holdout_sensitivity": _state_holdout(rows, candidate, terms, inner_count),
        })
    by_id = {str(item["candidate_id"]): item for item in diagnostics}
    reference_id = "successor_model11_termset_elastic_net"
    reference = by_id[reference_id]
    qualifiers = []
    for item in diagnostics:
        if item["candidate_id"] == reference_id:
            continue
        if (
            item["aggregate_oof"]["pooled"]["spearman"] >= reference["aggregate_oof"]["pooled"]["spearman"]
            and item["aggregate_oof"]["pooled"]["log_rmse"] <= reference["aggregate_oof"]["pooled"]["log_rmse"] * 1.05
            and item["aggregate_oof"]["michigan"]["spearman"] >= reference["aggregate_oof"]["michigan"]["spearman"] - 0.01
        ):
            qualifiers.append(item)
    qualifiers.sort(key=lambda item: (-item["aggregate_oof"]["michigan"]["spearman"], -item["aggregate_oof"]["pooled"]["spearman"], item["aggregate_oof"]["pooled"]["log_rmse"], -item["stability"]["stability_score"], item["mean_outer_effective_degrees_of_freedom"], str(item["candidate_id"])))
    selected_id = str(qualifiers[0]["candidate_id"]) if qualifiers else reference_id
    selection = {"primary_reference_candidate_id": reference_id, "qualifying_challenger_ids": [str(item["candidate_id"]) for item in qualifiers], "selected_candidate_id": selected_id, "challenger_selected": bool(qualifiers), "rule_applied_without_change": True}
    selected_candidate = next(item for item in candidates if item["candidate_id"] == selected_id)
    selected_terms = list(terms_by_candidate[selected_id])
    final_parameters = tune_parameters(rows, selected_candidate, selected_terms, inner_count)
    final_model = fit_regularized(rows, selected_id, str(selected_candidate["architecture"]), selected_terms, alpha=final_parameters["alpha"], l1_ratio=final_parameters["l1_ratio"])
    return ComparisonResult(tuple(diagnostics), selection, oof_by_candidate, final_model, final_parameters)
