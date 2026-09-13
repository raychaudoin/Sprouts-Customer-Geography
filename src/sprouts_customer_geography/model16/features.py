"""Target-blind historical ACS/TIGER feature design and protected anchor join."""
from __future__ import annotations

import json
import math
import re
from pathlib import Path
from zipfile import ZipFile

import numpy as np
from pyproj import Transformer
from shapely.geometry import Point
from shapely.strtree import STRtree

from sprouts_customer_geography.geo04 import _read_dbf_records
from sprouts_customer_geography.pipe01.production import _read_shapefile_polygons
from sprouts_customer_geography.model11.features import _aggregate_measure
from sprouts_customer_geography.pipe01.errors import require
from .public_data import STATES, EXTRA_TABLES, read_acs_table, read_acs_metadata, verify_receipt

SPATIAL = ("log_households_5mi", "inner_household_share_3mi_of_7mi", "log_inner_outer_household_density_gradient")
PROFILE_MEASURES = ("median_household_income", "per_capita_income", "median_home_value", "median_gross_rent", "average_household_size")
RADII = (4828.032, 8046.72, 11265.408)
EXTRAS = {
    "log_population_5mi": ("household_mass", "B01003", [1], None, "log1p", "Population scale distinct from household mass"),
    "high_income_household_share": ("household_economics", "B19001", [14, 15, 16, 17], [1], "share", "Household economic capacity, annual income at least $100,000 in vintage dollars"),
    "poverty_share": ("household_economics", "B17001", [2], [1], "share", "Economic constraint, total poverty universe; no age/sex/race breakdown"),
    "multifamily_housing_share": ("housing_urban_form", "B25024", [4, 5, 6, 7, 8, 9], [1], "share", "Housing units in structures with two or more units"),
    "rent_burden_35plus_share": ("household_economics", "B25070", [8, 9, 10], [1, -11], "share", "Gross rent at least 35 percent of income among computed rent-burden households"),
    "commute_45plus_share": ("commuting", "B08303", [11, 12, 13], [1], "share", "Travel time at least 45 minutes among workers not working at home"),
}


def contracts(repository):
    data = json.loads((Path(repository) / "config/data/data03_wisconsin_multivariate_acs_feature_source_contract.json").read_text())
    model = json.loads((Path(repository) / "config/model/model11_wisconsin_multivariate_model_contract.json").read_text())
    return data, model


def feature_catalog(repository):
    data, model = contracts(repository)
    base = [dict(feature_id=name, family="household_mass", baseline=True,
                 source="ACS_B11001_TIGER", transform=expression) for name, expression in zip(SPATIAL,
                    ("log1p(sum households within 5 miles)", "households3mi / households7mi", "log1p(households3mi/(pi*9)) - log1p((households7mi-households3mi)/(pi*40))"))]
    for spec in model["candidate_measures"]:
        base.append({"feature_id": spec["measure_id"], "family": "baseline_demographics", "baseline": True,
                     "source": "ACS_DATA03_DEFINITIONS", "accepted_definition": spec, "transform": spec["transform"]})
    for name, (family, table, numerator, denominator, transform, hypothesis) in EXTRAS.items():
        base.append({"feature_id": name, "family": family, "baseline": False, "source": table,
                     "numerator_indices": numerator, "denominator_signed_indices": denominator,
                     "transform": transform, "business_hypothesis": hypothesis})
    base.append({"feature_id": "log_population_land_density_5mi", "family": "housing_urban_form", "baseline": False,
                 "source": "ACS_B01003_TIGER_ALAND", "transform": "log1p(sum population / summed member land area in square miles)"})
    for feature, table in (("household_growth", "B11001"), ("population_growth", "B01003"), ("housing_unit_growth", "B25002")):
        base.append({"feature_id": feature, "family": "growth", "baseline": False, "source": table,
                     "transform": "log1p(sum latest estimate) minus log1p(sum preceding ACS vintage estimate), same latest member tract keys",
                     "limitation": "successive five-year ACS periods overlap four years; descriptive noisy change, not an independent annual growth estimate"})
    for measure in PROFILE_MEASURES:
        base.append({"feature_id": "covered_" + measure, "family": "household_economics", "baseline": False,
                     "source": "ACS_DATA03_DEFINITIONS", "transform": "log1p weighted tract profile" if measure != "average_household_size" else "weighted tract profile",
                     "aggregation": "same published weights as accepted definition; zero-weight tracts do not contribute; positive valid estimates must cover at least 95 percent of known positive weight",
                     "uncertainty": "aggregate published MOE only when all contributing MOEs available; otherwise explicitly unknown, estimate may still be used",
                     "distinction": "coverage-qualified tract profile, not a median of all households in the catchment; strict accepted baseline retained separately"})
    return {"artifact_id": "MODEL16_TARGET_BLIND_FEATURE_CATALOG_V1", "primary_track": "historical",
            "forecast_year_to_acs_vintage": {"2024": 2022, "2025": 2023, "2026": 2023},
            "forecast_year_to_tiger_vintage": {"2024": 2023, "2025": 2023, "2026": 2023},
            "availability_cutoff": "Verified raw-file HTTP revision date must precede each forecast year; original statistical release labels do not backdate subsequently revised bytes",
            "temporal_exclusions": {"ACS2024": "Downloaded table bytes are dated January 29, 2026; pre-2026 bytes were not established, so excluded from primary historical scoring", "TIGER2024": "Downloaded ZIP bytes are dated June 27, 2025; use fixed verified pre-2024 TIGER2023 geometry for every forecast year"},
            "geometry_policy": "Fixed 2023 TIGER geography, with exact MI/WI tract-key equality required against each admitted ACS vintage; no silent geography crosswalk",
            "support": "state-isolated unrounded NAD83 EPSG:4269 to EPSG:5070 tract internal-point radial membership; containing tract forced",
            "radii_m": list(RADII), "crs_pipeline": "+proj=pipeline +step +proj=unitconvert +xy_in=deg +xy_out=rad +step +proj=aea +lat_0=23 +lon_0=-96 +lat_1=29.5 +lat_2=45.5 +x_0=0 +y_0=0 +ellps=GRS80",
            "missingness": "invalid or missing constituent estimate/MOE stays null; fold-local preprocessing only",
            "baseline": "accepted MODEL-13 method and DATA-03 feature definitions reapplied to temporally admissible public vintages; accepted parameters not reused",
            "protected_characteristics": "excluded; total population and economic quantities only; no direct age, sex, race, ethnicity, religion, disability inputs",
            "features": base}


