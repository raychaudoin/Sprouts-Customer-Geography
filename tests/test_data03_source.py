"""Synthetic, target-blind conformance tests for DATA-03 public ACS sources."""

from __future__ import annotations

import copy
import csv
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from sprouts_customer_geography.data03.contract import (
    EXPECTED_MEASURE_IDS,
    EXPECTED_TABLE_IDS,
    build_api_query_url,
    metadata_identity_document,
    validate_contract,
    validate_metadata_documents,
)
from sprouts_customer_geography.data03.materialization import (
    compare_materializations,
    derive_measure,
    materialize_from_tables,
    parse_table_file,
    parse_value_pair,
)
from sprouts_customer_geography.pipe01.canonical import content_digest, file_sha256
from sprouts_customer_geography.pipe01.errors import ConformanceError


ROOT = Path(__file__).resolve().parents[1]


def load(relative: str):
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def temporary_directory() -> tempfile.TemporaryDirectory:
    return tempfile.TemporaryDirectory(dir=os.environ.get("DATA03_TEST_TEMP_ROOT") or None)


def synthetic_geoids() -> list[str]:
    return [f"55{1 + 2 * (index // 1000):03d}{index % 1000:06d}" for index in range(1542)]


def source_values(component_id: str) -> tuple[str, str]:
    estimates = {
        "vehicle_table_households_total": "100",
        "households_no_vehicle": "10",
        "commuters_total": "100",
        "commuters_drive_alone": "70",
        "commuters_work_from_home": "10",
        "education_population_25_plus": "100",
        "education_bachelors": "10",
        "education_masters": "5",
        "education_professional": "2",
        "education_doctorate": "1",
        "median_household_income": "75000",
        "per_capita_income": "40000",
        "labor_population_16_plus": "100",
        "civilian_labor_force": "65",
        "civilian_employed": "60",
        "housing_units_total": "110",
        "housing_units_vacant": "10",
        "occupied_housing_units_total": "100",
        "owner_occupied_housing_units": "60",
        "average_household_size": "2.5",
        "median_gross_rent": "1300",
        "median_home_value": "300000",
    }
    return estimates[component_id], "0.1" if component_id == "average_household_size" else "2"


def write_synthetic_sources(root: Path, contract: dict, omit_last_from: str | None = None) -> dict[str, dict]:
    manifests: dict[str, dict] = {}
    geoids = synthetic_geoids()
    for table in contract["tables"]:
        table_id = table["table_id"]
        manifest = load(table["source_manifest_path"])
        source_path = root / manifest["source_filename"]
        fields = manifest["request_identity"]["header_required"]
        rows = geoids[:-1] if table_id == omit_last_from else geoids
        with source_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, delimiter="|", lineterminator="\n")
            writer.writeheader()
            for geoid in rows:
                row = {"GEO_ID": f"1400000US{geoid}"}
                for variable in table["variables"]:
                    estimate, moe = source_values(variable["component_id"])
                    row[variable["table_estimate_field"]] = estimate
                    row[variable["table_moe_field"]] = moe
                writer.writerow(row)
        manifest["retrieval"]["expected_byte_length"] = source_path.stat().st_size
        manifest["byte_sha256"] = file_sha256(source_path)
        unhashed = copy.deepcopy(manifest)
        unhashed.pop("manifest_content_sha256")
        manifest["manifest_content_sha256"] = content_digest(unhashed)
        manifests[table_id] = manifest
    return manifests


