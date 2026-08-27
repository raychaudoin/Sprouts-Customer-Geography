"""Target-blind, outside-Git public-feature materialization for MODEL-14."""

from __future__ import annotations

from collections import Counter, defaultdict
import copy
import csv
from dataclasses import dataclass
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import struct
from typing import Any, Iterable, Mapping, Sequence
from zipfile import ZipFile

from shapely.geometry import LineString, MultiLineString, Point
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform as transform_geometry
from shapely.strtree import STRtree

from sprouts_customer_geography.geo04 import _read_dbf_records
from sprouts_customer_geography.pipe01.canonical import content_digest, file_sha256, write_json_exclusive
from sprouts_customer_geography.pipe01.errors import ConformanceError, require
from sprouts_customer_geography.pipe01.production import Geo03ProductionTransformer
from sprouts_customer_geography.pipe02.resolver import _is_within


CONTRACT_ID = "MODEL14_EXPERIMENTAL_PUBLIC_FEATURE_CONTRACT_V1"
FREEZE_ID = "MODEL14_TARGET_BLIND_PUBLIC_FEATURE_FREEZE_V1"
MATRIX_FILENAME = "model14_public_tract_feature_matrix.csv"
FREEZE_FILENAME = "model14_target_blind_public_feature_freeze.json"
READY_FILENAME = "READY.json"
SQ_METERS_PER_SQ_MILE = 2_589_988.110336

STATE_CONFIG = {
    "MI": {
        "state_fips": "26",
        "tract_count": 3017,
        "tiger_manifest": "data/manifests/tiger_2024_michigan_tract.source_manifest.json",
        "tiger_source": "data/raw/data04/tl_2024_26_tract.zip",
    },
    "WI": {
        "state_fips": "55",
        "tract_count": 1542,
        "tiger_manifest": "data/manifests/tiger_2024_wisconsin_tract.source_manifest.json",
        "tiger_source": "data/raw/data03/tl_2024_55_tract.zip",
    },
}

LODES_SUM_FIELDS = (
    "lodes_workplace_jobs",
    "lodes_resident_workers",
    "lodes_high_earnings_jobs",
    "lodes_retail_trade_jobs",
    "lodes_accommodation_food_jobs",
    "lodes_education_health_jobs",
    "lodes_goods_producing_jobs",
    "lodes_workplace_job_square_sum",
    "lodes_active_workplace_blocks",
    "lodes_main_work_flows",
    "lodes_aux_work_flows",
    "lodes_same_tract_live_work_flows",
    "lodes_origin_hhi_weighted_flow",
    "lodes_origin_hhi_weight",
)

ACS_COMPONENTS: dict[str, tuple[str, str]] = {
    "population_total": ("B01003", "B01003_001E"),
    "vehicle_households_total": ("B08201", "B08201_001E"),
    "vehicle_households_two": ("B08201", "B08201_004E"),
    "vehicle_households_three": ("B08201", "B08201_005E"),
    "vehicle_households_four_plus": ("B08201", "B08201_006E"),
    "commuters_total": ("B08301", "B08301_001E"),
    "commuters_public_transit": ("B08301", "B08301_010E"),
    "commuters_bicycle": ("B08301", "B08301_018E"),
    "commuters_walked": ("B08301", "B08301_019E"),
    "commute_time_total": ("B08303", "B08303_001E"),
    "commute_time_45_59": ("B08303", "B08303_011E"),
    "commute_time_60_89": ("B08303", "B08303_012E"),
    "commute_time_90_plus": ("B08303", "B08303_013E"),
    "households_total": ("B11001", "B11001_001E"),
    "nonfamily_households": ("B11001", "B11001_007E"),
    "poverty_universe": ("B17001", "B17001_001E"),
    "poverty_below": ("B17001", "B17001_002E"),
    "income_households_total": ("B19001", "B19001_001E"),
    **{f"income_low_{index:03d}": ("B19001", f"B19001_{index:03d}E") for index in range(2, 8)},
    **{f"income_high_{index:03d}": ("B19001", f"B19001_{index:03d}E") for index in range(14, 18)},
    "housing_units_total": ("B25024", "B25024_001E"),
    **{f"housing_multiunit_{index:03d}": ("B25024", f"B25024_{index:03d}E") for index in range(4, 10)},
    **{f"rent_computed_{index:03d}": ("B25070", f"B25070_{index:03d}E") for index in range(2, 11)},
}

EXPECTED_LABELS = {
    "B01003_001E": "Estimate!!Total",
    "B08201_001E": "Estimate!!Total:",
    "B08201_004E": "Estimate!!Total:!!2 vehicles available",
    "B08201_005E": "Estimate!!Total:!!3 vehicles available",
    "B08201_006E": "Estimate!!Total:!!4 or more vehicles available",
    "B08301_001E": "Estimate!!Total:",
    "B08301_010E": "Estimate!!Total:!!Public transportation:",
    "B08301_018E": "Estimate!!Total:!!Bicycle",
    "B08301_019E": "Estimate!!Total:!!Walked",
    "B08303_001E": "Estimate!!Total:",
    "B08303_011E": "Estimate!!Total:!!45 to 59 minutes",
    "B08303_012E": "Estimate!!Total:!!60 to 89 minutes",
    "B08303_013E": "Estimate!!Total:!!90 or more minutes",
    "B11001_001E": "Estimate!!Total:",
    "B11001_007E": "Estimate!!Total:!!Nonfamily households:",
    "B17001_001E": "Estimate!!Total:",
    "B17001_002E": "Estimate!!Total:!!Income in the past 12 months below poverty level:",
    "B19001_001E": "Estimate!!Total:",
    "B19001_002E": "Estimate!!Total:!!Less than $10,000",
    "B19001_007E": "Estimate!!Total:!!$30,000 to $34,999",
    "B19001_014E": "Estimate!!Total:!!$100,000 to $124,999",
    "B19001_017E": "Estimate!!Total:!!$200,000 or more",
    "B25024_001E": "Estimate!!Total:",
    "B25024_004E": "Estimate!!Total:!!2",
    "B25024_009E": "Estimate!!Total:!!50 or more",
    "B25070_002E": "Estimate!!Total:!!Less than 10.0 percent",
    "B25070_006E": "Estimate!!Total:!!25.0 to 29.9 percent",
    "B25070_007E": "Estimate!!Total:!!30.0 to 34.9 percent",
    "B25070_010E": "Estimate!!Total:!!50.0 percent or more",
}

