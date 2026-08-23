from __future__ import annotations

import copy
import inspect
import io
import json
import sys
import tempfile
import unittest
import zipfile
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from sprouts_customer_geography.pipe01.canonical import write_json_exclusive
from sprouts_customer_geography.pipe01.errors import ConformanceError
from sprouts_customer_geography.pipe01.orchestration import Model04Binding
from sprouts_customer_geography.pipe01.safeguards import assert_no_protected_tracked_paths
from sprouts_customer_geography.pipe03 import binding, cli
from sprouts_customer_geography.pipe03.binding import (
    BINDING_PACKAGE_ID,
    BINDING_PACKAGE_VERSION,
    BindingResult,
    ProtectedDevelopmentBindingRun,
    build_disclosure_safe_result,
    derive_eligible_wisconsin_cohort,
    execute_protected_binding,
    protected_binding_is_ready,
)
from sprouts_customer_geography.pipe03.resolver import (
    ProtectedHandleResolver,
    load_authorized_registry,
)
from sprouts_customer_geography.pipe03.xlsx_projection import (
    DevelopmentTargetAccessAudit,
    WisconsinDevelopmentProjectionPolicy,
    project_authorized_isolated_sales,
)


ROOT = Path(__file__).resolve().parents[1]


def _record(
    *,
    row: int,
    lineage: str,
    vintage: int,
    market: str,
    location: str,
    workbook: str = "FICTIONAL-WISCONSIN-WORKBOOK",
    sheet: str = "Targets",
    identity_state: str = "GENUINELY_NEW_LOCATION",
    quarantined: bool = False,
    role: str | None = None,
    target_view_state: str = "SEALED",
) -> dict:
    if role is None:
        role = (
            "AMBIGUOUS_QUARANTINE"
            if quarantined
            else "PROSPECTIVE_MILWAUKEE_HOLDOUT"
            if market.lower() == "milwaukee"
            else "EXTERNAL_MADISON_HOLDOUT"
        )
    return {
        "physical_location_id": location,
        "source_workbook_identity": workbook,
        "source_sheet": sheet,
        "source_row": row,
        "source_seed_point_id": lineage,
        "vintage_year": vintage,
        "market": market,
        "identity_state": identity_state,
        "quarantined": quarantined,
        "evidence_role": role,
        "target_view_state": target_view_state,
    }


def _fictional_model04_package() -> dict:
    return {
        "records": [
            _record(
                row=2,
                lineage="FICTIONAL-MKE-2025",
                vintage=2025,
                market="milwaukee",
                location="FICTIONAL-LOCATION-MKE",
                role="DEVELOPMENT_REFERENCE",
                target_view_state="DEVELOPMENT_CONSUMED",
            ),
            _record(
                row=3,
                lineage="FICTIONAL-MSN-2026",
                vintage=2026,
                market="madison",
                location="FICTIONAL-LOCATION-MSN",
            ),
            _record(
                row=4,
                lineage="FICTIONAL-AMBIGUOUS",
                vintage=2026,
                market="milwaukee",
                location="FICTIONAL-LOCATION-AMBIGUOUS",
                identity_state="AMBIGUOUS_IDENTITY",
                quarantined=True,
            ),
        ]
    }


def _model_binding(package: dict | None = None) -> Model04Binding:
    return Model04Binding(package or _fictional_model04_package(), "fictional", {})


def _inline_cell(column: str, row: int, value: str) -> str:
    return (
        f'<c r="{column}{row}" t="inlineStr"><is><t>{value}</t></is></c>'
    )


def _numeric_cell(column: str, row: int, value: str) -> str:
    return f'<c r="{column}{row}"><v>{value}</v></c>'


