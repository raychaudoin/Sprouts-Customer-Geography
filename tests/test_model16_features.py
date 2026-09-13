"""Synthetic feature chronology, grouping, definitions, and missingness checks."""
from __future__ import annotations

import copy
import math
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np
from pyproj import Transformer
from shapely.geometry import Polygon
from shapely.strtree import STRtree

from sprouts_customer_geography.model16 import features


ROOT = Path(__file__).resolve().parents[1]


def fake_context():
    context = object.__new__(features.PublicContext)
    context.vintage = 2023
    context.geometry_vintage = 2023
    context.catalog = features.feature_catalog(ROOT)
    context.transformer = Transformer.from_pipeline(context.catalog["crs_pipeline"])
    context.model = {"candidate_measures": []}
    keys = ["26001000100", "26001000200"]
    polygons = [Polygon([(-85.01, 43.99), (-85.0, 43.99), (-85.0, 44.01), (-85.01, 44.01)]),
                Polygon([(-85.0, 43.99), (-84.99, 43.99), (-84.99, 44.01), (-85.0, 44.01)])]
    records = [{"GEOID": key, "ALAND": "2589988.110336"} for key in keys]
    xy = np.asarray([context.transformer.transform(-85.005, 44), context.transformer.transform(-84.995, 44)])
    context.states = {"MI": (records, polygons, STRtree(polygons), xy)}
    context.tables = {}
    for table in {"B11001", "B01003", "B25002", *features.EXTRA_TABLES}:
        context.tables[table] = {}
        for key in keys:
            values = {f"{table}_{kind}{index:03d}": str(10 if kind == "E" else 1) for kind in ("E", "M") for index in range(1, 18)}
            values[f"{table}_E001"] = "100" if table == "B11001" else "1000"
            context.tables[table][key] = values
    context.previous = {table: {key: {f"{table}_E001": "90", f"{table}_M001": "1"} for key in keys} for table in ("B11001", "B01003", "B25002")}
    context.components = {key: {name: {"estimate": 100.0, "moe": 1.0, "status": "valid"} for name in (*features.PROFILE_MEASURES, "occupied_housing_units_total", "owner_occupied_housing_units")} for key in keys}
    return context


