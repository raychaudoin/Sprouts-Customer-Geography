from __future__ import annotations

import io
import json
import re
import tempfile
import unittest
import zipfile
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from sprouts_customer_geography.model06 import ProjectedWorkbook, read_target_blind_projection
from sprouts_customer_geography.model10 import cli
from sprouts_customer_geography.model10.binding import (
    PACKAGE_ID,
    MaterializationResult,
    ProtectedSuccessorRun,
    build_disclosure_safe_result,
    build_successor_identity_package,
    protected_materialization_is_ready,
)
from sprouts_customer_geography.model10.resolver import ProtectedHandleResolver, load_authorized_registry
from sprouts_customer_geography.pipe01.canonical import canonical_bytes, content_digest, write_json_exclusive
from sprouts_customer_geography.pipe01.errors import ConformanceError
from sprouts_customer_geography.pipe01.safeguards import assert_no_protected_tracked_paths


ROOT = Path(__file__).resolve().parents[1]
TEST_TMP = ROOT / ".tmp" / "model10-tests"
FICTIONAL_REPOSITORY_ROOT = ROOT / "fictional-repository-boundary"
TEST_TMP.mkdir(parents=True, exist_ok=True)


def _row(
    number: int,
    year: int,
    seed: str,
    latitude: float,
    longitude: float,
    market: str,
    address: str,
) -> dict:
    return {
        "source_row": number,
        "vintage": year,
        "seed_point_id": seed,
        "address": address,
        "city": market.title(),
        "state": "WI",
        "zip": "00000",
        "latitude": latitude,
        "longitude": longitude,
        "market": market.title(),
    }


def _rows() -> list[dict]:
    return [
        _row(20, 2024, "SUCCESSOR-MKE-24", 43.000000, -87.900000, "milwaukee", "1 Fictional Way"),
        _row(44, 2025, "CHANGED-MKE-25", 43.000000, -87.900000, "milwaukee", "1 Fictional Way"),
        _row(61, 2026, "NEW-MKE-26", 43.100000, -87.900000, "milwaukee", "99 Fictional Way"),
        _row(22, 2024, "SUCCESSOR-MAD-24", 43.070000, -89.400000, "madison", "2 Imaginary Lane"),
        _row(48, 2025, "CHANGED-MAD-25", 43.070000, -89.400000, "madison", "2 Imaginary Lane"),
        _row(65, 2026, "NEW-MAD-26", 43.200000, -89.400000, "madison", "88 Imaginary Lane"),
    ]


def _projected(rows: list[dict] | None = None) -> ProjectedWorkbook:
    values = rows or _rows()
    return ProjectedWorkbook(
        source_identity="FICTIONAL-CONSOLIDATED-WISCONSIN-SUCCESSOR",
        rows=tuple(values),
        projection_sha256=content_digest(values),
        access_report={
            "source_identity": "FICTIONAL-CONSOLIDATED-WISCONSIN-SUCCESSOR",
            "worksheet_member": "xl/worksheets/sheet1.xml",
            "sheet_logical_name": "Sheet1",
            "body_projection": "A:I",
            "body_rows_materialized": len(values),
            "maximum_authorized_body_column": "I",
            "outside_projection_body_values_materialized": 0,
            "formula_values_materialized": 0,
            "styles_comments_charts_metadata_loaded": False,
            "target_headers_confirmed_outside_projection": ["impactedsales", "isolatedsales"],
            "max_body_column_observed_by_reference_only": 11,
        },
    )


