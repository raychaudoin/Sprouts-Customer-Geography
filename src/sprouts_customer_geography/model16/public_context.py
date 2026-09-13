"""Historical public EPA, USDA and Census business context; no network access."""
from __future__ import annotations

import csv
import io
import json
import math
from email.utils import parsedate_to_datetime
from pathlib import Path
from zipfile import ZipFile

import numpy as np
from pyproj import Transformer
from shapely import from_wkb, make_valid
from shapely.geometry import Point, shape
from shapely.ops import transform
from shapely.strtree import STRtree

from sprouts_customer_geography.geo04 import _read_dbf_records
from sprouts_customer_geography.pipe01.production import _read_shapefile_polygons
from sprouts_customer_geography.pipe01.errors import require
from .context_research import EPA_FIELDS
from .public_data import digest_file
from .lodes_context import LodesContext, feature_catalog as lodes_feature_catalog
from .bps_context import BPS_YEAR, bps_vector, read_bps, feature_catalog as bps_feature_catalog


CBP_YEAR = {2024: 2021, 2025: 2022, 2026: 2023}
CBP_CODES = {"all": "------", "retail": "44----", "grocery": "445110", "food_service": "722///", "fitness": "713940"}
FARA_FIELDS = ("CensusTract", "Pop2010", "OHU2010", "lapophalf", "lahunvhalf")
FIPS = {"MI": "26", "WI": "55"}
RADIUS_M = 8046.72
PROJECTION = "+proj=pipeline +step +proj=unitconvert +xy_in=deg +xy_out=rad +step +proj=aea +lat_0=23 +lon_0=-96 +lat_1=29.5 +lat_2=45.5 +x_0=0 +y_0=0 +ellps=GRS80"


def feature_catalog():
    specs = [
        ("epa_log_jobs_5mi", "employment", "EPA_SLD2021", "log1p(sum TotEmp)", "Workplace employment mass; 2017 LEHD WAC"),
        ("epa_log_jobs_resident_balance_5mi", "employment", "EPA_SLD2021", "log1p(sum TotEmp)-log1p(sum Workers)", "Workplace/resident-worker balance; not unique daytime visitors"),
        ("epa_retail_job_share_5mi", "business_context", "EPA_SLD2021", "sum E5_Ret / sum TotEmp", "Local retail employment mix, not store identity or footfall"),
        ("epa_office_job_share_5mi", "business_context", "EPA_SLD2021", "sum E5_Off / sum TotEmp", "Office employment mix"),
        ("epa_log_road_density_5mi", "roads_urban_form", "EPA_SLD2021", "log1p(polygon-area-weighted mean D3A)", "Road network density; EPA public indicator derived from 2018 HERE"),
        ("epa_log_intersection_density_5mi", "roads_urban_form", "EPA_SLD2021", "log1p(polygon-area-weighted mean D3B)", "Pedestrian-oriented intersection density; EPA public HERE-derived indicator"),
        ("epa_log_transit_frequency_5mi", "transit_access", "EPA_SLD2021", "log1p(polygon-area-weighted mean D4D)", "Afternoon peak transit frequency per square mile; incomplete GTFS coverage stays missing"),
        ("epa_log_auto_jobs45_anchor", "travel_access", "EPA_SLD2021", "log1p(anchor block group D5AR)", "Time-decayed jobs accessible within 45-minute auto trip; EPA public TravelTime-derived indicator"),
        ("epa_log_transit_jobs45_anchor", "travel_access", "EPA_SLD2021", "log1p(anchor block group D5BR)", "Time-decayed jobs accessible by transit; known old-feed coverage limitations"),
        ("cbp_log_grocery_establishments_county", "county_business", "CBP_LAGGED", "log1p(county NAICS445110 est)", "County supermarket/grocery establishment context; not site competition"),
        ("cbp_retail_establishment_share_county", "county_business", "CBP_LAGGED", "county NAICS44---- est / county all-industry est", "Retail establishment mix"),
        ("cbp_food_service_share_county", "county_business", "CBP_LAGGED", "county NAICS722/// est / county all-industry est", "Food-service establishment mix"),
        ("cbp_fitness_share_county", "county_business", "CBP_LAGGED", "county NAICS713940 est / county all-industry est", "Fitness/recreation-center establishment mix; missing industry row remains missing"),
        ("fara_lowaccess_population_share_tract", "food_access", "USDA_FARA2019", "anchor historical tract lapophalf / Pop2010", "Population over half a mile from supermarket; historical 2019 store access with 2010 population"),
        ("fara_lowaccess_novehicle_household_share_tract", "food_access", "USDA_FARA2019", "anchor historical tract lahunvhalf / OHU2010", "Households without vehicles over half a mile from supermarket"),
    ]
    return [{"feature_id": name, "family": family, "baseline": False, "source": source,
             "transform": expression, "business_hypothesis": hypothesis,
             "support": "containing county" if source == "CBP_LAGGED" else "containing 2019 TIGER tract; public data retain 2010 tract identities" if source == "USDA_FARA2019" else "containing historical block group" if name.endswith("_anchor") else "state-isolated 5-mile historical polygon representative-point membership, containing polygon forced",
             "missingness": "any missing required numerator/denominator/member remains null; nonpositive denominator remains null; no absent-category zero-fill",
             "reference_vintages": CBP_YEAR if source == "CBP_LAGGED" else {"population_households": 2010, "store_access": 2019} if source == "USDA_FARA2019" else {"employment_resident_workers": 2017, "road_network": 2018, "block_group_geometry": 2019, "transit_and_network_access": 2020},
             "source_release": "2023-04-27 / 2024-06-27 / 2025-06-26 preserved county files" if source == "CBP_LAGGED" else "April 2021" if source == "USDA_FARA2019" else "SLD v3 ZIP last modified 2021-06-08; metadata/guide identify 2021 public release",
             "temporal_track": "historical; source release before forecast year"} for name, family, source, expression, hypothesis in specs] + lodes_feature_catalog() + bps_feature_catalog()


