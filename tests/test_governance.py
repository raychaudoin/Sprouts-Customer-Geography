from __future__ import annotations

import copy
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sprouts_customer_geography.governance import (
    branch_name_is_valid,
    future_pr_title_is_valid,
    load_and_validate_task_manifest,
    task_commit_message_is_valid,
    task_id_is_valid,
    validate_task_manifest,
    validate_task_retry,
)
from sprouts_customer_geography.pipe01.errors import ConformanceError
from sprouts_customer_geography.pipe01.safeguards import assert_no_protected_tracked_paths


SCHEMA = ROOT / "schemas" / "governance" / "task_manifest.schema.json"
MANIFEST = ROOT / "governance" / "tasks" / "GOV-02.github-workflow-execution-governance.task.json"


class GovernanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    def test_01_manifest_validates_against_stable_schema(self):
        document = load_and_validate_task_manifest(MANIFEST, SCHEMA)
        self.assertEqual(document["task_id"], "GOV-02")

    def test_02_task_id_rules_allow_existing_prefixes_and_reject_bad_ids(self):
        self.assertTrue(task_id_is_valid("GOV-02"))
        self.assertTrue(task_id_is_valid("PIPE-01B"))
        self.assertTrue(task_id_is_valid("INTEGRATION-14"))
        for invalid in ("GOV2", "UNKNOWN-02", "GOV-2", "GOV-02-RETRY"):
            self.assertFalse(task_id_is_valid(invalid))

    def test_03_only_contract_states_are_allowed(self):
        candidate = copy.deepcopy(self.manifest)
        candidate["state"] = "MERGED"
        with self.assertRaisesRegex(ConformanceError, "TASK_STATE_INVALID"):
            validate_task_manifest(candidate)

    def test_04_branch_commit_and_future_pr_naming(self):
        self.assertTrue(branch_name_is_valid("task/gov-02-github-workflow-execution-governance", "GOV-02"))
        self.assertFalse(branch_name_is_valid("codex/gov02", "GOV-02"))
        self.assertTrue(task_commit_message_is_valid("GOV-02: implement repository workflow governance", "GOV-02"))
        self.assertFalse(task_commit_message_is_valid("GOV-02 implement workflow", "GOV-02"))
        self.assertTrue(future_pr_title_is_valid("GOV-02: GitHub Workflow & Execution Governance", "GOV-02"))

    def test_05_rejects_protected_paths_values_and_fields(self):
        cases = [
            ("scope", ["C:\\Protected\\workbook.xlsx"], "TASK_MANIFEST_ABSOLUTE_PATH_REJECTED"),
            ("scope", ["43.12345, -87.12345"], "TASK_MANIFEST_COORDINATE_REJECTED"),
            ("scope", ["a" * 64], "TASK_MANIFEST_PROTECTED_DIGEST_REJECTED"),
        ]
        for field, value, code in cases:
            with self.subTest(code=code):
                candidate = copy.deepcopy(self.manifest)
                candidate[field] = value
                with self.assertRaisesRegex(ConformanceError, code):
                    validate_task_manifest(candidate)
        candidate = copy.deepcopy(self.manifest)
        candidate["nonce"] = "fictional"
        with self.assertRaisesRegex(ConformanceError, "TASK_MANIFEST_FIELD_PROHIBITED"):
            validate_task_manifest(candidate)
        candidate = copy.deepcopy(self.manifest)
        candidate["target_cell_address"] = "A1"
        with self.assertRaisesRegex(ConformanceError, "TASK_MANIFEST_FIELD_PROHIBITED"):
            validate_task_manifest(candidate)

    def test_06_opaque_protected_logical_ids_are_allowed(self):
        candidate = copy.deepcopy(self.manifest)
        candidate["protected_dependency_logical_ids"] = ["PROTECTED_FUTURE_INPUT_V1"]
        validate_task_manifest(candidate)

    def test_07_evidence_alone_cannot_close_a_capability(self):
        for evidence in ("LOCAL_COMMIT", "TEST_PASS", "COMPLETION_REPORT", "FUTURE_PULL_REQUEST", "FUTURE_MERGE"):
            with self.subTest(evidence=evidence):
                candidate = copy.deepcopy(self.manifest)
                candidate["state"] = "ACCEPTED_CLOSED"
                candidate["completion_state"]["implementation_evidence"] = [evidence]
                with self.assertRaisesRegex(ConformanceError, "TASK_ACCEPTANCE_METADATA_REQUIRED"):
                    validate_task_manifest(candidate)

    def test_08_accepted_closed_requires_explicit_acceptance_metadata(self):
        candidate = copy.deepcopy(self.manifest)
        candidate["state"] = "ACCEPTED_CLOSED"
        candidate["completion_state"]["capability_acceptance"] = "ACCEPTED"
        candidate["acceptance_disposition"] = "ACCEPTED"
        candidate["acceptance_metadata"] = {
            "capability_owner": "GOV: Repository Workflow Decisions & Acceptance",
            "recorded_by": "capability acceptance",
            "recorded_on": "2026-08-20",
        }
        validate_task_manifest(candidate)
        candidate["acceptance_metadata"]["recorded_on"] = "not-a-date"
        with self.assertRaisesRegex(ConformanceError, "TASK_ACCEPTANCE_METADATA_INVALID"):
            validate_task_manifest(candidate)

    def test_09_corrections_retain_task_identity(self):
        correction = copy.deepcopy(self.manifest)
        correction["state"] = "IN_PROGRESS"
        correction["completion_state"] = {"execution": "IN_PROGRESS", "implementation_evidence": [], "capability_acceptance": "NOT_REVIEWED"}
        validate_task_retry(self.manifest, correction)
        correction["task_id"] = "GOV-03"
        with self.assertRaisesRegex(ConformanceError, "TASK_ID_MUTATION_REJECTED"):
            validate_task_retry(self.manifest, correction)

    def test_10_destinations_are_required(self):
        for field in ("acceptance_destination", "exact_next_destination"):
            candidate = copy.deepcopy(self.manifest)
            candidate[field] = ""
            with self.assertRaisesRegex(ConformanceError, "TASK_MANIFEST_FIELD_INVALID"):
                validate_task_manifest(candidate)

    def test_11_synthetic_fixture_and_tracked_path_safeguard_are_safe(self):
        self.assertNotIn("Sprouts", json.dumps(self.manifest))
        stageable = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
        assert_no_protected_tracked_paths(stageable)


if __name__ == "__main__":
    unittest.main()
