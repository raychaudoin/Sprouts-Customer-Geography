from __future__ import annotations

import copy
import io
import json
import tempfile
import unittest
import zipfile
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from sprouts_customer_geography.pipe01.canonical import content_digest, file_sha256
from sprouts_customer_geography.pipe01.commitment import DOMAIN_SEPARATOR, freeze_commitment
from sprouts_customer_geography.pipe01.errors import ConformanceError
from sprouts_customer_geography.pipe01.safeguards import assert_no_protected_tracked_paths
from sprouts_customer_geography.pipe04 import binding, cli
from sprouts_customer_geography.pipe04.binding import (
    ProtectedBindingRun,
    build_disclosure_safe_result,
    derive_eligible_wisconsin_cohort,
    execute_protected_binding,
    protected_binding_is_ready,
    validate_semantic_package,
    verify_model10_authority,
)
from sprouts_customer_geography.pipe04.resolver import ProtectedHandleResolver, load_authorized_registry
from sprouts_customer_geography.pipe04.xlsx_projection import Model10WisconsinProjectionPolicy, TargetAccessAudit, project_authorized_isolated_sales


ROOT = Path(__file__).resolve().parents[1]


def _model10_record(*, row: int, observation: str, seed: str, vintage: int, market: str, physical: str, historical: str | None, quarantined: bool = False) -> dict:
    return {
        "source_observation_id": observation,
        "source_observation_lineage": {
            "source_workbook_identity": "FICTIONAL-SUCCESSOR-WISCONSIN",
            "source_sheet": "Targets",
            "source_row": row,
            "source_seed_point_id": seed,
        },
        "market": market,
        "forecast_vintage": vintage,
        "successor_physical_location_id": physical,
        "historical_model04_physical_location_id": historical,
        "identity_state": "AMBIGUOUS_IDENTITY" if quarantined else ("SAME_UNDERLYING_LOCATION" if historical else "GENUINELY_NEW_LOCATION"),
        "identity_rule_reason_code": "FICTIONAL_CONFORMANCE",
        "quarantined": quarantined,
        "quarantine_reason": "FICTIONAL_AMBIGUITY" if quarantined else None,
        "successor_canonical_anchor": None if quarantined else {"source_observation_id": observation},
        "historical_evidence_role_lineage": [] if historical is None else [{"evidence_role": "DEVELOPMENT_REFERENCE", "evidence_subrole": "FICTIONAL", "historical_target_view_state": "DEVELOPMENT_CONSUMED"}],
        "model09_development_eligible": not quarantined,
        "target_access_state": "NOT_ACCESSED_BY_MODEL10",
    }


def _model10_package() -> dict:
    records = [
        _model10_record(row=2, observation="sobs-fictional-2024", seed="SUCCESSOR-CHANGED-SEED-2024", vintage=2024, market="Milwaukee successor", physical="HISTORICAL-MODEL04-LOCATION", historical="HISTORICAL-MODEL04-LOCATION"),
        _model10_record(row=3, observation="sobs-fictional-2025", seed="SUCCESSOR-NEW-SEED-2025", vintage=2025, market="Statewide Wisconsin", physical="m10loc-fictional-new", historical=None),
        _model10_record(row=4, observation="sobs-fictional-2026-q", seed="SUCCESSOR-QUARANTINED-2026", vintage=2026, market="Madison successor", physical="m10qloc-fictional", historical=None, quarantined=True),
    ]
    semantic = {
        "package_id": "MODEL10_WISCONSIN_COHORT_IDENTITY_LINEAGE_PACKAGE_V1",
        "version": "1.0.0",
        "materialization_run_id": "m10run-fictional",
        "state": "ready",
        "contract_authority": {},
        "model04_authority": {},
        "target_blind_projection": {"body_columns": "A:I", "target_body_values_materialized": False, "isolated_sales_materialized": False, "impacted_sales_materialized": False},
        "source_authorities": [],
        "identity_rules": {"physical_location_matching_partition": "wisconsin_state", "source_market_label_is_identity_partition": False, "target_evidence_permitted": False},
        "records": records,
        "aggregate_conformance": {
            "observation_count": 3,
            "physical_location_count": 3,
            "historically_linked_observation_count": 1,
            "quarantined_observation_count": 1,
            "model09_development_eligible_observation_count": 2,
            "markets": sorted({record["market"] for record in records}),
            "forecast_vintages": [2024, 2025, 2026],
        },
        "target_access": {"isolated_sales_accessed": False, "impacted_sales_accessed": False, "target_ordering_used": False, "forecast_magnitude_used": False, "model_predictions_or_residuals_used": False, "marks_development_consumed": False},
        "protected_handle_registry_identity": "fictional-model10-registry",
        "supersedes": None,
        "supersession_policy": "fictional immutable correction",
    }
    return {**semantic, "protected_content_sha256": content_digest(semantic), "protected_content_hash_semantics": "fictional conformance"}


