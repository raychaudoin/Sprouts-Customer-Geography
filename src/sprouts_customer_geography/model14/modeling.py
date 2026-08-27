"""Bounded grouped modeling with training-fold-only missing-value preprocessing."""

from __future__ import annotations

import copy
from dataclasses import dataclass
import math
from statistics import median
from typing import Any, Mapping, Sequence

from sprouts_customer_geography.model09.modeling import grouped_metrics
from sprouts_customer_geography.model13.modeling import (
    FittedSuccessorModel,
    GROUP_FIELD,
    fit_regularized,
    state_balanced_grouped_folds,
)
from sprouts_customer_geography.pipe01.errors import ConformanceError, require


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


@dataclass(frozen=True)
class TrainingFoldPreprocessor:
    """Medians learned from distinct training groups only."""

    terms: tuple[str, ...]
    medians: Mapping[str, float]
    training_group_count: int

    def transform_features(self, features: Mapping[str, Any]) -> dict[str, Any]:
        output = dict(features)
        for term in self.terms:
            value = output.get(term)
            output[term] = float(value) if _finite(value) else float(self.medians[term])
        return output

    def transform_rows(self, rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
        return [{**copy.deepcopy(dict(row)), "features": self.transform_features(row["features"])} for row in rows]


def fit_training_fold_preprocessor(rows: Sequence[Mapping[str, Any]], terms: Sequence[str]) -> TrainingFoldPreprocessor:
    rows = list(rows)
    ordered_terms = tuple(str(term) for term in terms)
    require(rows and ordered_terms and len(ordered_terms) == len(set(ordered_terms)), "MODEL14_PREPROCESSING_CONFIG_INVALID", "MODEL-14 preprocessing configuration is invalid")
    group_features: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        group = str(row[GROUP_FIELD])
        features = row.get("features")
        require(isinstance(features, Mapping), "MODEL14_FEATURE_VECTOR_INVALID", "one MODEL-14 feature vector is invalid")
        prior = group_features.get(group)
        if prior is None:
            group_features[group] = features
            continue
        for term in ordered_terms:
            left = prior.get(term)
            right = features.get(term)
            require(
                (not _finite(left) and not _finite(right)) or (_finite(left) and _finite(right) and abs(float(left) - float(right)) <= 1e-12),
                "MODEL14_WITHIN_GROUP_FEATURE_MISMATCH",
                "repeated observations from one physical location have different feature values",
            )
    medians: dict[str, float] = {}
    for term in ordered_terms:
        values = [float(features[term]) for features in group_features.values() if _finite(features.get(term))]
        require(values, "MODEL14_TRAINING_FEATURE_ALL_MISSING", "one MODEL-14 training feature is missing in every training group")
        value = float(median(values))
        require(math.isfinite(value), "MODEL14_TRAINING_MEDIAN_INVALID", "one MODEL-14 training median is invalid")
        medians[term] = value
    return TrainingFoldPreprocessor(ordered_terms, medians, len(group_features))


@dataclass(frozen=True)
class FittedExperimentalModel:
    base: FittedSuccessorModel
    preprocessor: TrainingFoldPreprocessor

    def predict(self, row: Mapping[str, Any]) -> float:
        return self.base.predict_features(self.preprocessor.transform_features(row["features"]))


def fit_experimental_model(
    rows: Sequence[Mapping[str, Any]],
    candidate_id: str,
    terms: Sequence[str],
    *,
    alpha: float,
    l1_ratio: float,
) -> FittedExperimentalModel:
    preprocessor = fit_training_fold_preprocessor(rows, terms)
    transformed = preprocessor.transform_rows(rows)
    model = fit_regularized(
        transformed,
        candidate_id,
        "elastic_net",
        terms,
        alpha=float(alpha),
        l1_ratio=float(l1_ratio),
    )
    return FittedExperimentalModel(model, preprocessor)


def _parameter_grid(alpha_grid: Sequence[float], l1_ratio_grid: Sequence[float]) -> list[dict[str, float]]:
    grid = [{"alpha": float(alpha), "l1_ratio": float(ratio)} for alpha in alpha_grid for ratio in l1_ratio_grid]
    require(
        grid
        and len(grid) <= 12
        and all(item["alpha"] >= 0 and 0 < item["l1_ratio"] <= 1 for item in grid),
        "MODEL14_PARAMETER_GRID_INVALID",
        "MODEL-14 parameter grid is invalid or unbounded",
    )
    return grid


def grouped_oof_predictions(
    rows: Sequence[Mapping[str, Any]],
    candidate_id: str,
    terms: Sequence[str],
    *,
    alpha: float,
    l1_ratio: float,
    fold_count: int,
) -> tuple[list[float], list[dict[str, Any]]]:
    rows = list(rows)
    assignment = state_balanced_grouped_folds(rows, fold_count)
    predictions: dict[str, float] = {}
    audits: list[dict[str, Any]] = []
    for fold in range(fold_count):
        train = [row for row in rows if assignment[str(row[GROUP_FIELD])] != fold]
        test = [row for row in rows if assignment[str(row[GROUP_FIELD])] == fold]
        train_groups = {str(row[GROUP_FIELD]) for row in train}
        test_groups = {str(row[GROUP_FIELD]) for row in test}
        require(not train_groups & test_groups, "MODEL14_PHYSICAL_LOCATION_LEAKAGE", "one physical location crossed a MODEL-14 fold")
        fitted = fit_experimental_model(train, candidate_id, terms, alpha=alpha, l1_ratio=l1_ratio)
        imputed_test_values = sum(not _finite(row["features"].get(term)) for row in test for term in terms)
        for row in test:
            observation = str(row["analytical_observation_id"])
            require(observation not in predictions, "MODEL14_OOF_OBSERVATION_DUPLICATE", "one MODEL-14 OOF observation is duplicate")
            predictions[observation] = fitted.predict(row)
        audits.append({
            "fold": fold,
            "training_group_count": len(train_groups),
            "test_group_count": len(test_groups),
            "group_overlap_count": 0,
            "preprocessing_fit_scope": "training_groups_only",
            "test_value_count_imputed": imputed_test_values,
        })
    require(len(predictions) == len(rows), "MODEL14_OOF_PREDICTION_INCOMPLETE", "MODEL-14 OOF predictions are incomplete")
    return [predictions[str(row["analytical_observation_id"])] for row in rows], audits


def tune_parameters(
    rows: Sequence[Mapping[str, Any]],
    candidate_id: str,
    terms: Sequence[str],
    *,
    alpha_grid: Sequence[float],
    l1_ratio_grid: Sequence[float],
    fold_count: int,
) -> dict[str, float]:
    scored: list[tuple[float, float, int, dict[str, float]]] = []
    for index, parameters in enumerate(_parameter_grid(alpha_grid, l1_ratio_grid)):
        try:
            predictions, _ = grouped_oof_predictions(
                rows,
                candidate_id,
                terms,
                alpha=parameters["alpha"],
                l1_ratio=parameters["l1_ratio"],
                fold_count=fold_count,
            )
            # A grid point is eligible only if it also converges on the complete
            # current training scope, not merely on every inner-fold subset.
            fit_experimental_model(rows, candidate_id, terms, **parameters)
        except ConformanceError as exc:
            if exc.code == "MODEL13_ELASTIC_NET_DID_NOT_CONVERGE":
                continue
            raise
        metrics = grouped_metrics(list(rows), predictions)
        scored.append((-float(metrics["spearman"]), float(metrics["log_rmse"]), index, parameters))
    require(scored, "MODEL14_NO_CONVERGENT_PARAMETER", "no bounded MODEL-14 elastic-net parameter converged across the training scope")
    scored.sort(key=lambda item: (item[0], item[1], item[2]))
    return scored[0][3]


def _domain_metrics(
    rows: Sequence[Mapping[str, Any]],
    predictions: Sequence[float],
    state: str | None = None,
) -> dict[str, float]:
    selected = [
        (row, prediction)
        for row, prediction in zip(rows, predictions)
        if state is None or str(row["state"]) == state
    ]
    require(selected, "MODEL14_METRIC_DOMAIN_EMPTY", "one MODEL-14 metric domain is empty")
    return grouped_metrics(
        [row for row, _ in selected],
        [prediction for _, prediction in selected],
    )


def _coefficient_stability(models: Sequence[FittedExperimentalModel]) -> dict[str, Any]:
    require(
        models and all(model.base.terms == models[0].base.terms for model in models),
        "MODEL14_TERM_INSTABILITY",
        "MODEL-14 fold model terms differ",
    )
    terms = models[0].base.terms
    selection: dict[str, float] = {}
    signs: dict[str, float] = {}
    deviations: dict[str, float] = {}
    for index, term in enumerate(terms):
        values = [model.base.coefficients[index] for model in models]
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
    return {
        "selection_frequency": selection,
        "coefficient_sign_stability": signs,
        "coefficient_standard_deviation": deviations,
        "stability_score": score,
    }


def _family_stability(
    stability: Mapping[str, Any],
    terms: Sequence[str],
    term_families: Mapping[str, str],
) -> dict[str, Any]:
    grouped: dict[str, list[str]] = {}
    for term in terms:
        grouped.setdefault(str(term_families.get(term, "unassigned")), []).append(term)
    output: dict[str, Any] = {}
    for family, family_terms in sorted(grouped.items()):
        selection = [float(stability["selection_frequency"][term]) for term in family_terms]
        signs = [float(stability["coefficient_sign_stability"][term]) for term in family_terms]
        output[family] = {
            "term_count": len(family_terms),
            "selected_in_any_fold_count": sum(value > 0 for value in selection),
            "selected_in_every_fold_count": sum(value >= 1.0 - 1e-12 for value in selection),
            "mean_selection_frequency": sum(selection) / len(selection),
            "mean_dominant_sign_agreement": sum(signs) / len(signs),
        }
    return output


def _outlier_sensitivity(rows: Sequence[Mapping[str, Any]], predictions: Sequence[float]) -> dict[str, Any]:
    grouped: dict[str, tuple[list[float], list[float]]] = {}
    for row, prediction in zip(rows, predictions):
        actual, predicted = grouped.setdefault(str(row[GROUP_FIELD]), ([], []))
        actual.append(float(row["isolated_sales"]))
        predicted.append(float(prediction))
    require(len(grouped) >= 3, "MODEL14_OUTLIER_SUPPORT_INSUFFICIENT", "MODEL-14 outlier sensitivity lacks group support")
    errors = {
        group: abs(
            math.log1p(sum(actual) / len(actual))
            - math.log1p(max(0.0, sum(predicted) / len(predicted)))
        )
        for group, (actual, predicted) in grouped.items()
    }
    worst_group = max(errors, key=lambda group: (errors[group], group))
    retained = [
        (row, prediction)
        for row, prediction in zip(rows, predictions)
        if str(row[GROUP_FIELD]) != worst_group
    ]
    before = _domain_metrics(rows, predictions)
    after = grouped_metrics(
        [row for row, _ in retained],
        [prediction for _, prediction in retained],
    )
    return {
        "maximum_physical_location_absolute_log_error": errors[worst_group],
        "excluded_physical_location_count": 1,
        "retained_physical_location_count": len(grouped) - 1,
        "pooled_metrics_without_max_error_location": after,
        "pooled_metric_delta_without_max_error_location": {
            metric: float(after[metric]) - float(before[metric]) for metric in before
        },
        "protected_location_identity_disclosed": False,
    }


def nested_grouped_oof(
    rows: Sequence[Mapping[str, Any]],
    candidate_id: str,
    terms: Sequence[str],
    *,
    alpha_grid: Sequence[float] = (0.01, 0.1, 1.0, 10.0),
    l1_ratio_grid: Sequence[float] = (0.25, 0.5, 0.75),
    outer_count: int = 5,
    inner_count: int = 4,
    term_families: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    rows = list(rows)
    assignment = state_balanced_grouped_folds(rows, outer_count)
    predictions: dict[str, float] = {}
    fold_audits: list[dict[str, Any]] = []
    selected_parameters: list[dict[str, float]] = []
    fold_models: list[FittedExperimentalModel] = []
    fold_domains: dict[str, list[dict[str, float]]] = {
        "pooled": [],
        "michigan": [],
        "wisconsin": [],
    }
    for fold in range(outer_count):
        train = [row for row in rows if assignment[str(row[GROUP_FIELD])] != fold]
        test = [row for row in rows if assignment[str(row[GROUP_FIELD])] == fold]
        train_groups = {str(row[GROUP_FIELD]) for row in train}
        test_groups = {str(row[GROUP_FIELD]) for row in test}
        require(not train_groups & test_groups, "MODEL14_PHYSICAL_LOCATION_LEAKAGE", "one physical location crossed a MODEL-14 outer fold")
        parameters = tune_parameters(
            train,
            candidate_id,
            terms,
            alpha_grid=alpha_grid,
            l1_ratio_grid=l1_ratio_grid,
            fold_count=inner_count,
        )
        fitted = fit_experimental_model(train, candidate_id, terms, **parameters)
        fold_models.append(fitted)
        selected_parameters.append(dict(parameters))
        fold_predictions = [fitted.predict(row) for row in test]
        fold_domains["pooled"].append(_domain_metrics(test, fold_predictions))
        fold_domains["michigan"].append(_domain_metrics(test, fold_predictions, "MI"))
        fold_domains["wisconsin"].append(_domain_metrics(test, fold_predictions, "WI"))
        for row, prediction in zip(test, fold_predictions):
            predictions[str(row["analytical_observation_id"])] = prediction
        fold_audits.append({
            "fold": fold,
            "training_group_count": len(train_groups),
            "test_group_count": len(test_groups),
            "group_overlap_count": 0,
            "preprocessing_fit_scope": "outer_training_groups_only",
            "inner_preprocessing_fit_scope": "inner_training_groups_only",
        })
    require(len(predictions) == len(rows), "MODEL14_OOF_PREDICTION_INCOMPLETE", "MODEL-14 nested OOF predictions are incomplete")
    ordered = [predictions[str(row["analytical_observation_id"])] for row in rows]
    domains = {
        "pooled": _domain_metrics(rows, ordered),
        "michigan": _domain_metrics(rows, ordered, "MI"),
        "wisconsin": _domain_metrics(rows, ordered, "WI"),
    }
    metric_names = ("spearman", "kendall_tau_b", "log_rmse", "level_mae")
    ranges = {
        domain: {
            metric: {
                "minimum": min(fold[metric] for fold in values),
                "maximum": max(fold[metric] for fold in values),
            }
            for metric in metric_names
        }
        for domain, values in fold_domains.items()
    }
    stability = _coefficient_stability(fold_models)
    families = {str(term): "unassigned" for term in terms}
    if term_families is not None:
        families.update({str(term): str(family) for term, family in term_families.items()})
    final_parameters = tune_parameters(
        rows,
        candidate_id,
        terms,
        alpha_grid=alpha_grid,
        l1_ratio_grid=l1_ratio_grid,
        fold_count=inner_count,
    )
    final_model = fit_experimental_model(rows, candidate_id, terms, **final_parameters)
    degrees = [model.base.effective_degrees_of_freedom() for model in fold_models]
    return {
        "candidate_id": candidate_id,
        "terms": list(terms),
        "aggregate_oof": domains,
        "outer_fold_metric_ranges": ranges,
        "outer_selected_parameters": selected_parameters,
        "fold_audits": fold_audits,
        "stability": stability,
        "feature_family_stability": _family_stability(stability, terms, families),
        "mean_outer_effective_degrees_of_freedom": sum(degrees) / len(degrees),
        "outer_effective_degrees_of_freedom_range": [min(degrees), max(degrees)],
        "outlier_sensitivity": _outlier_sensitivity(rows, ordered),
        "final_parameters": dict(final_parameters),
        "final_standardized_coefficients": {
            term: coefficient
            for term, coefficient in zip(final_model.base.terms, final_model.base.coefficients)
        },
        "final_effective_degrees_of_freedom": final_model.base.effective_degrees_of_freedom(),
        "predictions": ordered,
    }
