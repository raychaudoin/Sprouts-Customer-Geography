from __future__ import annotations

import copy
import io
import json
import math
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from shapely.geometry import Polygon

from sprouts_customer_geography.model09.modeling import _oof_predictions as model09_oof_predictions, grouped_folds, grouped_metrics
from sprouts_customer_geography.model11 import cli
from sprouts_customer_geography.model11.development import ProtectedDevelopmentRun, _join_targets
from sprouts_customer_geography.model11.features import (
    FeatureFreezeResult,
    TargetBlindFreezeRun,
    _aggregate_measure,
    build_disclosure_safe_freeze_result,
    build_multivariate_features,
    verify_repository_authority,
)
from sprouts_customer_geography.model11.modeling import (
    BASE_TERMS,
    _fixed_terms,
    compare_candidates,
    fit_regularized,
)
from sprouts_customer_geography.model11.resolver import ProtectedHandleResolver
from sprouts_customer_geography.model09.features import TractEvidence
from sprouts_customer_geography.pipe01.errors import ConformanceError
from sprouts_customer_geography.pipe01.production import Geo03ProductionTransformer


ROOT = Path(__file__).resolve().parents[1]


def _contract() -> dict:
    return json.loads((ROOT / "config/model/model11_wisconsin_multivariate_model_contract.json").read_text(encoding="utf-8"))


def _temporary_directory() -> tempfile.TemporaryDirectory:
    return tempfile.TemporaryDirectory(dir=os.environ.get("MODEL11_TEST_TEMP_ROOT") or None)


def _components(geoids: list[str], *, missing_measure: str | None = None) -> dict:
    values = {
        "median_household_income": (70000, 3000), "per_capita_income": (35000, 1500),
        "civilian_labor_force": (600, 30), "labor_population_16_plus": (900, 40), "civilian_employed": (570, 28),
        "education_bachelors": (160, 15), "education_masters": (80, 10), "education_professional": (20, 5), "education_doctorate": (10, 4), "education_population_25_plus": (700, 35),
        "owner_occupied_housing_units": (300, 20), "occupied_housing_units_total": (500, 25), "housing_units_vacant": (50, 10), "housing_units_total": (550, 28),
        "median_home_value": (250000, 12000), "median_gross_rent": (1300, 80), "average_household_size": (2.5, 0.1),
        "households_no_vehicle": (40, 9), "vehicle_table_households_total": (500, 25),
        "commuters_drive_alone": (400, 25), "commuters_total": (520, 27), "commuters_work_from_home": (60, 11),
    }
    output = {}
    for geoid_index, geoid in enumerate(geoids):
        output[geoid] = {}
        for name, (estimate, moe) in values.items():
            output[geoid][name] = {"estimate": estimate + geoid_index * (2 if estimate < 1000 else 100), "moe": moe, "status": "missing" if name == missing_measure else "valid"}
    return output


def _rows(group_count: int = 10) -> list[dict]:
    rows = []
    for group in range(group_count):
        repeats = 2 if group < 3 else 1
        for repeat in range(repeats):
            features = {
                "log_households_5mi": 9.0 + group * 0.08,
                "inner_household_share_3mi_of_7mi": 0.2 + group * 0.025,
                "log_inner_outer_household_density_gradient": -0.5 + group * 0.1,
                "median_household_income": 10.8 + group * 0.03,
                "employment_rate": 0.8 + group * 0.005,
                "vacancy_share": 0.12 - group * 0.004,
            }
            target_log = 2.0 + 0.3 * features["log_households_5mi"] + 1.2 * features["inner_household_share_3mi_of_7mi"] + 0.45 * features["log_inner_outer_household_density_gradient"] + 0.25 * features["median_household_income"] - 1.5 * features["vacancy_share"]
            rows.append({"source_observation_id": f"fictional-observation-{group}-{repeat}", "successor_physical_location_id": f"fictional-location-{group}", "market": f"FICTIONAL-{group % 3}", "forecast_vintage": 2024 + repeat, "isolated_sales": math.expm1(target_log), "features": features})
    return rows