class Model16FeaturesTests(unittest.TestCase):
    def test_fixed_historical_mapping_and_explicit_rejected_future_bytes(self):
        catalog = features.feature_catalog(ROOT)
        self.assertEqual(catalog["forecast_year_to_acs_vintage"], {"2024": 2022, "2025": 2023, "2026": 2023})
        self.assertEqual(set(catalog["forecast_year_to_tiger_vintage"].values()), {2023})
        self.assertIn("January 29, 2026", catalog["temporal_exclusions"]["ACS2024"])
        self.assertEqual(len(catalog["features"]), len({item["feature_id"] for item in catalog["features"]}))

    def test_materialization_uses_catalog_not_forecast_minus_two(self):
        calls = []
        class Context:
            def __init__(self, repository, cache, vintage, geometry_vintage):
                self.vintage, self.geometry = vintage, geometry_vintage
                calls.append((vintage, geometry_vintage))
            def vector(self, row):
                return {"synthetic": self.vintage}, {"acs_vintage": self.vintage, "tiger_vintage": self.geometry}
        rows = [{"observation_id": f"SYNTHETIC_{year}", "forecast_year": year} for year in (2024, 2025, 2026)]
        with patch.object(features, "PublicContext", Context):
            result = features.materialize(ROOT, "synthetic-public-cache", rows)
        self.assertEqual(calls, [(2022, 2023), (2023, 2023)])
        self.assertEqual(result["SYNTHETIC_2026"]["features"]["synthetic"], 2023)
        self.assertEqual(result["SYNTHETIC_2026"]["quality"]["prior_acs_vintage"], 2022)
        self.assertEqual(result["SYNTHETIC_2026"]["quality"]["forecast_year"], 2026)

    def test_unmapped_year_duplicate_observation_and_future_context_fail(self):
        with self.assertRaises(Exception):
            features.materialize(ROOT, "synthetic-public-cache", [{"forecast_year": 2027, "observation_id": "SYNTHETIC"}])
        for vintage, geometry in ((2024, 2023), (2023, 2024)):
            with self.assertRaises(Exception):
                features.PublicContext(ROOT, "synthetic-public-cache", vintage, geometry)
        with patch.object(features, "PublicContext") as constructor:
            constructor.return_value.vector.return_value = ({}, {})
            with self.assertRaises(Exception):
                features.materialize(ROOT, "synthetic-public-cache", [{"forecast_year": 2024, "observation_id": "SYNTHETIC"}] * 2)

    def test_baseline_historical_schema_allows_currency_year_only(self):
        contract = {"tables": [{"table_id": "B19013", "variables": [{"estimate_variable": "B19013_001E", "moe_variable": "B19013_001M", "estimate_label": "Estimate!!Median income (in 2024 inflation-adjusted dollars)", "moe_label": "Margin of Error!!Median income (in 2024 inflation-adjusted dollars)"}]}]}
        metadata = {"variables": {"B19013_001E": {"label": "Estimate!!Median income (in 2022 inflation-adjusted dollars)"}, "B19013_001M": {"label": "Margin of Error!!Median income (in 2022 inflation-adjusted dollars)"}}}
        with patch.object(features, "read_acs_metadata", return_value=metadata) as read:
            features.validate_baseline_metadata(Path("synthetic-public-cache"), 2022, contract)
            self.assertEqual(read.call_count, 1)
        metadata["variables"]["B19013_001E"]["label"] = "Estimate!!Different economic definition"
        with patch.object(features, "read_acs_metadata", return_value=metadata):
            with self.assertRaises(Exception):
                features.validate_baseline_metadata(Path("synthetic-public-cache"), 2022, contract)

    def test_extra_indices_and_invalid_quantities_are_explicit(self):
        self.assertEqual(features.EXTRAS["rent_burden_35plus_share"][3], [1, -11])
        self.assertEqual(features.EXTRAS["multifamily_housing_share"][2], [4, 5, 6, 7, 8, 9])
        self.assertEqual(features.EXTRAS["commute_45plus_share"][2], [11, 12, 13])
        for value in (None, "", "N", -999999999, math.nan, math.inf):
            self.assertIsNone(features._number(value))
        self.assertEqual(features._number(0), 0)
        component = features._component({"B11001_E001": "25"}, "B11001", 1)
        self.assertEqual(component["status"], "noncomputable")
        self.assertIsNone(component["moe"])

    def test_radial_features_growth_and_land_density_are_reconstructable(self):
        context = fake_context()
        vector, quality = context.vector({"state": "MI", "longitude": -85.005, "latitude": 44})
        self.assertAlmostEqual(vector["log_households_5mi"], math.log1p(200))
        self.assertAlmostEqual(vector["inner_household_share_3mi_of_7mi"], 1)
        self.assertAlmostEqual(vector["household_growth"], math.log1p(200) - math.log1p(180))
        self.assertAlmostEqual(vector["log_population_land_density_5mi"], math.log1p(1000))
        self.assertEqual(quality["tiger_vintage"], 2023)
        self.assertEqual(quality["acs_vintage"], 2023)
        self.assertEqual(quality["household_totals"], [200, 200, 200])

    def test_missing_member_and_prior_year_remain_null(self):
        context = fake_context()
        context.tables["B11001"]["26001000200"]["B11001_M001"] = ""
        context.previous["B01003"].pop("26001000200")
        vector, quality = context.vector({"state": "MI", "longitude": -85.005, "latitude": 44})
        self.assertTrue(all(vector[name] is None for name in features.SPATIAL))
        self.assertIsNone(vector["population_growth"])
        self.assertEqual(quality["status"], "SPATIAL_NONCOMPUTABLE")

    def test_outside_anchor_is_explicitly_noncomputable(self):
        context = fake_context()
        vector, quality = context.vector({"state": "MI", "longitude": -86, "latitude": 44})
        self.assertTrue(all(value is None for value in vector.values()))
        self.assertEqual(quality["status"], "ANCHOR_TRACT_MISSING_OR_AMBIGUOUS")
        self.assertEqual(quality["tiger_vintage"], 2023)


if __name__ == "__main__":
    unittest.main()
