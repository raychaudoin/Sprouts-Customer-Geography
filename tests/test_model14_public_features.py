"""Repository-safe MODEL-14 target-blind public-feature tests."""

from __future__ import annotations

import copy
from contextlib import redirect_stdout
import io
import json
import math
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from sprouts_customer_geography.model14.public import (
    ACS_COMPONENTS,
    FEATURE_IDS,
    LODES_SUM_FIELDS,
    aggregate_context_features,
    load_contract,
)
from sprouts_customer_geography.model14.modeling import (
    fit_training_fold_preprocessor,
    grouped_oof_predictions,
    nested_grouped_oof,
    tune_parameters,
)
from sprouts_customer_geography.model14.experiment import (
    MODEL13_ACCEPTED_ROUNDED,
    _verify_baseline_reproduction,
    build_disclosure_safe_result,
)
from sprouts_customer_geography.model14.cli import main as model14_main
from sprouts_customer_geography.model13.modeling import SPATIAL_TERMS, _cv_predictions
from sprouts_customer_geography.pipe01.canonical import content_digest
from sprouts_customer_geography.pipe01.errors import ConformanceError


REPOSITORY = Path(__file__).resolve().parents[1]


def _public_component_row(state: str = "MI") -> dict[str, object]:
    row: dict[str, object] = {
        "state": state,
        "aland_sq_m": 2_589_988.110336,
        "traffic_distance_primary_road_m": 100.0,
        "traffic_distance_primary_secondary_road_m": 25.0,
    }
    row.update({field: 10.0 for field in LODES_SUM_FIELDS})
    row.update({
        "lodes_workplace_jobs": 100.0,
        "lodes_resident_workers": 100.0,
        "lodes_main_work_flows": 80.0,
        "lodes_aux_work_flows": 20.0,
        "lodes_same_tract_live_work_flows": 10.0,
        "lodes_workplace_job_square_sum": 500.0,
        "lodes_origin_hhi_weighted_flow": 5.0,
        "lodes_origin_hhi_weight": 10.0,
    })
    row.update({f"acs_{component}_estimate": 10.0 for component in ACS_COMPONENTS})
    for denominator in (
        "vehicle_households_total",
        "commuters_total",
        "commute_time_total",
        "households_total",
        "poverty_universe",
        "income_households_total",
        "housing_units_total",
        "population_total",
    ):
        row[f"acs_{denominator}_estimate"] = 100.0
    return row


def _synthetic_model_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for state_index, state in enumerate(("MI", "WI")):
        for group_index in range(8):
            x_value = float(group_index + 1 + state_index * 0.35)
            features = {
                "log_households_5mi": math.log1p(10_000.0 + 700.0 * x_value),
                "inner_household_share_3mi_of_7mi": 0.20 + 0.014 * x_value,
                "log_inner_outer_household_density_gradient": -0.4 + 0.05 * x_value,
                "fictional_public_expansion": math.log1p(100.0 + 9.0 * x_value),
            }
            target = math.expm1(
                9.6
                + 0.22 * features["log_households_5mi"]
                + 0.35 * features["log_inner_outer_household_density_gradient"]
                + 0.08 * features["fictional_public_expansion"]
            )
            group = f"{state}:fictional-{group_index:02d}"
            for repeat in range(1 + group_index % 2):
                rows.append({
                    "analytical_observation_id": f"{group}:{repeat}",
                    "successor_physical_location_id": group,
                    "state": state,
                    "features": dict(features),
                    "isolated_sales": target * (1.0 + 0.001 * repeat),
                })
    return rows


