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
from sprouts_customer_geography.pipe01.orchestration import Model04Binding, load_model04_binding, load_repository_authorities
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
    execute_protected_binding,
    protected_binding_is_ready,
    reconcile_pipe_freeze,
)
from sprouts_customer_geography.pipe02.resolver import (
    CURRENT_2026_TEMPORAL_SOURCE,
    PRIOR_VINTAGE_TEMPORAL_SOURCE,
    ProtectedHandleResolver,
)
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


def _policy_document(source_role: str, workbook_handle: str) -> dict:
    document = {
        "projection_id": "MODEL07_MINIMUM_TEMPORAL_TARGET_PROJECTION_V1",
        "version": "1.0.0",
        "source_role": source_role,
        "workbook_handle": workbook_handle,
        "default_deny": True,
        "allowed_market": "milwaukee",
        "allowed_role": "TEMPORAL_VALIDATION",
        "permitted_pair_role": "most_recent_eligible_prior" if source_role == PRIOR_VINTAGE_TEMPORAL_SOURCE else "corresponding_2026",
        "sheet_name": "Authorized Projection",
        "header_row": 1,
        "columns": {"lineage_key": "A", "forecast_vintage": "B", "isolated_sales": "C"},
        "headers": {"lineage_key": "Lineage Key", "forecast_vintage": "Forecast Vintage", "isolated_sales": "Isolated Sales"},
        "model04_lineage_field": "source_seed_point_id",
    }
    if source_role == PRIOR_VINTAGE_TEMPORAL_SOURCE:
        document["vintage_rule"] = "MOST_RECENT_ELIGIBLE_PRIOR_TO_2026"
    else:
        document["target_year"] = 2026
    return document


def _write_xlsx(path: Path, source_role: str, target_value: str = "111111", *, lineage_override: str | None = None) -> None:
    workbook = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Authorized Projection" sheetId="1" r:id="rId1"/></sheets></workbook>"""
    relationships = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>"""
    if source_role == PRIOR_VINTAGE_TEMPORAL_SOURCE:
        lineage, vintage, unrelated_lineage, unrelated_vintage = "FICTIONAL-PRIOR", 2025, "FICTIONAL-CURRENT", 2026
    else:
        lineage, vintage, unrelated_lineage, unrelated_vintage = "FICTIONAL-CURRENT", 2026, "FICTIONAL-PRIOR", 2025
    lineage = lineage_override or lineage
    sheet = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>
<row r="1"><c r="A1" t="inlineStr"><is><t>Lineage Key</t></is></c><c r="B1" t="inlineStr"><is><t>Forecast Vintage</t></is></c><c r="C1" t="inlineStr"><is><t>Isolated Sales</t></is></c><c r="D1" t="inlineStr"><is><t>Impacted Sales</t></is></c></row>
<row r="2"><c r="A2" t="inlineStr"><is><t>{lineage}</t></is></c><c r="B2" t="n"><v>{vintage}</v></c><c r="C2" t="n"><v>{target_value}</v></c><c r="D2" t="n"><v>333333</v></c></row>
<row r="3"><c r="A3" t="inlineStr"><is><t>{unrelated_lineage}</t></is></c><c r="B3" t="n"><v>{unrelated_vintage}</v></c><c r="C3" t="n"><v>777777</v></c><c r="D3" t="n"><v>444444</v></c></row>
<row r="4"><c r="A4" t="inlineStr"><is><t>UNRELATED-HOLDOUT</t></is></c><c r="B4" t="n"><v>2026</v></c><c r="C4" t="n"><v>999999</v></c></row>
</sheetData></worksheet>"""
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", relationships)
        archive.writestr("xl/worksheets/sheet1.xml", sheet)


def _requested_pairs(source_role: str) -> list[dict]:
    if source_role == PRIOR_VINTAGE_TEMPORAL_SOURCE:
        return [{"source_role": source_role, "pair_role": "most_recent_eligible_prior", "physical_location_id": FICTIONAL_LOCATION, "lineage_key": "FICTIONAL-PRIOR", "vintage_year": 2025}]
    return [{"source_role": source_role, "pair_role": "corresponding_2026", "physical_location_id": FICTIONAL_LOCATION, "lineage_key": "FICTIONAL-CURRENT", "vintage_year": 2026}]