class Model11DevelopmentTests(unittest.TestCase):
    def test_exact_authority_candidate_menu_vintage_and_bounds(self) -> None:
        contract = verify_repository_authority(ROOT)
        expected = ["median_household_income", "per_capita_income", "civilian_labor_force_share", "employment_rate", "bachelors_or_higher_share", "owner_occupancy_share", "vacancy_share", "median_home_value", "median_gross_rent", "average_household_size", "no_vehicle_household_share", "drive_alone_commuter_share", "work_from_home_commuter_share"]
        self.assertEqual([item["measure_id"] for item in contract["candidate_measures"]], expected)
        self.assertEqual(len(contract["candidates"]), 3)
        self.assertEqual(contract["accepted_authority"]["data03_contract_id"], "DATA03_WISCONSIN_MULTIVARIATE_ACS_FEATURE_SOURCE_CONTRACT_V1")
        data03 = json.loads((ROOT / "config/data/data03_wisconsin_multivariate_acs_feature_source_contract.json").read_text(encoding="utf-8"))
        self.assertEqual(data03["source_product"]["vintage"], "2024")

    def test_share_aggregation_sums_numerators_and_denominators(self) -> None:
        components = _components(["55000000001", "55000000002"])
        spec = next(item for item in _contract()["candidate_measures"] if item["measure_id"] == "owner_occupancy_share")
        result = _aggregate_measure(spec, list(components), components, {geoid: 100 for geoid in components})
        numerator = 300 + 302
        denominator = 500 + 502
        self.assertAlmostEqual(result["value"], numerator / denominator)
        self.assertNotAlmostEqual(result["value"], ((300 / 500) + (302 / 502)) / 2)

    def test_direct_weighted_profile_semantics_and_missingness(self) -> None:
        geoids = ["55000000001", "55000000002"]
        components = _components(geoids)
        spec = next(item for item in _contract()["candidate_measures"] if item["measure_id"] == "median_home_value")
        result = _aggregate_measure(spec, geoids, components, {geoid: 1 for geoid in geoids})
        expected = (250000 * 300 + 250100 * 302) / (300 + 302)
        self.assertAlmostEqual(result["value"], expected)
        missing = _components(geoids, missing_measure="median_home_value")
        self.assertEqual(_aggregate_measure(spec, geoids, missing, {geoid: 1 for geoid in geoids})["status"], "noncomputable")

    def test_target_blind_feature_generation_is_deterministic_and_drops_no_rows(self) -> None:
        contract = _contract()
        contract["cohort"] = {**contract["cohort"], "eligible_observation_count": 2, "physical_location_count": 1}
        geo03 = json.loads((ROOT / "config/geo/geo03_internal_point_membership_spatial_spec.json").read_text(encoding="utf-8"))
        transformer = Geo03ProductionTransformer(geo03)
        x_value, y_value = transformer.transform(-89.0, 44.0)
        tract = TractEvidence("55000000001", x_value, y_value, Polygon([(-90, 43), (-88, 43), (-88, 45), (-90, 45), (-90, 43)]), 1000, 100)
        cohort = [
            {"source_observation_id": "fictional-a", "successor_physical_location_id": "fictional-location", "market": "FICTIONAL", "forecast_vintage": 2024, "canonical_latitude": 44.0, "canonical_longitude": -89.0},
            {"source_observation_id": "fictional-b", "successor_physical_location_id": "fictional-location", "market": "FICTIONAL", "forecast_vintage": 2025, "canonical_latitude": 44.0, "canonical_longitude": -89.0},
        ]
        first = build_multivariate_features(cohort, [tract], _components([tract.geoid]), geo03, contract)
        second = build_multivariate_features(list(reversed(cohort)), [tract], _components([tract.geoid]), geo03, contract)
        self.assertEqual(len(first[0]), 2)
        self.assertEqual(first[0][0]["features"], first[0][1]["features"])
        self.assertEqual(first[1], second[1])
        self.assertNotIn("isolated_sales", json.dumps(first).lower())

    def test_missing_candidate_rejects_feature_not_observation(self) -> None:
        contract = _contract()
        contract["cohort"] = {**contract["cohort"], "eligible_observation_count": 1, "physical_location_count": 1}
        geo03 = json.loads((ROOT / "config/geo/geo03_internal_point_membership_spatial_spec.json").read_text(encoding="utf-8"))
        transformer = Geo03ProductionTransformer(geo03)
        x_value, y_value = transformer.transform(-89.0, 44.0)
        tract = TractEvidence("55000000001", x_value, y_value, Polygon([(-90, 43), (-88, 43), (-88, 45), (-90, 45), (-90, 43)]), 1000, 100)
        cohort = [{"source_observation_id": "fictional-a", "successor_physical_location_id": "fictional-location", "market": "FICTIONAL", "forecast_vintage": 2024, "canonical_latitude": 44.0, "canonical_longitude": -89.0}]
        rows, preparation = build_multivariate_features(cohort, [tract], _components([tract.geoid], missing_measure="median_home_value"), geo03, contract)
        self.assertEqual(len(rows), 1)
        self.assertEqual(preparation["excluded_data03_features"]["median_home_value"], "incomplete_member_tract_evidence")
        self.assertNotIn("median_home_value", rows[0]["features"])

    def test_training_scaling_uses_training_rows_only(self) -> None:
        rows = _rows(6)
        rows[-1]["features"][BASE_TERMS[0]] += 100.0
        train = rows[:-1]
        model = fit_regularized(train, "fictional-ridge", "ridge", list(BASE_TERMS), alpha=1.0)
        weights = []
        counts = {}
        for row in train:
            counts[row["successor_physical_location_id"]] = counts.get(row["successor_physical_location_id"], 0) + 1
        for row in train:
            weights.append(1 / counts[row["successor_physical_location_id"]])
        expected = sum(weight * row["features"][BASE_TERMS[0]] for row, weight in zip(train, weights)) / sum(weights)
        self.assertAlmostEqual(model.means[BASE_TERMS[0]], expected)
        self.assertNotAlmostEqual(model.means[BASE_TERMS[0]], sum(row["features"][BASE_TERMS[0]] for row in rows) / len(rows))

    def test_grouped_folds_and_predictor_scope_guards(self) -> None:
        rows = _rows(10)
        assignment = grouped_folds(rows, 5)
        self.assertEqual(assignment, grouped_folds(list(reversed(rows)), 5))
        for row in rows:
            self.assertEqual(assignment[row["successor_physical_location_id"]], assignment[row["successor_physical_location_id"]])
        with self.assertRaisesRegex(ConformanceError, "MODEL11_PREDICTOR_SCOPE_VIOLATION"):
            _fixed_terms(_contract()["candidates"][1], ["market=FICTIONAL"])

    def test_bounded_nested_comparison_is_deterministic_and_separates_semantics(self) -> None:
        rows = _rows(10)
        contract = _contract()
        contract["development_diagnostics"]["inner_grouped_fold_count"] = 3
        reference_candidate = {"candidate_id": "model09_spatial_concentration_reference", "terms": list(BASE_TERMS), "ridge_penalty": 0.1}
        assignment = grouped_folds(rows, 5)
        predicted, _ = model09_oof_predictions(rows, reference_candidate, assignment, sorted({row["market"] for row in rows}))
        metric = grouped_metrics(rows, predicted)
        contract["reference_reproduction"].update({"grouped_spearman": round(metric["spearman"], 4), "grouped_kendall_tau_b": round(metric["kendall_tau_b"], 4), "grouped_log_rmse": round(metric["log_rmse"], 4)})
        comparison = compare_candidates(rows, contract, ["median_household_income", "employment_rate", "vacancy_share"])
        rerun = compare_candidates(rows, contract, ["median_household_income", "employment_rate", "vacancy_share"])
        self.assertEqual(comparison.comparison, rerun.comparison)
        self.assertEqual(comparison.selection, rerun.selection)
        self.assertEqual(len(comparison.comparison), 3)
        self.assertEqual(set(comparison.oof_predictions), {item["candidate_id"] for item in contract["candidates"]})
        self.assertIn(comparison.selection["preferred_candidate_id"], comparison.fitted_models)
        for model in comparison.fitted_models.values():
            row = rows[0]
            self.assertGreater(model.predict(row), 0)
            factor = model.customer_fit_factor(row) if hasattr(model, "customer_fit_factor") else model.fit_proxy_factor(row)
            self.assertGreater(factor, 0)
            self.assertNotEqual(factor, model.predict(row))
        bounded = copy.deepcopy(contract)
        bounded["candidates"].append(copy.deepcopy(bounded["candidates"][-1]))
        with self.assertRaisesRegex(ConformanceError, "BOUNDED_CANDIDATE_CONFIG_INVALID"):
            compare_candidates(rows, bounded, [])

    def test_target_join_allows_isolated_sales_only_and_preserves_cohort(self) -> None:
        features = [{"source_observation_id": "fictional-a", "successor_physical_location_id": "fictional-location", "market": "FICTIONAL", "forecast_vintage": 2024, "features": {}}]
        bound = {"source_observation_id": "fictional-a", "successor_physical_location_id": "fictional-location", "market": "FICTIONAL", "forecast_vintage": 2024}
        binding = {"eligible_wisconsin_cohort": [bound], "minimum_target_projection": {"default_deny": True, "allowed_fields": ["forecast_vintage", "isolated_sales", "source_observation_lineage"], "denied_scope": ["Impacted Sales", "every non-Wisconsin target"], "rows": [{"source_observation_id": "fictional-a", "forecast_vintage": 2024, "isolated_sales": "123"}]}}
        rows, targets = _join_targets(features, binding)
        self.assertEqual(targets, {"fictional-a": 123.0})
        self.assertEqual(len(rows), 1)
        denied = copy.deepcopy(binding)
        denied["minimum_target_projection"]["rows"][0]["impacted_sales"] = "999"
        with self.assertRaisesRegex(ConformanceError, "TARGET_PROJECTION_SCOPE_VIOLATION"):
            _join_targets(features, denied)

    def test_immutable_runs_are_incomplete_first_ready_last_and_outside_git(self) -> None:
        with _temporary_directory() as temporary:
            output = Path(temporary) / "protected"
            output.mkdir()
            freeze = TargetBlindFreezeRun(output, ROOT, freeze_run_id="m11freeze-fictional")
            self.assertTrue((freeze.run_dir / "freeze_state.json").is_file())
            self.assertFalse((freeze.run_dir / "READY.json").exists())
            freeze.finalize({"package_id": "MODEL11_TARGET_BLIND_FEATURE_FREEZE_PACKAGE_V1", "freeze_run_id": freeze.freeze_run_id, "state": "ready"})
            self.assertTrue((freeze.run_dir / "READY.json").is_file())
            with self.assertRaisesRegex(ConformanceError, "MODEL11_FREEZE_IMMUTABLE"):
                TargetBlindFreezeRun(output, ROOT, freeze_run_id="m11freeze-fictional")
            run = ProtectedDevelopmentRun(output, ROOT, development_run_id="m11run-fictional")
            self.assertFalse((run.run_dir / "READY.json").exists())
            run.mark_target_reuse(1)
            run.finalize({"package_id": "MODEL11_WISCONSIN_MULTIVARIATE_DEVELOPMENT_PACKAGE_V1", "development_run_id": run.development_run_id, "state": "ready"})
            self.assertTrue((run.run_dir / "READY.json").is_file())

    def test_protected_resolver_requires_exact_handles_and_containment(self) -> None:
        with _temporary_directory() as temporary:
            root = Path(temporary)
            protected = root / "protected"
            protected.mkdir()
            output = protected / "output"
            output.mkdir()
            fields = {
                "model10_package_handle": ("model10.json", "model10_package"), "model10_ready_marker_handle": ("model10-ready.json", "model10_ready_marker"),
                "pipe04_binding_handle": ("pipe04.json", "pipe04_binding"), "pipe04_ready_marker_handle": ("pipe04-ready.json", "pipe04_ready_marker"),
                "acs_b11001_source_handle": ("acs.dat", "accepted_acs_b11001_source"), "tiger_source_handle": ("tiger.zip", "accepted_tiger_tract_source"),
                "data03_normalized_source_handle": ("normalized.csv", "data03_normalized_source"), "data03_verification_report_handle": ("report.json", "data03_verification_report"), "data03_ready_marker_handle": ("data03-ready.json", "data03_ready_marker"),
            }
            resources = {}
            request = {}
            for field, (name, kind) in fields.items():
                (protected / name).write_text("{}", encoding="utf-8")
                handle = "phandle-" + name.replace(".", "-")
                resources[handle] = {"root_handle": "proot-fictional", "relative_path": name, "kind": kind}
                request[field] = handle
            resources["phandle-output"] = {"root_handle": "proot-fictional", "relative_path": "output", "kind": "model11_output_root"}
            request["model11_output_root_handle"] = "phandle-output"
            registry = {"registry_id": "MODEL11_PROTECTED_HANDLE_REGISTRY_V1", "version": "1.0.0", "protected_roots": {"proot-fictional": str(protected.resolve())}, "resources": resources, "development_request": request}
            registry_path = root / "registry.json"
            registry_path.write_text(json.dumps(registry), encoding="utf-8")
            resolver = ProtectedHandleResolver.load(registry_path, ROOT)
            self.assertEqual(resolver.resolve("phandle-output", "model11_output_root").path, output.resolve())
            with self.assertRaisesRegex(ConformanceError, "PROTECTED_HANDLE_UNRESOLVED"):
                resolver.resolve("phandle-unknown", "pipe04_binding")

    def test_cli_without_registry_fails_closed_without_discovery(self) -> None:
        stdout = io.StringIO()
        with patch("sys.argv", ["model11-develop", "freeze", "--repository-root", str(ROOT)]), patch.dict("os.environ", {}, clear=True), redirect_stdout(stdout):
            self.assertEqual(cli.main(), 2)
        report = json.loads(stdout.getvalue())
        self.assertEqual(report["error_code"], "AUTHORITATIVE_ACCESS_REGISTRY_UNRESOLVED")
        self.assertFalse(report["filesystem_discovery_performed"])

    def test_disclosure_safe_freeze_report_contains_no_protected_detail(self) -> None:
        report = build_disclosure_safe_freeze_result(FeatureFreezeResult(63, 41, 13, 7, 6, 0.94))
        self.assertEqual(report["target_values_accessed"], 0)
        self.assertNotIn("source_observation", json.dumps(report).lower())


if __name__ == "__main__":
    unittest.main()