def _historical() -> dict:
    def record(location: str, seed: str, latitude: float, longitude: float, market: str, role: str, state: str) -> dict:
        return {
            "physical_location_id": location,
            "source_seed_point_id": seed,
            "market": market,
            "quarantined": False,
            "observed_coordinate": {"latitude": latitude, "longitude": longitude},
            "evidence_role": role,
            "evidence_subrole": "FICTIONAL-HISTORICAL-LINEAGE",
            "target_view_state": state,
        }

    return {
        "package_id": "MODEL04_VALIDATION_IDENTITY_ROLE_ANCHOR_PACKAGE_V1",
        "package_version": "1.0.0",
        "identity_version": "MODEL04_TARGET_BLIND_PHYSICAL_LOCATION_IDENTITY_V1",
        "records": [
            record("ploc-fictional-historical-mke", "OLD-MKE", 43.0, -87.9, "milwaukee", "DEVELOPMENT_REFERENCE", "DEVELOPMENT_CONSUMED"),
            record("ploc-fictional-historical-mad", "OLD-MAD", 43.07, -89.4, "madison", "EXTERNAL_MADISON_HOLDOUT", "SEALED"),
        ],
    }


def _package(rows: list[dict] | None = None, run_id: str = "m10run-fictional") -> dict:
    return build_successor_identity_package(
        [_projected(rows)],
        _historical(),
        materialization_run_id=run_id,
    )


def _xlsx_payload(targets: tuple[str, str]) -> bytes:
    headers = ["Year", "Seedpoint_ID", "Address", "City", "State", "Zip", "Lat", "Long", "MSA", "Isolated Sales", "Impacted Sales"]
    letters = "ABCDEFGHIJK"
    header_cells = "".join(
        f"<c r='{letter}1' t='inlineStr'><is><t>{header}</t></is></c>"
        for letter, header in zip(letters, headers)
    )
    body: list[str] = []
    for index, row in enumerate(_rows(), start=2):
        values = [row["vintage"], row["seed_point_id"], row["address"], row["city"], row["state"], row["zip"], row["latitude"], row["longitude"], row["market"]]
        cells: list[str] = []
        for letter, value in zip(letters[:9], values):
            if isinstance(value, (int, float)) and letter not in {"F"}:
                cells.append(f"<c r='{letter}{index}'><v>{value}</v></c>")
            else:
                cells.append(f"<c r='{letter}{index}' t='inlineStr'><is><t>{value}</t></is></c>")
        cells.append(f"<c r='J{index}'><v>{targets[0]}</v></c>")
        cells.append(f"<c r='K{index}'><v>{targets[1]}</v></c>")
        body.append(f"<row r='{index}'>" + "".join(cells) + "</row>")
    sheet = "<?xml version='1.0' encoding='UTF-8'?><worksheet xmlns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'><sheetData><row r='1'>" + header_cells + "</row>" + "".join(body) + "</sheetData></worksheet>"
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr("xl/worksheets/sheet1.xml", sheet)
    return payload.getvalue()


def _registry(root: Path, registry_path: Path) -> ProtectedHandleResolver:
    for name in ("model04.json", "model04-nonce.bin", "successor.xlsx"):
        (root / name).write_bytes(b"fixture")
    (root / "output").mkdir(exist_ok=True)
    document = {
        "registry_id": "MODEL10_PROTECTED_HANDLE_REGISTRY_V1",
        "version": "1.0.0",
        "protected_roots": {"proot-fixture": str(root.resolve())},
        "resources": {
            "phandle-model04": {"root_handle": "proot-fixture", "relative_path": "model04.json", "kind": "model04_package"},
            "phandle-model04-verification": {"root_handle": "proot-fixture", "relative_path": "model04-nonce.bin", "kind": "model04_verification_material"},
            "phandle-successor": {"root_handle": "proot-fixture", "relative_path": "successor.xlsx", "kind": "wisconsin_successor_identity_workbook"},
            "phandle-output": {"root_handle": "proot-fixture", "relative_path": "output", "kind": "model10_output_root"},
        },
        "materialization_request": {
            "model04_package_handle": "phandle-model04",
            "model04_verification_material_handle": "phandle-model04-verification",
            "successor_workbook_handles": ["phandle-successor"],
            "materialization_output_root_handle": "phandle-output",
        },
        "successor_source_authorities": [
            {
                "authority_id": "FICTIONAL-SUCCESSOR-AUTHORITY",
                "provenance_class": "fictional_conformance",
                "source_workbook_identity": "FICTIONAL-CONSOLIDATED-WISCONSIN-SUCCESSOR",
                "workbook_handle": "phandle-successor",
                "byte_hash_permitted": False,
                "projection_id": "MODEL04_TARGET_BLIND_A_I_IDENTITY_PROJECTION_V1",
                "expected_observation_count": 6,
                "expected_forecast_vintages": [2024, 2025, 2026],
                "expected_markets": ["milwaukee", "madison"],
            }
        ],
    }
    write_json_exclusive(registry_path, document)
    return ProtectedHandleResolver.load(registry_path, FICTIONAL_REPOSITORY_ROOT)


