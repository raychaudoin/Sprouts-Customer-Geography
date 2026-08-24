from __future__ import annotations

import copy
import io
import json
import math
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from sprouts_customer_geography.model06 import ProjectedWorkbook, TARGET_HEADER_TOKENS, read_target_blind_projection
from sprouts_customer_geography.model11.modeling import BASE_TERMS
from sprouts_customer_geography.model12.contract import CONTRACT_ID, verify_repository_authority
from sprouts_customer_geography.model12.frozen import FrozenScoringState, load_frozen_scoring_state
from sprouts_customer_geography.model12.materialization import (
    FEATURE_PACKAGE_ID,
    FIELD_PACKAGE_ID,
    SCORING_PACKAGE_ID,
    STAGE_FILENAMES,
    ProtectedRun,
    _scoring_package,
    build_disclosure_safe_result,
    compare_materializations,
    execute_field_scoring,
    MaterializationResult,
)
from sprouts_customer_geography.model12.public import (
    MichiganPublicSources,
    RADII_M,
    _validate_anchor_inputs,
    build_anchor_public_features,
)
from sprouts_customer_geography.model12.resolver import ProtectedHandleResolver, resolve_exact_basename
from sprouts_customer_geography.model12.source import build_michigan_identity_package
from sprouts_customer_geography.pipe01.canonical import content_digest, file_sha256, write_json_exclusive
from sprouts_customer_geography.pipe01.errors import ConformanceError
from sprouts_customer_geography.pipe02.resolver import ResolvedHandle


ROOT = Path(__file__).resolve().parents[1]


def _temporary_directory() -> tempfile.TemporaryDirectory:
    return tempfile.TemporaryDirectory(dir=os.environ.get("MODEL12_TEST_TEMP_ROOT") or None)


def _contract() -> dict:
    return json.loads((ROOT / "config/model/model12_michigan_target_blind_frozen_scoring_contract.json").read_text(encoding="utf-8"))


def _model11_contract() -> dict:
    return json.loads((ROOT / "config/model/model11_wisconsin_multivariate_model_contract.json").read_text(encoding="utf-8"))


def _identity_rows() -> list[dict]:
    return [
        {"vintage": 2024, "seed_point_id": "FICTIONAL-A", "address": "1 Fictional Ave", "city": "Example", "state": "MI", "zip": "00001", "latitude": 42.0, "longitude": -83.0, "market": "FICTIONAL-A", "source_row": 2},
        {"vintage": 2025, "seed_point_id": "FICTIONAL-A-NEW", "address": "1 Fictional Ave", "city": "Example", "state": "MI", "zip": "00001", "latitude": 42.0, "longitude": -83.0, "market": "FICTIONAL-B", "source_row": 3},
        {"vintage": 2026, "seed_point_id": "FICTIONAL-A-LATEST", "address": "1 Fictional Ave", "city": "Example", "state": "MI", "zip": "00001", "latitude": 42.0, "longitude": -83.0, "market": "FICTIONAL-C", "source_row": 4},
        {"vintage": 2024, "seed_point_id": "FICTIONAL-B", "address": "9 Imaginary Rd", "city": "Example", "state": "MI", "zip": "00002", "latitude": 43.0, "longitude": -84.0, "market": "FICTIONAL-A", "source_row": 5},
        {"vintage": 2025, "seed_point_id": "FICTIONAL-AMBIGUOUS", "address": "77 Different St", "city": "Elsewhere", "state": "MI", "zip": "00003", "latitude": 43.001, "longitude": -84.0, "market": "FICTIONAL-Z", "source_row": 6},
    ]


