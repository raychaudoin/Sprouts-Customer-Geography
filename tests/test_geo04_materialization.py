"""GEO-04 public spatial authority validation; no protected context inputs are used."""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import tempfile
import unittest

from sprouts_customer_geography.geo04 import (
    CONTEXT_SPEC_ID,
    DERIVATION_ID,
    DISTANCE_SPEC_ID,
    MARKETS,
    MEMBERSHIP_SPEC_ID,
    TIGER_MANIFEST_ID,
    TIGER_SHA256,
    derive_ordered_geoids,
    materialize,
    tiger_rows_from_pinned_zip,
    validate_context_specification,
    validate_inventory_document,
    validate_membership_specification,
)
from sprouts_customer_geography.pipe01.errors import ConformanceError


ROOT = Path(__file__).resolve().parents[1]


def load(relative: str):
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


class Geo04MaterializationTests(unittest.TestCase):
    def setUp(self):
        self.derivation = load("config/geo/canonical_tract_inventory_derivation.json")
        self.inventories = {
            "milwaukee": load("config/geo/canonical_tract_inventory_milwaukee.json"),
            "madison": load("config/geo/canonical_tract_inventory_madison.json"),
        }
        self.context = load("config/geo/geo02_validation_context_spatial_spec.json")
        self.membership = load("config/geo/geo03_internal_point_membership_spatial_spec.json")

    def test_authority_artifacts_validate_and_hash_deterministically(self):
        self.assertEqual(self.derivation["artifact_id"], DERIVATION_ID)
        self.assertEqual(self.derivation["data_authority"]["tiger_manifest_id"], TIGER_MANIFEST_ID)
        self.assertEqual(self.derivation["data_authority"]["tiger_source_sha256"], TIGER_SHA256)
        for market, inventory in self.inventories.items():
            self.assertEqual(validate_inventory_document(inventory, self.derivation), inventory["content_sha256"])
            self.assertEqual(inventory["tract_count"], MARKETS[market]["qa_expected_count"])
            self.assertTrue(inventory["qa_count_matches"])
        self.assertEqual(validate_context_specification(self.context, self.inventories, self.derivation), self.context["content_sha256"])
        self.assertEqual(validate_membership_specification(self.membership, self.context), self.membership["content_sha256"])

    def test_inventory_fail_closed_for_wrong_county_order_hash_or_duplicate(self):
        wrong_county = copy.deepcopy(self.inventories["milwaukee"])
        wrong_county["market_configuration"]["ordered_county_allow_list"] = ["55079"]
        with self.assertRaisesRegex(ConformanceError, "GEO04_CONTENT_HASH_MISMATCH|GEO04_COUNTY_CONFIG_INVALID"):
            validate_inventory_document(wrong_county, self.derivation)
        bad_order = copy.deepcopy(self.inventories["madison"])
        bad_order["ordered_geoids"] = list(reversed(bad_order["ordered_geoids"]))
        with self.assertRaisesRegex(ConformanceError, "GEO04_CONTENT_HASH_MISMATCH|GEO04_INVENTORY_ORDER_MISMATCH"):
            validate_inventory_document(bad_order, self.derivation)
        duplicate = copy.deepcopy(self.inventories["madison"])
        duplicate["ordered_geoids"][1] = duplicate["ordered_geoids"][0]
        with self.assertRaisesRegex(ConformanceError, "GEO04_CONTENT_HASH_MISMATCH|GEO04_DUPLICATE_CANONICAL_GEOID"):
            validate_inventory_document(duplicate, self.derivation)
        bad_hash = copy.deepcopy(self.inventories["milwaukee"])
        bad_hash["inventory_sha256"] = "0" * 64
        with self.assertRaisesRegex(ConformanceError, "GEO04_CONTENT_HASH_MISMATCH|GEO04_INVENTORY_HASH_MISMATCH"):
            validate_inventory_document(bad_hash, self.derivation)

    def test_derivation_rejects_malformed_duplicate_and_missing_county_rows(self):
        rows = [
            {"STATEFP": "55", "COUNTYFP": "079", "TRACTCE": "000100", "GEOID": "55079000100"},
            {"STATEFP": "55", "COUNTYFP": "089", "TRACTCE": "000100", "GEOID": "55089000100"},
        ]
        with self.assertRaisesRegex(ConformanceError, "GEO04_COUNTY_RECONCILIATION_FAILED"):
            derive_ordered_geoids(rows, ["55079", "55089", "55131"])
        duplicate = rows + [rows[0]]
        with self.assertRaisesRegex(ConformanceError, "GEO04_DUPLICATE_CANONICAL_GEOID"):
            derive_ordered_geoids(duplicate, ["55079", "55089"])
        malformed = copy.deepcopy(rows)
        malformed[0]["GEOID"] = "55079000101"
        with self.assertRaisesRegex(ConformanceError, "GEO04_GEOID_COMPONENT_MISMATCH"):
            derive_ordered_geoids(malformed, ["55079", "55089"])

    def test_geo02_context_and_geo03_operation_fail_closed(self):
        wrong_context = copy.deepcopy(self.context)
        wrong_context["version"] = "2.0.0"
        with self.assertRaisesRegex(ConformanceError, "GEO04_CONTENT_HASH_MISMATCH|GEO02_CONTEXT_VERSION_MISMATCH"):
            validate_context_specification(wrong_context, self.inventories, self.derivation)
        wrong_operation = copy.deepcopy(self.membership)
        wrong_operation["transformation"]["operation"]["target_crs"] = "EPSG:3857"
        with self.assertRaisesRegex(ConformanceError, "GEO04_CONTENT_HASH_MISMATCH|GEO03_OPERATION_SEMANTICS_MISMATCH"):
            validate_membership_specification(wrong_operation, self.context)
        wrong_fingerprint = copy.deepcopy(self.membership)
        wrong_fingerprint["transformation"]["operation_fingerprint_sha256"] = "0" * 64
        with self.assertRaisesRegex(ConformanceError, "GEO04_CONTENT_HASH_MISMATCH|GEO03_OPERATION_FINGERPRINT_MISMATCH"):
            validate_membership_specification(wrong_fingerprint, self.context)
        wrong_lineage = copy.deepcopy(self.membership)
        wrong_lineage["geo02_lineage"]["subordinate_to_context_specification"]["content_sha256"] = "0" * 64
        with self.assertRaisesRegex(ConformanceError, "GEO04_CONTENT_HASH_MISMATCH|GEO03_CONTEXT_LINEAGE_MISMATCH"):
            validate_membership_specification(wrong_lineage, self.context)

    def test_geo03_semantics_preserve_accepted_boundaries_and_authority(self):
        operation = self.membership["transformation"]["operation"]
        self.assertEqual(operation["source_crs"], "EPSG:4269")
        self.assertEqual(operation["target_crs"], "EPSG:5070")
        self.assertEqual(operation["logical_input_axis_order"], ["longitude", "latitude"])
        self.assertEqual(self.membership["validation_membership_distance"]["artifact_id"], DISTANCE_SPEC_ID)
        boundary = self.membership["boundary_and_radius_binding"]
        self.assertEqual(boundary["comparison"], "distance_m <= radius_m")
        self.assertFalse(boundary["epsilon_or_snap_or_rounding_permitted"])
        self.assertEqual(boundary["owner"], "MODEL")
        self.assertEqual(boundary["radii_m"], [4828.032, 8046.72, 11265.408])
        self.assertEqual(self.membership["geo02_lineage"]["subordinate_to_context_specification"]["artifact_id"], CONTEXT_SPEC_ID)
        self.assertNotIn("membership_jaccard", json.dumps(self.membership, sort_keys=True).lower())

    def test_repository_safe_artifacts_reference_schemas_and_contain_no_instances(self):
        artifacts = [self.derivation, *self.inventories.values(), self.context, self.membership]
        for artifact in artifacts:
            schema_path = ROOT / "config/geo" / artifact["$schema"]
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
            self.assertTrue(set(schema["required"]) <= set(artifact))
        context_text = json.dumps(self.context, sort_keys=True).lower()
        self.assertNotIn('"context_instance_id"', context_text)
        self.assertNotIn('"anchor_latitude"', context_text)
        self.assertNotIn('"anchor_longitude"', context_text)
        self.assertNotIn('"prediction', context_text)
        self.assertNotIn('"residual', context_text)

    def test_exact_pinned_source_regenerates_committed_artifacts_when_supplied(self):
        source_value = os.environ.get("GEO04_PINNED_TIGER_ZIP")
        if not source_value:
            self.skipTest("GEO04_PINNED_TIGER_ZIP not supplied; raw public source is deliberately not tracked")
        source_zip = Path(source_value)
        tiger_manifest = load("data/manifests/tiger_2024_wisconsin_tract.source_manifest.json")
        rows = tiger_rows_from_pinned_zip(source_zip, tiger_manifest)
        for market, inventory in self.inventories.items():
            self.assertEqual(derive_ordered_geoids(rows, MARKETS[market]["county_allow_list"]), inventory["ordered_geoids"])
        with tempfile.TemporaryDirectory() as temporary:
            output_root = Path(temporary) / "geo"
            regenerated = materialize(source_zip, ROOT, output_root)
            self.assertEqual(regenerated["canonical_tract_inventory_milwaukee.json"], self.inventories["milwaukee"])
            self.assertEqual(regenerated["canonical_tract_inventory_madison.json"], self.inventories["madison"])
            self.assertEqual(regenerated["geo02_validation_context_spatial_spec.json"], self.context)
            self.assertEqual(regenerated["geo03_internal_point_membership_spatial_spec.json"], self.membership)


if __name__ == "__main__":
    unittest.main()