def _number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) and result >= 0 else None
    except (TypeError, ValueError):
        return None


def _component(row, table, index):
    estimate = _number(row.get(f"{table}_E{index:03d}"))
    moe = _number(row.get(f"{table}_M{index:03d}"))
    return {"estimate": estimate, "moe": moe, "status": "valid" if estimate is not None and moe is not None else "noncomputable"}


def validate_extra_metadata(cache, vintage):
    # Validate exact business meaning independently of protected outcomes.
    required_labels = {("B19001", 14): "$100,000 to $124,999", ("B25024", 4): "2", ("B25070", 8): "35.0 to 39.9 percent",
                       ("B08303", 11): "45 to 59 minutes", ("B17001", 2): "Income in the past 12 months below poverty level"}
    for (table, index), expected in required_labels.items():
        meta = read_acs_metadata(Path(cache) / f"acs{vintage}-{table.lower()}.metadata.json", table, vintage)
        label = meta["variables"][f"{table}_{index:03d}E"]["label"]
        require(expected.casefold() in label.casefold(), "MODEL16_PUBLIC_DEFINITION_DRIFT", "public variable semantics differ from feature catalog")


def validate_baseline_metadata(cache, vintage, source_contract):
    """Historical variable semantics must match accepted definitions, not just IDs."""
    def normalized(label):
        return re.sub(r"\b20[0-9]{2}\b", "VINTAGE", " ".join(label.casefold().split()))
    for table in source_contract["tables"]:
        metadata = read_acs_metadata(Path(cache) / f"acs{vintage}-{table['table_id'].lower()}.metadata.json", table["table_id"], vintage)
        for variable in table["variables"]:
            for kind in ("estimate", "moe"):
                observed = metadata["variables"].get(variable[kind + "_variable"], {})
                require(isinstance(observed.get("label"), str) and normalized(observed["label"]) == normalized(variable[kind + "_label"]),
                        "MODEL16_BASELINE_DEFINITION_DRIFT", "historical ACS component meaning differs from its accepted definition")


