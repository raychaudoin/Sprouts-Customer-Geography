from __future__ import annotations

import json
import math
import os
from pathlib import Path
import tempfile
import unittest

from sprouts_customer_geography.model13.modeling import SPATIAL_TERMS, compare_and_refit, fit_regularized, state_balanced_grouped_folds
from sprouts_customer_geography.model13.workflow import STAGE_FILES, ProtectedModel13Run, _rank_values, _required_spatial_features_computable, build_disclosure_safe_result, compare_runs, execute_model13, verify_repository_authority
from sprouts_customer_geography.pipe01.canonical import content_digest
from sprouts_customer_geography.pipe01.errors import ConformanceError


REPOSITORY = Path(__file__).resolve().parents[1]


def _temporary_directory() -> tempfile.TemporaryDirectory:
    return tempfile.TemporaryDirectory(dir=os.environ.get("MODEL13_TEST_TEMP_ROOT") or None)


def _synthetic_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for state_index, state in enumerate(("MI", "WI")):
        for group_index in range(12):
            group = f"{state}:fictional-{group_index:02d}"
            x = float(group_index + 1 + state_index * 0.35)
            features = {
                "households_5mi": 10000.0 + 800.0 * x,
                "log_households_5mi": math.log1p(10000.0 + 800.0 * x),
                "inner_household_share_3mi_of_7mi": 0.2 + 0.015 * x,
                "log_inner_outer_household_density_gradient": -0.45 + 0.055 * x,
                "fictional_capacity": math.log1p(40000.0 + 2500.0 * x),
                "fictional_access": 0.08 + 0.012 * ((group_index * 5 + state_index) % 11),
            }
            target = max(0.0, math.expm1(9.9 + 0.42 * features["log_inner_outer_household_density_gradient"] + 0.16 * features["fictional_capacity"] - 0.7 * features["fictional_access"]))
            for repeat in range(1 + (group_index % 2)):
                rows.append({
                    "analytical_observation_id": f"{state}:fictional-observation-{group_index:02d}-{repeat}",
                    "source_observation_id": f"fictional-{state}-{group_index:02d}-{repeat}",
                    "state": state,
                    "successor_physical_location_id": group,
                    "original_physical_location_id": f"fictional-{group_index:02d}",
                    "features": dict(features),
                    "isolated_sales": target * (1.0 + 0.002 * repeat),
                })
    return rows


class Model13AuthorityTests(unittest.TestCase):
    def test_frozen_contract_and_output_contract_verify(self) -> None:
        contract, output = verify_repository_authority(REPOSITORY)
        self.assertEqual(contract["artifact_id"], "MODEL13_MICHIGAN_BENCHMARK_POOLED_SUCCESSOR_STATEWIDE_SCORING_CONTRACT_V1")
        self.assertEqual(contract["version"], "1.1.0")
        self.assertEqual(contract["combined_cohort"]["fitting"]["pooled"], {"observation_count": 196, "physical_location_count": 123})
        self.assertEqual(contract["authority_amendment"]["excluded_from_fitting"], {"michigan_observation_count": 5, "michigan_physical_location_count": 3})
        self.assertFalse(contract["authority_amendment"]["frozen_benchmark_changed_or_rerun"])
        self.assertEqual(contract["selection"]["primary_reference_candidate_id"], "successor_model11_termset_elastic_net")
        self.assertEqual(output["tract_output"]["row_count"], 3017)
        self.assertEqual(len(contract["candidate_family"]), 4)

    def test_exactly_one_manifest_and_work_order(self) -> None:
        manifests = list((REPOSITORY / "governance/tasks").glob("MODEL-13*.json"))
        work_orders = list((REPOSITORY / "docs/work_orders").glob("MODEL_13*.md"))
        self.assertEqual(len(manifests), 1)
        self.assertEqual(len(work_orders), 1)

    def test_disclosure_safe_execution_commitment_binds_amended_authority(self) -> None:
        commitment = json.loads((REPOSITORY / "config/model/model13_execution_commitment.json").read_text(encoding="utf-8"))
        semantic = dict(commitment)
        expected_hash = semantic.pop("content_sha256")
        self.assertEqual(expected_hash, content_digest(semantic))
        self.assertEqual(commitment["contract_authority"]["version"], "1.1.0")
        result = commitment["execution_result"]
        self.assertEqual(result["selected_successor_formulation"], "successor_combined_multivariate_elastic_net")
        self.assertEqual(result["statewide_computable_count"] + result["statewide_noncomputable_count"], 3017)
        self.assertEqual(result["deterministic_rerun"], "MATCH")
        self.assertTrue(result["benchmark_reused_without_reevaluation"])
        self.assertEqual(result["impacted_sales_values_accessed"], 0)

    def test_target_blind_freeze_requires_complete_spatial_opportunity_vectors(self) -> None:
        complete = {"MI:fictional": {"features": {"households_5mi": 100.0, "log_households_5mi": math.log1p(100.0), "inner_household_share_3mi_of_7mi": 0.4, "log_inner_outer_household_density_gradient": 0.2}}}
        self.assertTrue(_required_spatial_features_computable(complete))
        incomplete = {"MI:fictional": {"features": {**complete["MI:fictional"]["features"], "log_households_5mi": None}}}
        self.assertFalse(_required_spatial_features_computable(incomplete))


