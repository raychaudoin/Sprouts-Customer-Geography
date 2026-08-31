from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
TEST_TEMP_ROOT = Path(os.environ.get("READINESS_TEST_TEMP_ROOT", tempfile.gettempdir()))
TEST_TEMP_ROOT.mkdir(parents=True, exist_ok=True)

from sprouts_customer_geography.pipe01.errors import ConformanceError
from sprouts_customer_geography.readiness.disclosure import validate_development_readiness
from sprouts_customer_geography.readiness.mailbox_contract import MAILBOX_ENFORCEMENT_PATHS
from sprouts_customer_geography.readiness.publisher import build_readiness_document, publish_readiness
from sprouts_customer_geography.readiness.store import initialize_project_state


class ReadinessPublisherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="gov16-publisher-", dir=TEST_TEMP_ROOT)
        self.root = Path(self.temporary.name)
        self.source = self.root / "source"
        self.mailbox = self.root / "mailbox"
        for relative in MAILBOX_ENFORCEMENT_PATHS:
            destination = self.source / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, destination)
        self._git(self.source.parent, "init", "-b", "task/gov-16-synthetic", str(self.source))
        self._git(self.source, "config", "user.email", "synthetic@example.invalid")
        self._git(self.source, "config", "user.name", "Synthetic Readiness Test")
        self._git(self.source, "add", ".")
        self._git(self.source, "commit", "-m", "synthetic source baseline")
        self.source_commit = self._git(self.source, "rev-parse", "HEAD").stdout.strip()
        self._git(self.source, "branch", "task/model-14-frozen", self.source_commit)
        self._git(self.source, "branch", "task/model-15-preserved", self.source_commit)
        self._git(self.source, "branch", "readiness-mailbox", self.source_commit)
        self._git(self.source, "worktree", "add", str(self.mailbox), "readiness-mailbox")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def _git(cwd: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *arguments],
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
        )

    def _registered_store(self):
        state_root = self.root / "state"
        protected_root = self.root / "protected"
        protected_root.mkdir()
        store = initialize_project_state(state_root, repository_root=self.source)
        store.register_root("SYNTHETIC_ROOT", protected_root, repository_root=self.source)
        store.register_asset("MODEL13_AUTHORITY_PACKAGE", "SYNTHETIC_ROOT", ".", "PROTECTED_PACKAGE_DIRECTORY")
        store.register_asset("APP01_PROTECTED_INPUT_PACKAGE", "SYNTHETIC_ROOT", ".", "PROTECTED_PACKAGE_DIRECTORY")
        store.set_preservation("MODEL-14", "frozen", self.source_commit)
        store.set_preservation("MODEL-15", "preserved-paused", self.source_commit)
        store.record_recovery(self.source_commit, "passed", fresh_session=True)
        return store, protected_root

    def test_01_missing_protected_state_blocks_only_protected_readiness(self):
        document = build_readiness_document(self.source, state_root=self.root / "missing")
        validate_development_readiness(document)
        self.assertEqual(document["repository"]["verified_commit"], self.source_commit)
        self.assertEqual(document["protected_state"]["project_profile"], "MISSING")
        self.assertEqual(document["recovery"]["fresh_session"], "NOT_VERIFIED")

    def test_02_publisher_uses_registered_state_and_canonical_snapshot(self):
        store, protected_root = self._registered_store()
        output = self.mailbox / "development-readiness.json"
        document = publish_readiness(self.source, output, state_root=store.state_root)
        self.assertEqual(json.loads(output.read_text(encoding="utf-8")), document)
        self.assertEqual(document["protected_state"]["model13_authority"], "REGISTERED_RECOVERABLE")
        self.assertEqual(document["protected_state"]["app01_inputs"], "REGISTERED_RECOVERABLE")
        self.assertEqual(document["preservation"], {"model14": "PRESERVED", "model15": "PRESERVED"})
        self.assertEqual(document["recovery"], {"fresh_session": "SUCCEEDED"})
        rendered = output.read_text(encoding="utf-8")
        self.assertNotIn(str(protected_root), rendered)
        self.assertNotIn("\\", rendered)

    def test_03_snapshot_exposes_time_and_exact_repository_baseline(self):
        document = build_readiness_document(self.source, state_root=self.root / "missing")
        self.assertRegex(document["generated_at_utc"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
        self.assertEqual(document["repository"]["verified_commit"], self.source_commit)

    def test_04_publisher_rejects_arbitrary_output_and_dirty_mailbox(self):
        store, _ = self._registered_store()
        with self.assertRaisesRegex(ConformanceError, "READINESS_MAILBOX_WORKTREE_INVALID"):
            publish_readiness(self.source, self.root / "development-readiness.json", state_root=store.state_root)
        unrelated = self.mailbox / "unrelated.txt"
        unrelated.write_text("synthetic", encoding="utf-8")
        with self.assertRaisesRegex(ConformanceError, "READINESS_MAILBOX_DIRTY"):
            publish_readiness(self.source, self.mailbox / "development-readiness.json", state_root=store.state_root)

    def test_05_build_does_not_claim_fresh_session_without_recorded_proof(self):
        store, _ = self._registered_store()
        with store._connect() as connection:
            connection.execute("DELETE FROM session_recoveries")
        document = build_readiness_document(self.source, state_root=store.state_root)
        self.assertEqual(document["recovery"]["fresh_session"], "NOT_VERIFIED")

    def test_06_publisher_rejects_stale_mailbox_validation_runtime(self):
        store, _ = self._registered_store()
        enforcement_file = self.mailbox / "scripts" / "check_readiness_mailbox.py"
        enforcement_file.write_text(enforcement_file.read_text(encoding="utf-8") + "\n# synthetic drift\n", encoding="utf-8")
        self._git(self.mailbox, "add", "scripts/check_readiness_mailbox.py")
        self._git(self.mailbox, "commit", "-m", "synthetic stale enforcement")
        with self.assertRaisesRegex(ConformanceError, "READINESS_MAILBOX_ENFORCEMENT_STALE"):
            publish_readiness(self.source, self.mailbox / "development-readiness.json", state_root=store.state_root)

    def test_07_actual_checker_rejects_prior_runtime_drift_under_snapshot_head(self):
        store, _ = self._registered_store()
        snapshot = self.mailbox / "development-readiness.json"
        checker_environment = os.environ.copy()
        checker_environment.pop("GITHUB_REF_NAME", None)
        publish_readiness(self.source, snapshot, state_root=store.state_root)
        self._git(self.mailbox, "add", "development-readiness.json")
        self._git(self.mailbox, "commit", "-m", "synthetic mailbox refresh")
        checker = subprocess.run(
            [sys.executable, "scripts/check_readiness_mailbox.py"],
            cwd=self.mailbox,
            check=False,
            capture_output=True,
            text=True,
            env=checker_environment,
        )
        self.assertEqual(checker.returncode, 0, checker.stderr)

        imported_runtime = self.mailbox / "src" / "sprouts_customer_geography" / "constants.py"
        imported_runtime.write_text(imported_runtime.read_text(encoding="utf-8") + "\n# synthetic prior drift\n", encoding="utf-8")
        self._git(self.mailbox, "add", "src/sprouts_customer_geography/constants.py")
        self._git(self.mailbox, "commit", "-m", "synthetic prior runtime drift")
        document = json.loads(snapshot.read_text(encoding="utf-8"))
        document["generated_at_utc"] = "2026-08-31T00:00:00Z"
        snapshot.write_text(json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
        self._git(self.mailbox, "add", "development-readiness.json")
        self._git(self.mailbox, "commit", "-m", "synthetic later snapshot refresh")
        checker = subprocess.run(
            [sys.executable, "scripts/check_readiness_mailbox.py"],
            cwd=self.mailbox,
            check=False,
            capture_output=True,
            text=True,
            env=checker_environment,
        )
        self.assertNotEqual(checker.returncode, 0)
        self.assertIn("READINESS_MAILBOX_ENFORCEMENT_STALE", checker.stderr)


if __name__ == "__main__":
    unittest.main()
