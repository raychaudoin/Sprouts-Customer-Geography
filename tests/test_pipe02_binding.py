from __future__ import annotations

import copy
import inspect
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from sprouts_customer_geography.model06 import build_commitment_evidence
from sprouts_customer_geography.pipe01.canonical import content_digest, write_json_exclusive
from sprouts_customer_geography.pipe01.errors import ConformanceError
from sprouts_customer_geography.pipe01.orchestration import load_model04_binding
from sprouts_customer_geography.pipe01.run import MANDATORY_DEPENDENCIES, ProtectedRun
from sprouts_customer_geography.pipe01.safeguards import assert_no_protected_tracked_paths
from sprouts_customer_geography.pipe02 import binding
from sprouts_customer_geography.pipe02.binding import (
    BINDING_PACKAGE_ID,
    BINDING_PACKAGE_VERSION,
    EXPECTED_PIPE_EXECUTION_COMMIT,
    EXPECTED_PIPE_RUN_ID,
    ProtectedBindingRun,
    build_disclosure_safe_result,
    derive_temporal_mapping,
    protected_binding_is_ready,
    reconcile_pipe_freeze,
)
from sprouts_customer_geography.pipe02.resolver import ProtectedHandleResolver
from sprouts_customer_geography.pipe02.xlsx_projection import (
    MinimumTargetProjectionPolicy,
    _decode_cell_payload,
    project_target_addresses,
)


ROOT = Path(__file__).resolve().parents[1]
FICTIONAL_LOCATION = "fictional-physical-location-pipe02"


def _dependencies() -> dict[str, str]:
    return {key: f"accepted-fictional-{key}" for key in MANDATORY_DEPENDENCIES}


def _model04_record(*, year: int, seed: str, role: str, source_identity: str, state: str) -> dict:
    anchor = {
        "latitude": 0.0,
        "longitude": 0.0,
        "source_workbook_identity": "MODEL03A_DEVELOPMENT_REFERENCE_WORKBOOK",
        "source_sheet": "Sheet1",
        "source_row": 2,
        "source_seed_point_id": "FICTIONAL-PRIOR",
        "anchor_version": "MODEL04_EARLIEST_OBSERVED_MEMBER_ANCHOR_V1",
        "selection_semantics": "EARLIEST_VINTAGE_THEN_ACCEPTED_PROVENANCE_TIER_THEN_SOURCE_LINEAGE",
    }
    return {
        "package_id": "MODEL04_VALIDATION_IDENTITY_ROLE_ANCHOR_PACKAGE_V1",
        "package_version": "1.0.0",
        "identity_version": "MODEL04_TARGET_BLIND_PHYSICAL_LOCATION_IDENTITY_V1",
        "physical_location_id": FICTIONAL_LOCATION,
        "source_workbook_identity": source_identity,
        "source_sheet": "Sheet1",
        "source_row": 2 if year < 2026 else 3,
        "source_seed_point_id": seed,
        "vintage": str(year),
        "vintage_year": year,
        "market": "milwaukee",
        "identity_state": state,
        "identity_rule_reason_code": "MORE_THAN_500M_WITHOUT_STABLE_LINEAGE_OR_CONFLICT" if year < 2026 else "EXACT_OBSERVED_COORDINATE",
        "linked_prior_physical_location_id": FICTIONAL_LOCATION if year == 2026 else None,
        "quarantined": False,
        "evidence_role": role,
        "evidence_subrole": "PRIOR_MILWAUKEE_CONSUMED" if year < 2026 else "MILWAUKEE_2026_REPEATED_LOCATION",
        "observed_coordinate": {"latitude": 0.0, "longitude": 0.0, "provenance": "FICTIONAL_CONFORMANCE_ONLY"},
        "canonical_anchor": anchor,
        "canonical_anchor_state": "SELECTED_ACTUAL_OBSERVED_MEMBER",
        "target_view_state": "DEVELOPMENT_CONSUMED" if year < 2026 else "SEALED",
    }


