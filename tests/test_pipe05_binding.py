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

from sprouts_customer_geography.model12.resolver import resolve_exact_basename
from sprouts_customer_geography.pipe01.canonical import content_digest, file_sha256
from sprouts_customer_geography.pipe01.commitment import freeze_commitment
from sprouts_customer_geography.pipe01.errors import ConformanceError
from sprouts_customer_geography.pipe01.safeguards import assert_no_protected_tracked_paths
from sprouts_customer_geography.pipe05 import binding, cli
from sprouts_customer_geography.pipe05.binding import (
    ProtectedBindingRun,
    _verify_stage,
    build_disclosure_safe_result,
    build_repository_execution_commitment,
    derive_target_binding_cohort,
    execute_protected_binding,
    protected_binding_is_ready,
    validate_semantic_package,
    verify_persisted_binding,
)
from sprouts_customer_geography.pipe05.contract import verify_repository_authority
from sprouts_customer_geography.pipe05.resolver import ProtectedHandleResolver, load_authorized_registry
from sprouts_customer_geography.pipe05.xlsx_projection import MichiganIsolatedSalesProjectionPolicy, TargetAccessAudit, inspect_minimum_projection_authority, project_authorized_isolated_sales


ROOT = Path(__file__).resolve().parents[1]


def _inline(column: str, row: int, value: str) -> str:
    return f'<c r="{column}{row}" t="inlineStr"><is><t>{value}</t></is></c>'


def _number(column: str, row: int, value: str) -> str:
    return f'<c r="{column}{row}"><v>{value}</v></c>'


def _write_xlsx(
    path: Path,
    rows: list[dict],
    *,
    add_unexpected: bool = False,
    second_seed_override: str | None = None,
    second_vintage_override: str | None = None,
) -> None:
    header_values = ["Year", "Seed Point ID", "Address", "City", "State", "ZIP", "Latitude", "Longitude", "Market"]
    header = "".join(_inline(chr(ord("A") + index), 1, value) for index, value in enumerate(header_values))
    header += _inline("J", 1, "Isolated Sales") + _inline("K", 1, "Impacted Sales") + _inline("L", 1, "Unrelated Forecast")
    xml_rows = ['<row r="1">' + header + "</row>"]
    for index, row in enumerate(rows):
        number = int(row["source_observation_lineage"]["source_projection_row"])
        seed = str(row["source_observation_lineage"]["source_seed_point_id"])
        vintage = f"Forecast {row['forecast_vintage']}"
        if index == 1 and second_seed_override is not None:
            seed = second_seed_override
        if index == 1 and second_vintage_override is not None:
            vintage = second_vintage_override
        identity = _inline("A", number, vintage) + _inline("B", number, seed) + _inline("E", number, "MI")
        if row.get("quarantined"):
            target = _inline("J", number, "FORBIDDEN-QUARANTINED-TARGET")
        elif row.get("fictional_target_kind") == "missing":
            target = ""
        elif row.get("fictional_target_kind") == "invalid":
            target = _inline("J", number, "FICTIONAL-INVALID")
        else:
            target = _number("J", number, str(row.get("fictional_target", number * 1.25)))
        denied = _inline("K", number, "FORBIDDEN-IMPACTED") + _inline("L", number, "FORBIDDEN-OTHER")
        xml_rows.append(f'<row r="{number}">{identity}{target}{denied}</row>')
    if add_unexpected:
        xml_rows.append('<row r="999">' + _inline("A", 999, "Forecast 2026") + _inline("B", 999, "UNEXPECTED") + _number("J", 999, "1") + "</row>")
    worksheet = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>' + "".join(xml_rows) + "</sheetData></worksheet>"
    workbook = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets></workbook>'
    relationships = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>'
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", relationships)
        archive.writestr("xl/worksheets/sheet1.xml", worksheet)


