from __future__ import annotations

import unittest

from sprouts_customer_geography.constants import RADII_M, RADIUS_5_M
from sprouts_customer_geography.pipe01.errors import ConformanceError
from sprouts_customer_geography.pipe01.pipeline import PretargetPipeline

from tests.test_pipe01_core import SyntheticTransformer, context, evidence, inventory


def acs_rows(second_status="valid", second_estimate=200):
    return [
        {"tract_geoid": "00000000001", "estimate": 100, "moe": 10, "annotation": None, "status": "valid"},
        {"tract_geoid": "00000000002", "estimate": second_estimate, "moe": 20, "annotation": "fictional", "status": second_status},
    ]


def spatial(completeness: float, jaccard: float = 0.0):
    return {
        "context_spec_id": "geo02-synthetic-v1",
        "context_instance_id": "fictional-context-a",
        "market_edge_state": "synthetic_complete",
        "geometric_completeness": completeness,
        "geometric_jaccard": jaccard,
        "spatial_components": {"synthetic": True},
        "geo02_lineage": {"synthetic": True},
    }


class AggregationTests(unittest.TestCase):
    def setUp(self):
        transformer = SyntheticTransformer()
        self.pipeline = PretargetPipeline(transformer.operation_fingerprint, transformer)
        self.inventory = inventory(self.pipeline)
        self.membership = self.pipeline.build_membership(self.inventory, evidence(self.pipeline, self.inventory), context())

    def test_acs_estimate_moe_annotation_status_are_separate(self):
        acs = self.pipeline.build_acs_evidence(self.inventory, acs_rows(), {"vintage": "synthetic"})
        row = acs["rows"][1]
        self.assertEqual(row["total_household_estimate"], 200)
        self.assertEqual(row["total_household_moe"], 20)
        self.assertEqual(row["annotation"], "fictional")
        self.assertEqual(row["status"], "valid")
        self.assertTrue(row["moe_valid"])
        self.assertTrue(row["evidence_valid"])

    def test_missing_suppressed_inapplicable_never_become_zero(self):
        for status in ("missing", "suppressed", "inapplicable", "invalid"):
            acs = self.pipeline.build_acs_evidence(self.inventory, acs_rows(status, None), {"synthetic": True})
            row = acs["rows"][1]
            self.assertIsNone(row["total_household_estimate"])
            self.assertFalse(row["estimate_valid"])

    def test_unknown_acs_status_fails_closed(self):
        with self.assertRaisesRegex(ConformanceError, "ACS_STATUS_INVALID"):
            self.pipeline.build_acs_evidence(self.inventory, acs_rows("mystery", 200), {})

    def test_invalid_acs_on_member_prevents_complete_total(self):
        acs = self.pipeline.build_acs_evidence(self.inventory, acs_rows("suppressed", None), {})
        aggregate = self.pipeline.aggregate_households(self.membership, acs)
        primary = next(row for row in aggregate["rows"] if row["radius_m"] == RADIUS_5_M)
        self.assertEqual(primary["calculation_state"], "noncomputable")
        self.assertIsNone(primary["household_opportunity"])

    def test_missing_moe_on_member_prevents_complete_total(self):
        rows = acs_rows()
        rows[1]["moe"] = None
        acs = self.pipeline.build_acs_evidence(self.inventory, rows, {})
        aggregate = self.pipeline.aggregate_households(self.membership, acs)
        primary = next(row for row in aggregate["rows"] if row["radius_m"] == RADIUS_5_M)
        self.assertEqual(primary["calculation_state"], "noncomputable")

    def test_invalid_acs_on_nonmember_does_not_poison_small_context(self):
        acs = self.pipeline.build_acs_evidence(self.inventory, acs_rows("suppressed", None), {})
        aggregate = self.pipeline.aggregate_households(self.membership, acs)
        small = next(row for row in aggregate["rows"] if row["radius_m"] == RADII_M[0])
        self.assertEqual(small["calculation_state"], "complete")
        self.assertEqual(small["household_opportunity"], 100)

    def test_noncomputable_membership_prevents_all_affected_totals(self):
        membership = self.pipeline.build_membership(self.inventory, evidence(self.pipeline, self.inventory, second_lon=None), context())
        acs = self.pipeline.build_acs_evidence(self.inventory, acs_rows(), {})
        aggregate = self.pipeline.aggregate_households(membership, acs)
        self.assertTrue(all(row["calculation_state"] == "noncomputable" for row in aggregate["rows"]))

    def test_whole_tract_aggregation_once(self):
        acs = self.pipeline.build_acs_evidence(self.inventory, acs_rows(), {})
        aggregate = self.pipeline.aggregate_households(self.membership, acs)
        primary = next(row for row in aggregate["rows"] if row["radius_m"] == RADIUS_5_M)
        self.assertEqual(primary["aggregation_method"], "whole_tract_final_membership_once")
        self.assertEqual(primary["member_count"], 2)
        self.assertEqual(primary["household_opportunity"], 300)

    def test_baseline_is_only_authorized_raw_5_mile_candidate(self):
        acs = self.pipeline.build_acs_evidence(self.inventory, acs_rows(), {})
        aggregate = self.pipeline.aggregate_households(self.membership, acs)
        spec = {"model_spec_id": "model05-synthetic", "model_spec_version": "v1", "preregistration_id": "prereg-synthetic", "preregistration_version": "v1", "prediction_semantics": "raw_5_mile_whole_tract_household_opportunity", "accepted": True}
        baseline = self.pipeline.build_baseline_prediction(aggregate, spec)
        self.assertEqual(baseline["radius_m"], RADIUS_5_M)
        self.assertEqual(baseline["prediction_candidate"], 300)
        self.assertNotIn("target", baseline)

    def test_unaccepted_or_parameterized_model_spec_fails(self):
        acs = self.pipeline.build_acs_evidence(self.inventory, acs_rows(), {})
        aggregate = self.pipeline.aggregate_households(self.membership, acs)
        base = {"model_spec_id": "m", "model_spec_version": "v", "preregistration_id": "p", "preregistration_version": "v", "prediction_semantics": "raw_5_mile_whole_tract_household_opportunity", "accepted": False}
        with self.assertRaisesRegex(ConformanceError, "MODEL_SPEC_NOT_ACCEPTED"):
            self.pipeline.build_baseline_prediction(aggregate, base)
        base["accepted"] = True
        base["numerical_parameters"] = {"coefficient": 1}
        with self.assertRaisesRegex(ConformanceError, "UNAUTHORIZED_MODEL_PARAMETERS"):
            self.pipeline.build_baseline_prediction(aggregate, base)

    def test_geo02_spatial_evidence_and_jaccard_stress(self):
        result = self.pipeline.validate_spatial_evidence(spatial(0.95, 0.25))
        self.assertTrue(result["jaccard_dependence_stress"])
        with self.assertRaisesRegex(ConformanceError, "COMPETING_MEMBERSHIP_JACCARD_REJECTED"):
            self.pipeline.validate_spatial_evidence({**spatial(0.95), "membership_jaccard": 0.1})

    def test_completeness_boundaries(self):
        acs = self.pipeline.build_acs_evidence(self.inventory, acs_rows(), {})
        household = self.pipeline.aggregate_households(self.membership, acs)
        expected = [(0.90, "primary_statistic_eligible"), (0.75, "secondary_truncated_stratum"), (0.749999, "qa_only")]
        for completeness, status in expected:
            spatial_result = self.pipeline.validate_spatial_evidence(spatial(completeness))
            self.assertEqual(self.pipeline.build_eligibility(spatial_result, household, False)["eligibility_status"], status)

    def test_quarantine_overrides_eligibility(self):
        acs = self.pipeline.build_acs_evidence(self.inventory, acs_rows(), {})
        household = self.pipeline.aggregate_households(self.membership, acs)
        result = self.pipeline.build_eligibility(self.pipeline.validate_spatial_evidence(spatial(1.0)), household, True)
        self.assertEqual(result["eligibility_status"], "quarantined")
        self.assertIn("MODEL04_QUARANTINE", result["reason_codes"])


if __name__ == "__main__":
    unittest.main()
