from __future__ import annotations

import copy
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
TEST_TEMP_ROOT = Path(os.environ.get("READINESS_TEST_TEMP_ROOT", tempfile.gettempdir()))
TEST_TEMP_ROOT.mkdir(parents=True, exist_ok=True)

from sprouts_customer_geography.pipe01.errors import ConformanceError
from sprouts_customer_geography.readiness.disclosure import (
    load_and_validate_development_readiness,
    validate_development_readiness,
    validate_development_readiness_schema,
)


SCHEMA = ROOT / "schemas" / "readiness" / "development_readiness.schema.json"
APPROVED = {
    "schema_version": "1.0.0",
    "snapshot_id": "development-readiness-v1",
    "generated_at_utc": "2026-08-31T04:30:00Z",
    "repository": {
        "verified_commit": "a" * 40,
        "worktree_state": "KNOWN_PRESERVED_WORK",
        "active_initiatives": [
            {
                "initiative_id": "GOV-16",
                "worktree_state": "CLEAN",
                "push_state": "SYNCHRONIZED",
            },
            {
                "initiative_id": "MODEL-14",
                "worktree_state": "KNOWN_PRESERVED_WORK",
                "push_state": "UNPUSHED_SAFE_WORK",
            },
        ],
        "safe_work": [
            {
                "initiative_id": "MODEL-14",
                "state": "UNCOMMITTED_AND_UNPUSHED",
            }
        ],
    },
    "protected_state": {
        "project_profile": "READY",
        "asset_catalog": "READY",
        "original_source_inventory": "INCOMPLETE",
        "evidence_ledger": "READY",
        "model13_authority": "REGISTERED_RECOVERABLE",
        "app01_inputs": "REGISTERED_RECOVERABLE",
    },
    "preservation": {
        "model14": "PRESERVED",
        "model15": "PRESERVED",
    },
    "recovery": {"fresh_session": "SUCCEEDED"},
    "prerequisites": [
        {"code": "REPOSITORY_READINESS", "status": "READY"},
        {"code": "PROTECTED_PROJECT_PROFILE", "status": "READY"},
        {"code": "PROTECTED_ASSET_CATALOG", "status": "READY"},
        {"code": "ORIGINAL_SOURCE_INVENTORY", "status": "NEEDS_RUNWAY"},
        {"code": "EVIDENCE_LEDGER", "status": "READY"},
        {"code": "MODEL13_AUTHORITY", "status": "READY"},
        {"code": "APP01_INPUT_PACKAGE", "status": "READY"},
        {"code": "MODEL14_PRESERVATION", "status": "READY"},
        {"code": "MODEL15_PRESERVATION", "status": "READY"},
        {"code": "FRESH_SESSION_RECOVERY", "status": "READY"},
    ],
}


class ReadinessDisclosureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schema = json.loads(SCHEMA.read_text(encoding="utf-8"))

    def candidate(self):
        return copy.deepcopy(APPROVED)

    def test_01_approved_document_and_schema_pass(self):
        validate_development_readiness_schema(self.schema)
        result = validate_development_readiness(self.candidate(), schema=self.schema)
        self.assertEqual(result["repository"]["verified_commit"], "a" * 40)

    def test_02_schema_closes_every_publishable_object(self):
        object_schemas = []

        def visit(value):
            if isinstance(value, dict):
                if value.get("type") == "object":
                    object_schemas.append(value)
                for member in value.values():
                    visit(member)
            elif isinstance(value, list):
                for member in value:
                    visit(member)

        visit(self.schema)
        self.assertGreaterEqual(len(object_schemas), 7)
        self.assertTrue(all(item.get("additionalProperties") is False for item in object_schemas))
        self.assertEqual(
            self.schema["properties"]["repository"]["properties"]["verified_commit"]["pattern"],
            "^[0-9a-f]{40}$",
        )

    def test_03_unknown_top_level_and_nested_fields_are_rejected(self):
        cases = []
        top_level = self.candidate()
        top_level["notes"] = "READY"
        cases.append(top_level)
        nested = self.candidate()
        nested["repository"]["active_initiatives"][0]["branch"] = "GOV-16"
        cases.append(nested)
        prerequisite = self.candidate()
        prerequisite["prerequisites"][0]["detail"] = "READY"
        cases.append(prerequisite)
        for candidate in cases:
            with self.subTest(candidate=candidate):
                with self.assertRaisesRegex(ConformanceError, "READINESS_FIELD_PROHIBITED"):
                    validate_development_readiness(candidate)

    def test_04_absolute_unc_unix_file_uri_and_relative_paths_are_rejected(self):
        cases = {
            "windows": r"C:\Protected\source.xlsx",
            "unc": r"\\server\share\source.xlsx",
            "unix": "/srv/protected/source.xlsx",
            "file_uri": "file:///C:/Protected/source.xlsx",
            "relative": "protected/source.xlsx",
        }
        for name, value in cases.items():
            with self.subTest(name=name):
                candidate = self.candidate()
                candidate["repository"]["worktree_state"] = value
                with self.assertRaises(ConformanceError):
                    validate_development_readiness(candidate)

    def test_05_path_traversal_is_rejected_before_publication(self):
        for value in ("../protected/source.xlsx", r"..\protected\source.xlsx", "%2e%2e/protected"):
            with self.subTest(value=value):
                candidate = self.candidate()
                candidate["repository"]["worktree_state"] = value
                with self.assertRaisesRegex(ConformanceError, "READINESS_PATH_TRAVERSAL_REJECTED"):
                    validate_development_readiness(candidate)

    def test_06_coordinates_are_rejected(self):
        for value in ("43.0389, -87.9065", "POINT (-87.9065 43.0389)", "latitude=43.0389"):
            with self.subTest(value=value):
                candidate = self.candidate()
                candidate["repository"]["worktree_state"] = value
                with self.assertRaisesRegex(ConformanceError, "READINESS_COORDINATE_REJECTED"):
                    validate_development_readiness(candidate)

    def test_07_target_like_values_are_rejected(self):
        for value in ("TARGET-42", "isolated_sales", "forecast value"):
            with self.subTest(value=value):
                candidate = self.candidate()
                candidate["repository"]["active_initiatives"][0]["initiative_id"] = value
                with self.assertRaisesRegex(ConformanceError, "READINESS_TARGET_VALUE_REJECTED"):
                    validate_development_readiness(candidate)

    def test_08_row_identities_are_rejected(self):
        for value in ("ROW-42", "m12obs-synthetic-1", "SeedPointID-7", "A42", "26163540100"):
            with self.subTest(value=value):
                candidate = self.candidate()
                candidate["repository"]["active_initiatives"][0]["initiative_id"] = value
                with self.assertRaisesRegex(ConformanceError, "READINESS_ROW_IDENTITY_REJECTED"):
                    validate_development_readiness(candidate)

    def test_09_revealing_hashes_are_rejected_outside_exact_commit_field(self):
        candidate = self.candidate()
        candidate["repository"]["worktree_state"] = "b" * 64
        with self.assertRaisesRegex(ConformanceError, "READINESS_DIGEST_REJECTED"):
            validate_development_readiness(candidate)
        candidate = self.candidate()
        candidate["repository"]["verified_commit"] = "b" * 64
        with self.assertRaisesRegex(ConformanceError, "READINESS_COMMIT_INVALID"):
            validate_development_readiness(candidate)

    def test_10_arbitrary_numbers_booleans_and_free_text_are_rejected(self):
        for value in (42, 3.14, True, "arbitrary narrative about local evidence"):
            with self.subTest(value=value):
                candidate = self.candidate()
                candidate["repository"]["worktree_state"] = value
                with self.assertRaises(ConformanceError):
                    validate_development_readiness(candidate)

    def test_11_snapshot_time_and_commit_make_staleness_visible(self):
        candidate = self.candidate()
        candidate["generated_at_utc"] = "2026-02-30T04:30:00Z"
        with self.assertRaisesRegex(ConformanceError, "READINESS_TIMESTAMP_INVALID"):
            validate_development_readiness(candidate)
        candidate = self.candidate()
        candidate["repository"]["verified_commit"] = "A" * 40
        with self.assertRaisesRegex(ConformanceError, "READINESS_COMMIT_INVALID"):
            validate_development_readiness(candidate)

    def test_12_duplicate_or_orphaned_coded_entries_are_rejected(self):
        duplicate = self.candidate()
        duplicate["prerequisites"][-1] = copy.deepcopy(duplicate["prerequisites"][0])
        with self.assertRaisesRegex(ConformanceError, "READINESS_DUPLICATE_PREREQUISITE"):
            validate_development_readiness(duplicate)
        orphaned = self.candidate()
        orphaned["repository"]["safe_work"][0]["initiative_id"] = "MODEL-15"
        with self.assertRaisesRegex(ConformanceError, "READINESS_SAFE_WORK_ORPHANED"):
            validate_development_readiness(orphaned)

    def test_13_loader_binds_document_to_schema(self):
        fixture = ROOT / "tests" / "__absent_readiness_disclosure_fixture.json"
        self.assertFalse(fixture.exists())
        with self.assertRaisesRegex(ConformanceError, "READINESS_DOCUMENT_UNREADABLE"):
            load_and_validate_development_readiness(fixture, SCHEMA)

    def test_14_mutated_nested_schema_is_rejected(self):
        mutated = copy.deepcopy(self.schema)
        mutated["properties"]["protected_state"]["properties"]["asset_catalog"]["enum"].append(
            "UNSAFE_EXTENSION"
        )
        with self.assertRaisesRegex(ConformanceError, "READINESS_SCHEMA_INVALID"):
            validate_development_readiness(self.candidate(), schema=mutated)

    def test_15_initiative_family_is_closed(self):
        candidate = self.candidate()
        candidate["repository"]["active_initiatives"][0]["initiative_id"] = "SECRET-42"
        with self.assertRaisesRegex(ConformanceError, "READINESS_INITIATIVE_ID_INVALID"):
            validate_development_readiness(candidate)

    def test_16_all_prerequisites_are_required_and_exactly_derived(self):
        missing = self.candidate()
        missing["prerequisites"].pop()
        with self.assertRaisesRegex(ConformanceError, "READINESS_PREREQUISITE_SET_INVALID"):
            validate_development_readiness(missing)

        contradictory = self.candidate()
        contradictory["prerequisites"][0]["status"] = "NEEDS_RUNWAY"
        with self.assertRaisesRegex(
            ConformanceError, "READINESS_PREREQUISITE_STATUS_MISMATCH"
        ):
            validate_development_readiness(contradictory)

    def test_17_safe_work_must_exactly_match_active_work(self):
        missing = self.candidate()
        missing["repository"]["safe_work"] = []
        with self.assertRaisesRegex(ConformanceError, "READINESS_SAFE_WORK_SET_MISMATCH"):
            validate_development_readiness(missing)

        contradictory = self.candidate()
        contradictory["repository"]["safe_work"][0]["state"] = "UNPUSHED"
        with self.assertRaisesRegex(
            ConformanceError, "READINESS_SAFE_WORK_STATE_MISMATCH"
        ):
            validate_development_readiness(contradictory)

    def test_18_overall_repository_state_cannot_hide_active_work(self):
        candidate = self.candidate()
        candidate["repository"]["worktree_state"] = "CLEAN"
        with self.assertRaisesRegex(
            ConformanceError, "READINESS_REPOSITORY_STATE_CONTRADICTION"
        ):
            validate_development_readiness(candidate)

        hidden_attention = self.candidate()
        hidden_attention["repository"] = {
            "verified_commit": "a" * 40,
            "worktree_state": "ATTENTION_NEEDED",
            "active_initiatives": [],
            "safe_work": [],
        }
        hidden_attention["prerequisites"][0]["status"] = "NEEDS_RUNWAY"
        validate_development_readiness(hidden_attention)

    def test_19_duplicate_json_keys_are_rejected_for_document_and_schema(self):
        with tempfile.TemporaryDirectory(
            prefix="gov16-disclosure-", dir=TEST_TEMP_ROOT
        ) as temporary:
            root = Path(temporary)
            duplicate_document = root / "duplicate-document.json"
            duplicate_document.write_text(
                '{"schema_version":"1.0.0","schema_version":"1.0.0"}',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                ConformanceError, "READINESS_DOCUMENT_UNREADABLE"
            ):
                load_and_validate_development_readiness(duplicate_document, SCHEMA)

            document = root / "document.json"
            document.write_text(json.dumps(self.candidate()), encoding="utf-8")
            duplicate_schema = root / "duplicate-schema.json"
            schema_text = SCHEMA.read_text(encoding="utf-8")
            identifier = (
                '  "$id": "urn:sprouts-customer-geography:readiness:'
                'development-readiness:v1",'
            )
            self.assertIn(identifier, schema_text)
            duplicate_schema.write_text(
                schema_text.replace(identifier, identifier + "\n" + identifier, 1),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                ConformanceError, "READINESS_SCHEMA_UNREADABLE"
            ):
                load_and_validate_development_readiness(document, duplicate_schema)


if __name__ == "__main__":
    unittest.main()