def _number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number >= 0 else None


def _ratio(numerator, denominator):
    if numerator is None or denominator is None or denominator <= 0 or numerator > denominator:
        return None
    return numerator / denominator


def _log(value):
    return math.log1p(value) if value is not None else None


def _sum(rows, name):
    values = [_number(row.get(name)) for row in rows]
    return sum(values) if values and all(value is not None for value in values) else None


def _verified(path):
    path = Path(path)
    receipt = json.loads(path.with_name(path.name + ".receipt.json").read_text())
    require(receipt["sha256"] == digest_file(path), "MODEL16_CONTEXT_BYTES_CHANGED", "public context bytes differ from receipt")
    return receipt


def read_cbp(path, forecast_year):
    """Project establishment counts only; employment noise/suppression is unused."""
    receipt = _verified(path)
    modified = receipt.get("http_last_modified")
    require(bool(modified) and parsedate_to_datetime(modified).year < forecast_year,
            "MODEL16_CONTEXT_FUTURE_VINTAGE", "business bytes lack a defensible pre-forecast publication date")
    results = {}
    with ZipFile(path) as archive:
        names = [name for name in archive.namelist() if name.endswith("co.txt")]
        require(len(names) == 1, "MODEL16_CBP_ARCHIVE_SCHEMA", "county business archive must contain one county table")
        reader = csv.DictReader(io.TextIOWrapper(archive.open(names[0]), encoding="utf-8-sig", newline=""))
        require({"fipstate", "fipscty", "naics", "est"} <= set(reader.fieldnames or []), "MODEL16_CBP_SCHEMA", "county business schema changed")
        for row in reader:
            if row["fipstate"] not in FIPS.values() or row["naics"] not in CBP_CODES.values():
                continue
            county = row["fipstate"].zfill(2) + row["fipscty"].zfill(3)
            key = (county, row["naics"])
            require(key not in results, "MODEL16_CBP_DUPLICATE", "county business geography and industry keys repeat")
            results[key] = _number(row["est"])
    require(bool(results), "MODEL16_CBP_EMPTY", "county business state selection is empty")
    return results


