from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
TEST_TEMP_ROOT = Path(os.environ.get("READINESS_TEST_TEMP_ROOT", tempfile.gettempdir()))
TEST_TEMP_ROOT.mkdir(parents=True, exist_ok=True)

from sprouts_customer_geography.readiness.repository import (
    InitiativeWorktree,
    _initiative_id,
    _parse_local_task_refs,
    probe_repository,
    verify_initiative_commit,
)


def _git(repository: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", *arguments],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    ).stdout.strip()


class ReadinessRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(
            prefix="gov16-repository-", dir=TEST_TEMP_ROOT
        )
        self.root = Path(self.temporary.name)
        self.remote = self.root / "remote.git"
        self.repository = self.root / "repository"
        self.repository.mkdir()
        _git(self.root, "init", "--bare", str(self.remote))
        _git(self.repository, "init", "-b", "main")
        _git(self.repository, "config", "user.name", "Synthetic Readiness Test")
        _git(self.repository, "config", "user.email", "synthetic@example.invalid")
        (self.repository / "baseline.txt").write_text("baseline\n", encoding="utf-8")
        _git(self.repository, "add", "baseline.txt")
        _git(self.repository, "commit", "-m", "synthetic baseline")
        _git(self.repository, "remote", "add", "origin", str(self.remote))
        _git(self.repository, "push", "-u", "origin", "main")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _make_unlinked_ahead_branch(self, branch: str) -> None:
        _git(self.repository, "switch", "-c", branch, "main")
        _git(self.repository, "push", "-u", "origin", branch)
        (self.repository / "ahead.txt").write_text("ahead\n", encoding="utf-8")
        _git(self.repository, "add", "ahead.txt")
        _git(self.repository, "commit", "-m", "synthetic local ahead commit")

    def test_01_local_task_ref_parser_and_family_filter_are_closed(self):
        parsed = _parse_local_task_refs(
            "refs/heads/task/model-14-unlinked\trefs/remotes/origin/task/model-14-unlinked\n"
            "refs/heads/task/secret-42-hidden\trefs/remotes/origin/task/secret-42-hidden\n"
        )
        self.assertEqual(len(parsed), 2)
        self.assertEqual(_initiative_id(parsed[0][0]), "MODEL-14")
        self.assertIsNone(_initiative_id(parsed[1][0]))

    def test_02_unlinked_ahead_branch_is_merged_with_linked_initiative(self):
        self._make_unlinked_ahead_branch("task/model-14-unlinked")
        _git(self.repository, "switch", "-c", "task/model-14-linked", "main")
        _git(self.repository, "push", "-u", "origin", "task/model-14-linked")

        probe = probe_repository(self.repository, {"MODEL-14": "frozen"})
        expected = InitiativeWorktree("MODEL-14", "clean", "detected")
        self.assertEqual(probe.active_initiatives, (expected,))
        self.assertEqual(probe.safe_work, (expected,))
        self.assertEqual(probe.worktree_state, "known-preserved-work")
        rendered = repr(probe)
        self.assertNotIn("unlinked", rendered)
        self.assertNotIn(str(self.root), rendered)

    def test_03_untrusted_branch_is_hidden_but_drives_aggregate_attention(self):
        self._make_unlinked_ahead_branch("task/secret-42-hidden")
        _git(self.repository, "switch", "main")

        probe = probe_repository(self.repository)
        self.assertEqual(probe.active_initiatives, ())
        self.assertEqual(probe.safe_work, ())
        self.assertEqual(probe.worktree_state, "attention-needed")
        self.assertNotIn("SECRET-42", repr(probe))

    def test_04_linked_unknown_push_state_requires_attention(self):
        _git(self.repository, "switch", "-c", "task/gov-16-linked", "main")
        with patch(
            "sprouts_customer_geography.readiness.repository._push_state",
            return_value="unknown",
        ), patch(
            "sprouts_customer_geography.readiness.repository._local_task_refs",
            return_value=(),
        ):
            probe = probe_repository(self.repository)
        self.assertEqual(
            probe.active_initiatives,
            (InitiativeWorktree("GOV-16", "clean", "unknown"),),
        )
        self.assertEqual(probe.worktree_state, "attention-needed")

    def test_05_synchronized_unlinked_historical_branch_is_not_active(self):
        _git(self.repository, "branch", "task/data-100-historical", "main")
        _git(self.repository, "push", "-u", "origin", "task/data-100-historical")
        probe = probe_repository(self.repository)
        self.assertNotIn("DATA-100", {item.initiative_id for item in probe.active_initiatives})

    def test_06_three_digit_codex_initiative_and_preservation_ref_are_supported(self):
        _git(self.repository, "switch", "-c", "codex/gov-100-boundary", "main")
        commit = _git(self.repository, "rev-parse", "HEAD")
        self.assertEqual(_initiative_id("refs/heads/codex/gov-100-boundary"), "GOV-100")
        self.assertTrue(verify_initiative_commit(self.repository, "GOV-100", commit))

    def test_07_behind_and_diverged_linked_branches_require_attention(self):
        branch = "task/gov-16-linked"
        _git(self.repository, "switch", "-c", branch, "main")
        _git(self.repository, "push", "-u", "origin", branch)
        updater = self.root / "updater"
        _git(self.root, "clone", str(self.remote), str(updater))
        _git(updater, "config", "user.name", "Synthetic Remote Updater")
        _git(updater, "config", "user.email", "updater@example.invalid")
        _git(updater, "switch", branch)
        (updater / "remote.txt").write_text("remote ahead\n", encoding="utf-8")
        _git(updater, "add", "remote.txt")
        _git(updater, "commit", "-m", "synthetic remote advance")
        _git(updater, "push", "origin", branch)
        _git(self.repository, "fetch", "origin")

        behind = probe_repository(self.repository)
        self.assertEqual(behind.active_initiatives[0].push_state, "unknown")
        self.assertEqual(behind.worktree_state, "attention-needed")

        (self.repository / "local.txt").write_text("local ahead\n", encoding="utf-8")
        _git(self.repository, "add", "local.txt")
        _git(self.repository, "commit", "-m", "synthetic local divergence")
        diverged = probe_repository(self.repository)
        self.assertEqual(diverged.active_initiatives[0].push_state, "unknown")
        self.assertEqual(diverged.worktree_state, "attention-needed")


if __name__ == "__main__":
    unittest.main()
