"""Bounded, deterministic MODEL-16 development, with no source/target I/O.

All returned model objects, prediction arrays, fold audits, parameter selections,
stability values, and exact memberships are protected-local artifacts when inputs
are protected. A caller must separately freeze evidence and authorize target access.
This module never opens a file containing an observation or target.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
import hashlib
import itertools
import json
import math
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
import warnings

import numpy as np
from scipy.stats import kendalltau, rankdata
from sklearn.ensemble import ExtraTreesRegressor, GradientBoostingRegressor, RandomForestRegressor
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import ElasticNet, Ridge


BASELINE_ID = "clean_model13_baseline"
NONLINEAR_STABILITY_ARCHITECTURES = frozenset({"spline_ridge", "random_forest", "extra_trees", "gradient_boosting", "simple_log_ensemble"})
SPATIAL_TERMS = (
    "log_households_5mi", "inner_household_share_3mi_of_7mi",
    "log_inner_outer_household_density_gradient",
)
METRICS = ("spearman", "kendall_tau_b", "log_rmse", "level_mae",
           "calibration_slope", "calibration_intercept", "top_quartile_overlap")


class ModelingError(ValueError):
    """Only safe reason codes; never include input values in exceptions."""


def _check(condition: bool, code: str) -> None:
    if not condition:
        raise ModelingError(code)


@dataclass(frozen=True)
class Dataset:
    X: np.ndarray
    y: np.ndarray
    groups: tuple[str, ...]
    states: tuple[str, ...]
    years: tuple[int, ...]
    evidence_classes: tuple[str, ...]
    feature_names: tuple[str, ...]
    feature_families: tuple[str, ...]
    baseline_features: tuple[str, ...]
    markets: tuple[str, ...] = ()

    def validate(self, *, development: bool = False) -> None:
        x, y = np.asarray(self.X, dtype=float), np.asarray(self.y, dtype=float)
        n = len(y)
        _check(x.ndim == 2 and y.ndim == 1 and n > 0, "MODEL16_ARRAY_SHAPE_INVALID")
        _check(x.shape == (n, len(self.feature_names)), "MODEL16_FEATURE_DIMENSION_MISMATCH")
        _check(len(self.feature_families) == len(self.feature_names) > 0, "MODEL16_CATALOG_DIMENSION_MISMATCH")
        _check(len(set(self.feature_names)) == len(self.feature_names), "MODEL16_FEATURE_NAME_DUPLICATE")
        _check(all(len(v) == n for v in (self.groups, self.states, self.years, self.evidence_classes)), "MODEL16_METADATA_LENGTH_MISMATCH")
        _check(not self.markets or len(self.markets) == n, "MODEL16_MARKET_LENGTH_MISMATCH")
        _check(np.all(np.isfinite(y)) and np.all(y > 0), "MODEL16_TARGET_INVALID")
        _check(not np.any(np.isinf(x)), "MODEL16_INFINITE_FEATURE")
        _check(all(self.groups) and set(self.states) <= {"MI", "WI"}, "MODEL16_GROUP_STATE_INVALID")
        _check(set(self.baseline_features) <= set(self.feature_names) and len(set(self.baseline_features)) == len(self.baseline_features), "MODEL16_BASELINE_FEATURES_INVALID")
        _check(bool(self.baseline_features), "MODEL16_BASELINE_FEATURES_EMPTY")
        group_states: dict[str, str] = {}
        group_markets: dict[str, str] = {}
        for i, (group, state) in enumerate(zip(self.groups, self.states)):
            _check(group not in group_states or group_states[group] == state, "MODEL16_CROSS_STATE_GROUP")
            group_states[group] = state
            if self.markets:
                _check(group not in group_markets or group_markets[group] == self.markets[i], "MODEL16_CROSS_MARKET_GROUP_UNRESOLVED")
                group_markets[group] = self.markets[i]
        if development:
            _check(set(self.years) <= {2024, 2025}, "MODEL16_HOLDOUT_IN_DEVELOPMENT")
            _check(set(self.evidence_classes) == {"SEED_POINT"}, "MODEL16_PURSUED_IN_DEVELOPMENT")
            _check(set(self.states) == {"MI", "WI"}, "MODEL16_BOTH_STATES_REQUIRED")

    def take(self, indices: Sequence[int] | np.ndarray) -> Dataset:
        idx = np.asarray(indices)
        if idx.dtype == bool:
            idx = np.flatnonzero(idx)
        idx = idx.astype(int)
        return Dataset(np.asarray(self.X)[idx], np.asarray(self.y)[idx],
                       *(tuple(values[i] for i in idx) for values in
                         (self.groups, self.states, self.years, self.evidence_classes)),
                       self.feature_names, self.feature_families, self.baseline_features,
                       tuple(self.markets[i] for i in idx) if self.markets else ())


def load_library(path: str | Path | None = None) -> dict[str, Any]:
    if path is None:
        # Repository configuration remains the authority when this module is
        # installed as a wheel. Callers outside the checkout pass an exact path.
        path = Path.cwd() / "config" / "model16" / "model_library.json"
    _check(Path(path).is_file(), "MODEL16_LIBRARY_MISSING")
    try:
        result = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise ModelingError("MODEL16_LIBRARY_UNREADABLE") from None
    _check(result.get("artifact_id") == "MODEL16_GENERATION1_MODEL_LIBRARY_V1", "MODEL16_LIBRARY_INVALID")
    return result


def location_weights(groups: Sequence[str]) -> np.ndarray:
    counts = Counter(groups)
    _check(bool(counts) and all(groups), "MODEL16_GROUPS_EMPTY")
    return np.asarray([1.0 / counts[g] for g in groups], dtype=float)


def grouped_folds(groups: Sequence[str], states: Sequence[str], count: int, seed: int) -> np.ndarray:
    _check(len(groups) == len(states) and count >= 2, "MODEL16_FOLDS_INVALID")
    state_by_group: dict[str, str] = {}
    for group, state in zip(groups, states):
        _check(group not in state_by_group or state_by_group[group] == state, "MODEL16_CROSS_STATE_GROUP")
        state_by_group[group] = state
    assignment: dict[str, int] = {}
    for state in sorted(set(states)):
        ordered = sorted((g for g, s in state_by_group.items() if s == state),
                         key=lambda g: (hashlib.sha256(f"{seed}:{g}".encode()).hexdigest(), g))
        _check(len(ordered) >= count, "MODEL16_STATE_FOLD_SUPPORT_INSUFFICIENT")
        for i, group in enumerate(ordered):
            assignment[group] = i % count
    return np.asarray([assignment[g] for g in groups], dtype=int)


def _weighted_quantile(values: np.ndarray, weights: np.ndarray, q: float) -> float:
    order = np.argsort(values, kind="stable")
    v, w = values[order], weights[order]
    # Collapse ties: duplicated rows cannot change a weighted knot or median.
    unique, inverse = np.unique(v, return_inverse=True)
    mass = np.bincount(inverse, weights=w)
    cumulative = np.cumsum(mass)
    index = min(int(np.searchsorted(cumulative, q * cumulative[-1], side="left")), len(unique) - 1)
    return float(unique[index])


@dataclass
class FoldPreprocessor:
    """Weights, imputation, screening, and transforms are learned on fit rows only."""
    selected_input: tuple[int, ...]
    names: tuple[str, ...]
    baseline: bool
    config: Mapping[str, Any]
    architecture: str
    components: int = 2
    retained_input: tuple[int, ...] = ()
    medians: np.ndarray = field(default_factory=lambda: np.empty(0))
    indicator_input: tuple[int, ...] = ()
    means: np.ndarray = field(default_factory=lambda: np.empty(0))
    scales: np.ndarray = field(default_factory=lambda: np.empty(0))
    transformed_names: tuple[str, ...] = ()
    excluded: dict[str, str] = field(default_factory=dict)
    knots: np.ndarray | None = None
    pca_loadings: np.ndarray | None = None
    expansion_means: np.ndarray | None = None
    expansion_scales: np.ndarray | None = None

    def fit(self, x: np.ndarray, groups: Sequence[str]) -> FoldPreprocessor:
        x = np.asarray(x, dtype=float)
        w = location_weights(groups)
        retained, medians, imputed, indicators = [], [], [], []
        tolerance = float(self.config["constant_tolerance"])
        for j in self.selected_input:
            col = x[:, j]
            missing = np.isnan(col)
            if missing.all() or (self.baseline and missing.any()):
                self.excluded[self.names[j]] = "ALL_MISSING_TRAIN" if missing.all() else "BASELINE_INCOMPLETE_TRAIN"
                continue
            median = _weighted_quantile(col[~missing], w[~missing], 0.5)
            filled = np.where(missing, median, col)
            mean = np.average(filled, weights=w)
            variance = np.average((filled - mean) ** 2, weights=w)
            if variance <= tolerance ** 2:
                self.excluded[self.names[j]] = "CONSTANT_TRAIN"
                continue
            retained.append(j)
            medians.append(median)
            imputed.append(filled)
            if missing.any() and not self.baseline:
                indicators.append(j)
        _check(bool(retained), "MODEL16_NO_COMPUTABLE_TRAIN_FEATURES")
        z = np.asarray(imputed).T
        means = np.average(z, axis=0, weights=w)
        scales = np.sqrt(np.average((z - means) ** 2, axis=0, weights=w))
        standardized = (z - means) / scales
        # Accepted MODEL-13 screening uses one feature vector per location.
        # Clean yearly observations can differ; use their location mean for
        # this screen while retaining all observations for weighted estimation.
        correlation_design = standardized
        correlation_weights = w
        if self.baseline:
            group_array = np.asarray(groups)
            grouped = np.asarray([np.mean(z[group_array == group], axis=0) for group in sorted(set(groups))])
            group_scales = np.std(grouped, axis=0)
            group_scales[group_scales <= tolerance] = 1.0
            correlation_design = (grouped - np.mean(grouped, axis=0)) / group_scales
            correlation_weights = np.ones(len(grouped))
        threshold = float(self.config["baseline_redundancy_absolute_correlation"] if self.baseline else self.config["redundancy_absolute_correlation"])
        kept: list[int] = []
        exempt = set(self.config["baseline_exempt_terms"]) if self.baseline else set()
        for k, j in enumerate(retained):
            redundant = self.names[j] not in exempt and any(
                abs(float(np.average(correlation_design[:, k] * correlation_design[:, previous], weights=correlation_weights))) >= threshold
                for previous in kept)
            if redundant:
                self.excluded[self.names[j]] = "REDUNDANT_TRAIN"
            else:
                kept.append(k)
        self.retained_input = tuple(retained[k] for k in kept)
        self.medians = np.asarray([medians[k] for k in kept])
        self.indicator_input = tuple(j for j in indicators if j in self.retained_input)
        raw = self._raw(x)
        self.means = np.average(raw, axis=0, weights=w)
        self.scales = np.sqrt(np.average((raw - self.means) ** 2, axis=0, weights=w))
        _check(np.all(self.scales > tolerance), "MODEL16_PREPROCESSOR_CONSTANT")
        self.transformed_names = tuple(self.names[j] for j in self.retained_input) + tuple(self.names[j] + "__missing" for j in self.indicator_input)
        scaled = (raw - self.means) / self.scales
        if self.architecture == "spline_ridge":
            self.knots = np.asarray([[_weighted_quantile(scaled[:, j], w, q) for q in (1 / 3, 2 / 3)] for j in range(scaled.shape[1])])
            expanded = self._expand(scaled)
            self.expansion_means = np.average(expanded, axis=0, weights=w)
            self.expansion_scales = np.sqrt(np.average((expanded - self.expansion_means) ** 2, axis=0, weights=w))
            self.expansion_scales[self.expansion_scales <= tolerance] = 1.0
        elif self.architecture == "pca_ridge":
            _, singular, vt = np.linalg.svd(scaled * np.sqrt(w[:, None]), full_matrices=False)
            dim = min(self.components, max(1, len(set(groups)) // 5), int(np.sum(singular > tolerance)), scaled.shape[1])
            _check(dim > 0, "MODEL16_PCA_RANK_ZERO")
            self.pca_loadings = vt[:dim].T
            for j in range(dim):
                pivot = np.argmax(np.abs(self.pca_loadings[:, j]))
                if self.pca_loadings[pivot, j] < 0:
                    self.pca_loadings[:, j] *= -1
        return self

    def _raw(self, x: np.ndarray) -> np.ndarray:
        selected = np.asarray(x, dtype=float)[:, self.retained_input]
        if self.baseline:
            _check(np.all(np.isfinite(selected)), "MODEL16_BASELINE_RETAINED_FEATURE_MISSING")
        filled = np.where(np.isnan(selected), self.medians, selected)
        if self.indicator_input:
            filled = np.column_stack((filled, np.isnan(x[:, self.indicator_input]).astype(float)))
        return filled

    def _expand(self, z: np.ndarray) -> np.ndarray:
        assert self.knots is not None
        return np.column_stack([v for j in range(z.shape[1]) for v in
                                (z[:, j], np.maximum(0, z[:, j] - self.knots[j, 0]),
                                 np.maximum(0, z[:, j] - self.knots[j, 1]))])

    def transform(self, x: np.ndarray) -> np.ndarray:
        _check(np.asarray(x).ndim == 2 and np.asarray(x).shape[1] == len(self.names), "MODEL16_PREDICT_FEATURE_DIMENSION_MISMATCH")
        _check(not np.any(np.isinf(x)), "MODEL16_INFINITE_FEATURE")
        z = (self._raw(np.asarray(x)) - self.means) / self.scales
        if self.knots is not None:
            z = (self._expand(z) - self.expansion_means) / self.expansion_scales
        if self.pca_loadings is not None:
            z = z @ self.pca_loadings
        _check(np.all(np.isfinite(z)), "MODEL16_TRANSFORM_NONFINITE")
        return z


@dataclass
class FittedModel:
    candidate_id: str
    architecture: str
    feature_names: tuple[str, ...]
    preprocessor: FoldPreprocessor
    estimator: Any
    parameters: dict[str, Any]
    train_groups: tuple[str, ...]
    state_levels: tuple[str, ...] = ()
    state_coefficients: np.ndarray | None = None
    ensemble_tree: Any = None

    def predict(self, x: np.ndarray, states: Sequence[str], feature_names: Sequence[str] | None = None) -> np.ndarray:
        if feature_names is not None:
            _check(tuple(feature_names) == self.feature_names, "MODEL16_PREDICT_FEATURE_ORDER_MISMATCH")
        _check(len(states) == len(x) and set(states) <= {"MI", "WI"}, "MODEL16_PREDICT_STATE_INVALID")
        z = self.preprocessor.transform(x)
        if self.architecture == "state_partial_pooling":
            design = np.column_stack((np.ones(len(z)), z, *[np.asarray(states) == s for s in self.state_levels]))
            log_predictions = design @ self.state_coefficients
        else:
            log_predictions = self.estimator.predict(z)
        if self.ensemble_tree is not None:
            mix = float(self.parameters["tree_weight"])
            log_predictions = (1 - mix) * log_predictions + mix * self.ensemble_tree.predict(z)
        _check(np.all(np.isfinite(log_predictions)) and np.max(log_predictions) < 700, "MODEL16_PREDICTION_NONFINITE")
        return np.maximum(0, np.expm1(log_predictions))

    def original_feature_effects(self) -> dict[str, float]:
        """Protected diagnostics: mapped standardized coefficients or impurity importances."""
        p = self.preprocessor
        if self.architecture == "state_partial_pooling":
            values = self.state_coefficients[1:1 + len(p.transformed_names)]
        elif hasattr(self.estimator, "coef_"):
            values = np.asarray(self.estimator.coef_)
            if p.pca_loadings is not None:
                values = p.pca_loadings @ values
            elif p.knots is not None:
                # Magnitude of the three basis coefficients, not a monotonicity claim.
                values = np.sqrt(np.sum(values.reshape(-1, 3) ** 2, axis=1))
        else:
            values = self.estimator.feature_importances_
        if self.ensemble_tree is not None:
            mix = float(self.parameters["tree_weight"])
            magnitude = np.abs(values)
            magnitude = magnitude / magnitude.sum() if magnitude.sum() else magnitude
            values = (1 - mix) * magnitude + mix * self.ensemble_tree.feature_importances_
        output = {name: 0.0 for name in self.feature_names}
        for name, value in zip(p.transformed_names, values):
            original = name.removesuffix("__missing")
            output[original] += float(value)
        return output

    def stability_effects(self) -> dict[str, float]:
        """Comparable fold vectors; linear missingness/state effects stay distinct.

        Nonlinear magnitudes describe distribution of feature importance, not
        coefficient signs or stability of the complete fitted response shape.
        """
        if self.architecture in NONLINEAR_STABILITY_ARCHITECTURES:
            return self.original_feature_effects()
        p = self.preprocessor
        if self.architecture == "state_partial_pooling":
            values = self.state_coefficients[1:1 + len(p.transformed_names)]
        else:
            values = np.asarray(self.estimator.coef_)
            if p.pca_loadings is not None:
                values = p.pca_loadings @ values
        effects = {name: float(value) for name, value in zip(p.transformed_names, values)}
        if self.architecture == "state_partial_pooling":
            start = 1 + len(p.transformed_names)
            effects.update({"state:" + state: float(value) for state, value in zip(self.state_levels, self.state_coefficients[start:])})
        return effects

    def fitted_dimension_count(self) -> int:
        """PCA complexity is fitted latent dimension, not its input feature count."""
        p = self.preprocessor
        return int(p.pca_loadings.shape[1]) if p.pca_loadings is not None else len(p.transformed_names)


def fit_model(data: Dataset, candidate: Mapping[str, Any], parameters: Mapping[str, Any], library: Mapping[str, Any]) -> FittedModel:
    data.validate()
    architecture = str(candidate["architecture"])
    names = tuple(candidate["features"])
    _check(bool(names) and set(names) <= set(data.feature_names), "MODEL16_CANDIDATE_FEATURES_INVALID")
    index = tuple(data.feature_names.index(name) for name in names)
    p = FoldPreprocessor(index, data.feature_names, architecture == "baseline_elastic_net", library["preprocessing"], architecture, int(parameters.get("components", 2)))
    p.fit(np.asarray(data.X), data.groups)
    z = p.transform(np.asarray(data.X))
    w, target = location_weights(data.groups), np.log1p(data.y)
    seed = int(library["seed"])
    estimator, levels, state_coefs, ensemble_tree = None, (), None, None
    if architecture in {"ridge", "spline_ridge", "pca_ridge", "simple_log_ensemble"}:
        estimator = Ridge(alpha=float(parameters["alpha"]), solver="svd")
    elif architecture in {"elastic_net", "baseline_elastic_net"}:
        # sklearn rescales sample weights to n; alpha/sum(original weights)
        # exactly reproduces accepted MODEL-13 unnormalized weighted objective.
        estimator = ElasticNet(alpha=float(parameters["alpha"]) / w.sum(), l1_ratio=float(parameters["l1_ratio"]), max_iter=50000, tol=1e-8, selection="cyclic")
    elif architecture in {"random_forest", "extra_trees"}:
        cls = RandomForestRegressor if architecture == "random_forest" else ExtraTreesRegressor
        estimator = cls(n_estimators=96, max_depth=int(parameters["max_depth"]), max_features=float(parameters["max_features"]), min_weight_fraction_leaf=0.08, bootstrap=False, random_state=seed, n_jobs=1)
    elif architecture == "gradient_boosting":
        estimator = GradientBoostingRegressor(n_estimators=int(parameters["n_estimators"]), max_depth=int(parameters["max_depth"]), learning_rate=0.03, min_weight_fraction_leaf=0.08, loss="squared_error", random_state=seed)
    elif architecture == "state_partial_pooling":
        levels = tuple(sorted(set(data.states)))
        design = np.column_stack((np.ones(len(z)), z, *[np.asarray(data.states) == s for s in levels]))
        penalty = np.diag([0.0] + [float(parameters["alpha"])] * z.shape[1] + [float(parameters["state_penalty"])] * len(levels))
        state_coefs = np.linalg.solve(design.T @ (design * w[:, None]) + penalty, design.T @ (target * w))
    else:
        raise ModelingError("MODEL16_ARCHITECTURE_UNDECLARED")
    if estimator is not None:
        with warnings.catch_warnings():
            warnings.simplefilter("error", ConvergenceWarning)
            try:
                estimator.fit(z, target, sample_weight=w)
            except ConvergenceWarning:
                raise ModelingError("MODEL16_SOLVER_NONCONVERGENCE") from None
    if architecture == "simple_log_ensemble":
        ensemble_tree = ExtraTreesRegressor(n_estimators=96, max_depth=int(parameters["max_depth"]), max_features=1.0, min_weight_fraction_leaf=0.08, bootstrap=False, random_state=seed, n_jobs=1)
        ensemble_tree.fit(z, target, sample_weight=w)
    return FittedModel(str(candidate["candidate_id"]), architecture, data.feature_names, p, estimator, dict(parameters), tuple(sorted(set(data.groups))), levels, state_coefs, ensemble_tree)


def _pairs(data: Dataset, predictions: np.ndarray) -> tuple[list[str], np.ndarray, np.ndarray]:
    _check(len(predictions) == len(data.y) and np.all(np.isfinite(predictions)), "MODEL16_METRIC_PREDICTIONS_INVALID")
    names = sorted(set(data.groups))
    group_array = np.asarray(data.groups)
    return names, np.asarray([np.mean(data.y[group_array == g]) for g in names]), np.asarray([np.mean(predictions[group_array == g]) for g in names])


def grouped_metrics(data: Dataset, predictions: Sequence[float]) -> dict[str, Any]:
    p = np.asarray(predictions, dtype=float)
    names, actual, predicted = _pairs(data, p)
    a, b = np.log1p(actual), np.log1p(predicted)
    n = len(names)
    ranks_a, ranks_b = rankdata(actual), rankdata(predicted)
    rank_defined = n >= 2 and np.ptp(ranks_a) > 0 and np.ptp(ranks_b) > 0
    rho = float(np.corrcoef(ranks_a, ranks_b)[0, 1]) if rank_defined else None
    tau = float(kendalltau(actual, predicted).statistic) if rank_defined else None
    variance = float(np.var(b))
    slope = float(np.mean((a - a.mean()) * (b - b.mean())) / variance) if n >= 2 and variance > 1e-20 else None
    intercept = float(a.mean() - slope * b.mean()) if slope is not None else None
    k = max(1, math.ceil(n / 4))
    # Fractional tie membership gives the top k places equal treatment without
    # arbitrary physical IDs determining ranking-overlap claims.
    def top_membership(v: np.ndarray) -> np.ndarray:
        cut = np.sort(v)[-k]
        out = (v > cut).astype(float)
        tied = v == cut
        out[tied] = (k - out.sum()) / tied.sum()
        return out
    overlap = float(np.minimum(top_membership(actual), top_membership(predicted)).sum() / k) if rank_defined else None
    row_w = location_weights(data.groups)
    return {"observations": len(actual) if len(data.y) == n else len(data.y), "physical_locations": n,
            "spearman": rho, "kendall_tau_b": tau,
            "log_rmse": float(np.sqrt(np.mean((a - b) ** 2))),
            "level_mae": float(np.mean(np.abs(actual - predicted))),
            "calibration_slope": slope, "calibration_intercept": intercept,
            "top_quartile_overlap": overlap,
            "location_weighted_row_log_rmse": float(np.sqrt(np.average((np.log1p(data.y) - np.log1p(p)) ** 2, weights=row_w))),
            "location_weighted_row_level_mae": float(np.average(np.abs(data.y - p), weights=row_w)),
            "rank_defined": rank_defined}


def domain_metrics(data: Dataset, predictions: Sequence[float]) -> dict[str, Any]:
    p = np.asarray(predictions)
    result = {"pooled": grouped_metrics(data, p)}
    for state in ("MI", "WI"):
        mask = np.asarray(data.states) == state
        result[state] = grouped_metrics(data.take(mask), p[mask]) if mask.any() else None
    return result


def build_candidates(data: Dataset, library: Mapping[str, Any]) -> list[dict[str, Any]]:
    baseline = list(data.baseline_features)
    priority = [*SPATIAL_TERMS, *library["preprocessing"]["baseline_priority"]]
    baseline.sort(key=lambda name: (priority.index(name) if name in priority else len(priority), name))
    output = []
    for specification in library["candidates"]:
        candidate = dict(specification)
        candidate["features"] = baseline if candidate["feature_set"] == "baseline" else list(data.feature_names)
        candidate["experiment"] = "core_library"
        output.append(candidate)
    families = sorted(set(data.feature_families))
    policy = library["family_experiments"]
    _check(len(families) <= int(policy["maximum_family_count"]), "MODEL16_FAMILY_BOUND_EXCEEDED")
    for family in families:
        family_features = [n for n, f in zip(data.feature_names, data.feature_families) if f == family]
        added = [*baseline, *[n for n in family_features if n not in baseline]]
        removed = [n for n, f in zip(data.feature_names, data.feature_families) if f != family]
        variants = []
        if len(added) > len(baseline):
            variants.append(("add", added))
        if removed:
            variants.append(("remove", removed))
        for operation, features in variants:
            output.append({"candidate_id": f"family_{operation}__{family}", "architecture": "ridge", "features": features, "complexity_rank": 1,
                           "experiment": f"family_{operation}", "family": family, "grid": {"alpha": list(policy["alpha_grid"])}})
    # An exact same-method baseline termset ridge anchors family additions.
    output.append({"candidate_id": "baseline_terms_ridge", "architecture": "ridge", "features": baseline, "complexity_rank": 1,
                   "experiment": "family_reference", "grid": {"alpha": list(policy["alpha_grid"])}})
    _check(len({x["candidate_id"] for x in output}) == len(output), "MODEL16_CANDIDATE_ID_DUPLICATE")
    return output


def _grid(candidate: Mapping[str, Any]) -> list[dict[str, Any]]:
    keys = list(candidate["grid"])
    return [dict(zip(keys, values)) for values in itertools.product(*(candidate["grid"][k] for k in keys))]


def tune_parameters(data: Dataset, candidate: Mapping[str, Any], library: Mapping[str, Any], audit: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    folds = grouped_folds(data.groups, data.states, int(library["inner_folds"]), int(library["seed"]) + 1)
    scored = []
    for grid_index, parameters in enumerate(_grid(candidate)):
        predictions = np.full(len(data.y), np.nan)
        active = []
        for fold in range(int(library["inner_folds"])):
            train, test = data.take(folds != fold), data.take(folds == fold)
            _check(not set(train.groups) & set(test.groups), "MODEL16_INNER_LOCATION_LEAKAGE")
            fitted = fit_model(train, candidate, parameters, library)
            predictions[folds == fold] = fitted.predict(test.X, test.states, test.feature_names)
            active.append(fitted.fitted_dimension_count())
            if audit is not None and grid_index == 0:
                audit.append({"stage": "inner", "candidate_id": candidate["candidate_id"], "fold": fold,
                              "train_groups": sorted(set(train.groups)), "test_groups": sorted(set(test.groups)),
                              "preprocessing_training_groups": list(fitted.train_groups)})
        metrics = grouped_metrics(data, predictions)
        if candidate["architecture"] == "baseline_elastic_net":
            order = (-(metrics["spearman"] if metrics["spearman"] is not None else -1.0), metrics["log_rmse"], grid_index)
        else:
            order = (metrics["log_rmse"], float(np.mean(active)), grid_index)
        scored.append((order, parameters))
    _check(bool(scored), "MODEL16_EMPTY_PARAMETER_GRID")
    return dict(min(scored, key=lambda item: item[0])[1])


def _delta(left: Mapping[str, Any], right: Mapping[str, Any]) -> dict[str, float | None]:
    return {key: float(left[key] - right[key]) if left.get(key) is not None and right.get(key) is not None else None for key in METRICS}


def _stability(models: Sequence[FittedModel], features: Sequence[str]) -> dict[str, Any]:
    _check(len(models) >= 2 and len({model.architecture for model in models}) == 1, "MODEL16_STABILITY_FOLD_MODELS_INVALID")
    effects = [model.original_feature_effects() for model in models]
    signed = models[0].architecture not in NONLINEAR_STABILITY_ARCHITECTURES
    frequencies, signs, deviations = {}, {}, {}
    for name in features:
        values = np.asarray([mapping[name] for mapping in effects])
        active = values[np.abs(values) > 1e-8]
        frequencies[name] = len(active) / len(values)
        signs[name] = max(float(np.mean(active > 0)), float(np.mean(active < 0))) if len(active) else 0.0
        deviations[name] = float(np.std(values))
    comparable = [model.stability_effects() for model in models]
    names = sorted(set().union(*(mapping.keys() for mapping in comparable)))
    vectors = np.asarray([[mapping.get(name, 0.0) for name in names] for mapping in comparable], dtype=float)
    _check(np.all(np.isfinite(vectors)), "MODEL16_STABILITY_EFFECT_NONFINITE")
    vectors[np.abs(vectors) <= 1e-8] = 0.0
    if not signed:
        vectors = np.abs(vectors)
    norms = np.sum(np.abs(vectors), axis=1)
    normalized = np.divide(vectors, norms[:, None], out=np.zeros_like(vectors), where=norms[:, None] > 0)
    agreements, activity = [], []
    for left, right in itertools.combinations(range(len(models)), 2):
        active_left, active_right = np.abs(vectors[left]) > 0, np.abs(vectors[right]) > 0
        union = np.count_nonzero(active_left | active_right)
        activity.append(float(np.count_nonzero(active_left & active_right) / union) if union else 0.0)
        # Zero-information folds cannot earn stability by sharing an empty fit.
        if norms[left] == 0 or norms[right] == 0:
            agreements.append(0.0)
        else:
            agreements.append(float(np.clip(1.0 - 0.5 * np.sum(np.abs(normalized[left] - normalized[right])), 0.0, 1.0)))
    score = float(np.mean(agreements))
    return {"selection_frequency": frequencies, "dominant_sign_agreement": signs if signed else None, "effect_standard_deviation": deviations,
            "score": score,
            "score_definition": "mean pairwise shared signed L1-normalized effect mass" if signed else "mean pairwise shared L1-normalized nonnegative importance mass",
            "pairwise_agreement": agreements, "mean_activity_jaccard": float(np.mean(activity)),
            "fold_effect_l1_norms": [float(value) for value in norms],
            "effect_kind": "signed standardized linear effects including separate missingness/state effects" if signed else "spline basis norms, tree impurity importances, or ensemble mixture importances",
            "sign_diagnostic_applicable": signed,
            "fold_exclusions": [dict(model.preprocessor.excluded) for model in models]}


def _omission_sensitivity(data: Dataset, predictions: np.ndarray, baseline: np.ndarray) -> dict[str, Any]:
    names, actual, predicted = _pairs(data, predictions)
    worst = names[int(np.argmax(np.abs(np.log1p(actual) - np.log1p(predicted))))]
    omitted = np.asarray(data.groups) != worst
    result: dict[str, Any] = {"worst_error_location_removed": {"candidate": domain_metrics(data.take(omitted), predictions[omitted]),
                              "baseline": domain_metrics(data.take(omitted), baseline[omitted])},
                              "worst_location": worst, "role": "fixed OOF diagnostic; no target-conditioned refit"}
    each_location, error_ratios, rank_deltas = [], [], []
    for group in names:
        keep = np.asarray(data.groups) != group
        candidate_metrics = grouped_metrics(data.take(keep), predictions[keep])
        baseline_metrics = grouped_metrics(data.take(keep), baseline[keep])
        base_error, candidate_error = baseline_metrics["log_rmse"], candidate_metrics["log_rmse"]
        error_ratio = candidate_error / base_error if base_error > 0 else (1.0 if candidate_error == 0 else None)
        rank_delta = candidate_metrics["spearman"] - baseline_metrics["spearman"] if candidate_metrics["spearman"] is not None and baseline_metrics["spearman"] is not None else None
        error_ratios.append(error_ratio)
        rank_deltas.append(rank_delta)
        each_location.append({"omitted_location": group, "candidate": candidate_metrics, "baseline": baseline_metrics,
                              "error_ratio": error_ratio, "rank_delta": rank_delta})
    result["each_location_removed"] = each_location
    result["all_location_omission_summary"] = {
        "evaluated_locations": len(each_location),
        "maximum_error_ratio": max(error_ratios) if all(value is not None for value in error_ratios) else None,
        "minimum_rank_delta": min(rank_deltas) if all(value is not None for value in rank_deltas) else None,
    }
    if data.markets:
        market_results = []
        for market in sorted(set(data.markets)):
            keep = np.asarray(data.markets) != market
            if len(set(np.asarray(data.groups)[keep])) >= 5:
                market_results.append({"market": market, "candidate": domain_metrics(data.take(keep), predictions[keep]), "baseline": domain_metrics(data.take(keep), baseline[keep])})
        result["each_market_removed"] = market_results
    return result


@dataclass
class DevelopmentResult:
    diagnostics: list[dict[str, Any]]
    selection: dict[str, Any]
    frozen_models: dict[str, FittedModel]
    oof_predictions: dict[str, np.ndarray]
    fold_audit: list[dict[str, Any]]
    family_contributions: list[dict[str, Any]]
    library: Mapping[str, Any]
    development_groups: tuple[str, ...]
    development_fingerprint: str


def _rank(metrics: Mapping[str, Any]) -> float:
    return float(metrics["spearman"]) if metrics.get("spearman") is not None else -1.0


def _not_collapsed(candidate: Mapping[str, Any], baseline: Mapping[str, Any], policy: Mapping[str, Any]) -> bool:
    return (candidate["log_rmse"] <= baseline["log_rmse"] * float(policy["maximum_state_error_ratio"])
            and _rank(candidate) >= _rank(baseline) - float(policy["maximum_state_rank_deterioration"]))


def _qualify(item: Mapping[str, Any], baseline: Mapping[str, Any], all_items: Mapping[str, Any], policy: Mapping[str, Any]) -> list[str]:
    rejected = []
    c, b = item["aggregate_oof"]["pooled"], baseline["aggregate_oof"]["pooled"]
    rank_route = _rank(c) >= _rank(b) + policy["minimum_rank_improvement"] and c["log_rmse"] <= b["log_rmse"] * policy["rank_route_max_error_ratio"]
    error_route = c["log_rmse"] <= b["log_rmse"] * policy["error_route_max_error_ratio"] and _rank(c) >= _rank(b) + policy["error_route_min_rank_delta"]
    if not (rank_route or error_route):
        rejected.append("NO_MATERIAL_POOLED_IMPROVEMENT")
    for state in ("MI", "WI"):
        if not _not_collapsed(item["aggregate_oof"][state], baseline["aggregate_oof"][state], policy):
            rejected.append(f"{state}_DETERIORATION")
    favorable = [fold["pooled"]["log_rmse"] < 0 or (fold["pooled"]["spearman"] is not None and fold["pooled"]["spearman"] > 0) for fold in item["paired_fold_differences"]]
    if np.mean(favorable) < policy["minimum_favorable_fold_fraction"]:
        rejected.append("IMPROVEMENT_NOT_REPEATABLE_ACROSS_FOLDS")
    if item["stability"]["score"] < policy["minimum_stability"]:
        rejected.append("LOW_FEATURE_STABILITY")
    sensitivity = item["sensitivity"]["worst_error_location_removed"]
    sc, sb = sensitivity["candidate"]["pooled"], sensitivity["baseline"]["pooled"]
    if sc["log_rmse"] > sb["log_rmse"] * policy["maximum_location_removed_error_ratio"] or _rank(sc) < _rank(sb) + policy["error_route_min_rank_delta"]:
        rejected.append("WORST_LOCATION_SENSITIVITY")
    all_locations = item["sensitivity"]["all_location_omission_summary"]
    if (all_locations["maximum_error_ratio"] is None or all_locations["minimum_rank_delta"] is None
            or all_locations["maximum_error_ratio"] > policy["maximum_any_location_removed_error_ratio"]
            or all_locations["minimum_rank_delta"] < policy["minimum_any_location_removed_rank_delta"]):
        rejected.append("ANY_LOCATION_SENSITIVITY")
    for market in item["sensitivity"].get("each_market_removed", []):
        if market["candidate"]["pooled"]["log_rmse"] > market["baseline"]["pooled"]["log_rmse"] * policy["maximum_market_removed_error_ratio"]:
            rejected.append("MARKET_CONCENTRATION_SENSITIVITY")
            break
    if item["architecture"] == "simple_log_ensemble":
        for constituent in ("ridge", "extra_trees"):
            other = all_items.get(constituent)
            if other is None or other.get("status") != "EVALUATED":
                rejected.append("ENSEMBLE_CONSTITUENT_UNAVAILABLE")
                continue
            if c["log_rmse"] > other["aggregate_oof"]["pooled"]["log_rmse"] * policy["maximum_ensemble_constituent_error_ratio"]:
                rejected.append("ENSEMBLE_NOT_BETTER_THAN_CONSTITUENTS")
            improved = [left["pooled"]["log_rmse"] < right["pooled"]["log_rmse"] for left, right in zip(item["fold_metrics"], other["fold_metrics"])]
            if np.mean(improved) < policy["ensemble_minimum_favorable_fold_fraction"]:
                rejected.append("ENSEMBLE_GAIN_INCONSISTENT")
    return sorted(set(rejected))


def _candidate_family_robustness(data: Dataset, specification: Mapping[str, Any], library: Mapping[str, Any], folds: np.ndarray,
                                 baseline: Mapping[str, Any], audit: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Predeclared same-architecture incremental-family-out nested diagnostics.

    Applied only to provisional qualifiers, before any holdout/final refit.
    The family and parameter menus are fixed; this does not invent variants from
    held-out evidence or use an outer fold to tune a predictor for that fold.
    """
    features = list(specification["features"])
    families = sorted({family for name, family in zip(data.feature_names, data.feature_families) if name in features})
    outputs = []
    for family in families:
        incremental = {name for name, feature_family in zip(data.feature_names, data.feature_families)
                       if name in features and feature_family == family and name not in data.baseline_features}
        if not incremental:
            outputs.append({"family": family, "status": "BASELINE_ONLY_FAMILY", "passes": True,
                            "role": "accepted baseline retained; full-family removal reported separately"})
            continue
        reduced = [name for name in features if name not in incremental]
        ablation = {**specification, "candidate_id": str(specification["candidate_id"]) + "__robustness_remove__" + family, "features": reduced}
        predictions = np.full(len(data.y), np.nan)
        try:
            for fold in range(int(library["outer_folds"])):
                train, test = data.take(folds != fold), data.take(folds == fold)
                parameters = tune_parameters(train, ablation, library, audit)
                model = fit_model(train, ablation, parameters, library)
                predictions[folds == fold] = model.predict(test.X, test.states, test.feature_names)
            metrics = domain_metrics(data, predictions)
            passes = metrics["pooled"]["log_rmse"] <= baseline["aggregate_oof"]["pooled"]["log_rmse"] * library["selection"]["maximum_family_removed_error_ratio"]
            passes = passes and all(_not_collapsed(metrics[state], baseline["aggregate_oof"][state], library["selection"]) for state in ("MI", "WI"))
            outputs.append({"candidate_id": ablation["candidate_id"], "family": family, "status": "EVALUATED", "aggregate_oof": metrics, "passes": bool(passes),
                            "role": "same-architecture incremental-source-dependence diagnostic; baseline features retained; never a new challenger"})
        except ModelingError as exc:
            outputs.append({"candidate_id": ablation["candidate_id"], "family": family, "status": "UNAVAILABLE", "reason": str(exc), "passes": False})
    return outputs


