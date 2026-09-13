"""Fictional XLSX fixtures prove MODEL-16 default-deny projection boundaries."""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from xml.sax.saxutils import escape
import zipfile

from sprouts_customer_geography.model16 import intake
from sprouts_customer_geography.model16.intake import (
    AccessAudit, EXPECTED_COUNTS, IntakeError, SOURCE_ROLES, WorkbookProjection,
    inspect_workbook, load_targets, reconcile_identity, validate_sources,
)


MI = "MI_SEED_FORECASTS_2024_2026_V1"
WI = "WI_SEED_FORECASTS_2024_2026_V1"
PURSUED = "MI_WI_PURSUED_SITES_2025_ISOLATED_V1"
HEADERS = ["Year", "Seedpoint_ID", "Address", "City2", "State", "Zip", "Lat", "Long", "MSA", "Isolated Sales", "Impacted Sales", "Coordinates"]
DENIED = "SYNTHETIC_POISON_DENIED_BODY"


def write_workbook(path: Path, rows: list[list], *, shared: bool = False, extra_sheet: bool = False,
                   headers: list[str] | None = None, formula_cell: str | None = None) -> dict[str, int]:
    strings, shared_by_value, indices_by_cell = [], {}, {}
    def cell(column: str, row: int, value) -> str:
        address = f"{column}{row}"
        formula = "<f>UNAVAILABLE_SYNTHETIC_FORMULA()</f>" if address == formula_cell else ""
        if shared:
            value = str(value)
            if value not in shared_by_value:
                shared_by_value[value] = len(strings)
                strings.append(value)
            index = shared_by_value[value]
            indices_by_cell[address] = index
            return f'<c r="{address}" t="s">{formula}<v>{index}</v></c>'
        if isinstance(value, (int, float)):
            return f'<c r="{address}">{formula}<v>{value}</v></c>'
        return f'<c r="{address}" t="inlineStr">{formula}<is><t>{escape(str(value))}</t></is></c>'
    all_rows = [headers or HEADERS, *rows]
    xml_rows = [f'<row r="{r}">' + "".join(cell(chr(65 + c), r, value) for c, value in enumerate(values)) + "</row>" for r, values in enumerate(all_rows, start=1)]
    workbook = '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Synthetic Evidence" sheetId="1" r:id="rId1"/>'
    if extra_sheet:
        workbook += '<sheet name="Extra Synthetic" sheetId="2" r:id="rId2"/>'
    workbook += "</sheets></workbook>"
    relationships = '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>'
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", relationships)
        archive.writestr("xl/worksheets/sheet1.xml", '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>' + "".join(xml_rows) + "</sheetData></worksheet>")
        if shared:
            archive.writestr("xl/sharedStrings.xml", '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">' + "".join("<si><t>" + escape(value) + "</t></si>" for value in strings) + "</sst>")
    return indices_by_cell


def source_row(*, year=2024, label="SYNTHETIC_SEED_A", state="MI", lat=44.0, lon=-85.0, isolated=100000, address="100 Fictional Avenue") -> list:
    return [year, label, address, "Fictional City", state, "00000", lat, lon, "Fictional MSA", isolated, DENIED + "_IMPACTED", DENIED + "_COORDINATES"]


def projection_from_rows(rows: list[dict], source_id: str) -> WorkbookProjection:
    return WorkbookProjection(tuple(rows), {}, {}, "SYNTHETIC", "SYNTHETIC", "SYNTHETIC", SOURCE_ROLES[source_id][0], source_id, AccessAudit())


def identity_row(*, row=2, year=2024, state="MI", label="SYNTHETIC_A", lat=44.0, lon=-85.0, pursued=False, address="") -> dict:
    return {"source_row": row, "source_id": None, "year": year, "state": state,
            "seedpoint_id": None if pursued else label, "source_site_name": label if pursued else None,
            "latitude": lat, "longitude": lon, "coordinate_key": (str(lat), str(lon)),
            "address": address, "city": "Fictional City", "postal_code": "00000", "msa": "Fictional MSA",
            "evidence_class": "PURSUED_SITE" if pursued else "SEED_POINT"}


