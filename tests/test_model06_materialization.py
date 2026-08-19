from __future__ import annotations

import copy
import io
import json
import unittest
import zipfile
from pathlib import Path

from sprouts_customer_geography.model06 import (
    ANCHOR_VERSION,
    COMMITMENT_DOMAIN,
    EVIDENCE_ROLES,
    IDENTITY_STATES,
    ProjectedWorkbook,
    build_commitment_evidence,
    build_identity_package,
    read_target_blind_projection,
    validate_identity_package,
    validate_preregistration,
    verify_commitment,
)
from sprouts_customer_geography.pipe01.canonical import canonical_bytes, content_digest
from sprouts_customer_geography.pipe01.errors import ConformanceError
from sprouts_customer_geography.pipe01.safeguards import assert_no_protected_tracked_paths


ROOT = Path(__file__).resolve().parents[1]


def projected(identity: str, rows: list[dict]) -> ProjectedWorkbook:
    return ProjectedWorkbook(
        source_identity=identity,
        rows=tuple(rows),
        projection_sha256=content_digest(rows),
        access_report={
            "source_identity": identity,
            "worksheet_member": "xl/worksheets/sheet1.xml",
            "sheet_logical_name": "Sheet1",
            "body_projection": "A:I",
            "body_rows_materialized": len(rows),
            "maximum_authorized_body_column": "I",
            "outside_projection_body_values_materialized": 0,
            "formula_values_materialized": 0,
            "styles_comments_charts_metadata_loaded": False,
            "target_headers_confirmed_outside_projection": ["impactedsales", "isolatedsales"],
            "max_body_column_observed_by_reference_only": 12,
        },
    )


def row(number: int, year: int, seed: str, lat: float, lon: float, market: str = "Milwaukee", address: str | None = None) -> dict:
    return {
        "source_row": number,
        "vintage": year,
        "seed_point_id": seed,
        "address": address or f"{number} Fictional Ave",
        "city": market,
        "state": "WI",
        "zip": "00000",
        "latitude": lat,
        "longitude": lon,
        "market": market,
    }


