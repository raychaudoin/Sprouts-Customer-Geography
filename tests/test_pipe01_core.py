from __future__ import annotations

import hashlib
import math
import unittest

from sprouts_customer_geography.constants import RADII_M, RADIUS_3_M, RADIUS_5_M, RADIUS_7_M
from sprouts_customer_geography.pipe01.errors import ConformanceError
from sprouts_customer_geography.pipe01.pipeline import PretargetPipeline, reject_target_inputs
from sprouts_customer_geography.pipe01.sources import verify_pinned_source
from sprouts_customer_geography.pipe01.spatial import ordinary_membership, parse_internal_point, planar_distance_m


class SyntheticTransformer:
    source_crs = "EPSG:4269"
    target_crs = "EPSG:5070"
    operation_fingerprint = "synthetic-test-operation-v1"

    def __init__(self):
        self.calls: list[tuple[float, float]] = []

    def transform(self, longitude: float, latitude: float) -> tuple[float, float]:
        self.calls.append((longitude, latitude))
        return longitude * 1000.0, latitude * 1000.0


def inventory(pipeline: PretargetPipeline, geoids: list[str] | None = None):
    return pipeline.build_inventory("fictional_market", geoids or ["00000000001", "00000000002"], {"synthetic": True}, qa_expected_count=2)


def evidence(pipeline: PretargetPipeline, inv, first_lon="0", second_lon="6"):
    return pipeline.build_internal_point_evidence(
        inv,
        [
            {"market_id": "fictional_market", "tract_geoid": "00000000001", "INTPTLAT": "0.000", "INTPTLON": first_lon, "source_lineage": {"synthetic": True}},
            {"market_id": "fictional_market", "tract_geoid": "00000000002", "INTPTLAT": "0", "INTPTLON": second_lon, "source_lineage": {"synthetic": True}},
        ],
    )


def context(anchor="00000000001"):
    return {"market_id": "fictional_market", "context_spec_id": "geo02-synthetic-v1", "context_instance_id": "fictional-context-a", "anchor_tract_geoid": anchor, "anchor_latitude": "0", "anchor_longitude": "0"}


class SourceAndInventoryTests(unittest.TestCase):
    def setUp(self):
        self.transformer = SyntheticTransformer()
        self.pipeline = PretargetPipeline(self.transformer.operation_fingerprint, self.transformer)

    def test_pinned_source_checksum_acceptance(self):
        payload = b"fictional public source bytes"
        manifest = {"source_id": "synthetic", "source_name": "Synthetic", "accepted_vintage": "v1", "source_reference": "fixture", "byte_sha256": hashlib.sha256(payload).hexdigest(), "schema_version": "v1", "acquisition_state": "acquired", "lineage": {}}
        self.assertEqual(verify_pinned_source(manifest, payload)["checksum_state"], "accepted")

    def test_checksum_mismatch_rejected_without_substitution(self):
        manifest = {"source_id": "synthetic", "source_name": "Synthetic", "accepted_vintage": "v1", "source_reference": "fixture", "byte_sha256": "0" * 64, "schema_version": "v1", "acquisition_state": "acquired", "lineage": {}}
        with self.assertRaisesRegex(ConformanceError, "SOURCE_CHECKSUM_MISMATCH"):
            verify_pinned_source(manifest, b"different")

    def test_unacquired_source_rejected(self):
        manifest = {"source_id": "synthetic", "source_name": "Synthetic", "accepted_vintage": "v1", "source_reference": "fixture", "byte_sha256": "0" * 64, "schema_version": "v1", "acquisition_state": "not_acquired", "lineage": {}}
        with self.assertRaisesRegex(ConformanceError, "SOURCE_NOT_ACQUIRED"):
            verify_pinned_source(manifest, b"")

    def test_inventory_is_deterministic_and_count_is_qa_only(self):
        left = self.pipeline.build_inventory("fictional_market", ["00000000002", "00000000001"], {"synthetic": True}, 99)
        right = self.pipeline.build_inventory("fictional_market", ["00000000001", "00000000002"], {"synthetic": True}, 99)
        self.assertEqual(left["inventory_digest"], right["inventory_digest"])
        self.assertEqual([row["tract_geoid"] for row in left["rows"]], ["00000000001", "00000000002"])
        self.assertFalse(left["qa_count_matches"])
        self.assertEqual(left["readiness_basis"], "ordered_inventory_digest_and_row_validation")

    def test_duplicate_geoid_rejected(self):
        with self.assertRaisesRegex(ConformanceError, "DUPLICATE_GEOID"):
            self.pipeline.build_inventory("fictional_market", ["00000000001", "00000000001"], {}, 2)