def _identity_package() -> dict:
    observations: list[dict] = []
    locations: list[dict] = []
    observation_index = 0
    for location_index in range(86):
        member_count = 2 if location_index < 53 else 1
        quarantined = location_index == 85
        physical_id = ("m12qloc-" if quarantined else "m12loc-") + f"fictional-{location_index:03d}"
        member_ids: list[str] = []
        vintages: set[int] = set()
        markets: set[str] = set()
        for _member in range(member_count):
            vintage = 2024 + observation_index % 3
            observation_id = f"m12obs-fictional-{observation_index:03d}"
            member_ids.append(observation_id)
            vintages.add(vintage)
            markets.add("Fictional Michigan")
            observations.append(
                {
                    "source_observation_id": observation_id,
                    "source_observation_lineage": {
                        "source_authority_id": "FICTIONAL-MICHIGAN-SOURCE",
                        "source_projection_id": "MODEL12_TARGET_BLIND_IDENTITY_PROJECTION_V1",
                        "source_projection_row": observation_index + 2,
                        "source_seed_point_id": f"FICTIONAL-SEED-{observation_index:03d}",
                        "forecast_vintage_original": f"Forecast {vintage}",
                    },
                    "forecast_vintage": vintage,
                    "source_market_lineage": "Fictional Michigan",
                    "physical_location_id": physical_id,
                    "identity_state": "AMBIGUOUS_IDENTITY" if quarantined else "RESOLVED_TARGET_BLIND_IDENTITY",
                    "identity_rule_reason_code": "FICTIONAL_CONFORMANCE",
                    "quarantined": quarantined,
                    "quarantine_reason": "FICTIONAL_AMBIGUITY" if quarantined else None,
                    "observed_coordinate": {"latitude": 42.0, "longitude": -84.0},
                    "canonical_target_blind_coordinate": None if quarantined else {"latitude": 42.0, "longitude": -84.0},
                    "target_access_state": "NOT_ACCESSED_BY_MODEL12",
                }
            )
            observation_index += 1
        locations.append(
            {
                "physical_location_id": physical_id,
                "identity_state": "AMBIGUOUS_IDENTITY" if quarantined else "RESOLVED_TARGET_BLIND_IDENTITY",
                "identity_rule_reason_codes": ["FICTIONAL_CONFORMANCE"],
                "quarantined": quarantined,
                "quarantine_reason": "FICTIONAL_AMBIGUITY" if quarantined else None,
                "canonical_target_blind_coordinate": None if quarantined else {"latitude": 42.0, "longitude": -84.0},
                "canonical_anchor_source_observation_id": None if quarantined else member_ids[0],
                "canonical_anchor_selection_semantics": None if quarantined else "EARLIEST_VINTAGE_THEN_SOURCE_LINEAGE",
                "source_observation_ids": member_ids,
                "source_vintages": sorted(vintages),
                "source_market_lineage_values": sorted(markets),
            }
        )
    assert observation_index == 139
    semantic = {
        "$schema": "model12-michigan-physical-location-identity-package-v1",
        "package_id": binding.IDENTITY_PACKAGE_ID,
        "version": "1.0.0",
        "state": "ready",
        "contract_authority": {"artifact_id": "MODEL12_MICHIGAN_TARGET_BLIND_FROZEN_SCORING_CONTRACT_V1", "version": "1.0.0", "content_sha256": "a" * 64},
        "source_authority": {"source_authority_id": "FICTIONAL-MICHIGAN-SOURCE", "source_projection_id": "MODEL12_TARGET_BLIND_IDENTITY_PROJECTION_V1", "projection_sha256": "b" * 64, "whole_source_file_hash_computed": False, "complete_forecast_vintages": [2024, 2025, 2026]},
        "target_blind_projection": {"target_body_values_accessed": 0},
        "identity_rules": {},
        "source_observations": observations,
        "physical_locations": locations,
        "aggregate_conformance": {"source_observation_count": 139, "physical_location_count": 86, "quarantined_source_observation_count": 1, "quarantined_physical_location_count": 1, "forecast_vintages": [2024, 2025, 2026], "complete_source_observation_accounting": True},
        "target_access": {"target_body_values_accessed": 0, "target_body_values_materialized": 0, "target_ordering_used": False, "target_ranking_used": False, "target_summary_computed": False, "pipe_target_binding_created": False},
        "protected_handle_registry_identity": "protected-handle-registry:sha256:" + "c" * 64,
    }
    protected_hash = content_digest(semantic)
    return {**semantic, "protected_content_sha256": protected_hash, "stable_package_identity": "model12-identity:sha256:" + protected_hash}


