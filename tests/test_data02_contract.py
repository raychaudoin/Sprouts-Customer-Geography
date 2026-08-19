from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from sprouts_customer_geography.pipe01.canonical import content_digest
from sprouts_customer_geography.pipe01.data_contracts import validate_data02_contract
from sprouts_customer_geography.pipe01.errors import ConformanceError
from sprouts_customer_geography.pipe01.sources import verify_pinned_source


ROOT = Path(__file__).resolve().parents[1]


def load(relative: str):
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def rehash_manifest(value):
    hashed = copy.deepcopy(value)
    hashed.pop("manifest_content_sha256")
    value["manifest_content_sha256"] = content_digest(hashed)


class Data02AuthoritativeContractTests(unittest.TestCase):
    def setUp(self):
        self.config = load("config/data/data01_validation_source_contract.json")
        self.tiger = load("data/manifests/tiger_2024_wisconsin_tract.source_manifest.json")
        self.acs = load("data/manifests/acs_2024_acs5_b11001_wisconsin_tract.source_manifest.json")

    def test_authoritative_contract_hashes_and_identities_are_deterministic(self):
        first = validate_data02_contract(self.config, self.tiger, self.acs)
        second = validate_data02_contract(self.config, self.tiger, self.acs)
        self.assertEqual(first, second)
        self.assertEqual(first["data01_config_version"], "1.0.0")
        self.assertEqual(first["tiger_source_sha256"], "313c378d7fa173bf653381d644d8ded7b4f6241b2065d2b890e1fccccaab5de5")
        self.assertEqual(first["acs_source_identity"], "census-acs-2024-acs5-detailed-b11001")
        self.assertEqual(first["acs_retrieval_manifest_sha256"], "3beb2f39ef4f0ba02953322da4fef0bc7136947d228dbf4d1353c0b5a94424ce")

    def test_moving_source_alias_is_rejected(self):
        changed = copy.deepcopy(self.config)
        changed["accepted_sources"][0]["vintage"] = "latest"
        with self.assertRaisesRegex(ConformanceError, "DATA_MOVING_IDENTITY_REJECTED"):
            validate_data02_contract(changed, self.tiger, self.acs)

    def test_tiger_checksum_mismatch_fails_closed(self):
        with self.assertRaisesRegex(ConformanceError, "SOURCE_CHECKSUM_MISMATCH"):
            verify_pinned_source(self.tiger, b"not the accepted Census ZIP")

    def test_acs_vintage_schema_and_required_fields_fail_closed(self):
        wrong_vintage = copy.deepcopy(self.acs)
        wrong_vintage["accepted_vintage"] = "2025"
        with self.assertRaisesRegex(ConformanceError, "DATA_SOURCE_VINTAGE_MISMATCH"):
            validate_data02_contract(self.config, self.tiger, wrong_vintage)
        missing_moe = copy.deepcopy(self.acs)
        missing_moe["request_identity"]["header_required"].remove("B11001_M001")
        rehash_manifest(missing_moe)
        with self.assertRaisesRegex(ConformanceError, "ACS_REQUEST_HASH_MISMATCH|ACS_REQUIRED_FIELD_MISSING"):
            validate_data02_contract(self.config, self.tiger, missing_moe)

    def test_missing_manifest_identity_and_tampered_hash_fail_closed(self):
        missing_id = copy.deepcopy(self.tiger)
        missing_id.pop("manifest_id")
        with self.assertRaisesRegex(ConformanceError, "DATA_MANIFEST_INCOMPLETE"):
            validate_data02_contract(self.config, missing_id, self.acs)
        tampered = copy.deepcopy(self.config)
        tampered["version"] = "1.0.1"
        with self.assertRaisesRegex(ConformanceError, "DATA_CONFIG_VERSION_MISMATCH"):
            validate_data02_contract(tampered, self.tiger, self.acs)

    def test_authoritative_manifest_schema_reuses_pipe_source_manifest_schema(self):
        schema = load("schemas/pipe01/source_manifest.schema.json")
        self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertEqual(self.tiger["$schema"], "../../schemas/pipe01/source_manifest.schema.json")
        self.assertEqual(self.acs["$schema"], "../../schemas/pipe01/source_manifest.schema.json")
        allowed = set(schema["properties"])
        for manifest in (self.tiger, self.acs):
            self.assertFalse(set(manifest) - allowed)
            self.assertTrue(set(schema["required"]) <= set(manifest))


if __name__ == "__main__":
    unittest.main()