def _inline(column: str, row: int, value: str) -> str:
    return f'<c r="{column}{row}" t="inlineStr"><is><t>{value}</t></is></c>'


def _number(column: str, row: int, value: str) -> str:
    return f'<c r="{column}{row}"><v>{value}</v></c>'


def _write_xlsx(path: Path, *, second_seed: str = "SUCCESSOR-NEW-SEED-2025") -> None:
    rows = [
        '<row r="1">' + _inline("A", 1, "Seed Point ID") + _inline("B", 1, "Forecast Vintage") + _inline("C", 1, "Isolated Sales") + _inline("D", 1, "Impacted Sales") + "</row>",
        '<row r="2">' + _inline("A", 2, "SUCCESSOR-CHANGED-SEED-2024") + _inline("B", 2, "Forecast 2024") + _number("C", 2, "101") + _inline("D", 2, "FORBIDDEN-IMPACTED") + "</row>",
        '<row r="3">' + _inline("A", 3, second_seed) + _inline("B", 3, "Forecast 2025") + _number("C", 3, "202.50") + _inline("D", 3, "FORBIDDEN-IMPACTED-2") + "</row>",
        '<row r="4">' + _inline("A", 4, "SUCCESSOR-QUARANTINED-2026") + _inline("B", 4, "Forecast 2026") + _inline("C", 4, "FORBIDDEN-QUARANTINED-TARGET") + _inline("D", 4, "FORBIDDEN-QUARANTINED-IMPACTED") + "</row>",
        '<row r="8">' + _inline("A", 8, "FICTIONAL-MICHIGAN") + _inline("B", 8, "Forecast 2026") + _inline("C", 8, "FORBIDDEN-NON-WISCONSIN-TARGET") + _inline("D", 8, "FORBIDDEN-NON-WISCONSIN-IMPACTED") + "</row>",
    ]
    worksheet = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>' + "".join(rows) + "</sheetData></worksheet>"
    workbook = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Targets" sheetId="1" r:id="rId1"/></sheets></workbook>'
    relationships = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>'
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", relationships)
        archive.writestr("xl/worksheets/sheet1.xml", worksheet)


def _projection(handle: str = "phandle-target") -> dict:
    return {
        "projection_id": "MODEL09_MINIMUM_MODEL10_WISCONSIN_DEVELOPMENT_TARGET_PROJECTION_V1",
        "version": "1.0.0",
        "workbook_handle": handle,
        "source_workbook_identity": "FICTIONAL-SUCCESSOR-WISCONSIN",
        "default_deny": True,
        "allowed_state": "wisconsin",
        "permitted_target_field": "Isolated Sales",
        "denied_target_field": "Impacted Sales",
        "successor_lineage_field": "source_seed_point_id",
        "forecast_vintage_field": "forecast_vintage",
        "source_row_field": "source_row",
        "historical_model04_equality_required": False,
        "sheet_name": "Targets",
        "header_row": 1,
        "columns": {"lineage_key": "A", "forecast_vintage": "B", "isolated_sales": "C"},
        "headers": {"lineage_key": "Seed Point ID", "forecast_vintage": "Forecast Vintage", "isolated_sales": "Isolated Sales"},
    }