def cbp_vector(rows, county):
    values = {name: rows.get((county, code)) for name, code in CBP_CODES.items()}
    return {"cbp_log_grocery_establishments_county": _log(values["grocery"]),
            "cbp_retail_establishment_share_county": _ratio(values["retail"], values["all"]),
            "cbp_food_service_share_county": _ratio(values["food_service"], values["all"]),
            "cbp_fitness_share_county": _ratio(values["fitness"], values["all"])}


def read_fara(path):
    _verified(path)
    with ZipFile(path) as archive:
        require("Initial release: April 2021" in archive.read("ReadMe.csv").decode("utf-8-sig"),
                "MODEL16_FARA_RELEASE_DRIFT", "food access release does not match historical version")
        require(all(info.date_time[0] <= 2021 for info in archive.infolist()),
                "MODEL16_FARA_REVISION_DRIFT", "food access archive contains a later revision")
        reader = csv.reader(io.TextIOWrapper(archive.open("Food Access Research Atlas.csv"), encoding="utf-8-sig", newline=""))
        header = next(reader)
        require(set(FARA_FIELDS) <= set(header), "MODEL16_FARA_SCHEMA", "food access schema changed")
        indices = {field: header.index(field) for field in FARA_FIELDS}
        rows = {}
        for values in reader:
            if not values:
                continue
            # Only the five allowed public fields enter analytical records. Public
            # race/age/ethnicity disaggregations in the source are never retained.
            geoid = values[indices["CensusTract"]].zfill(11)
            if geoid[:2] not in FIPS.values():
                continue
            require(len(geoid) == 11 and geoid.isdigit() and geoid not in rows, "MODEL16_FARA_KEY", "food access keys do not reconcile")
            rows[geoid] = {field: values[index] for field, index in indices.items()}
    return rows


def _geoid(value):
    if isinstance(value, (int, float, np.number)):
        require(math.isfinite(value) and float(value).is_integer(), "MODEL16_EPA_GEOID", "EPA public geography identifier is invalid")
        result = str(int(value)).zfill(12)
    else:
        result = str(value).zfill(12)
    require(len(result) == 12 and result.isdigit(), "MODEL16_EPA_GEOID", "EPA public geography identifier is invalid")
    return result


def read_epa_original(path, fips):
    """Read only allowed original 2021 FileGDB fields via GDAL's raw array API."""
    import pyogrio
    from pyogrio.raw import read

    receipt = _verified(path)
    modified = receipt.get("http_last_modified")
    require(bool(modified) and parsedate_to_datetime(modified).year == 2021,
            "MODEL16_EPA_ORIGINAL_VINTAGE", "EPA original release bytes lack their 2021 publication evidence")
    with ZipFile(path) as archive:
        require(any(name.startswith("SmartLocationDatabase.gdb/") for name in archive.namelist()),
                "MODEL16_EPA_ORIGINAL_ARCHIVE", "EPA historical geodatabase is missing")
        require(all(info.date_time[0] <= 2021 for info in archive.infolist()),
                "MODEL16_EPA_ORIGINAL_REVISION", "EPA archive contains later-version members")
    location = "/vsizip/" + Path(path).resolve().as_posix() + "/SmartLocationDatabase.gdb"
    info = pyogrio.read_info(location)
    available = {str(name).upper(): str(name) for name in info["fields"]}
    selected = [name for name in EPA_FIELDS if name != "OBJECTID"]
    require(all(name.upper() in available for name in selected), "MODEL16_EPA_ORIGINAL_FIELDS", "original EPA field schema differs from allowlist")
    names = [available[name.upper()] for name in selected]
    meta, fids, geometry, arrays = read(location, columns=names, where=f"STATEFP = '{fips}'", return_fids=True)
    lookup = {str(name).upper(): array for name, array in zip(meta["fields"], arrays)}
    require(meta.get("crs") and len(geometry) == len(fids) and len(fids) > 0,
            "MODEL16_EPA_ORIGINAL_GEOMETRY", "original EPA state geometry is incomplete")
    operation = Transformer.from_crs(meta["crs"], "EPSG:4269", always_xy=True)
    records, polygons = [], []
    for index, fid in enumerate(fids):
        row = {name: lookup[name.upper()][index].item() if isinstance(lookup[name.upper()][index], np.generic) else lookup[name.upper()][index] for name in selected}
        row["OBJECTID"] = int(fid)
        row["GEOID20"] = _geoid(row["GEOID20"])
        row["GEOID10"] = _geoid(row["GEOID10"])
        require(str(row["STATEFP"]).zfill(2) == fips and row["GEOID20"].startswith(fips), "MODEL16_EPA_ORIGINAL_STATE", "original EPA state selection is inconsistent")
        records.append(row)
        polygons.append(transform(operation.transform, from_wkb(geometry[index])))
    require(len({row["GEOID20"] for row in records}) == len(records), "MODEL16_EPA_ORIGINAL_DUPLICATE", "original EPA block-group identifiers repeat")
    return records, polygons, {"source_crs": meta["crs"], "join_crs": "EPSG:4269",
                              "projection_operation": operation.description, "original_release_sha256": receipt["sha256"]}


