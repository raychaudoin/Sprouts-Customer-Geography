"""Fictional acquisition bytes test receipts, chronology, and crash recovery."""
from __future__ import annotations

import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sprouts_customer_geography.model16 import public_data


def acs_url(path: Path, vintage: int) -> str:
    return f"https://www2.census.gov/programs-surveys/acs/summary_file/{vintage}/table-based-SF/data/5YRData/{path.name}"


def receipt(path: Path, url: str, modified="Thu, 07 Dec 2023 12:00:00 GMT", *, bytes_path: Path | None = None):
    source = bytes_path or path
    result = {"url": url, "resolved_url": url, "sha256": public_data.digest_file(source), "byte_length": source.stat().st_size,
              "http_last_modified": modified, "retrieved_at_utc": "2026-09-13T00:00:00+00:00"}
    path.with_name(path.name + ".receipt.json").write_text(json.dumps(result), encoding="utf-8")
    return result


class Response(io.BytesIO):
    def __init__(self, url, payload=b"fictional public bytes"):
        super().__init__(payload)
        self.url = url
        self.headers = {"Last-Modified": "Thu, 07 Dec 2023 12:00:00 GMT"}
    def geturl(self):
        return self.url


class Model16PublicDataTests(unittest.TestCase):
    def test_acs_raw_integrity_identity_and_historical_revision(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "acsdt5y2022-b11001.dat"
            path.write_text("GEO_ID|B11001_E001|B11001_M001\n1400000US26001000100|100|5\n1400000US55001000100|120|6\n1400000US06001000100|999|9\n", encoding="utf-8")
            receipt(path, acs_url(path, 2022))
            result = public_data.read_acs_table(path, "B11001")
            self.assertEqual(set(result), {"26001000100", "55001000100"})
            receipt(path, acs_url(path, 2022), "Mon, 01 Jan 2024 00:00:00 GMT")
            with self.assertRaises(Exception):
                public_data.read_acs_table(path, "B11001")
            receipt(path, acs_url(path, 2022))
            path.write_text(path.read_text().replace("|100|", "|101|"), encoding="utf-8")
            with self.assertRaises(Exception):
                public_data.read_acs_table(path, "B11001")

    def test_2024_acs_revised_in_2026_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "acsdt5y2024-b11001.dat"
            path.write_text("GEO_ID|B11001_E001|B11001_M001\n1400000US26001000100|100|5\n", encoding="utf-8")
            receipt(path, acs_url(path, 2024), "Thu, 29 Jan 2026 12:00:00 GMT")
            with self.assertRaises(Exception):
                public_data.read_acs_table(path, "B11001")

    def test_missing_receipt_missing_revision_and_wrong_url_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "acsdt5y2022-b11001.dat"
            path.write_text("GEO_ID|B11001_E001|B11001_M001\n1400000US26001000100|100|5\n", encoding="utf-8")
            with self.assertRaises(Exception):
                public_data.read_acs_table(path, "B11001")
            receipt(path, acs_url(path, 2022), None)
            with self.assertRaises(Exception):
                public_data.read_acs_table(path, "B11001")
            receipt(path, "https://www2.census.gov/wrong-source")
            with self.assertRaises(Exception):
                public_data.read_acs_table(path, "B11001")

    def test_duplicate_keys_columns_and_invalid_row_width_are_rejected(self):
        variants = ["GEO_ID|B11001_E001|B11001_M001\n1400000US26001000100|100|5\n1400000US26001000100|200|6\n",
                    "GEO_ID|B11001_E001|B11001_M001|B11001_E001\n1400000US26001000100|100|5|200\n",
                    "GEO_ID|B11001_E001|B11001_M001\n1400000US26001000100|100\n"]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "acsdt5y2022-b11001.dat"
            for content in variants:
                path.write_text(content, encoding="utf-8")
                receipt(path, acs_url(path, 2022))
                with self.assertRaises(Exception):
                    public_data.read_acs_table(path, "B11001")

    def test_versioned_schema_receipt_and_hash_are_verified(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "acs2022-b11001.metadata.json"
            path.write_text(json.dumps({"variables": {"B11001_001E": {"label": "Estimate!!Total:"}}}), encoding="utf-8")
            url = "https://api.census.gov/data/2022/acs/acs5/groups/B11001.json"
            receipt(path, url, None)
            self.assertIn("variables", public_data.read_acs_metadata(path, "B11001", 2022))
            path.write_text("{}", encoding="utf-8")
            with self.assertRaises(Exception):
                public_data.read_acs_metadata(path, "B11001", 2022)

    def test_fixed_geometry_cannot_use_a_later_revised_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tl_2023_26_tract.zip"
            path.write_bytes(b"synthetic geometry container")
            url = "https://www2.census.gov/geo/tiger/TIGER2023/TRACT/tl_2023_26_tract.zip"
            receipt(path, url, "Fri, 27 Jun 2025 12:00:00 GMT")
            with self.assertRaises(Exception):
                public_data.verify_receipt(path, expected_url=url, latest_allowed_year=2023)

    def test_recover_old_receipt_before_rename_without_network_or_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "synthetic-public.dat"
            partial = destination.with_name(destination.name + ".partial-123")
            partial.write_bytes(b"synthetic immutable acquisition")
            other = destination.with_name(destination.name + ".partial-122")
            other.write_bytes(b"unrelated incomplete attempt")
            url = "https://www2.census.gov/synthetic-public.dat"
            original = receipt(destination, url, bytes_path=partial)
            with patch.object(public_data, "urlopen") as network:
                actual = public_data.download(url, destination)
                network.assert_not_called()
            self.assertEqual(actual, original)
            self.assertEqual(destination.read_bytes(), b"synthetic immutable acquisition")
            self.assertTrue(other.exists())
            self.assertFalse(partial.exists())

    def test_orphan_receipt_with_mismatched_partial_does_not_refresh(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "synthetic-public.dat"
            partial = destination.with_name(destination.name + ".partial-123")
            partial.write_bytes(b"synthetic immutable acquisition")
            url = "https://www2.census.gov/synthetic-public.dat"
            receipt(destination, url, bytes_path=partial)
            partial.write_bytes(b"wrong bytes")
            with patch.object(public_data, "urlopen") as network:
                with self.assertRaises(Exception):
                    public_data.download(url, destination)
                network.assert_not_called()
            self.assertFalse(destination.exists())
            self.assertTrue(partial.exists())

    def test_transient_rename_failure_recovers_receipted_bytes_without_redownload(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "synthetic-public.dat"
            url = "https://www2.census.gov/synthetic-public.dat"
            original_replace = public_data.os.replace
            calls = []
            def transient(source, target):
                calls.append((source, target))
                if len(calls) == 1:
                    raise OSError("synthetic interrupted rename")
                return original_replace(source, target)
            with patch.object(public_data, "urlopen", return_value=Response(url)) as network, patch.object(public_data.os, "replace", transient):
                result = public_data.download(url, destination)
                self.assertEqual(network.call_count, 1)
            self.assertEqual(result["sha256"], public_data.digest_file(destination))
            self.assertEqual(len(calls), 2)


if __name__ == "__main__":
    unittest.main()