def _authority() -> dict:
    return {
        "commitment_artifact_id": binding.MODEL10_COMMITMENT_ID,
        "commitment_artifact_version": binding.MODEL10_COMMITMENT_VERSION,
        "package_id": binding.MODEL10_PACKAGE_ID,
        "package_version": binding.MODEL10_PACKAGE_VERSION,
        "substantive_h": binding.ACCEPTED_MODEL10_H,
        "acceptance_record_a": binding.ACCEPTED_MODEL10_A,
        "canonical_merge": binding.ACCEPTED_MODEL10_MERGE,
        "commitment_reconciled": True,
        "ready_marker_reconciled": True,
    }


def _registry(root: Path, registry_path: Path) -> ProtectedHandleResolver:
    (root / "output").mkdir(exist_ok=True)
    for name in ("model10.json", "model10-evidence.json", "model10-ready.json"):
        (root / name).write_text("{}", encoding="utf-8")
    (root / "model10-nonce.bin").write_bytes(b"N" * 32)
    if not (root / "targets.xlsx").exists():
        _write_xlsx(root / "targets.xlsx")
    document = {
        "registry_id": "PIPE04_PROTECTED_HANDLE_REGISTRY_V1",
        "version": "1.0.0",
        "protected_roots": {"proot-fixture": str(root.resolve())},
        "resources": {
            "phandle-model10": {"root_handle": "proot-fixture", "relative_path": "model10.json", "kind": "model10_package"},
            "phandle-model10-evidence": {"root_handle": "proot-fixture", "relative_path": "model10-evidence.json", "kind": "model10_commitment_evidence"},
            "phandle-model10-nonce": {"root_handle": "proot-fixture", "relative_path": "model10-nonce.bin", "kind": "model10_commitment_nonce"},
            "phandle-model10-ready": {"root_handle": "proot-fixture", "relative_path": "model10-ready.json", "kind": "model10_ready_marker"},
            "phandle-target": {"root_handle": "proot-fixture", "relative_path": "targets.xlsx", "kind": "wisconsin_development_target_workbook"},
            "phandle-output": {"root_handle": "proot-fixture", "relative_path": "output", "kind": "pipe04_output_root"},
        },
        "binding_request": {
            "model10_package_handle": "phandle-model10",
            "model10_commitment_evidence_handle": "phandle-model10-evidence",
            "model10_commitment_nonce_handle": "phandle-model10-nonce",
            "model10_ready_marker_handle": "phandle-model10-ready",
            "wisconsin_development_target_workbook_handles": ["phandle-target"],
            "binding_output_root_handle": "phandle-output",
        },
        "target_source_authorities": [{"authority_id": "FICTIONAL-WISCONSIN-SUCCESSOR-TARGET", "provenance_class": "fictional_conformance", "source_workbook_identity": "FICTIONAL-SUCCESSOR-WISCONSIN", "workbook_handle": "phandle-target", "byte_hash_permitted": False, "projection": _projection()}],
    }
    registry_path.write_text(json.dumps(document), encoding="utf-8")
    return ProtectedHandleResolver.load(registry_path, ROOT)


def _projection_rows() -> list[dict]:
    _cohort, rows, _quarantined = derive_eligible_wisconsin_cohort(_model10_package())
    return rows