class Model10IdentityLineageTests(unittest.TestCase):
    def test_01_historical_model04_physical_location_and_role_are_preserved(self):
        package = _package()
        linked = [record for record in package["records"] if record["source_observation_lineage"]["source_seed_point_id"] == "SUCCESSOR-MKE-24"][0]
        self.assertEqual(linked["successor_physical_location_id"], "ploc-fictional-historical-mke")
        self.assertEqual(linked["historical_model04_physical_location_id"], "ploc-fictional-historical-mke")
        self.assertEqual(linked["physical_location_identity_origin"], "HISTORICAL_MODEL04")
        self.assertEqual(linked["historical_evidence_role_lineage"][0]["evidence_role"], "DEVELOPMENT_REFERENCE")

    def test_02_changed_source_row_and_seed_id_remain_same_physical_location(self):
        package = _package()
        mke = [
            record
            for record in package["records"]
            if record["source_observation_lineage"]["source_seed_point_id"]
            in {"SUCCESSOR-MKE-24", "CHANGED-MKE-25"}
        ]
        self.assertEqual(len({record["source_observation_id"] for record in mke}), 2)
        self.assertEqual({record["successor_physical_location_id"] for record in mke}, {"ploc-fictional-historical-mke"})
        self.assertEqual({record["identity_state"] for record in mke}, {"SAME_UNDERLYING_LOCATION"})

    def test_03_genuinely_new_locations_are_classified_without_historical_link(self):
        package = _package()
        new = [record for record in package["records"] if record["source_observation_lineage"]["source_seed_point_id"] == "NEW-MKE-26"][0]
        self.assertEqual(new["identity_state"], "GENUINELY_NEW_LOCATION")
        self.assertTrue(new["successor_physical_location_id"].startswith("m10loc-"))
        self.assertIsNone(new["historical_model04_physical_location_id"])
        self.assertTrue(new["model09_development_eligible"])

    def test_04_ambiguity_is_quarantined_and_ineligible(self):
        rows = _rows()
        rows[2] = _row(61, 2026, "AMBIGUOUS-MKE-26", 43.002000, -87.900000, "milwaukee", "Unresolved Fictional Way")
        package = _package(rows)
        ambiguous = [record for record in package["records"] if record["source_observation_lineage"]["source_seed_point_id"] == "AMBIGUOUS-MKE-26"][0]
        self.assertEqual(ambiguous["identity_state"], "AMBIGUOUS_IDENTITY")
        self.assertTrue(ambiguous["quarantined"])
        self.assertFalse(ambiguous["model09_development_eligible"])
        self.assertEqual(ambiguous["quarantine_reason"], "CONFLICTING_OR_10_TO_500M_IDENTITY_EVIDENCE")

    def test_05_target_values_cannot_influence_identity_or_lineage(self):
        first = read_target_blind_projection(_xlsx_payload(("101", "202")), "FICTIONAL-CONSOLIDATED-WISCONSIN-SUCCESSOR")
        second = read_target_blind_projection(_xlsx_payload(("999999", "888888")), "FICTIONAL-CONSOLIDATED-WISCONSIN-SUCCESSOR")
        self.assertEqual(first.rows, second.rows)
        one = build_successor_identity_package([first], _historical(), materialization_run_id="m10run-target-invariant")
        two = build_successor_identity_package([second], _historical(), materialization_run_id="m10run-target-invariant")
        self.assertEqual(one, two)
        serialized = canonical_bytes(one)
        self.assertNotIn(b"999999", serialized)
        self.assertNotIn(b"888888", serialized)
        self.assertTrue(one["target_access"]["isolated_sales_accessed"] is False)

    def test_06_incomplete_vintage_cohort_fails_closed(self):
        rows = [row for row in _rows() if row["vintage"] != 2025]
        with self.assertRaisesRegex(ConformanceError, "SUCCESSOR_COHORT_VINTAGE_INCOMPLETE"):
            _package(rows)

    def test_07_source_observation_identity_is_distinct_from_physical_identity(self):
        package = _package()
        repeated = [record for record in package["records"] if record["successor_physical_location_id"] == "ploc-fictional-historical-mad"]
        self.assertEqual(len(repeated), 2)
        self.assertEqual(len({record["source_observation_id"] for record in repeated}), 2)

    def test_08_explicit_handle_resolution_and_containment(self):
        with tempfile.TemporaryDirectory(dir=TEST_TMP) as temp:
            root = Path(temp)
            resolver = _registry(root, root / "registry.json")
            resolved = resolver.resolve("phandle-successor", "wisconsin_successor_identity_workbook")
            self.assertEqual(resolved.path, (root / "successor.xlsx").resolve())
            with self.assertRaisesRegex(ConformanceError, "PROTECTED_HANDLE_UNRESOLVED"):
                resolver.resolve("phandle-unknown", "wisconsin_successor_identity_workbook")
            resolver._resources["phandle-successor"]["relative_path"] = "../escape.xlsx"
            with self.assertRaisesRegex(ConformanceError, "PROTECTED_PATH_TRAVERSAL_REJECTED"):
                resolver.resolve("phandle-successor", "wisconsin_successor_identity_workbook")

    def test_09_registry_requires_complete_2024_2025_2026_authority(self):
        with tempfile.TemporaryDirectory(dir=TEST_TMP) as temp:
            root = Path(temp)
            _registry(root, root / "registry.json")
            document = json.loads((root / "registry.json").read_text(encoding="utf-8"))
            document["successor_source_authorities"][0]["expected_forecast_vintages"] = [2024, 2026]
            bad = root / "bad-registry.json"
            write_json_exclusive(bad, document)
            with self.assertRaisesRegex(ConformanceError, "SUCCESSOR_COHORT_VINTAGE_INCOMPLETE"):
                ProtectedHandleResolver.load(bad, FICTIONAL_REPOSITORY_ROOT)

    def test_10_no_registry_means_no_discovery(self):
        with self.assertRaisesRegex(ConformanceError, "AUTHORITATIVE_ACCESS_REGISTRY_UNRESOLVED"):
            load_authorized_registry(None, ROOT)
        stream = io.StringIO()
        with patch("sys.argv", ["model10-reconcile"]), redirect_stdout(stream):
            code = cli.main()
        report = json.loads(stream.getvalue())
        self.assertEqual(code, 2)
        self.assertFalse(report["filesystem_discovery_performed"])
        self.assertEqual(report["target_values_materialized"], 0)

    def test_11_incomplete_first_ready_last_and_immutable_run(self):
        with tempfile.TemporaryDirectory(dir=TEST_TMP) as temp:
            root = Path(temp)
            run = ProtectedSuccessorRun(root, FICTIONAL_REPOSITORY_ROOT, materialization_run_id="m10run-final-order")
            self.assertFalse(protected_materialization_is_ready(run.run_dir))
            package = _package(run_id="m10run-final-order")
            writes: list[str] = []
            from sprouts_customer_geography.model10 import binding
            original = binding.write_json_exclusive

            def recording(path: Path, document: dict) -> None:
                writes.append(path.name)
                original(path, document)

            with patch.object(binding, "write_json_exclusive", side_effect=recording):
                result = run.finalize(package)
            self.assertEqual(writes[-1], "READY.json")
            self.assertTrue(protected_materialization_is_ready(run.run_dir))
            self.assertEqual(result["commitment_evidence"]["artifact_id"], "MODEL10_WISCONSIN_COHORT_IDENTITY_LINEAGE_COMMITMENT_V1")
            with self.assertRaisesRegex(ConformanceError, "MODEL10_RUN_ALREADY_EXISTS"):
                ProtectedSuccessorRun(root, FICTIONAL_REPOSITORY_ROOT, materialization_run_id="m10run-final-order")

    def test_12_corrections_require_patch_version_and_supersession(self):
        with tempfile.TemporaryDirectory(dir=TEST_TMP) as temp:
            with self.assertRaisesRegex(ConformanceError, "MODEL10_SUPERSESSION_VERSION_REQUIRED"):
                ProtectedSuccessorRun(Path(temp), FICTIONAL_REPOSITORY_ROOT, materialization_run_id="m10run-bad", supersedes="m10run-original")
            correction = ProtectedSuccessorRun(Path(temp), FICTIONAL_REPOSITORY_ROOT, materialization_run_id="m10run-correction", package_version="1.0.1", supersedes="m10run-original")
            self.assertEqual(correction.supersedes, "m10run-original")

    def test_13_disclosure_safe_result_excludes_protected_details(self):
        result = MaterializationResult("m10run-safe", Path("protected"), "a" * 64, "b" * 64, {}, 6, 4, 4, 0, 6, 1)
        report = build_disclosure_safe_result(result)
        serialized = json.dumps(report).lower()
        for forbidden in ("source_row", "seed_point", "physical_location_id", "nonce", "sha256", "workbook"):
            self.assertNotIn(forbidden, serialized)

    def test_14_protected_paths_are_not_stageable(self):
        for protected in (
            "outputs/model10-materializations/m10run-real/READY.json",
            "outputs/model10_wisconsin_cohort_identity_lineage_package.json",
        ):
            with self.assertRaisesRegex(ConformanceError, "PROTECTED_TRACKED_PATH_REJECTED"):
                assert_no_protected_tracked_paths([protected])

    def test_15_contract_reuses_model04_rules_without_new_threshold(self):
        contract = json.loads((ROOT / "config/model/model10_wisconsin_cohort_identity_lineage_contract.json").read_text(encoding="utf-8"))
        rules = contract["model04_rule_reuse"]
        self.assertEqual(rules["probable_same_max_m"], 10.0)
        self.assertEqual(rules["genuinely_new_minimum_m_exclusive"], 500.0)
        self.assertFalse(rules["new_threshold_or_tolerance_introduced"])
        self.assertFalse(rules["target_evidence_permitted"])
        market_rule = contract["successor_market_lineage_rule"]
        self.assertEqual(market_rule["physical_location_matching_partition"], "wisconsin_state")
        self.assertFalse(market_rule["source_market_label_is_physical_identity_partition"])

    def test_16_changed_market_lineage_does_not_manufacture_new_location(self):
        rows = _rows()
        rows[0]["market"] = "Fictional East Market"
        rows[1]["market"] = "Fictional East Metro"
        package = _package(rows)
        repeated = [record for record in package["records"] if record["forecast_vintage"] in {2024, 2025} and record["source_observation_lineage"]["source_seed_point_id"] in {"SUCCESSOR-MKE-24", "CHANGED-MKE-25"}]
        self.assertEqual({record["market"] for record in repeated}, {"Fictional East Market", "Fictional East Metro"})
        self.assertEqual({record["successor_physical_location_id"] for record in repeated}, {"ploc-fictional-historical-mke"})

    def test_17_repository_commitment_discloses_neither_digest_nonce_nor_observations(self):
        commitment = json.loads((ROOT / "config/model/model10_wisconsin_cohort_identity_lineage_commitment.json").read_text(encoding="utf-8"))
        self.assertEqual(commitment["artifact_id"], "MODEL10_WISCONSIN_COHORT_IDENTITY_LINEAGE_COMMITMENT_V1")
        self.assertTrue(re.fullmatch(r"[0-9a-f]{64}", commitment["commitment_sha256"]))
        self.assertFalse(commitment["protected_package_digest_disclosed"])
        self.assertFalse(commitment["nonce_disclosed"])
        self.assertFalse(commitment["observation_content_disclosed"])


if __name__ == "__main__":
    unittest.main()
