"""Synthetic and repository-safe conformance tests for DATA-04 Michigan public sources."""

from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Src"))

from sprouts_customer_geography.data03.contract import EXPECTED_MEASURE_IDS, EXPECTED_TABLE_IDS
from sprouts_customer_geography.data03.acquisition import download_pinned_exact
from sprouts_customer_geography.data03.materialization import materialize_from_tables, parse_table_file
from sprouts_customer_geography.data04.contract import EXPECTED_TRACT_COUNT, load_authority
from sprouts_customer_geography.data04.materialization import (
    HOUSEHOLD_COLUMNS,
    TIGER_COLUMNS,
    _require_expected_source_row_reconciliation,
    compare_materializations,
)
from sprouts_customer_geography.pipe01.canonical import content_digest, file_sha256
from sprouts_customer_geography.pipe01.errors import ConformanceError
from sprouts_customer_geography.pipe01.production import load_statewide_acs_b11001_evidence


def load(relative: str):
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def temporary_directory() -> tempfile.TemporaryDirectory:
    return tempfile.TemporaryDirectory(dir=os.environ.get("DATA04_TEST_TEMP_ROOT") or None)


def synthetic_michigan_geoids(count: int = 3) -> list[str]:
    return [f"26001{index:06d}" for index in range(1, count + 1)]


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


def write_multivariate_sources(root: Path, authority, geoids: list[str], omit_last_from: str | None = None, extra_geoid_in: str | None = None) -> dict[str, dict]:
    manifests: dict[str, dict] = {}
    for table in authority.data03_contract["tables"]:
        manifest = copy.deepcopy(authority.multivariate_manifests[table["table_id"]])
        source = root / manifest["source_filename"]
        fields = manifest["request_identity"]["header_required"]
        with source.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, delimiter="|", lineterminator="\n")
            writer.writeheader()
            table_geoids = geoids[:-1] if table["table_id"] == omit_last_from else list(geoids)
            if table["table_id"] == extra_geoid_in:
                table_geoids.append("26003000001")
            for geoid in table_geoids:
                row = {"GEO_ID": f"1400000US{geoid}"}
                for variable in table["variables"]:
                    row[variable["table_estimate_field"]], row[variable["table_moe_field"]] = source_values(variable["component_id"])
                writer.writerow(row)
        manifest["retrieval"]["expected_byte_length"] = source.stat().st_size
        manifest["byte_sha256"] = file_sha256(source)
        unhashed = copy.deepcopy(manifest)
        unhashed.pop("manifest_content_sha256")
        manifest["manifest_content_sha256"] = content_digest(unhashed)
        manifests[table["table_id"]] = manifest
    return manifests