class PublicContext:
    def __init__(self, repository, cache, vintage, geometry_vintage=2023):
        self.vintage = vintage
        self.geometry_vintage = geometry_vintage
        require(vintage in {2022, 2023} and geometry_vintage == 2023, "MODEL16_PRIMARY_VINTAGE_UNAUTHORIZED", "primary historical feature vintages differ from the frozen catalog")
        self.cache = Path(cache)
        data, self.model = contracts(repository)
        self.catalog = feature_catalog(repository)
        self.transformer = Transformer.from_pipeline(self.catalog["crs_pipeline"])
        validate_extra_metadata(cache, vintage)
        validate_baseline_metadata(cache, vintage, data)
        tables = sorted({"B11001", *EXTRA_TABLES, *(item["table_id"] for item in data["tables"])})
        self.tables = {table: read_acs_table(Path(cache) / f"acsdt5y{vintage}-{table.lower()}.dat", table) for table in tables}
        self.previous = {table: read_acs_table(Path(cache) / f"acsdt5y{vintage-1}-{table.lower()}.dat", table) for table in ("B11001", "B01003", "B25002")}
        keys = set(self.tables["B11001"])
        require(all(set(rows) <= keys for rows in self.tables.values()), "MODEL16_ACS_TABLE_COVERAGE", "ACS tables contain unrecognized state tract keys")
        self.source_missing_rows = {table: sorted(keys-set(rows)) for table, rows in self.tables.items() if set(rows) != keys}
        self.components = {key: {} for key in keys}
        for table in data["tables"]:
            for variable in table["variables"]:
                index = int(variable["estimate_variable"].split("_")[1][:-1])
                for key in keys:
                    self.components[key][variable["component_id"]] = _component(self.tables[table["table_id"]].get(key, {}), table["table_id"], index)
        self.states = {}
        for state, fips in STATES.items():
            stem = f"tl_{self.geometry_vintage}_{fips}_tract"
            path = Path(cache) / (stem + ".zip")
            verify_receipt(path, expected_url=f"https://www2.census.gov/geo/tiger/TIGER{self.geometry_vintage}/TRACT/{stem}.zip", latest_allowed_year=2023)
            with ZipFile(path) as archive:
                records = _read_dbf_records(archive.read(stem + ".dbf"))
                polygons = _read_shapefile_polygons(archive.read(stem + ".shp"))
            require(len(records) == len(polygons), "MODEL16_TIGER_SCHEMA", "TIGER geometry and attributes differ")
            tract_keys = [row["GEOID"] for row in records]
            require(len(set(tract_keys)) == len(tract_keys) and set(tract_keys) == {key for key in keys if key.startswith(fips)},
                    "MODEL16_GEOGRAPHY_VINTAGE_COVERAGE", "ACS and lagged TIGER keys differ; explicit harmonization required")
            xy = np.asarray([self.transformer.transform(float(row["INTPTLON"]), float(row["INTPTLAT"])) for row in records])
            self.states[state] = (records, polygons, STRtree(polygons), xy)

    def vector(self, row):
        records, polygons, tree, xy = self.states[row["state"]]
        point = Point(float(row["longitude"]), float(row["latitude"]))
        covered = [int(i) for i in tree.query(point) if polygons[int(i)].covers(point)]
        if len(covered) > 1:
            covered = [i for i in covered if polygons[i].contains(point)]
        if len(covered) != 1:
            return {item["feature_id"]: None for item in self.catalog["features"]}, {"status": "ANCHOR_TRACT_MISSING_OR_AMBIGUOUS", "acs_vintage": self.vintage, "tiger_vintage": self.geometry_vintage}
        x, y = self.transformer.transform(point.x, point.y)
        distance = np.hypot(xy[:, 0] - x, xy[:, 1] - y)
        members = [sorted(set(np.flatnonzero(distance <= radius).tolist()) | {covered[0]}) for radius in RADII]
        keys = [[records[i]["GEOID"] for i in ids] for ids in members]
        hh = {key: _component(self.tables["B11001"][key], "B11001", 1) for key in set(sum(keys, []))}
        household_valid = all(v["status"] == "valid" for v in hh.values())
        vector = {}
        totals = [sum(hh[key]["estimate"] for key in group) for group in keys] if household_valid else [None]*3
        if household_valid and 0 < totals[0] <= totals[1] <= totals[2]:
            h3, h5, h7 = totals
            vector.update(zip(SPATIAL, (math.log1p(h5), h3/h7, math.log1p(h3/(math.pi*9)) - math.log1p((h7-h3)/(math.pi*40)))))
        else:
            vector.update({name: None for name in SPATIAL})
        profiles = {}
        weights = {key: hh[key]["estimate"] for key in keys[1]}
        for spec in self.model["candidate_measures"]:
            name = spec["measure_id"]
            profile = _aggregate_measure(spec, keys[1], self.components, weights) if all(v is not None for v in weights.values()) else {"value": None, "moe": None, "status": "noncomputable"}
            profiles[name] = profile
            vector[name] = None if profile["value"] is None else math.log1p(profile["value"]) if spec["transform"] == "log1p" else profile["value"]
        covered_profiles = {}
        for measure in PROFILE_MEASURES:
            weighted = []
            for key in keys[1]:
                values = self.components[key]
                if measure in {"median_household_income", "per_capita_income"}:
                    weight = hh[key]["estimate"]
                elif measure == "median_home_value":
                    weight = values["owner_occupied_housing_units"]["estimate"]
                elif measure == "median_gross_rent":
                    occupied, owner = values["occupied_housing_units_total"]["estimate"], values["owner_occupied_housing_units"]["estimate"]
                    weight = occupied-owner if occupied is not None and owner is not None else None
                else:
                    weight = values["occupied_housing_units_total"]["estimate"]
                weighted.append((values[measure], weight))
            known = all(weight is not None and weight >= 0 for _, weight in weighted)
            all_weight = sum(weight for _, weight in weighted) if known else 0
            usable = [(value, weight) for value, weight in weighted if weight is not None and weight > 0 and value["estimate"] is not None]
            valid_weight = sum(weight for _, weight in usable)
            coverage = valid_weight/all_weight if all_weight > 0 else None
            value = sum(item["estimate"]*weight for item, weight in usable)/valid_weight if known and coverage is not None and coverage >= .95 else None
            moe = math.sqrt(sum((item["moe"]*weight)**2 for item, weight in usable))/valid_weight if value is not None and all(item["moe"] is not None for item, weight in usable) else None
            vector["covered_"+measure] = value if measure == "average_household_size" or value is None else math.log1p(value)
            covered_profiles[measure] = {"value": value, "moe": moe, "known_positive_weight_coverage": coverage, "uncertainty_unknown": moe is None}
        def total(table, signed_indices):
            components = [(_component(self.tables[table].get(key, {}), table, abs(index)), 1 if index > 0 else -1) for key in keys[1] for index in signed_indices]
            if not all(value["status"] == "valid" for value, sign in components):
                return None
            return sum(value["estimate"]*sign for value, sign in components)
        for name, (family, table, numerator, denominator, transform, hypothesis) in EXTRAS.items():
            num = total(table, numerator)
            den = total(table, denominator) if denominator else None
            if transform == "log1p":
                value = math.log1p(num) if num is not None and num >= 0 else None
            else:
                value = num/den if num is not None and den is not None and den > 0 and 0 <= num <= den else None
            vector[name] = value
        population = total("B01003", [1])
        area = sum(float(records[i]["ALAND"]) for i in members[1]) / 2589988.110336
        vector["log_population_land_density_5mi"] = math.log1p(population/area) if population is not None and area > 0 else None
        for name, table in (("household_growth", "B11001"), ("population_growth", "B01003"), ("housing_unit_growth", "B25002")):
            prior = [_component(self.previous[table].get(key, {}), table, 1) for key in keys[1]]
            current = total(table, [1])
            vector[name] = math.log1p(current) - math.log1p(sum(value["estimate"] for value in prior)) if current is not None and all(value["status"] == "valid" for value in prior) else None
        quality = {"status": "COMPUTABLE" if all(vector[name] is not None for name in SPATIAL) else "SPATIAL_NONCOMPUTABLE",
                   "acs_vintage": self.vintage, "tiger_vintage": self.geometry_vintage, "anchor_tract": records[covered[0]]["GEOID"],
                   "member_tracts": keys, "household_totals": totals,
                   "household_moe": [math.sqrt(sum(hh[key]["moe"]**2 for key in group)) for group in keys] if household_valid else [None]*3,
                   "profiles": profiles, "covered_profiles": covered_profiles, "missing_feature_count": sum(value is None for value in vector.values()),
                   "cross_state_support": "state-isolated; adjacent-state and Canadian households omitted; no coverage claim"}
        return vector, quality