def _fictional_model04_package() -> dict:
    package = {
        "$schema": "model04-validation-identity-role-anchor-package-v1",
        "package_id": "MODEL04_VALIDATION_IDENTITY_ROLE_ANCHOR_PACKAGE_V1",
        "package_version": "1.0.0",
        "identity_version": "MODEL04_TARGET_BLIND_PHYSICAL_LOCATION_IDENTITY_V1",
        "canonical_anchor_version": "MODEL04_EARLIEST_OBSERVED_MEMBER_ANCHOR_V1",
        "status": "fictional_conformance_only",
        "target_blind_projection": {"sealed_targets_supplied_or_used": False},
        "source_projection_identities": [],
        "identity_rules": {},
        "evidence_role_semantics": ["DEVELOPMENT_REFERENCE", "TEMPORAL_VALIDATION"],
        "records": [
            _model04_record(year=2025, seed="FICTIONAL-PRIOR", role="DEVELOPMENT_REFERENCE", source_identity="MODEL03A_DEVELOPMENT_REFERENCE_WORKBOOK", state="GENUINELY_NEW_LOCATION"),
            _model04_record(year=2026, seed="FICTIONAL-CURRENT", role="TEMPORAL_VALIDATION", source_identity="FICTIONAL_2026_TARGET_WORKBOOK", state="SAME_UNDERLYING_LOCATION"),
        ],
        "supersedes": None,
        "supersession_policy": "fictional immutable fixture",
        "materialization_provenance": {"mode": "genuinely_fictional"},
    }
    semantic = copy.deepcopy(package)
    package["protected_content_sha256"] = content_digest(semantic)
    package["protected_content_hash_semantics"] = "fictional test follows accepted hash exclusion semantics"
    semantic = copy.deepcopy(package)
    semantic.pop("protected_content_sha256")
    semantic.pop("protected_content_hash_semantics")
    package["protected_content_sha256"] = content_digest(semantic)
    return package


def _write_model04(root: Path) -> tuple[Path, Path, Path]:
    package_path = root / "model04.json"
    nonce_path = root / "nonce.bin"
    evidence_path = root / "evidence.json"
    write_json_exclusive(package_path, _fictional_model04_package())
    nonce = b"F" * 32
    nonce_path.write_bytes(nonce)
    write_json_exclusive(evidence_path, build_commitment_evidence(package_path, nonce))
    return package_path, nonce_path, evidence_path


def _policy_document(workbook_handle: str = "phandle-target") -> dict:
    return {
        "projection_id": "MODEL07_MINIMUM_TEMPORAL_TARGET_PROJECTION_V1",
        "version": "1.0.0",
        "workbook_handle": workbook_handle,
        "default_deny": True,
        "allowed_market": "milwaukee",
        "allowed_role": "TEMPORAL_VALIDATION",
        "target_year": 2026,
        "sheet_name": "Authorized Projection",
        "header_row": 1,
        "columns": {"lineage_key": "A", "forecast_vintage": "B", "isolated_sales": "C"},
        "headers": {"lineage_key": "Lineage Key", "forecast_vintage": "Forecast Vintage", "isolated_sales": "Isolated Sales"},
        "model04_lineage_field": "source_seed_point_id",
    }


