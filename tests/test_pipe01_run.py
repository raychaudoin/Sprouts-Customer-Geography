from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from sprouts_customer_geography.pipe01.canonical import content_digest
from sprouts_customer_geography.pipe01.commitment import DOMAIN_SEPARATOR, freeze_commitment
from sprouts_customer_geography.pipe01.errors import ConformanceError
from sprouts_customer_geography.pipe01.reporting import build_disclosure_safe_report
from sprouts_customer_geography.pipe01.run import MANDATORY_DEPENDENCIES, ProtectedRun, protected_run_is_frozen
from sprouts_customer_geography.pipe01.safeguards import assert_no_protected_tracked_paths


def dependencies():
    return {key: f"accepted-synthetic-{key}" for key in MANDATORY_DEPENDENCIES}


def temporary_directory():
    configured_root = os.environ.get("PIPE01_TEST_TEMP_ROOT")
    return tempfile.TemporaryDirectory(dir=configured_root or None)


class ProtectedRunTests(unittest.TestCase):
    def test_protected_root_inside_repository_is_rejected(self):
        repo = Path.cwd()
        with self.assertRaisesRegex(ConformanceError, "PROTECTED_ROOT_INSIDE_REPOSITORY"):
            ProtectedRun(repo / "outputs" / "protected", repo, run_id="prun-synthetic")

    def test_target_value_artifact_is_rejected(self):
        with temporary_directory() as temp:
            run = ProtectedRun(Path(temp), Path.cwd(), run_id="prun-synthetic-target-reject")
            with self.assertRaisesRegex(ConformanceError, "TARGET_INPUT_REJECTED"):
                run.write_artifact("bad.json", {"target_value": 123})

    def test_interrupted_run_remains_incomplete(self):
        with temporary_directory() as temp:
            run = ProtectedRun(Path(temp), Path.cwd(), run_id="prun-synthetic-interrupted")
            run.write_artifact("synthetic.json", {"synthetic": True})
            self.assertFalse(protected_run_is_frozen(run.run_dir))
            state = json.loads((run.run_dir / "run_state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["state"], "incomplete")

    def test_incomplete_dependencies_never_finalize(self):
        with temporary_directory() as temp:
            run = ProtectedRun(Path(temp), Path.cwd(), run_id="prun-synthetic-missing-deps")
            run.write_artifact("synthetic.json", {"synthetic": True})
            with self.assertRaisesRegex(ConformanceError, "ACCEPTED_DEPENDENCIES_MISSING"):
                run.finalize({}, "commit-synthetic", {"spec": "synthetic"}, {"mandatory_passed": True}, False)
            self.assertFalse(protected_run_is_frozen(run.run_dir))

    def test_unexpected_dependency_fields_never_finalize(self):
        with temporary_directory() as temp:
            run = ProtectedRun(Path(temp), Path.cwd(), run_id="prun-synthetic-unexpected-deps")
            run.write_artifact("synthetic.json", {"synthetic": True})
            supplied = {**dependencies(), "extra_dependency": "not-authorized"}
            with self.assertRaisesRegex(ConformanceError, "UNEXPECTED_DEPENDENCIES_REJECTED"):
                run.finalize(supplied, "commit-synthetic", {"spec": "synthetic"}, {"mandatory_passed": True}, False)
            self.assertFalse(protected_run_is_frozen(run.run_dir))

    def test_failed_conformance_or_supplied_targets_never_finalize(self):
        for suffix, conformance, supplied, code in [
            ("conf", {"mandatory_passed": False}, False, "CONFORMANCE_NOT_PASSED"),
            ("target", {"mandatory_passed": True}, True, "SEALED_TARGETS_PROHIBITED"),
        ]:
            with temporary_directory() as temp:
                run = ProtectedRun(Path(temp), Path.cwd(), run_id=f"prun-synthetic-{suffix}")
                run.write_artifact("synthetic.json", {"synthetic": True})
                with self.assertRaisesRegex(ConformanceError, code):
                    run.finalize(dependencies(), "commit-synthetic", {"spec": "synthetic"}, conformance, supplied)
                self.assertFalse(protected_run_is_frozen(run.run_dir))

    def test_successful_finalization_writes_completion_marker_last_contract(self):
        with temporary_directory() as temp:
            run = ProtectedRun(Path(temp), Path.cwd(), run_id="prun-synthetic-final")
            run.write_artifact("synthetic.json", {"synthetic": True})
            result = run.finalize(dependencies(), "commit-synthetic", {"spec": "synthetic"}, {"mandatory_passed": True, "passed": 40}, False)
            self.assertEqual(result["state"], "frozen")
            self.assertTrue(protected_run_is_frozen(run.run_dir))
            self.assertTrue((run.run_dir / "freeze_manifest.json").exists())
            self.assertTrue((run.run_dir / "freeze_nonce.bin").exists())
            self.assertRegex(result["commitment_sha256"], r"^[0-9a-f]{64}$")

    def test_finalized_run_cannot_be_overwritten_and_correction_supersedes(self):
        with temporary_directory() as temp:
            root = Path(temp)
            first = ProtectedRun(root, Path.cwd(), run_id="prun-synthetic-v1")
            first.write_artifact("synthetic.json", {"version": 1})
            first.finalize(dependencies(), "commit-v1", {"spec": "v1"}, {"mandatory_passed": True}, False)
            with self.assertRaisesRegex(ConformanceError, "RUN_ALREADY_EXISTS"):
                ProtectedRun(root, Path.cwd(), run_id="prun-synthetic-v1")
            correction = ProtectedRun(root, Path.cwd(), run_id="prun-synthetic-v2", supersedes="prun-synthetic-v1")
            correction.write_artifact("synthetic.json", {"version": 2})
            correction.finalize(dependencies(), "commit-v2", {"spec": "v2"}, {"mandatory_passed": True}, False)
            manifest = json.loads((correction.run_dir / "freeze_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["supersedes"], "prun-synthetic-v1")

    def test_deterministic_content_and_nondeterministic_commitment_events(self):
        value = {"ordered": [1, 2, 3], "synthetic": True}
        self.assertEqual(content_digest(value), content_digest(value))
        digest = content_digest(value)
        one = freeze_commitment(digest, b"1" * 32)
        two = freeze_commitment(digest, b"2" * 32)
        self.assertNotEqual(one, two)
        self.assertTrue(DOMAIN_SEPARATOR.startswith(b"sprouts-customer-geography/pipe01"))

    def test_tracked_protected_artifact_classes_are_rejected(self):
        with self.assertRaisesRegex(ConformanceError, "PROTECTED_TRACKED_PATH_REJECTED"):
            assert_no_protected_tracked_paths(["results/context_membership.json"])
        assert_no_protected_tracked_paths(["schemas/pipe01/context_membership.json", "tests/fixtures/synthetic/context_membership.json"])

    def test_disclosure_safe_report_has_no_protected_values(self):
        report = build_disclosure_safe_report(
            run_state="blocked", mandatory_passed=False, check_counts={"passed": 40},
            dependency_states={"model04": "missing"}, source_checksum_states={"tiger": "unestablished"},
            inventory_counts={"milwaukee": None, "madison": None}, eligibility_summary={}, commitment=None,
        )
        serialized = json.dumps(report)
        for forbidden in ("anchor_tract_geoid", "distance_m", "prediction_candidate", "target_value"):
            self.assertNotIn(forbidden, serialized)

    def test_disclosure_safe_report_recursively_rejects_protected_fields(self):
        with self.assertRaisesRegex(ConformanceError, "PROTECTED_REPORT_FIELD_REJECTED"):
            build_disclosure_safe_report(
                run_state="blocked", mandatory_passed=False, check_counts={}, dependency_states={"nested": {"distance_m": "not-safe"}},
                source_checksum_states={}, inventory_counts={}, eligibility_summary={}, commitment=None,
            )


if __name__ == "__main__":
    unittest.main()
