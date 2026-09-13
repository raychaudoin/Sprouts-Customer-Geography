"""Synthetic flows prove direction, missing geography and job-margin safeguards."""
import io
import unittest
from unittest.mock import patch

from sprouts_customer_geography.model16.lodes_context import (
    FLOW_FEATURES, flow_vector, read_lodes_state,
)


class LodesContextTests(unittest.TestCase):
    def test_external_incoming_share_and_coarse_distance(self):
        flows = {"26001000100": {"26001000100": 10, "26001000200": 10}}
        points = {"26001000100": (0, 0), "26001000200": (10000, 0)}
        result, quality = flow_vector(flows, ["26001000100"], points)
        self.assertEqual(result[FLOW_FEATURES[0]], 0.5)
        self.assertEqual(result[FLOW_FEATURES[1]], 5)
        self.assertEqual(quality["distance_job_coverage"], 1)

    def test_unknown_origin_distance_is_never_zero_filled(self):
        flows = {"26001000100": {"26001000100": 90, "17031000100": 10}}
        result, quality = flow_vector(flows, ["26001000100"], {"26001000100": (0, 0)})
        self.assertEqual(result[FLOW_FEATURES[0]], 0.1)
        self.assertIsNone(result[FLOW_FEATURES[1]])
        self.assertEqual(quality["distance_job_coverage"], 0.9)

    def test_zero_workplace_denominator_remains_missing(self):
        result, quality = flow_vector({}, ["26001000100"], {"26001000100": (0, 0)})
        self.assertTrue(all(value is None for value in result.values()))
        self.assertTrue(quality["zero_workplace_jobs"])

    def fixture(self, wac_total=15, duplicate=False, createdate="20211018"):
        header = "w_geocode,h_geocode,S000,createdate,SA01\n"
        main = f"260010001001001,260010001001002,10,{createdate},UNUSED_AGE\n"
        files = {
            "mi_od_main_JT00_2019.csv.gz": header + main + (main if duplicate else ""),
            "mi_od_aux_JT00_2019.csv.gz": header + f"260010001001001,550010001001001,5,{createdate},UNUSED_AGE\n",
            "mi_wac_S000_JT00_2019.csv.gz": f"w_geocode,C000,createdate,CR01\n260010001001001,{wac_total},{createdate},UNUSED_RACE\n",
        }
        return files

    def parse(self, files):
        with patch("sprouts_customer_geography.model16.lodes_context.gzip.open", side_effect=lambda path, *args, **kwargs: io.StringIO(files[path.name])):
            return read_lodes_state("synthetic-public", "mi", lambda path: {"http_last_modified": "Sun, 24 Oct 2021 20:29:00 GMT"})

    def test_main_plus_aux_includes_other_state_and_reconciles_wac(self):
        flows, quality = self.parse(self.fixture())
        self.assertEqual(flows["26001000100"]["55001000100"], 5)
        self.assertEqual(quality["jobs"], 15)
        self.assertTrue(quality["od_wac_margin_exact"])
        self.assertNotIn("SA01", str(flows))

    def test_missing_or_extra_flow_fails_margin_check(self):
        with self.assertRaises(Exception):
            self.parse(self.fixture(wac_total=20))

    def test_duplicate_pair_fails_closed(self):
        with self.assertRaises(Exception):
            self.parse(self.fixture(duplicate=True))

    def test_future_creation_fails_closed(self):
        with self.assertRaises(Exception):
            self.parse(self.fixture(createdate="20260101"))


if __name__ == "__main__":
    unittest.main()
