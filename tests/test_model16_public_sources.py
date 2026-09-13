"""Public-only historical admission and complete-manifest drift contracts."""
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from sprouts_customer_geography.model16 import public_sources as s
from sprouts_customer_geography.pipe01.errors import ConformanceError


class PublicSourceManifestTests(unittest.TestCase):
    def test_later_revision_is_rejected_even_for_old_reference_year(self):
        with self.assertRaisesRegex(ConformanceError, "MODEL16_SOURCE_AFTER_HISTORICAL_CUTOFF"):
            s.classify("ACS2023_B11001", {"http_last_modified": "Thu, 01 Jan 2026 00:00:00 GMT"})
        self.assertEqual(s.classify("ACS2024_B11001")["admitted_forecast_years"], [])
        self.assertEqual(s.classify("ACS2024_B11001_SCHEMA")["analytical_role"], "REJECTED_PRIMARY_TEMPORAL_REVISION")

    def test_no_2026_acs_vintage_gain_and_fixed_geometry(self):
        self.assertEqual(s.classify("ACS2023_B11001")["admitted_forecast_years"], [2025, 2026])
        self.assertEqual(s.classify("TIGER2023_26")["admitted_forecast_years"], [2024, 2025, 2026])
        self.assertEqual(s.classify("TIGER2024_55")["admitted_forecast_years"], [])
        self.assertEqual(s.classify("TIGER2025_55")["admitted_forecast_years"], [])

    def test_metadata_is_schema_evidence_and_missing_raw_dates_fail(self):
        self.assertEqual(s.classify("ACS2023_B11001_SCHEMA", {"http_last_modified": None})["analytical_role"], "ADMITTED_SCHEMA")
        with self.assertRaisesRegex(ConformanceError, "MODEL16_SOURCE_AVAILABILITY_MISSING"):
            s.classify("ACS2023_B11001", {"http_last_modified": None})

    def test_supplemental_dates_and_live_service_separation(self):
        self.assertEqual(s.classify("BPS2022_COUNTY")["admitted_forecast_years"], [2025])
        self.assertEqual(s.classify("CBP2021_COUNTY")["admitted_forecast_years"], [2024])
        self.assertEqual(s.classify("EPA_SLD2021_26_0")["analytical_role"], "CURRENT_SERVICE_QA_ONLY")
        self.assertEqual(s.classify("EPA_SLD2021_ORIGINAL_PACKAGE")["analytical_role"], "ADMITTED_SUPPLEMENTAL_DATA")
        with self.assertRaisesRegex(ConformanceError, "MODEL16_SOURCE_AFTER_HISTORICAL_CUTOFF"):
            s.classify("BPS2021_COUNTY", {"http_last_modified": "Mon, 01 Jan 2024 00:00:00 GMT"})

    def test_manifest_full_equality_rejects_changed_receipt_or_admission(self):
        expected = {"fictional_source": "hash-a", "admitted": False}
        with patch.object(Path, "read_text", return_value=json.dumps(expected)), patch.object(s, "build_manifest", return_value=expected):
            self.assertEqual(s.verify_manifest(Path("fictional"), Path("fictional-cache")), expected)
        for actual in ({**expected, "fictional_source": "hash-b"}, {**expected, "admitted": True}):
            with patch.object(Path, "read_text", return_value=json.dumps(expected)), patch.object(s, "build_manifest", return_value=actual):
                with self.assertRaisesRegex(ConformanceError, "MODEL16_PUBLIC_MANIFEST_DRIFT"):
                    s.verify_manifest(Path("fictional"), Path("fictional-cache"))


if __name__ == "__main__":
    unittest.main()