class Pipe04BindingTests(unittest.TestCase):
    def test_01_exact_model10_commitment_package_and_ready_verification(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "config/model").mkdir(parents=True)
            (root / "config/pipe04").mkdir(parents=True)
            package_path = root / "model10.json"
            package_path.write_text(json.dumps(_model10_package(), sort_keys=True), encoding="utf-8")
            nonce = b"F" * 32
            commitment_value = freeze_commitment(file_sha256(package_path), nonce)
            evidence = {"artifact_id": binding.MODEL10_COMMITMENT_ID, "version": "1.0.0", "protected_package_id": binding.MODEL10_PACKAGE_ID, "protected_package_version": "1.0.0", "domain": DOMAIN_SEPARATOR.decode("utf-8"), "commitment_sha256": commitment_value}
            ready = {"materialization_run_id": "m10run-fictional", "state": "ready", "package_id": binding.MODEL10_PACKAGE_ID, "package_version": "1.0.0", "protected_content_sha256": _model10_package()["protected_content_sha256"], "commitment_sha256": commitment_value}
            (root / "evidence.json").write_text(json.dumps(evidence), encoding="utf-8")
            (root / "nonce.bin").write_bytes(nonce)
            (root / "READY.json").write_text(json.dumps(ready), encoding="utf-8")
            commitment = {**evidence, "$schema": "fictional", "commitment_semantics": "fictional", "protected_package_digest_disclosed": False, "nonce_disclosed": False, "observation_content_disclosed": False, "supersedes": None, "supersession_policy": "fictional"}
            (root / binding.MODEL10_COMMITMENT_DOCUMENT).write_text(json.dumps(commitment), encoding="utf-8")
            contract = {"artifact_id": binding.CONTRACT_ID, "version": binding.CONTRACT_VERSION, "accepted_model10_authority": {"commitment_id": binding.MODEL10_COMMITMENT_ID, "package_id": binding.MODEL10_PACKAGE_ID, "substantive_h": binding.ACCEPTED_MODEL10_H, "acceptance_record_a": binding.ACCEPTED_MODEL10_A, "canonical_merge": binding.ACCEPTED_MODEL10_MERGE}}
            (root / binding.PIPE04_CONTRACT_DOCUMENT).write_text(json.dumps(contract), encoding="utf-8")
            with patch.object(binding, "EXPECTED_MODEL10_COMMITMENT", commitment_value):
                verified, authority = verify_model10_authority(repository_root=root, package_path=package_path, commitment_evidence_path=root / "evidence.json", nonce_path=root / "nonce.bin", ready_path=root / "READY.json")
            self.assertEqual(verified["package_id"], binding.MODEL10_PACKAGE_ID)
            self.assertTrue(authority["commitment_reconciled"])

    def test_02_model10_commitment_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "config/model").mkdir(parents=True)
            (root / "config/pipe04").mkdir(parents=True)
            (root / binding.MODEL10_COMMITMENT_DOCUMENT).write_text("{}", encoding="utf-8")
            (root / binding.PIPE04_CONTRACT_DOCUMENT).write_text("{}", encoding="utf-8")
            for name in ("package.json", "evidence.json", "ready.json"):
                (root / name).write_text("{}", encoding="utf-8")
            (root / "nonce.bin").write_bytes(b"F" * 32)
            with self.assertRaises(ConformanceError) as caught:
                verify_model10_authority(repository_root=root, package_path=root / "package.json", commitment_evidence_path=root / "evidence.json", nonce_path=root / "nonce.bin", ready_path=root / "ready.json")
            self.assertEqual(caught.exception.code, "MODEL10_COMMITMENT_AUTHORITY_MISMATCH")

    def test_03_complete_eligible_cohort_quarantine_and_historical_linkage(self):
        cohort, rows, quarantined = derive_eligible_wisconsin_cohort(_model10_package())
        self.assertEqual(len(cohort), 2)
        self.assertEqual(len(rows), 2)
        self.assertEqual(quarantined, 1)
        self.assertEqual(cohort[0]["source_observation_lineage"]["source_seed_point_id"], "SUCCESSOR-CHANGED-SEED-2024")
        self.assertEqual(cohort[0]["historical_model04_physical_location_id"], "HISTORICAL-MODEL04-LOCATION")
        self.assertIsNone(cohort[1]["historical_model04_physical_location_id"])

    def test_04_isolated_sales_only_projection_ignores_denied_rows_and_fields(self):
        with tempfile.TemporaryDirectory() as temporary:
            workbook = Path(temporary) / "targets.xlsx"
            _write_xlsx(workbook)
            policy = Model10WisconsinProjectionPolicy(_projection(), "phandle-target", "FICTIONAL-SUCCESSOR-WISCONSIN")
            projected, audit = project_authorized_isolated_sales(workbook, policy, _projection_rows())
            self.assertEqual([row["isolated_sales"] for row in projected], ["101", "202.5"])
            self.assertEqual(audit.impacted_sales_decode_calls, 0)
            self.assertEqual(audit.non_wisconsin_target_decode_calls, 0)
            self.assertNotIn("FORBIDDEN", json.dumps(projected))

    def test_05_impacted_sales_and_non_wisconsin_projection_authority_denied(self):
        impacted = _projection()
        impacted["permitted_target_field"] = "Impacted Sales"
        with self.assertRaises(ConformanceError):
            Model10WisconsinProjectionPolicy(impacted, "phandle-target", "FICTIONAL-SUCCESSOR-WISCONSIN")
        michigan = _projection()
        michigan["allowed_state"] = "michigan"
        with self.assertRaises(ConformanceError):
            Model10WisconsinProjectionPolicy(michigan, "phandle-target", "FICTIONAL-SUCCESSOR-WISCONSIN")

    def test_06_successor_lineage_mismatch_rejected_without_model04_fallback(self):
        with tempfile.TemporaryDirectory() as temporary:
            workbook = Path(temporary) / "targets.xlsx"
            _write_xlsx(workbook, second_seed="HISTORICAL-MODEL04-SEED")
            policy = Model10WisconsinProjectionPolicy(_projection(), "phandle-target", "FICTIONAL-SUCCESSOR-WISCONSIN")
            with self.assertRaises(ConformanceError) as caught:
                project_authorized_isolated_sales(workbook, policy, _projection_rows())
            self.assertEqual(caught.exception.code, "TARGET_SUCCESSOR_LINEAGE_UNRESOLVED")

    def test_07_exact_handle_resolution_and_containment(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            resolver = _registry(root, root / "registry.json")
            self.assertEqual(resolver.resolve("phandle-target", "wisconsin_development_target_workbook").path, (root / "targets.xlsx").resolve())
            document = json.loads((root / "registry.json").read_text(encoding="utf-8"))
            document["resources"]["phandle-target"]["relative_path"] = "../escape.xlsx"
            (root / "bad-registry.json").write_text(json.dumps(document), encoding="utf-8")
            bad = ProtectedHandleResolver.load(root / "bad-registry.json", ROOT)
            with self.assertRaises(ConformanceError) as caught:
                bad.resolve("phandle-target", "wisconsin_development_target_workbook")
            self.assertEqual(caught.exception.code, "PROTECTED_PATH_TRAVERSAL_REJECTED")

    def test_08_full_binding_freezes_identity_and_writes_ready_last(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            resolver = _registry(root, root / "registry.json")
            writes: list[str] = []
            original = binding.write_json_exclusive

            def recording(path: Path, value: object) -> None:
                writes.append(path.name)
                original(path, value)

            with patch.object(binding, "verify_model10_authority", return_value=(_model10_package(), _authority())), patch.object(binding, "write_json_exclusive", side_effect=recording):
                result = execute_protected_binding(repository_root=ROOT, resolver=resolver, binding_run_id="p4bind-fictional-full")
            self.assertTrue(protected_binding_is_ready(result.run_dir))
            self.assertEqual(writes[-1], "READY.json")
            package = json.loads((result.run_dir / "pipe04_model10_wisconsin_development_binding.json").read_text(encoding="utf-8"))
            self.assertEqual(package["cohort_freeze"]["cohort_identity_sha256"], content_digest(package["eligible_wisconsin_cohort"]))
            self.assertFalse(package["finalization"]["historical_model04_source_equality_required"])

    def test_09_target_content_cannot_change_identity_or_membership(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            resolver = _registry(root, root / "registry.json")
            with patch.object(binding, "verify_model10_authority", return_value=(_model10_package(), _authority())):
                result = execute_protected_binding(repository_root=ROOT, resolver=resolver, binding_run_id="p4bind-invariance")
            package = json.loads((result.run_dir / "pipe04_model10_wisconsin_development_binding.json").read_text(encoding="utf-8"))
            for key in ("protected_content_sha256", "stable_binding_identity", "protected_content_hash_semantics"):
                package.pop(key)
            package["minimum_target_projection"]["rows"][0]["source_observation_id"] = "sobs-target-derived"
            with self.assertRaises(ConformanceError):
                validate_semantic_package(package)

    def test_10_interruption_remains_incomplete_and_unready(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            resolver = _registry(root, root / "registry.json")
            with patch.object(binding, "verify_model10_authority", return_value=(_model10_package(), _authority())), patch.object(binding, "project_authorized_isolated_sales", side_effect=ConformanceError("FICTIONAL_INTERRUPTION", "stop")):
                with self.assertRaises(ConformanceError):
                    execute_protected_binding(repository_root=ROOT, resolver=resolver, binding_run_id="p4bind-interrupted")
            run = root / "output/pipe04-bindings/p4bind-interrupted"
            self.assertTrue((run / "binding_state.json").is_file())
            self.assertFalse((run / "READY.json").exists())

    def test_11_immutable_runs_and_supersession(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = ProtectedBindingRun(root, ROOT, binding_run_id="p4bind-first")
            self.assertFalse(protected_binding_is_ready(first.run_dir))
            with self.assertRaises(ConformanceError) as caught:
                ProtectedBindingRun(root, ROOT, binding_run_id="p4bind-first")
            self.assertEqual(caught.exception.code, "BINDING_ALREADY_EXISTS")
            corrected = ProtectedBindingRun(root, ROOT, binding_run_id="p4bind-corrected", package_version="1.0.1", supersedes="p4bind-first")
            self.assertEqual(corrected.supersedes, "p4bind-first")
            with self.assertRaises(ConformanceError):
                ProtectedBindingRun(root, ROOT, binding_run_id="p4bind-bad-correction", supersedes="p4bind-first")

    def test_12_disclosure_safe_reporting(self):
        result = binding.BindingResult("p4bind-secret", Path("C:/protected/secret"), "a" * 64, "pipe04-binding:sha256:" + "b" * 64, "c" * 64, 2, 1, 1, TargetAccessAudit(authorized_isolated_sales_decode_calls=2))
        report = build_disclosure_safe_result(result)
        rendered = json.dumps(report).lower()
        self.assertNotIn("secret", rendered)
        self.assertNotIn("sha256", rendered)
        self.assertEqual(report["impacted_sales_values_materialized"], 0)

    def test_13_cli_without_registry_is_disclosure_safe_and_does_not_discover(self):
        output = io.StringIO()
        with patch("sys.argv", ["pipe04"]), patch.dict("os.environ", {}, clear=True), redirect_stdout(output):
            self.assertEqual(cli.main(), 2)
        report = json.loads(output.getvalue())
        self.assertFalse(report["filesystem_discovery_performed"])
        self.assertFalse(report["protected_details_disclosed"])

    def test_14_registry_requires_exact_request_and_source_handles(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _registry(root, root / "registry.json")
            document = json.loads((root / "registry.json").read_text(encoding="utf-8"))
            document["binding_request"]["extra_handle"] = "phandle-extra"
            (root / "bad.json").write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaises(ConformanceError) as caught:
                load_authorized_registry(root / "bad.json", ROOT)
            self.assertEqual(caught.exception.code, "BINDING_REQUEST_INVALID")

    def test_15_pipe04_protected_artifacts_are_not_stageable(self):
        with self.assertRaises(ConformanceError) as caught:
            assert_no_protected_tracked_paths(
                ["local/pipe04-bindings/p4bind-fictional/pipe04_model10_wisconsin_development_binding.json"]
            )
        self.assertEqual(caught.exception.code, "PROTECTED_TRACKED_PATH_REJECTED")


if __name__ == "__main__":
    unittest.main()