def compare_epa_public_rows(original, service):
    """Later service is QA only; historical originals remain authoritative."""
    original_by_id = {_geoid(row["GEOID20"]): row for row in original}
    service_by_id = {_geoid(row["GEOID20"]): row for row in service}
    common = sorted(set(original_by_id) & set(service_by_id))
    numeric_fields = [name for name in EPA_FIELDS if name not in {"OBJECTID", "GEOID10", "GEOID20", "STATEFP"}]
    differences = {name: 0 for name in numeric_fields}
    for key in common:
        for name in numeric_fields:
            left, right = _number(original_by_id[key].get(name)), _number(service_by_id[key].get(name))
            if (left is None) != (right is None) or left is not None and not math.isclose(left, right, rel_tol=1e-12, abs_tol=1e-12):
                differences[name] += 1
    return {"common_block_groups": len(common), "original_only": len(set(original_by_id) - set(service_by_id)),
            "service_only": len(set(service_by_id) - set(original_by_id)), "numeric_field_difference_counts": differences,
            "analytical_authority": "original 2021 EPA FileGDB; service used only for current-public-source comparison"}


class _Spatial:
    def __init__(self, records, polygons, transformer):
        require(len(records) == len(polygons) and bool(records), "MODEL16_CONTEXT_GEOMETRY", "context geometry and attributes differ")
        # ArcGIS reprojection can produce tiny self-intersections. A deterministic
        # polygon-only repair is allowed only below one part per million of area.
        # Larger changes, empty output, and non-polygon output fail closed.
        self.geometry_repairs = 0
        self.maximum_repair_relative_area_change = 0.0
        cleaned = []
        for polygon in polygons:
            require(not polygon.is_empty and polygon.area > 0, "MODEL16_CONTEXT_GEOMETRY_INVALID", "public context polygon is empty")
            if not polygon.is_valid:
                repaired = make_valid(polygon)
                relative = abs(repaired.area - polygon.area) / polygon.area
                require(repaired.geom_type in {"Polygon", "MultiPolygon"} and repaired.is_valid and relative <= 1e-6,
                        "MODEL16_CONTEXT_GEOMETRY_REPAIR_LIMIT", "public geometry repair exceeds the bounded area rule")
                polygon = repaired
                self.geometry_repairs += 1
                self.maximum_repair_relative_area_change = max(self.maximum_repair_relative_area_change, relative)
            cleaned.append(polygon)
        polygons = cleaned
        self.records, self.polygons = records, polygons
        self.tree = STRtree(polygons)
        self.projected = [transform(transformer.transform, polygon) for polygon in polygons]
        self.xy = np.asarray([(polygon.representative_point().x, polygon.representative_point().y) for polygon in self.projected])
        self.area = np.asarray([polygon.area for polygon in self.projected])
        self.transformer = transformer

    def membership(self, longitude, latitude):
        point = Point(longitude, latitude)
        matches = [int(i) for i in self.tree.query(point) if self.polygons[int(i)].covers(point)]
        if len(matches) > 1:
            matches = [i for i in matches if self.polygons[i].contains(point)]
        if len(matches) != 1:
            return None, []
        x, y = self.transformer.transform(longitude, latitude)
        distances = np.hypot(self.xy[:, 0] - x, self.xy[:, 1] - y)
        members = sorted(set(np.flatnonzero(distances <= RADIUS_M).tolist()) | {matches[0]})
        return matches[0], members