def _xlsx_payload(rows: list[dict], target_values: tuple[str, str]) -> bytes:
    headers = ["Year", "Seedpoint_ID", "Address", "MunicipalityAlt", "State", "Zip", "Lat", "Long", "MSA", *sorted(TARGET_HEADER_TOKENS)]
    letters = "ABCDEFGHIJK"
    header_cells = "".join(f"<c r='{letter}1' t='inlineStr'><is><t>{header}</t></is></c>" for letter, header in zip(letters, headers))
    body: list[str] = []
    for index, row in enumerate(rows, start=2):
        values = [row["vintage"], row["seed_point_id"], row["address"], row["city"], row["state"], row["zip"], row["latitude"], row["longitude"], row["market"]]
        cells: list[str] = []
        for letter, value in zip(letters[:9], values):
            if isinstance(value, (int, float)) and letter != "F":
                cells.append(f"<c r='{letter}{index}'><v>{value}</v></c>")
            else:
                cells.append(f"<c r='{letter}{index}' t='inlineStr'><is><t>{value}</t></is></c>")
        cells.append(f"<c r='J{index}'><v>{target_values[0]}</v></c>")
        cells.append(f"<c r='K{index}'><v>{target_values[1]}</v></c>")
        body.append(f"<row r='{index}'>" + "".join(cells) + "</row>")
    sheet = "<?xml version='1.0' encoding='UTF-8'?><worksheet xmlns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'><sheetData><row r='1'>" + header_cells + "</row>" + "".join(body) + "</sheetData></worksheet>"
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr("xl/worksheets/sheet1.xml", sheet)
    return payload.getvalue()


def _projected(targets: tuple[str, str] = ("100", "200")) -> ProjectedWorkbook:
    return read_target_blind_projection(
        _xlsx_payload(_identity_rows(), targets),
        "FICTIONAL_MI_AGGREGATED_SOURCE_V1",
        header_alias_overrides={"city": ["MunicipalityAlt"]},
    )


def _identity(targets: tuple[str, str] = ("100", "200")) -> dict:
    return build_michigan_identity_package(
        _projected(targets),
        registry_identity="protected-handle-registry:sha256:" + "1" * 64,
        contract_authority={"artifact_id": CONTRACT_ID, "version": "1.0.0", "content_sha256": _contract()["content_sha256"]},
    )


def _components(geoids: list[str], *, missing: str | None = None) -> dict:
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
    for index, geoid in enumerate(geoids):
        output[geoid] = {
            name: {"estimate": estimate + index, "moe": moe, "status": "missing" if name == missing else "valid", "status_detail": "fictional"}
            for name, (estimate, moe) in values.items()
        }
    return output


def _frozen(terms: tuple[str, ...] | None = None) -> FrozenScoringState:
    selected = terms or ("log_households_5mi", "inner_household_share_3mi_of_7mi", "log_inner_outer_household_density_gradient", "median_household_income")
    return FrozenScoringState(
        model_contract_id="MODEL11_WISCONSIN_MULTIVARIATE_MODEL_CONTRACT_V1",
        preferred_candidate_id="challenger_multivariate_elastic_net",
        architecture="elastic_net",
        terms=selected,
        means={term: 0.0 for term in selected},
        scales={term: 1.0 for term in selected},
        intercept=1.0,
        coefficients=tuple(0.1 * (index + 1) for index in range(len(selected))),
        alpha=0.1,
        l1_ratio=0.5,
        target_transformation="log1p",
        inverse_target_transformation="max zero expm1",
        stable_development_identity="model11-development:sha256:" + "2" * 64,
        stable_feature_freeze_identity="model11-feature-freeze:sha256:" + "3" * 64,
        protected_registry_identity="protected-handle-registry:sha256:" + "4" * 64,
    )


class _FakeResolver:
    def __init__(self, output: Path):
        self.output = output
        self.materialization_request = {"model12_output_root_handle": "phandle-output"}
        self.public_dependencies = {"data04_ready_dir": output, "geo05_support_dir": output}
        self.registry_identity = "protected-handle-registry:sha256:" + "5" * 64

    def resolve(self, handle: str, expected_kind: str) -> ResolvedHandle:
        if handle != "phandle-output" or expected_kind != "model12_output_root":
            raise AssertionError("unexpected handle resolution")
        return ResolvedHandle(handle, expected_kind, self.output)