class Data04SourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.authority = load_authority(ROOT)

    def test_exact_state_vintage_and_source_authority(self):
        contract = self.authority.contract
        self.assertEqual(contract["state_scope"]["state_fips"], "26")
        self.assertEqual(contract["state_scope"]["table_file_geo_id_prefix"], "1400000US26")
        self.assertEqual(contract["state_scope"]["observed_tract_count"], EXPECTED_TRACT_COUNT)
        self.assertTrue(contract["state_scope"]["statewide"])
        self.assertEqual(contract["source_products"]["acs"]["vintage"], "2024")
        self.assertEqual(contract["source_products"]["tiger"]["vintage"], "2024")
        self.assertFalse(contract["source_products"]["acs"]["credential_required"])

    def test_exact_data03_tables_pairs_measures_and_semantics_are_reused(self):
        data03 = self.authority.data03_contract
        contract = self.authority.contract
        self.assertEqual(tuple(table["table_id"] for table in data03["tables"]), EXPECTED_TABLE_IDS)
        self.assertEqual(sum(len(table["variables"]) for table in data03["tables"]), 22)
        self.assertEqual(tuple(measure["measure_id"] for measure in data03["candidate_measures"]), EXPECTED_MEASURE_IDS)
        reference = contract["accepted_acs_national_authority"]["data03_contract"]
        self.assertEqual(content_digest(data03["tables"]), reference["table_identity_sha256"])
        self.assertEqual(content_digest(data03["candidate_measures"]), reference["candidate_measure_identity_sha256"])
        self.assertEqual(content_digest(data03["special_value_contract"]), reference["special_value_contract_sha256"])
        self.assertEqual(content_digest(data03["derivation_contract"]), reference["derivation_contract_sha256"])

    def test_exact_observed_multivariate_source_row_coverage_is_pinned(self):
        expected = self.authority.contract["multivariate_extraction"]["expected_source_row_reconciliation"]
        self.assertEqual(tuple(expected), EXPECTED_TABLE_IDS)
        self.assertEqual(expected["B19301"]["present_source_row_count"], 3011)
        self.assertEqual(expected["B19301"]["missing_source_row_count"], 6)
        self.assertTrue(all(value["extra_source_row_count"] == 0 for value in expected.values()))
        actual = {table_id: {**counts, "missing_source_row_geoids": []} for table_id, counts in expected.items()}
        _require_expected_source_row_reconciliation(actual, expected)
        actual["B19301"]["missing_source_row_count"] = 5
        with self.assertRaisesRegex(ConformanceError, "DATA04_SOURCE_ROW_RECONCILIATION_MISMATCH"):
            _require_expected_source_row_reconciliation(actual, expected)

    def test_exact_national_source_manifest_byte_identities_are_bound(self):
        accepted = self.authority.contract["accepted_acs_national_authority"]
        self.assertEqual(accepted["household_manifest"]["source_byte_sha256"], self.authority.household_manifest["byte_sha256"])
        for reference in accepted["multivariate_tables"]:
            manifest = self.authority.multivariate_manifests[reference["table_id"]]
            self.assertEqual(reference["source_filename"], manifest["source_filename"])
            self.assertEqual(reference["source_byte_length"], manifest["retrieval"]["expected_byte_length"])
            self.assertEqual(reference["source_byte_sha256"], manifest["byte_sha256"])
            self.assertEqual(reference["manifest_content_sha256"], manifest["manifest_content_sha256"])

    def test_pinned_downloader_preserves_partial_and_retries_without_promoting_it(self):
        with temporary_directory() as temporary:
            root = Path(temporary)
            destination = root / "source.dat"
            incomplete = destination.with_name(destination.name + ".partial")
            incomplete.write_bytes(b"incomplete")
            expected = b"exact accepted source bytes"

            with patch("sprouts_customer_geography.data03.acquisition.urlopen", return_value=io.BytesIO(expected)):
                observation = download_pinned_exact("https://example.invalid/source.dat", destination, len(expected), hashlib.sha256(expected).hexdigest(), lambda _: None)
            self.assertTrue(destination.is_file())
            self.assertEqual(destination.read_bytes(), expected)
            self.assertTrue(incomplete.is_file())
            self.assertFalse(destination.with_name(destination.name + ".partial.2").exists())
            self.assertFalse(observation["reused_existing"])

    def test_pinned_downloader_rejects_wrong_complete_bytes_before_promotion(self):
        with temporary_directory() as temporary:
            root = Path(temporary)
            destination = root / "source.dat"
            expected = b"exact accepted source bytes"

            with patch("sprouts_customer_geography.data03.acquisition.urlopen", return_value=io.BytesIO(b"different complete bytes")):
                with self.assertRaisesRegex(ConformanceError, "PINNED_SOURCE_(LENGTH|CHECKSUM)_MISMATCH"):
                    download_pinned_exact("https://example.invalid/source.dat", destination, len(expected), hashlib.sha256(expected).hexdigest(), lambda _: None)
            self.assertFalse(destination.exists())
            self.assertTrue(destination.with_name(destination.name + ".partial").is_file())

    def test_pinned_downloader_retries_transient_failure_in_a_new_partial_slot(self):
        with temporary_directory() as temporary:
            destination = Path(temporary) / "source.dat"
            expected = b"exact accepted source bytes"
            with patch(
                "sprouts_customer_geography.data03.acquisition.urlopen",
                side_effect=[OSError("synthetic transient failure"), io.BytesIO(expected)],
            ) as mocked_open:
                observation = download_pinned_exact(
                    "https://example.invalid/source.dat",
                    destination,
                    len(expected),
                    hashlib.sha256(expected).hexdigest(),
                    lambda _: None,
                )
            self.assertEqual(mocked_open.call_count, 2)
            self.assertEqual(destination.read_bytes(), expected)
            self.assertFalse(observation["reused_existing"])

    def test_michigan_tiger_manifest_pins_complete_source_evidence(self):
        manifest = self.authority.tiger_manifest
        properties = manifest["expected_file_properties"]
        self.assertEqual(manifest["source_filename"], "tl_2024_26_tract.zip")
        self.assertEqual(manifest["byte_sha256"], "220c0a351d94c9de456d87c5db78f3e3864b3287370350f1e503a84565224e82")
        self.assertEqual(properties["expected_statewide_tract_row_count_at_retrieval"], EXPECTED_TRACT_COUNT)
        self.assertEqual(properties["expected_geometry_record_count_at_retrieval"], EXPECTED_TRACT_COUNT)
        self.assertEqual(properties["expected_parseable_internal_point_count_at_retrieval"], EXPECTED_TRACT_COUNT)
        self.assertEqual(properties["expected_crs"], "EPSG:4269")
        self.assertEqual(set(properties["required_source_fields"]), {"STATEFP", "COUNTYFP", "TRACTCE", "GEOID", "INTPTLAT", "INTPTLON"})

    def test_b11001_state_extraction_preserves_special_status_and_ignores_wisconsin(self):
        with temporary_directory() as temporary:
            source = Path(temporary) / "acsdt5y2024-b11001.dat"
            with source.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["GEO_ID", "B11001_E001", "B11001_M001"], delimiter="|", lineterminator="\n")
                writer.writeheader()
                writer.writerow({"GEO_ID": "1400000US26001000001", "B11001_E001": "100", "B11001_M001": "5"})
                writer.writerow({"GEO_ID": "1400000US26001000002", "B11001_E001": "-666666666", "B11001_M001": "2"})
                writer.writerow({"GEO_ID": "1400000US55001000001", "B11001_E001": "999", "B11001_M001": "1"})
            manifest = copy.deepcopy(self.authority.household_manifest)
            manifest["retrieval"]["expected_byte_length"] = source.stat().st_size
            manifest["byte_sha256"] = file_sha256(source)
            evidence, lineage = load_statewide_acs_b11001_evidence(source, manifest, "26", 2)
            self.assertEqual(set(evidence), {"26001000001", "26001000002"})
            self.assertEqual(evidence["26001000001"]["estimate"], 100)
            self.assertEqual(evidence["26001000002"]["status"], "missing")
            self.assertIsNone(evidence["26001000002"]["estimate"])
            self.assertEqual(lineage["table_file_geo_id_prefix"], "1400000US26")

    def test_b11001_missing_source_row_is_distinct_and_fails_closed(self):
        with temporary_directory() as temporary:
            source = Path(temporary) / "acsdt5y2024-b11001.dat"
            source.write_text("GEO_ID|B11001_E001|B11001_M001\n1400000US26001000001|0|0\n", encoding="utf-8")
            manifest = copy.deepcopy(self.authority.household_manifest)
            manifest["retrieval"]["expected_byte_length"] = source.stat().st_size
            manifest["byte_sha256"] = file_sha256(source)
            with self.assertRaisesRegex(ConformanceError, "ACS_STATE_TRACT_COUNT_MISMATCH"):
                load_statewide_acs_b11001_evidence(source, manifest, "26", 2)

    def test_generalized_b11001_loader_preserves_wisconsin_count_error_identity(self):
        with temporary_directory() as temporary:
            source = Path(temporary) / "acsdt5y2024-b11001.dat"
            source.write_text("GEO_ID|B11001_E001|B11001_M001\n1400000US55001000001|0|0\n", encoding="utf-8")
            manifest = copy.deepcopy(self.authority.household_manifest)
            manifest["retrieval"]["expected_byte_length"] = source.stat().st_size
            manifest["byte_sha256"] = file_sha256(source)
            with self.assertRaisesRegex(ConformanceError, "ACS_WISCONSIN_TRACT_COUNT_MISMATCH"):
                load_statewide_acs_b11001_evidence(source, manifest, "55", 2)

    def test_shared_data03_parser_uses_explicit_michigan_state_configuration(self):
        with temporary_directory() as temporary:
            root = Path(temporary)
            table = self.authority.data03_contract["tables"][0]
            manifest = copy.deepcopy(self.authority.multivariate_manifests[table["table_id"]])
            source = root / manifest["source_filename"]
            fields = manifest["request_identity"]["header_required"]
            with source.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields, delimiter="|", lineterminator="\n")
                writer.writeheader()
                for geoid in ("26001000001", "26001000002", "55001000001"):
                    row = {"GEO_ID": f"1400000US{geoid}"}
                    for variable in table["variables"]:
                        row[variable["table_estimate_field"]], row[variable["table_moe_field"]] = source_values(variable["component_id"])
                    writer.writerow(row)
            manifest["retrieval"]["expected_byte_length"] = source.stat().st_size
            manifest["byte_sha256"] = file_sha256(source)
            parsed = parse_table_file(source, table, manifest, self.authority.data03_contract, state_configuration={"state_name": "Michigan", "state_slug": "michigan", "state_fips": "26", "table_file_geo_id_prefix": "1400000US26", "expected_tract_count": 2})
            self.assertEqual(set(parsed), {"26001000001", "26001000002"})

    def test_shared_materializer_produces_michigan_outputs_without_row_dropping(self):
        with temporary_directory() as temporary:
            root = Path(temporary)
            raw = root / "raw"
            raw.mkdir()
            geoids = synthetic_michigan_geoids()
            manifests = write_multivariate_sources(raw, self.authority, geoids)
            state = {"state_name": "Michigan", "state_slug": "michigan", "state_fips": "26", "table_file_geo_id_prefix": "1400000US26", "expected_tract_count": len(geoids), "report_id": "DATA04_SYNTHETIC_MI_REPORT"}
            first = root / "first"
            second = root / "second"
            one = materialize_from_tables(self.authority.data03_contract, manifests, ROOT, raw, geoids, first, validate_cached_metadata=False, state_configuration=state)
            two = materialize_from_tables(self.authority.data03_contract, manifests, ROOT, raw, geoids, second, validate_cached_metadata=False, state_configuration=state)
            self.assertEqual(one, two)
            self.assertEqual(one["tract_count"], len(geoids))
            self.assertEqual(one["normalized_output"]["row_count"], len(geoids) * 22)
            self.assertEqual(one["candidate_output"]["row_count"], len(geoids))
            self.assertTrue((first / "michigan_tract_source_values.csv").is_file())
            self.assertTrue((first / "michigan_tract_candidate_measures.csv").is_file())

    def test_missing_multivariate_source_row_is_retained_and_distinct_from_value_missingness(self):
        with temporary_directory() as temporary:
            root = Path(temporary)
            raw = root / "raw"
            raw.mkdir()
            geoids = synthetic_michigan_geoids()
            manifests = write_multivariate_sources(raw, self.authority, geoids, omit_last_from="B19301")
            state = {"state_name": "Michigan", "state_slug": "michigan", "state_fips": "26", "table_file_geo_id_prefix": "1400000US26", "expected_tract_count": len(geoids), "report_id": "DATA04_SYNTHETIC_MI_REPORT"}
            output = root / "output"
            report = materialize_from_tables(self.authority.data03_contract, manifests, ROOT, raw, geoids, output, validate_cached_metadata=False, state_configuration=state, allow_missing_source_rows=True)
            reconciliation = report["source_row_reconciliation"]["B19301"]
            self.assertEqual(reconciliation["missing_source_row_count"], 1)
            self.assertEqual(reconciliation["missing_source_row_geoids"], [geoids[-1]])
            with (output / "michigan_tract_source_values.csv").open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            missing = [row for row in rows if row["tract_geoid"] == geoids[-1] and row["table_id"] == "B19301"]
            self.assertEqual(len(missing), 1)
            self.assertEqual(missing[0]["status"], "missing")
            self.assertEqual(missing[0]["status_detail"], "source_row_missing")
            self.assertEqual(len(rows), len(geoids) * 22)

    def test_extra_multivariate_source_row_fails_reconciliation(self):
        with temporary_directory() as temporary:
            root = Path(temporary)
            raw = root / "raw"
            raw.mkdir()
            geoids = synthetic_michigan_geoids()
            manifests = write_multivariate_sources(raw, self.authority, geoids, extra_geoid_in="B19301")
            state = {"state_name": "Michigan", "state_slug": "michigan", "state_fips": "26", "table_file_geo_id_prefix": "1400000US26", "expected_tract_count": len(geoids), "report_id": "DATA04_SYNTHETIC_MI_REPORT"}
            with self.assertRaisesRegex(ConformanceError, "DATA03_COMPLETE_TRACT_COVERAGE_FAILED"):
                materialize_from_tables(self.authority.data03_contract, manifests, ROOT, raw, geoids, root / "output", validate_cached_metadata=False, state_configuration=state, allow_missing_source_rows=True)

    def test_data04_recursive_comparison_detects_determinism_and_difference(self):
        with temporary_directory() as temporary:
            root = Path(temporary)
            first, second = root / "first", root / "second"
            for directory in (first, second):
                (directory / "multivariate").mkdir(parents=True)
                (directory / "example.csv").write_text("a\n1\n", encoding="utf-8")
                (directory / "multivariate" / "example.csv").write_text("b\n2\n", encoding="utf-8")
                (directory / "READY.json").write_text("{}\n", encoding="utf-8")
            report = compare_materializations(first, second)
            self.assertEqual(report["state"], "DETERMINISTIC_BYTE_IDENTICAL")
            (second / "example.csv").write_text("a\n3\n", encoding="utf-8")
            with self.assertRaisesRegex(ConformanceError, "DATA04_RERUN_NONDETERMINISTIC"):
                compare_materializations(first, second)

    def test_output_schemas_bind_ordered_columns(self):
        household_schema = load("schemas/data04/michigan_b11001_tract_evidence.schema.json")
        tiger_schema = load("schemas/data04/michigan_tiger_tract_evidence.schema.json")
        report_schema = load("schemas/data04/michigan_public_data_materialization_report.schema.json")
        self.assertEqual(household_schema["required"], HOUSEHOLD_COLUMNS)
        self.assertEqual(tiger_schema["required"], TIGER_COLUMNS)
        self.assertEqual(report_schema["properties"]["tract_count"]["const"], EXPECTED_TRACT_COUNT)

    def test_michigan_and_wisconsin_authority_are_separate(self):
        self.assertEqual(self.authority.data03_contract["geography"]["state_fips"], "55")
        self.assertEqual(self.authority.contract["state_scope"]["state_fips"], "26")
        self.assertEqual(self.authority.household_manifest["request_identity"]["geography_selection"].split("1400000US")[1][:2], "55")
        self.assertEqual(self.authority.contract["household_extraction"]["extraction_id"], "DATA04_ACS2024_ACS5_B11001_MI_TRACT_EXTRACTION_V1")

    def test_protected_characteristic_and_protected_evidence_boundaries(self):
        contract = self.authority.contract
        self.assertTrue(contract["protected_evidence_boundary"]["public_data_only"])
        self.assertEqual(contract["protected_evidence_boundary"]["protected_filesystem_discovery"], "prohibited and unnecessary")
        variable_ids = {variable["estimate_variable"] for table in self.authority.data03_contract["tables"] for variable in table["variables"]}
        forbidden = ("B01001_", "B02001_", "B03003_", "B05001_", "B18101_")
        self.assertFalse(any(variable.startswith(forbidden) for variable in variable_ids))

    def test_downstream_readiness_is_source_only(self):
        readiness = self.authority.contract["downstream_readiness_contract"]
        self.assertIn("B11001 household estimate and MOE", readiness["model11_public_source_requirements"])
        self.assertEqual(readiness["geo_methodology_change"], "prohibited")
        self.assertEqual(readiness["model_execution"], "prohibited")

    def test_raw_generated_paths_are_ignored_and_not_stageable(self):
        ignored = subprocess.run(["git", "check-ignore", "--no-index", "data/raw/data04/example.zip", "outputs/data04/example.csv"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
        self.assertIn("data/raw/data04/example.zip", ignored)
        self.assertIn("outputs/data04/example.csv", ignored)
        stageable = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.splitlines()
        self.assertFalse(any(path.replace("\\", "/").startswith(("data/raw/", "outputs/")) for path in stageable))

    def test_single_manifest_and_work_order_identity(self):
        self.assertEqual(len(list((ROOT / "governance" / "tasks").glob("DATA-04*.task.json"))), 1)
        self.assertEqual(len(list((ROOT / "docs" / "work_orders").glob("DATA_04*.md"))), 1)
        task = load("governance/tasks/DATA-04.michigan-public-data-parity-foundation.task.json")
        self.assertEqual(task["implementation_branch"], "task/data-04-michigan-public-data-parity-foundation")
        self.assertEqual(task["capability_owner"], "DATA Public Data Sources")
        self.assertIn(
            (task["state"], task["completion_state"]["capability_acceptance"]),
            {
                ("COMPLETED_AWAITING_ACCEPTANCE", "NOT_REVIEWED"),
                ("ACCEPTED_CLOSED", "ACCEPTED"),
            },
        )


if __name__ == "__main__":
    unittest.main()