class Data03SourceContractTests(unittest.TestCase):
    def setUp(self):
        self.contract = load("config/data/data03_wisconsin_multivariate_acs_feature_source_contract.json")
        self.schema = load("schemas/data03/wisconsin_multivariate_acs_feature_source_contract.schema.json")

    def test_exact_release_geography_menu_and_hashes_validate(self):
        self.assertEqual(validate_contract(self.contract, self.schema), self.contract["content_sha256"])
        self.assertEqual(tuple(table["table_id"] for table in self.contract["tables"]), EXPECTED_TABLE_IDS)
        self.assertEqual(tuple(measure["measure_id"] for measure in self.contract["candidate_measures"]), EXPECTED_MEASURE_IDS)
        self.assertEqual(self.contract["source_product"]["vintage"], "2024")
        self.assertEqual(self.contract["source_product"]["release_period"], "2020-2024")
        self.assertEqual(self.contract["geography"]["state_fips"], "55")
        self.assertEqual(self.contract["geography"]["level"], "tract")

    def test_estimate_moe_pairs_and_deterministic_api_query(self):
        variables = [item for table in self.contract["tables"] for variable in table["variables"] for item in (variable["estimate_variable"], variable["moe_variable"])]
        self.assertEqual(variables, self.contract["api_query_identity"]["ordered_get_variables"])
        self.assertEqual(len(variables), 44)
        first = build_api_query_url(self.contract)
        self.assertEqual(first, build_api_query_url(copy.deepcopy(self.contract)))
        self.assertTrue(first.startswith("https://api.census.gov/data/2024/acs/acs5?get="))
        self.assertIn("for=tract%3A%2A", first)
        self.assertIn("in=state%3A55", first)
        self.assertNotIn("key=", first)

    def test_stale_latest_and_pair_drift_fail_closed(self):
        stale = copy.deepcopy(self.contract)
        stale["source_product"]["vintage"] = "latest"
        with self.assertRaisesRegex(ConformanceError, "DATA03_SOURCE_VINTAGE_MISMATCH"):
            validate_contract(stale)
        moving = copy.deepcopy(self.contract)
        moving["source_product"]["api_base_url"] = "https://api.census.gov/data/latest/acs/acs5"
        with self.assertRaisesRegex(ConformanceError, "DATA03_API_IDENTITY_MISMATCH"):
            validate_contract(moving)
        broken_pair = copy.deepcopy(self.contract)
        broken_pair["tables"][0]["variables"][0]["moe_variable"] = "B08201_009M"
        with self.assertRaisesRegex(ConformanceError, "DATA03_ESTIMATE_MOE_PAIR_MISMATCH"):
            validate_contract(broken_pair)

    def test_metadata_identity_accepts_exact_schema_and_rejects_change(self):
        documents = {}
        expected = metadata_identity_document(self.contract)
        for table in self.contract["tables"]:
            variables = {}
            for variable in table["variables"]:
                for role in ("estimate", "moe"):
                    variable_id = variable[f"{role}_variable"]
                    variables[variable_id] = {**expected[variable_id], "concept": table["concept"]}
            documents[table["table_id"]] = {"variables": variables}
        self.assertEqual(validate_metadata_documents(self.contract, documents), self.contract["metadata_identity_sha256"])
        documents["B19013"]["variables"]["B19013_001E"]["label"] = "changed"
        with self.assertRaisesRegex(ConformanceError, "DATA03_METADATA_SCHEMA_CHANGED"):
            validate_metadata_documents(self.contract, documents)

    def test_special_missing_float_and_invalid_values_are_not_zero_imputed(self):
        integer = self.contract["tables"][0]["variables"][0]
        missing = parse_value_pair("-666666666", "2", integer, self.contract)
        self.assertEqual(missing["status"], "missing")
        self.assertIsNone(missing["estimate"])
        self.assertNotEqual(missing["estimate"], 0)
        suppressed = parse_value_pair("-999999999", "-222222222", integer, self.contract)
        self.assertEqual(suppressed["status"], "suppressed")
        invalid = parse_value_pair("not-a-number", "2", integer, self.contract)
        self.assertEqual(invalid["status"], "invalid")
        average = self.contract["tables"][8]["variables"][0]
        valid_float = parse_value_pair("2.75", "0.12", average, self.contract)
        self.assertEqual(valid_float["status"], "valid")
        self.assertEqual(valid_float["estimate"], 2.75)

    def test_derived_rates_handle_component_sum_and_invalid_denominator(self):
        valid_pair = lambda estimate, moe: {"estimate": estimate, "moe": moe, "status": "valid", "status_detail": "synthetic"}
        measure = next(item for item in self.contract["candidate_measures"] if item["measure_id"] == "bachelors_or_higher_share")
        components = {
            "education_bachelors": valid_pair(10, 2),
            "education_masters": valid_pair(5, 1),
            "education_professional": valid_pair(2, 1),
            "education_doctorate": valid_pair(1, 1),
            "education_population_25_plus": valid_pair(100, 4),
        }
        result = derive_measure(measure, components)
        self.assertEqual(result["status"], "valid")
        self.assertAlmostEqual(result["estimate"], 18.0)
        components["education_population_25_plus"] = valid_pair(0, 0)
        invalid = derive_measure(measure, components)
        self.assertEqual(invalid["status_detail"], "invalid_denominator")
        components["education_population_25_plus"] = valid_pair(10, 1)
        outside = derive_measure(measure, components)
        self.assertEqual(outside["status_detail"], "invalid_subset")

    def test_duplicate_tract_and_source_schema_change_fail_closed(self):
        with temporary_directory() as temporary:
            root = Path(temporary)
            table = self.contract["tables"][0]
            manifest = load(table["source_manifest_path"])
            source = root / manifest["source_filename"]
            fields = manifest["request_identity"]["header_required"]
            row = {"GEO_ID": "1400000US55001000100"}
            for variable in table["variables"]:
                row[variable["table_estimate_field"]], row[variable["table_moe_field"]] = source_values(variable["component_id"])
            with source.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields, delimiter="|", lineterminator="\n")
                writer.writeheader()
                writer.writerow(row)
                writer.writerow(row)
            manifest["retrieval"]["expected_byte_length"] = source.stat().st_size
            manifest["byte_sha256"] = file_sha256(source)
            with self.assertRaisesRegex(ConformanceError, "DATA03_DUPLICATE_TRACT"):
                parse_table_file(source, table, manifest, self.contract, enforce_contract_count=False)
            source.write_text("GEO_ID|B08201_E001\n1400000US55001000100|100\n", encoding="utf-8")
            manifest["retrieval"]["expected_byte_length"] = source.stat().st_size
            manifest["byte_sha256"] = file_sha256(source)
            with self.assertRaisesRegex(ConformanceError, "DATA03_SOURCE_SCHEMA_CHANGED"):
                parse_table_file(source, table, manifest, self.contract, enforce_contract_count=False)

    def test_complete_materialization_schema_and_rerun_are_deterministic(self):
        with temporary_directory() as temporary:
            root = Path(temporary)
            raw = root / "raw"
            raw.mkdir()
            manifests = write_synthetic_sources(raw, self.contract)
            first = root / "outputs" / "first"
            second = root / "outputs" / "second"
            first_report = materialize_from_tables(self.contract, manifests, ROOT, raw, synthetic_geoids(), first, validate_cached_metadata=False)
            second_report = materialize_from_tables(self.contract, manifests, ROOT, raw, synthetic_geoids(), second, validate_cached_metadata=False)
            self.assertEqual(first_report, second_report)
            self.assertEqual(first_report["tract_count"], 1542)
            self.assertEqual(first_report["normalized_output"]["row_count"], 1542 * 22)
            self.assertEqual(first_report["candidate_output"]["row_count"], 1542)
            compare_materializations(first, second)
            with (first / "wisconsin_tract_candidate_measures.csv").open(encoding="utf-8", newline="") as handle:
                header = next(csv.reader(handle))
            expected_header = list(self.contract["output_contract"]["wide_key_columns"])
            for measure_id in EXPECTED_MEASURE_IDS:
                expected_header.extend(f"{measure_id}_{suffix}" for suffix in self.contract["output_contract"]["wide_measure_suffixes"])
            self.assertEqual(header, expected_header)

    def test_missing_tract_key_fails_complete_coverage(self):
        with temporary_directory() as temporary:
            root = Path(temporary)
            raw = root / "raw"
            raw.mkdir()
            manifests = write_synthetic_sources(raw, self.contract, omit_last_from="B25077")
            with self.assertRaisesRegex(ConformanceError, "DATA03_WISCONSIN_TRACT_COUNT_MISMATCH|DATA03_COMPLETE_TRACT_COVERAGE_FAILED"):
                materialize_from_tables(self.contract, manifests, ROOT, raw, synthetic_geoids(), root / "outputs" / "missing", validate_cached_metadata=False)

    def test_raw_and_generated_data_are_git_ignored(self):
        result = subprocess.run(
            ["git", "check-ignore", "--no-index", "data/raw/data03/example.dat", "outputs/data03/example.csv"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertIn("data/raw/data03/example.dat", result.stdout)
        self.assertIn("outputs/data03/example.csv", result.stdout)

    def test_protected_characteristic_boundary_is_an_exact_allowlist(self):
        policy = self.contract["protected_characteristic_policy"]
        self.assertTrue(policy["direct_proxy_recreation_prohibited"])
        self.assertTrue(policy["all_candidate_measures_clear"])
        self.assertEqual({measure["protected_characteristic_basis"] for measure in self.contract["candidate_measures"]}, {False})
        variable_ids = {variable["estimate_variable"] for table in self.contract["tables"] for variable in table["variables"]}
        forbidden_prefixes = ("B01001_", "B02001_", "B03003_", "B05001_", "B18101_")
        self.assertFalse(any(variable_id.startswith(forbidden_prefixes) for variable_id in variable_ids))


if __name__ == "__main__":
    unittest.main()
