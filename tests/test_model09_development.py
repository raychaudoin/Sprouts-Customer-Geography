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

from sprouts_customer_geography.model09 import cli
from sprouts_customer_geography.model09.development import (
    DevelopmentResult,
    ProtectedDevelopmentRun,
    _target_rows,
    build_disclosure_safe_result,
)
from sprouts_customer_geography.model09.features import TractEvidence, build_public_features, reconcile_fixed_cohort
from sprouts_customer_geography.model09.modeling import compare_candidates, grouped_folds, grouped_metrics
from sprouts_customer_geography.model09.resolver import ProtectedHandleResolver, load_authorized_registry
from sprouts_customer_geography.pipe01.errors import ConformanceError
from sprouts_customer_geography.pipe01.production import Geo03ProductionTransformer
from sprouts_customer_geography.pipe01.safeguards import assert_no_protected_tracked_paths


ROOT = Path(__file__).resolve().parents[1]


def _temporary_directory() -> tempfile.TemporaryDirectory:
    return tempfile.TemporaryDirectory(dir=os.environ.get("MODEL09_TEST_TEMP_ROOT") or None)


def _contract() -> dict:
    return json.loads((ROOT / "config/model/model09_wisconsin_experimental_model_contract.json").read_text(encoding="utf-8"))


def _model_rows() -> list[dict]:
    rows = []
    for group in range(30):
        market = f"FICTIONAL-MARKET-{group % 5}"
        share = 0.18 + group * 0.012
        gradient = -0.8 + group * 0.055
        households = 12000 + group * 850
        repeats = 2 if group < 10 else 1
        for repeat in range(repeats):
            vintage = 2024 + repeat
            target = math.expm1(5.0 + 0.35 * math.log1p(households) + 2.7 * share + 0.6 * gradient + 0.04 * repeat)
            rows.append(
                {
                    "source_observation_id": f"sobs-fictional-{group}-{repeat}",
                    "successor_physical_location_id": f"m10loc-fictional-{group}",
                    "market": market,
                    "forecast_vintage": vintage,
                    "isolated_sales": target,
                    "features": {
                        "log_households_5mi": math.log1p(households),
                        "inner_household_share_3mi_of_7mi": share,
                        "log_inner_outer_household_density_gradient": gradient,
                    },
                }
            )
    return rows


def _bound_row(observation: str, physical: str, vintage: int = 2024) -> dict:
    return {
        "source_observation_id": observation,
        "source_observation_lineage": {"source_workbook_identity": "FICTIONAL-WI", "source_sheet": "Targets", "source_row": 2 if vintage == 2024 else 3, "source_seed_point_id": observation},
        "successor_physical_location_id": physical,
        "historical_model04_physical_location_id": None,
        "market": "FICTIONAL-MARKET",
        "forecast_vintage": vintage,
        "identity_state": "GENUINELY_NEW_LOCATION",
        "historical_evidence_role_lineage": [],
        "target_access_state": "NOT_ACCESSED_BY_MODEL10",
    }


def _model10_row(bound: dict, latitude: float = 44.0, longitude: float = -89.0) -> dict:
    return {
        **copy.deepcopy(bound),
        "model09_development_eligible": True,
        "quarantined": False,
        "quarantine_reason": None,
        "successor_canonical_anchor": {"source_observation_id": bound["source_observation_id"], "selection_semantics": "FICTIONAL", "observed_coordinate": {"latitude": latitude, "longitude": longitude, "provenance": "FICTIONAL"}},
    }


