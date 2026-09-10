from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sprouts_customer_geography.governance_surfaces import (
    AUTHORITY_CONSISTENCY_PATHS,
    DURABLE_SURFACE_PATHS,
    GovernanceSurfaceError,
    validate_authority_consistency_texts,
    validate_durable_surface_texts,
    validate_governance_surfaces,
)


class GovernanceSurfaceTests(unittest.TestCase):
    def _surface_texts(self) -> dict[str, str]:
        return {
            path: (ROOT / path).read_text(encoding="utf-8")
            for path in DURABLE_SURFACE_PATHS
        }

    def _authority_texts(self) -> dict[str, str]:
        return {
            path: (ROOT / path).read_text(encoding="utf-8")
            for path in AUTHORITY_CONSISTENCY_PATHS
        }

    def test_01_repository_implements_four_surface_and_two_mailbox_contract(self):
        result = validate_governance_surfaces(ROOT)
        self.assertEqual(result["durable_instruction_surfaces"], "passed")
        self.assertEqual(result["development_custom_instructions"], "absent")
        self.assertEqual(result["active_mailbox_records"], "passed")
        self.assertEqual(result["authority_consistency"], "passed")
        self.assertEqual(result["volatile_surface_state"], "absent")

    def test_02_volatile_candidate_state_is_rejected_from_durable_surfaces(self):
        texts = self._surface_texts()
        texts["AGENTS.md"] += "\nCurrent PR #45 is the active candidate.\n"
        with self.assertRaisesRegex(GovernanceSurfaceError, "GOVERNANCE_SURFACE_PR_ISSUE_VOLATILE"):
            validate_durable_surface_texts(texts)

    def test_03_hard_coded_model_inventory_is_rejected_from_durable_surfaces(self):
        texts = self._surface_texts()
        texts["AGENTS.md"] += "\nUse GPT-9 Example for every task.\n"
        with self.assertRaisesRegex(GovernanceSurfaceError, "GOVERNANCE_SURFACE_MODEL_INVENTORY_VOLATILE"):
            validate_durable_surface_texts(texts)

    def test_04_missing_surface_is_rejected(self):
        texts = self._surface_texts()
        texts.pop("AGENTS.md")
        with self.assertRaisesRegex(GovernanceSurfaceError, "GOVERNANCE_SURFACE_SET_INVALID"):
            validate_durable_surface_texts(texts)

    def test_05_issue_as_authority_wording_is_rejected(self):
        texts = self._authority_texts()
        path = ".github/ISSUE_TEMPLATE/initiative-brief.yml"
        texts[path] = texts[path].replace(
            "This Issue records the approved repository-safe objective, boundaries, prerequisites, and Work Order pointer.",
            "This Issue authorizes only its stated repository-safe objective.",
        )
        with self.assertRaisesRegex(GovernanceSurfaceError, "GOVERNANCE_ISSUE_OR_RECORD_AS_AUTHORITY"):
            validate_authority_consistency_texts(texts)

    def test_06_initiative_merge_preauthorization_wording_is_rejected(self):
        texts = self._authority_texts()
        path = ".github/PULL_REQUEST_TEMPLATE.md"
        texts[path] += "\n- Merge posture: Authorized by Initiative\n"
        with self.assertRaisesRegex(GovernanceSurfaceError, "GOVERNANCE_ISSUE_OR_RECORD_AS_AUTHORITY"):
            validate_authority_consistency_texts(texts)

    def test_07_derivative_evidence_authority_boundary_is_required(self):
        texts = self._authority_texts()
        path = "docs/governance/ACTIVE_MAILBOX_RECORDS.md"
        texts[path] = texts[path].replace("cannot create or enlarge authority", "may create authority")
        with self.assertRaisesRegex(GovernanceSurfaceError, "GOVERNANCE_AUTHORITY_BOUNDARY_MISSING"):
            validate_authority_consistency_texts(texts)

    def test_08_historical_evidence_is_outside_current_consistency_check(self):
        texts = self._authority_texts()
        texts["docs/work_orders/HISTORICAL_EXAMPLE.md"] = "This Issue authorizes a historical action."
        validate_authority_consistency_texts(texts)


if __name__ == "__main__":
    unittest.main()