def _write_xlsx(
    path: Path,
    *,
    isolated_values: tuple[str, str] = ("101", "202.50"),
    second_lineage: str = "FICTIONAL-MSN-2026",
) -> None:
    rows = [
        "<row r=\"1\">"
        + _inline_cell("A", 1, "Seed Point ID")
        + _inline_cell("B", 1, "Forecast Vintage")
        + _inline_cell("C", 1, "Isolated Sales")
        + _inline_cell("D", 1, "Impacted Sales")
        + "</row>",
        "<row r=\"2\">"
        + _inline_cell("A", 2, "FICTIONAL-MKE-2025")
        + _inline_cell("B", 2, "Forecast 2025")
        + _numeric_cell("C", 2, isolated_values[0])
        + _inline_cell("D", 2, "FORBIDDEN-IMPACTED-SENTINEL")
        + "</row>",
        "<row r=\"3\">"
        + _inline_cell("A", 3, second_lineage)
        + _inline_cell("B", 3, "Forecast 2026")
        + _numeric_cell("C", 3, isolated_values[1])
        + _inline_cell("D", 3, "FORBIDDEN-IMPACTED-SENTINEL-2")
        + "</row>",
        "<row r=\"5\">"
        + _inline_cell("A", 5, "FICTIONAL-DETROIT")
        + _inline_cell("B", 5, "Forecast 2026")
        + _inline_cell("C", 5, "FORBIDDEN-NON-WISCONSIN-TARGET")
        + _inline_cell("D", 5, "FORBIDDEN-NON-WISCONSIN-IMPACTED")
        + "</row>",
    ]
    worksheet = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData>{''.join(rows)}</sheetData></worksheet>"
    )
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Targets" sheetId="1" r:id="rId1"/></sheets></workbook>'
    )
    relationships = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/></Relationships>'
    )
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", relationships)
        archive.writestr("xl/worksheets/sheet1.xml", worksheet)


def _projection_document(
    handle: str = "phandle-target",
    workbook_identity: str = "FICTIONAL-WISCONSIN-WORKBOOK",
) -> dict:
    return {
        "projection_id": "MODEL09_MINIMUM_WISCONSIN_DEVELOPMENT_TARGET_PROJECTION_V1",
        "version": "1.0.0",
        "workbook_handle": handle,
        "source_workbook_identity": workbook_identity,
        "default_deny": True,
        "allowed_state": "wisconsin",
        "allowed_markets": ["milwaukee", "madison"],
        "permitted_target_field": "Isolated Sales",
        "denied_target_field": "Impacted Sales",
        "model04_lineage_field": "source_seed_point_id",
        "forecast_vintage_field": "vintage_year",
        "source_row_field": "source_row",
        "sheet_name": "Targets",
        "header_row": 1,
        "columns": {
            "lineage_key": "A",
            "forecast_vintage": "B",
            "isolated_sales": "C",
        },
        "headers": {
            "lineage_key": "Seed Point ID",
            "forecast_vintage": "Forecast Vintage",
            "isolated_sales": "Isolated Sales",
        },
    }


def _policy() -> WisconsinDevelopmentProjectionPolicy:
    return WisconsinDevelopmentProjectionPolicy(
        _projection_document(),
        "phandle-target",
        "FICTIONAL-WISCONSIN-WORKBOOK",
    )


def _eligible_rows() -> list[dict]:
    cohort, _, _ = derive_eligible_wisconsin_cohort(_model_binding())
    return cohort


def _registry(root: Path, registry_path: Path) -> ProtectedHandleResolver:
    (root / "output").mkdir(exist_ok=True)
    (root / "model04.json").write_text("{}", encoding="utf-8")
    (root / "model04-nonce.bin").write_bytes(b"F" * 32)
    if not (root / "targets.xlsx").exists():
        _write_xlsx(root / "targets.xlsx")
    document = {
        "registry_id": "PIPE03_PROTECTED_HANDLE_REGISTRY_V1",
        "version": "1.0.0",
        "protected_roots": {"proot-fixture": str(root.resolve())},
        "resources": {
            "phandle-model04": {
                "root_handle": "proot-fixture",
                "relative_path": "model04.json",
                "kind": "model04_package",
            },
            "phandle-model04-verification": {
                "root_handle": "proot-fixture",
                "relative_path": "model04-nonce.bin",
                "kind": "model04_verification_material",
            },
            "phandle-target": {
                "root_handle": "proot-fixture",
                "relative_path": "targets.xlsx",
                "kind": "wisconsin_development_target_workbook",
            },
            "phandle-output": {
                "root_handle": "proot-fixture",
                "relative_path": "output",
                "kind": "pipe03_output_root",
            },
        },
        "binding_request": {
            "model04_package_handle": "phandle-model04",
            "model04_verification_material_handle": "phandle-model04-verification",
            "wisconsin_development_target_workbook_handles": ["phandle-target"],
            "binding_output_root_handle": "phandle-output",
        },
        "target_source_authorities": [
            {
                "authority_id": "FICTIONAL-WISCONSIN-TARGET-AUTHORITY",
                "provenance_class": "fictional_conformance",
                "source_workbook_identity": "FICTIONAL-WISCONSIN-WORKBOOK",
                "workbook_handle": "phandle-target",
                "byte_hash_permitted": False,
                "projection": _projection_document(),
            }
        ],
    }
    write_json_exclusive(registry_path, document)
    return ProtectedHandleResolver.load(registry_path, ROOT)