FEATURE_IDS = (
    "lodes_log_workplace_jobs_5mi",
    "lodes_log_resident_workers_5mi",
    "lodes_log_jobs_to_resident_worker_ratio_5mi",
    "lodes_net_job_worker_imbalance_share_5mi",
    "lodes_same_tract_live_work_share_5mi",
    "lodes_out_of_state_inflow_share_5mi",
    "lodes_high_earnings_job_share_5mi",
    "lodes_retail_trade_job_share_5mi",
    "lodes_accommodation_food_job_share_5mi",
    "lodes_education_health_job_share_5mi",
    "lodes_goods_producing_job_share_5mi",
    "lodes_workplace_block_hhi_5mi",
    "lodes_flow_weighted_origin_hhi_5mi",
    "lodes_log_active_workplace_blocks_5mi",
    "acs_two_plus_vehicle_household_share_5mi",
    "acs_public_transit_commuter_share_5mi",
    "acs_active_commuter_share_5mi",
    "acs_long_commute_45plus_share_5mi",
    "acs_nonfamily_household_share_5mi",
    "acs_poverty_share_5mi",
    "acs_low_income_under_35k_household_share_5mi",
    "acs_high_income_100k_plus_household_share_5mi",
    "acs_multiunit_housing_share_5mi",
    "acs_rent_burden_30plus_share_5mi",
    "acs_log_population_density_5mi",
    "traffic_log_distance_primary_road_m",
    "traffic_log_distance_primary_secondary_road_m",
)

FEATURE_FAMILIES = {
    feature: (
        "lodes"
        if feature.startswith("lodes_")
        else "richer_acs"
        if feature.startswith("acs_")
        else "traffic_accessibility"
    )
    for feature in FEATURE_IDS
}

UNIT_INTERVAL_FEATURES = frozenset(
    {
        "lodes_same_tract_live_work_share_5mi",
        "lodes_out_of_state_inflow_share_5mi",
        "lodes_high_earnings_job_share_5mi",
        "lodes_retail_trade_job_share_5mi",
        "lodes_accommodation_food_job_share_5mi",
        "lodes_education_health_job_share_5mi",
        "lodes_goods_producing_job_share_5mi",
        "lodes_workplace_block_hhi_5mi",
        "lodes_flow_weighted_origin_hhi_5mi",
        "acs_two_plus_vehicle_household_share_5mi",
        "acs_public_transit_commuter_share_5mi",
        "acs_active_commuter_share_5mi",
        "acs_long_commute_45plus_share_5mi",
        "acs_nonfamily_household_share_5mi",
        "acs_poverty_share_5mi",
        "acs_low_income_under_35k_household_share_5mi",
        "acs_high_income_100k_plus_household_share_5mi",
        "acs_multiunit_housing_share_5mi",
        "acs_rent_burden_30plus_share_5mi",
    }
)


def _json_object(path: Path, code: str) -> dict[str, Any]:
    require(path.is_file(), code, "required JSON object is absent")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ConformanceError(code, "required JSON object is unreadable") from exc
    require(isinstance(value, dict), code, "required JSON value must be an object")
    return value


def load_contract(repository_root: Path) -> dict[str, Any]:
    contract = _json_object(repository_root / "config/model/model14_experimental_public_feature_contract.json", "MODEL14_CONTRACT_MISSING")
    semantic = copy.deepcopy(contract)
    recorded = semantic.pop("content_sha256", None)
    require(
        contract.get("artifact_id") == CONTRACT_ID
        and contract.get("version") == "1.0.0"
        and contract.get("status") == "EXPERIMENTAL_TARGET_BLIND_DEFINITIONS_FROZEN"
        and contract.get("production_source_authority") is False
        and contract.get("target_blind") is True
        and recorded == content_digest(semantic),
        "MODEL14_CONTRACT_MISMATCH",
        "MODEL-14 experimental public-feature contract differs",
    )
    catalog = [str(item.get("feature_id")) for item in contract.get("feature_catalog", [])]
    require(tuple(catalog) == FEATURE_IDS and len(catalog) == 27, "MODEL14_FEATURE_CATALOG_MISMATCH", "MODEL-14 frozen feature catalog differs")
    return contract


def _gzip_content_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with gzip.open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _table_field(variable: str) -> str:
    table, suffix = variable.split("_", 1)
    require(len(suffix) == 4 and suffix[-1] in "EM" and suffix[:3].isdigit(), "MODEL14_ACS_VARIABLE_INVALID", "ACS variable ID is invalid")
    return f"{table}_{suffix[-1]}{suffix[:3]}"


def _moe_variable(estimate_variable: str) -> str:
    return estimate_variable[:-1] + "M"


def _parse_nonnegative(raw: str) -> float | None:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) and value >= 0 else None


@dataclass(frozen=True)
class TractInventory:
    state: str
    rows: Mapping[str, Mapping[str, Any]]
    source_sha256: str


def _load_tract_inventory(repository_root: Path, state: str, transformer: Geo03ProductionTransformer) -> TractInventory:
    config = STATE_CONFIG[state]
    source = repository_root / str(config["tiger_source"])
    manifest = _json_object(repository_root / str(config["tiger_manifest"]), "MODEL14_TIGER_MANIFEST_MISSING")
    require(source.is_file() and file_sha256(source) == manifest.get("byte_sha256"), "MODEL14_TIGER_SOURCE_MISMATCH", "accepted TIGER source bytes differ")
    stem = str(manifest["source_filename"]).removesuffix(".zip")
    with ZipFile(source) as archive:
        records = _read_dbf_records(archive.read(f"{stem}.dbf"))
        projection = archive.read(f"{stem}.prj").decode("ascii")
    require("GCS_North_American_1983" in projection and "GRS_1980" in projection, "MODEL14_TIGER_CRS_MISMATCH", "accepted TIGER CRS differs")
    rows: dict[str, dict[str, Any]] = {}
    for record in records:
        geoid = str(record.get("GEOID", ""))
        require(geoid.startswith(str(config["state_fips"])) and len(geoid) == 11 and geoid.isdigit() and geoid not in rows, "MODEL14_TIGER_GEOID_INVALID", "accepted TIGER GEOID is invalid")
        latitude = _parse_nonnegative(record.get("INTPTLAT", ""))
        if latitude is None:
            try:
                latitude = float(record["INTPTLAT"])
            except (KeyError, ValueError) as exc:
                raise ConformanceError("MODEL14_TIGER_INTERNAL_POINT_INVALID", "accepted TIGER internal point is invalid") from exc
        try:
            longitude = float(record["INTPTLON"])
            aland = float(record["ALAND"])
        except (KeyError, ValueError) as exc:
            raise ConformanceError("MODEL14_TIGER_ATTRIBUTE_INVALID", "accepted TIGER attribute is invalid") from exc
        require(math.isfinite(latitude) and math.isfinite(longitude) and math.isfinite(aland) and aland >= 0, "MODEL14_TIGER_ATTRIBUTE_INVALID", "accepted TIGER attribute is invalid")
        x_value, y_value = transformer.transform(longitude, latitude)
        rows[geoid] = {
            "state": state,
            "state_fips": str(config["state_fips"]),
            "tract_geoid": geoid,
            "aland_sq_m": aland,
            "intpt_x_m": x_value,
            "intpt_y_m": y_value,
        }
    require(len(rows) == int(config["tract_count"]), "MODEL14_TIGER_TRACT_COUNT_MISMATCH", "accepted TIGER tract count differs")
    return TractInventory(state, dict(sorted(rows.items())), file_sha256(source))


