from __future__ import annotations

import json
import os
import subprocess
import sqlite3
import stat
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
TEST_TEMP_ROOT = Path(os.environ.get("READINESS_TEST_TEMP_ROOT", tempfile.gettempdir()))
TEST_TEMP_ROOT.mkdir(parents=True, exist_ok=True)

from sprouts_customer_geography.pipe01.errors import ConformanceError
from sprouts_customer_geography.pipe01.safeguards import assert_no_protected_tracked_paths
from sprouts_customer_geography.readiness.repository import probe_repository
from sprouts_customer_geography.readiness.store import (
    bootstrap_from_app01_settings,
    default_state_root,
    initialize_project_state,
    migrate_model15_parser_incident,
    recover_project_state,
)


class ReadinessStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="gov16-readiness-", dir=TEST_TEMP_ROOT)
        self.root = Path(self.temporary.name)
        self.state_root = self.root / "state"
        self.repository_root = self.root / "repository"
        self.repository_root.mkdir()
        self.protected_root = self.root / "protected"
        self.protected_root.mkdir()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_01_default_state_root_uses_durable_override(self):
        expected = self.root / "relocated"
        self.assertEqual(default_state_root({"SCG_PROJECT_STATE_HOME": str(expected)}), expected)

    def test_02_initialize_and_fresh_recovery_need_no_asset_path(self):
        environment = os.environ.copy()
        environment.pop("SCG_PROJECT_STATE_HOME", None)
        environment["LOCALAPPDATA"] = str(self.root / "automatic-local-state")
        automatic_state_root = default_state_root(environment)
        initialized = initialize_project_state(automatic_state_root, repository_root=self.repository_root)
        initialized.register_root("SYNTHETIC_ROOT", self.protected_root, repository_root=self.repository_root)
        initialized.register_asset("SYNTHETIC_PACKAGE", "SYNTHETIC_ROOT", ".", "PROTECTED_PACKAGE_DIRECTORY")
        recovered = recover_project_state(automatic_state_root, repository_root=self.repository_root)
        self.assertEqual(recovered.resolve_asset("SYNTHETIC_PACKAGE").asset_id, "SYNTHETIC_PACKAGE")

        environment["PYTHONPATH"] = str(ROOT / "src")
        result = subprocess.run(
            [sys.executable, "-m", "sprouts_customer_geography.readiness", "verify", "--repository-root", str(ROOT)],
            cwd=ROOT,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"profile": "ready", "state": "recovered"})
        baseline = probe_repository(ROOT).verified_commit
        self.assertEqual(recover_project_state(automatic_state_root, repository_root=self.repository_root).fresh_session_recovery_status(baseline), "passed")

    def test_03_exact_asset_resolution_rejects_traversal_and_absolute_paths(self):
        store = initialize_project_state(self.state_root, repository_root=self.repository_root)
        store.register_root("SYNTHETIC_ROOT", self.protected_root, repository_root=self.repository_root)
        exact = self.protected_root / "registered"
        exact.mkdir()
        store.register_asset("EXACT_ASSET", "SYNTHETIC_ROOT", "registered", "PROTECTED_PACKAGE_DIRECTORY")
        self.assertEqual(store.resolve_asset("EXACT_ASSET").path, exact.resolve())
        for invalid in ("../escape", "C:\\protected\\escape", "/protected/escape", "file:///protected/escape"):
            with self.subTest(invalid=invalid), self.assertRaises(ConformanceError):
                store.register_asset("BAD_ASSET", "SYNTHETIC_ROOT", invalid, "PROTECTED_PACKAGE_DIRECTORY")

    def test_04_machine_read_does_not_promote_visibility_or_use(self):
        store = initialize_project_state(self.state_root, repository_root=self.repository_root)
        migrate_model15_parser_incident(store)
        states = store.event_states("MODEL15_PARSER_INCIDENT")
        self.assertEqual(states["machine_target_read"], "uncertain")
        self.assertEqual(states["visible"], "false")
        self.assertEqual(states["analytically_used"], "false")
        self.assertEqual(states["development_used"], "false")
        self.assertEqual(states["disclosed"], "false")

    def test_05_evidence_events_and_model_membership_are_auditable(self):
        store = initialize_project_state(self.state_root, repository_root=self.repository_root)
        store.register_root("SYNTHETIC_ROOT", self.protected_root, repository_root=self.repository_root)
        source = self.protected_root / "source.xlsx"
        source.write_bytes(b"synthetic-not-a-real-workbook")
        store.register_asset("SYNTHETIC_SOURCE_ASSET", "SYNTHETIC_ROOT", "source.xlsx", "ORIGINAL_SOURCE_FILE", immutable_original=True)
        store.register_source("SYNTHETIC_SOURCE", "SYNTHETIC_SOURCE_ASSET", "VINTAGE_2026", "SYNTHETIC_MEASURE", "ready")
        store.register_evidence_unit("LOCATION_ALPHA", "reconciled", "EVIDENCE_ALPHA", "VINTAGE_2026", "SYNTHETIC_MEASURE", "ready")
        store.register_source_alias("ALIAS_ALPHA", "EVIDENCE_ALPHA", "SYNTHETIC_SOURCE", "SYNTHETIC_ROW_ALPHA")
        store.register_model("SYNTHETIC_MODEL", "candidate")
        store.register_model_membership("SYNTHETIC_MODEL", "EVIDENCE_ALPHA", "development")
        store.record_event("EVIDENCE_UNIT", "EVIDENCE_ALPHA", "identity_read", "true", "SYNTHETIC_TEST")
        store.set_source_inventory_completeness("ready")
        store.set_evidence_ledger_completeness("ready")
        self.assertEqual(store.model_membership("SYNTHETIC_MODEL"), (("EVIDENCE_ALPHA", "development"),))
        self.assertEqual(store.event_states("EVIDENCE_ALPHA"), {"identity_read": "true"})
        self.assertEqual(store.readiness_facts()["evidence_ledger"], "ready")

    def test_06_trusted_bootstrap_registers_only_the_exact_candidate(self):
        repository = self.root / "repository"
        settings_dir = repository / "presentation" / "app01" / "local"
        settings_dir.mkdir(parents=True)
        candidate = self.protected_root / "model13-package"
        candidate.mkdir()
        settings = settings_dir / "settings.json"
        settings.write_text(json.dumps({"model13_candidates": [str(candidate)]}), encoding="utf-8")
        store = bootstrap_from_app01_settings(repository, state_root=self.state_root)
        facts = store.readiness_facts()
        self.assertEqual(facts["model13_authority"], "registered-recoverable")
        self.assertEqual(facts["app01_inputs"], "registered-recoverable")
        self.assertEqual(store.preservation()["MODEL-14"], "frozen")
        self.assertEqual(store.preservation()["MODEL-15"], "preserved-paused")

    def test_07_missing_profile_does_not_block_repository_only_probe(self):
        with self.assertRaisesRegex(ConformanceError, "PROJECT_STATE_PROFILE_MISSING"):
            recover_project_state(self.state_root, repository_root=self.repository_root)
        probe = probe_repository(ROOT)
        self.assertRegex(probe.verified_commit, r"^[0-9a-f]{40}$")

    def test_08_artifact_incident_and_backup_state_are_supported(self):
        store = initialize_project_state(self.state_root, repository_root=self.repository_root)
        store.register_root("SYNTHETIC_ROOT", self.protected_root, repository_root=self.repository_root)
        store.register_asset("SYNTHETIC_PACKAGE", "SYNTHETIC_ROOT", ".", "PROTECTED_PACKAGE_DIRECTORY")
        store.register_artifact("SYNTHETIC_ARTIFACT", "SYNTHETIC_PACKAGE", "MODEL_PACKAGE", "recoverable")
        store.record_incident("SYNTHETIC_INCIDENT", "PARSER_BOUNDARY", "recorded", "SYNTHETIC_NO_DISCLOSURE")
        store.set_backup_state("SYNTHETIC_BACKUP", "ready")
        store.verify()

    def test_09_stale_profile_and_asset_catalog_are_publishable_states(self):
        store = initialize_project_state(self.state_root, repository_root=self.repository_root)
        store.set_profile_status("stale")
        store.register_root("SYNTHETIC_ROOT", self.protected_root, status="stale", repository_root=self.repository_root)
        store.register_asset("SYNTHETIC_PACKAGE", "SYNTHETIC_ROOT", ".", "PROTECTED_PACKAGE_DIRECTORY", status="stale")
        facts = store.readiness_facts()
        self.assertEqual(facts["project_profile"], "stale")
        self.assertEqual(facts["asset_catalog"], "stale")

    def test_10_immutable_original_and_source_provenance_cannot_be_retargeted(self):
        store = initialize_project_state(self.state_root, repository_root=self.repository_root)
        store.register_root("SYNTHETIC_ROOT", self.protected_root, repository_root=self.repository_root)
        source = self.protected_root / "source.xlsx"
        source.write_bytes(b"synthetic")
        store.register_asset("SYNTHETIC_SOURCE_ASSET", "SYNTHETIC_ROOT", "source.xlsx", "ORIGINAL_SOURCE_FILE", immutable_original=True)
        store.register_source("SYNTHETIC_SOURCE", "SYNTHETIC_SOURCE_ASSET", "VINTAGE_2026", "SYNTHETIC_MEASURE", "ready")
        with self.assertRaisesRegex(ConformanceError, "PROJECT_STATE_IMMUTABLE_ORIGINAL_REJECTED"):
            store.register_asset("SYNTHETIC_SOURCE_ASSET", "SYNTHETIC_ROOT", ".", "ORIGINAL_SOURCE_FILE", immutable_original=True)
        with self.assertRaisesRegex(ConformanceError, "PROJECT_STATE_SOURCE_PROVENANCE_REJECTED"):
            store.register_source("SYNTHETIC_SOURCE", "SYNTHETIC_SOURCE_ASSET", "VINTAGE_2027", "SYNTHETIC_MEASURE", "ready")
        store.register_asset("MUTABLE_SOURCE_ASSET", "SYNTHETIC_ROOT", ".", "SOURCE_DIRECTORY")
        with self.assertRaisesRegex(ConformanceError, "PROJECT_STATE_SOURCE_IMMUTABILITY_REQUIRED"):
            store.register_source("MUTABLE_SOURCE", "MUTABLE_SOURCE_ASSET", "VINTAGE_2026", "SYNTHETIC_MEASURE", "ready")

    def test_11_existing_ledger_version_and_shape_are_never_rewritten(self):
        store = initialize_project_state(self.state_root, repository_root=self.repository_root)
        connection = sqlite3.connect(store.ledger_path)
        try:
            connection.execute("UPDATE metadata SET value = '2' WHERE key = 'schema_version'")
            connection.execute("PRAGMA user_version = 2")
            connection.commit()
        finally:
            connection.close()
        with self.assertRaisesRegex(ConformanceError, "PROJECT_STATE_LEDGER_VERSION_MISMATCH"):
            initialize_project_state(self.state_root, repository_root=self.repository_root)
        connection = sqlite3.connect(store.ledger_path)
        try:
            self.assertEqual(connection.execute("SELECT value FROM metadata WHERE key = 'schema_version'").fetchone()[0], "2")
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 2)
        finally:
            connection.close()

    def test_12_partial_inventory_requires_explicit_completeness(self):
        store = initialize_project_state(self.state_root, repository_root=self.repository_root)
        store.register_root("SYNTHETIC_ROOT", self.protected_root, repository_root=self.repository_root)
        source = self.protected_root / "source.xlsx"
        source.write_bytes(b"synthetic")
        store.register_asset("SYNTHETIC_SOURCE_ASSET", "SYNTHETIC_ROOT", "source.xlsx", "ORIGINAL_SOURCE_FILE", immutable_original=True)
        store.register_source("SYNTHETIC_SOURCE", "SYNTHETIC_SOURCE_ASSET", "VINTAGE_2026", "SYNTHETIC_MEASURE", "ready")
        self.assertEqual(store.readiness_facts()["original_source_inventory"], "incomplete")
        store.set_source_inventory_completeness("ready")
        self.assertEqual(store.readiness_facts()["original_source_inventory"], "ready")

    def test_13_state_and_protected_roots_reject_git_or_unbounded_locations(self):
        git_root = self.root / "git-repository"
        git_root.mkdir()
        (git_root / ".git").mkdir()
        with self.assertRaisesRegex(ConformanceError, "PROJECT_STATE_INSIDE_WORKTREE"):
            recover_project_state(git_root / "nested", repository_root=self.repository_root)
        with self.assertRaisesRegex(ConformanceError, "PROJECT_STATE_ROOT_SCOPE_INVALID"):
            initialize_project_state(Path(self.root.anchor), repository_root=self.repository_root)
        with self.assertRaisesRegex(ConformanceError, "PROJECT_STATE_ROOT_SCOPE_INVALID"):
            initialize_project_state(Path.home(), repository_root=self.repository_root)
        with self.assertRaisesRegex(ConformanceError, "PROJECT_STATE_INSIDE_WORKTREE"):
            initialize_project_state(self.root, repository_root=self.repository_root)
        store = initialize_project_state(self.state_root, repository_root=self.repository_root)
        with self.assertRaisesRegex(ConformanceError, "PROJECT_STATE_ROOT_INSIDE_WORKTREE"):
            store.register_root("BROAD_ROOT", self.repository_root, repository_root=self.repository_root)
        with self.assertRaisesRegex(ConformanceError, "PROJECT_STATE_ROOT_SCOPE_INVALID"):
            store.register_root("FILESYSTEM_ROOT", Path(self.root.anchor), repository_root=self.repository_root)

    def test_14_unready_asset_status_does_not_resolve(self):
        store = initialize_project_state(self.state_root, repository_root=self.repository_root)
        store.register_root("SYNTHETIC_ROOT", self.protected_root, status="stale", repository_root=self.repository_root)
        store.register_asset("SYNTHETIC_PACKAGE", "SYNTHETIC_ROOT", ".", "PROTECTED_PACKAGE_DIRECTORY", status="stale")
        with self.assertRaisesRegex(ConformanceError, "PROJECT_STATE_ASSET_UNRESOLVED"):
            store.resolve_asset("SYNTHETIC_PACKAGE")

    def test_15_protected_state_files_and_sidecars_fail_without_path_disclosure(self):
        for candidate in (
            "schemas/evidence.sqlite3",
            "synthetic/scg_project_profile.json",
            "local/evidence.sqlite3-wal",
            "local/evidence.sqlite3-shm",
            "local/evidence.sqlite3-journal",
            "local/scg_project_profile.json.backup",
        ):
            with self.subTest(candidate=candidate):
                with self.assertRaises(ConformanceError) as caught:
                    assert_no_protected_tracked_paths([candidate])
                self.assertEqual(caught.exception.code, "PROTECTED_TRACKED_PATH_REJECTED")
                self.assertNotIn(candidate, str(caught.exception))

    @unittest.skipIf(os.name == "nt", "Windows uses the per-user profile ACL")
    def test_16_posix_state_permissions_are_owner_only(self):
        store = initialize_project_state(self.state_root, repository_root=self.repository_root)
        self.assertEqual(stat.S_IMODE(store.state_root.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(store.profile_path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(store.ledger_path.stat().st_mode), 0o600)

    def test_17_evidence_unit_identity_cannot_be_rebound(self):
        store = initialize_project_state(self.state_root, repository_root=self.repository_root)
        store.register_evidence_unit(
            "LOCATION_ALPHA",
            "reconciled",
            "EVIDENCE_ALPHA",
            "VINTAGE_2026",
            "SYNTHETIC_MEASURE",
            "ready",
        )
        with self.assertRaisesRegex(ConformanceError, "PROJECT_STATE_EVIDENCE_PROVENANCE_REJECTED"):
            store.register_evidence_unit(
                "LOCATION_BETA",
                "reconciled",
                "EVIDENCE_ALPHA",
                "VINTAGE_2027",
                "SYNTHETIC_MEASURE",
                "ready",
            )

    def test_18_foreign_key_breakage_fails_recovery(self):
        store = initialize_project_state(self.state_root, repository_root=self.repository_root)
        connection = sqlite3.connect(store.ledger_path)
        try:
            connection.execute("PRAGMA foreign_keys = OFF")
            connection.execute(
                "INSERT INTO model_evidence_membership(model_id, evidence_unit_id, usage_role, registered_at) VALUES (?, ?, ?, ?)",
                ("MISSING_MODEL", "MISSING_EVIDENCE", "development", "2026-08-31T00:00:00Z"),
            )
            connection.commit()
        finally:
            connection.close()
        with self.assertRaisesRegex(ConformanceError, "PROJECT_STATE_LEDGER_FOREIGN_KEY_INVALID"):
            recover_project_state(self.state_root, repository_root=self.repository_root)

    def test_19_state_file_symlink_is_rejected(self):
        store = initialize_project_state(self.state_root, repository_root=self.repository_root)
        outside_profile = self.root / "outside-profile.json"
        outside_profile.write_text(store.profile_path.read_text(encoding="utf-8"), encoding="utf-8")
        store.profile_path.unlink()
        try:
            store.profile_path.symlink_to(outside_profile)
        except OSError:
            self.skipTest("symbolic links are unavailable in this Windows test environment")
        with self.assertRaisesRegex(ConformanceError, "PROJECT_STATE_SYMLINK_REJECTED"):
            recover_project_state(self.state_root, repository_root=self.repository_root)

    def test_20_nonempty_override_directory_is_not_modified(self):
        override = self.root / "unrelated-directory"
        override.mkdir()
        marker = override / "keep.txt"
        marker.write_text("synthetic unrelated content", encoding="utf-8")
        with self.assertRaises(ConformanceError) as caught:
            initialize_project_state(override, repository_root=self.repository_root)
        self.assertEqual(caught.exception.code, "PROJECT_STATE_ROOT_NOT_DEDICATED")
        self.assertNotIn(str(override), str(caught.exception))
        self.assertEqual(marker.read_text(encoding="utf-8"), "synthetic unrelated content")
        self.assertFalse((override / "scg_project_profile.json").exists())
        self.assertFalse((override / "evidence.sqlite3").exists())


if __name__ == "__main__":
    unittest.main()
