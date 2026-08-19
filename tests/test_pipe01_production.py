from __future__ import annotations

import copy
import inspect
import json
import math
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from shapely.geometry import box

from sprouts_customer_geography.constants import RADII_M, RADIUS_5_M
from sprouts_customer_geography.model06 import build_commitment_evidence
from sprouts_customer_geography.pipe01.canonical import content_digest, write_json_exclusive
from sprouts_customer_geography.pipe01.errors import ConformanceError
from sprouts_customer_geography.pipe01.orchestration import (
    Geo02ProductionSpatialAdapter,
    Model04Binding,
    PreparedContext,
    bind_authoritative_dependencies,
    build_protected_contexts,
    execute_protected_freeze,
    load_repository_authorities,
)
from sprouts_customer_geography.pipe01.production import (
    ACCEPTED_GEO03_OPERATION_FINGERPRINT,
    Geo03ProductionTransformer,
    TigerMarketData,
    TigerProductionBundle,
    load_acs_b11001_production_bundle,
    load_tiger_production_bundle,
    parse_acs_b11001_values,
)
from sprouts_customer_geography.pipe01.run import MANDATORY_DEPENDENCIES, ProtectedRun
from sprouts_customer_geography.pipe01.spatial import ordinary_membership, parse_internal_point


ROOT = Path(__file__).resolve().parents[1]


def _public_paths() -> tuple[Path, Path] | None:
    tiger = Path(os.environ.get("PIPE01B_PINNED_TIGER_ZIP", ROOT / "data/local/tl_2024_55_tract.zip"))
    acs = Path(os.environ.get("PIPE01B_PINNED_ACS_B11001", ROOT / "data/local/acsdt5y2024-b11001.dat"))
    return (tiger, acs) if tiger.is_file() and acs.is_file() else None


def _temporary_directory():
    configured_root = os.environ.get("PIPE01_TEST_TEMP_ROOT")
    return tempfile.TemporaryDirectory(dir=configured_root or None)


def _fictional_model04_package(latitude: float, longitude: float) -> dict:
    record = {
        "package_id": "MODEL04_VALIDATION_IDENTITY_ROLE_ANCHOR_PACKAGE_V1",
        "package_version": "1.0.0",
        "identity_version": "MODEL04_TARGET_BLIND_PHYSICAL_LOCATION_IDENTITY_V1",
        "physical_location_id": "fictional-location-pipe01b-conformance",
        "source_workbook_identity": "FICTIONAL_PIPE01B_CONFORMANCE_WORKBOOK",
        "source_sheet": "Fictional",
        "source_row": 2,
        "source_seed_point_id": "FICTIONAL-NOT-A-SPROUTS-SEED",
        "vintage": "fictional-2099",
        "vintage_year": 2099,
        "market": "milwaukee",
        "identity_state": "GENUINELY_NEW_LOCATION",
        "identity_rule_reason_code": "MORE_THAN_500M_WITHOUT_STABLE_LINEAGE_OR_CONFLICT",
        "linked_prior_physical_location_id": None,
        "quarantined": False,
        "evidence_role": "PROSPECTIVE_MILWAUKEE_HOLDOUT",
        "evidence_subrole": "FICTIONAL_PIPE01B_CONFORMANCE_ONLY",
        "observed_coordinate": {"latitude": latitude, "longitude": longitude, "provenance": "FICTIONAL_PUBLIC_TRACT_INTERNAL_POINT_FIXTURE"},
        "canonical_anchor": {
            "latitude": latitude,
            "longitude": longitude,
            "source_workbook_identity": "FICTIONAL_PIPE01B_CONFORMANCE_WORKBOOK",
            "source_sheet": "Fictional",
            "source_row": 2,
            "source_seed_point_id": "FICTIONAL-NOT-A-SPROUTS-SEED",
            "anchor_version": "MODEL04_EARLIEST_OBSERVED_MEMBER_ANCHOR_V1",
            "selection_semantics": "EARLIEST_VINTAGE_THEN_ACCEPTED_PROVENANCE_TIER_THEN_SOURCE_LINEAGE",
        },
        "canonical_anchor_state": "SELECTED_ACTUAL_OBSERVED_MEMBER",
        "target_view_state": "SEALED",
    }
    package = {
        "$schema": "model04-validation-identity-role-anchor-package-v1",
        "package_id": "MODEL04_VALIDATION_IDENTITY_ROLE_ANCHOR_PACKAGE_V1",
        "package_version": "1.0.0",
        "identity_version": "MODEL04_TARGET_BLIND_PHYSICAL_LOCATION_IDENTITY_V1",
        "canonical_anchor_version": "MODEL04_EARLIEST_OBSERVED_MEMBER_ANCHOR_V1",
        "status": "fictional_conformance_only",
        "target_blind_projection": {"sealed_targets_supplied_or_used": False, "fixture_classification": "genuinely_fictional_not_derived_from_sprouts_seeds"},
        "source_projection_identities": [],
        "identity_rules": {},
        "evidence_role_semantics": ["PROSPECTIVE_MILWAUKEE_HOLDOUT"],
        "records": [record],
        "supersedes": None,
        "supersession_policy": "fictional conformance fixtures are immutable per test run",
        "materialization_provenance": {"mode": "fictional_pipe01b_conformance"},
    }
    package["protected_content_sha256"] = content_digest(package)
    package["protected_content_hash_semantics"] = "SHA-256 after removing protected_content_sha256 and protected_content_hash_semantics"
    semantic = copy.deepcopy(package)
    semantic.pop("protected_content_sha256")
    semantic.pop("protected_content_hash_semantics")
    package["protected_content_sha256"] = content_digest(semantic)
    return package


