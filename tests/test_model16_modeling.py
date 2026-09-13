"""Synthetic-only invariants for the bounded MODEL-16 modeling contract."""

from __future__ import annotations

from dataclasses import replace
import copy
import math
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from sprouts_customer_geography.model13.modeling import fit_regularized
from sprouts_customer_geography.model16.modeling import (
    BASELINE_ID, Dataset, FoldPreprocessor, ModelingError, SPATIAL_TERMS,
    build_candidates, domain_metrics, evaluate_frozen, fit_model, grouped_folds,
    grouped_metrics, load_library, location_weights, run_development,
    _omission_sensitivity, _stability, tune_parameters,
)


def synthetic_dataset(locations_per_state: int = 12) -> Dataset:
    rng = np.random.default_rng(1616)
    names = (*SPATIAL_TERMS, "public_workplace_jobs", "public_road_exposure", "public_housing_growth")
    families = ("households", "households", "households", "employment", "access", "growth")
    rows, target, groups, states, years, classes, markets = [], [], [], [], [], [], []
    for state_index, state in enumerate(("MI", "WI")):
        for group in range(locations_per_state):
            values = rng.normal(size=len(names))
            for year in (2024, 2025):
                x = values + rng.normal(scale=0.03, size=len(names))
                rows.append(x)
                target.append(math.expm1(10 + 0.25 * x[0] + 0.12 * x[3] + 0.02 * state_index + 0.01 * (year - 2024)))
                groups.append(f"SYNTHETIC_{state}_{group}")
                states.append(state)
                years.append(year)
                classes.append("SEED_POINT")
                markets.append(f"SYNTHETIC_MARKET_{state}_{group % 3}")
    return Dataset(np.asarray(rows), np.asarray(target), tuple(groups), tuple(states), tuple(years), tuple(classes), tuple(names), families, tuple(SPATIAL_TERMS), tuple(markets))


def short_library() -> dict:
    library = copy.deepcopy(load_library())
    library["outer_folds"], library["inner_folds"] = 3, 2
    library["candidates"] = [candidate for candidate in library["candidates"] if candidate["candidate_id"] in {BASELINE_ID, "ridge"}]
    for candidate in library["candidates"]:
        candidate["grid"] = {key: [values[0]] for key, values in candidate["grid"].items()}
    library["family_experiments"]["alpha_grid"] = [1.0]
    return library