class Model14PublicAuthorityTests(unittest.TestCase):
    def test_exactly_one_manifest_and_work_order_and_pre_h_posture(self) -> None:
        manifests = list((REPOSITORY / "governance/tasks").glob("MODEL-14*.json"))
        work_orders = list((REPOSITORY / "docs/work_orders").glob("MODEL_14*.md"))
        self.assertEqual(len(manifests), 1)
        self.assertEqual(len(work_orders), 1)
        manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
        self.assertEqual(manifest["task_id"], "MODEL-14")
        self.assertEqual(manifest["state"], "IN_PROGRESS")
        self.assertEqual(manifest["completion_state"]["execution"], "IN_PROGRESS")
        self.assertEqual(manifest["completion_state"]["capability_acceptance"], "NOT_REVIEWED")
        self.assertNotIn("implementation_commit", manifest)

    def test_contract_is_target_blind_bounded_and_excludes_protected_features(self) -> None:
        contract = load_contract(REPOSITORY)
        self.assertTrue(contract["target_blind"])
        self.assertFalse(contract["production_source_authority"])
        self.assertEqual(contract["model_feature_count_by_family"], {"lodes": 14, "business_context": 0, "traffic_accessibility": 2, "richer_acs": 11})
        self.assertEqual(tuple(item["feature_id"] for item in contract["feature_catalog"]), FEATURE_IDS)
        protected_tokens = ("race", "ethnicity", "sex", "religion")
        self.assertFalse(any(token in feature.lower() for feature in FEATURE_IDS for token in protected_tokens))
        self.assertTrue(all(value is False for value in contract["protected_characteristic_policy"].values()))

    def test_public_freeze_commitment_binds_zero_target_access_and_determinism(self) -> None:
        commitment = json.loads((REPOSITORY / "config/model14/target_blind_public_feature_commitment.json").read_text(encoding="utf-8"))
        semantic = dict(commitment)
        recorded = semantic.pop("content_sha256")
        self.assertEqual(recorded, content_digest(semantic))
        self.assertEqual(commitment["state"], "TARGET_BLIND_PUBLIC_FEATURES_FROZEN")
        self.assertEqual(commitment["chronology"]["target_values_accessed"], 0)
        self.assertEqual(commitment["chronology"]["protected_anchor_rows_accessed"], 0)
        self.assertFalse(commitment["chronology"]["sealed_or_prospective_evidence_accessed"])
        matrix = commitment["public_matrix_commitment"]
        self.assertEqual((matrix["row_count"], matrix["michigan_row_count"], matrix["wisconsin_row_count"]), (4559, 3017, 1542))
        self.assertEqual(matrix["determinism_state"], "DETERMINISTIC_BYTE_IDENTICAL")
        self.assertFalse(matrix["missing_to_zero"])


class Model14PublicFeatureTests(unittest.TestCase):
    def test_feature_generation_is_complete_finite_and_deterministic(self) -> None:
        rows = {"26001000100": _public_component_row()}
        first = aggregate_context_features(rows, ["26001000100"], "26001000100")
        second = aggregate_context_features(rows, ["26001000100"], "26001000100")
        self.assertEqual(first, second)
        self.assertEqual(tuple(first), FEATURE_IDS)
        self.assertEqual(len(first), 27)
        self.assertTrue(all(value is not None and math.isfinite(float(value)) for value in first.values()))

    def test_missing_component_propagates_without_zero_substitution(self) -> None:
        row = _public_component_row()
        row["acs_income_low_002_estimate"] = None
        features = aggregate_context_features({"26001000100": row}, ["26001000100"], "26001000100")
        self.assertIsNone(features["acs_low_income_under_35k_household_share_5mi"])
        self.assertIsNotNone(features["acs_high_income_100k_plus_household_share_5mi"])

    def test_undefined_ratio_remains_missing_and_zero_count_remains_observed(self) -> None:
        row = _public_component_row()
        row["lodes_workplace_jobs"] = 0.0
        row["lodes_high_earnings_jobs"] = 0.0
        features = aggregate_context_features({"26001000100": row}, ["26001000100"], "26001000100")
        self.assertIsNone(features["lodes_high_earnings_job_share_5mi"])
        self.assertEqual(features["lodes_log_workplace_jobs_5mi"], 0.0)

    def test_duplicate_members_and_cross_state_members_fail_closed(self) -> None:
        rows = {"26001000100": _public_component_row(), "55001000100": _public_component_row("WI")}
        with self.assertRaisesRegex(ConformanceError, "MODEL14_CONTEXT_GEOID_INVALID"):
            aggregate_context_features(rows, ["26001000100", "26001000100"], "26001000100")
        with self.assertRaisesRegex(ConformanceError, "MODEL14_CONTEXT_STATE_MISMATCH"):
            aggregate_context_features(rows, ["26001000100", "55001000100"], "26001000100")