class Model09DevelopmentTests(unittest.TestCase):
    def test_grouped_folds_keep_repeated_locations_together_and_are_deterministic(self) -> None:
        rows = _model_rows()
        first = grouped_folds(rows, 5)
        second = grouped_folds(list(reversed(rows)), 5)
        self.assertEqual(first, second)
        self.assertEqual(set(first.values()), set(range(5)))
        for row in rows:
            self.assertEqual(first[row["successor_physical_location_id"]], first[row["successor_physical_location_id"]])

    def test_bounded_comparison_is_reproducible_and_selects_only_configured_candidate(self) -> None:
        rows = _model_rows()
        comparison, fitted, selection, oof = compare_candidates(rows, _contract())
        rerun = compare_candidates(rows, _contract())
        self.assertEqual(comparison, rerun[0])
        self.assertEqual(selection, rerun[2])
        self.assertEqual(len(comparison), 4)
        self.assertEqual(len(fitted), 4)
        self.assertEqual(set(oof), {item["candidate_id"] for item in _contract()["candidates"]})
        self.assertIn(selection["preferred_candidate_id"], {None, *oof})
        self.assertTrue(all(len(values) == len(rows) for values in oof.values()))

    def test_grouped_metrics_weight_each_physical_location_once(self) -> None:
        rows = [
            {"successor_physical_location_id": "repeat", "isolated_sales": 10.0},
            {"successor_physical_location_id": "repeat", "isolated_sales": 30.0},
            {"successor_physical_location_id": "single", "isolated_sales": 100.0},
        ]
        grouped = grouped_metrics(rows, [12.0, 28.0, 90.0])
        expected = grouped_metrics([
            {"successor_physical_location_id": "repeat", "isolated_sales": 20.0},
            rows[2],
        ], [20.0, 90.0])
        self.assertEqual(grouped, expected)

    def test_reconcile_complete_cohort_preserves_identity_and_canonical_anchor(self) -> None:
        first = _bound_row("sobs-fictional-a", "m10loc-fictional-one", 2024)
        second = _bound_row("sobs-fictional-b", "m10loc-fictional-one", 2025)
        binding = {"eligible_wisconsin_cohort": [first, second]}
        model10 = {"records": [_model10_row(first), _model10_row(second)]}
        result = reconcile_fixed_cohort(binding, model10)
        self.assertEqual(len(result), 2)
        self.assertEqual({row["canonical_latitude"] for row in result}, {44.0})
        changed = copy.deepcopy(binding)
        changed["eligible_wisconsin_cohort"][0]["market"] = "TARGET-DERIVED-CHANGE"
        with self.assertRaisesRegex(ConformanceError, "TARGET_CONTENT_CHANGED_COHORT"):
            reconcile_fixed_cohort(changed, model10)

    def test_reconcile_rejects_quarantined_or_missing_observation(self) -> None:
        bound = _bound_row("sobs-fictional-a", "m10loc-fictional-one")
        model10 = _model10_row(bound)
        model10["model09_development_eligible"] = False
        model10["quarantined"] = True
        with self.assertRaisesRegex(ConformanceError, "COMPLETE_COHORT_ACCOUNTING_FAILED"):
            reconcile_fixed_cohort({"eligible_wisconsin_cohort": [bound]}, {"records": [model10]})

    def test_target_projection_allows_only_isolated_sales_and_complete_unique_rows(self) -> None:
        binding = {
            "minimum_target_projection": {
                "default_deny": True,
                "allowed_fields": ["forecast_vintage", "isolated_sales", "source_observation_lineage"],
                "denied_scope": ["Impacted Sales", "every non-Wisconsin target"],
                "rows": [{"source_observation_id": "sobs-fictional", "forecast_vintage": 2024, "isolated_sales": "123.5"}],
            }
        }
        self.assertEqual(_target_rows(binding), {"sobs-fictional": 123.5})
        denied = copy.deepcopy(binding)
        denied["minimum_target_projection"]["rows"][0]["impacted_sales"] = "999"
        with self.assertRaisesRegex(ConformanceError, "TARGET_PROJECTION_SCOPE_VIOLATION"):
            _target_rows(denied)
        missing = copy.deepcopy(binding)
        missing["minimum_target_projection"]["allowed_fields"] = ["forecast_vintage", "isolated_sales", "source_observation_lineage", "impacted_sales"]
        with self.assertRaisesRegex(ConformanceError, "TARGET_SCOPE_MISMATCH"):
            _target_rows(missing)

    def test_public_features_repeat_by_physical_location_and_separate_semantics(self) -> None:
        geo03 = json.loads((ROOT / "config/geo/geo03_internal_point_membership_spatial_spec.json").read_text(encoding="utf-8"))
        transformer = Geo03ProductionTransformer(geo03)
        x_value, y_value = transformer.transform(-89.0, 44.0)
        tract = TractEvidence("55000000001", x_value, y_value, Polygon([(-90, 43), (-88, 43), (-88, 45), (-90, 45), (-90, 43)]), 1000, 100)
        first = {**_bound_row("sobs-fictional-a", "m10loc-fictional-one", 2024), "canonical_latitude": 44.0, "canonical_longitude": -89.0}
        second = {**_bound_row("sobs-fictional-b", "m10loc-fictional-one", 2025), "canonical_latitude": 44.0, "canonical_longitude": -89.0}
        result = build_public_features([first, second], [tract], geo03)
        self.assertEqual(result[0]["features"], result[1]["features"])
        self.assertEqual(result[0]["features"]["households_5mi"], 1000)
        self.assertEqual(result[0]["features"]["inner_household_share_3mi_of_7mi"], 1.0)
        self.assertNotIn("isolated_sales", result[0]["features"])

    def test_noncomputable_public_feature_fails_instead_of_imputing(self) -> None:
        geo03 = json.loads((ROOT / "config/geo/geo03_internal_point_membership_spatial_spec.json").read_text(encoding="utf-8"))
        transformer = Geo03ProductionTransformer(geo03)
        x_value, y_value = transformer.transform(-89.0, 44.0)
        tract = TractEvidence("55000000001", x_value, y_value, Polygon([(-90, 43), (-88, 43), (-88, 45), (-90, 45), (-90, 43)]), 0, 0)
        row = {**_bound_row("sobs-fictional-a", "m10loc-fictional-one"), "canonical_latitude": 44.0, "canonical_longitude": -89.0}
        with self.assertRaisesRegex(ConformanceError, "HOUSEHOLD_FEATURE_NONCOMPUTABLE"):
            build_public_features([row], [tract], geo03)

    def test_protected_resolver_enforces_explicit_handles_and_containment(self) -> None:
        with _temporary_directory() as temporary:
            root = Path(temporary)
            protected = root / "protected"
            protected.mkdir()
            output = protected / "output"
            output.mkdir()
            for name in ("pipe04.json", "pipe04-ready.json", "model10.json", "model10-ready.json", "acs.dat", "tiger.zip"):
                (protected / name).write_text("{}", encoding="utf-8")
            resources = {
                "phandle-pipe04": {"root_handle": "proot-fixture", "relative_path": "pipe04.json", "kind": "pipe04_binding"},
                "phandle-pipe04-ready": {"root_handle": "proot-fixture", "relative_path": "pipe04-ready.json", "kind": "pipe04_ready_marker"},
                "phandle-model10": {"root_handle": "proot-fixture", "relative_path": "model10.json", "kind": "model10_package"},
                "phandle-model10-ready": {"root_handle": "proot-fixture", "relative_path": "model10-ready.json", "kind": "model10_ready_marker"},
                "phandle-acs": {"root_handle": "proot-fixture", "relative_path": "acs.dat", "kind": "accepted_acs_b11001_source"},
                "phandle-tiger": {"root_handle": "proot-fixture", "relative_path": "tiger.zip", "kind": "accepted_tiger_tract_source"},
                "phandle-output": {"root_handle": "proot-fixture", "relative_path": "output", "kind": "model09_output_root"},
            }
            request = {
                "pipe04_binding_handle": "phandle-pipe04", "pipe04_ready_marker_handle": "phandle-pipe04-ready",
                "model10_package_handle": "phandle-model10", "model10_ready_marker_handle": "phandle-model10-ready",
                "acs_source_handle": "phandle-acs", "tiger_source_handle": "phandle-tiger", "model09_output_root_handle": "phandle-output",
            }
            registry_path = root / "registry.json"
            registry = {"registry_id": "MODEL09_PROTECTED_HANDLE_REGISTRY_V1", "version": "1.0.0", "protected_roots": {"proot-fixture": str(protected.resolve())}, "resources": resources, "development_request": request}
            registry_path.write_text(json.dumps(registry), encoding="utf-8")
            resolver = ProtectedHandleResolver.load(registry_path, ROOT)
            self.assertEqual(resolver.resolve("phandle-output", "model09_output_root").path, output.resolve())
            with self.assertRaisesRegex(ConformanceError, "PROTECTED_HANDLE_UNRESOLVED"):
                resolver.resolve("phandle-unknown", "pipe04_binding")
            escaped = copy.deepcopy(registry)
            escaped["resources"]["phandle-acs"]["relative_path"] = "../outside.dat"
            escaped_path = root / "escaped.json"
            escaped_path.write_text(json.dumps(escaped), encoding="utf-8")
            with self.assertRaisesRegex(ConformanceError, "PROTECTED_PATH_TRAVERSAL_REJECTED"):
                ProtectedHandleResolver.load(escaped_path, ROOT).resolve("phandle-acs", "accepted_acs_b11001_source")

    def test_protected_run_is_incomplete_first_ready_last_and_immutable(self) -> None:
        with _temporary_directory() as temporary:
            protected = Path(temporary) / "protected"
            protected.mkdir()
            run = ProtectedDevelopmentRun(protected, ROOT, development_run_id="m09run-fictional")
            self.assertTrue((run.run_dir / "development_state.json").is_file())
            self.assertFalse((run.run_dir / "READY.json").exists())
            run.mark_development_consumed(2)
            consumption = json.loads((run.run_dir / "development_consumption_state.json").read_text(encoding="utf-8"))
            self.assertEqual(consumption["state"], "DEVELOPMENT_CONSUMED")
            semantic = {"development_run_id": run.development_run_id, "state": "ready"}
            run.finalize(semantic)
            self.assertTrue((run.run_dir / "READY.json").is_file())
            with self.assertRaisesRegex(ConformanceError, "MODEL09_RUN_IMMUTABLE"):
                ProtectedDevelopmentRun(protected, ROOT, development_run_id="m09run-fictional")

    def test_disclosure_safe_report_contains_only_aggregate_development_evidence(self) -> None:
        comparison = tuple({"candidate_id": candidate, "grouped_oof": {"spearman": 0.2, "kendall_tau_b": 0.1, "log_rmse": 0.5}, "leave_one_market_out": {"spearman": 0.1}} for candidate in ("baseline_opportunity", "challenger_spatial_concentration", "challenger_spatial_vintage", "challenger_market_sensitive"))
        result = DevelopmentResult("m09run-secret", 63, 2, 41, 20, 14, comparison, {"preferred_candidate_id": None, "conclusion": "NO_CUSTOMER_FIT_MODEL_JUSTIFIED"}, 0.12)
        report = build_disclosure_safe_result(result)
        serialized = json.dumps(report).lower()
        self.assertEqual(report["evidence_role"], "DEVELOPMENT_ONLY_NOT_INDEPENDENT_VALIDATION")
        self.assertNotIn("m09run-secret", serialized)
        self.assertNotIn("coefficient", serialized)
        self.assertNotIn("residual", serialized)

    def test_cli_without_registry_fails_closed_without_discovery(self) -> None:
        stdout = io.StringIO()
        with patch("sys.argv", ["model09-develop", "--repository-root", str(ROOT)]), patch.dict("os.environ", {}, clear=True), redirect_stdout(stdout):
            self.assertEqual(cli.main(), 2)
        report = json.loads(stdout.getvalue())
        self.assertEqual(report["error_code"], "AUTHORITATIVE_ACCESS_REGISTRY_UNRESOLVED")
        self.assertFalse(report["filesystem_discovery_performed"])

    def test_cli_unexpected_failure_does_not_disclose_exception_or_path(self) -> None:
        stdout = io.StringIO()
        with patch("sys.argv", ["model09-develop", "--repository-root", str(ROOT), "--registry", "fictional.json"]), patch("sprouts_customer_geography.model09.cli.load_authorized_registry", return_value=object()), patch("sprouts_customer_geography.model09.cli.execute_protected_development", side_effect=RuntimeError("secret path and value")), redirect_stdout(stdout):
            self.assertEqual(cli.main(), 2)
        report = json.loads(stdout.getvalue())
        self.assertEqual(report["error_code"], "UNEXPECTED_FAIL_CLOSED")
        self.assertNotIn("secret", stdout.getvalue().lower())

    def test_repository_guard_rejects_protected_paths(self) -> None:
        assert_no_protected_tracked_paths(["src/sprouts_customer_geography/model09/modeling.py"])
        with self.assertRaises(ConformanceError):
            assert_no_protected_tracked_paths(["protected/model09/targets.json"])


if __name__ == "__main__":
    unittest.main()