class Model13ModelingTests(unittest.TestCase):
    def test_state_balanced_folds_keep_groups_whole(self) -> None:
        rows = _synthetic_rows()
        assignment = state_balanced_grouped_folds(rows, 5)
        self.assertEqual(len(assignment), 24)
        for state in ("MI", "WI"):
            counts = [sum(group.startswith(state + ":") and fold == index for group, fold in assignment.items()) for index in range(5)]
            self.assertLessEqual(max(counts) - min(counts), 1)
        for row in rows:
            self.assertEqual(assignment[str(row["successor_physical_location_id"])], assignment[str(row["successor_physical_location_id"])])

    def test_inverse_location_weighted_fit_separates_output_concepts(self) -> None:
        rows = _synthetic_rows()
        model = fit_regularized(rows, "fictional", "ridge", list(SPATIAL_TERMS), alpha=0.1)
        score = model.score_features(rows[0]["features"])
        self.assertEqual(score["household_opportunity"], rows[0]["features"]["households_5mi"])
        self.assertGreater(score["customer_fit_proxy"], 0)
        self.assertGreaterEqual(score["modeled_target_mass"], 0)
        self.assertEqual(model.protected_parameters()["estimation_weighting"], "inverse physical-location observation count")

    def test_four_candidate_comparison_and_single_final_refit(self) -> None:
        rows = _synthetic_rows()
        candidates = [
            {"candidate_id": "successor_spatial_reference", "architecture": "ridge", "fixed_alpha": 0.1},
            {"candidate_id": "successor_model11_termset_elastic_net", "architecture": "elastic_net", "alpha_grid": [0.1], "l1_ratio_grid": [0.5]},
            {"candidate_id": "successor_combined_multivariate_ridge", "architecture": "ridge", "alpha_grid": [0.1]},
            {"candidate_id": "successor_combined_multivariate_elastic_net", "architecture": "elastic_net", "alpha_grid": [0.1], "l1_ratio_grid": [0.5]},
        ]
        reference_terms = [*SPATIAL_TERMS, "fictional_capacity"]
        all_terms = [*SPATIAL_TERMS, "fictional_capacity", "fictional_access"]
        terms = {
            "successor_spatial_reference": list(SPATIAL_TERMS),
            "successor_model11_termset_elastic_net": reference_terms,
            "successor_combined_multivariate_ridge": all_terms,
            "successor_combined_multivariate_elastic_net": all_terms,
        }
        result = compare_and_refit(rows, candidates, terms)
        self.assertEqual(len(result.diagnostics), 4)
        self.assertIn(result.selection["selected_candidate_id"], terms)
        self.assertTrue(result.selection["rule_applied_without_change"])
        for item in result.diagnostics:
            self.assertEqual(set(item["aggregate_oof"]), {"pooled", "michigan", "wisconsin"})
            self.assertEqual(set(item["outer_fold_metric_ranges"]), {"pooled", "michigan", "wisconsin"})
            self.assertIn("state_holdout_sensitivity", item)
        self.assertEqual(result.final_model.candidate_id, result.selection["selected_candidate_id"])

    def test_ranks_retain_noncomputable_rows(self) -> None:
        rows = [{"geoid": "a", "score": 10.0}, {"geoid": "b", "score": 5.0}, {"geoid": "c", "score": 5.0}, {"geoid": "d", "score": None}]
        _rank_values(rows, "score", "rank", "percentile")
        self.assertEqual(rows[0]["rank"], 1)
        self.assertEqual(rows[1]["rank"], rows[2]["rank"])
        self.assertIsNone(rows[3]["rank"])
        self.assertIsNone(rows[3]["percentile"])


