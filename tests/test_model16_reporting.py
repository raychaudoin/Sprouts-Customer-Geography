"""Synthetic canaries for the protected-to-public aggregate projection."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sprouts_customer_geography.model16.reporting import BASELINE, aggregate_evidence_counts, build_public_report, render_markdown
from sprouts_customer_geography.pipe01.errors import ConformanceError


CANARY = "FICTIONAL_PROTECTED_CANARY_NEVER_PUBLIC"
CATALOG = {"features": [{"feature_id": "fictional_economics", "family": "economics", "baseline": True}, {"feature_id": "fictional_access", "family": "access", "baseline": False}]}


def metric(*, rank=0.4, error=0.2, n=20):
    return {"observations": n + 3, "physical_locations": n, "spearman": rank, "kendall_tau_b": rank * 0.7, "log_rmse": error, "level_mae": 12000.0, "calibration_slope": 0.8, "calibration_intercept": 0.4, "top_quartile_overlap": 0.5, "location_weighted_row_log_rmse": error + 0.01, "location_weighted_row_level_mae": 12500.0, "rank_defined": True, "private_identity": CANARY}


def domains(**kwargs):
    return {domain: metric(**kwargs) for domain in ("pooled", "MI", "WI")}


def fixture(*, challenger="ridge"):
    library = {"selection": {"minimum_rank_improvement": 0.03, "rank_route_max_error_ratio": 1.02, "error_route_max_error_ratio": 0.95, "error_route_min_rank_delta": -0.01, "maximum_state_rank_deterioration": 0.03, "maximum_state_error_ratio": 1.05}, "holdout_evaluation": {"minimum_independent_locations_for_replacement_evidence": 10, "minimum_state_locations_for_domain_claim": 5}}
    diagnostics = []
    for name, architecture in ((BASELINE, "baseline_elastic_net"), ("ridge", "ridge"), ("family_add__access", "ridge")):
        diagnostics.append({"candidate_id": name, "architecture": architecture, "experiment": "family_add" if name.startswith("family_add") else "core_library", "family": "access" if name.startswith("family_add") else None, "status": "EVALUATED", "aggregate_oof": domains(), "fold_metrics": [domains(), domains()], "paired_fold_differences": [{domain: {"spearman": 0.02, "log_rmse": -0.01, "secret": CANARY} for domain in ("pooled", "MI", "WI")}], "stability": {"score": 0.8, "selection_frequency": {CANARY: 1.0}, "effect_standard_deviation": {CANARY: 3.4}, "fold_exclusions": [{CANARY: "private"}]}, "sensitivity": {"worst_error_location_removed": {"candidate": domains(), "baseline": domains()}, "worst_location": CANARY, "each_market_removed": [{"market": CANARY, "candidate": domains(), "baseline": domains()}]}, "outer_parameters": [{"alpha": 0.123456, "private": CANARY}], "features": [CANARY], "qualification_rejections": []})
    diagnostics.append({"candidate_id": "lasso", "architecture": "elastic_net", "experiment": "core_library", "family": None, "status": "UNAVAILABLE", "reason": CANARY + " C:/fictional/private.xlsx"})
    result = SimpleNamespace(diagnostics=diagnostics, selection={"baseline_id": BASELINE, "challenger_id": challenger, "generation": 1, "post_holdout_retuning_allowed": False, "secret": CANARY}, library=library, family_contributions=[{"family": "access", "operation": "family_add", "candidate_id": "family_add__access", "reference_id": "ridge", "differences": {domain: {"spearman": 0.03, "log_rmse": -0.01} for domain in ("pooled", "MI", "WI")}, "paired_fold_differences": [], "interpretation": CANARY}], frozen_models={CANARY: object()}, development_fingerprint=CANARY, fold_audit=[{"groups": [CANARY]}], oof_predictions={CANARY: [987654321.0]})
    return result


def holdout(role, *, challenger="ridge", challenger_error=0.18, challenger_rank=0.45, n=20):
    names = ("all", "independent_development_location", "matched_development_location")
    if role == "pursued_sites":
        names += ("independent_of_all_seedpoints", "matched_seedpoint_location")
    models = {BASELINE: {"subsets": {name: domains(n=n) for name in names}, "predictions": [987654321.0], "private": CANARY}}
    if challenger is not None:
        models[challenger] = {"subsets": {name: domains(rank=challenger_rank, error=challenger_error, n=n) for name in names}, "predictions": [987654321.0]}
    return {"evaluation": {"role": role, "generation": 1, "refit": False, "models": models, "independence_note": CANARY}, "access": {"targets": [987654321.0], "path": CANARY}, "observation_ids": [CANARY], "excluded_count": 2}


class Model16ReportingTests(unittest.TestCase):
    def report(self, **kwargs):
        return build_public_report(fixture(), holdout("temporal_2026"), holdout("pursued_sites"), public_catalog=CATALOG, **kwargs)

    def test_projection_omits_nested_protected_content_and_keeps_every_candidate(self):
        report = self.report()
        encoded = json.dumps(report)
        for forbidden in (CANARY, "987654321", '"outer_parameters"', '"predictions"', '"fingerprint"', '"train_groups"', "private.xlsx", '"effect_standard_deviation"', '"selection_frequency"'):
            self.assertNotIn(forbidden, encoded)
        self.assertEqual(len(report["candidates"]), len(fixture().diagnostics))
        self.assertEqual(report["candidates"][-1]["reason"], "BOUNDED_CANDIDATE_UNAVAILABLE")
        self.assertEqual(len(report["source_family_contributions"]), 1)
        self.assertIn("market_omission_summary", report["candidates"][0]["sensitivity"])
        self.assertNotIn(CANARY, render_markdown(report))

    def test_candidate_and_qualification_labels_fail_closed(self):
        result = fixture()
        result.diagnostics[1]["candidate_id"] = CANARY
        with self.assertRaisesRegex(ConformanceError, "MODEL16_PUBLIC_CANDIDATE_INVALID"):
            build_public_report(result, None, None, public_catalog=CATALOG)

    def test_known_failure_reason_is_retained_but_unknown_exception_is_not(self):
        result = fixture()
        result.diagnostics[-1]["reason"] = "MODEL16_SOLVER_NONCONVERGENCE"
        report = build_public_report(result, None, None, public_catalog=CATALOG)
        self.assertEqual(report["candidates"][-1]["reason"], "MODEL16_SOLVER_NONCONVERGENCE")

    def test_all_location_sensitivity_is_aggregate_only_and_new_gate_is_retained(self):
        result = fixture()
        result.diagnostics[1]["qualification_rejections"] = ["ANY_LOCATION_SENSITIVITY"]
        result.diagnostics[1]["sensitivity"]["all_location_omission_summary"] = {"evaluated_locations": 20, "maximum_error_ratio": 1.04, "minimum_rank_delta": -0.02, "worst_location": CANARY, "each_location_removed": [{"location": CANARY}]}
        report = build_public_report(result, None, None, public_catalog=CATALOG)
        summary = report["candidates"][1]["sensitivity"]["all_location_omission_summary"]
        self.assertEqual(summary, {"evaluated_locations": 20, "maximum_error_ratio": 1.04, "minimum_rank_delta": -0.02})
        self.assertEqual(report["candidates"][1]["qualification_rejections"], ["ANY_LOCATION_SENSITIVITY"])
        self.assertNotIn(CANARY, json.dumps(report))
        result.diagnostics[1]["sensitivity"]["all_location_omission_summary"]["evaluated_locations"] = CANARY
        with self.assertRaisesRegex(ConformanceError, "MODEL16_PUBLIC_NUMBER_INVALID"):
            build_public_report(result, None, None, public_catalog=CATALOG)
        result = fixture()
        result.diagnostics[1]["qualification_rejections"] = [CANARY]
        with self.assertRaisesRegex(ConformanceError, "MODEL16_PUBLIC_QUALIFICATION_INVALID"):
            build_public_report(result, None, None, public_catalog=CATALOG)

    def test_nonfinite_numeric_and_boolean_metric_inputs_are_rejected(self):
        for invalid in (float("nan"), float("inf"), True, CANARY):
            result = fixture()
            result.diagnostics[0]["aggregate_oof"]["pooled"]["log_rmse"] = invalid
            with self.subTest(invalid=type(invalid).__name__), self.assertRaisesRegex(ConformanceError, "MODEL16_PUBLIC_NUMBER_INVALID"):
                build_public_report(result, None, None, public_catalog=CATALOG)

    def test_holdouts_preserve_independent_and_matched_subsets_for_each_state(self):
        report = self.report()
        for candidate in (BASELINE, "ridge"):
            subsets = report["pursued_sites"]["models"][candidate]["subsets"]
            self.assertIn("independent_of_all_seedpoints", subsets)
            self.assertIn("matched_seedpoint_location", subsets)
            self.assertEqual(set(subsets["independent_of_all_seedpoints"]), {"pooled", "MI", "WI"})
            temporal = report["temporal_2026"]["models"][candidate]["subsets"]
            self.assertIn("independent_development_location", temporal)
            self.assertIn("matched_development_location", temporal)

    def test_recommendations_require_both_holdouts_and_domain_evidence(self):
        favorable = self.report()["recommendation"]
        self.assertEqual(favorable["decision"], "REPLACEMENT_SUPPORTED_FOR_REVIEW")
        self.assertFalse(favorable["successor_accepted"])
        self.assertFalse(favorable["merge_authorized"])
        insufficient = build_public_report(fixture(), holdout("temporal_2026"), holdout("pursued_sites", n=4), public_catalog=CATALOG)
        self.assertEqual(insufficient["recommendation"]["decision"], "CONTINUE_DEVELOPMENT")
        collapse = holdout("pursued_sites")
        collapse["evaluation"]["models"]["ridge"]["subsets"]["independent_of_all_seedpoints"]["WI"]["log_rmse"] = 0.5
        failed = build_public_report(fixture(), holdout("temporal_2026"), collapse, public_catalog=CATALOG)
        self.assertIn("PURSUED_INDEPENDENT_WI_NONINFERIORITY_NOT_CONFIRMED", failed["recommendation"]["reasons"])
        pending = build_public_report(fixture(), None, None, public_catalog=CATALOG)
        self.assertEqual(pending["recommendation"]["reasons"], ["FINAL_EVALUATION_INCOMPLETE"])
        matched_only = holdout("temporal_2026")
        for model in matched_only["evaluation"]["models"].values():
            model["subsets"]["independent_development_location"] = None
        no_independent_temporal = build_public_report(fixture(), matched_only, holdout("pursued_sites"), public_catalog=CATALOG)
        self.assertIn("TEMPORAL_INDEPENDENT_INSUFFICIENT_LOCATIONS", no_independent_temporal["recommendation"]["reasons"])

    def test_no_challenger_preserves_model13_without_inventing_evaluation(self):
        report = build_public_report(fixture(challenger=None), holdout("temporal_2026", challenger=None), holdout("pursued_sites", challenger=None), public_catalog=CATALOG)
        self.assertEqual(report["recommendation"]["decision"], "RETAIN_MODEL13")
        self.assertIsNone(report["selection"]["challenger_id"])
        self.assertEqual(set(report["pursued_sites"]["models"]), {BASELINE})

    def test_evidence_counts_group_privately_and_never_sum_independence_across_years(self):
        rows = [{"state": "MI", "forecast_year": year, "evidence_class": "SEED_POINT", "role": "development", "physical_location_id": CANARY, "target": 987654321.0} for year in (2024, 2025)]
        counts = aggregate_evidence_counts(rows)
        self.assertEqual([item["physical_locations"] for item in counts], [1, 1])
        self.assertNotIn(CANARY, json.dumps(counts))
        self.assertNotIn("target", json.dumps(counts))

    def test_missingness_accepts_only_public_catalog_and_role_counts(self):
        report = self.report(public_missingness={"fictional_access": {"development": 3, "temporal_test": 1}})
        self.assertEqual(report["feature_missingness_by_role"]["fictional_access"]["development"], 3)
        stratified = self.report(public_missingness={"fictional_access": {"development": {"all": 3, "MI": 1, "WI": 2}}})
        self.assertEqual(stratified["feature_missingness_by_role"]["fictional_access"]["development"]["WI"], 2)
        with self.assertRaisesRegex(ConformanceError, "MODEL16_PUBLIC_MISSINGNESS_INVALID"):
            self.report(public_missingness={CANARY: {"development": 1}})
        with self.assertRaisesRegex(ConformanceError, "MODEL16_PUBLIC_MISSINGNESS_INVALID"):
            self.report(public_missingness={"fictional_access": {CANARY: 1}})


if __name__ == "__main__":
    unittest.main()
