"""Synthetic permit rows preserve totals, reporting coverage and missingness."""
import io
import math
import unittest

from sprouts_customer_geography.model16.bps_context import BPS_FEATURES, bps_vector, parse_bps


HEADER = "Survey,FIPS,FIPS,Region,Division,County,,1-unit,,,2-units,,,3-4 units,,,5+ units,,,1-unit rep,,,2-units rep,,,3-4 units rep,,, 5+units rep\nDate,State,County,Code,Code,Name,Bldgs,Units,Value,Bldgs,Units,Value,Bldgs,Units,Value,Bldgs,Units,Value,Bldgs,Units,Value,Bldgs,Units,Value,Bldgs,Units,Value,Bldgs,Units,Value\n"


def row(county="001", total=(100, 10, 20, 40), reported=(90, 10, 20, 40)):
    values = ["2021", "26", county, "2", "3", "Fictional County"]
    for count in total + reported:
        values.extend(["1", str(count), "1"])
    return ",".join(values) + "\n"


class BpsContextTests(unittest.TestCase):
    def test_total_estimates_and_reported_units_remain_distinct(self):
        records = parse_bps(io.StringIO(HEADER + row()), 2021)
        result, quality = bps_vector(records, "26001")
        self.assertEqual(records["26001"]["total_units"], 170)
        self.assertEqual(result[BPS_FEATURES[0]], math.log1p(170))
        self.assertEqual(result[BPS_FEATURES[1]], 70/170)
        self.assertEqual(quality["reported_unit_fraction"], 160/170)
        self.assertTrue(quality["includes_estimated_nonresponse"])

    def test_state_balance_never_becomes_a_county(self):
        records = parse_bps(io.StringIO(HEADER + row(county="000") + row()), 2021)
        self.assertEqual(set(records), {"26001"})

    def test_missing_total_is_not_zero_filled(self):
        records = parse_bps(io.StringIO(HEADER + row(total=("", 10, 20, 40))), 2021)
        result, _ = bps_vector(records, "26001")
        self.assertTrue(all(value is None for value in result.values()))

    def test_zero_units_preserve_zero_count_but_not_zero_share(self):
        records = parse_bps(io.StringIO(HEADER + row(total=(0,0,0,0), reported=(0,0,0,0))), 2021)
        result, _ = bps_vector(records, "26001")
        self.assertEqual(result[BPS_FEATURES[0]], 0)
        self.assertIsNone(result[BPS_FEATURES[1]])

    def test_duplicate_and_reporting_margin_fail_closed(self):
        with self.assertRaises(Exception):
            parse_bps(io.StringIO(HEADER + row() + row()), 2021)
        with self.assertRaises(Exception):
            parse_bps(io.StringIO(HEADER + row(reported=(1000,10,20,40))), 2021)


if __name__ == "__main__":
    unittest.main()