class SupplementalContext:
    """Load complete public-state products once and join locally to any anchor."""
    def __init__(self, cache):
        self.root = Path(cache) / "context"
        self.transformer = Transformer.from_pipeline(PROJECTION)
        self.cbp = {year: read_cbp(self.root / f"cbp{vintage % 100}co.zip", year) for year, vintage in CBP_YEAR.items()}
        self.bps = {year: read_bps(self.root / f"bps-co{vintage}a.txt", vintage, year, _verified) for year, vintage in BPS_YEAR.items()}
        self.fara = read_fara(self.root / "fara2019.zip")
        self.epa_states, self.fara_states = {}, {}
        self.source_quality = {"epa": {}, "fara": {}}
        schema_path = self.root / "epa-sld-layer.json"
        _verified(schema_path)
        schema = json.loads(schema_path.read_text())
        fields = {row["name"]: row.get("alias", "") for row in schema["fields"]}
        require(set(EPA_FIELDS) <= fields.keys() and "2017" in fields["TotEmp"] and "2017" in fields["Workers"],
                "MODEL16_EPA_DEFINITION_DRIFT", "EPA public field definitions changed")
        for state, fips in FIPS.items():
            records, polygons, ids = [], [], []
            inventory_path = self.root / f"epa-sld2021-{fips}-ids.json"
            _verified(inventory_path)
            expected = json.loads(inventory_path.read_text()).get("objectIds")
            require(isinstance(expected, list) and bool(expected), "MODEL16_EPA_INVENTORY", "EPA source inventory is missing")
            for offset in (0, 5000):
                path = self.root / f"epa-sld2021-{fips}-{offset}.geojson"
                _verified(path)
                package = json.loads(path.read_text())
                require(package.get("type") == "FeatureCollection" and "features" in package, "MODEL16_EPA_RESPONSE", "EPA response is not feature data")
                for feature in package["features"]:
                    properties = feature["properties"]
                    require(set(properties) <= set(EPA_FIELDS) and str(properties["STATEFP"]).zfill(2) == fips,
                            "MODEL16_EPA_FIELD_ALLOWLIST", "EPA response contains unapproved fields or geography")
                    records.append({key: properties.get(key) for key in EPA_FIELDS})
                    ids.append(properties["OBJECTID"])
                    polygons.append(shape(feature["geometry"]))
            require(len(ids) == len(set(ids)) and set(ids) == set(expected), "MODEL16_EPA_PAGE_COVERAGE", "EPA pagination does not reconcile to complete state inventory")
            original_records, original_polygons, original_meta = read_epa_original(self.root / "epa-sld-v3-original.zip", fips)
            comparison = compare_epa_public_rows(original_records, records)
            self.epa_states[state] = _Spatial(original_records, original_polygons, self.transformer)
            self.source_quality["epa"][state] = {"block_groups": len(original_records), "release": "2021", "geometry_vintage": 2019,
                "original_metadata": original_meta, "current_service_comparison": comparison,
                "geometry_repairs": self.epa_states[state].geometry_repairs,
                "maximum_repair_relative_area_change": self.epa_states[state].maximum_repair_relative_area_change}
            stem = f"tl_2019_{fips}_tract"
            path = self.root / (stem + ".zip")
            _verified(path)
            with ZipFile(path) as archive:
                source_records = _read_dbf_records(archive.read(stem + ".dbf"))
                geometry = _read_shapefile_polygons(archive.read(stem + ".shp"))
            require(len(source_records) == len(geometry), "MODEL16_FARA_GEOMETRY", "historical tract attributes and geometry differ")
            self.fara_states[state] = _Spatial(source_records, geometry, self.transformer)
            self.source_quality["fara"][state] = {"source_rows": sum(key.startswith(fips) for key in self.fara),
                "geometry_tracts": len(source_records), "geometry_without_source_rows": sum(row["GEOID"] not in self.fara for row in source_records),
                "release": "2021-04", "store_vintage": 2019, "population_vintage": 2010, "geometry_vintage": 2019,
                "geometry_repairs": self.fara_states[state].geometry_repairs}
        self.lodes = LodesContext(self.root, self.fara_states, self.transformer, _verified)
        self.source_quality["lodes"] = self.lodes.source_quality
        self.source_quality["bps"] = {str(year): {"reference_year": BPS_YEAR[year],
            "MI_counties": sum(key.startswith("26") for key in rows), "WI_counties": sum(key.startswith("55") for key in rows),
            "missing_total_units": sum(row["total_units"] is None for row in rows.values()),
            "unallocated_state_balance": "county000 excluded; not allocated to actual counties",
            "counties_with_estimated_nonresponse": sum(row["total_units"] is not None and row["reported_units"] is not None and row["total_units"] > row["reported_units"] for row in rows.values())}
            for year, rows in self.bps.items()}

    def vector(self, row, anchor_tract_geoid):
        year, state = int(row["forecast_year"]), row["state"]
        require(year in CBP_YEAR and state in FIPS and str(anchor_tract_geoid).startswith(FIPS[state]),
                "MODEL16_CONTEXT_ANCHOR", "context anchor state/year does not reconcile")
        result = {spec["feature_id"]: None for spec in feature_catalog()}
        result.update(cbp_vector(self.cbp[year], str(anchor_tract_geoid)[:5]))
        longitude, latitude = float(row["longitude"]), float(row["latitude"])
        source = self.epa_states[state]
        anchor, members = source.membership(longitude, latitude)
        quality = {"epa_release": 2021, "cbp_reference_year": CBP_YEAR[year], "fara_store_year": 2019,
                   "epa_anchor_found": anchor is not None, "epa_members": len(members), "missing_fields": []}
        if anchor is not None:
            rows = [source.records[i] for i in members]
            jobs, workers = _sum(rows, "TotEmp"), _sum(rows, "Workers")
            result["epa_log_jobs_5mi"] = _log(jobs)
            result["epa_log_jobs_resident_balance_5mi"] = _log(jobs) - _log(workers) if jobs is not None and workers is not None else None
            result["epa_retail_job_share_5mi"] = _ratio(_sum(rows, "E5_Ret"), jobs)
            result["epa_office_job_share_5mi"] = _ratio(_sum(rows, "E5_Off"), jobs)
            for feature, field in (("epa_log_road_density_5mi", "D3A"), ("epa_log_intersection_density_5mi", "D3B"), ("epa_log_transit_frequency_5mi", "D4D")):
                values = [_number(record[field]) for record in rows]
                weights = source.area[members]
                result[feature] = math.log1p(float(np.average(values, weights=weights))) if all(value is not None for value in values) and weights.sum() > 0 else None
            result["epa_log_auto_jobs45_anchor"] = _log(_number(source.records[anchor]["D5AR"]))
            result["epa_log_transit_jobs45_anchor"] = _log(_number(source.records[anchor]["D5BR"]))
        source = self.fara_states[state]
        anchor, members = source.membership(longitude, latitude)
        quality.update({"fara_anchor_found": anchor is not None, "fara_members": len(members)})
        if anchor is not None:
            record = self.fara.get(source.records[anchor]["GEOID"], {})
            result["fara_lowaccess_population_share_tract"] = _ratio(_number(record.get("lapophalf")), _number(record.get("Pop2010")))
            result["fara_lowaccess_novehicle_household_share_tract"] = _ratio(_number(record.get("lahunvhalf")), _number(record.get("OHU2010")))
            quality["fara_anchor_without_source"] = not bool(record)
        flow_values, flow_quality = self.lodes.vector(row)
        result.update(flow_values)
        quality["lodes"] = flow_quality
        permit_values, permit_quality = bps_vector(self.bps[year], str(anchor_tract_geoid)[:5])
        result.update(permit_values)
        quality["bps"] = {"reference_year": BPS_YEAR[year], **permit_quality}
        quality["missing_fields"] = sorted(name for name, value in result.items() if value is None)
        return result, quality
