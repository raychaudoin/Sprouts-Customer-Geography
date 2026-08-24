"""GEO-05 Michigan statewide public spatial-support conformance."""

from __future__ import annotations

import copy
from contextlib import contextmanager
from dataclasses import replace
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import unittest
import uuid

from shapely.geometry import Point, box

from sprouts_customer_geography.geo04 import inventory_digest, validate_membership_specification
from sprouts_customer_geography.geo05.contract import (
    ANCHOR_EVIDENCE_SCHEMA_ID,
    DEFAULT_RADII_M,
    EXPECTED_INVENTORY_SHA256,
    EXPECTED_TRACT_COUNT,
    INVENTORY_ID,
    SPECIFICATION_ID,
    load_authority,
)
from sprouts_customer_geography.geo05.materialization import (
    SpatialTract,
    SupportPackage,
    compare_materializations,
    evaluate_anchor_package,
    load_support_package,
    materialize_real,
    verify_data04_ready,
)
from sprouts_customer_geography.pipe01.canonical import content_digest
from sprouts_customer_geography.pipe01.errors import ConformanceError
from sprouts_customer_geography.pipe01.production import Geo03ProductionTransformer
from sprouts_customer_geography.pipe01.spatial import ordinary_membership, parse_internal_point, project_internal_point


ROOT = Path(__file__).resolve().parents[1]
AUTHORIZATION_BASE = "431e2f2a1aefcf877b7312bd4e7d16dccecb3da5"


def load(relative: str):
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


@contextmanager
def temporary_directory():
    base = Path(os.environ.get("GEO05_TEST_TEMP_ROOT") or ROOT / "outputs" / "geo05-test-tmp")
    base.mkdir(parents=True, exist_ok=True)
    path = base / ("case-" + uuid.uuid4().hex)
    path.mkdir()
    try:
        yield str(path)
    finally:
        shutil.rmtree(path, ignore_errors=True)