class Model12ScoringTests(unittest.TestCase):
    def test_exact_accepted_authority_identities_hashes_and_future_freeze(self) -> None:
        contract = verify_repository_authority(ROOT)
        self.assertEqual(contract["artifact_id"], CONTRACT_ID)
        self.assertEqual(contract["accepted_authority"]["data04"]["artifact_id"], "DATA04_MICHIGAN_PUBLIC_DATA_PARITY_SOURCE_CONTRACT_V1")
        self.assertEqual(contract["accepted_authority"]["geo05"]["artifact_id"], "GEO05_MICHIGAN_STATEWIDE_SPATIAL_SUPPORT_SPEC_V1")
        self.assertEqual(contract["accepted_authority"]["model10"]["artifact_id"], "MODEL10_WISCONSIN_COHORT_IDENTITY_LINEAGE_CONTRACT_V1")
        self.assertEqual(contract["accepted_authority"]["model11"]["preferred_candidate_id"], "challenger_multivariate_elastic_net")
        self.assertEqual(contract["public_feature_application"]["radii_m"], list(RADII_M))
        self.assertEqual(contract["future_transport_evaluation_freeze"]["metrics"], ["spearman", "kendall_tau_b", "log_rmse", "level_mae"])
        self.assertFalse(contract["future_transport_evaluation_freeze"]["target_access_authorized"])

    def test_exact_source_basename_resolution_rejects_similar_and_nonrecursive_files(self) -> None:
        with _temporary_directory() as temporary:
            root = Path(temporary)
            (root / "fictional-source-copy.xlsx").write_bytes(b"similar")
            exact = root / "fictional-source.xlsx"
            exact.write_bytes(b"exact")
            self.assertEqual(resolve_exact_basename(root, "fictional-source"), exact.resolve())
            exact.unlink()
            with self.assertRaisesRegex(ConformanceError, "MODEL12_EXACT_SOURCE_BASENAME_UNRESOLVED"):
                resolve_exact_basename(root, "fictional-source")
            nested = root / "nested"
            nested.mkdir()
            (nested / "fictional-source.xlsx").write_bytes(b"outside-immediate-root")
            with self.assertRaisesRegex(ConformanceError, "MODEL12_EXACT_SOURCE_BASENAME_UNRESOLVED"):
                resolve_exact_basename(root, "fictional-source")

    def test_target_blind_projection_target_content_invariance_and_zero_access(self) -> None:
        first = _identity(("100", "200"))
        second = _identity(("999999", "1"))
        self.assertEqual(first, second)
        self.assertEqual(first["target_access"]["target_body_values_accessed"], 0)
        self.assertEqual(first["target_blind_projection"]["body_values_outside_projection_materialized"], 0)
        self.assertFalse(first["source_authority"]["whole_source_file_hash_computed"])

    def test_cross_vintage_identity_seed_novelty_market_nonpartition_and_quarantine(self) -> None:
        package = _identity()
        observations = package["source_observations"]
        repeated = [row for row in observations if row["source_observation_lineage"]["source_projection_row"] in {2, 3, 4}]
        self.assertEqual(len({row["physical_location_id"] for row in repeated}), 1)
        self.assertEqual(len({row["source_market_lineage"] for row in repeated}), 3)
        self.assertEqual(len({row["source_observation_lineage"]["source_seed_point_id"] for row in repeated}), 3)
        ambiguous = next(row for row in observations if row["source_observation_lineage"]["source_projection_row"] == 6)
        self.assertTrue(ambiguous["quarantined"])
        self.assertEqual(ambiguous["identity_state"], "AMBIGUOUS_IDENTITY")
        rules = package["identity_rules"]
        self.assertEqual(rules["probable_same_max_m"], 10.0)
        self.assertEqual(rules["coherent_stable_non_target_lineage_max_m"], 500.0)
        self.assertFalse(rules["new_threshold_or_tolerance_introduced"])

    def test_complete_observation_accounting_and_duplicate_source_rejection(self) -> None:
        package = _identity()
        self.assertEqual(package["aggregate_conformance"]["source_observation_count"], len(_identity_rows()))
        self.assertTrue(package["aggregate_conformance"]["complete_source_observation_accounting"])
        projection = _projected()
        duplicate = ProjectedWorkbook(projection.source_identity, tuple([*projection.rows, dict(projection.rows[0])]), projection.projection_sha256, projection.access_report)
        with self.assertRaisesRegex(ConformanceError, "MODEL12_SOURCE_OBSERVATION_DUPLICATE"):
            build_michigan_identity_package(duplicate, registry_identity="protected-handle-registry:sha256:" + "1" * 64, contract_authority={"artifact_id": CONTRACT_ID})

    def test_geo05_membership_public_feature_parity_weights_missingness_and_support(self) -> None:
        geoids = ["26000000001", "26000000002", "26000000003"]
        households = {geoid: {"estimate": 100 + index * 50, "moe": 10 + index, "status": "valid", "status_detail": "fictional"} for index, geoid in enumerate(geoids)}
        sources = MichiganPublicSources(tuple(geoids), households, _components(geoids), _model11_contract(), {"data04_contract_id": "DATA04_MICHIGAN_PUBLIC_DATA_PARITY_SOURCE_CONTRACT_V1"})
        spatial = {
            "state": "COMPUTABLE",
            "containing_tract_geoid": geoids[0],
            "memberships": [
                {"radius_m": RADII_M[0], "member_geoids": geoids[:1], "member_count": 1},
                {"radius_m": RADII_M[1], "member_geoids": geoids[:2], "member_count": 2},
                {"radius_m": RADII_M[2], "member_geoids": geoids, "member_count": 3},
            ],
            "support_completeness": [
                {"radius_m": radius, "support_completeness_ratio": 0.8 if index == 2 else 1.0, "extends_outside_michigan_support": index == 2, "outside_support_area_m2": index, "anchor_to_support_boundary_m": 1.0, "footprint_edge_margin_m": -1.0}
                for index, radius in enumerate(RADII_M)
            ],
            "spatial_lineage": {"spatial_spec_id": "GEO05_MICHIGAN_STATEWIDE_SPATIAL_SUPPORT_SPEC_V1"},
        }
        with patch("sprouts_customer_geography.model12.public.evaluate_anchor_package", return_value=spatial) as evaluate:
            result = build_anchor_public_features(support=object(), sources=sources, opaque_anchor_id="fictional-anchor", latitude=44.0, longitude=-84.0, required_frozen_terms=("log_households_5mi", "median_household_income"))
        self.assertEqual(tuple(evaluate.call_args.kwargs["radii_m"]), RADII_M)
        self.assertEqual(result["public_features"]["households_3mi"], 100)
        self.assertEqual(result["public_features"]["households_5mi"], 250)
        self.assertEqual(result["public_features"]["households_7mi"], 450)
        self.assertEqual(result["member_counts"], {"3mi": 1, "5mi": 2, "7mi": 3})
        expected_income = (70000 * 100 + 70001 * 150) / 250
        self.assertAlmostEqual(result["public_features"]["median_household_income"], math.log1p(expected_income))
        self.assertTrue(result["any_support_truncation"])
        self.assertFalse(result["imputation_performed"])
        self.assertFalse(result["michigan_feature_selection_performed"])

        missing_sources = MichiganPublicSources(tuple(geoids), households, _components(geoids, missing="per_capita_income"), _model11_contract(), {})
        with patch("sprouts_customer_geography.model12.public.evaluate_anchor_package", return_value=spatial):
            missing = build_anchor_public_features(support=object(), sources=missing_sources, opaque_anchor_id="fictional-anchor", latitude=44.0, longitude=-84.0, required_frozen_terms=("per_capita_income",))
        self.assertEqual(missing["state"], "MODEL_SCORE_NONCOMPUTABLE")
        self.assertIsNone(missing["public_features"]["per_capita_income"])

    def test_frozen_preprocessing_scoring_order_and_output_semantic_separation(self) -> None:
        frozen = _frozen()
        features = {"households_5mi": 1000.0, "log_households_5mi": 6.0, "inner_household_share_3mi_of_7mi": 0.2, "log_inner_outer_household_density_gradient": -0.1, "median_household_income": 11.0}
        with patch("sprouts_customer_geography.model11.modeling.fit_regularized", side_effect=AssertionError("refit prohibited")):
            scored = frozen.score(features)
        standardized = [features[term] for term in frozen.terms]
        expected_log = frozen.intercept + sum(value * coefficient for value, coefficient in zip(standardized, frozen.coefficients))
        expected_nonopportunity = sum(value * coefficient for term, value, coefficient in zip(frozen.terms, standardized, frozen.coefficients) if term != "log_households_5mi")
        self.assertEqual(scored["household_opportunity"], 1000.0)
        self.assertAlmostEqual(scored["customer_fit_proxy"], math.exp(expected_nonopportunity))
        self.assertAlmostEqual(scored["modeled_target_mass"], math.expm1(expected_log))
        self.assertNotEqual(scored["customer_fit_proxy"], scored["modeled_target_mass"])
        missing = dict(features)
        missing.pop(frozen.terms[-1])
        with self.assertRaisesRegex(ConformanceError, "MODEL_SCORE_INPUT_NONCOMPUTABLE"):
            frozen.score(missing)

    def test_repeated_location_scoring_consistency_and_explicit_noncomputability(self) -> None:
        identity = _identity()
        resolved = next(location for location in identity["physical_locations"] if not location["quarantined"])
        scored = [{
            "opaque_anchor_id": resolved["physical_location_id"], "score_computability_status": "MODEL_SCORE_COMPUTABLE", "noncomputability_reasons": [],
            "household_opportunity": 1000.0, "customer_fit_proxy": 1.2, "modeled_target_mass": 200.0, "any_support_truncation": True,
        }]
        for location in identity["physical_locations"]:
            if not location["quarantined"] and location["physical_location_id"] != resolved["physical_location_id"]:
                scored.append({
                    "opaque_anchor_id": location["physical_location_id"], "score_computability_status": "MODEL_SCORE_NONCOMPUTABLE", "noncomputability_reasons": ["FICTIONAL_MISSING"],
                    "household_opportunity": None, "customer_fit_proxy": None, "modeled_target_mass": None, "any_support_truncation": False,
                })
        package = _scoring_package(identity, scored, _frozen(), _contract(), "protected-handle-registry:sha256:" + "1" * 64)
        repeated_rows = [row for row in package["source_observations"] if row["physical_location_id"] == resolved["physical_location_id"]]
        self.assertGreater(len(repeated_rows), 1)
        self.assertEqual(len({json.dumps(row, sort_keys=True) for row in repeated_rows}), len({row["source_observation_id"] for row in repeated_rows}))
        self.assertEqual({row["customer_fit_proxy"] for row in repeated_rows}, {1.2})
        noncomputable = [row for row in package["physical_locations"] if row["score_computability_status"] == "MODEL_SCORE_NONCOMPUTABLE"]
        self.assertTrue(all(row["household_opportunity"] is row["customer_fit_proxy"] is row["modeled_target_mass"] is None for row in noncomputable))

    def test_immutable_ready_last_overwrite_rejection_and_deterministic_packages(self) -> None:
        with _temporary_directory() as temporary:
            output = Path(temporary) / "protected"
            output.mkdir()
            first = ProtectedRun(output, ROOT, collection="model12-materializations", run_id_prefix="m12run-", run_id="m12run-fictional-a")
            self.assertFalse((first.run_dir / "READY.json").exists())
            semantics = {
                "identity": {"package_id": "MODEL12_MICHIGAN_PHYSICAL_LOCATION_IDENTITY_PACKAGE_V1", "version": "1.0.0", "state": "ready", "fictional": True},
                "public_features": {"package_id": FEATURE_PACKAGE_ID, "version": "1.0.0", "state": "ready", "fictional": True},
                "frozen_scoring": {"package_id": SCORING_PACKAGE_ID, "version": "1.0.0", "state": "ready", "fictional": True},
            }
            for name, semantic in semantics.items():
                first.write_stage(name, semantic)
            first.finalize(package_id="MODEL12_MICHIGAN_TARGET_BLIND_FROZEN_SCORING_RUN_V1", aggregate={"fictional": 1}, expected_stages=("identity", "public_features", "frozen_scoring"))
            self.assertTrue((first.run_dir / "READY.json").is_file())
            with self.assertRaisesRegex(ConformanceError, "MODEL12_RUN_IMMUTABLE"):
                ProtectedRun(output, ROOT, collection="model12-materializations", run_id_prefix="m12run-", run_id="m12run-fictional-a")
            second = ProtectedRun(output, ROOT, collection="model12-materializations", run_id_prefix="m12run-", run_id="m12run-fictional-b")
            for name, semantic in semantics.items():
                second.write_stage(name, semantic)
            second.finalize(package_id="MODEL12_MICHIGAN_TARGET_BLIND_FROZEN_SCORING_RUN_V1", aggregate={"fictional": 1}, expected_stages=("identity", "public_features", "frozen_scoring"))
            comparison = compare_materializations(first.run_dir, second.run_dir)
            self.assertTrue(comparison["semantic_packages_byte_identical"])
            self.assertEqual(comparison["target_body_values_accessed"], 0)

    def test_generic_anchor_schema_and_field_scorer_never_resolves_seed_source(self) -> None:
        self.assertEqual(_validate_anchor_inputs([{"opaque_anchor_id": "fictional", "latitude": 44.0, "longitude": -84.0}])[0]["opaque_anchor_id"], "fictional")
        with self.assertRaisesRegex(ConformanceError, "MODEL12_ANCHOR_INPUT_SCHEMA_INVALID"):
            _validate_anchor_inputs([{"opaque_anchor_id": "fictional", "latitude": 44.0, "longitude": -84.0, "market": "not-permitted"}])
        with _temporary_directory() as temporary:
            directory = Path(temporary)
            output = directory / "protected-output"
            output.mkdir()
            input_path = directory / "anchors.json"
            input_path.write_text(json.dumps([{"opaque_anchor_id": "fictional", "latitude": 44.0, "longitude": -84.0}]), encoding="utf-8")
            resolver = _FakeResolver(output)
            scored = [{
                "opaque_anchor_id": "fictional", "score_computability_status": "MODEL_SCORE_COMPUTABLE", "state": "PUBLIC_FEATURES_COMPUTABLE", "noncomputability_reasons": [],
                "anchor": {"latitude": 44.0, "longitude": -84.0}, "containing_tract_geoid": "26000000001", "member_counts": {"3mi": 1, "5mi": 1, "7mi": 1},
                "public_features": {}, "data03_feature_profiles": {}, "required_frozen_feature_order": [], "support_completeness": [], "any_support_truncation": False,
                "spatial_lineage": {}, "public_source_lineage": {}, "household_opportunity": 100.0, "customer_fit_proxy": 1.0, "modeled_target_mass": 10.0,
                "model_lineage": {}, "imputation_performed": False, "member_tract_dropping_performed": False, "michigan_feature_selection_performed": False, "michigan_redundancy_screen_performed": False,
            }]
            with patch("sprouts_customer_geography.model12.materialization.load_frozen_scoring_state", return_value=_frozen()), patch("sprouts_customer_geography.model12.materialization.load_verified_public_dependencies", return_value=(object(), object())), patch("sprouts_customer_geography.model12.materialization.score_anchor_batch", return_value=scored):
                result = execute_field_scoring(repository_root=ROOT, resolver=resolver, input_path=input_path, run_id="m12field-fictional")
            self.assertEqual(result.anchor_count, 1)
            self.assertTrue((result.run_dir / "READY.json").is_file())
            package = json.loads((result.run_dir / "field_scoring" / STAGE_FILENAMES["field_scoring"]).read_text(encoding="utf-8"))
            self.assertEqual(package["package_id"], FIELD_PACKAGE_ID)
            self.assertFalse(package["execution_boundary"]["seed_source_opened"])

    def test_protected_resolver_requires_exact_handles_containment_and_public_output_scope(self) -> None:
        with _temporary_directory() as temporary:
            directory = Path(temporary)
            protected = directory / "protected"
            protected.mkdir()
            source = protected / "fictional.xlsx"
            source.write_bytes(b"fixture")
            output = protected / "output"
            output.mkdir()
            public_a = directory / "public-a"
            public_b = directory / "public-b"
            public_a.mkdir()
            public_b.mkdir()
            resources = {
                "phandle-source": {"root_handle": "proot-fixture", "relative_path": source.name, "kind": "michigan_seed_source"},
                "phandle-output": {"root_handle": "proot-fixture", "relative_path": output.name, "kind": "model12_output_root"},
            }
            request = {
                "michigan_source_handle": "phandle-source",
                "model11_development_package_handle": "phandle-source",
                "model11_development_ready_marker_handle": "phandle-source",
                "model11_development_manifest_handle": "phandle-source",
                "model11_feature_freeze_package_handle": "phandle-source",
                "model11_feature_freeze_ready_marker_handle": "phandle-source",
                "model12_output_root_handle": "phandle-output",
            }
            document = {
                "registry_id": "MODEL12_PROTECTED_HANDLE_REGISTRY_V1", "version": "1.0.0",
                "protected_roots": {"proot-fixture": str(protected.resolve())}, "resources": resources,
                "source_authority": {"source_authority_id": "FICTIONAL", "source_root_handle": "proot-fixture", "exact_basename": "fictional", "workbook_handle": "phandle-source", "whole_workbook_hash_permitted": False, "expected_forecast_vintages": [2024, 2025, 2026], "header_alias_overrides": {}},
                "public_dependencies": {"data04_ready_dir": str(public_a.resolve()), "geo05_support_dir": str(public_b.resolve())},
                "materialization_request": request,
                "upstream_model11_registry_identity": "protected-handle-registry:sha256:" + "6" * 64,
            }
            registry_path = directory / "registry.json"
            write_json_exclusive(registry_path, document)
            resolver = ProtectedHandleResolver.load(registry_path, ROOT)
            self.assertEqual(resolver.resolve_source().path, source.resolve())
            self.assertEqual(resolver.resolve("phandle-output", "model12_output_root").path, output.resolve())
            with self.assertRaisesRegex(ConformanceError, "PROTECTED_HANDLE_UNRESOLVED"):
                resolver.resolve("phandle-unknown", "model11_development_package")
            escaped = copy.deepcopy(document)
            escaped["resources"]["phandle-source"]["relative_path"] = "../outside.xlsx"
            bad_path = directory / "bad-registry.json"
            write_json_exclusive(bad_path, escaped)
            bad = ProtectedHandleResolver.load(bad_path, ROOT)
            with self.assertRaisesRegex(ConformanceError, "PROTECTED_PATH_TRAVERSAL_REJECTED"):
                bad.resolve_source()

    def test_disclosure_safe_report_contains_aggregates_not_protected_details(self) -> None:
        report = build_disclosure_safe_result(MaterializationResult(Path("protected"), 10, 7, 1, 5, 1, 2, {}))
        serialized = json.dumps(report, sort_keys=True).lower()
        self.assertEqual(report["michigan_target_body_values_accessed"], 0)
        self.assertFalse(report["model_refit_performed"])
        for forbidden in ("latitude", "longitude", "physical_location_id", "customer_fit_proxy", "modeled_target_mass", "protected_content_sha256"):
            self.assertNotIn(forbidden, serialized)


if __name__ == "__main__":
    unittest.main()