def _policy(source_role: str) -> MinimumTargetProjectionPolicy:
    handle = "phandle-prior-target" if source_role == PRIOR_VINTAGE_TEMPORAL_SOURCE else "phandle-current-target"
    return MinimumTargetProjectionPolicy(_policy_document(source_role, handle), handle, source_role)


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
        "$schema": "pipe02-protected-validation-access-binding-v1.1",
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
        "target_source_authorities": [
            {"source_role": PRIOR_VINTAGE_TEMPORAL_SOURCE, "authority_id": "FICTIONAL_PRIOR_AUTHORITY", "provenance_class": "fictional", "workbook_handle": "phandle-prior-target", "whole_workbook_hash_computed": False, "sheet_name": "Authorized Projection"},
            {"source_role": CURRENT_2026_TEMPORAL_SOURCE, "authority_id": "FICTIONAL_CURRENT_AUTHORITY", "provenance_class": "fictional", "workbook_handle": "phandle-current-target", "whole_workbook_hash_computed": False, "sheet_name": "Authorized Projection"},
        ],
        "temporal_eligibility_mapping": [{"physical_location_id": FICTIONAL_LOCATION}],
        "minimum_target_projection": {
            "projection_id": "MODEL07_MINIMUM_TEMPORAL_TARGET_PROJECTION_V1",
            "version": "1.0.0",
            "default_deny": True,
            "source_projections": [
                {"source_role": PRIOR_VINTAGE_TEMPORAL_SOURCE, "workbook_handle": "phandle-prior-target", "projection_id": "MODEL07_MINIMUM_TEMPORAL_TARGET_PROJECTION_V1", "version": "1.0.0", "permitted_pair_role": "most_recent_eligible_prior", "sheet_name": "Authorized Projection", "allowed_fields": ["lineage_key", "forecast_vintage", "isolated_sales_address"], "denied_scope": ["default-deny"]},
                {"source_role": CURRENT_2026_TEMPORAL_SOURCE, "workbook_handle": "phandle-current-target", "projection_id": "MODEL07_MINIMUM_TEMPORAL_TARGET_PROJECTION_V1", "version": "1.0.0", "permitted_pair_role": "corresponding_2026", "sheet_name": "Authorized Projection", "allowed_fields": ["lineage_key", "forecast_vintage", "isolated_sales_address"], "denied_scope": ["default-deny"]},
            ],
            "target_cells": [{"physical_location_id": FICTIONAL_LOCATION, "prior": {"source_role": PRIOR_VINTAGE_TEMPORAL_SOURCE, "isolated_sales_cell_address": "C2"}, "current_2026": {"source_role": CURRENT_2026_TEMPORAL_SOURCE, "isolated_sales_cell_address": "C2"}}],
            "target_access_audits": {
                PRIOR_VINTAGE_TEMPORAL_SOURCE: {"target_payload_decode_calls": 0, "target_values_materialized": False},
                CURRENT_2026_TEMPORAL_SOURCE: {"target_payload_decode_calls": 0, "target_values_materialized": False},
            },
        },
        "protected_handle_registry_identity": "fictional-registry",
        "finalization": {"mandatory_reconciliations_passed": True, "target_values_accessed": False, "ready_marker_written_last": True},
        "supersedes": supersedes,
        "supersession_policy": "fictional immutable fixture",
    }