class Geo05SpatialSupportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.authority = load_authority(ROOT)
        cls.transformer = Geo03ProductionTransformer(cls.authority.geo03)

    def _synthetic_package(self) -> tuple[SupportPackage, float, float]:
        latitude, longitude = 42.5, -84.5
        projected = self.transformer.transform(longitude, latitude)
        geoids = ["26001000100", "26001000200", "26001000300", "26001000400"]
        source_geometries = [
            box(-85.0, 42.0, -84.0, 43.0),
            box(-83.9, 42.0, -83.8, 42.1),
            box(-83.7, 42.0, -83.6, 42.1),
            box(-83.5, 42.0, -83.4, 42.1),
        ]
        offsets = [10_000.0, 50.0, 200.0, 300.0]
        tracts = tuple(
            SpatialTract(
                geoid=geoid,
                latitude=latitude if index == 0 else 42.05,
                longitude=longitude if index == 0 else -83.85 + index * 0.2,
                internal_x_m=projected[0] + offsets[index],
                internal_y_m=projected[1],
                source_geometry=source_geometries[index],
            )
            for index, geoid in enumerate(geoids)
        )
        specification = copy.deepcopy(self.authority.specification)
        specification["state_scope"]["tract_count"] = len(tracts)
        specification["statewide_inventory"]["tract_count"] = len(tracts)
        specification["statewide_inventory"]["inventory_sha256"] = inventory_digest(geoids)
        synthetic_authority = replace(self.authority, specification=specification)
        support = Point(projected).buffer(150.0, quad_segs=64)
        return SupportPackage(synthetic_authority, tracts, support, self.transformer.runtime_provenance, {}), latitude, longitude

    def test_specification_binds_exact_michigan_source_and_inventory(self) -> None:
        specification = self.authority.specification
        self.assertEqual(specification["artifact_id"], SPECIFICATION_ID)
        self.assertEqual(specification["status"], "proposed_awaiting_acceptance")
        self.assertEqual(specification["state_scope"]["state_fips"], "26")
        self.assertTrue(specification["state_scope"]["statewide"])
        self.assertFalse(specification["state_scope"]["named_market_inventory"])
        self.assertEqual(specification["state_scope"]["tract_count"], EXPECTED_TRACT_COUNT)
        self.assertEqual(specification["statewide_inventory"]["artifact_id"], INVENTORY_ID)
        self.assertEqual(specification["statewide_inventory"]["inventory_sha256"], EXPECTED_INVENTORY_SHA256)
        source = specification["data04_source_authority"]
        self.assertEqual(source["contract"]["content_sha256"], self.authority.data04.contract["content_sha256"])
        self.assertEqual(source["tiger_manifest"]["content_sha256"], self.authority.data04.tiger_manifest["manifest_content_sha256"])
        self.assertEqual(source["tiger_source"]["byte_sha256"], "220c0a351d94c9de456d87c5db78f3e3864b3287370350f1e503a84565224e82")
        self.assertEqual(source["source_geometry"]["shapefile_member_sha256"], "c1cc3adf41b9e9fa565a2bc5c58fd78dcd9a7488dddbf16e044ac036586af3c1")

    def test_specification_hash_and_schemas_are_deterministic(self) -> None:
        specification = copy.deepcopy(self.authority.specification)
        expected_hash = specification.pop("content_sha256")
        self.assertEqual(content_digest(specification), expected_hash)
        schema = self.authority.specification_schema
        self.assertTrue(set(schema["required"]) <= set(self.authority.specification))
        self.assertTrue(set(self.authority.specification) <= set(schema["properties"]))
        self.assertEqual(self.authority.anchor_schema["properties"]["schema_id"]["const"], ANCHOR_EVIDENCE_SCHEMA_ID)
        self.assertEqual(self.authority.report_schema["properties"]["tract_count"]["const"], EXPECTED_TRACT_COUNT)

    def test_geo03_operation_axis_distance_boundary_and_radii_are_exact(self) -> None:
        specification = self.authority.specification
        methodology = specification["geo03_methodology"]
        operation = self.authority.geo03["transformation"]["operation"]
        self.assertEqual(methodology["operation_id"], operation["operation_id"])
        self.assertEqual(methodology["operation_fingerprint_sha256"], "3c7421053e63df6e120d8aefd142399c9c53e6a1594ed23c37c644609a21bf14")
        self.assertEqual(methodology["logical_input_axis_order"], ["longitude", "latitude"])
        self.assertEqual(methodology["source_crs"], "EPSG:4269")
        self.assertEqual(methodology["target_crs"], "EPSG:5070")
        self.assertEqual(methodology["projection_method"], "EPSG:9822 Albers Equal Area / Conus Albers")
        self.assertFalse(methodology["alternate_datum_transformation_permitted"])
        self.assertEqual(methodology["grid_dependencies"], [])
        self.assertEqual(methodology["membership_comparison"], "distance_m <= radius_m")
        self.assertEqual(methodology["membership_rounding"], "none")
        self.assertTrue(methodology["forced_containing_tract"])
        self.assertTrue(ordinary_membership(200.0, 200.0))
        self.assertFalse(ordinary_membership(math.nextafter(200.0, math.inf), 200.0))
        self.assertEqual(tuple(specification["model_downstream_compatibility"]["radii_m"]), DEFAULT_RADII_M)
        self.assertEqual(validate_membership_specification(self.authority.geo03, self.authority.geo02), self.authority.geo03["content_sha256"])

    def test_transformer_uses_longitude_latitude_and_records_runtime(self) -> None:
        expected = self.transformer.transform(-84.5, 42.5)
        swapped = self.transformer.transform(42.5, -84.5)
        self.assertTrue(all(math.isfinite(value) for value in expected + swapped))
        self.assertGreater(math.hypot(expected[0] - swapped[0], expected[1] - swapped[1]), 1_000_000.0)
        self.assertEqual(self.transformer.operation_fingerprint, self.authority.specification["geo03_methodology"]["operation_fingerprint_sha256"])
        self.assertEqual(self.transformer.runtime_provenance["logical_input_axis_order"], ["longitude", "latitude"])
        self.assertEqual(self.transformer.runtime_provenance["grid_dependencies"], [])

    def test_valid_and_invalid_internal_points_and_anchors_are_explicit(self) -> None:
        valid = parse_internal_point("42.5", "-84.5")
        self.assertEqual(valid.coordinate_state, "valid")
        self.assertIsNotNone(project_internal_point(valid, self.transformer))
        for latitude, longitude, state in (
            (None, "-84.5", "missing"),
            ("not-a-number", "-84.5", "invalid_parse"),
            ("nan", "-84.5", "invalid_nonfinite"),
            ("91", "-84.5", "invalid_range"),
        ):
            point = parse_internal_point(latitude, longitude)
            self.assertEqual(point.coordinate_state, state)
            self.assertIsNone(project_internal_point(point, self.transformer))
        package, _, longitude_value = self._synthetic_package()
        with self.assertRaisesRegex(ConformanceError, "GEO05_ANCHOR_COORDINATE_INVALID"):
            evaluate_anchor_package(package, latitude=float("nan"), longitude=longitude_value, opaque_anchor_identity="synthetic", opaque_anchor_lineage="fixture")
        bad = replace(package.tracts[1], internal_x_m=float("nan"))
        invalid_package = replace(package, tracts=(package.tracts[0], bad, *package.tracts[2:]))
        with self.assertRaisesRegex(ConformanceError, "GEO05_MEMBERSHIP_DISTANCE_NONCOMPUTABLE"):
            evaluate_anchor_package(invalid_package, latitude=42.5, longitude=-84.5, opaque_anchor_identity="synthetic", opaque_anchor_lineage="fixture")

    def test_membership_is_nested_deduplicated_boundary_exact_and_forces_containing_tract(self) -> None:
        package, latitude, longitude = self._synthetic_package()
        evidence = evaluate_anchor_package(
            package,
            latitude=latitude,
            longitude=longitude,
            opaque_anchor_identity="synthetic-membership",
            opaque_anchor_lineage="fictional-test-fixture",
            radii_m=[100.0, 200.0, 300.0],
        )
        memberships = evidence["memberships"]
        self.assertEqual([item["radius_m"] for item in memberships], [100.0, 200.0, 300.0])
        self.assertEqual([item["ordinary_member_count"] for item in memberships], [1, 2, 3])
        self.assertEqual([item["member_count"] for item in memberships], [2, 3, 4])
        self.assertTrue(all(item["containing_tract_forced"] for item in memberships))
        self.assertIn("26001000300", memberships[1]["member_geoids"])
        for item in memberships:
            self.assertEqual(item["member_geoids"], sorted(set(item["member_geoids"])))
            self.assertIn(evidence["containing_tract_geoid"], item["member_geoids"])
        self.assertLessEqual(set(memberships[0]["member_geoids"]), set(memberships[1]["member_geoids"]))
        self.assertLessEqual(set(memberships[1]["member_geoids"]), set(memberships[2]["member_geoids"]))

    def test_anchor_containment_and_boundary_ambiguity_match_accepted_behavior(self) -> None:
        package, latitude, longitude = self._synthetic_package()
        evidence = evaluate_anchor_package(package, latitude=latitude, longitude=longitude, opaque_anchor_identity="synthetic", opaque_anchor_lineage="fixture")
        self.assertEqual(evidence["containing_tract_geoid"], "26001000100")

        left = replace(package.tracts[0], source_geometry=box(-85.0, 42.0, -84.5, 43.0))
        right = replace(package.tracts[1], source_geometry=box(-84.5, 42.0, -84.0, 43.0))
        specification = copy.deepcopy(package.authority.specification)
        specification["state_scope"]["tract_count"] = 2
        ambiguous = replace(package, authority=replace(package.authority, specification=specification), tracts=(left, right))
        with self.assertRaisesRegex(ConformanceError, "GEO05_ANCHOR_TRACT_MISSING_OR_AMBIGUOUS"):
            evaluate_anchor_package(ambiguous, latitude=42.5, longitude=-84.5, opaque_anchor_identity="synthetic", opaque_anchor_lineage="boundary-fixture")

    def test_support_completeness_reports_full_inside_and_truncated_footprints_without_threshold(self) -> None:
        package, latitude, longitude = self._synthetic_package()
        evidence = evaluate_anchor_package(
            package,
            latitude=latitude,
            longitude=longitude,
            opaque_anchor_identity="synthetic-completeness",
            opaque_anchor_lineage="fictional-test-fixture",
            radii_m=[100.0, 200.0],
        )
        inside, truncated = evidence["support_completeness"]
        self.assertAlmostEqual(inside["support_completeness_ratio"], 1.0, places=12)
        self.assertFalse(inside["extends_outside_michigan_support"])
        self.assertGreater(inside["footprint_edge_margin_m"], 0.0)
        self.assertLess(truncated["support_completeness_ratio"], 1.0)
        self.assertTrue(truncated["extends_outside_michigan_support"])
        self.assertGreater(truncated["outside_support_area_m2"], 0.0)
        self.assertLess(truncated["footprint_edge_margin_m"], 0.0)
        self.assertTrue(all(item["footprint_quad_segs"] == 64 for item in evidence["support_completeness"]))
        qa = self.authority.specification["support_completeness_qa"]
        self.assertIsNone(qa["threshold"])
        self.assertFalse(qa["automatic_rejection"])
        self.assertFalse(qa["other_state_or_canadian_demographics"])

    def test_anchor_evidence_interface_is_machine_consumable_and_target_blind(self) -> None:
        package, latitude, longitude = self._synthetic_package()
        evidence = evaluate_anchor_package(package, latitude=latitude, longitude=longitude, opaque_anchor_identity="opaque-anchor", opaque_anchor_lineage="opaque-lineage")
        self.assertEqual(set(evidence), set(self.authority.anchor_schema["required"]))
        self.assertEqual(evidence["schema_id"], ANCHOR_EVIDENCE_SCHEMA_ID)
        self.assertEqual(evidence["state"], "COMPUTABLE")
        self.assertEqual(evidence["anchor"]["opaque_anchor_identity"], "opaque-anchor")
        self.assertEqual(evidence["projected_anchor"]["crs"], "EPSG:5070")
        self.assertEqual([item["radius_m"] for item in evidence["memberships"]], list(DEFAULT_RADII_M))
        self.assertEqual(evidence["spatial_lineage"]["inventory_id"], INVENTORY_ID)
        self.assertEqual(evidence["spatial_lineage"]["operation_fingerprint_sha256"], self.transformer.operation_fingerprint)
        serialized = json.dumps(evidence, allow_nan=False, sort_keys=True)
        for forbidden in ("score", "prediction", "coefficient", "intercept", "target_value"):
            self.assertNotIn(f'"{forbidden}"', serialized.lower())

    def test_generic_radius_validation_fails_closed(self) -> None:
        package, latitude, longitude = self._synthetic_package()
        for radii, code in (([], "GEO05_RADIUS_INVALID"), ([0.0], "GEO05_RADIUS_INVALID"), ([100.0, 100.0], "GEO05_RADIUS_DUPLICATE"), ([float("nan")], "GEO05_RADIUS_INVALID")):
            with self.assertRaisesRegex(ConformanceError, code):
                evaluate_anchor_package(package, latitude=latitude, longitude=longitude, opaque_anchor_identity="synthetic", opaque_anchor_lineage="fixture", radii_m=radii)

    def test_output_overwrite_is_denied_before_source_access(self) -> None:
        with temporary_directory() as temporary:
            existing = Path(temporary) / "already-exists"
            existing.mkdir()
            with self.assertRaisesRegex(ConformanceError, "GEO05_OUTPUT_OVERWRITE_DENIED"):
                materialize_real(ROOT, Path(temporary) / "missing.zip", Path(temporary) / "missing-ready", existing)

    def test_materialization_comparison_includes_ready_and_detects_difference(self) -> None:
        with temporary_directory() as temporary:
            root = Path(temporary)
            first, second = root / "first", root / "second"
            for directory in (first, second):
                directory.mkdir()
                (directory / "example.csv").write_text("a\n1\n", encoding="utf-8")
                (directory / "READY.json").write_text('{"ready_marker_written_last":true,"state":"READY"}\n', encoding="utf-8")
            report = compare_materializations(first, second)
            self.assertEqual(report["state"], "DETERMINISTIC_BYTE_IDENTICAL")
            self.assertTrue(report["ready_markers_included"])
            (second / "example.csv").write_text("a\n2\n", encoding="utf-8")
            with self.assertRaisesRegex(ConformanceError, "GEO05_RERUN_NONDETERMINISTIC"):
                compare_materializations(first, second)

    def test_current_data04_ready_package_when_supplied(self) -> None:
        value = os.environ.get("GEO05_DATA04_READY_DIR")
        if not value:
            self.skipTest("GEO05_DATA04_READY_DIR not supplied; ignored public outputs are deliberately not tracked")
        rows, lineage = verify_data04_ready(self.authority, Path(value))
        self.assertEqual(len(rows), EXPECTED_TRACT_COUNT)
        self.assertEqual(lineage["inventory_sha256"], EXPECTED_INVENTORY_SHA256)
        self.assertEqual(lineage["data04_contract_content_sha256"], self.authority.data04.contract["content_sha256"])

    def test_real_ready_spatial_package_when_supplied(self) -> None:
        value = os.environ.get("GEO05_READY_PACKAGE_DIR")
        if not value:
            self.skipTest("GEO05_READY_PACKAGE_DIR not supplied; bulk public spatial outputs are deliberately not tracked")
        package = load_support_package(ROOT, Path(value))
        self.assertEqual(len(package.tracts), EXPECTED_TRACT_COUNT)
        self.assertTrue(package.projected_support.is_valid)
        self.assertGreater(package.projected_support.area, 0.0)
        report = package.verification_report
        self.assertEqual(report["spatial_evidence"]["projected_internal_point_count"], EXPECTED_TRACT_COUNT)
        self.assertTrue(report["public_anchor_qa"]["edge_internal_point"]["support_completeness"][0]["extends_outside_michigan_support"])
        self.assertFalse(report["protected_evidence_access"]["sprouts_or_protected_evidence_accessed"])

    def test_michigan_and_wisconsin_authority_remain_separate_and_unchanged(self) -> None:
        self.assertEqual(self.authority.specification["state_scope"]["state_fips"], "26")
        self.assertEqual(self.authority.geo03["data_authority"]["tiger_manifest_id"], "DATA02_TIGER2024_WI_TRACT_SOURCE_MANIFEST_V1")
        accepted_paths = [
            "config/geo/geo02_validation_context_spatial_spec.json",
            "config/geo/geo03_internal_point_membership_spatial_spec.json",
            "config/geo/canonical_tract_inventory_derivation.json",
            "config/geo/canonical_tract_inventory_milwaukee.json",
            "config/geo/canonical_tract_inventory_madison.json",
            "src/sprouts_customer_geography/pipe01/production.py",
            "src/sprouts_customer_geography/model09/features.py",
            "src/sprouts_customer_geography/model11/features.py",
        ]
        changed = subprocess.run(["git", "diff", "--name-only", AUTHORIZATION_BASE, "--", *accepted_paths], cwd=ROOT, check=True, capture_output=True, text=True).stdout.splitlines()
        self.assertEqual(changed, [])

    def test_no_michigan_market_inventory_or_protected_dependency_is_created(self) -> None:
        market_paths = [path.name.lower() for path in (ROOT / "config" / "markets").glob("*") if path.is_file()]
        geo_paths = [path.name.lower() for path in (ROOT / "config" / "geo").glob("*") if path.is_file()]
        self.assertFalse(any("michigan" in path for path in market_paths))
        self.assertFalse(any("canonical_tract_inventory_michigan" in path for path in geo_paths))
        specification = self.authority.specification
        self.assertFalse(specification["statewide_inventory"]["market_inventory"])
        self.assertEqual(specification["protected_evidence_boundary"]["protected_dependencies"], [])
        self.assertEqual(specification["protected_evidence_boundary"]["protected_filesystem_discovery"], "prohibited and unnecessary")
        self.assertFalse(specification["protected_evidence_boundary"]["anchor_instances_created_by_geo05"])
        self.assertFalse(specification["model_downstream_compatibility"]["model_execution_performed"])
        self.assertFalse(specification["model_downstream_compatibility"]["scoring_authority_created"])

    def test_raw_and_generated_spatial_outputs_are_ignored_and_untracked(self) -> None:
        ignored = subprocess.run(
            ["git", "check-ignore", "--no-index", "data/raw/data04/tl_2024_26_tract.zip", "outputs/geo05/example.wkb"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        self.assertIn("data/raw/data04/tl_2024_26_tract.zip", ignored)
        self.assertIn("outputs/geo05/example.wkb", ignored)
        stageable = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=ROOT, check=True, capture_output=True, text=True).stdout.splitlines()
        self.assertFalse(any(path.replace("\\", "/").startswith(("data/raw/", "outputs/")) for path in stageable))
        self.assertFalse(any(path.lower().endswith((".zip", ".shp", ".dbf", ".wkb")) for path in stageable))

    def test_single_manifest_work_order_and_lane_b_destination(self) -> None:
        manifests = list((ROOT / "governance" / "tasks").glob("GEO-05*.task.json"))
        work_orders = list((ROOT / "docs" / "work_orders").glob("GEO_05*.md"))
        self.assertEqual(len(manifests), 1)
        self.assertEqual(len(work_orders), 1)
        task = json.loads(manifests[0].read_text(encoding="utf-8"))
        self.assertEqual(task["implementation_branch"], "task/geo-05-michigan-statewide-geography-enablement")
        self.assertEqual(task["capability_owner"], "GEO Decisions Acceptance")
        self.assertEqual(task["acceptance_destination"], "GEO Decisions Acceptance")
        self.assertIn(
            (task["state"], task["completion_state"]["execution"], task["completion_state"]["capability_acceptance"]),
            {
                ("IN_PROGRESS", "IN_PROGRESS", "NOT_REVIEWED"),
                ("COMPLETED_AWAITING_ACCEPTANCE", "COMPLETED", "NOT_REVIEWED"),
                ("ACCEPTED_CLOSED", "COMPLETED", "ACCEPTED"),
            },
        )


if __name__ == "__main__":
    unittest.main()