def materialize(repository, cache, observations):
    outputs = {}
    catalog = feature_catalog(repository)
    acs_by_year, geometry_by_year = catalog["forecast_year_to_acs_vintage"], catalog["forecast_year_to_tiger_vintage"]
    require(all(str(row["forecast_year"]) in acs_by_year for row in observations), "MODEL16_FORECAST_YEAR_UNDECLARED", "an observation year has no frozen public-vintage mapping")
    for vintage, geometry_vintage in sorted({(acs_by_year[str(row["forecast_year"])], geometry_by_year[str(row["forecast_year"])]) for row in observations}):
        selected = [row for row in observations if acs_by_year[str(row["forecast_year"])] == vintage and geometry_by_year[str(row["forecast_year"])] == geometry_vintage]
        if not selected:
            continue
        context = PublicContext(repository, cache, vintage, geometry_vintage=geometry_vintage)
        for row in selected:
            features, quality = context.vector(row)
            quality.update({"forecast_year": int(row["forecast_year"]), "prior_acs_vintage": vintage - 1, "temporal_track": "verified historical raw bytes and fixed 2023 geography"})
            outputs[row["observation_id"]] = {"features": features, "quality": quality}
    require(len(outputs) == len(observations), "MODEL16_FEATURE_ROW_ACCOUNTING", "feature materialization omitted observations")
    return outputs