class Model06SyntheticTests(unittest.TestCase):
    def test_identity_roles_quarantine_and_observed_anchor(self):
        development = projected(
            "MODEL03A_DEVELOPMENT_REFERENCE_WORKBOOK",
            [
                row(2, 2024, "DEV-A", 10.000000, -20.000000, address="1 Fictional Ave"),
                row(3, 2024, "DEV-B", 10.020000, -20.000000, address="2 Fictional Ave"),
            ],
        )
        new = projected(
            "MODEL04_NEW_TARGET_BLIND_IDENTITY_ROLE_WORKBOOK",
            [
                row(2, 2026, "RENAMED-A", 10.000000, -20.000000, address="1 Fictional Ave"),
                row(3, 2026, "RENAMED-B", 10.020005, -20.000000, address="2 Fictional Avenue"),
                row(4, 2026, "AMB", 10.023000, -20.000000, address="4 Fictional Ave"),
                row(5, 2026, "NEW", 10.100000, -20.000000, address="5 Fictional Ave"),
            ],
        )
        package = build_identity_package([development, new])
        result = validate_identity_package(package)
        self.assertEqual(result["state"], "passed")
        by_seed = {record["source_seed_point_id"]: record for record in package["records"]}
        self.assertEqual(by_seed["RENAMED-A"]["identity_state"], "SAME_UNDERLYING_LOCATION")
        self.assertEqual(by_seed["RENAMED-B"]["identity_state"], "PROBABLE_SAME_LOCATION")
        self.assertEqual(by_seed["AMB"]["identity_state"], "AMBIGUOUS_IDENTITY")
        self.assertEqual(by_seed["AMB"]["evidence_role"], "AMBIGUOUS_QUARANTINE")
        self.assertTrue(by_seed["AMB"]["quarantined"])
        self.assertIsNone(by_seed["AMB"]["canonical_anchor"])
        self.assertEqual(by_seed["AMB"]["canonical_anchor_state"], "FAILED_CLOSED_AMBIGUOUS_IDENTITY")
        self.assertEqual(by_seed["NEW"]["identity_state"], "GENUINELY_NEW_LOCATION")
        self.assertEqual(by_seed["NEW"]["evidence_role"], "PROSPECTIVE_MILWAUKEE_HOLDOUT")
        self.assertEqual(by_seed["RENAMED-A"]["canonical_anchor"]["source_seed_point_id"], "DEV-A")
        self.assertEqual(by_seed["RENAMED-A"]["canonical_anchor"]["anchor_version"], ANCHOR_VERSION)
        self.assertEqual(set(package["identity_rules"]["states"]), IDENTITY_STATES)
        self.assertEqual(set(package["evidence_role_semantics"]), EVIDENCE_ROLES)

    def test_id_novelty_does_not_create_location_novelty_and_conflict_quarantines(self):
        development = projected(
            "MODEL03A_DEVELOPMENT_REFERENCE_WORKBOOK",
            [row(2, 2024, "OLD", 10.0, -20.0, address="1 Fictional Ave")],
        )
        new = projected(
            "MODEL04_NEW_TARGET_BLIND_IDENTITY_ROLE_WORKBOOK",
            [
                row(2, 2026, "NEW-ID", 10.0, -20.0, address="1 Fictional Ave"),
                row(3, 2026, "OLD", 11.0, -20.0, address="999 Conflict Road"),
            ],
        )
        package = build_identity_package([development, new])
        by_row = {record["source_row"]: record for record in package["records"] if record["source_workbook_identity"].startswith("MODEL04_NEW")}
        self.assertEqual(by_row[2]["identity_state"], "SAME_UNDERLYING_LOCATION")
        self.assertEqual(by_row[3]["identity_state"], "AMBIGUOUS_IDENTITY")

    def test_anchor_tie_break_is_deterministic_and_does_not_prefer_precision(self):
        rows = [
            row(3, 2024, "B", 10.0000000, -20.0000000, address="Tie Site"),
            row(2, 2024, "A", 10.0, -20.0, address="Tie Site"),
        ]
        package = build_identity_package([projected("MODEL03A_DEVELOPMENT_REFERENCE_WORKBOOK", rows)])
        anchor = package["records"][0]["canonical_anchor"]
        self.assertEqual(anchor["source_row"], 2)
        self.assertEqual(anchor["latitude"], 10.0)

    def test_madison_stage_subroles(self):
        new = projected(
            "MODEL04_NEW_TARGET_BLIND_IDENTITY_ROLE_WORKBOOK",
            [
                row(2, 2024, "MAD-A", 30.0, -40.0, market="Madison", address="1 Imaginary St"),
                row(3, 2025, "MAD-A", 30.0, -40.0, market="Madison", address="1 Imaginary St"),
                row(4, 2026, "MAD-N", 30.2, -40.0, market="Madison", address="2 Imaginary St"),
            ],
        )
        package = build_identity_package([new])
        by_seed_year = {(record["source_seed_point_id"], record["vintage_year"]): record for record in package["records"]}
        self.assertEqual(by_seed_year[("MAD-A", 2025)]["evidence_subrole"], "MADISON_REPEATED_LOCATION_EVIDENCE")
        self.assertEqual(by_seed_year[("MAD-N", 2026)]["evidence_subrole"], "MADISON_2026_GENUINELY_NEW_LOCATION")

    def test_projection_excludes_target_body_and_rejects_formula_in_a_to_i(self):
        sheet = """<?xml version='1.0' encoding='UTF-8' standalone='yes'?>
<worksheet xmlns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'><sheetData>
<row r='1'><c r='A1' t='inlineStr'><is><t>Year</t></is></c><c r='B1' t='inlineStr'><is><t>Seedpoint_ID</t></is></c><c r='C1' t='inlineStr'><is><t>Address</t></is></c><c r='D1' t='inlineStr'><is><t>City</t></is></c><c r='E1' t='inlineStr'><is><t>State</t></is></c><c r='F1' t='inlineStr'><is><t>Zip</t></is></c><c r='G1' t='inlineStr'><is><t>Lat</t></is></c><c r='H1' t='inlineStr'><is><t>Long</t></is></c><c r='I1' t='inlineStr'><is><t>MSA</t></is></c><c r='J1' t='inlineStr'><is><t>Isolated Sales</t></is></c><c r='K1' t='inlineStr'><is><t>Impacted Sales</t></is></c></row>
<row r='2'><c r='A2'><v>2026</v></c><c r='B2' t='inlineStr'><is><t>SYNTHETIC</t></is></c><c r='C2' t='inlineStr'><is><t>1 Fictional Ave</t></is></c><c r='D2' t='inlineStr'><is><t>Milwaukee</t></is></c><c r='E2' t='inlineStr'><is><t>WI</t></is></c><c r='F2' t='inlineStr'><is><t>00000</t></is></c><c r='G2'><v>10</v></c><c r='H2'><v>-20</v></c><c r='I2' t='inlineStr'><is><t>Milwaukee</t></is></c><c r='J2'><f>SUM(1,2)</f><v>SECRET_TARGET</v></c><c r='K2' t='inlineStr'><is><t>SECRET_TARGET</t></is></c></row>
</sheetData></worksheet>"""
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as archive:
            archive.writestr("xl/worksheets/sheet1.xml", sheet)
        result = read_target_blind_projection(payload.getvalue(), "SYNTHETIC")
        self.assertEqual(result.access_report["outside_projection_body_values_materialized"], 0)
        self.assertNotIn(b"SECRET_TARGET", canonical_bytes(result.rows))
        bad = sheet.replace("<c r='G2'><v>10</v></c>", "<c r='G2'><f>SUM(8,2)</f><v>10</v></c>")
        bad_payload = io.BytesIO()
        with zipfile.ZipFile(bad_payload, "w") as archive:
            archive.writestr("xl/worksheets/sheet1.xml", bad)
        with self.assertRaisesRegex(ConformanceError, "TARGET_BLIND_MATERIALIZATION_NOT_ENFORCEABLE"):
            read_target_blind_projection(bad_payload.getvalue(), "SYNTHETIC")

    def test_preregistration_hash_dependencies_and_frozen_values(self):
        document = json.loads((ROOT / "config/model/model05_prospective_validation_preregistration.json").read_text(encoding="utf-8"))
        first = validate_preregistration(document)
        second = validate_preregistration(document)
        self.assertEqual(first, second)
        self.assertEqual(first["content_sha256"], "a73b1c165e4ef26b3d0ee984af7cf8ca3ae917aeda003cb62dbb6e2ef4d28620")
        self.assertEqual(document["aggregation"]["anchor_tract_forced_inclusion"], True)
        self.assertEqual(document["aggregation"]["area_apportionment_permitted"], False)
        self.assertEqual(document["household_opportunity"]["estimate"], "B11001_001E")
        self.assertEqual(document["household_opportunity"]["moe"], "B11001_001M")
        self.assertEqual(document["validation"]["milwaukee_temporal_gate"]["pass"]["tau_b_minimum"], 0.50)
        self.assertEqual(document["freeze_prerequisites"]["prediction_artifact_created_by_model06"], False)
        data = document["dependencies"]["data"][0]
        self.assertEqual(data["content_sha256"], "31f224e87bb20c9444a061b7d8a513e45b37928158744f562d2fe8a45fe8d6e3")
        geo03 = next(item for item in document["dependencies"]["geo"] if item["artifact_id"].startswith("GEO03_"))
        self.assertEqual(geo03["operation_fingerprint_sha256"], "3c7421053e63df6e120d8aefd142399c9c53e6a1594ed23c37c644609a21bf14")
        changed = copy.deepcopy(document)
        changed["spatial_contexts"]["primary"]["metres"] = 9999
        with self.assertRaisesRegex(ConformanceError, "MODEL05_CONTENT_HASH_MISMATCH|MODEL05_PRIMARY_RADIUS_MISMATCH"):
            validate_preregistration(changed)

    def test_commitment_reuses_pipe_domain_and_verifies(self):
        package = ROOT / "config/model/model05_prospective_validation_preregistration.json"
        nonce = b"N" * 32
        evidence = build_commitment_evidence(package, nonce)
        self.assertEqual(evidence["domain"], COMMITMENT_DOMAIN)
        self.assertFalse(evidence["protected_package_digest_disclosed"])
        self.assertFalse(evidence["nonce_disclosed"])
        verify_commitment(package, nonce, evidence)
        with self.assertRaisesRegex(ConformanceError, "MODEL04_COMMITMENT_MISMATCH"):
            verify_commitment(package, b"X" * 32, evidence)

    def test_model04_protected_package_and_nonce_are_rejected_from_git(self):
        for path in (
            "results/model04_identity_role_anchor_package.json",
            "results/commitment_nonce.bin",
        ):
            with self.assertRaisesRegex(ConformanceError, "PROTECTED_TRACKED_PATH_REJECTED"):
                assert_no_protected_tracked_paths([path])


if __name__ == "__main__":
    unittest.main()