class IdentityTransformer:
    source_crs = "EPSG:4269"
    target_crs = "EPSG:5070"
    operation_fingerprint = ACCEPTED_GEO03_OPERATION_FINGERPRINT
    runtime_provenance = {"implementation": "fictional_identity_transformer"}

    def transform(self, longitude: float, latitude: float):
        return longitude, latitude


class ProductionAdapterUnitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.authorities = load_repository_authorities(ROOT)

    def test_geo03_runtime_reproduces_exact_accepted_operation(self):
        transformer = Geo03ProductionTransformer(self.authorities.membership_specification)
        self.assertEqual(transformer.operation_fingerprint, ACCEPTED_GEO03_OPERATION_FINGERPRINT)
        self.assertEqual(transformer.source_crs, "EPSG:4269")
        self.assertEqual(transformer.target_crs, "EPSG:5070")
        self.assertIn("proj=aea", transformer.runtime_provenance["runtime_definition"])
        self.assertEqual(transformer.runtime_provenance["grid_dependencies"], [])
        x_value, y_value = transformer.transform(-87.9, 43.0)
        self.assertTrue(math.isfinite(x_value) and math.isfinite(y_value))

    def test_geo03_mismatch_fails_closed(self):
        wrong = copy.deepcopy(self.authorities.membership_specification)
        wrong["transformation"]["operation_fingerprint_sha256"] = "0" * 64
        with self.assertRaisesRegex(ConformanceError, "GEO03_OPERATION_FINGERPRINT_MISMATCH"):
            Geo03ProductionTransformer(wrong)

    def test_all_exact_radius_equalities_are_members(self):
        for radius in RADII_M:
            self.assertTrue(ordinary_membership(radius, radius))
            self.assertFalse(ordinary_membership(math.nextafter(radius, math.inf), radius))

    def test_internal_point_states_are_explicit_and_never_repaired(self):
        self.assertEqual(parse_internal_point(None, "-88").coordinate_state, "missing")
        self.assertEqual(parse_internal_point("bad", "-88").coordinate_state, "invalid_parse")
        self.assertEqual(parse_internal_point("91", "-88").coordinate_state, "invalid_range")
        self.assertEqual(parse_internal_point("nan", "-88").coordinate_state, "invalid_nonfinite")

    def test_acs_estimate_moe_and_special_states_are_lossless(self):
        valid = parse_acs_b11001_values("123", "9")
        self.assertEqual((valid["estimate"], valid["moe"], valid["status"]), (123, 9, "valid"))
        for estimate, status in (("", "missing"), ("-999999999", "suppressed"), ("-888888888", "inapplicable"), ("not-a-number", "invalid")):
            parsed = parse_acs_b11001_values(estimate, "10")
            self.assertEqual(parsed["status"], status)
            self.assertIsNone(parsed["estimate"])
            self.assertNotEqual(parsed["estimate"], 0)
            self.assertEqual(parsed["raw_estimate"], estimate)
            self.assertIsNone(parsed["annotation"])

    def _spatial_adapter(self, support):
        market = TigerMarketData(
            "milwaukee",
            tuple(),
            {"00000000001": support},
            {"00000000001": support},
        )
        bundle = TigerProductionBundle({"milwaukee": market}, "fictional-public-source", {"synthetic": True})
        return Geo02ProductionSpatialAdapter(self.authorities, bundle, IdentityTransformer())

    def _prepared(self, ordinal: int, context_id: str, x_value: float, y_value: float):
        return PreparedContext(
            ordinal,
            context_id,
            {
                "market_id": "milwaukee",
                "context_spec_id": self.authorities.context_specification["artifact_id"],
                "context_instance_id": context_id,
                "anchor_tract_geoid": "00000000001",
                "anchor_longitude": x_value,
                "anchor_latitude": y_value,
            },
            {"fictional": True},
            False,
        )

    def test_geo02_context_lineage_edge_and_completeness(self):
        radius = RADIUS_5_M
        complete = self._spatial_adapter(box(-radius, -radius, radius, radius)).execute((self._prepared(1, "fictional-complete", 0, 0),))["fictional-complete"]
        self.assertEqual(complete["context_spec_id"], self.authorities.context_specification["artifact_id"])
        self.assertEqual(complete["context_instance_id"], "fictional-complete")
        self.assertEqual(complete["market_edge_state"], "not_truncated")
        self.assertEqual(complete["geometric_completeness"], 1.0)
        self.assertEqual(complete["geo02_lineage"]["projected_context_space"], "EPSG:5070")

        truncated = self._spatial_adapter(box(-radius, -radius, 0, radius)).execute((self._prepared(1, "fictional-truncated", 0, 0),))["fictional-truncated"]
        self.assertEqual(truncated["market_edge_state"], "truncated")
        self.assertGreater(truncated["geometric_completeness"], 0.49)
        self.assertLess(truncated["geometric_completeness"], 0.51)

    def test_geo02_geometric_jaccard_and_components(self):
        radius = RADIUS_5_M
        adapter = self._spatial_adapter(box(-3 * radius, -3 * radius, 3 * radius, 3 * radius))
        contexts = (self._prepared(1, "fictional-a", 0, 0), self._prepared(2, "fictional-b", 1000, 0))
        result = adapter.execute(contexts)
        self.assertGreater(result["fictional-a"]["geometric_jaccard"], 0.25)
        self.assertEqual(result["fictional-a"]["spatial_components"]["component_size"], 2)
        self.assertEqual(result["fictional-b"]["spatial_components"]["component_size"], 2)
        serialized = json.dumps(result).lower()
        self.assertNotIn("membership_jaccard", serialized)

    def test_production_orchestration_interface_has_no_target_parameter(self):
        parameters = set(inspect.signature(execute_protected_freeze).parameters)
        self.assertFalse(parameters & {"target", "target_values", "forecast", "sealed_targets"})


class ExactPinnedSourceProductionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        paths = _public_paths()
        if paths is None:
            raise unittest.SkipTest("exact pinned public artifacts are not supplied")
        cls.tiger_path, cls.acs_path = paths
        cls.authorities = load_repository_authorities(ROOT)
        cls.transformer = Geo03ProductionTransformer(cls.authorities.membership_specification)
        cls.tiger = load_tiger_production_bundle(
            cls.tiger_path,
            cls.authorities.tiger_manifest,
            cls.authorities.inventories,
            cls.authorities.derivation,
            cls.transformer,
        )
        cls.acs = load_acs_b11001_production_bundle(cls.acs_path, cls.authorities.acs_manifest, cls.authorities.inventories)
        first = cls.tiger.markets["milwaukee"].rows[0]
        cls.package = _fictional_model04_package(float(first["INTPTLAT"]), float(first["INTPTLON"]))
        cls.binding = Model04Binding(cls.package, cls.package["protected_content_sha256"], {"state": "passed"})

    def test_exact_tiger_raw_parsing_and_canonical_inventory_binding(self):
        self.assertEqual(len(self.tiger.markets["milwaukee"].rows), 452)
        self.assertEqual(len(self.tiger.markets["madison"].rows), 152)
        for market_id, market in self.tiger.markets.items():
            self.assertEqual(
                [row["tract_geoid"] for row in market.rows],
                self.authorities.inventories[market_id]["ordered_geoids"],
            )
            self.assertTrue(all(isinstance(row["INTPTLAT"], str) and isinstance(row["INTPTLON"], str) for row in market.rows))
            self.assertTrue(all(row["coordinate_state"] == "valid" for row in market.rows))

    def test_exact_acs_binding_and_status_provenance(self):
        self.assertEqual(self.acs.wisconsin_tract_count, 1542)
        self.assertEqual(len(self.acs.markets["milwaukee"]), 452)
        self.assertEqual(len(self.acs.markets["madison"]), 152)
        self.assertTrue(all(row["status"] == "valid" for rows in self.acs.markets.values() for row in rows))
        self.assertEqual(self.acs.source_lineage["estimate_contract_field"], "B11001_001E")
        self.assertEqual(self.acs.source_lineage["moe_contract_field"], "B11001_001M")

    def test_model04_anchor_is_strictly_spatially_bound_and_not_resolved_again(self):
        contexts = build_protected_contexts(self.binding, self.authorities, self.tiger)
        self.assertEqual(len(contexts), 1)
        context = contexts[0].context
        self.assertIsNotNone(context)
        assert context is not None
        self.assertEqual(context["anchor_tract_geoid"], self.authorities.inventories["milwaukee"]["ordered_geoids"][0])
        serialized = json.dumps(context).lower()
        for forbidden in ("target_value", "forecast", "isolated_sales", "impacted_sales", "residual"):
            self.assertNotIn(forbidden, serialized)

    def test_authoritative_dependency_difference_fails_closed(self):
        accepted = {
            **self.authorities.public_dependency_values,
            "model04_package_id": self.package["package_id"],
            "model04_package_version": self.package["package_version"],
            "model04_package_sha256": self.package["protected_content_sha256"],
        }
        self.assertEqual(set(accepted), MANDATORY_DEPENDENCIES)
        self.assertEqual(bind_authoritative_dependencies(self.authorities, self.binding, accepted), accepted)
        wrong = {**accepted, "tiger_source_sha256": "0" * 64}
        with self.assertRaisesRegex(ConformanceError, "AUTHORITATIVE_DEPENDENCY_MISMATCH"):
            bind_authoritative_dependencies(self.authorities, self.binding, wrong)

    def test_complete_fictional_freeze_finalizes_through_production_path(self):
        with _temporary_directory() as temporary:
            root = Path(temporary)
            package_path = root / "model04_identity_role_anchor_package.json"
            nonce_path = root / "commitment_nonce.bin"
            evidence_path = root / "model04_commitment.json"
            preflight_path = root / "accepted_dependencies.json"
            write_json_exclusive(package_path, self.package)
            nonce_path.write_bytes(b"F" * 32)
            write_json_exclusive(evidence_path, build_commitment_evidence(package_path, nonce_path.read_bytes()))
            preflight = {
                **self.authorities.public_dependency_values,
                "model04_package_id": self.package["package_id"],
                "model04_package_version": self.package["package_version"],
                "model04_package_sha256": self.package["protected_content_sha256"],
            }
            write_json_exclusive(preflight_path, preflight)
            result = execute_protected_freeze(
                repository_root=ROOT,
                protected_root=root / "protected",
                tiger_source_zip=self.tiger_path,
                acs_source_file=self.acs_path,
                model04_package_path=package_path,
                model04_nonce_path=nonce_path,
                model04_commitment_evidence_path=evidence_path,
                accepted_dependency_preflight_path=preflight_path,
                code_identity="fictional-pipe01b-conformance-code",
                run_id="prun-fictional-pipe01b-e2e",
            )
            self.assertEqual(result.context_count, 1)
            self.assertEqual(result.prediction_count, 1)
            self.assertTrue((result.run_dir / "FROZEN.json").is_file())
            self.assertTrue((result.run_dir / "freeze_manifest.json").is_file())
            self.assertRegex(result.commitment_sha256, r"^[0-9a-f]{64}$")
            report_text = json.dumps(result.disclosure_safe_report)
            self.assertNotIn("household_opportunity", report_text)
            self.assertNotIn("prediction_candidate", report_text)
            lineage_files = list((result.run_dir / "artifacts").glob("*-model04-lineage.json"))
            self.assertEqual(len(lineage_files), 1)
            self.assertIn("FICTIONAL-NOT-A-SPROUTS-SEED", lineage_files[0].read_text(encoding="utf-8"))


class FinalizationOrderingTests(unittest.TestCase):
    def test_final_marker_is_the_last_exclusive_json_write(self):
        dependencies = {key: f"fictional-{key}" for key in MANDATORY_DEPENDENCIES}
        with _temporary_directory() as temporary:
            run = ProtectedRun(Path(temporary), ROOT, run_id="prun-fictional-ordering")
            run.write_artifact("fictional.json", {"fictional": True})
            import sprouts_customer_geography.pipe01.run as run_module

            original = run_module.write_json_exclusive
            order: list[str] = []

            def recording_write(path, value):
                order.append(path.name)
                return original(path, value)

            with patch.object(run_module, "write_json_exclusive", side_effect=recording_write):
                run.finalize(dependencies, "fictional-code", {"spec": "fictional"}, {"mandatory_passed": True}, False)
            self.assertEqual(order[-1], "FROZEN.json")


if __name__ == "__main__":
    unittest.main()