class Model13ProtectedRunTests(unittest.TestCase):
    def test_resume_reuses_ready_benchmark_without_rewriting_it(self) -> None:
        with _temporary_directory() as directory:
            output = Path(directory) / "protected-output"
            output.mkdir()
            original = ProtectedModel13Run(output, REPOSITORY, run_id="m13run-fictional-resume")
            stage = original.write_stage("benchmark", {"package_id": "MODEL13_MICHIGAN_FROZEN_BENCHMARK_V1", "state": "ready", "fictional": True})
            before = stage.package_path.read_bytes()
            resumed = ProtectedModel13Run.resume_after_benchmark(output, REPOSITORY, run_id="m13run-fictional-resume")
            self.assertEqual(tuple(resumed.stages), ("benchmark",))
            self.assertEqual(stage.package_path.read_bytes(), before)
            self.assertFalse((resumed.run_dir / "feature_freeze").exists())

    def test_fresh_benchmark_execution_is_denied_after_amendment(self) -> None:
        with self.assertRaisesRegex(ConformanceError, "MODEL13_FROZEN_BENCHMARK_RERUN_DENIED"):
            execute_model13(repository_root=REPOSITORY, resolver=object())

    def test_incomplete_first_ready_last_and_immutability(self) -> None:
        with _temporary_directory() as directory:
            temporary = Path(directory)
            output = temporary / "protected-output"
            output.mkdir()
            run = ProtectedModel13Run(output, REPOSITORY, run_id="m13run-fictional")
            self.assertTrue((run.run_dir / "run_state.json").is_file())
            for stage, package_id in zip(("benchmark", "feature_freeze", "transition", "development", "statewide"), ("MODEL13_MICHIGAN_FROZEN_BENCHMARK_V1", "MODEL13_COMBINED_TARGET_BLIND_FEATURE_FREEZE_V1", "MODEL13_MICHIGAN_DEVELOPMENT_ROLE_TRANSITION_V1", "MODEL13_POOLED_SUCCESSOR_DEVELOPMENT_V1", "MODEL13_MICHIGAN_STATEWIDE_TRACT_SCORING_V1")):
                run.write_stage(stage, {"package_id": package_id, "state": "ready", "fictional": True})
                self.assertTrue(run.require_ready(stage).ready_path.is_file())
            run.finalize({"tract_count": 3017, "fictional": True})
            self.assertTrue((run.run_dir / "READY.json").is_file())
            with self.assertRaises(ConformanceError):
                ProtectedModel13Run(output, REPOSITORY, run_id="m13run-fictional")

    def test_semantic_rerun_ignores_run_specific_commitment_fields(self) -> None:
        with _temporary_directory() as directory:
            root = Path(directory)
            first = root / "first"
            second = root / "second"
            for run, token in ((first, "one"), (second, "two")):
                run.mkdir()
                (run / "READY.json").write_text("{}", encoding="utf-8")
                for stage, filename in STAGE_FILES.items():
                    path = run / stage
                    path.mkdir()
                    payload = {"stage": stage, "value": 7, "verification_of": token, "protected_content_sha256": token, "stable_package_identity": token}
                    (path / filename).write_text(json.dumps(payload), encoding="utf-8")
                presentation = run / "presentation"
                presentation.mkdir()
                (presentation / "model13_michigan_tract_scores.csv").write_bytes(b"geoid\nfictional\n")
                (presentation / "model13_michigan_seed_context.csv").write_bytes(b"id\nfictional\n")
            comparison = compare_runs(first, second)
            self.assertEqual(comparison["state"], "MATCH")
            self.assertTrue(comparison["presentation_csvs_byte_identical"])
            self.assertTrue(comparison["benchmark_reused_without_reevaluation"])

    def test_disclosure_safe_report_rejects_no_aggregate_surface(self) -> None:
        class Result:
            benchmark_count = 82
            benchmark_metrics = {"spearman": 0.5, "kendall_tau_b": 0.3, "log_rmse": 0.1, "level_mae": 2.0}
            retained_feature_count = 7
            excluded_feature_count = 6
            comparison = ({"candidate_id": "successor_spatial_reference", "aggregate_oof": {domain: {"spearman": 0.5, "kendall_tau_b": 0.3, "log_rmse": 0.1, "level_mae": 2.0} for domain in ("pooled", "michigan", "wisconsin")}, "stability": {"stability_score": 1.0}, "mean_outer_effective_degrees_of_freedom": 3.0, "maximum_physical_location_absolute_log_error": 0.2},)
            selected_candidate_id = "successor_spatial_reference"
            statewide_computable_count = 3000
            statewide_noncomputable_count = 17
            statewide_support_truncation_count = 200
        report = build_disclosure_safe_result(Result(), {"state": "MATCH"})
        self.assertEqual(report["statewide_tract_count"], 3017)
        self.assertEqual(report["protected_accounting_observation_count"], 201)
        self.assertEqual(report["pooled_development_observation_count"], 196)
        self.assertEqual(report["pooled_development_physical_location_count"], 123)
        self.assertFalse(report["frozen_benchmark_reevaluated"])
        self.assertEqual(report["impacted_sales_values_accessed"], 0)
        serialized = json.dumps(report).lower()
        self.assertNotIn("latitude", serialized)
        self.assertNotIn("coefficient", serialized)


if __name__ == "__main__":
    unittest.main()