def _small_rows() -> tuple[list[dict], list[dict]]:
    identity = _identity_package()
    eligible, excluded, _physical = derive_target_binding_cohort(identity)
    return copy.deepcopy(eligible[:2]), copy.deepcopy(excluded)


def _materialization_authorities() -> list[dict]:
    output = []
    for ordinal in (1, 2):
        stages = {}
        for stage in ("identity", "public_features", "frozen_scoring"):
            prefix = f"phandle-m12-{ordinal}-{stage}"
            stages[stage] = {"package_handle": prefix + "-package", "ready_marker_handle": prefix + "-ready", "commitment_evidence_handle": prefix + "-evidence", "commitment_nonce_handle": prefix + "-nonce"}
        output.append({"ordinal": ordinal, "run_ready_marker_handle": f"phandle-m12-{ordinal}-run-ready", "stages": stages})
    return output


def _resolver(temp_root: Path, rows: list[dict], *, workbook_name: str = "authorized.xlsx") -> ProtectedHandleResolver:
    source = temp_root / workbook_name
    _write_xlsx(source, rows)
    output = temp_root / "output"
    output.mkdir()
    projection = inspect_minimum_projection_authority(source, workbook_handle="phandle-source", source_authority_id="FICTIONAL-MICHIGAN-SOURCE")
    registry = {
        "registry_id": "PIPE05_PROTECTED_HANDLE_REGISTRY_V1",
        "version": "1.0.0",
        "protected_roots": {"proot-fixture": str(temp_root.resolve())},
        "resources": {
            "phandle-source": {"root_handle": "proot-fixture", "relative_path": workbook_name, "kind": "michigan_isolated_sales_target_source"},
            "phandle-output": {"root_handle": "proot-fixture", "relative_path": "output", "kind": "pipe05_output_root"},
        },
        "model12_materialization_authorities": _materialization_authorities(),
        "source_authority": {"source_authority_id": "FICTIONAL-MICHIGAN-SOURCE", "source_root_handle": "proot-fixture", "exact_basename": Path(workbook_name).stem, "workbook_handle": "phandle-source", "whole_workbook_hash_permitted": False, "projection": projection},
        "binding_request": {"primary_identity_authority_ordinal": 1, "michigan_target_source_handle": "phandle-source", "binding_output_root_handle": "phandle-output"},
    }
    registry_path = temp_root / "registry.json"
    registry_path.write_text(json.dumps(registry), encoding="utf-8")
    return ProtectedHandleResolver.load(registry_path, ROOT)


def _authority() -> dict:
    return {
        "repository_contract_id": "MODEL12_MICHIGAN_TARGET_BLIND_FROZEN_SCORING_CONTRACT_V1",
        "repository_execution_commitment_id": binding.MODEL12_EXECUTION_COMMITMENT_ID,
        "substantive_h": binding.ACCEPTED_MODEL12_H,
        "acceptance_record_a": binding.ACCEPTED_MODEL12_A,
        "canonical_merge": binding.ACCEPTED_MODEL12_MERGE,
        "identity_package_id": binding.IDENTITY_PACKAGE_ID,
        "frozen_scoring_package_id": binding.SCORING_PACKAGE_ID,
        "independent_materialization_count": 2,
        "semantic_stage_count": 3,
        "semantic_packages_byte_identical": True,
        "aggregate_conformance_identical": True,
        "protected_materializations": [{"ordinal": 1}, {"ordinal": 2}],
        "prediction_body_materialized_by_pipe05": False,
        "identity_recomputed_or_reinterpreted": False,
    }


def _contract() -> dict:
    return {"artifact_id": binding.CONTRACT_ID, "version": binding.CONTRACT_VERSION, "content_sha256": "d" * 64, "accepted_model12_authority": {"contract_content_sha256": "a" * 64}}


