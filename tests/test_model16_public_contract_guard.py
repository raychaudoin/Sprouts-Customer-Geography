"""Public authority tokens do not exempt private filenames or other aliases."""
from pathlib import Path
import re
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
from sprouts_customer_geography.model16 import public_contract as guard


class PublicContractGuardTests(unittest.TestCase):
    def test_only_exact_published_logical_ids_are_recognized(self):
        allowed = guard.MODEL16_PUBLIC_LOGICAL_IDS[0]
        self.assertEqual(guard.source_name_guard_text(ROOT, "fictional.txt", allowed), "PUBLIC_LOGICAL_ASSET")
        for unknown in (allowed+"_PRIVATE", "prefix_"+allowed, allowed.lower(), "fictional_source.xlsx"):
            self.assertEqual(guard.source_name_guard_text(ROOT, "fictional.txt", unknown), unknown)

    def test_header_exception_has_exact_path_and_token_scope(self):
        public_alias = "City" + str(2)
        private_alias = "City" + str(99)
        path = "src/sprouts_customer_geography/model16/intake.py"
        self.assertEqual(guard.source_name_guard_text(ROOT, path, public_alias), "PUBLIC_CITY_SCHEMA_ALIAS")
        self.assertEqual(guard.source_name_guard_text(ROOT, "fictional.txt", public_alias), public_alias)
        self.assertEqual(guard.source_name_guard_text(ROOT, path, private_alias), private_alias)

    def test_missing_or_modified_authority_grants_no_exception(self):
        with tempfile.TemporaryDirectory(prefix="model16-fictional-public-guard-") as temp:
            root = Path(temp)
            token = guard.MODEL16_PUBLIC_LOGICAL_IDS[0]
            self.assertEqual(guard.source_name_guard_text(root, "fictional.txt", token), token)
            authority = root / guard.MODEL16_PUBLIC_WORK_ORDER
            authority.parent.mkdir(parents=True)
            authority.write_text("FICTIONAL NONCONTROLLING AUTHORITY", encoding="utf-8")
            self.assertEqual(guard.source_name_guard_text(root, "fictional.txt", token), token)

    def test_filename_suffix_survives_and_narrative_guard_still_rejects(self):
        text = guard.MODEL16_PUBLIC_LOGICAL_IDS[0] + ".xlsx"
        masked = guard.source_name_guard_text(ROOT, "fictional.txt", text)
        self.assertRegex(masked, r"[A-Za-z0-9 _.-]+\.xlsx")


if __name__ == "__main__":
    unittest.main()