def _write_xlsx(path: Path, prior_value: str = "111111", current_value: str = "222222") -> None:
    workbook = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Authorized Projection" sheetId="1" r:id="rId1"/></sheets></workbook>"""
    relationships = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>"""
    sheet = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>
<row r="1"><c r="A1" t="inlineStr"><is><t>Lineage Key</t></is></c><c r="B1" t="inlineStr"><is><t>Forecast Vintage</t></is></c><c r="C1" t="inlineStr"><is><t>Isolated Sales</t></is></c><c r="D1" t="inlineStr"><is><t>Impacted Sales</t></is></c></row>
<row r="2"><c r="A2" t="inlineStr"><is><t>FICTIONAL-PRIOR</t></is></c><c r="B2" t="n"><v>2025</v></c><c r="C2" t="n"><v>{prior_value}</v></c><c r="D2" t="n"><v>333333</v></c></row>
<row r="3"><c r="A3" t="inlineStr"><is><t>FICTIONAL-CURRENT</t></is></c><c r="B3" t="n"><v>2026</v></c><c r="C3" t="n"><v>{current_value}</v></c><c r="D3" t="n"><v>444444</v></c></row>
<row r="4"><c r="A4" t="inlineStr"><is><t>UNRELATED-HOLDOUT</t></is></c><c r="B4" t="n"><v>2026</v></c><c r="C4" t="n"><v>999999</v></c></row>
</sheetData></worksheet>"""
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", relationships)
        archive.writestr("xl/worksheets/sheet1.xml", sheet)


def _requested_pairs() -> list[dict]:
    return [
        {"pair_role": "most_recent_eligible_prior", "physical_location_id": FICTIONAL_LOCATION, "lineage_key": "FICTIONAL-PRIOR", "vintage_year": 2025},
        {"pair_role": "corresponding_2026", "physical_location_id": FICTIONAL_LOCATION, "lineage_key": "FICTIONAL-CURRENT", "vintage_year": 2026},
    ]


def _write_pipe_run(root: Path) -> tuple[Path, str]:
    run = ProtectedRun(root, ROOT, run_id=EXPECTED_PIPE_RUN_ID)
    run.write_artifact(
        "context-0001-model04-lineage.json",
        {"artifact_id": "fictional-lineage", "physical_location_id": FICTIONAL_LOCATION, "evidence_role": "TEMPORAL_VALIDATION"},
    )
    run.write_artifact("context-0001-baseline-prediction.json", {"artifact_id": "fictional-frozen-prediction"})
    run.write_artifact("context-0001-eligibility-readiness.json", {"artifact_id": "fictional-readiness"})
    run.write_artifact("context-0001-context-spatial-evidence.json", {"context_spec_id": "fictional-spatial"})
    finalized = run.finalize(_dependencies(), EXPECTED_PIPE_EXECUTION_COMMIT, {"fictional": "exact"}, {"mandatory_passed": True}, False)
    return run.run_dir, finalized["commitment_sha256"]


def _temporal_mapping() -> list[dict]:
    return [{"physical_location_id": FICTIONAL_LOCATION, "pipe_context_ordinal": 1}]