class Model16IntakeTests(unittest.TestCase):
    def test_identity_projection_never_decodes_sales_or_redundant_coordinates(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "synthetic.xlsx"
            write_workbook(path, [source_row(isolated=DENIED + "_ISOLATED")], formula_cell="K2")
            original = intake._decode
            def guarded(cell, strings, audit, purpose):
                if cell.row > 1:
                    self.assertNotIn(cell.column, {"J", "K", "L"})
                return original(cell, strings, audit, purpose)
            with patch.object(intake, "_decode", guarded):
                projection = inspect_workbook(path, "SEED_POINT", source_id=MI)
            row = projection.rows[0]
            self.assertEqual(row["city"], "Fictional City")
            self.assertEqual(row["seedpoint_id"], "SYNTHETIC_SEED_A")
            self.assertNotIn(DENIED, json.dumps(projection.rows))
            self.assertNotIn("isolated_sales", row)
            self.assertNotIn("impacted_sales", row)
            self.assertEqual(projection.audit.isolated_payload_decodes, 0)
            self.assertEqual(projection.audit.impacted_payload_decodes, 0)

    def test_shared_string_requests_exclude_every_denied_body(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "synthetic.xlsx"
            indices = write_workbook(path, [source_row(isolated=DENIED + "_ISOLATED")], shared=True)
            requested = []
            original = intake._load_shared_strings
            def observe(archive, wanted):
                requested.extend(wanted)
                return original(archive, wanted)
            with patch.object(intake, "_load_shared_strings", observe):
                inspect_workbook(path, "SEED_POINT", source_id=MI)
            for cell in ("J2", "K2", "L2"):
                self.assertNotIn(indices[cell], requested)

    def test_exact_development_mask_leaves_2026_poison_and_impacted_sealed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "synthetic.xlsx"
            indices = write_workbook(path, [source_row(year=2024, isolated=120000), source_row(year=2025, isolated=125000), source_row(year=2026, isolated=DENIED + "_2026")], shared=True)
            projection = inspect_workbook(path, "SEED_POINT", source_id=MI)
            original = intake._load_shared_strings
            requested = []
            def observe(archive, wanted):
                requested.extend(wanted)
                return original(archive, wanted)
            with patch.object(intake, "_load_shared_strings", observe):
                values, audit = load_targets(path, projection, source_rows={2, 3}, role="development")
            self.assertEqual(values, {2: 120000.0, 3: 125000.0})
            self.assertEqual(audit.isolated_payload_decodes, 2)
            self.assertEqual(audit.impacted_payload_decodes, 0)
            for cell in ("J4", "K2", "L2"):
                self.assertNotIn(indices[cell], requested)

    def test_role_checks_and_freeze_precede_target_parsing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "synthetic.xlsx"
            write_workbook(path, [source_row(year=2026)])
            projection = inspect_workbook(path, "SEED_POINT", source_id=MI)
            with patch.object(intake, "_read_sheet") as read:
                with self.assertRaisesRegex(IntakeError, "HOLDOUT_ROW_IN_DEVELOPMENT"):
                    load_targets(path, projection, source_rows={2}, role="development")
                with self.assertRaisesRegex(IntakeError, "HOLDOUT_FREEZE_REQUIRED"):
                    load_targets(path, projection, source_rows={2}, role="temporal_2026")
                read.assert_not_called()
            values, audit = load_targets(path, projection, source_rows={2}, role="temporal_2026", holdout_freeze_id="SYNTHETIC_FROZEN")
            self.assertEqual(values, {2: 100000.0})
            self.assertEqual(audit.isolated_payload_decodes, 1)

    def test_missing_or_outside_row_mask_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "synthetic.xlsx"
            write_workbook(path, [source_row()])
            projection = inspect_workbook(path, "SEED_POINT", source_id=MI)
            for mask in (set(), [2], {True}, {900}):
                with self.assertRaises(IntakeError):
                    load_targets(path, projection, source_rows=mask, role="development")

    def test_source_change_rejected_before_target_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "synthetic.xlsx"
            write_workbook(path, [source_row()])
            projection = inspect_workbook(path, "SEED_POINT", source_id=MI)
            write_workbook(path, [source_row(isolated=101000)])
            with self.assertRaisesRegex(IntakeError, "SOURCE_CHANGED_SINCE_PROJECTION"):
                load_targets(path, projection, source_rows={2}, role="development")

    def test_formula_target_and_nonpositive_targets_fail_without_value_disclosure(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "synthetic.xlsx"
            for value, formula in ((0, None), ("nan", None), (DENIED, None), (100000, "J2")):
                write_workbook(path, [source_row(isolated=value)], formula_cell=formula)
                projection = inspect_workbook(path, "SEED_POINT", source_id=MI)
                with self.assertRaises(IntakeError) as caught:
                    load_targets(path, projection, source_rows={2}, role="development")
                self.assertNotIn(str(value), str(caught.exception))

    def test_exact_one_sheet_twelve_headers_and_complete_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "synthetic.xlsx"
            write_workbook(path, [source_row()], extra_sheet=True)
            with self.assertRaisesRegex(IntakeError, "WORKSHEET_COUNT_MISMATCH"):
                inspect_workbook(path, "SEED_POINT")
            write_workbook(path, [source_row()], headers=[*HEADERS, "Unapproved Field"])
            with self.assertRaisesRegex(IntakeError, "TWELVE_COLUMN"):
                inspect_workbook(path, "SEED_POINT")
            changed_headers = HEADERS.copy()
            changed_headers[8] = "Unknown Geography"
            write_workbook(path, [source_row()], headers=changed_headers)
            with self.assertRaisesRegex(IntakeError, "HEADER_SCHEMA"):
                inspect_workbook(path, "SEED_POINT")
            row = source_row()
            row[8] = ""
            write_workbook(path, [row])
            with self.assertRaisesRegex(IntakeError, "REQUIRED_IDENTITY"):
                inspect_workbook(path, "SEED_POINT")

    def test_pursued_label_never_becomes_seed_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "synthetic.xlsx"
            headers = HEADERS.copy()
            headers[3] = "City"
            write_workbook(path, [source_row(year=2025, label="Fictional Shopping Centre")], headers=headers)
            projection = inspect_workbook(path, "PURSUED_SITE", source_id=PURSUED)
            self.assertIsNone(projection.rows[0]["seedpoint_id"])
            self.assertEqual(projection.rows[0]["source_site_name"], "Fictional Shopping Centre")
            with self.assertRaisesRegex(IntakeError, "HOLDOUT_ROW_IN_DEVELOPMENT"):
                load_targets(path, projection, source_rows={2}, role="development")

    def test_exact_expected_bounded_source_counts(self):
        sources = {}
        for source_id, expected in EXPECTED_COUNTS.items():
            rows = []
            for (state, year), count in expected.items():
                rows.extend(identity_row(row=len(rows) + i + 2, state=state, year=year, label=f"SYNTHETIC_{state}_{year}_{i}", pursued=source_id == PURSUED) for i in range(count))
            sources[source_id] = projection_from_rows(rows, source_id)
        report = validate_sources(sources)
        self.assertEqual(report["observations"], 240)
        broken = dict(sources)
        broken[MI] = replace(sources[MI], rows=sources[MI].rows[:-1])
        with self.assertRaisesRegex(IntakeError, "SOURCE_COUNTS_MISMATCH"):
            validate_sources(broken)

    def test_different_years_and_seed_aliases_at_exact_location_are_retained(self):
        rows = [identity_row(year=2024), identity_row(row=3, year=2025), identity_row(row=4, year=2026, label="SYNTHETIC_ALIAS")]
        result = reconcile_identity({MI: projection_from_rows(rows, MI)}, require_expected_shape=False)
        self.assertTrue(result.ready)
        self.assertEqual(len(result.rows), 3)
        self.assertEqual(len(result.groups), 1)
        self.assertEqual(len({row["observation_id"] for row in result.rows}), 3)
        self.assertTrue(all(row["observation_id"].startswith("MODEL16_OBS_") for row in result.rows))

    def test_same_year_id_or_exact_coordinate_duplicates_fail_closed(self):
        variants = ([identity_row(), identity_row(row=3, lat=44.01)],
                    [identity_row(), identity_row(row=3, label="SYNTHETIC_DIFFERENT")])
        for rows in variants:
            with self.assertRaisesRegex(IntakeError, "DUPLICATE"):
                reconcile_identity({MI: projection_from_rows(rows, MI)}, require_expected_shape=False)

    def test_nearby_same_year_seeds_are_not_merged_or_removed(self):
        rows = [identity_row(), identity_row(row=3, lat=44.00001, label="SYNTHETIC_NEARBY")]
        result = reconcile_identity({MI: projection_from_rows(rows, MI)}, require_expected_shape=False)
        self.assertTrue(result.ready)
        self.assertEqual(len(result.rows), 2)
        self.assertEqual(len(result.groups), 2)

    def test_same_seed_id_with_coordinate_change_is_unresolved(self):
        rows = [identity_row(), identity_row(row=3, year=2025, lat=44.00001)]
        result = reconcile_identity({MI: projection_from_rows(rows, MI)}, require_expected_shape=False)
        self.assertFalse(result.ready)
        self.assertEqual(result.unresolved[0]["reason"], "SEED_ID_COORDINATE_CONFLICT")
        self.assertTrue(all(row["identity_status"] == "UNRESOLVED" for row in result.rows))

    def test_exact_cross_source_match_preserves_evidence_classes(self):
        sources = {MI: projection_from_rows([identity_row()], MI), PURSUED: projection_from_rows([identity_row(year=2025, label="Fictional Site", pursued=True)], PURSUED)}
        result = reconcile_identity(sources, require_expected_shape=False)
        self.assertTrue(result.ready)
        self.assertEqual(len(result.groups), 1)
        self.assertEqual(len(result.matches), 1)
        self.assertEqual({row["evidence_class"] for row in result.rows}, {"SEED_POINT", "PURSUED_SITE"})
        self.assertEqual(result.aggregates["matched_development_pursued_observations"], 1)

    def test_2026_only_seed_match_is_never_independent(self):
        sources = {MI: projection_from_rows([identity_row(year=2026)], MI), PURSUED: projection_from_rows([identity_row(year=2025, label="Fictional Site", pursued=True)], PURSUED)}
        result = reconcile_identity(sources, require_expected_shape=False)
        site = next(row for row in result.rows if row["evidence_class"] == "PURSUED_SITE")
        self.assertTrue(site["matched_seedpoint_location"])
        self.assertFalse(site["matched_development_location"])
        self.assertEqual(site["independence_status"], "MATCHED_SEEDPOINT")

    def test_near_cross_source_and_far_address_matches_stay_unresolved(self):
        for latitude, address in ((44.00001, "Other Fictional Street"), (45.0, "100 Fictional Ave.")):
            sources = {MI: projection_from_rows([identity_row(address="100 Fictional Avenue")], MI), PURSUED: projection_from_rows([identity_row(year=2025, label="Fictional Site", lat=latitude, pursued=True, address=address)], PURSUED)}
            result = reconcile_identity(sources, require_expected_shape=False)
            self.assertFalse(result.ready)
            self.assertEqual(len(result.groups), 2)
            self.assertEqual(len(result.matches), 0)
            self.assertEqual(result.aggregates["unresolved_observations"], 2)

    def test_pursued_duplicate_coordinates_and_normalized_names_fail(self):
        for site in (identity_row(row=3, year=2025, label="Other Name", pursued=True),
                     identity_row(row=3, year=2025, label="fictional-site", lat=45.0, pursued=True)):
            first = identity_row(year=2025, label="Fictional Site", pursued=True)
            with self.assertRaisesRegex(IntakeError, "PURSUED_.*DUPLICATE"):
                reconcile_identity({PURSUED: projection_from_rows([first, site], PURSUED)}, require_expected_shape=False)

    def test_identity_never_accepts_target_values(self):
        row = identity_row()
        row["isolated_sales"] = 100000
        with self.assertRaisesRegex(IntakeError, "IDENTITY_TARGET_FIELD_PRESENT"):
            reconcile_identity({MI: projection_from_rows([row], MI)}, require_expected_shape=False)


if __name__ == "__main__":
    unittest.main()