class CoordinateAndMembershipTests(unittest.TestCase):
    def setUp(self):
        self.transformer = SyntheticTransformer()
        self.pipeline = PretargetPipeline(self.transformer.operation_fingerprint, self.transformer)
        self.inventory = inventory(self.pipeline)

    def test_raw_internal_point_strings_preserved(self):
        result = evidence(self.pipeline, self.inventory, first_lon="-01.2500")
        row = result["rows"][0]
        self.assertEqual(row["raw_INTPTLAT"], "0.000")
        self.assertEqual(row["raw_INTPTLON"], "-01.2500")
        self.assertEqual(row["parsed_longitude"], -1.25)

    def test_coordinate_states_preserve_missing_invalid_and_range(self):
        self.assertEqual(parse_internal_point(None, "1").coordinate_state, "missing")
        self.assertEqual(parse_internal_point("x", "1").coordinate_state, "invalid_parse")
        self.assertEqual(parse_internal_point("91", "1").coordinate_state, "invalid_range")
        self.assertEqual(parse_internal_point("nan", "1").coordinate_state, "invalid_nonfinite")

    def test_transform_identity_is_exact(self):
        with self.assertRaisesRegex(ConformanceError, "TRANSFORM_FINGERPRINT_MISMATCH"):
            PretargetPipeline("accepted-other-operation", self.transformer)

    def test_nonfinite_transform_output_is_noncomputable(self):
        class NonfiniteTransformer(SyntheticTransformer):
            def transform(self, longitude: float, latitude: float):
                return math.inf, 0.0

        transformer = NonfiniteTransformer()
        pipeline = PretargetPipeline(transformer.operation_fingerprint, transformer)
        inv = pipeline.build_inventory("fictional_market", ["00000000001"], {}, 1)
        result = pipeline.build_internal_point_evidence(inv, [{"market_id": "fictional_market", "tract_geoid": "00000000001", "INTPTLAT": "0", "INTPTLON": "0"}])
        self.assertEqual(result["rows"][0]["transformation_state"], "noncomputable")

    def test_longitude_latitude_order_is_normalized(self):
        inv = self.pipeline.build_inventory("fictional_market", ["00000000001"], {}, 1)
        self.pipeline.build_internal_point_evidence(inv, [{"market_id": "fictional_market", "tract_geoid": "00000000001", "INTPTLAT": "2", "INTPTLON": "-3"}])
        self.assertEqual(self.transformer.calls[-1], (-3.0, 2.0))

    def test_planar_euclidean_distance(self):
        self.assertEqual(planar_distance_m((0, 0), (3, 4)), 5.0)

    def test_exact_radii_are_frozen(self):
        self.assertEqual(RADII_M, (4828.032, 8046.72, 11265.408))

    def test_exact_equality_is_inside_without_epsilon(self):
        self.assertTrue(ordinary_membership(RADIUS_5_M, RADIUS_5_M))
        self.assertFalse(ordinary_membership(math.nextafter(RADIUS_5_M, math.inf), RADIUS_5_M))

    def test_nested_memberships_and_grain(self):
        result = self.pipeline.build_membership(self.inventory, evidence(self.pipeline, self.inventory), context())
        self.assertEqual(len(result["rows"]), 6)
        keys = {(r["membership_spec_id"], r["context_instance_id"], r["radius_m"], r["tract_geoid"]) for r in result["rows"]}
        self.assertEqual(len(keys), 6)
        second = {r["radius_m"]: r["final_membership"] for r in result["rows"] if r["tract_geoid"] == "00000000002"}
        self.assertEqual(second, {RADIUS_3_M: False, RADIUS_5_M: True, RADIUS_7_M: True})

    def test_membership_rechecks_transform_lineage(self):
        tract_evidence = evidence(self.pipeline, self.inventory)
        tract_evidence["rows"][0]["transformation_fingerprint"] = "wrong"
        with self.assertRaisesRegex(ConformanceError, "EVIDENCE_TRANSFORM_FINGERPRINT_MISMATCH"):
            self.pipeline.build_membership(self.inventory, tract_evidence, context())

    def test_nesting_violation_invalidates_run(self):
        rows = []
        for radius, member in zip(RADII_M, [True, False, True]):
            rows.append({"context_instance_id": "x", "tract_geoid": "00000000001", "radius_m": radius, "final_membership": member})
        with self.assertRaisesRegex(ConformanceError, "MEMBERSHIP_NESTING_VIOLATION"):
            self.pipeline.validate_nesting(rows)

    def test_ordinary_anchor_has_no_forced_event(self):
        rows = self.pipeline.build_membership(self.inventory, evidence(self.pipeline, self.inventory), context())["rows"]
        anchor_rows = [row for row in rows if row["tract_geoid"] == "00000000001"]
        self.assertTrue(all(row["ordinary_membership"] is True and row["forced_anchor_inclusion"] is False for row in anchor_rows))

    def test_anchor_outside_is_forced_until_ordinary_inside(self):
        rows = self.pipeline.build_membership(self.inventory, evidence(self.pipeline, self.inventory, first_lon="9"), context())["rows"]
        anchor = {row["radius_m"]: row for row in rows if row["tract_geoid"] == "00000000001"}
        self.assertTrue(anchor[RADIUS_3_M]["forced_anchor_inclusion"])
        self.assertTrue(anchor[RADIUS_5_M]["forced_anchor_inclusion"])
        self.assertFalse(anchor[RADIUS_7_M]["forced_anchor_inclusion"])

    def test_anchor_internal_point_failure_exception(self):
        result = self.pipeline.build_membership(self.inventory, evidence(self.pipeline, self.inventory, first_lon=None), context())
        anchor = [row for row in result["rows"] if row["tract_geoid"] == "00000000001"]
        self.assertTrue(all(row["final_membership"] is True and row["distance_computable"] is False for row in anchor))

    def test_missing_anchor_identity_fails_closed(self):
        bad = context(anchor=None)
        with self.assertRaisesRegex(ConformanceError, "ANCHOR_IDENTITY_MISSING_OR_AMBIGUOUS"):
            self.pipeline.build_membership(self.inventory, evidence(self.pipeline, self.inventory), bad)

    def test_absent_anchor_tract_fails_closed(self):
        with self.assertRaisesRegex(ConformanceError, "ANCHOR_TRACT_ABSENT"):
            self.pipeline.build_membership(self.inventory, evidence(self.pipeline, self.inventory), context("00000000999"))

    def test_structural_market_mismatch_fails_closed(self):
        rows = [{"market_id": "wrong_market", "tract_geoid": "00000000001", "INTPTLAT": "0", "INTPTLON": "0"}, {"market_id": "fictional_market", "tract_geoid": "00000000002", "INTPTLAT": "0", "INTPTLON": "1"}]
        with self.assertRaisesRegex(ConformanceError, "STRUCTURAL_MARKET_MISMATCH"):
            self.pipeline.build_internal_point_evidence(self.inventory, rows)

    def test_nonanchor_coordinate_failure_remains_noncomputable(self):
        result = self.pipeline.build_membership(self.inventory, evidence(self.pipeline, self.inventory, second_lon=None), context())
        other = [row for row in result["rows"] if row["tract_geoid"] == "00000000002"]
        self.assertTrue(all(row["ordinary_membership"] is None and row["final_membership"] is None for row in other))

    def test_target_fields_are_rejected(self):
        for key in ("target_value", "forecast", "kendall_tau_b", "residual"):
            with self.assertRaisesRegex(ConformanceError, "TARGET_INPUT_REJECTED"):
                reject_target_inputs({"nested": [{key: 1}]})


if __name__ == "__main__":
    unittest.main()