def _registry(root: Path, registry_path: Path) -> ProtectedHandleResolver:
    output = root / "output"
    output.mkdir()
    prior_target = root / "nondiscoverable-prior-source.bin"
    prior_target.write_bytes(b"fixture")
    current_target = root / "nondiscoverable-current-source.bin"
    current_target.write_bytes(b"fixture")
    run = root / "run"
    run.mkdir()
    model = root / "model.json"
    model.write_text("{}", encoding="utf-8")
    nonce = root / "nonce.bin"
    nonce.write_bytes(b"F" * 32)
    document = {
        "registry_id": "PIPE02_PROTECTED_HANDLE_REGISTRY_V1",
        "version": "1.1.0",
        "protected_roots": {"proot-fictional": str(root)},
        "resources": {
            "phandle-output": {"kind": "pipe02_output_root", "root_handle": "proot-fictional", "relative_path": "output"},
            "phandle-prior-target": {"kind": "prior_vintage_temporal_workbook", "root_handle": "proot-fictional", "relative_path": "nondiscoverable-prior-source.bin"},
            "phandle-current-target": {"kind": "current_2026_temporal_workbook", "root_handle": "proot-fictional", "relative_path": "nondiscoverable-current-source.bin"},
            "phandle-run": {"kind": "pipe01_run_directory", "root_handle": "proot-fictional", "relative_path": "run"},
            "phandle-model": {"kind": "model04_package", "root_handle": "proot-fictional", "relative_path": "model.json"},
            "phandle-verification": {"kind": "model04_verification_material", "root_handle": "proot-fictional", "relative_path": "nonce.bin"},
        },
        "binding_request": {
            "model04_package_handle": "phandle-model",
            "model04_verification_material_handle": "phandle-verification",
            "pipe01_run_directory_handle": "phandle-run",
            "prior_vintage_target_workbook_handle": "phandle-prior-target",
            "current_2026_target_workbook_handle": "phandle-current-target",
            "binding_output_root_handle": "phandle-output",
        },
        "target_source_authorities": [
            {
                "source_role": PRIOR_VINTAGE_TEMPORAL_SOURCE,
                "authority_id": "FICTIONAL_PRIOR_TARGET_SOURCE_AUTHORITY",
                "provenance_class": "fictional_prior_conformance",
                "workbook_handle": "phandle-prior-target",
                "byte_hash_permitted": False,
                "projection": _policy_document(PRIOR_VINTAGE_TEMPORAL_SOURCE, "phandle-prior-target"),
            },
            {
                "source_role": CURRENT_2026_TEMPORAL_SOURCE,
                "authority_id": "FICTIONAL_CURRENT_TARGET_SOURCE_AUTHORITY",
                "provenance_class": "fictional_current_conformance",
                "workbook_handle": "phandle-current-target",
                "byte_hash_permitted": False,
                "projection": _policy_document(CURRENT_2026_TEMPORAL_SOURCE, "phandle-current-target"),
            },
        ],
    }
    write_json_exclusive(registry_path, document)
    return ProtectedHandleResolver.load(registry_path, ROOT)