def run_development(data: Dataset, library: Mapping[str, Any] | None = None, progress: Callable[[str], None] | None = None) -> DevelopmentResult:
    """Never pass held-out targets. Caller freezes returned models before holdout IO.

    Progress callbacks receive public candidate IDs only. Do not log result objects.
    A baseline failure aborts; a bounded alternative failure is explicitly recorded.
    """
    data.validate(development=True)
    library = dict(library or load_library())
    candidates = build_candidates(data, library)
    folds = grouped_folds(data.groups, data.states, int(library["outer_folds"]), int(library["seed"]))
    diagnostics, audit, predictions_by_id = [], [], {}
    for candidate in candidates:
        candidate_id = candidate["candidate_id"]
        if progress:
            progress(str(candidate_id))
        predictions = np.full(len(data.y), np.nan)
        models, selected_parameters, fold_metrics = [], [], []
        try:
            for fold in range(int(library["outer_folds"])):
                train, test = data.take(folds != fold), data.take(folds == fold)
                _check(not set(train.groups) & set(test.groups), "MODEL16_OUTER_LOCATION_LEAKAGE")
                parameters = tune_parameters(train, candidate, library, audit)
                fitted = fit_model(train, candidate, parameters, library)
                test_predictions = fitted.predict(test.X, test.states, test.feature_names)
                predictions[folds == fold] = test_predictions
                models.append(fitted)
                selected_parameters.append(parameters)
                fold_metrics.append(domain_metrics(test, test_predictions))
                audit.append({"stage": "outer", "candidate_id": candidate_id, "fold": fold, "train_groups": sorted(set(train.groups)), "test_groups": sorted(set(test.groups)), "preprocessing_training_groups": list(fitted.train_groups)})
            item = {"candidate_id": candidate_id, "architecture": candidate["architecture"], "experiment": candidate["experiment"],
                    "family": candidate.get("family"), "status": "EVALUATED", "features": list(candidate["features"]),
                    "complexity_rank": candidate["complexity_rank"], "aggregate_oof": domain_metrics(data, predictions),
                    "fold_metrics": fold_metrics, "outer_parameters": selected_parameters, "stability": _stability(models, data.feature_names)}
            predictions_by_id[candidate_id] = predictions
        except ModelingError as exc:
            if candidate_id == BASELINE_ID:
                raise
            item = {"candidate_id": candidate_id, "architecture": candidate["architecture"], "experiment": candidate["experiment"],
                    "family": candidate.get("family"), "status": "UNAVAILABLE", "reason": str(exc), "features": list(candidate["features"])}
        diagnostics.append(item)
    by_id = {item["candidate_id"]: item for item in diagnostics}
    baseline = by_id[BASELINE_ID]
    family_contributions = []
    for item in diagnostics:
        if item["status"] != "EVALUATED":
            continue
        item["paired_fold_differences"] = [{domain: _delta(fold[domain], base[domain]) for domain in ("pooled", "MI", "WI")} for fold, base in zip(item["fold_metrics"], baseline["fold_metrics"])]
        item["sensitivity"] = _omission_sensitivity(data, predictions_by_id[item["candidate_id"]], predictions_by_id[BASELINE_ID])
        if item["experiment"] in {"family_add", "family_remove"}:
            reference = by_id["baseline_terms_ridge"] if item["experiment"] == "family_add" else by_id["ridge"]
            if reference["status"] == "EVALUATED":
                family_contributions.append({"family": item["family"], "operation": item["experiment"], "candidate_id": item["candidate_id"],
                                             "reference_id": reference["candidate_id"], "differences": {domain: _delta(item["aggregate_oof"][domain], reference["aggregate_oof"][domain]) for domain in ("pooled", "MI", "WI")},
                                             "paired_fold_differences": [{domain: _delta(f[domain], r[domain]) for domain in ("pooled", "MI", "WI")} for f, r in zip(item["fold_metrics"], reference["fold_metrics"])],
                                             "interpretation": "addition lower error is gain; removal higher error is contribution; development diagnostics only"})
    qualifiers = []
    for item in diagnostics:
        if item["status"] != "EVALUATED" or item["candidate_id"] == BASELINE_ID:
            continue
        item["qualification_rejections"] = _qualify(item, baseline, by_id, library["selection"])
        if not item["qualification_rejections"]:
            specification = next(c for c in candidates if c["candidate_id"] == item["candidate_id"])
            if progress:
                progress(str(item["candidate_id"]) + "__family_robustness")
            item["same_architecture_family_robustness"] = _candidate_family_robustness(data, specification, library, folds, baseline, audit)
            if all(result["passes"] for result in item["same_architecture_family_robustness"]):
                qualifiers.append(item)
            else:
                item["qualification_rejections"].append("SOURCE_FAMILY_DEPENDENCE")
    qualifiers.sort(key=lambda item: (item["aggregate_oof"]["pooled"]["log_rmse"], -_rank(item["aggregate_oof"]["pooled"]), item["complexity_rank"], item["candidate_id"]))
    selected_id = qualifiers[0]["candidate_id"] if qualifiers else None
    frozen = {}
    for candidate_id in (BASELINE_ID, selected_id):
        if candidate_id is not None:
            specification = next(c for c in candidates if c["candidate_id"] == candidate_id)
            parameters = tune_parameters(data, specification, library, audit)
            frozen[candidate_id] = fit_model(data, specification, parameters, library)
    fingerprint = hashlib.sha256(np.asarray(data.X, dtype="<f8").tobytes() + np.asarray(data.y, dtype="<f8").tobytes() + json.dumps([data.groups, data.states, data.years, data.feature_names], separators=(",", ":")).encode()).hexdigest()
    return DevelopmentResult(diagnostics, {"baseline_id": BASELINE_ID, "challenger_id": selected_id,
                             "qualifying_candidates": [q["candidate_id"] for q in qualifiers],
                             "decision": "CHALLENGER_FROZEN" if selected_id else "NO_CREDIBLE_CHALLENGER",
                             "generation": 1, "post_holdout_retuning_allowed": False}, frozen, predictions_by_id, audit, family_contributions, library, tuple(sorted(set(data.groups))), fingerprint)