def _finalizable_binding(binding_run_id: str, version: str = BINDING_PACKAGE_VERSION, supersedes: str | None = None) -> dict:
    return {
        "$schema": "pipe02-protected-validation-access-binding-v1",
        "package_id": BINDING_PACKAGE_ID,
        "version": version,
        "binding_run_id": binding_run_id,
        "state": "ready",
        "model_authority": {
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
        "pipe01_authority": {
            "run_id": EXPECTED_PIPE_RUN_ID,
            "freeze_commitment": binding.EXPECTED_PIPE_FREEZE_COMMITMENT,
            "upstream_frozen_artifacts_regenerated": False,
        },
        "target_source_authority": {"whole_workbook_hash_computed": False},
        "temporal_eligibility_mapping": [{"physical_location_id": FICTIONAL_LOCATION}],
        "minimum_target_projection": {
            "projection_id": "MODEL07_MINIMUM_TEMPORAL_TARGET_PROJECTION_V1",
            "version": "1.0.0",
            "default_deny": True,
            "target_cells": [{"physical_location_id": FICTIONAL_LOCATION, "prior": {"isolated_sales_cell_address": "C2"}, "current_2026": {"isolated_sales_cell_address": "C3"}}],
            "target_access_audit": {"target_payload_decode_calls": 0, "target_values_materialized": False},
        },
        "protected_handle_registry_identity": "fictional-registry",
        "finalization": {"mandatory_reconciliations_passed": True, "target_values_accessed": False, "ready_marker_written_last": True},
        "supersedes": supersedes,
        "supersession_policy": "fictional immutable fixture",
    }


def _registry(root: Path, registry_path: Path) -> ProtectedHandleResolver:
    output = root / "output"
    output.mkdir()
    target = root / "nondiscoverable-source.bin"
    target.write_bytes(b"fixture")
    run = root / "run"
    run.mkdir()
    model = root / "model.json"
    model.write_text("{}", encoding="utf-8")
    nonce = root / "nonce.bin"
    nonce.write_bytes(b"F" * 32)
    document = {
        "registry_id": "PIPE02_PROTECTED_HANDLE_REGISTRY_V1",
        "version": "1.0.0",
        "protected_roots": {"proot-fictional": str(root)},
        "resources": {
            "phandle-output": {"kind": "pipe02_output_root", "root_handle": "proot-fictional", "relative_path": "output"},
            "phandle-target": {"kind": "validation_target_workbook", "root_handle": "proot-fictional", "relative_path": "nondiscoverable-source.bin"},
            "phandle-run": {"kind": "pipe01_run_directory", "root_handle": "proot-fictional", "relative_path": "run"},
            "phandle-model": {"kind": "model04_package", "root_handle": "proot-fictional", "relative_path": "model.json"},
            "phandle-verification": {"kind": "model04_verification_material", "root_handle": "proot-fictional", "relative_path": "nonce.bin"},
        },
        "binding_request": {
            "model04_package_handle": "phandle-model",
            "model04_verification_material_handle": "phandle-verification",
            "pipe01_run_directory_handle": "phandle-run",
            "target_workbook_handle": "phandle-target",
            "binding_output_root_handle": "phandle-output",
        },
        "target_source_authority": {
            "authority_id": "FICTIONAL_TARGET_SOURCE_AUTHORITY",
            "provenance_class": "fictional_conformance",
            "workbook_handle": "phandle-target",
            "byte_hash_permitted": False,
            "projection": _policy_document(),
        },
    }
    write_json_exclusive(registry_path, document)
    return ProtectedHandleResolver.load(registry_path, ROOT)


class Pipe02ConformanceTests(unittest.TestCase):
    def test_01_model04_resolves_and_commitment_reconciles(self):
        with tempfile.TemporaryDirectory() as temp:
            package, nonce, evidence = _write_model04(Path(temp))
            loaded = load_model04_binding(package, nonce, evidence)
            self.assertEqual(loaded.package["package_id"], "MODEL04_VALIDATION_IDENTITY_ROLE_ANCHOR_PACKAGE_V1")

    def test_02_wrong_model04_verification_material_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            package, nonce, evidence = _write_model04(Path(temp))
            nonce.write_bytes(b"X" * 32)
            with self.assertRaisesRegex(ConformanceError, "MODEL04_COMMITMENT_MISMATCH"):
                load_model04_binding(package, nonce, evidence)

    def test_03_pipe_run_resolves_exact_accepted_id(self):
        with tempfile.TemporaryDirectory() as temp:
            run_dir, commitment = _write_pipe_run(Path(temp))
            with patch.object(binding, "EXPECTED_PIPE_FREEZE_COMMITMENT", commitment):
                result = reconcile_pipe_freeze(run_dir, "phandle-run", _temporal_mapping())
            self.assertEqual(result.run_reference["run_id"], EXPECTED_PIPE_RUN_ID)

    def test_04_pipe_freeze_commitment_reconciles_exactly(self):
        with tempfile.TemporaryDirectory() as temp:
            run_dir, commitment = _write_pipe_run(Path(temp))
            with patch.object(binding, "EXPECTED_PIPE_FREEZE_COMMITMENT", commitment):
                result = reconcile_pipe_freeze(run_dir, "phandle-run", _temporal_mapping())
            self.assertEqual(result.run_reference["freeze_commitment"], commitment)

    def test_05_required_frozen_artifacts_resolve_by_manifest_hash(self):
        with tempfile.TemporaryDirectory() as temp:
            run_dir, commitment = _write_pipe_run(Path(temp))
            with patch.object(binding, "EXPECTED_PIPE_FREEZE_COMMITMENT", commitment):
                artifacts = reconcile_pipe_freeze(run_dir, "phandle-run", _temporal_mapping()).artifact_bindings[FICTIONAL_LOCATION]
            self.assertEqual(set(artifacts), {"model04_lineage", "frozen_prediction", "readiness", "geometric_completeness", "dependence_geometric_jaccard"})

    def test_06_missing_frozen_artifact_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            run_dir, commitment = _write_pipe_run(Path(temp))
            (run_dir / "artifacts/context-0001-baseline-prediction.json").unlink()
            with patch.object(binding, "EXPECTED_PIPE_FREEZE_COMMITMENT", commitment), self.assertRaisesRegex(ConformanceError, "PIPE_FROZEN_ARTIFACT_MISSING"):
                reconcile_pipe_freeze(run_dir, "phandle-run", _temporal_mapping())

    def test_07_corrupted_frozen_artifact_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            run_dir, commitment = _write_pipe_run(Path(temp))
            (run_dir / "artifacts/context-0001-eligibility-readiness.json").write_text("{}", encoding="utf-8")
            with patch.object(binding, "EXPECTED_PIPE_FREEZE_COMMITMENT", commitment), self.assertRaisesRegex(ConformanceError, "PIPE_FROZEN_ARTIFACT_HASH_MISMATCH"):
                reconcile_pipe_freeze(run_dir, "phandle-run", _temporal_mapping())

    def test_08_superseded_frozen_artifact_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            run_dir, commitment = _write_pipe_run(Path(temp))
            write_json_exclusive(run_dir / "SUPERSEDED.json", {"superseded": True})
            with patch.object(binding, "EXPECTED_PIPE_FREEZE_COMMITMENT", commitment), self.assertRaisesRegex(ConformanceError, "PIPE_RUN_SUPERSEDED"):
                reconcile_pipe_freeze(run_dir, "phandle-run", _temporal_mapping())

    def test_09_temporal_eligibility_comes_only_from_model04(self):
        with tempfile.TemporaryDirectory() as temp:
            package, nonce, evidence = _write_model04(Path(temp))
            mapping, pairs = derive_temporal_mapping(load_model04_binding(package, nonce, evidence))
            self.assertEqual(mapping[0]["role"], "TEMPORAL_VALIDATION")
            self.assertEqual([pair["vintage_year"] for pair in pairs], [2025, 2026])

    def test_10_target_source_resolves_only_by_authorized_handle(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            resolver = _registry(root, root / "registry.json")
            resolved = resolver.resolve("phandle-target", "validation_target_workbook")
            self.assertEqual(resolved.handle, "phandle-target")

    def test_11_filename_guessing_is_impossible(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            resolver = _registry(root, root / "registry.json")
            with self.assertRaisesRegex(ConformanceError, "PROTECTED_HANDLE_INVALID"):
                resolver.resolve("nondiscoverable-source.bin", "validation_target_workbook")
            self.assertFalse(hasattr(resolver, "search"))

    def test_12_permitted_lineage_and_vintage_fields_can_be_read(self):
        with tempfile.TemporaryDirectory() as temp:
            workbook = Path(temp) / "fictional.xlsx"
            _write_xlsx(workbook)
            rows, _ = project_target_addresses(workbook, MinimumTargetProjectionPolicy(_policy_document(), "phandle-target"), _requested_pairs())
            self.assertEqual(rows[0]["lineage_key"], "FICTIONAL-PRIOR")
            self.assertEqual(rows[1]["vintage_year"], 2026)

    def test_13_addresses_resolve_without_target_decoding(self):
        with tempfile.TemporaryDirectory() as temp:
            workbook = Path(temp) / "fictional.xlsx"
            _write_xlsx(workbook)
            rows, audit = project_target_addresses(workbook, MinimumTargetProjectionPolicy(_policy_document(), "phandle-target"), _requested_pairs())
            self.assertEqual([row["isolated_sales_cell_address"] for row in rows], ["C2", "C3"])
            self.assertEqual(audit.target_cells_addressed, 2)
            self.assertEqual(audit.target_payload_decode_calls, 0)

    def test_14_instrumented_target_decoder_is_never_invoked(self):
        with tempfile.TemporaryDirectory() as temp:
            workbook = Path(temp) / "fictional.xlsx"
            _write_xlsx(workbook, "TARGET-SENTINEL-ONE", "TARGET-SENTINEL-TWO")

            def poison_target(cell, strings, audit):
                if cell.target_body:
                    raise AssertionError("target decoder invoked")
                return _decode_cell_payload(cell, strings, audit)

            rows, audit = project_target_addresses(workbook, MinimumTargetProjectionPolicy(_policy_document(), "phandle-target"), _requested_pairs(), decoder=poison_target)
            self.assertNotIn("TARGET-SENTINEL", json.dumps(rows))
            self.assertEqual(audit.target_payload_decode_calls, 0)

    def test_15_impacted_sales_is_denied(self):
        policy = MinimumTargetProjectionPolicy(_policy_document(), "phandle-target")
        with self.assertRaisesRegex(ConformanceError, "TARGET_FIELD_DENIED"):
            policy.authorize(field="Impacted Sales", market="milwaukee", role="TEMPORAL_VALIDATION", quarantined=False, row_allowed=True)

    def test_16_prospective_milwaukee_holdout_is_denied(self):
        policy = MinimumTargetProjectionPolicy(_policy_document(), "phandle-target")
        with self.assertRaisesRegex(ConformanceError, "TARGET_ROLE_DENIED"):
            policy.authorize(field="isolated_sales_address", market="milwaukee", role="PROSPECTIVE_MILWAUKEE_HOLDOUT", quarantined=False, row_allowed=True)

    def test_17_madison_is_denied(self):
        policy = MinimumTargetProjectionPolicy(_policy_document(), "phandle-target")
        with self.assertRaisesRegex(ConformanceError, "TARGET_MARKET_DENIED"):
            policy.authorize(field="isolated_sales_address", market="madison", role="TEMPORAL_VALIDATION", quarantined=False, row_allowed=True)

    def test_18_ambiguous_quarantine_is_denied(self):
        policy = MinimumTargetProjectionPolicy(_policy_document(), "phandle-target")
        with self.assertRaisesRegex(ConformanceError, "TARGET_QUARANTINE_DENIED"):
            policy.authorize(field="isolated_sales_address", market="milwaukee", role="TEMPORAL_VALIDATION", quarantined=True, row_allowed=True)

    def test_19_unrelated_rows_are_denied(self):
        policy = MinimumTargetProjectionPolicy(_policy_document(), "phandle-target")
        with self.assertRaisesRegex(ConformanceError, "TARGET_ROW_DENIED"):
            policy.authorize(field="isolated_sales_address", market="milwaukee", role="TEMPORAL_VALIDATION", quarantined=False, row_allowed=False)

    def test_20_unrelated_columns_are_denied(self):
        policy = MinimumTargetProjectionPolicy(_policy_document(), "phandle-target")
        with self.assertRaisesRegex(ConformanceError, "TARGET_FIELD_DENIED"):
            policy.authorize(field="address", market="milwaukee", role="TEMPORAL_VALIDATION", quarantined=False, row_allowed=True)

    def test_21_unknown_fields_are_default_denied(self):
        policy = MinimumTargetProjectionPolicy(_policy_document(), "phandle-target")
        with self.assertRaisesRegex(ConformanceError, "TARGET_FIELD_DENIED"):
            policy.authorize(field="future_unknown_field", market="milwaukee", role="TEMPORAL_VALIDATION", quarantined=False, row_allowed=True)

    def test_22_target_values_cannot_influence_selection(self):
        with tempfile.TemporaryDirectory() as temp:
            first = Path(temp) / "first.xlsx"
            second = Path(temp) / "second.xlsx"
            _write_xlsx(first, "1", "2")
            _write_xlsx(second, "888888888", "999999999")
            policy = MinimumTargetProjectionPolicy(_policy_document(), "phandle-target")
            one, _ = project_target_addresses(first, policy, _requested_pairs())
            two, _ = project_target_addresses(second, policy, _requested_pairs())
            self.assertEqual(one, two)

    def test_23_protected_output_inside_git_is_rejected(self):
        with self.assertRaisesRegex(ConformanceError, "PROTECTED_ROOT_INSIDE_REPOSITORY"):
            ProtectedBindingRun(ROOT / ".tmp/pipe02", ROOT, binding_run_id="pbind-fictional")

    def test_24_protected_artifact_is_not_stageable_by_normal_paths(self):
        with self.assertRaisesRegex(ConformanceError, "PROTECTED_TRACKED_PATH_REJECTED"):
            assert_no_protected_tracked_paths(["results/pipe02_protected_validation_access_binding.json"])

    def test_25_interrupted_finalization_remains_incomplete(self):
        with tempfile.TemporaryDirectory() as temp:
            run = ProtectedBindingRun(Path(temp), ROOT, binding_run_id="pbind-interrupted")
            self.assertFalse(protected_binding_is_ready(run.run_dir))
            state = json.loads((run.run_dir / "binding_state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["state"], "incomplete")

    def test_26_finalized_binding_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run = ProtectedBindingRun(root, ROOT, binding_run_id="pbind-final")
            semantic = _finalizable_binding("pbind-final")
            run.finalize(semantic)
            self.assertTrue(protected_binding_is_ready(run.run_dir))
            with self.assertRaisesRegex(ConformanceError, "BINDING_ALREADY_EXISTS"):
                ProtectedBindingRun(root, ROOT, binding_run_id="pbind-final")

    def test_27_supersession_requires_new_version_and_run(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with self.assertRaisesRegex(ConformanceError, "BINDING_SUPERSESSION_VERSION_REQUIRED"):
                ProtectedBindingRun(root, ROOT, binding_run_id="pbind-v2-bad", supersedes="pbind-v1")
            correction = ProtectedBindingRun(root, ROOT, binding_run_id="pbind-v2", package_version="1.0.1", supersedes="pbind-v1")
            self.assertEqual(correction.supersedes, "pbind-v1")

    def test_28_disclosure_safe_report_excludes_protected_details(self):
        fake = binding.BindingResult("pbind-safe", "a" * 64, "pipe02-binding:sha256:" + "a" * 64, "b" * 64, Path("protected"), 1, 2, binding.TargetAccessAudit())
        report = build_disclosure_safe_result(fake)
        serialized = json.dumps(report)
        for forbidden in ("source_row", "cell_address", "nonce", "physical_location_id", "\"target_value\":", "prediction_candidate"):
            self.assertNotIn(forbidden, serialized)

    def test_29_existing_pipe_framework_is_reused(self):
        source = inspect.getsource(binding)
        self.assertIn("from sprouts_customer_geography.pipe01.canonical import", source)
        self.assertIn("from sprouts_customer_geography.pipe01.commitment import", source)
        self.assertNotIn("import hashlib", source)

    def test_30_model04_role_cannot_be_reinterpreted_from_workbook(self):
        package = _fictional_model04_package()
        package["records"][1]["evidence_role"] = "PROSPECTIVE_MILWAUKEE_HOLDOUT"
        package["protected_content_sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "model.json"
            nonce = Path(temp) / "nonce.bin"
            evidence = Path(temp) / "evidence.json"
            write_json_exclusive(path, package)
            nonce.write_bytes(b"F" * 32)
            write_json_exclusive(evidence, build_commitment_evidence(path, b"F" * 32))
            with self.assertRaises(ConformanceError):
                load_model04_binding(path, nonce, evidence)


if __name__ == "__main__":
    unittest.main()