def _lodes_files(contract: Mapping[str, Any], state: str) -> dict[str, Mapping[str, Any]]:
    files = {str(item["role"]): item for item in contract["source_families"]["lodes"]["files"] if item["state"] == state}
    require(set(files) == {"crosswalk", "wac", "rac", "od_main", "od_aux"}, "MODEL14_LODES_FILESET_MISMATCH", "LODES file set differs")
    return files


def _verify_lodes_source(path: Path, spec: Mapping[str, Any]) -> None:
    require(path.is_file() and path.stat().st_size == int(spec["byte_length"]), "MODEL14_LODES_SOURCE_MISSING", "LODES source is absent or has the wrong length")
    require(file_sha256(path) == spec["gzip_sha256"] and _gzip_content_sha256(path) == spec["official_csv_sha256"], "MODEL14_LODES_SOURCE_CHECKSUM_MISMATCH", "LODES source checksum differs")


def _load_lodes_state(raw_root: Path, state: str, tract_geoids: set[str], contract: Mapping[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    slug = state.lower()
    files = _lodes_files(contract, state)
    paths = {role: raw_root / "lodes" / slug / str(spec["filename"]) for role, spec in files.items()}
    for role, path in paths.items():
        _verify_lodes_source(path, files[role])
    block_to_tract: dict[str, str] = {}
    with gzip.open(paths["crosswalk"], "rt", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        require(reader.fieldnames is not None and {"tabblk2020", "trct"} <= set(reader.fieldnames), "MODEL14_LODES_XWALK_SCHEMA_MISMATCH", "LODES crosswalk schema differs")
        for row in reader:
            block = str(row["tabblk2020"])
            tract = str(row["trct"])
            require(len(block) == 15 and block.isdigit() and tract in tract_geoids and block not in block_to_tract, "MODEL14_LODES_XWALK_KEY_INVALID", "LODES crosswalk key is invalid")
            block_to_tract[block] = tract
    require(set(block_to_tract.values()) == tract_geoids, "MODEL14_LODES_TRACT_RECONCILIATION_FAILED", "LODES crosswalk does not exactly cover accepted tracts")
    output = {geoid: {field: 0.0 for field in LODES_SUM_FIELDS} for geoid in tract_geoids}
    wac_fields = {"w_geocode", "C000", "CE03", "CNS01", "CNS02", "CNS04", "CNS05", "CNS07", "CNS15", "CNS16", "CNS18"}
    with gzip.open(paths["wac"], "rt", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        require(reader.fieldnames is not None and wac_fields <= set(reader.fieldnames), "MODEL14_LODES_WAC_SCHEMA_MISMATCH", "LODES WAC schema differs")
        for row in reader:
            tract = block_to_tract.get(str(row["w_geocode"]))
            require(tract is not None, "MODEL14_LODES_BLOCK_UNRESOLVED", "LODES workplace block is absent from crosswalk")
            values = {field: int(row[field]) for field in wac_fields - {"w_geocode"}}
            require(all(value >= 0 for value in values.values()), "MODEL14_LODES_COUNT_INVALID", "LODES WAC count is invalid")
            target = output[tract]
            jobs = values["C000"]
            target["lodes_workplace_jobs"] += jobs
            target["lodes_high_earnings_jobs"] += values["CE03"]
            target["lodes_retail_trade_jobs"] += values["CNS07"]
            target["lodes_accommodation_food_jobs"] += values["CNS18"]
            target["lodes_education_health_jobs"] += values["CNS15"] + values["CNS16"]
            target["lodes_goods_producing_jobs"] += values["CNS01"] + values["CNS02"] + values["CNS04"] + values["CNS05"]
            target["lodes_workplace_job_square_sum"] += jobs * jobs
            target["lodes_active_workplace_blocks"] += int(jobs > 0)
    with gzip.open(paths["rac"], "rt", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        require(reader.fieldnames is not None and {"h_geocode", "C000"} <= set(reader.fieldnames), "MODEL14_LODES_RAC_SCHEMA_MISMATCH", "LODES RAC schema differs")
        for row in reader:
            tract = block_to_tract.get(str(row["h_geocode"]))
            require(tract is not None, "MODEL14_LODES_BLOCK_UNRESOLVED", "LODES residence block is absent from crosswalk")
            value = int(row["C000"])
            require(value >= 0, "MODEL14_LODES_COUNT_INVALID", "LODES RAC count is invalid")
            output[tract]["lodes_resident_workers"] += value
    origins: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    with gzip.open(paths["od_main"], "rt", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        require(reader.fieldnames is not None and {"w_geocode", "h_geocode", "S000"} <= set(reader.fieldnames), "MODEL14_LODES_OD_SCHEMA_MISMATCH", "LODES main OD schema differs")
        for row in reader:
            work = block_to_tract.get(str(row["w_geocode"]))
            home = block_to_tract.get(str(row["h_geocode"]))
            require(work is not None and home is not None, "MODEL14_LODES_BLOCK_UNRESOLVED", "LODES main OD block is absent from crosswalk")
            value = int(row["S000"])
            require(value >= 0, "MODEL14_LODES_COUNT_INVALID", "LODES main OD count is invalid")
            output[work]["lodes_main_work_flows"] += value
            if work == home:
                output[work]["lodes_same_tract_live_work_flows"] += value
            origins[work][home] += value
    with gzip.open(paths["od_aux"], "rt", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        require(reader.fieldnames is not None and {"w_geocode", "h_geocode", "S000"} <= set(reader.fieldnames), "MODEL14_LODES_OD_SCHEMA_MISMATCH", "LODES auxiliary OD schema differs")
        for row in reader:
            work = block_to_tract.get(str(row["w_geocode"]))
            require(work is not None and str(row["h_geocode"])[:2] != STATE_CONFIG[state]["state_fips"], "MODEL14_LODES_AUX_FLOW_INVALID", "LODES auxiliary flow does not have the expected state boundary")
            value = int(row["S000"])
            require(value >= 0, "MODEL14_LODES_COUNT_INVALID", "LODES auxiliary OD count is invalid")
            output[work]["lodes_aux_work_flows"] += value
    for tract, values in origins.items():
        total = sum(values.values())
        if total > 0:
            hhi = sum(value * value for value in values.values()) / (total * total)
            output[tract]["lodes_origin_hhi_weighted_flow"] = hhi * total
            output[tract]["lodes_origin_hhi_weight"] = total
    differences = []
    for values in output.values():
        differences.append(values["lodes_workplace_jobs"] - values["lodes_main_work_flows"] - values["lodes_aux_work_flows"])
    return dict(sorted(output.items())), {
        "state": state,
        "crosswalk_block_count": len(block_to_tract),
        "tract_count": len(output),
        "wac_od_total_difference": sum(differences),
        "maximum_absolute_tract_wac_od_difference": max(abs(value) for value in differences),
        "source_files": {role: {"filename": path.name, "gzip_sha256": file_sha256(path), "official_csv_sha256": _gzip_content_sha256(path)} for role, path in sorted(paths.items())},
        "protected_lodes_columns_read_for_features": False,
    }


def _acs_paths(repository_root: Path, raw_root: Path, table: str) -> tuple[Path, Path]:
    slug = table.lower()
    if table in {"B08201", "B08301"}:
        return repository_root / "data/raw/data03" / f"acsdt5y2024-{slug}.dat", repository_root / "data/raw/data03" / f"{slug}.metadata.json"
    return raw_root / "acs" / f"acsdt5y2024-{slug}.dat", raw_root / "acs" / f"{slug}.metadata.json"


def _verify_accepted_acs_reuse(repository_root: Path, table: str, source: Path) -> None:
    path = repository_root / "data/manifests" / f"acs_2024_acs5_{table.lower()}_wisconsin_tract_data03.source_manifest.json"
    manifest = _json_object(path, "MODEL14_ACCEPTED_ACS_MANIFEST_MISSING")
    require(manifest.get("accepted_vintage") == "2024" and source.name == manifest.get("source_filename") and file_sha256(source) == manifest.get("byte_sha256"), "MODEL14_ACCEPTED_ACS_SOURCE_MISMATCH", "accepted DATA-03 ACS source differs")


def _load_acs_components(
    repository_root: Path,
    raw_root: Path,
    inventories: Mapping[str, TractInventory],
    contract: Mapping[str, Any],
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    by_geoid: dict[str, dict[str, Any]] = {geoid: {} for inventory in inventories.values() for geoid in inventory.rows}
    table_components: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for component, (table, variable) in ACS_COMPONENTS.items():
        table_components[table].append((component, variable))
    source_report: dict[str, Any] = {}
    richer = contract["source_families"]["richer_acs"]
    for table in sorted(table_components):
        source, metadata_path = _acs_paths(repository_root, raw_root, table)
        require(source.is_file() and metadata_path.is_file(), "MODEL14_ACS_SOURCE_MISSING", "one required ACS source or metadata file is absent")
        if table in {"B08201", "B08301"}:
            _verify_accepted_acs_reuse(repository_root, table, source)
        else:
            require(file_sha256(source) == richer["raw_file_sha256"][table] and file_sha256(metadata_path) == richer["metadata_sha256"][table], "MODEL14_ACS_SOURCE_CHECKSUM_MISMATCH", "one experimental ACS source checksum differs")
        metadata = _json_object(metadata_path, "MODEL14_ACS_METADATA_INVALID")
        variables = metadata.get("variables")
        require(isinstance(variables, Mapping), "MODEL14_ACS_METADATA_INVALID", "ACS metadata variables are absent")
        for variable, label in EXPECTED_LABELS.items():
            if variable.startswith(table + "_"):
                item = variables.get(variable)
                require(isinstance(item, Mapping) and item.get("label") == label, "MODEL14_ACS_METADATA_LABEL_MISMATCH", "one ACS variable label differs")
        selected = table_components[table]
        estimate_fields = {_table_field(variable): (component, variable) for component, variable in selected}
        moe_fields = {_table_field(_moe_variable(variable)): component for component, variable in selected}
        observed: dict[str, int] = {state: 0 for state in inventories}
        seen: set[str] = set()
        with source.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="|")
            required_fields = {"GEO_ID", *estimate_fields, *moe_fields}
            require(reader.fieldnames is not None and required_fields <= set(reader.fieldnames), "MODEL14_ACS_SOURCE_SCHEMA_MISMATCH", "one ACS table schema differs")
            for row in reader:
                raw_id = str(row["GEO_ID"])
                if not raw_id.startswith("1400000US"):
                    continue
                geoid = raw_id.removeprefix("1400000US")
                state = "MI" if geoid.startswith("26") else "WI" if geoid.startswith("55") else None
                if state is None:
                    continue
                require(geoid in inventories[state].rows and geoid not in seen, "MODEL14_ACS_GEOID_RECONCILIATION_FAILED", "ACS tract key is invalid or duplicate")
                target = by_geoid[geoid]
                for field, (component, _variable) in estimate_fields.items():
                    target[f"acs_{component}_estimate"] = _parse_nonnegative(row[field])
                    target[f"acs_{component}_moe"] = _parse_nonnegative(row[_table_field(_moe_variable(_variable))])
                seen.add(geoid)
                observed[state] += 1
        expected = set().union(*(set(inventory.rows) for inventory in inventories.values()))
        require(seen == expected, "MODEL14_ACS_GEOID_RECONCILIATION_FAILED", "ACS table does not exactly cover accepted MI/WI tracts")
        source_report[table] = {
            "source_filename": source.name,
            "source_sha256": file_sha256(source),
            "metadata_filename": metadata_path.name,
            "metadata_sha256": file_sha256(metadata_path),
            "michigan_tract_count": observed["MI"],
            "wisconsin_tract_count": observed["WI"],
            "component_count": len(selected),
            "estimate_moe_pairs_retained": True,
        }
    return dict(sorted(by_geoid.items())), source_report


def _read_shapefile_lines(data: bytes) -> list[BaseGeometry]:
    """Read PolyLine/PolyLineZ/PolyLineM records without adding a GIS reader dependency."""
    require(len(data) >= 100 and struct.unpack_from(">I", data, 0)[0] == 9994, "MODEL14_ROAD_SHP_INVALID", "road shapefile header is invalid")
    declared_bytes = struct.unpack_from(">I", data, 24)[0] * 2
    require(declared_bytes == len(data) and struct.unpack_from("<I", data, 28)[0] == 1000 and struct.unpack_from("<I", data, 32)[0] in {3, 13, 23}, "MODEL14_ROAD_SHP_INVALID", "road shapefile identity differs")
    output: list[BaseGeometry] = []
    offset = 100
    expected_record = 1
    while offset < len(data):
        require(offset + 8 <= len(data), "MODEL14_ROAD_SHP_TRUNCATED", "road record header is truncated")
        record_number, content_words = struct.unpack_from(">II", data, offset)
        content_start = offset + 8
        content_end = content_start + content_words * 2
        require(record_number == expected_record and content_words > 0 and content_end <= len(data), "MODEL14_ROAD_SHP_TRUNCATED", "road record is invalid or truncated")
        shape_type = struct.unpack_from("<I", data, content_start)[0]
        require(shape_type in {3, 13, 23} and content_start + 44 <= content_end, "MODEL14_ROAD_SHP_TYPE_INVALID", "road record is not polyline geometry")
        part_count, point_count = struct.unpack_from("<II", data, content_start + 36)
        parts_start = content_start + 44
        points_start = parts_start + part_count * 4
        minimum_end = points_start + point_count * 16
        require(part_count > 0 and point_count >= 2 and minimum_end <= content_end, "MODEL14_ROAD_SHP_TRUNCATED", "road coordinates are invalid or truncated")
        offsets = list(struct.unpack_from(f"<{part_count}I", data, parts_start))
        require(offsets[0] == 0 and offsets == sorted(set(offsets)) and offsets[-1] < point_count, "MODEL14_ROAD_SHP_PART_INVALID", "road part index is invalid")
        points = [struct.unpack_from("<dd", data, points_start + index * 16) for index in range(point_count)]
        require(all(math.isfinite(x_value) and math.isfinite(y_value) for x_value, y_value in points), "MODEL14_ROAD_SHP_COORDINATE_INVALID", "road geometry has a nonfinite coordinate")
        bounds = offsets + [point_count]
        parts = [[(float(x_value), float(y_value)) for x_value, y_value in points[start:stop]] for start, stop in zip(bounds, bounds[1:])]
        require(all(len(part) >= 2 and len(set(part)) >= 2 for part in parts), "MODEL14_ROAD_SHP_GEOMETRY_INVALID", "road line is degenerate")
        geometry: BaseGeometry = LineString(parts[0]) if len(parts) == 1 else MultiLineString(parts)
        require(geometry.is_valid and not geometry.is_empty, "MODEL14_ROAD_SHP_GEOMETRY_INVALID", "road line is invalid")
        output.append(geometry)
        offset = content_end
        expected_record += 1
    require(offset == len(data) and output, "MODEL14_ROAD_SHP_INVALID", "road shapefile did not end on a complete record")
    return output


def _load_traffic_state(
    raw_root: Path,
    state: str,
    inventory: TractInventory,
    contract: Mapping[str, Any],
    transformer: Geo03ProductionTransformer,
) -> tuple[dict[str, dict[str, float]], dict[str, Any]]:
    spec = next(item for item in contract["source_families"]["traffic_accessibility"]["files"] if item["state"] == state)
    source = raw_root / "traffic" / str(spec["filename"])
    require(source.is_file() and source.stat().st_size == int(spec["byte_length"]) and file_sha256(source) == spec["sha256"], "MODEL14_TRAFFIC_SOURCE_MISMATCH", "traffic source checksum differs")
    stem = source.name.removesuffix(".zip")
    with ZipFile(source) as archive:
        records = _read_dbf_records(archive.read(f"{stem}.dbf"))
        lines = _read_shapefile_lines(archive.read(f"{stem}.shp"))
        projection = archive.read(f"{stem}.prj").decode("ascii")
    require(len(records) == len(lines) and "GCS_North_American_1983" in projection and "GRS_1980" in projection, "MODEL14_TRAFFIC_SOURCE_SCHEMA_MISMATCH", "traffic attributes, geometries, or CRS differ")
    classes = Counter(str(row.get("MTFCC", "")) for row in records)
    require(set(classes) == {"S1100", "S1200"} and classes["S1100"] > 0 and classes["S1200"] > 0, "MODEL14_TRAFFIC_MTFCC_MISMATCH", "traffic road classes differ")
    projected = [transform_geometry(transformer._runtime.transform, line) for line in lines]
    require(all(item.is_valid and not item.is_empty for item in projected), "MODEL14_TRAFFIC_PROJECTION_FAILED", "one projected road geometry is invalid")
    primary = [line for line, record in zip(projected, records) if record["MTFCC"] == "S1100"]
    all_tree = STRtree(projected)
    primary_tree = STRtree(primary)
    output: dict[str, dict[str, float]] = {}
    for geoid, tract in inventory.rows.items():
        point = Point(float(tract["intpt_x_m"]), float(tract["intpt_y_m"]))
        primary_index = int(primary_tree.nearest(point))
        all_index = int(all_tree.nearest(point))
        primary_distance = float(point.distance(primary[primary_index]))
        all_distance = float(point.distance(projected[all_index]))
        require(math.isfinite(primary_distance) and primary_distance >= 0 and math.isfinite(all_distance) and 0 <= all_distance <= primary_distance + 1e-7, "MODEL14_TRAFFIC_DISTANCE_INVALID", "traffic proximity distance is invalid")
        output[geoid] = {
            "traffic_distance_primary_road_m": primary_distance,
            "traffic_distance_primary_secondary_road_m": all_distance,
        }
    return output, {
        "state": state,
        "source_filename": source.name,
        "source_sha256": file_sha256(source),
        "road_feature_count": len(projected),
        "mtfcc_counts": dict(sorted(classes.items())),
        "tract_count": len(output),
        "source_crs": "EPSG:4269",
        "target_crs": "EPSG:5070",
        "operation_id": contract["geography_authority"]["operation_id"],
    }


def _complete_sum(rows: Sequence[Mapping[str, Any]], field: str) -> float | None:
    values = [row.get(field) for row in rows]
    if not all(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value)) for value in values):
        return None
    return sum(float(value) for value in values)


def _complete_fields_sum(rows: Sequence[Mapping[str, Any]], fields: Sequence[str]) -> float | None:
    values = [_complete_sum(rows, field) for field in fields]
    if any(value is None for value in values):
        return None
    return sum(float(value) for value in values if value is not None)


def _ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator <= 0 or numerator < 0:
        return None
    value = numerator / denominator
    return value if math.isfinite(value) else None


def aggregate_context_features(
    matrix_rows: Mapping[str, Mapping[str, Any]],
    member_geoids: Sequence[str],
    anchor_tract_geoid: str,
) -> dict[str, float | None]:
    """Aggregate frozen tract components using accepted five-mile members."""
    unique = list(dict.fromkeys(str(value) for value in member_geoids))
    require(unique and len(unique) == len(member_geoids) and anchor_tract_geoid in matrix_rows and all(geoid in matrix_rows for geoid in unique), "MODEL14_CONTEXT_GEOID_INVALID", "MODEL-14 context GEOIDs are invalid")
    rows = [matrix_rows[geoid] for geoid in unique]
    require(len({str(row["state"]) for row in rows}) == 1 and str(matrix_rows[anchor_tract_geoid]["state"]) == str(rows[0]["state"]), "MODEL14_CONTEXT_STATE_MISMATCH", "MODEL-14 context crosses state support")
    jobs = _complete_sum(rows, "lodes_workplace_jobs")
    resident = _complete_sum(rows, "lodes_resident_workers")
    all_flows = _complete_fields_sum(rows, ("lodes_main_work_flows", "lodes_aux_work_flows"))
    main_flows = _complete_sum(rows, "lodes_main_work_flows")
    aux_flows = _complete_sum(rows, "lodes_aux_work_flows")
    same_tract = _complete_sum(rows, "lodes_same_tract_live_work_flows")
    aland = _complete_sum(rows, "aland_sq_m")
    population = _complete_sum(rows, "acs_population_total_estimate")
    vehicle_total = _complete_sum(rows, "acs_vehicle_households_total_estimate")
    vehicle_two_plus = _complete_fields_sum(rows, ("acs_vehicle_households_two_estimate", "acs_vehicle_households_three_estimate", "acs_vehicle_households_four_plus_estimate"))
    commuters = _complete_sum(rows, "acs_commuters_total_estimate")
    active_commuters = _complete_fields_sum(rows, ("acs_commuters_bicycle_estimate", "acs_commuters_walked_estimate"))
    commute_time = _complete_sum(rows, "acs_commute_time_total_estimate")
    long_commute = _complete_fields_sum(rows, ("acs_commute_time_45_59_estimate", "acs_commute_time_60_89_estimate", "acs_commute_time_90_plus_estimate"))
    income_total = _complete_sum(rows, "acs_income_households_total_estimate")
    income_low = _complete_fields_sum(rows, tuple(f"acs_income_low_{index:03d}_estimate" for index in range(2, 8)))
    income_high = _complete_fields_sum(rows, tuple(f"acs_income_high_{index:03d}_estimate" for index in range(14, 18)))
    housing_total = _complete_sum(rows, "acs_housing_units_total_estimate")
    multiunit = _complete_fields_sum(rows, tuple(f"acs_housing_multiunit_{index:03d}_estimate" for index in range(4, 10)))
    rent_denominator = _complete_fields_sum(rows, tuple(f"acs_rent_computed_{index:03d}_estimate" for index in range(2, 11)))
    rent_burden = _complete_fields_sum(rows, tuple(f"acs_rent_computed_{index:03d}_estimate" for index in range(7, 11)))
    origin_weight = _complete_sum(rows, "lodes_origin_hhi_weight")
    anchor = matrix_rows[anchor_tract_geoid]
    features: dict[str, float | None] = {
        "lodes_log_workplace_jobs_5mi": None if jobs is None else math.log1p(jobs),
        "lodes_log_resident_workers_5mi": None if resident is None else math.log1p(resident),
        "lodes_log_jobs_to_resident_worker_ratio_5mi": None if jobs is None or resident is None else math.log((jobs + 1.0) / (resident + 1.0)),
        "lodes_net_job_worker_imbalance_share_5mi": None if jobs is None or resident is None or jobs + resident <= 0 else (jobs - resident) / (jobs + resident),
        "lodes_same_tract_live_work_share_5mi": _ratio(same_tract, all_flows),
        "lodes_out_of_state_inflow_share_5mi": _ratio(aux_flows, all_flows),
        "lodes_high_earnings_job_share_5mi": _ratio(_complete_sum(rows, "lodes_high_earnings_jobs"), jobs),
        "lodes_retail_trade_job_share_5mi": _ratio(_complete_sum(rows, "lodes_retail_trade_jobs"), jobs),
        "lodes_accommodation_food_job_share_5mi": _ratio(_complete_sum(rows, "lodes_accommodation_food_jobs"), jobs),
        "lodes_education_health_job_share_5mi": _ratio(_complete_sum(rows, "lodes_education_health_jobs"), jobs),
        "lodes_goods_producing_job_share_5mi": _ratio(_complete_sum(rows, "lodes_goods_producing_jobs"), jobs),
        "lodes_workplace_block_hhi_5mi": _ratio(_complete_sum(rows, "lodes_workplace_job_square_sum"), None if jobs is None else jobs * jobs),
        "lodes_flow_weighted_origin_hhi_5mi": _ratio(_complete_sum(rows, "lodes_origin_hhi_weighted_flow"), origin_weight),
        "lodes_log_active_workplace_blocks_5mi": None if (active := _complete_sum(rows, "lodes_active_workplace_blocks")) is None else math.log1p(active),
        "acs_two_plus_vehicle_household_share_5mi": _ratio(vehicle_two_plus, vehicle_total),
        "acs_public_transit_commuter_share_5mi": _ratio(_complete_sum(rows, "acs_commuters_public_transit_estimate"), commuters),
        "acs_active_commuter_share_5mi": _ratio(active_commuters, commuters),
        "acs_long_commute_45plus_share_5mi": _ratio(long_commute, commute_time),
        "acs_nonfamily_household_share_5mi": _ratio(_complete_sum(rows, "acs_nonfamily_households_estimate"), _complete_sum(rows, "acs_households_total_estimate")),
        "acs_poverty_share_5mi": _ratio(_complete_sum(rows, "acs_poverty_below_estimate"), _complete_sum(rows, "acs_poverty_universe_estimate")),
        "acs_low_income_under_35k_household_share_5mi": _ratio(income_low, income_total),
        "acs_high_income_100k_plus_household_share_5mi": _ratio(income_high, income_total),
        "acs_multiunit_housing_share_5mi": _ratio(multiunit, housing_total),
        "acs_rent_burden_30plus_share_5mi": _ratio(rent_burden, rent_denominator),
        "acs_log_population_density_5mi": None if population is None or aland is None or aland <= 0 else math.log1p(population / (aland / SQ_METERS_PER_SQ_MILE)),
        "traffic_log_distance_primary_road_m": math.log1p(float(anchor["traffic_distance_primary_road_m"])),
        "traffic_log_distance_primary_secondary_road_m": math.log1p(float(anchor["traffic_distance_primary_secondary_road_m"])),
    }
    require(tuple(features) == FEATURE_IDS and all(value is None or math.isfinite(float(value)) for value in features.values()), "MODEL14_DERIVED_FEATURE_INVALID", "one MODEL-14 derived feature is invalid")
    require(
        all(features[feature] is None or -1e-12 <= float(features[feature]) <= 1.0 + 1e-12 for feature in UNIT_INTERVAL_FEATURES)
        and (
            features["lodes_net_job_worker_imbalance_share_5mi"] is None
            or -1.0 - 1e-12 <= float(features["lodes_net_job_worker_imbalance_share_5mi"]) <= 1.0 + 1e-12
        ),
        "MODEL14_DERIVED_FEATURE_RANGE_INVALID",
        "one MODEL-14 bounded feature is outside its semantic range",
    )
    return features


@dataclass(frozen=True)
class PublicFreeze:
    """Verified outside-Git public tract matrix and target-blind freeze report."""

    root: Path
    report: Mapping[str, Any]
    rows: Mapping[str, Mapping[str, Any]]


def _matrix_columns() -> tuple[str, ...]:
    acs_columns = tuple(
        column
        for component in sorted(ACS_COMPONENTS)
        for column in (f"acs_{component}_estimate", f"acs_{component}_moe")
    )
    return (
        "tract_geoid",
        "state",
        "state_fips",
        "aland_sq_m",
        "intpt_x_m",
        "intpt_y_m",
        *LODES_SUM_FIELDS,
        *acs_columns,
        "traffic_distance_primary_road_m",
        "traffic_distance_primary_secondary_road_m",
        *FEATURE_IDS,
    )


def _assert_public_paths(repository_root: Path, raw_root: Path, output_dir: Path) -> tuple[Path, Path, Path]:
    root = repository_root.resolve()
    raw = raw_root.resolve()
    output = output_dir.resolve()
    require(
        _is_within(raw, root / "data" / "raw") and raw != root / "data" / "raw",
        "MODEL14_RAW_ROOT_INVALID",
        "MODEL-14 raw root must be a bounded ignored public-data directory",
    )
    require(
        _is_within(output, root / "outputs") and output != root / "outputs",
        "MODEL14_OUTPUT_ROOT_INVALID",
        "MODEL-14 output must be a bounded ignored output directory",
    )
    require(not output.exists(), "MODEL14_OUTPUT_OVERWRITE_DENIED", "MODEL-14 public freeze output already exists")
    return root, raw, output


def _five_mile_memberships(inventory: TractInventory, radius_m: float) -> tuple[dict[str, list[str]], dict[str, Any]]:
    geoids = list(inventory.rows)
    points = [Point(float(inventory.rows[geoid]["intpt_x_m"]), float(inventory.rows[geoid]["intpt_y_m"])) for geoid in geoids]
    tree = STRtree(points)
    memberships: dict[str, list[str]] = {}
    counts: list[int] = []
    for geoid, point in zip(geoids, points):
        indexes = tree.query(point, predicate="dwithin", distance=radius_m)
        members = sorted(
            geoids[int(index)]
            for index in indexes
            if float(point.distance(points[int(index)])) <= radius_m
        )
        require(geoid in members and members, "MODEL14_TARGET_BLIND_MEMBERSHIP_INVALID", "target-blind tract-anchor membership is invalid")
        memberships[geoid] = members
        counts.append(len(members))
    return memberships, {
        "state": inventory.state,
        "anchor_tract_count": len(memberships),
        "minimum_member_count": min(counts),
        "maximum_member_count": max(counts),
        "radius_m": radius_m,
        "distance_rule": "accepted EPSG:5070 internal-point distance less than or equal to radius",
        "protected_anchor_accessed": False,
    }


def _numeric_text(value: Any) -> str:
    if value is None:
        return ""
    require(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value)), "MODEL14_MATRIX_VALUE_INVALID", "public matrix contains an invalid numeric value")
    return format(float(value), ".17g")


def _write_public_matrix(path: Path, rows: Mapping[str, Mapping[str, Any]]) -> None:
    columns = _matrix_columns()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n", extrasaction="raise")
        writer.writeheader()
        for geoid in sorted(rows):
            row = rows[geoid]
            output = {
                column: str(row[column]) if column in {"tract_geoid", "state", "state_fips"} else _numeric_text(row.get(column))
                for column in columns
            }
            writer.writerow(output)
        handle.flush()
        os.fsync(handle.fileno())


def _feature_coverage(rows: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for feature in FEATURE_IDS:
        by_state: dict[str, Any] = {}
        for state in STATE_CONFIG:
            values = [float(row[feature]) for row in rows.values() if row["state"] == state and row[feature] is not None]
            state_count = sum(row["state"] == state for row in rows.values())
            require(all(math.isfinite(value) for value in values), "MODEL14_FEATURE_COVERAGE_INVALID", "one feature has a nonfinite value")
            by_state[state] = {
                "tract_count": state_count,
                "computable_count": len(values),
                "missing_count": state_count - len(values),
                "minimum": None if not values else min(values),
                "maximum": None if not values else max(values),
            }
        output[feature] = {"family": FEATURE_FAMILIES[feature], "by_state": by_state}
    return output


def materialize_public_freeze(
    repository_root: Path,
    raw_root: Path,
    output_dir: Path,
) -> PublicFreeze:
    """Create one immutable, public-only statewide freeze before target access."""
    root, raw, output = _assert_public_paths(repository_root, raw_root, output_dir)
    contract = load_contract(root)
    specification = _json_object(root / "config/geo/geo03_internal_point_membership_spatial_spec.json", "MODEL14_GEO03_AUTHORITY_MISSING")
    transformer = Geo03ProductionTransformer(specification)
    inventories = {state: _load_tract_inventory(root, state, transformer) for state in STATE_CONFIG}
    require(
        sum(len(inventory.rows) for inventory in inventories.values()) == int(contract["freeze_policy"]["expected_matrix_row_count"]),
        "MODEL14_TRACT_INVENTORY_MISMATCH",
        "accepted combined tract inventory differs",
    )

    lodes: dict[str, dict[str, dict[str, Any]]] = {}
    lodes_reports: dict[str, Any] = {}
    for state, inventory in inventories.items():
        lodes[state], lodes_reports[state] = _load_lodes_state(raw, state, set(inventory.rows), contract)
    acs, acs_report = _load_acs_components(root, raw, inventories, contract)
    traffic: dict[str, dict[str, dict[str, float]]] = {}
    traffic_reports: dict[str, Any] = {}
    for state, inventory in inventories.items():
        traffic[state], traffic_reports[state] = _load_traffic_state(raw, state, inventory, contract, transformer)

    rows: dict[str, dict[str, Any]] = {}
    for state, inventory in inventories.items():
        require(set(lodes[state]) == set(inventory.rows) and set(traffic[state]) == set(inventory.rows), "MODEL14_PUBLIC_KEY_RECONCILIATION_FAILED", "one public family does not exactly reconcile to accepted tract keys")
        for geoid, base in inventory.rows.items():
            require(geoid in acs and geoid not in rows, "MODEL14_PUBLIC_KEY_RECONCILIATION_FAILED", "ACS or combined public key reconciliation failed")
            rows[geoid] = {**base, **lodes[state][geoid], **acs[geoid], **traffic[state][geoid]}

    membership_reports: dict[str, Any] = {}
    for state, inventory in inventories.items():
        memberships, membership_reports[state] = _five_mile_memberships(inventory, float(contract["geography_authority"]["model_context_radius_m"]))
        for geoid, members in memberships.items():
            rows[geoid].update(aggregate_context_features(rows, members, geoid))

    columns = _matrix_columns()
    require(
        len(rows) == 4559
        and set().union(*(set(inventory.rows) for inventory in inventories.values())) == set(rows)
        and all(set(row) == set(columns) for row in rows.values()),
        "MODEL14_PUBLIC_MATRIX_RECONCILIATION_FAILED",
        "public tract matrix columns or rows differ",
    )
    output.mkdir(parents=True, exist_ok=False)
    matrix_path = output / MATRIX_FILENAME
    _write_public_matrix(matrix_path, rows)
    coverage = _feature_coverage(rows)
    family_status = {
        family: {
            "status": contract["source_families"][family]["status"],
            "candidate_feature_count": int(contract["model_feature_count_by_family"][family]),
        }
        for family in contract["feature_family_order"]
    }
    report: dict[str, Any] = {
        "package_id": FREEZE_ID,
        "version": "1.0.0",
        "state": "TARGET_BLIND_PUBLIC_FEATURES_FROZEN",
        "controlling_task": "MODEL-14",
        "contract_id": CONTRACT_ID,
        "contract_content_sha256": contract["content_sha256"],
        "chronology": {
            "public_sources_acquired_before_target_access": True,
            "feature_definitions_frozen_before_target_access": True,
            "public_matrix_materialized_before_target_access": True,
            "target_values_accessed": 0,
            "protected_anchor_rows_accessed": 0,
            "sealed_or_prospective_evidence_accessed": False,
        },
        "matrix": {
            "filename": MATRIX_FILENAME,
            "byte_sha256": file_sha256(matrix_path),
            "row_count": len(rows),
            "column_count": len(columns),
            "columns": list(columns),
            "state_row_counts": {state: sum(row["state"] == state for row in rows.values()) for state in STATE_CONFIG},
            "key_reconciliation": "exact accepted 2024 MI/WI tract keys",
            "row_dropping": False,
            "missing_to_zero": False,
            "tract_anchor_diagnostic_features_only": True,
            "evaluation_anchor_features_recomputed_from_the_same_frozen_components_and_definitions_using_accepted_existing_support_memberships": True,
        },
        "geography": {
            "accepted_vintage": "2024",
            "operation_fingerprint_sha256": transformer.operation_fingerprint,
            "membership_reports": membership_reports,
            "inventory_source_sha256": {state: inventory.source_sha256 for state, inventory in inventories.items()},
            "authority_changed": False,
        },
        "source_families": family_status,
        "source_validation": {
            "lodes": lodes_reports,
            "richer_acs": acs_report,
            "traffic_accessibility": traffic_reports,
            "business_context": {"status": contract["source_families"]["business_context"]["status"], "materialized_feature_count": 0},
        },
        "candidate_feature_count": len(FEATURE_IDS),
        "candidate_feature_count_by_family": contract["model_feature_count_by_family"],
        "feature_coverage": coverage,
        "protected_characteristic_policy": contract["protected_characteristic_policy"],
        "public_only": True,
        "tracked_git_storage": False,
        "ready_marker_written_last": True,
    }
    report["content_sha256"] = content_digest(report)
    report_path = output / FREEZE_FILENAME
    write_json_exclusive(report_path, report)
    ready = {
        "state": "READY",
        "package_id": FREEZE_ID,
        "contract_content_sha256": contract["content_sha256"],
        "freeze_filename": FREEZE_FILENAME,
        "freeze_sha256": file_sha256(report_path),
        "matrix_filename": MATRIX_FILENAME,
        "matrix_sha256": file_sha256(matrix_path),
        "target_values_accessed": 0,
        "protected_anchor_rows_accessed": 0,
        "ready_marker_written_last": True,
    }
    write_json_exclusive(output / READY_FILENAME, ready)
    return PublicFreeze(output, report, dict(sorted(rows.items())))


def load_public_freeze(directory: Path) -> PublicFreeze:
    """Verify one immutable MODEL-14 public freeze without filesystem discovery."""
    root = directory.resolve()
    ready = _json_object(root / READY_FILENAME, "MODEL14_PUBLIC_FREEZE_NOT_READY")
    report = _json_object(root / FREEZE_FILENAME, "MODEL14_PUBLIC_FREEZE_INVALID")
    matrix_path = root / MATRIX_FILENAME
    require(
        ready.get("state") == "READY"
        and ready.get("package_id") == FREEZE_ID
        and ready.get("freeze_filename") == FREEZE_FILENAME
        and ready.get("matrix_filename") == MATRIX_FILENAME
        and ready.get("ready_marker_written_last") is True
        and ready.get("target_values_accessed") == 0
        and ready.get("protected_anchor_rows_accessed") == 0
        and matrix_path.is_file()
        and ready.get("freeze_sha256") == file_sha256(root / FREEZE_FILENAME)
        and ready.get("matrix_sha256") == file_sha256(matrix_path),
        "MODEL14_PUBLIC_FREEZE_NOT_READY",
        "MODEL-14 public freeze READY binding differs",
    )
    semantic = copy.deepcopy(report)
    recorded = semantic.pop("content_sha256", None)
    require(
        report.get("package_id") == FREEZE_ID
        and report.get("state") == "TARGET_BLIND_PUBLIC_FEATURES_FROZEN"
        and recorded == content_digest(semantic)
        and report.get("candidate_feature_count") == len(FEATURE_IDS)
        and report.get("chronology", {}).get("target_values_accessed") == 0
        and report.get("chronology", {}).get("protected_anchor_rows_accessed") == 0,
        "MODEL14_PUBLIC_FREEZE_INVALID",
        "MODEL-14 target-blind freeze report differs",
    )
    columns = _matrix_columns()
    rows: dict[str, dict[str, Any]] = {}
    with matrix_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        require(reader.fieldnames is not None and tuple(reader.fieldnames) == columns, "MODEL14_PUBLIC_MATRIX_SCHEMA_MISMATCH", "public matrix schema differs")
        for source in reader:
            geoid = str(source["tract_geoid"])
            state = str(source["state"])
            state_fips = str(source["state_fips"])
            require(
                geoid not in rows
                and state in STATE_CONFIG
                and state_fips == STATE_CONFIG[state]["state_fips"]
                and geoid.startswith(state_fips)
                and len(geoid) == 11
                and geoid.isdigit(),
                "MODEL14_PUBLIC_MATRIX_KEY_INVALID",
                "public matrix key is invalid or duplicate",
            )
            row: dict[str, Any] = {"tract_geoid": geoid, "state": state, "state_fips": state_fips}
            for column in columns[3:]:
                raw = source[column]
                if raw == "":
                    row[column] = None
                    continue
                try:
                    value = float(raw)
                except ValueError as exc:
                    raise ConformanceError("MODEL14_PUBLIC_MATRIX_VALUE_INVALID", "public matrix numeric value is invalid") from exc
                require(math.isfinite(value), "MODEL14_PUBLIC_MATRIX_VALUE_INVALID", "public matrix numeric value is nonfinite")
                row[column] = value
            rows[geoid] = row
    require(
        len(rows) == 4559
        and sum(row["state"] == "MI" for row in rows.values()) == 3017
        and sum(row["state"] == "WI" for row in rows.values()) == 1542,
        "MODEL14_PUBLIC_MATRIX_RECONCILIATION_FAILED",
        "public matrix tract accounting differs",
    )
    return PublicFreeze(root, report, dict(sorted(rows.items())))


def compare_public_freezes(first: Path, second: Path) -> dict[str, Any]:
    """Require byte-identical independent target-blind public freezes."""
    load_public_freeze(first)
    load_public_freeze(second)
    left = first.resolve()
    right = second.resolve()
    left_files = sorted(path.relative_to(left).as_posix() for path in left.rglob("*") if path.is_file())
    right_files = sorted(path.relative_to(right).as_posix() for path in right.rglob("*") if path.is_file())
    require(left_files == right_files, "MODEL14_PUBLIC_FREEZE_FILESET_MISMATCH", "public freeze file sets differ")
    left_hashes = {name: file_sha256(left / name) for name in left_files}
    right_hashes = {name: file_sha256(right / name) for name in right_files}
    require(left_hashes == right_hashes, "MODEL14_PUBLIC_FREEZE_NONDETERMINISTIC", "public freeze bytes differ across independent runs")
    return {
        "report_id": "MODEL14_TARGET_BLIND_PUBLIC_FREEZE_DETERMINISM_V1",
        "state": "DETERMINISTIC_BYTE_IDENTICAL",
        "file_count": len(left_files),
        "file_sha256": left_hashes,
        "target_values_accessed": 0,
        "protected_anchor_rows_accessed": 0,
    }