def _write_fictional_e2e_fixture(
    outer: Path,
    *,
    prior_value: str = "111111",
    current_value: str = "222222",
    current_lineage: str | None = None,
) -> tuple[Path, ProtectedHandleResolver, str, str]:
    repository = outer / "fictional-repository"
    protected = outer / "fictional-protected"
    repository.mkdir()
    protected.mkdir()
    output = protected / "output"
    output.mkdir()
    model04_package, model04_nonce, model04_evidence = _write_model04(protected)
    commitment_path = repository / "config/model/model04_validation_identity_role_anchor_commitment.json"
    commitment_path.parent.mkdir(parents=True)
    write_json_exclusive(commitment_path, json.loads(model04_evidence.read_text(encoding="utf-8")))
    model04_commitment = json.loads(model04_evidence.read_text(encoding="utf-8"))["commitment_sha256"]
    pipe_run, pipe_commitment = _write_pipe_run(protected / "pipe")
    prior_workbook = protected / "fictional-prior.xlsx"
    current_workbook = protected / "fictional-current.xlsx"
    _write_xlsx(prior_workbook, PRIOR_VINTAGE_TEMPORAL_SOURCE, prior_value)
    _write_xlsx(current_workbook, CURRENT_2026_TEMPORAL_SOURCE, current_value, lineage_override=current_lineage)
    document = {
        "registry_id": "PIPE02_PROTECTED_HANDLE_REGISTRY_V1",
        "version": "1.1.0",
        "protected_roots": {"proot-fictional-e2e": str(protected)},
        "resources": {
            "phandle-output": {"kind": "pipe02_output_root", "root_handle": "proot-fictional-e2e", "relative_path": "output"},
            "phandle-prior-target": {"kind": "prior_vintage_temporal_workbook", "root_handle": "proot-fictional-e2e", "relative_path": prior_workbook.name},
            "phandle-current-target": {"kind": "current_2026_temporal_workbook", "root_handle": "proot-fictional-e2e", "relative_path": current_workbook.name},
            "phandle-run": {"kind": "pipe01_run_directory", "root_handle": "proot-fictional-e2e", "relative_path": f"pipe/runs/{pipe_run.name}"},
            "phandle-model": {"kind": "model04_package", "root_handle": "proot-fictional-e2e", "relative_path": model04_package.name},
            "phandle-verification": {"kind": "model04_verification_material", "root_handle": "proot-fictional-e2e", "relative_path": model04_nonce.name},
        },
        "binding_request": {
            "model04_package_handle": "phandle-model",
            "model04_verification_material_handle": "phandle-verification",
            "pipe01_run_directory_handle": "phandle-run",
            "prior_vintage_target_workbook_handle": "phandle-prior-target",
            "current_2026_target_workbook_handle": "phandle-current-target",
            "binding_output_root_handle": "phandle-output",
        },
        "target_source_authorities": [
            {
                "source_role": PRIOR_VINTAGE_TEMPORAL_SOURCE,
                "authority_id": "FICTIONAL_PRIOR_TARGET_SOURCE_AUTHORITY",
                "provenance_class": "fictional_prior_conformance",
                "workbook_handle": "phandle-prior-target",
                "byte_hash_permitted": False,
                "projection": _policy_document(PRIOR_VINTAGE_TEMPORAL_SOURCE, "phandle-prior-target"),
            },
            {
                "source_role": CURRENT_2026_TEMPORAL_SOURCE,
                "authority_id": "FICTIONAL_CURRENT_TARGET_SOURCE_AUTHORITY",
                "provenance_class": "fictional_current_conformance",
                "workbook_handle": "phandle-current-target",
                "byte_hash_permitted": False,
                "projection": _policy_document(CURRENT_2026_TEMPORAL_SOURCE, "phandle-current-target"),
            },
        ],
    }
    registry_path = protected / "registry.json"
    write_json_exclusive(registry_path, document)
    return repository, ProtectedHandleResolver.load(registry_path, repository), model04_commitment, pipe_commitment


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
            self.assertEqual(pairs[PRIOR_VINTAGE_TEMPORAL_SOURCE][0]["vintage_year"], 2025)
            self.assertEqual(pairs[CURRENT_2026_TEMPORAL_SOURCE][0]["vintage_year"], 2026)

    def test_10_target_source_resolves_only_by_authorized_handle(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            resolver = _registry(root, root / "registry.json")
            prior = resolver.resolve("phandle-prior-target", "prior_vintage_temporal_workbook")
            current = resolver.resolve("phandle-current-target", "current_2026_temporal_workbook")
            self.assertEqual(prior.handle, "phandle-prior-target")
            self.assertEqual(current.handle, "phandle-current-target")
            self.assertNotEqual(prior.path, current.path)

    def test_11_filename_guessing_is_impossible(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            resolver = _registry(root, root / "registry.json")
            with self.assertRaisesRegex(ConformanceError, "PROTECTED_HANDLE_INVALID"):
                resolver.resolve("nondiscoverable-prior-source.bin", "prior_vintage_temporal_workbook")
            self.assertFalse(hasattr(resolver, "search"))

    def test_12_permitted_lineage_and_vintage_fields_can_be_read(self):
        with tempfile.TemporaryDirectory() as temp:
            for role, lineage, year in (
                (PRIOR_VINTAGE_TEMPORAL_SOURCE, "FICTIONAL-PRIOR", 2025),
                (CURRENT_2026_TEMPORAL_SOURCE, "FICTIONAL-CURRENT", 2026),
            ):
                workbook = Path(temp) / f"{role}.xlsx"
                _write_xlsx(workbook, role)
                rows, _ = project_target_addresses(workbook, _policy(role), _requested_pairs(role))
                self.assertEqual(rows[0]["lineage_key"], lineage)
                self.assertEqual(rows[0]["vintage_year"], year)

    def test_13_addresses_resolve_without_target_decoding(self):
        with tempfile.TemporaryDirectory() as temp:
            for role in (PRIOR_VINTAGE_TEMPORAL_SOURCE, CURRENT_2026_TEMPORAL_SOURCE):
                workbook = Path(temp) / f"{role}.xlsx"
                _write_xlsx(workbook, role)
                rows, audit = project_target_addresses(workbook, _policy(role), _requested_pairs(role))
                self.assertEqual(rows[0]["isolated_sales_cell_address"], "C2")
                self.assertEqual(audit.target_cells_addressed, 1)
                self.assertEqual(audit.target_payload_decode_calls, 0)

    def test_14_instrumented_target_decoder_is_never_invoked(self):
        with tempfile.TemporaryDirectory() as temp:
            def poison_target(cell, strings, audit):
                if cell.target_body:
                    raise AssertionError("target decoder invoked")
                return _decode_cell_payload(cell, strings, audit)

            for role in (PRIOR_VINTAGE_TEMPORAL_SOURCE, CURRENT_2026_TEMPORAL_SOURCE):
                workbook = Path(temp) / f"{role}.xlsx"
                _write_xlsx(workbook, role, f"TARGET-SENTINEL-{role}")
                rows, audit = project_target_addresses(workbook, _policy(role), _requested_pairs(role), decoder=poison_target)
                self.assertNotIn("TARGET-SENTINEL", json.dumps(rows))
                self.assertEqual(audit.target_payload_decode_calls, 0)

    def test_15_impacted_sales_is_denied(self):
        for source_role in (PRIOR_VINTAGE_TEMPORAL_SOURCE, CURRENT_2026_TEMPORAL_SOURCE):
            with self.assertRaisesRegex(ConformanceError, "TARGET_FIELD_DENIED"):
                _policy(source_role).authorize(field="Impacted Sales", market="milwaukee", role="TEMPORAL_VALIDATION", quarantined=False, row_allowed=True)

    def test_16_prospective_milwaukee_holdout_is_denied(self):
        for source_role in (PRIOR_VINTAGE_TEMPORAL_SOURCE, CURRENT_2026_TEMPORAL_SOURCE):
            with self.assertRaisesRegex(ConformanceError, "TARGET_ROLE_DENIED"):
                _policy(source_role).authorize(field="isolated_sales_address", market="milwaukee", role="PROSPECTIVE_MILWAUKEE_HOLDOUT", quarantined=False, row_allowed=True)

    def test_17_madison_is_denied(self):
        for source_role in (PRIOR_VINTAGE_TEMPORAL_SOURCE, CURRENT_2026_TEMPORAL_SOURCE):
            with self.assertRaisesRegex(ConformanceError, "TARGET_MARKET_DENIED"):
                _policy(source_role).authorize(field="isolated_sales_address", market="madison", role="TEMPORAL_VALIDATION", quarantined=False, row_allowed=True)

    def test_18_ambiguous_quarantine_is_denied(self):
        for source_role in (PRIOR_VINTAGE_TEMPORAL_SOURCE, CURRENT_2026_TEMPORAL_SOURCE):
            with self.assertRaisesRegex(ConformanceError, "TARGET_QUARANTINE_DENIED"):
                _policy(source_role).authorize(field="isolated_sales_address", market="milwaukee", role="TEMPORAL_VALIDATION", quarantined=True, row_allowed=True)

    def test_19_unrelated_rows_are_denied(self):
        for source_role in (PRIOR_VINTAGE_TEMPORAL_SOURCE, CURRENT_2026_TEMPORAL_SOURCE):
            with self.assertRaisesRegex(ConformanceError, "TARGET_ROW_DENIED"):
                _policy(source_role).authorize(field="isolated_sales_address", market="milwaukee", role="TEMPORAL_VALIDATION", quarantined=False, row_allowed=False)

    def test_20_unrelated_columns_are_denied(self):
        for source_role in (PRIOR_VINTAGE_TEMPORAL_SOURCE, CURRENT_2026_TEMPORAL_SOURCE):
            with self.assertRaisesRegex(ConformanceError, "TARGET_FIELD_DENIED"):
                _policy(source_role).authorize(field="address", market="milwaukee", role="TEMPORAL_VALIDATION", quarantined=False, row_allowed=True)

    def test_21_unknown_fields_are_default_denied(self):
        for source_role in (PRIOR_VINTAGE_TEMPORAL_SOURCE, CURRENT_2026_TEMPORAL_SOURCE):
            with self.assertRaisesRegex(ConformanceError, "TARGET_FIELD_DENIED"):
                _policy(source_role).authorize(field="future_unknown_field", market="milwaukee", role="TEMPORAL_VALIDATION", quarantined=False, row_allowed=True)

    def test_22_target_values_cannot_influence_selection(self):
        with tempfile.TemporaryDirectory() as temp:
            for role in (PRIOR_VINTAGE_TEMPORAL_SOURCE, CURRENT_2026_TEMPORAL_SOURCE):
                first = Path(temp) / f"first-{role}.xlsx"
                second = Path(temp) / f"second-{role}.xlsx"
                _write_xlsx(first, role, "1")
                _write_xlsx(second, role, "999999999")
                one, _ = project_target_addresses(first, _policy(role), _requested_pairs(role))
                two, _ = project_target_addresses(second, _policy(role), _requested_pairs(role))
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
        fake = binding.BindingResult(
            "pbind-safe",
            "a" * 64,
            "pipe02-binding:sha256:" + "a" * 64,
            "b" * 64,
            Path("protected"),
            1,
            2,
            {
                PRIOR_VINTAGE_TEMPORAL_SOURCE: binding.TargetAccessAudit(),
                CURRENT_2026_TEMPORAL_SOURCE: binding.TargetAccessAudit(),
            },
        )
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

    def test_31_request_and_schemas_require_exact_dual_source_roles(self):
        registry_schema = json.loads((ROOT / "schemas/pipe02/protected_handle_registry.schema.json").read_text(encoding="utf-8"))
        binding_schema = json.loads((ROOT / "schemas/pipe02/protected_validation_access_binding.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(registry_schema["properties"]["version"]["const"], "1.1.0")
        self.assertIn("target_source_authorities", registry_schema["required"])
        self.assertNotIn("target_source_authority", registry_schema["properties"])
        self.assertIn("target_source_authorities", binding_schema["required"])
        self.assertEqual(binding_schema["properties"]["$schema"]["const"], "pipe02-protected-validation-access-binding-v1.1")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _registry(root, root / "registry.json")
            document = json.loads((root / "registry.json").read_text(encoding="utf-8"))
            document["target_source_authority"] = document.pop("target_source_authorities")[0]
            bad = root / "single-source-registry.json"
            write_json_exclusive(bad, document)
            with self.assertRaisesRegex(ConformanceError, "SINGLE_TARGET_SOURCE_CONTRACT_REJECTED"):
                ProtectedHandleResolver.load(bad, ROOT)

    def test_32_missing_prior_vintage_source_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _registry(root, root / "registry.json")
            document = json.loads((root / "registry.json").read_text(encoding="utf-8"))
            document["target_source_authorities"] = [document["target_source_authorities"][1]]
            bad = root / "missing-prior.json"
            write_json_exclusive(bad, document)
            with self.assertRaisesRegex(ConformanceError, "TARGET_SOURCE_ROLES_INCOMPLETE"):
                ProtectedHandleResolver.load(bad, ROOT)

    def test_32a_missing_prior_vintage_request_handle_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _registry(root, root / "registry.json")
            document = json.loads((root / "registry.json").read_text(encoding="utf-8"))
            document["binding_request"].pop("prior_vintage_target_workbook_handle")
            bad = root / "missing-prior-request.json"
            write_json_exclusive(bad, document)
            with self.assertRaisesRegex(ConformanceError, "BINDING_REQUEST_INVALID"):
                ProtectedHandleResolver.load(bad, ROOT)

    def test_33_missing_2026_source_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _registry(root, root / "registry.json")
            document = json.loads((root / "registry.json").read_text(encoding="utf-8"))
            document["target_source_authorities"] = [document["target_source_authorities"][0]]
            bad = root / "missing-current.json"
            write_json_exclusive(bad, document)
            with self.assertRaisesRegex(ConformanceError, "TARGET_SOURCE_ROLES_INCOMPLETE"):
                ProtectedHandleResolver.load(bad, ROOT)

    def test_34_duplicate_source_role_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _registry(root, root / "registry.json")
            document = json.loads((root / "registry.json").read_text(encoding="utf-8"))
            document["target_source_authorities"][1]["source_role"] = PRIOR_VINTAGE_TEMPORAL_SOURCE
            bad = root / "duplicate-role.json"
            write_json_exclusive(bad, document)
            with self.assertRaisesRegex(ConformanceError, "TARGET_SOURCE_ROLE_DUPLICATE"):
                ProtectedHandleResolver.load(bad, ROOT)

    def test_35_unknown_source_role_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _registry(root, root / "registry.json")
            document = json.loads((root / "registry.json").read_text(encoding="utf-8"))
            document["target_source_authorities"][1]["source_role"] = "UNKNOWN_TEMPORAL_SOURCE"
            bad = root / "unknown-role.json"
            write_json_exclusive(bad, document)
            with self.assertRaisesRegex(ConformanceError, "TARGET_SOURCE_ROLE_UNKNOWN"):
                ProtectedHandleResolver.load(bad, ROOT)

    def test_36_swapped_or_misbound_source_roles_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            resolver = _registry(root, root / "registry.json")
            with self.assertRaisesRegex(ConformanceError, "PROTECTED_HANDLE_KIND_MISMATCH"):
                resolver.resolve("phandle-current-target", "prior_vintage_temporal_workbook")
            with self.assertRaisesRegex(ConformanceError, "PROTECTED_HANDLE_KIND_MISMATCH"):
                resolver.resolve("phandle-prior-target", "current_2026_temporal_workbook")
            document = json.loads((root / "registry.json").read_text(encoding="utf-8"))
            document["binding_request"]["prior_vintage_target_workbook_handle"] = "phandle-current-target"
            document["binding_request"]["current_2026_target_workbook_handle"] = "phandle-prior-target"
            swapped = root / "swapped-request.json"
            write_json_exclusive(swapped, document)
            with self.assertRaisesRegex(ConformanceError, "TARGET_SOURCE_HANDLE_MISMATCH"):
                ProtectedHandleResolver.load(swapped, ROOT)
        with self.assertRaisesRegex(ConformanceError, "TARGET_SOURCE_ROLE_MISMATCH"):
            MinimumTargetProjectionPolicy(
                _policy_document(PRIOR_VINTAGE_TEMPORAL_SOURCE, "phandle-prior-target"),
                "phandle-prior-target",
                CURRENT_2026_TEMPORAL_SOURCE,
            )

    def test_36a_one_handle_cannot_satisfy_both_source_roles(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _registry(root, root / "registry.json")
            document = json.loads((root / "registry.json").read_text(encoding="utf-8"))
            document["target_source_authorities"][1]["workbook_handle"] = "phandle-prior-target"
            bad = root / "reused-handle.json"
            write_json_exclusive(bad, document)
            with self.assertRaisesRegex(ConformanceError, "TARGET_SOURCE_HANDLE_REUSED"):
                ProtectedHandleResolver.load(bad, ROOT)

    def test_37_each_isolated_sales_projection_is_role_scoped(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            prior = root / "prior.xlsx"
            current = root / "current.xlsx"
            _write_xlsx(prior, PRIOR_VINTAGE_TEMPORAL_SOURCE)
            _write_xlsx(current, CURRENT_2026_TEMPORAL_SOURCE)
            with self.assertRaisesRegex(ConformanceError, "TARGET_SOURCE_ROLE_MISMATCH"):
                project_target_addresses(prior, _policy(PRIOR_VINTAGE_TEMPORAL_SOURCE), _requested_pairs(CURRENT_2026_TEMPORAL_SOURCE))
            with self.assertRaisesRegex(ConformanceError, "TARGET_SOURCE_ROLE_MISMATCH"):
                project_target_addresses(current, _policy(CURRENT_2026_TEMPORAL_SOURCE), _requested_pairs(PRIOR_VINTAGE_TEMPORAL_SOURCE))

    def test_38_prior_selection_uses_only_model04_vintage_evidence(self):
        package = _fictional_model04_package()
        prior_2024 = _model04_record(
            year=2024,
            seed="FICTIONAL-OLDER-PRIOR",
            role="DEVELOPMENT_REFERENCE",
            source_identity="FICTIONAL_OLDER_DEVELOPMENT_REFERENCE",
            state="GENUINELY_NEW_LOCATION",
        )
        package["records"].insert(0, prior_2024)
        mapping, requested = derive_temporal_mapping(Model04Binding(package, "fictional", {}))
        self.assertEqual(mapping[0]["prior"]["vintage_year"], 2025)
        self.assertEqual(requested[PRIOR_VINTAGE_TEMPORAL_SOURCE][0]["lineage_key"], "FICTIONAL-PRIOR")

    def test_39_pairing_basis_is_frozen_model04_lineage_only(self):
        model = Model04Binding(_fictional_model04_package(), "fictional", {})
        mapping, requested = derive_temporal_mapping(model)
        self.assertEqual(requested[PRIOR_VINTAGE_TEMPORAL_SOURCE][0]["physical_location_id"], mapping[0]["physical_location_id"])
        self.assertEqual(requested[CURRENT_2026_TEMPORAL_SOURCE][0]["physical_location_id"], mapping[0]["physical_location_id"])
        serialized = json.dumps(requested, sort_keys=True)
        for forbidden in ("target_value", "isolated_sales", "impacted_sales"):
            self.assertNotIn(forbidden, serialized.lower())

    def test_40_target_values_cannot_influence_cross_source_pairing(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            combined = []
            mutated = []
            for role in (PRIOR_VINTAGE_TEMPORAL_SOURCE, CURRENT_2026_TEMPORAL_SOURCE):
                first = root / f"first-{role}.xlsx"
                second = root / f"second-{role}.xlsx"
                _write_xlsx(first, role, "101")
                _write_xlsx(second, role, "909090909")
                combined.extend(project_target_addresses(first, _policy(role), _requested_pairs(role))[0])
                mutated.extend(project_target_addresses(second, _policy(role), _requested_pairs(role))[0])
            self.assertEqual(combined, mutated)
            self.assertEqual({item["physical_location_id"] for item in combined}, {FICTIONAL_LOCATION})

    def test_41_failure_to_establish_one_to_one_pairing_fails_closed(self):
        authorities = load_repository_authorities(ROOT)
        with tempfile.TemporaryDirectory() as temp:
            repository, resolver, model_commitment, pipe_commitment = _write_fictional_e2e_fixture(
                Path(temp), current_lineage="FICTIONAL-UNMATCHED-CURRENT"
            )
            with (
                patch.object(binding, "EXPECTED_MODEL04_COMMITMENT", model_commitment),
                patch.object(binding, "EXPECTED_PIPE_FREEZE_COMMITMENT", pipe_commitment),
                patch.object(binding, "load_repository_authorities", return_value=authorities),
                self.assertRaisesRegex(ConformanceError, "TARGET_LINEAGE_PAIR_UNRESOLVED"),
            ):
                execute_protected_binding(repository_root=repository, resolver=resolver, binding_run_id="pbind-fictional-unmatched")

    def test_42_immutable_binding_identity_incorporates_both_authorities(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first_root = root / "first"
            second_root = root / "second"
            first_root.mkdir()
            second_root.mkdir()
            first_semantic = _finalizable_binding("pbind-same")
            second_semantic = copy.deepcopy(first_semantic)
            second_semantic["target_source_authorities"][1]["authority_id"] = "FICTIONAL_CURRENT_AUTHORITY_CHANGED"
            first = ProtectedBindingRun(first_root, ROOT, binding_run_id="pbind-same").finalize(first_semantic)
            second = ProtectedBindingRun(second_root, ROOT, binding_run_id="pbind-same").finalize(second_semantic)
            self.assertNotEqual(first["stable_binding_identity"], second["stable_binding_identity"])

    def test_43_fictional_two_workbook_end_to_end_finalization(self):
        authorities = load_repository_authorities(ROOT)
        with tempfile.TemporaryDirectory() as temp:
            repository, resolver, model_commitment, pipe_commitment = _write_fictional_e2e_fixture(Path(temp))
            with (
                patch.object(binding, "EXPECTED_MODEL04_COMMITMENT", model_commitment),
                patch.object(binding, "EXPECTED_PIPE_FREEZE_COMMITMENT", pipe_commitment),
                patch.object(binding, "load_repository_authorities", return_value=authorities),
            ):
                result = execute_protected_binding(repository_root=repository, resolver=resolver, binding_run_id="pbind-fictional-e2e")
            self.assertTrue(protected_binding_is_ready(result.run_dir))
            self.assertEqual(result.temporal_location_count, 1)
            self.assertEqual(result.target_address_count, 2)
            self.assertEqual(set(result.target_access_audits), {PRIOR_VINTAGE_TEMPORAL_SOURCE, CURRENT_2026_TEMPORAL_SOURCE})
            self.assertTrue(all(audit.target_payload_decode_calls == 0 for audit in result.target_access_audits.values()))
            package = json.loads((result.run_dir / "pipe02_protected_validation_access_binding.json").read_text(encoding="utf-8"))
            self.assertEqual({item["source_role"] for item in package["target_source_authorities"]}, {PRIOR_VINTAGE_TEMPORAL_SOURCE, CURRENT_2026_TEMPORAL_SOURCE})
            self.assertEqual({item["provenance_class"] for item in package["target_source_authorities"]}, {"fictional_prior_conformance", "fictional_current_conformance"})
            self.assertEqual(package["minimum_target_projection"]["target_cells"][0]["prior"]["source_role"], PRIOR_VINTAGE_TEMPORAL_SOURCE)
            self.assertEqual(package["minimum_target_projection"]["target_cells"][0]["current_2026"]["source_role"], CURRENT_2026_TEMPORAL_SOURCE)
            self.assertFalse(package["finalization"]["target_values_accessed"])


if __name__ == "__main__":
    unittest.main()