class Model16ModelingTests(unittest.TestCase):
    @staticmethod
    def stability_model(architecture, effects):
        return SimpleNamespace(architecture=architecture, preprocessor=SimpleNamespace(excluded={}),
                               original_feature_effects=lambda: dict(effects), stability_effects=lambda: dict(effects))

    def test_dense_linear_sign_changes_cannot_pass_stability_by_activation(self):
        first = self.stability_model("ridge", {"a": 1.0, "b": 1.0, "c": 1.0, "d": 1.0})
        flipped = self.stability_model("ridge", {"a": 1.0, "b": 1.0, "c": -1.0, "d": -1.0})
        result = _stability([first, flipped], ("a", "b", "c", "d"))
        self.assertEqual(set(result["selection_frequency"].values()), {1.0})
        self.assertAlmostEqual(result["score"], 0.5)
        self.assertLess(result["score"], load_library()["selection"]["minimum_stability"])

    def test_tree_and_spline_importance_switches_reduce_stability(self):
        for architecture in ("extra_trees", "random_forest", "gradient_boosting", "spline_ridge", "simple_log_ensemble"):
            models = [self.stability_model(architecture, {"a": 0.99, "b": 0.01}),
                      self.stability_model(architecture, {"a": 0.01, "b": 0.99})]
            result = _stability(models, ("a", "b"))
            self.assertAlmostEqual(result["score"], 0.02)
            self.assertIsNone(result["dominant_sign_agreement"])
            self.assertFalse(result["sign_diagnostic_applicable"])

    def test_stability_normalization_preserves_agreeing_relative_effects(self):
        models = [self.stability_model("ridge", {"a": 1.0, "b": -2.0}),
                  self.stability_model("ridge", {"a": 3.0, "b": -6.0})]
        result = _stability(models, ("a", "b"))
        self.assertAlmostEqual(result["score"], 1)
        self.assertAlmostEqual(result["mean_activity_jaccard"], 1)
        self.assertEqual(result["fold_effect_l1_norms"], [3.0, 9.0])

    def test_zero_or_disjoint_active_effects_do_not_claim_stability(self):
        for effects in (({"a": 0.0, "b": 0.0}, {"a": 0.0, "b": 0.0}),
                        ({"a": 1.0, "b": 0.0}, {"a": 0.0, "b": 1.0})):
            result = _stability([self.stability_model("lasso", item) for item in effects], ("a", "b"))
            self.assertEqual(result["score"], 0)
            self.assertEqual(result["mean_activity_jaccard"], 0)

    def test_pca_tie_break_uses_fitted_latent_dimension(self):
        data, library = synthetic_dataset(), short_library()
        candidate = {"candidate_id": "SYNTHETIC_PCA", "architecture": "pca_ridge", "grid": {"components": [6, 2], "alpha": [1.0]}}
        def fitted(train, candidate, parameters, library):
            return SimpleNamespace(preprocessor=SimpleNamespace(transformed_names=tuple(range(50))),
                                   fitted_dimension_count=lambda: min(parameters["components"], 4),
                                   predict=lambda x, states, names: np.full(len(x), 100000.0))
        with patch("sprouts_customer_geography.model16.modeling.fit_model", fitted):
            selected = tune_parameters(data, candidate, library)
        self.assertEqual(selected["components"], 2)
        actual_candidate = next(c for c in build_candidates(data, load_library()) if c["candidate_id"] == "pca_ridge")
        actual = fit_model(data, actual_candidate, {"alpha": 1.0, "components": 6}, load_library())
        self.assertEqual(actual.fitted_dimension_count(), actual.preprocessor.pca_loadings.shape[1])
        self.assertLess(actual.fitted_dimension_count(), len(actual.preprocessor.transformed_names))

    def test_all_location_omission_detects_one_favorable_location_dependence(self):
        data = synthetic_dataset()
        favorable = data.groups[0]
        mask = np.asarray(data.groups) == favorable
        baseline = data.y * 1.03
        baseline[mask] = data.y[mask] * 3
        candidate = data.y * 1.06
        candidate[mask] = data.y[mask]
        sensitivity = _omission_sensitivity(data, candidate, baseline)
        self.assertNotEqual(sensitivity["worst_location"], favorable)
        worst = sensitivity["worst_error_location_removed"]
        self.assertLess(worst["candidate"]["pooled"]["log_rmse"], worst["baseline"]["pooled"]["log_rmse"])
        summary = sensitivity["all_location_omission_summary"]
        self.assertEqual(summary["evaluated_locations"], len(set(data.groups)))
        self.assertGreater(summary["maximum_error_ratio"], load_library()["selection"]["maximum_any_location_removed_error_ratio"])
        self.assertEqual(set(summary), {"evaluated_locations", "maximum_error_ratio", "minimum_rank_delta"})
        self.assertEqual(len(sensitivity["each_location_removed"]), len(set(data.groups)))

    def test_all_location_undefined_error_or_rank_is_explicit(self):
        data = synthetic_dataset()
        perfect_baseline = _omission_sensitivity(data, data.y * 1.01, data.y)
        self.assertIsNone(perfect_baseline["all_location_omission_summary"]["maximum_error_ratio"])
        constant = _omission_sensitivity(data, np.ones(len(data.y)), data.y)
        self.assertIsNone(constant["all_location_omission_summary"]["minimum_rank_delta"])

    def test_location_weight_preserves_every_year_and_totals_one(self):
        groups = ("a", "a", "b", "c", "c", "c")
        weights = location_weights(groups)
        self.assertEqual(len(weights), 6)
        for group in set(groups):
            self.assertAlmostEqual(float(weights[np.asarray(groups) == group].sum()), 1.0)

    def test_folds_keep_physical_locations_together_and_are_row_order_invariant(self):
        data = synthetic_dataset()
        folds = grouped_folds(data.groups, data.states, 3, 16)
        order = np.random.default_rng(8).permutation(len(data.y))
        reordered = data.take(order)
        reordered_folds = grouped_folds(reordered.groups, reordered.states, 3, 16)
        np.testing.assert_array_equal(folds[order], reordered_folds)
        for group in set(data.groups):
            self.assertEqual(len(set(folds[np.asarray(data.groups) == group])), 1)
        for state in ("MI", "WI"):
            self.assertEqual(set(folds[np.asarray(data.states) == state]), {0, 1, 2})

    def test_cross_state_location_fails_closed(self):
        with self.assertRaisesRegex(ModelingError, "CROSS_STATE"):
            grouped_folds(("a", "a", "b", "c"), ("MI", "WI", "MI", "WI"), 2, 1)

    def test_insufficient_state_groups_fails_closed(self):
        with self.assertRaisesRegex(ModelingError, "SUPPORT_INSUFFICIENT"):
            grouped_folds(("a", "b", "c"), ("MI", "MI", "WI"), 2, 1)

    def test_development_rejects_temporal_and_pursued_targets(self):
        data = synthetic_dataset()
        with self.assertRaisesRegex(ModelingError, "HOLDOUT_IN_DEVELOPMENT"):
            replace(data, years=(2026,) * len(data.y)).validate(development=True)
        with self.assertRaisesRegex(ModelingError, "PURSUED_IN_DEVELOPMENT"):
            replace(data, evidence_classes=("PURSUED_SITE",) * len(data.y)).validate(development=True)

    def test_missing_dimensions_and_invalid_targets_fail_closed(self):
        data = synthetic_dataset()
        with self.assertRaisesRegex(ModelingError, "DIMENSION_MISMATCH"):
            replace(data, X=data.X[:, :-1]).validate()
        with self.assertRaisesRegex(ModelingError, "TARGET_INVALID"):
            replace(data, y=np.zeros(len(data.y))).validate()
        x = data.X.copy()
        x[0, 0] = np.inf
        with self.assertRaisesRegex(ModelingError, "INFINITE_FEATURE"):
            replace(data, X=x).validate()

    def test_imputation_and_scaling_are_training_local_with_missing_indicator(self):
        x = np.asarray([[1.0, 4.0], [np.nan, 8.0], [3.0, 6.0], [5.0, 12.0]])
        library = load_library()
        processor = FoldPreprocessor((0, 1), ("first", "second"), False, library["preprocessing"], "ridge")
        processor.fit(x, ("a", "a", "b", "c"))
        medians, means = processor.medians.copy(), processor.means.copy()
        transformed = processor.transform(np.asarray([[np.nan, 999999.0]]))
        self.assertTrue(np.isfinite(transformed).all())
        np.testing.assert_array_equal(processor.medians, medians)
        np.testing.assert_array_equal(processor.means, means)
        self.assertIn("first__missing", processor.transformed_names)
        self.assertNotEqual(processor.medians[0], 0)

    def test_all_missing_and_constant_features_are_explicitly_excluded(self):
        x = np.asarray([[1.0, np.nan, 5.0], [2.0, np.nan, 5.0], [3.0, np.nan, 5.0]])
        p = FoldPreprocessor((0, 1, 2), ("vary", "missing", "constant"), False, load_library()["preprocessing"], "ridge").fit(x, ("a", "b", "c"))
        self.assertEqual(p.excluded, {"missing": "ALL_MISSING_TRAIN", "constant": "CONSTANT_TRAIN"})
        np.testing.assert_equal(p.retained_input, (0,))

    def test_baseline_never_silently_imputes_prediction(self):
        x = np.asarray([[1.0, 4.0], [2.0, 8.0], [3.0, 6.0]])
        p = FoldPreprocessor((0, 1), ("first", "second"), True, load_library()["preprocessing"], "baseline_elastic_net").fit(x, ("a", "b", "c"))
        with self.assertRaisesRegex(ModelingError, "BASELINE_RETAINED_FEATURE_MISSING"):
            p.transform(np.asarray([[np.nan, 7.0]]))

    def test_weighted_preprocessing_pca_and_linear_fit_ignore_duplicate_inflation(self):
        data = synthetic_dataset()
        repeated = data.take(np.r_[np.arange(len(data.y)), [0, 1, 0, 1]])
        library = load_library()
        for candidate_id in ("ridge", "pca_ridge", "spline_ridge", "state_partial_pooling"):
            specification = next(c for c in build_candidates(data, library) if c["candidate_id"] == candidate_id)
            parameters = {key: values[0] for key, values in specification["grid"].items()}
            original = fit_model(data, specification, parameters, library)
            duplicate = fit_model(repeated, specification, parameters, library)
            np.testing.assert_allclose(original.preprocessor.means, duplicate.preprocessor.means, atol=1e-12)
            np.testing.assert_allclose(original.predict(data.X, data.states), duplicate.predict(data.X, data.states), rtol=1e-8)

    def test_clean_baseline_reproduces_model13_weighted_objective(self):
        data = synthetic_dataset()
        library = load_library()
        candidate = build_candidates(data, library)[0]
        parameters = {"alpha": 0.1, "l1_ratio": 0.5}
        model = fit_model(data, candidate, parameters, library)
        rows = [{"successor_physical_location_id": group, "isolated_sales": target,
                 "features": dict(zip(data.feature_names, x))} for group, target, x in zip(data.groups, data.y, data.X)]
        accepted = fit_regularized(rows, "SYNTHETIC_BASELINE", "elastic_net", list(SPATIAL_TERMS), **parameters)
        np.testing.assert_allclose(model.predict(data.X, data.states), [accepted.predict(row) for row in rows], rtol=1e-5)

    def test_each_model_family_fits_and_predicts_deterministically(self):
        data, library = synthetic_dataset(), load_library()
        for specification in build_candidates(data, library)[:len(library["candidates"])]:
            with self.subTest(candidate=specification["candidate_id"]):
                parameters = {key: values[0] for key, values in specification["grid"].items()}
                first = fit_model(data, specification, parameters, library)
                second = fit_model(data, specification, parameters, library)
                predictions = first.predict(data.X, data.states, data.feature_names)
                self.assertTrue(np.all(np.isfinite(predictions)))
                np.testing.assert_array_equal(predictions, second.predict(data.X, data.states, data.feature_names))

    def test_prediction_column_order_cannot_change_silently(self):
        data, library = synthetic_dataset(), load_library()
        specification = build_candidates(data, library)[1]
        model = fit_model(data, specification, {"alpha": 1.0}, library)
        with self.assertRaisesRegex(ModelingError, "ORDER_MISMATCH"):
            model.predict(data.X, data.states, tuple(reversed(data.feature_names)))

    def test_metrics_keep_location_and_within_location_errors_distinct(self):
        data = synthetic_dataset()
        perfect = grouped_metrics(data, data.y)
        self.assertAlmostEqual(perfect["spearman"], 1)
        self.assertAlmostEqual(perfect["calibration_slope"], 1)
        self.assertAlmostEqual(perfect["calibration_intercept"], 0)
        self.assertAlmostEqual(perfect["top_quartile_overlap"], 1)
        pred = data.y.copy()
        pred[0] += 1
        pred[1] -= 1
        metrics = grouped_metrics(data, pred)
        self.assertAlmostEqual(metrics["level_mae"], 0)
        self.assertGreater(metrics["location_weighted_row_level_mae"], 0)
        constant = grouped_metrics(data, np.ones(len(data.y)))
        self.assertIsNone(constant["spearman"])
        self.assertFalse(constant["rank_defined"])

    def test_family_comparisons_have_same_method_reference(self):
        data = synthetic_dataset()
        candidates = build_candidates(data, load_library())
        self.assertTrue(any(c["candidate_id"] == "family_add__employment" for c in candidates))
        self.assertTrue(any(c["candidate_id"] == "family_remove__households" for c in candidates))
        self.assertTrue(any(c["candidate_id"] == "baseline_terms_ridge" for c in candidates))
        self.assertTrue(all(c["architecture"] == "ridge" for c in candidates if c["experiment"].startswith("family_")))

    def test_nested_run_audits_preprocessing_and_repeats_exactly(self):
        data, library = synthetic_dataset(), short_library()
        first = run_development(data, library)
        second = run_development(data, library)
        self.assertEqual(first.selection, second.selection)
        self.assertEqual(first.development_fingerprint, second.development_fingerprint)
        self.assertEqual(len(first.frozen_models) <= 2, True)
        self.assertIn(BASELINE_ID, first.frozen_models)
        for key in first.oof_predictions:
            np.testing.assert_array_equal(first.oof_predictions[key], second.oof_predictions[key])
        self.assertTrue(first.family_contributions)
        for audit in first.fold_audit:
            self.assertFalse(set(audit["train_groups"]) & set(audit["test_groups"]))
            self.assertEqual(audit["train_groups"], audit["preprocessing_training_groups"])
        self.assertTrue(any(audit["stage"] == "inner" for audit in first.fold_audit))
        self.assertTrue(any(audit["stage"] == "outer" for audit in first.fold_audit))
        for item in first.diagnostics:
            if item["status"] == "EVALUATED":
                self.assertIn("paired_fold_differences", item)
                self.assertIn("worst_error_location_removed", item["sensitivity"])

    def test_holdout_segregates_matched_pursued_locations_and_rejects_role_mix(self):
        data = synthetic_dataset()
        result = run_development(data, short_library())
        holdout = data.take(np.arange(8))
        groups = tuple(group if i < 4 else "NEW_SYNTHETIC_" + group for i, group in enumerate(holdout.groups))
        holdout = replace(holdout, groups=groups, evidence_classes=("PURSUED_SITE",) * 8, years=(2025,) * 8)
        evaluation = evaluate_frozen(result, holdout, role="pursued_sites", all_seedpoint_groups=data.groups)
        subsets = evaluation["models"][BASELINE_ID]["subsets"]
        self.assertEqual(subsets["matched_development_location"]["pooled"]["physical_locations"], 2)
        self.assertEqual(subsets["independent_development_location"]["pooled"]["physical_locations"], 2)
        self.assertEqual(subsets["independent_of_all_seedpoints"]["pooled"]["physical_locations"], 2)
        self.assertIsNone(subsets["all"]["WI"])
        with self.assertRaisesRegex(ModelingError, "SEED_IDENTITY_MEMBERSHIP_REQUIRED"):
            evaluate_frozen(result, holdout, role="pursued_sites")
        with self.assertRaisesRegex(ModelingError, "TEMPORAL_COHORT_INVALID"):
            evaluate_frozen(result, holdout, role="temporal_2026")


if __name__ == "__main__":
    unittest.main()
