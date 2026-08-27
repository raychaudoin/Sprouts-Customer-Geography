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
from sprouts_customer_geography.pipe01.errors import require


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
        predictions, _ = grouped_oof_predictions(
            rows,
            candidate_id,
            terms,
            alpha=parameters["alpha"],
            l1_ratio=parameters["l1_ratio"],
            fold_count=fold_count,
        )
        metrics = grouped_metrics(list(rows), predictions)
        scored.append((-float(metrics["spearman"]), float(metrics["log_rmse"]), index, parameters))
    scored.sort(key=lambda item: (item[0], item[1], item[2]))
    return scored[0][3]


def nested_grouped_oof(
    rows: Sequence[Mapping[str, Any]],
    candidate_id: str,
    terms: Sequence[str],
    *,
    alpha_grid: Sequence[float] = (0.01, 0.1, 1.0, 10.0),
    l1_ratio_grid: Sequence[float] = (0.25, 0.5, 0.75),
    outer_count: int = 5,
    inner_count: int = 4,
) -> dict[str, Any]:
    rows = list(rows)
    assignment = state_balanced_grouped_folds(rows, outer_count)
    predictions: dict[str, float] = {}
    fold_audits: list[dict[str, Any]] = []
    selected_parameters: list[dict[str, float]] = []
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
        selected_parameters.append(dict(parameters))
        for row in test:
            predictions[str(row["analytical_observation_id"])] = fitted.predict(row)
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
    domains: dict[str, Any] = {}
    for label, state in (("pooled", None), ("michigan", "MI"), ("wisconsin", "WI")):
        selected = [(row, prediction) for row, prediction in zip(rows, ordered) if state is None or row["state"] == state]
        require(selected, "MODEL14_METRIC_DOMAIN_EMPTY", "one MODEL-14 metric domain is empty")
        domains[label] = grouped_metrics([row for row, _ in selected], [prediction for _, prediction in selected])
    return {
        "candidate_id": candidate_id,
        "terms": list(terms),
        "aggregate_oof": domains,
        "outer_selected_parameters": selected_parameters,
        "fold_audits": fold_audits,
        "predictions": ordered,
    }
