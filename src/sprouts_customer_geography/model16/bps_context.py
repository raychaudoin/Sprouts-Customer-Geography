"""Historical county residential permits with explicit estimate/report separation."""
from __future__ import annotations

import csv
import math
from email.utils import parsedate_to_datetime

from sprouts_customer_geography.pipe01.errors import require


BPS_YEAR = {2024: 2021, 2025: 2022, 2026: 2023}
BPS_FEATURES = ("bps_log_permitted_units_county", "bps_multifamily_permit_unit_share_county")


def feature_catalog():
    common = {"family": "construction_permits", "source": "CENSUS_BPS_ANNUAL_COUNTY", "baseline": False,
              "forecast_year_to_reference_vintage": BPS_YEAR,
              "support": "containing county; public annual total units including Census estimates for nonresponse",
              "source_release": "2021 file dated2022-04-27; 2022/2023 files dated2024-04-25; fixed three-year lag avoids backdating the2022 revision",
              "missingness": "missing county/required total-unit field remains null; zero permitted units is valid but multifamily denominator zero remains null",
              "limitation": "authorization to build, not starts/completions; county activity is coarse context; reported-only counts retained as QA"}
    return [dict(common, feature_id=BPS_FEATURES[0], transform="log1p(sum total estimated units across1,2,3-4,and5plus-unit structures)",
                 business_hypothesis="Residential development activity and future household-supply context"),
            dict(common, feature_id=BPS_FEATURES[1], transform="total estimated units in2,3-4,and5plus-unit structures divided by all permitted units",
                 business_hypothesis="Mix of forthcoming multifamily versus detached housing supply")]


def _count(value):
    value = value.strip()
    return int(value) if value.isdigit() else None


def parse_bps(stream, reference_year):
    reader = csv.reader(stream)
    upper, lower = next(reader), next(reader)
    require(len(lower) == 30 and [value.strip() for value in lower[:6]] == ["Date", "State", "County", "Code", "Code", "Name"],
            "MODEL16_BPS_SCHEMA", "county permits schema differs from the two-line historical header")
    units, reported = (7, 10, 13, 16), (19, 22, 25, 28)
    require(all(lower[index].strip() == "Units" for index in units + reported)
            and [upper[index].strip() for index in units] == ["1-unit", "2-units", "3-4 units", "5+ units"]
            and all("rep" in upper[index] for index in reported), "MODEL16_BPS_ESTIMATE_SEMANTICS", "total and reported permit units do not reconcile")
    results = {}
    for row in reader:
        if not any(value.strip() for value in row):
            continue
        require(len(row) == 30 and row[0] == str(reference_year), "MODEL16_BPS_REFERENCE_YEAR", "county permits row has invalid width or reference year")
        if row[1] not in {"26", "55"}:
            continue
        # County000 is an unallocated state-balance category, not a real county.
        # Preserve it in raw provenance, but never assign its units to an anchor.
        if row[2] == "000":
            continue
        county = row[1] + row[2].zfill(3)
        require(len(county) == 5 and county.isdigit() and county not in results, "MODEL16_BPS_COUNTY", "county permits geography repeats or is invalid")
        estimated = [_count(row[index]) for index in units]
        direct = [_count(row[index]) for index in reported]
        total = sum(estimated) if all(value is not None for value in estimated) else None
        reported_total = sum(direct) if all(value is not None for value in direct) else None
        require(total is None or reported_total is None or reported_total <= total, "MODEL16_BPS_REPORTING_MARGIN", "reported units exceed total estimated units")
        results[county] = {"total_units": total, "multifamily_units": sum(estimated[1:]) if all(value is not None for value in estimated[1:]) else None,
                           "reported_units": reported_total, "reference_year": reference_year}
    require(bool(results), "MODEL16_BPS_EMPTY", "county permits MI/WI selection is empty")
    return results


def read_bps(path, reference_year, forecast_year, verify):
    receipt = verify(path)
    require(receipt.get("http_last_modified") and parsedate_to_datetime(receipt["http_last_modified"]).year < forecast_year,
            "MODEL16_BPS_FUTURE_REVISION", "county permits byte revision is after the forecast cutoff")
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return parse_bps(stream, reference_year)


def bps_vector(records, county):
    row = records.get(county, {})
    total, multiple, reported = row.get("total_units"), row.get("multifamily_units"), row.get("reported_units")
    return {BPS_FEATURES[0]: math.log1p(total) if total is not None else None,
            BPS_FEATURES[1]: multiple/total if multiple is not None and total is not None and total > 0 else None}, {
            "county_present": bool(row), "reported_unit_fraction": reported/total if reported is not None and total else None,
            "includes_estimated_nonresponse": total is not None and reported is not None and total > reported}