class Pipe05BindingTests(unittest.TestCase):
    def test_01_exact_repository_model12_and_pipe04_authority(self):
        contract = verify_repository_authority(ROOT)
        self.assertEqual(contract["accepted_model12_authority"]["canonical_merge"], binding.ACCEPTED_MODEL12_MERGE)
        self.assertEqual(contract["target_projection"]["allowed_target_field"], "Isolated Sales")

    def test_02_exact_protected_stage_commitment_verification(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            rows, excluded = _small_rows()
            resolver = _resolver(root, rows + excluded)
            package_path = root / "identity-package.json"
            package_path.write_text("{}", encoding="utf-8")
            nonce = b"F" * 32
            commitment = freeze_commitment(file_sha256(package_path), nonce)
            ready = {"stage": "identity", "state": "ready", "finalization_state": "complete", "package_id": binding.IDENTITY_PACKAGE_ID, "package_version": "1.0.0", "package_file_sha256": file_sha256(package_path), "protected_content_sha256": "e" * 64, "commitment_sha256": commitment, "ready_marker_written_last": True}
            evidence = {"domain": "sprouts-customer-geography/model12/identity-commitment/v1", "commitment_sha256": commitment, "protected_package_digest_disclosed": False, "nonce_disclosed": False, "protected_content_disclosed": False}
            (root / "identity-ready.json").write_text(json.dumps(ready), encoding="utf-8")
            (root / "identity-evidence.json").write_text(json.dumps(evidence), encoding="utf-8")
            (root / "identity-nonce.bin").write_bytes(nonce)
            document = json.loads((root / "registry.json").read_text(encoding="utf-8"))
            document["resources"].update({
                "phandle-stage-package": {"root_handle": "proot-fixture", "relative_path": "identity-package.json", "kind": "model12_identity_package"},
                "phandle-stage-ready": {"root_handle": "proot-fixture", "relative_path": "identity-ready.json", "kind": "model12_identity_ready_marker"},
                "phandle-stage-evidence": {"root_handle": "proot-fixture", "relative_path": "identity-evidence.json", "kind": "model12_identity_commitment_evidence"},
                "phandle-stage-nonce": {"root_handle": "proot-fixture", "relative_path": "identity-nonce.bin", "kind": "model12_identity_commitment_nonce"},
            })
            (root / "registry-stage.json").write_text(json.dumps(document), encoding="utf-8")
            stage_resolver = ProtectedHandleResolver.load(root / "registry-stage.json", ROOT)
            result = _verify_stage(stage_resolver, "identity", {"package_handle": "phandle-stage-package", "ready_marker_handle": "phandle-stage-ready", "commitment_evidence_handle": "phandle-stage-evidence", "commitment_nonce_handle": "phandle-stage-nonce"}, commitment)
            self.assertEqual(result["commitment_sha256"], commitment)

    def test_03_complete_139_observation_cohort_freeze_ignores_score_computability(self):
        eligible, excluded, physical = derive_target_binding_cohort(_identity_package())
        self.assertEqual(len(eligible) + len(excluded), 139)
        self.assertEqual(len(physical), 86)
        self.assertEqual(len(excluded), 1)
        self.assertTrue(all("score_computability_status" not in row for row in eligible))

    def test_04_header_only_projection_and_isolated_sales_allowlist(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            eligible, excluded = _small_rows()
            workbook = root / "source.xlsx"
            _write_xlsx(workbook, eligible + excluded)
            authority = inspect_minimum_projection_authority(workbook, workbook_handle="phandle-source", source_authority_id="FICTIONAL-MICHIGAN-SOURCE")
            policy = MichiganIsolatedSalesProjectionPolicy(authority, "phandle-source", "FICTIONAL-MICHIGAN-SOURCE")
            projected, audit = project_authorized_isolated_sales(workbook, policy, eligible, excluded)
            self.assertEqual(len(projected), 2)
            self.assertEqual(audit.impacted_sales_body_decode_calls, 0)
            self.assertEqual(audit.other_outcome_body_decode_calls, 0)
            self.assertEqual(audit.quarantined_target_body_decode_calls, 0)
            self.assertNotIn("FORBIDDEN", json.dumps(projected))

    def test_05_impacted_other_state_and_whole_hash_authority_denied(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            eligible, excluded = _small_rows()
            resolver = _resolver(root, eligible + excluded)
            authority = copy.deepcopy(resolver.source_authority["projection"])
            for field, value in (("permitted_target_field", "Impacted Sales"), ("allowed_state", "wisconsin"), ("whole_workbook_hash_permitted", True)):
                mutated = copy.deepcopy(authority)
                mutated[field] = value
                with self.assertRaises(ConformanceError):
                    MichiganIsolatedSalesProjectionPolicy(mutated, "phandle-source", "FICTIONAL-MICHIGAN-SOURCE")

    def test_06_exact_row_lineage_and_vintage_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            eligible, excluded = _small_rows()
            for name, seed, vintage, code in (("seed.xlsx", "WRONG-SEED", None, "TARGET_SOURCE_OBSERVATION_LINEAGE_UNRESOLVED"), ("vintage.xlsx", None, "Forecast 2030", "FORECAST_VINTAGE_INVALID")):
                workbook = root / name
                _write_xlsx(workbook, eligible + excluded, second_seed_override=seed, second_vintage_override=vintage)
                policy = MichiganIsolatedSalesProjectionPolicy(inspect_minimum_projection_authority(workbook, workbook_handle="phandle-source", source_authority_id="FICTIONAL-MICHIGAN-SOURCE"), "phandle-source", "FICTIONAL-MICHIGAN-SOURCE")
                with self.assertRaises(ConformanceError) as caught:
                    project_authorized_isolated_sales(workbook, policy, eligible, excluded)
                self.assertEqual(caught.exception.code, code)

    def test_07_unexpected_and_duplicate_mapping_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            eligible, excluded = _small_rows()
            workbook = root / "unexpected.xlsx"
            _write_xlsx(workbook, eligible + excluded, add_unexpected=True)
            policy = MichiganIsolatedSalesProjectionPolicy(inspect_minimum_projection_authority(workbook, workbook_handle="phandle-source", source_authority_id="FICTIONAL-MICHIGAN-SOURCE"), "phandle-source", "FICTIONAL-MICHIGAN-SOURCE")
            with self.assertRaises(ConformanceError) as caught:
                project_authorized_isolated_sales(workbook, policy, eligible, excluded)
            self.assertEqual(caught.exception.code, "TARGET_SOURCE_ROW_ACCOUNTING_MISMATCH")
            duplicate = copy.deepcopy(eligible)
            duplicate[1]["source_observation_lineage"]["source_projection_row"] = duplicate[0]["source_observation_lineage"]["source_projection_row"]
            with self.assertRaises(ConformanceError):
                project_authorized_isolated_sales(workbook, policy, duplicate, excluded)

    def test_08_missing_invalid_and_zero_remain_distinct_without_imputation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            eligible, excluded = _small_rows()
            eligible[0]["fictional_target_kind"] = "missing"
            eligible[1]["fictional_target_kind"] = "invalid"
            workbook = root / "status.xlsx"
            _write_xlsx(workbook, eligible + excluded)
            policy = MichiganIsolatedSalesProjectionPolicy(inspect_minimum_projection_authority(workbook, workbook_handle="phandle-source", source_authority_id="FICTIONAL-MICHIGAN-SOURCE"), "phandle-source", "FICTIONAL-MICHIGAN-SOURCE")
            projected, audit = project_authorized_isolated_sales(workbook, policy, eligible, excluded)
            self.assertEqual([row["target_status"] for row in projected], ["MISSING", "INVALID"])
            self.assertTrue(all(row["isolated_sales"] is None for row in projected))
            self.assertEqual(audit.missing_isolated_sales_count, 1)
            self.assertEqual(audit.invalid_isolated_sales_count, 1)
            eligible[0].pop("fictional_target_kind")
            eligible[1].pop("fictional_target_kind")
            eligible[0]["fictional_target"] = 0
            _write_xlsx(root / "zero.xlsx", eligible + excluded)
            zero_policy = MichiganIsolatedSalesProjectionPolicy(inspect_minimum_projection_authority(root / "zero.xlsx", workbook_handle="phandle-source", source_authority_id="FICTIONAL-MICHIGAN-SOURCE"), "phandle-source", "FICTIONAL-MICHIGAN-SOURCE")
            zero_rows, _ = project_authorized_isolated_sales(root / "zero.xlsx", zero_policy, eligible, excluded)
            self.assertEqual(zero_rows[0]["target_status"], "VALID")
            self.assertEqual(zero_rows[0]["isolated_sales"], "0")

    def test_09_target_content_cannot_change_identity_or_cohort(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            eligible, excluded = _small_rows()
            before = content_digest(eligible)
            for filename, multiplier in (("one.xlsx", 1), ("two.xlsx", 7)):
                changed = copy.deepcopy(eligible)
                for index, row in enumerate(changed):
                    row["fictional_target"] = (index + 1) * multiplier
                workbook = root / filename
                _write_xlsx(workbook, changed + excluded)
                policy = MichiganIsolatedSalesProjectionPolicy(inspect_minimum_projection_authority(workbook, workbook_handle="phandle-source", source_authority_id="FICTIONAL-MICHIGAN-SOURCE"), "phandle-source", "FICTIONAL-MICHIGAN-SOURCE")
                project_authorized_isolated_sales(workbook, policy, eligible, excluded)
                self.assertEqual(content_digest(eligible), before)

    def test_10_exact_basename_rejects_similar_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "exact.xlsx").write_bytes(b"x")
            (root / "exact-copy.xlsx").write_bytes(b"x")
            self.assertEqual(resolve_exact_basename(root, "exact").name, "exact.xlsx")
            (root / "exact.csv").write_bytes(b"x")
            with self.assertRaises(ConformanceError):
                resolve_exact_basename(root, "exact")

    def test_11_exact_handle_containment_and_request_shape(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            eligible, excluded = _small_rows()
            resolver = _resolver(root, eligible + excluded)
            self.assertEqual(resolver.resolve_source().path, (root / "authorized.xlsx").resolve())
            document = json.loads((root / "registry.json").read_text(encoding="utf-8"))
            document["resources"]["phandle-source"]["relative_path"] = "../escape.xlsx"
            (root / "bad.json").write_text(json.dumps(document), encoding="utf-8")
            bad = ProtectedHandleResolver.load(root / "bad.json", ROOT)
            with self.assertRaises(ConformanceError) as caught:
                bad.resolve_source()
            self.assertEqual(caught.exception.code, "PROTECTED_PATH_TRAVERSAL_REJECTED")
            document = json.loads((root / "registry.json").read_text(encoding="utf-8"))
            document["binding_request"]["extra"] = "phandle-extra"
            (root / "bad-request.json").write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaises(ConformanceError):
                load_authorized_registry(root / "bad-request.json", ROOT)

    def test_12_full_binding_incomplete_first_ready_last_and_deterministic_verification(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            identity = _identity_package()
            eligible, excluded, _physical = derive_target_binding_cohort(identity)
            resolver = _resolver(root, eligible + excluded)
            writes: list[str] = []
            from sprouts_customer_geography.pipe04 import binding as pipe04_binding
            original = pipe04_binding.write_json_exclusive

            def recording(path: Path, value: object) -> None:
                writes.append(path.name)
                original(path, value)

            with patch.object(binding, "verify_repository_authority", return_value=_contract()), patch.object(binding, "verify_model12_protected_authority", return_value=(identity, _authority())), patch.object(pipe04_binding, "write_json_exclusive", side_effect=recording):
                result = execute_protected_binding(repository_root=ROOT, resolver=resolver, binding_run_id="p5bind-fictional-full")
                verification = verify_persisted_binding(repository_root=ROOT, resolver=resolver, run_dir=result.run_dir)
            self.assertTrue(protected_binding_is_ready(result.run_dir))
            self.assertEqual(writes[-1], "READY.json")
            self.assertEqual(result.source_observation_count, 139)
            self.assertEqual(result.unique_bound_physical_location_count, 85)
            self.assertEqual(verification["state"], "MATCH")

    def test_13_interruption_remains_incomplete_and_unready(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            identity = _identity_package()
            eligible, excluded, _physical = derive_target_binding_cohort(identity)
            resolver = _resolver(root, eligible + excluded)
            with patch.object(binding, "verify_repository_authority", return_value=_contract()), patch.object(binding, "verify_model12_protected_authority", return_value=(identity, _authority())), patch.object(binding, "project_authorized_isolated_sales", side_effect=ConformanceError("FICTIONAL_INTERRUPTION", "stop")):
                with self.assertRaises(ConformanceError):
                    execute_protected_binding(repository_root=ROOT, resolver=resolver, binding_run_id="p5bind-interrupted")
            run = root / "output/pipe05-bindings/p5bind-interrupted"
            self.assertTrue((run / "binding_state.json").is_file())
            self.assertFalse((run / "READY.json").exists())

    def test_14_immutable_runs_and_explicit_supersession(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = ProtectedBindingRun(root, ROOT, binding_run_id="p5bind-first")
            self.assertFalse(protected_binding_is_ready(first.run_dir))
            with self.assertRaises(ConformanceError):
                ProtectedBindingRun(root, ROOT, binding_run_id="p5bind-first")
            corrected = ProtectedBindingRun(root, ROOT, binding_run_id="p5bind-corrected", package_version="1.0.1", supersedes="p5bind-first")
            self.assertEqual(corrected.supersedes, "p5bind-first")
            with self.assertRaises(ConformanceError):
                ProtectedBindingRun(root, ROOT, binding_run_id="p5bind-bad", supersedes="p5bind-first")

    def test_15_binding_package_rejects_analytical_or_consumption_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            identity = _identity_package()
            eligible, excluded, _physical = derive_target_binding_cohort(identity)
            resolver = _resolver(root, eligible + excluded)
            with patch.object(binding, "verify_repository_authority", return_value=_contract()), patch.object(binding, "verify_model12_protected_authority", return_value=(identity, _authority())):
                result = execute_protected_binding(repository_root=ROOT, resolver=resolver, binding_run_id="p5bind-boundary")
            package = json.loads((result.run_dir / binding.BINDING_FILENAME).read_text(encoding="utf-8"))
            for key in ("protected_content_sha256", "stable_binding_identity", "protected_content_hash_semantics"):
                package.pop(key)
            package["execution_boundary"]["benchmark_evaluation_performed"] = True
            with self.assertRaises(ConformanceError):
                validate_semantic_package(package)
            package["execution_boundary"]["benchmark_evaluation_performed"] = False
            package["evidence_role"]["binding_marks_development_consumed"] = True
            with self.assertRaises(ConformanceError):
                validate_semantic_package(package)

    def test_16_disclosure_safe_report_and_repository_commitment(self):
        result = binding.BindingResult("p5bind-secret", Path("C:/protected/secret"), "a" * 64, "pipe05-binding:sha256:" + "b" * 64, "c" * 64, 139, 138, 85, 1, TargetAccessAudit(authorized_isolated_sales_cell_examinations=138, valid_isolated_sales_decode_calls=137, missing_isolated_sales_count=1))
        verification = {"state": "MATCH", "source_observation_accounting_identical": True, "eligible_cohort_identity_identical": True, "minimum_target_projection_identical": True, "protected_content_verified": True, "ready_commitment_verified": True}
        report = build_disclosure_safe_result(result, verification)
        rendered = json.dumps(report).lower()
        self.assertNotIn("secret", rendered)
        self.assertNotIn("sha256", rendered)
        self.assertEqual(report["impacted_sales_body_values_accessed"], 0)
        commitment = build_repository_execution_commitment(result, verification, _contract())
        expected = commitment.pop("content_sha256")
        self.assertEqual(expected, content_digest(commitment))
        self.assertNotIn("p5bind-secret", json.dumps(commitment))

    def test_17_cli_without_registry_is_disclosure_safe_and_does_not_discover(self):
        output = io.StringIO()
        with patch("sys.argv", ["pipe05"]), patch.dict("os.environ", {}, clear=True), redirect_stdout(output):
            self.assertEqual(cli.main(), 2)
        report = json.loads(output.getvalue())
        self.assertFalse(report["filesystem_discovery_performed"])
        for relative in ("src/sprouts_customer_geography/pipe05/resolver.py", "src/sprouts_customer_geography/pipe05/registry_bootstrap.py"):
            source = (ROOT / relative).read_text(encoding="utf-8").lower()
            self.assertFalse(any(operation in source for operation in (".glob(", ".rglob(", ".iterdir(", "os.walk(")))
        self.assertFalse(report["protected_details_disclosed"])
        self.assertFalse(report["benchmark_evaluation_performed"])

    def test_18_pipe05_protected_artifacts_are_not_stageable(self):
        with self.assertRaises(ConformanceError) as caught:
            assert_no_protected_tracked_paths(["local/pipe05-bindings/p5bind-fictional/pipe05_model12_michigan_isolated_sales_binding.json"])
        self.assertEqual(caught.exception.code, "PROTECTED_TRACKED_PATH_REJECTED")


if __name__ == "__main__":
    unittest.main()