class Model14ModelingTests(unittest.TestCase):
    def test_complete_feature_baseline_is_mechanically_equivalent_to_model13_oof(self) -> None:
        rows = _synthetic_model_rows()
        terms = [*SPATIAL_TERMS, "fictional_public_expansion"]
        candidate = {"candidate_id": "fictional_baseline", "architecture": "elastic_net"}
        parameters = {"alpha": 0.1, "l1_ratio": 0.5}
        accepted_engine = _cv_predictions(rows, candidate, terms, parameters, 3)
        experimental_engine, audits = grouped_oof_predictions(rows, "fictional_baseline", terms, fold_count=3, **parameters)
        self.assertEqual(len(audits), 3)
        self.assertTrue(all(audit["group_overlap_count"] == 0 for audit in audits))
        for left, right in zip(accepted_engine, experimental_engine):
            self.assertAlmostEqual(left, right, places=9)

    def test_training_median_uses_distinct_training_groups_only(self) -> None:
        rows = []
        for group, value, repeats in (("MI:a", 1.0, 7), ("MI:b", 3.0, 1), ("MI:c", 100.0, 1)):
            for repeat in range(repeats):
                rows.append({"successor_physical_location_id": group, "features": {"fictional": value}, "analytical_observation_id": f"{group}:{repeat}", "state": "MI", "isolated_sales": 1.0})
        fitted = fit_training_fold_preprocessor(rows, ["fictional"])
        self.assertEqual(fitted.training_group_count, 3)
        self.assertEqual(fitted.medians["fictional"], 3.0)
        self.assertEqual(fitted.transform_features({"fictional": None})["fictional"], 3.0)

    def test_nested_grouped_evaluation_imputes_inside_folds_and_keeps_groups_whole(self) -> None:
        rows = _synthetic_model_rows()
        missing = copy.deepcopy(rows)
        for row in missing:
            if str(row["successor_physical_location_id"]).endswith(("02", "05")):
                row["features"]["fictional_public_expansion"] = None
        result = nested_grouped_oof(
            missing,
            "fictional_expanded",
            [*SPATIAL_TERMS, "fictional_public_expansion"],
            alpha_grid=(0.1,),
            l1_ratio_grid=(0.5,),
            outer_count=3,
            inner_count=2,
        )
        self.assertEqual(set(result["aggregate_oof"]), {"pooled", "michigan", "wisconsin"})
        self.assertEqual(len(result["predictions"]), len(missing))
        self.assertTrue(all(math.isfinite(value) and value >= 0 for value in result["predictions"]))
        self.assertTrue(all(audit["group_overlap_count"] == 0 and audit["preprocessing_fit_scope"] == "outer_training_groups_only" for audit in result["fold_audits"]))

    def test_inconsistent_repeated_group_feature_fails_closed(self) -> None:
        rows = [
            {"successor_physical_location_id": "MI:a", "features": {"fictional": 1.0}},
            {"successor_physical_location_id": "MI:a", "features": {"fictional": 2.0}},
        ]
        with self.assertRaisesRegex(ConformanceError, "MODEL14_WITHIN_GROUP_FEATURE_MISMATCH"):
            fit_training_fold_preprocessor(rows, ["fictional"])

    def test_nonconvergent_grid_point_is_ineligible_not_silently_retained(self) -> None:
        rows = _synthetic_model_rows()
        predictions = [float(row["isolated_sales"]) for row in rows]
        with patch(
            "sprouts_customer_geography.model14.modeling.grouped_oof_predictions",
            side_effect=[
                ConformanceError("MODEL13_ELASTIC_NET_DID_NOT_CONVERGE", "fictional nonconvergence"),
                (predictions, []),
            ],
        ), patch("sprouts_customer_geography.model14.modeling.fit_experimental_model"):
            selected = tune_parameters(
                rows,
                "fictional",
                [*SPATIAL_TERMS, "fictional_public_expansion"],
                alpha_grid=(0.01, 0.1),
                l1_ratio_grid=(0.5,),
                fold_count=2,
            )
        self.assertEqual(selected, {"alpha": 0.1, "l1_ratio": 0.5})

    def test_exact_accepted_baseline_rounding_is_required(self) -> None:
        result = {"aggregate_oof": copy.deepcopy(MODEL13_ACCEPTED_ROUNDED)}
        reproduced = _verify_baseline_reproduction(result)
        self.assertEqual(reproduced["state"], "MATCH")
        changed = copy.deepcopy(result)
        changed["aggregate_oof"]["pooled"]["spearman"] = 0.6200
        with self.assertRaisesRegex(ConformanceError, "MODEL14_BASELINE_REPRODUCTION_FAILED"):
            _verify_baseline_reproduction(changed)

    def test_disclosure_safe_result_omits_rows_targets_paths_and_identifiers(self) -> None:
        rows = _synthetic_model_rows()
        for row in rows:
            row["features"]["lodes_log_workplace_jobs_5mi"] = row["features"].pop("fictional_public_expansion")
        baseline = nested_grouped_oof(
            rows,
            "A_model13_reproduced",
            list(SPATIAL_TERMS),
            alpha_grid=(0.1,),
            l1_ratio_grid=(0.5,),
            outer_count=3,
            inner_count=2,
            term_families={term: "model13_accepted" for term in SPATIAL_TERMS},
        )
        expanded = nested_grouped_oof(
            rows,
            "B_model13_plus_lodes",
            [*SPATIAL_TERMS, "lodes_log_workplace_jobs_5mi"],
            alpha_grid=(0.1,),
            l1_ratio_grid=(0.5,),
            outer_count=3,
            inner_count=2,
            term_families={
                **{term: "model13_accepted" for term in SPATIAL_TERMS},
                "lodes_log_workplace_jobs_5mi": "lodes",
            },
        )
        zero_delta = {
            domain: {metric: 0.0 for metric in ("spearman", "kendall_tau_b", "log_rmse", "level_mae")}
            for domain in ("pooled", "michigan", "wisconsin")
        }
        protected = {
            "baseline_terms": list(SPATIAL_TERMS),
            "baseline_reproduction": {"state": "MATCH"},
            "public_feature_families": {
                "lodes": {"status": "evaluation-ready", "candidate_feature_count": 14},
            },
            "development_anchor_coverage": {},
            "candidates": {"A_model13_reproduced": baseline, "B_model13_plus_lodes": expanded},
            "strongest_expanded_candidate_id": "B_model13_plus_lodes",
            "ablations": {
                "lodes": {
                    "removed_feature_count": 14,
                    "reused_primary_matrix_candidate": True,
                    "aggregate_oof": baseline["aggregate_oof"],
                    "strongest_minus_ablation_metric_delta": zero_delta,
                    "stability_score": baseline["stability"]["stability_score"],
                }
            },
            "evidence_disposition": "no credible improvement",
            "disposition_evidence": ["synthetic disclosure fixture"],
        }
        safe = build_disclosure_safe_result(protected)
        serialized = json.dumps(safe, sort_keys=True)
        self.assertEqual(safe["state"], "PRE_H_EXPERIMENT_COMPLETE")
        for token in ("successor_physical_location_id", "isolated_sales", "predictions", "canonical_latitude", "C:\\Users\\"):
            self.assertNotIn(token, serialized)

    def test_cli_unexpected_failure_is_opaque_and_path_free(self) -> None:
        output = io.StringIO()
        with patch.dict(os.environ, {"MODEL13_AUTHORITY_REGISTRY": "fictional-registry"}), patch(
            "sprouts_customer_geography.model14.cli.execute_protected_experiment",
            side_effect=RuntimeError("C:\\protected\\must-not-disclose.json"),
        ), redirect_stdout(output):
            status = model14_main([
                "--repository-root", str(REPOSITORY),
                "protected-experiment",
                "--public-freeze", "outputs/fictional-public",
                "--verification-freeze", "outputs/fictional-verification",
                "--output", "outputs/fictional-experiment",
            ])
        self.assertEqual(status, 3)
        self.assertEqual(
            json.loads(output.getvalue()),
            {"state": "failed_closed", "code": "MODEL14_UNEXPECTED_FAILURE"},
        )
        self.assertNotIn("protected", output.getvalue().lower())


if __name__ == "__main__":
    unittest.main()