def _semantic_package(run_id: str = "p3bind-fictional") -> dict:
    cohort = _eligible_rows()[:1]
    projection_rows = [
        {
            "physical_location_id": cohort[0]["physical_location_id"],
            "lineage_key": cohort[0]["lineage_key"],
            "forecast_vintage": cohort[0]["forecast_vintage"],
            "isolated_sales": "101",
        }
    ]
    return {
        "$schema": "pipe03-wisconsin-development-target-access-binding-v1",
        "package_id": BINDING_PACKAGE_ID,
        "version": BINDING_PACKAGE_VERSION,
        "binding_run_id": run_id,
        "state": "ready",
        "model04_authority": {
            "package_id": "MODEL04_VALIDATION_IDENTITY_ROLE_ANCHOR_PACKAGE_V1",
            "package_version": "1.0.0",
            "commitment_sha256": binding.EXPECTED_MODEL04_COMMITMENT,
            "commitment_reconciled": True,
        },
        "model05_authority": {
            "preregistration_id": "MODEL05_PROSPECTIVE_VALIDATION_PREREGISTRATION_V1",
            "version": "1.0.0",
            "content_sha256": binding.EXPECTED_MODEL05_SHA256,
        },
        "model08_authority": {
            "strategy_document": binding.MODEL08_DOCUMENT,
            "wisconsin_first": True,
            "target_blind_identity": True,
        },
        "target_source_authorities": [
            {
                "authority_id": "FICTIONAL-WISCONSIN-TARGET-AUTHORITY",
                "provenance_class": "fictional_conformance",
                "source_workbook_identity": "FICTIONAL-WISCONSIN-WORKBOOK",
                "workbook_handle": "phandle-target",
                "whole_workbook_hash_computed": False,
            }
        ],
        "eligible_wisconsin_cohort": cohort,
        "minimum_target_projection": {
            "projection_id": WisconsinDevelopmentProjectionPolicy.PROJECTION_ID,
            "version": WisconsinDevelopmentProjectionPolicy.VERSION,
            "default_deny": True,
            "allowed_fields": sorted(WisconsinDevelopmentProjectionPolicy.ALLOWED_FIELDS),
            "denied_scope": ["Impacted Sales", "Michigan", "Detroit"],
            "rows": projection_rows,
            "target_access_audit": {
                "authorized_row_count": 1,
                "isolated_sales_materialized": True,
                "impacted_sales_decode_calls": 0,
                "non_wisconsin_target_decode_calls": 0,
                "unrelated_target_values_materialized": False,
            },
        },
        "consumption_semantics": {
            "binding_marks_development_consumed": False,
            "prior_evidence_metadata_preserved": True,
            "analytical_influence_triggers_model09_consumption": True,
        },
        "protected_handle_registry_identity": "fictional-registry",
        "finalization": {
            "cohort_established_before_target_projection": True,
            "mandatory_reconciliations_passed": True,
            "ready_marker_written_last": True,
        },
        "supersedes": None,
        "supersession_policy": "fictional immutable correction",
    }


