from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sprouts_customer_geography.governance_surfaces import (
    DURABLE_SURFACE_PATHS,
    GovernanceSurfaceError,
    validate_durable_surface_texts,
    validate_governance_surfaces,
)


class GovernanceSurfaceTests(unittest.TestCase):
    def _surface_texts(self) -> dict[str, str]:
        return {
            path: (ROOT / path).read_text(encoding="utf-8")
            for path in DURABLE_SURFACE_PATHS
        }

    def test_01_repository_implements_four_surface_and_two_mailbox_contract(self):
        result = validate_governance_surfaces(ROOT)
        self.assertEqual(result["durable_instruction_surfaces"], "passed")
        self.assertEqual(result["development_custom_instructions"], "absent")
        self.assertEqual(result["active_mailbox_records"], "passed")
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


if __name__ == "__main__":
    unittest.main()
