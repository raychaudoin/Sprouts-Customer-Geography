"""Bounded deterministic MODEL-09 candidate fitting and development diagnostics."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from sprouts_customer_geography.pipe01.errors import require


NUMERIC_TERMS = (
    "log_households_5mi",
    "inner_household_share_3mi_of_7mi",
    "log_inner_outer_household_density_gradient",
)
FIT_PROXY_TERMS = frozenset(("inner_household_share_3mi_of_7mi", "log_inner_outer_household_density_gradient"))


def _solve(matrix: list[list[float]], vector: list[float]) -> list[float]:
    size = len(vector)
    augmented = [list(matrix[index]) + [vector[index]] for index in range(size)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda index: abs(augmented[index][column]))
        require(abs(augmented[pivot][column]) > 1e-12, "MODEL_MATRIX_SINGULAR", "candidate design is singular")
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        divisor = augmented[column][column]
        augmented[column] = [value / divisor for value in augmented[column]]
        for row in range(size):
            if row == column:
                continue
            factor = augmented[row][column]
            augmented[row] = [left - factor * right for left, right in zip(augmented[row], augmented[column])]
    return [augmented[index][-1] for index in range(size)]


def _rank(values: list[float]) -> list[float]:
    ordered = sorted(range(len(values)), key=values.__getitem__)
    ranks = [0.0] * len(values)
    start = 0
    while start < len(ordered):
        stop = start + 1
        while stop < len(ordered) and values[ordered[stop]] == values[ordered[start]]:
            stop += 1
        average = (start + 1 + stop) / 2.0
        for index in ordered[start:stop]:
            ranks[index] = average
        start = stop
    return ranks


def _pearson(left: list[float], right: list[float]) -> float:
    left_mean = sum(left) / len(left)
    right_mean = sum(right) / len(right)
    numerator = sum((x - left_mean) * (y - right_mean) for x, y in zip(left, right))
    denominator = math.sqrt(sum((x - left_mean) ** 2 for x in left) * sum((y - right_mean) ** 2 for y in right))
    return 0.0 if denominator == 0 else numerator / denominator


def spearman(actual: list[float], predicted: list[float]) -> float:
    return _pearson(_rank(actual), _rank(predicted))


def kendall_tau_b(actual: list[float], predicted: list[float]) -> float:
    concordant = discordant = ties_actual = ties_predicted = 0
    for left in range(len(actual)):
        for right in range(left + 1, len(actual)):
            a = (actual[left] > actual[right]) - (actual[left] < actual[right])
            p = (predicted[left] > predicted[right]) - (predicted[left] < predicted[right])
            if a == 0 and p == 0:
                continue
            if a == 0:
                ties_actual += 1
            elif p == 0:
                ties_predicted += 1
            elif a == p:
                concordant += 1
            else:
                discordant += 1
    denominator = math.sqrt((concordant + discordant + ties_actual) * (concordant + discordant + ties_predicted))
    return 0.0 if denominator == 0 else (concordant - discordant) / denominator


def metrics(actual: list[float], predicted: list[float]) -> dict[str, float]:
    require(len(actual) == len(predicted) and actual, "MODEL_METRIC_INPUT_INVALID", "metric inputs differ or are empty")
    actual_log = [math.log1p(value) for value in actual]
    predicted_log = [math.log1p(max(0.0, value)) for value in predicted]
    return {
        "spearman": spearman(actual, predicted),
        "kendall_tau_b": kendall_tau_b(actual, predicted),
        "log_rmse": math.sqrt(sum((left - right) ** 2 for left, right in zip(actual_log, predicted_log)) / len(actual)),
        "level_mae": sum(abs(left - right) for left, right in zip(actual, predicted)) / len(actual),
    }


def grouped_metrics(rows: list[Mapping[str, Any]], predicted: list[float]) -> dict[str, float]:
    require(len(rows) == len(predicted) and rows, "MODEL_METRIC_INPUT_INVALID", "grouped metric inputs differ or are empty")
    grouped: dict[str, tuple[list[float], list[float]]] = {}
    for row, value in zip(rows, predicted):
        actual_values, predicted_values = grouped.setdefault(str(row["successor_physical_location_id"]), ([], []))
        actual_values.append(float(row["isolated_sales"]))
        predicted_values.append(float(value))
    actual = [sum(values[0]) / len(values[0]) for _, values in sorted(grouped.items())]
    fitted = [sum(values[1]) / len(values[1]) for _, values in sorted(grouped.items())]
    return metrics(actual, fitted)


@dataclass(frozen=True)
class FittedCandidate:
    candidate_id: str
    terms: tuple[str, ...]
    feature_names: tuple[str, ...]
    numeric_means: Mapping[str, float]
    numeric_scales: Mapping[str, float]
    market_reference: str | None
    coefficients: tuple[float, ...]
    ridge_penalty: float

    def vector(self, row: Mapping[str, Any]) -> list[float]:
        vector = [1.0]
        features = row["features"]
        for name in self.feature_names:
            if name in NUMERIC_TERMS:
                vector.append((float(features[name]) - self.numeric_means[name]) / self.numeric_scales[name])
            elif name == "vintage_2025":
                vector.append(1.0 if row["forecast_vintage"] == 2025 else 0.0)
            elif name == "vintage_2026":
                vector.append(1.0 if row["forecast_vintage"] == 2026 else 0.0)
            elif name.startswith("market="):
                vector.append(1.0 if str(row["market"]) == name.split("=", 1)[1] else 0.0)
            else:
                raise AssertionError(f"unknown protected feature: {name}")
        return vector

    def predict_log(self, row: Mapping[str, Any]) -> float:
        return sum(value * coefficient for value, coefficient in zip(self.vector(row), self.coefficients))

    def predict(self, row: Mapping[str, Any]) -> float:
        return max(0.0, math.expm1(self.predict_log(row)))

    def fit_proxy_factor(self, row: Mapping[str, Any]) -> float:
        vector = self.vector(row)
        contribution = sum(vector[index + 1] * self.coefficients[index + 1] for index, name in enumerate(self.feature_names) if name in FIT_PROXY_TERMS)
        return math.exp(contribution)

    def protected_parameters(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "terms": list(self.terms),
            "feature_names": ["intercept", *self.feature_names],
            "numeric_means": dict(self.numeric_means),
            "numeric_scales": dict(self.numeric_scales),
            "market_reference": self.market_reference,
            "coefficients": list(self.coefficients),
            "ridge_penalty": self.ridge_penalty,
            "estimation_weighting": "inverse physical-location observation count",
        }


def fit_candidate(rows: list[Mapping[str, Any]], candidate: Mapping[str, Any], all_markets: Iterable[str]) -> FittedCandidate:
    require(rows, "MODEL_TRAINING_COHORT_EMPTY", "candidate training cohort is empty")
    terms = tuple(str(term) for term in candidate["terms"])
    numeric = [term for term in NUMERIC_TERMS if term in terms]
    group_counts: dict[str, int] = {}
    for row in rows:
        group = str(row["successor_physical_location_id"])
        group_counts[group] = group_counts.get(group, 0) + 1
    weights = [1.0 / group_counts[str(row["successor_physical_location_id"])] for row in rows]
    total_weight = sum(weights)
    means = {name: sum(weight * float(row["features"][name]) for row, weight in zip(rows, weights)) / total_weight for name in numeric}
    scales = {name: math.sqrt(sum(weight * (float(row["features"][name]) - means[name]) ** 2 for row, weight in zip(rows, weights)) / total_weight) for name in numeric}
    require(all(math.isfinite(value) and value > 1e-12 for value in scales.values()), "MODEL_FEATURE_CONSTANT", "candidate numeric feature is constant")
    feature_names = list(numeric)
    if "vintage_indicators" in terms:
        feature_names.extend(("vintage_2025", "vintage_2026"))
    market_reference: str | None = None
    if "market_indicators" in terms:
        markets = sorted(set(str(value) for value in all_markets))
        require(markets, "MODEL_MARKET_LINEAGE_EMPTY", "market lineage is absent")
        market_reference = markets[0]
        feature_names.extend("market=" + market for market in markets[1:])
    provisional = FittedCandidate(str(candidate["candidate_id"]), terms, tuple(feature_names), means, scales, market_reference, tuple(), float(candidate["ridge_penalty"]))
    design = [[1.0, *provisional.vector(row)[1:]] for row in rows]
    target = [math.log1p(float(row["isolated_sales"])) for row in rows]
    width = len(design[0])
    gram = [[sum(weight * row[left] * row[right] for row, weight in zip(design, weights)) for right in range(width)] for left in range(width)]
    cross = [sum(weight * row[column] * value for row, value, weight in zip(design, target, weights)) for column in range(width)]
    penalty = float(candidate["ridge_penalty"])
    for index in range(1, width):
        gram[index][index] += penalty
    gram[0][0] += 1e-10
    coefficients = tuple(_solve(gram, cross))
    require(all(math.isfinite(value) for value in coefficients), "MODEL_COEFFICIENT_NONFINITE", "candidate coefficient is nonfinite")
    return FittedCandidate(provisional.candidate_id, terms, provisional.feature_names, means, scales, market_reference, coefficients, penalty)


def grouped_folds(rows: list[Mapping[str, Any]], fold_count: int) -> dict[str, int]:
    groups = sorted({str(row["successor_physical_location_id"]) for row in rows}, key=lambda value: hashlib.sha256(value.encode("utf-8")).hexdigest())
    require(len(groups) >= fold_count >= 2, "GROUPED_FOLD_COUNT_INVALID", "physical-location groups cannot support requested folds")
    assignment = {group: index % fold_count for index, group in enumerate(groups)}
    require(set(assignment.values()) == set(range(fold_count)), "GROUPED_FOLD_EMPTY", "a grouped development fold is empty")
    return assignment


def _oof_predictions(rows: list[Mapping[str, Any]], candidate: Mapping[str, Any], fold_by_group: Mapping[str, int], all_markets: list[str]) -> tuple[list[float], list[dict[str, float]]]:
    predictions: dict[str, float] = {}
    fold_metrics: list[dict[str, float]] = []
    for fold in sorted(set(fold_by_group.values())):
        train = [row for row in rows if fold_by_group[str(row["successor_physical_location_id"])] != fold]
        test = [row for row in rows if fold_by_group[str(row["successor_physical_location_id"])] == fold]
        require(train and test and not ({str(row["successor_physical_location_id"]) for row in train} & {str(row["successor_physical_location_id"]) for row in test}), "PHYSICAL_LOCATION_LEAKAGE", "one physical location crossed development folds")
        fitted = fit_candidate(train, candidate, all_markets)
        fold_predicted = [fitted.predict(row) for row in test]
        fold_metrics.append(grouped_metrics(test, fold_predicted))
        for row, value in zip(test, fold_predicted):
            predictions[str(row["source_observation_id"])] = value
    require(len(predictions) == len(rows), "OOF_PREDICTION_INCOMPLETE", "out-of-fold predictions do not cover the complete cohort")
    return [predictions[str(row["source_observation_id"])] for row in rows], fold_metrics


def _market_holdout(rows: list[Mapping[str, Any]], candidate: Mapping[str, Any], all_markets: list[str]) -> dict[str, Any]:
    predictions: dict[str, float] = {}
    evaluated_markets = 0
    for market in all_markets:
        test = [row for row in rows if str(row["market"]) == market]
        test_groups = {str(row["successor_physical_location_id"]) for row in test}
        train = [row for row in rows if str(row["successor_physical_location_id"]) not in test_groups]
        if not train or not test:
            continue
        require(not ({str(row["successor_physical_location_id"]) for row in train} & test_groups), "PHYSICAL_LOCATION_LEAKAGE", "one physical location crossed a market-holdout diagnostic")
        fitted = fit_candidate(train, candidate, all_markets)
        evaluated_markets += 1
        for row in test:
            predictions[str(row["source_observation_id"])] = fitted.predict(row)
    require(len(predictions) == len(rows), "MARKET_HOLDOUT_INCOMPLETE", "leave-one-market-out predictions do not cover complete cohort")
    return {"market_count": evaluated_markets, **grouped_metrics(rows, [predictions[str(row["source_observation_id"])] for row in rows])}


def compare_candidates(rows: list[Mapping[str, Any]], contract: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[FittedCandidate], dict[str, Any], dict[str, list[float]]]:
    candidates = contract.get("candidates")
    require(isinstance(candidates, list) and len(candidates) == 4 and len({item.get("candidate_id") for item in candidates}) == 4, "BOUNDED_CANDIDATE_CONFIG_INVALID", "exactly four distinct candidates are required")
    fold_count = int(contract["development_diagnostics"]["grouped_fold_count"])
    assignment = grouped_folds(rows, fold_count)
    all_markets = sorted({str(row["market"]) for row in rows})
    comparison: list[dict[str, Any]] = []
    fitted_models: list[FittedCandidate] = []
    oof_by_candidate: dict[str, list[float]] = {}
    for candidate in candidates:
        predicted, fold_values = _oof_predictions(rows, candidate, assignment, all_markets)
        candidate_id = str(candidate["candidate_id"])
        aggregate = grouped_metrics(rows, predicted)
        comparison.append(
            {
                "candidate_id": candidate_id,
                "complexity_rank": int(candidate["complexity_rank"]),
                "terms": list(candidate["terms"]),
                "grouped_oof": aggregate,
                "fold_metric_ranges": {name: {"minimum": min(fold[name] for fold in fold_values), "maximum": max(fold[name] for fold in fold_values)} for name in aggregate},
                "leave_one_market_out": _market_holdout(rows, candidate, all_markets),
            }
        )
        fitted_models.append(fit_candidate(rows, candidate, all_markets))
        oof_by_candidate[candidate_id] = predicted
    baseline = next(item for item in comparison if item["candidate_id"] == "baseline_opportunity")
    selection_config = contract["selection"]
    qualifiers = [
        item
        for item in comparison
        if item["candidate_id"] != "baseline_opportunity"
        and item["grouped_oof"]["spearman"] >= baseline["grouped_oof"]["spearman"] + float(selection_config["minimum_spearman_improvement_over_baseline"])
        and item["grouped_oof"]["log_rmse"] <= baseline["grouped_oof"]["log_rmse"] * float(selection_config["maximum_log_rmse_ratio_to_baseline"])
    ]
    qualifiers.sort(key=lambda item: (-item["grouped_oof"]["spearman"], item["grouped_oof"]["log_rmse"], item["complexity_rank"]))
    selection = {
        "baseline_candidate_id": "baseline_opportunity",
        "qualifying_challenger_ids": [item["candidate_id"] for item in qualifiers],
        "preferred_candidate_id": qualifiers[0]["candidate_id"] if qualifiers else None,
        "conclusion": "PREFERRED_EXPERIMENTAL_FORMULATION_SELECTED" if qualifiers else str(selection_config["no_qualifying_challenger"]),
        "selection_rule_applied_without_post_hoc_change": True,
    }
    return comparison, fitted_models, selection, oof_by_candidate