class Pipe03BindingTests(unittest.TestCase):
    def test_01_accepted_wisconsin_cohort_and_historical_metadata(self):
        cohort, quarantined, non_wisconsin = derive_eligible_wisconsin_cohort(_model_binding())
        self.assertEqual({row["market"] for row in cohort}, {"milwaukee", "madison"})
        self.assertEqual(quarantined, 1)
        self.assertEqual(non_wisconsin, 0)
        self.assertEqual(cohort[0]["target_view_state"], "DEVELOPMENT_CONSUMED")
        self.assertEqual(cohort[1]["target_view_state"], "SEALED")

    def test_02_ambiguous_identity_remains_quarantined(self):
        cohort, quarantined, _ = derive_eligible_wisconsin_cohort(_model_binding())
        self.assertEqual(quarantined, 1)
        self.assertNotIn("FICTIONAL-AMBIGUOUS", {row["lineage_key"] for row in cohort})
        with self.assertRaisesRegex(ConformanceError, "TARGET_QUARANTINE_DENIED"):
            _policy().authorize(
                field="isolated_sales",
                market="milwaukee",
                quarantined=True,
                row_allowed=True,
            )

    def test_03_non_wisconsin_records_are_denied(self):
        package = _fictional_model04_package()
        package["records"].append(
            _record(
                row=5,
                lineage="FICTIONAL-DETROIT",
                vintage=2026,
                market="detroit",
                location="FICTIONAL-DETROIT-LOCATION",
            )
        )
        cohort, _, denied = derive_eligible_wisconsin_cohort(_model_binding(package))
        self.assertEqual(denied, 1)
        self.assertNotIn("FICTIONAL-DETROIT", {row["lineage_key"] for row in cohort})
        with self.assertRaisesRegex(ConformanceError, "TARGET_MARKET_DENIED"):
            _policy().authorize(
                field="isolated_sales",
                market="detroit",
                quarantined=False,
                row_allowed=True,
            )

    def test_04_target_content_cannot_change_cohort_or_physical_identity(self):
        before = derive_eligible_wisconsin_cohort(_model_binding())[0]
        after = derive_eligible_wisconsin_cohort(_model_binding(copy.deepcopy(_fictional_model04_package())))[0]
        self.assertEqual(before, after)
        self.assertEqual(
            [row["physical_location_id"] for row in before],
            [row["physical_location_id"] for row in after],
        )

    def test_05_repeated_vintages_preserve_physical_location_group(self):
        package = _fictional_model04_package()
        package["records"].insert(
            1,
            _record(
                row=6,
                lineage="FICTIONAL-MKE-2026",
                vintage=2026,
                market="milwaukee",
                location="FICTIONAL-LOCATION-MKE",
                identity_state="SAME_UNDERLYING_LOCATION",
                role="TEMPORAL_VALIDATION",
            ),
        )
        cohort, _, _ = derive_eligible_wisconsin_cohort(_model_binding(package))
        mke = [row for row in cohort if row["market"] == "milwaukee"]
        self.assertEqual(len(mke), 2)
        self.assertEqual({row["physical_location_id"] for row in mke}, {"FICTIONAL-LOCATION-MKE"})

    def test_06_duplicate_or_incomplete_lineage_fails_closed(self):
        package = _fictional_model04_package()
        package["records"][1]["source_seed_point_id"] = "FICTIONAL-MKE-2025"
        package["records"][1]["vintage_year"] = 2025
        with self.assertRaisesRegex(ConformanceError, "WISCONSIN_OBSERVATION_DUPLICATE"):
            derive_eligible_wisconsin_cohort(_model_binding(package))
        package = _fictional_model04_package()
        package["records"][0]["physical_location_id"] = ""
        with self.assertRaisesRegex(ConformanceError, "WISCONSIN_LINEAGE_INCOMPLETE"):
            derive_eligible_wisconsin_cohort(_model_binding(package))

    def test_07_isolated_sales_values_are_materialized_only_for_authorized_rows(self):
        with tempfile.TemporaryDirectory() as temp:
            workbook = Path(temp) / "fictional.xlsx"
            _write_xlsx(workbook)
            rows, audit = project_authorized_isolated_sales(workbook, _policy(), _eligible_rows())
        self.assertEqual([row["isolated_sales"] for row in rows], ["101", "202.5"])
        self.assertEqual(audit.authorized_isolated_sales_decode_calls, 2)

    def test_08_impacted_sales_and_non_wisconsin_payloads_are_never_retained(self):
        with tempfile.TemporaryDirectory() as temp:
            workbook = Path(temp) / "fictional.xlsx"
            _write_xlsx(workbook)
            rows, audit = project_authorized_isolated_sales(workbook, _policy(), _eligible_rows())
        serialized = json.dumps(rows)
        self.assertNotIn("FORBIDDEN-IMPACTED", serialized)
        self.assertNotIn("FORBIDDEN-NON-WISCONSIN", serialized)
        self.assertEqual(audit.impacted_sales_decode_calls, 0)
        self.assertEqual(audit.non_wisconsin_target_decode_calls, 0)

    def test_09_impacted_sales_field_is_default_denied(self):
        with self.assertRaisesRegex(ConformanceError, "TARGET_FIELD_DENIED"):
            _policy().authorize(
                field="impacted_sales",
                market="milwaukee",
                quarantined=False,
                row_allowed=True,
            )

    def test_10_target_payload_mutation_does_not_change_identity_or_membership(self):
        with tempfile.TemporaryDirectory() as temp:
            first = Path(temp) / "first.xlsx"
            second = Path(temp) / "second.xlsx"
            _write_xlsx(first, isolated_values=("1", "2"))
            _write_xlsx(second, isolated_values=("999999", "888888"))
            one, _ = project_authorized_isolated_sales(first, _policy(), _eligible_rows())
            two, _ = project_authorized_isolated_sales(second, _policy(), _eligible_rows())
        identity = lambda rows: [
            (row["physical_location_id"], row["lineage_key"], row["forecast_vintage"])
            for row in rows
        ]
        self.assertEqual(identity(one), identity(two))
        self.assertNotEqual(
            [row["isolated_sales"] for row in one],
            [row["isolated_sales"] for row in two],
        )

    def test_11_unresolved_lineage_and_unsafe_target_storage_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            workbook = Path(temp) / "bad-lineage.xlsx"
            _write_xlsx(workbook, second_lineage="FICTIONAL-UNRESOLVED")
            with self.assertRaisesRegex(ConformanceError, "TARGET_LINEAGE_PAIR_UNRESOLVED"):
                project_authorized_isolated_sales(workbook, _policy(), _eligible_rows())

    def test_12_explicit_handle_only_resolution_and_containment(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            resolver = _registry(root, root / "registry.json")
            resolved = resolver.resolve(
                "phandle-target",
                "wisconsin_development_target_workbook",
            )
            self.assertEqual(resolved.path, (root / "targets.xlsx").resolve())
            with self.assertRaisesRegex(ConformanceError, "PROTECTED_HANDLE_UNRESOLVED"):
                resolver.resolve("phandle-unknown", "wisconsin_development_target_workbook")

    def test_13_no_registry_means_no_discovery(self):
        with self.assertRaisesRegex(ConformanceError, "AUTHORITATIVE_ACCESS_REGISTRY_UNRESOLVED"):
            load_authorized_registry(None, ROOT)
        source = inspect.getsource(ProtectedHandleResolver)
        for forbidden in ("glob(", "rglob(", "iterdir(", "os.walk", "filename search"):
            self.assertNotIn(forbidden, source.lower())

    def test_14_path_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            resolver = _registry(root, root / "registry.json")
            resolver._resources["phandle-target"]["relative_path"] = "../escape.xlsx"
            with self.assertRaisesRegex(ConformanceError, "PROTECTED_PATH_TRAVERSAL_REJECTED"):
                resolver.resolve("phandle-target", "wisconsin_development_target_workbook")

    def test_15_source_authorities_and_request_handles_must_match_exactly(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _registry(root, root / "registry.json")
            document = json.loads((root / "registry.json").read_text(encoding="utf-8"))
            document["binding_request"]["wisconsin_development_target_workbook_handles"] = []
            bad = root / "bad-registry.json"
            write_json_exclusive(bad, document)
            with self.assertRaisesRegex(ConformanceError, "TARGET_SOURCE_HANDLE_MISMATCH"):
                ProtectedHandleResolver.load(bad, ROOT)

    def test_16_interruption_remains_incomplete(self):
        with tempfile.TemporaryDirectory() as temp:
            run = ProtectedDevelopmentBindingRun(
                Path(temp), ROOT, binding_run_id="p3bind-interrupted"
            )
            self.assertFalse(protected_binding_is_ready(run.run_dir))
            state = json.loads((run.run_dir / "binding_state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["state"], "incomplete")

    def test_17_ready_marker_is_written_last(self):
        with tempfile.TemporaryDirectory() as temp:
            run = ProtectedDevelopmentBindingRun(
                Path(temp), ROOT, binding_run_id="p3bind-final-order"
            )
            writes: list[str] = []
            original = binding.write_json_exclusive

            def recording(path: Path, document: dict) -> None:
                writes.append(path.name)
                original(path, document)

            with patch.object(binding, "write_json_exclusive", side_effect=recording):
                run.finalize(_semantic_package("p3bind-final-order"))
            self.assertEqual(writes[-1], "READY.json")
            self.assertTrue(protected_binding_is_ready(run.run_dir))

    def test_18_run_identity_is_immutable(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run = ProtectedDevelopmentBindingRun(
                root, ROOT, binding_run_id="p3bind-immutable"
            )
            run.finalize(_semantic_package("p3bind-immutable"))
            with self.assertRaisesRegex(ConformanceError, "BINDING_ALREADY_EXISTS"):
                ProtectedDevelopmentBindingRun(
                    root, ROOT, binding_run_id="p3bind-immutable"
                )

    def test_19_corrections_require_new_version_and_supersession(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ConformanceError, "BINDING_SUPERSESSION_VERSION_REQUIRED"):
                ProtectedDevelopmentBindingRun(
                    Path(temp),
                    ROOT,
                    binding_run_id="p3bind-correction-bad",
                    supersedes="p3bind-original",
                )
            correction = ProtectedDevelopmentBindingRun(
                Path(temp),
                ROOT,
                binding_run_id="p3bind-correction",
                package_version="1.0.1",
                supersedes="p3bind-original",
            )
            self.assertEqual(correction.supersedes, "p3bind-original")

    def test_20_stable_identity_changes_with_authorized_target_content(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            one_doc = _semantic_package("p3bind-one")
            two_doc = _semantic_package("p3bind-two")
            two_doc["minimum_target_projection"]["rows"][0]["isolated_sales"] = "999"
            first = ProtectedDevelopmentBindingRun(root / "one", ROOT, binding_run_id="p3bind-one").finalize(one_doc)
            second = ProtectedDevelopmentBindingRun(root / "two", ROOT, binding_run_id="p3bind-two").finalize(two_doc)
            self.assertNotEqual(first["stable_binding_identity"], second["stable_binding_identity"])

    def test_21_disclosure_safe_report_excludes_protected_details_and_digests(self):
        result = BindingResult(
            "p3bind-safe",
            "a" * 64,
            "pipe03-binding:sha256:" + "b" * 64,
            "c" * 64,
            Path("protected"),
            2,
            1,
            1,
            DevelopmentTargetAccessAudit(authorized_isolated_sales_decode_calls=2),
        )
        report = build_disclosure_safe_result(result)
        serialized = json.dumps(report).lower()
        for forbidden in (
            "source_row",
            "physical_location_id",
            "nonce",
            "sha256",
            "cell_address",
            "101",
        ):
            self.assertNotIn(forbidden, serialized)

    def test_22_protected_paths_are_not_stageable(self):
        for protected in (
            "outputs/pipe03_wisconsin_development_target_access_binding.json",
            "outputs/pipe03-bindings/p3bind-real/READY.json",
        ):
            with self.assertRaisesRegex(ConformanceError, "PROTECTED_TRACKED_PATH_REJECTED"):
                assert_no_protected_tracked_paths([protected])

    def test_23_cli_without_registry_is_disclosure_safe_and_does_no_discovery(self):
        stream = io.StringIO()
        with patch.object(sys, "argv", ["pipe03-bind"]), redirect_stdout(stream):
            code = cli.main()
        report = json.loads(stream.getvalue())
        self.assertEqual(code, 2)
        self.assertFalse(report["filesystem_discovery_performed"])
        self.assertEqual(report["impacted_sales_values_materialized"], 0)
        self.assertFalse(report["protected_details_disclosed"])

    def test_24_accepted_pipe_framework_is_reused(self):
        source = inspect.getsource(binding)
        self.assertIn("from sprouts_customer_geography.pipe01.canonical import", source)
        self.assertIn("from sprouts_customer_geography.pipe01.commitment import", source)
        self.assertIn("from sprouts_customer_geography.pipe02.resolver import _is_within", source)
        self.assertNotIn("import hashlib", source)

    def test_25_fictional_end_to_end_binding(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            resolver = _registry(root, root / "registry.json")
            with patch.object(binding, "load_model04_binding", return_value=_model_binding()):
                result = execute_protected_binding(
                    repository_root=ROOT,
                    resolver=resolver,
                    binding_run_id="p3bind-fictional-e2e",
                )
            self.assertTrue(protected_binding_is_ready(result.run_dir))
            self.assertEqual(result.eligible_observation_count, 2)
            self.assertEqual(result.quarantined_observation_count, 1)
            package = json.loads(
                (result.run_dir / "pipe03_wisconsin_development_target_access_binding.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(package["package_id"], BINDING_PACKAGE_ID)
            self.assertEqual(len(package["minimum_target_projection"]["rows"]), 2)
            self.assertFalse(package["consumption_semantics"]["binding_marks_development_consumed"])
            self.assertFalse(package["finalization"]["impacted_sales_accessed"])
            self.assertFalse(package["finalization"]["non_wisconsin_targets_accessed"])


if __name__ == "__main__":
    unittest.main()
