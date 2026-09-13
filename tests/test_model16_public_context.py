"""Synthetic checks for historical supplemental source and missingness rules."""
import json
import math
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile, ZipInfo

from sprouts_customer_geography.model16.context_research import EPA_FIELDS, context_jobs, CONTEXT_PUBLIC_HOSTS
from sprouts_customer_geography.model16.public_context import (
    CBP_CODES, _number, _ratio, _sum, cbp_vector, feature_catalog, read_cbp, read_fara,
    compare_epa_public_rows,
)
from sprouts_customer_geography.model16.public_data import digest_file
from urllib.parse import urlparse
from pyproj import Transformer
from shapely.geometry import Polygon
from sprouts_customer_geography.model16.public_context import _Spatial, PROJECTION


def receipt(path, modified="Thu, 27 Apr 2023 11:41:32 GMT"):
    path.with_name(path.name + ".receipt.json").write_text(json.dumps({"sha256": digest_file(path), "http_last_modified": modified}))


class PublicContextTests(unittest.TestCase):
    def test_business_missing_industry_is_not_zero(self):
        rows = {("26001", CBP_CODES["all"]): 100, ("26001", CBP_CODES["retail"]): 25}
        result = cbp_vector(rows, "26001")
        self.assertEqual(result["cbp_retail_establishment_share_county"], 0.25)
        self.assertIsNone(result["cbp_log_grocery_establishments_county"])
        self.assertIsNone(result["cbp_fitness_share_county"])

    def test_business_future_revision_rejected_and_unused_employment_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cbp21co.zip"
            with ZipFile(path, "w") as archive:
                archive.writestr("cbp21co.txt", "fipstate,fipscty,naics,est,emp\n26,001,------,100,N\n26,001,445110,3,N\n")
            receipt(path)
            rows = read_cbp(path, 2024)
            self.assertEqual(rows[("26001", "445110")], 3)
            receipt(path, "Mon, 01 Jan 2024 00:00:00 GMT")
            with self.assertRaises(Exception):
                read_cbp(path, 2024)

    def test_business_duplicate_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cbp21co.zip"
            with ZipFile(path, "w") as archive:
                archive.writestr("cbp21co.txt", "fipstate,fipscty,naics,est\n26,001,------,100\n26,001,------,100\n")
            receipt(path)
            with self.assertRaises(Exception):
                read_cbp(path, 2024)

    def test_food_access_projects_allowed_fields_and_preserves_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fara2019.zip"
            with ZipFile(path, "w") as archive:
                archive.writestr(ZipInfo("ReadMe.csv", (2021, 4, 21, 0, 0, 0)), "Initial release: April 2021")
                archive.writestr(ZipInfo("Food Access Research Atlas.csv", (2021, 4, 21, 0, 0, 0)), "CensusTract,Pop2010,OHU2010,lapophalf,lahunvhalf,TractWhite\n26001000100,100,40,25,,IGNORED\n")
            receipt(path)
            rows = read_fara(path)
            self.assertNotIn("TractWhite", rows["26001000100"])
            self.assertEqual(_ratio(_sum(list(rows.values()), "lapophalf"), _sum(list(rows.values()), "Pop2010")), 0.25)
            self.assertIsNone(_sum(list(rows.values()), "lahunvhalf"))

    def test_invalid_and_missing_quantities(self):
        for value in (None, "N", "", -999, math.nan, math.inf):
            self.assertIsNone(_number(value))
        self.assertEqual(_number(0), 0)
        self.assertIsNone(_ratio(3, 0))
        self.assertIsNone(_ratio(4, 3))
        self.assertIsNone(_sum([{"x": 1}, {}], "x"))

    def test_later_epa_changes_are_reported_without_overwriting_original(self):
        original = [{"GEOID20": "260010001001", "TotEmp": 10, "D4D": -99999}]
        service = [{"GEOID20": "260010001001", "TotEmp": 25, "D4D": None}]
        result = compare_epa_public_rows(original, service)
        self.assertEqual(result["numeric_field_difference_counts"]["TotEmp"], 1)
        self.assertEqual(result["numeric_field_difference_counts"]["D4D"], 0)
        self.assertEqual(original[0]["TotEmp"], 10)
        self.assertIn("original 2021", result["analytical_authority"])

    def test_catalog_and_public_queries_are_explicit_and_unique(self):
        specs = feature_catalog()
        self.assertEqual(len({row["feature_id"] for row in specs}), len(specs))
        self.assertTrue(all(row["baseline"] is False and row["family"] and row["source"] and row["transform"] for row in specs))
        forbidden = {"White", "Male", "P_WrkAge", "D5AE", "D5BE", "VMT_per_worker", "SLC_score", "GHG_per_worker"}
        self.assertFalse(set(EPA_FIELDS) & forbidden)
        jobs = context_jobs(Path("synthetic-public-cache"))
        self.assertEqual(len({job[0] for job in jobs}), len(jobs))
        self.assertTrue(all(urlparse(url).scheme == "https" and urlparse(url).hostname in CONTEXT_PUBLIC_HOSTS for _, url, _ in jobs))

    def test_large_geometry_failure_is_not_silently_repaired(self):
        bowtie = Polygon([(0, 0), (1, 1), (0, 1), (1, 0), (0, 0)])
        with self.assertRaises(Exception):
            _Spatial([{}], [bowtie], Transformer.from_pipeline(PROJECTION))

    def test_containing_large_polygon_is_forced_into_support(self):
        # Fictional broad polygon whose interior point is far from its edge.
        polygon = Polygon([(-90, 40), (-89, 40), (-89, 41), (-90, 41), (-90, 40)])
        context = _Spatial([{"synthetic": True}], [polygon], Transformer.from_pipeline(PROJECTION))
        anchor, members = context.membership(-89.99, 40.01)
        self.assertEqual(anchor, 0)
        self.assertEqual(members, [0])
        self.assertEqual(context.geometry_repairs, 0)


if __name__ == "__main__":
    unittest.main()