def evaluate_frozen(result: DevelopmentResult, data: Dataset, *, role: str,
                    all_seedpoint_groups: Sequence[str] | None = None) -> dict[str, Any]:
    """Pure bounded evaluator; caller enforces durable one-open role ledger.

    Validation deliberately happens before prediction. The object is not refitted.
    Temporal observations can match development locations: reported explicitly.
    """
    data.validate()
    _check(role in {"temporal_2026", "pursued_sites"}, "MODEL16_HOLDOUT_ROLE_INVALID")
    if role == "temporal_2026":
        _check(set(data.years) == {2026} and set(data.evidence_classes) == {"SEED_POINT"}, "MODEL16_TEMPORAL_COHORT_INVALID")
    else:
        _check(set(data.evidence_classes) == {"PURSUED_SITE"}, "MODEL16_PURSUED_COHORT_INVALID")
        _check(all_seedpoint_groups is not None and set(result.development_groups) <= set(all_seedpoint_groups), "MODEL16_PURSUED_SEED_IDENTITY_MEMBERSHIP_REQUIRED")
    _check(len(result.frozen_models) <= 2 and BASELINE_ID in result.frozen_models, "MODEL16_FREEZE_INVALID")
    match = np.asarray([group in set(result.development_groups) for group in data.groups])
    subsets = {"all": np.ones(len(data.y), dtype=bool), "independent_development_location": ~match, "matched_development_location": match}
    if role == "pursued_sites":
        seed_match = np.asarray([group in set(all_seedpoint_groups) for group in data.groups])
        subsets.update({"independent_of_all_seedpoints": ~seed_match, "matched_seedpoint_location": seed_match})
    output: dict[str, Any] = {"role": role, "generation": 1, "models": {}, "refit": False,
                              "independence_note": "matched physical locations are not independent external evidence"}
    for candidate_id, model in result.frozen_models.items():
        _check(data.feature_names == model.feature_names, "MODEL16_HOLDOUT_FEATURE_CATALOG_CHANGED")
        predicted = model.predict(data.X, data.states, data.feature_names)
        output["models"][candidate_id] = {"subsets": {name: domain_metrics(data.take(mask), predicted[mask]) if mask.any() else None for name, mask in subsets.items()}, "predictions": predicted}
    return output
