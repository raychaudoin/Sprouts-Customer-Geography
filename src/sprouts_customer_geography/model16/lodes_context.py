"""Bounded 2019 LODES7 incoming job flows on original 2010-era tracts."""
from __future__ import annotations

from collections import defaultdict
import csv
import gzip
import hashlib
import math
from email.utils import parsedate_to_datetime
from pathlib import Path

from sprouts_customer_geography.pipe01.errors import require


FLOW_FEATURES = (
    "lodes_external_origin_job_share_5mi",
    "lodes_mean_commute_distance_km_5mi",
)
MIN_DISTANCE_JOB_COVERAGE = 0.95


def feature_catalog():
    return [
        {"feature_id": FLOW_FEATURES[0], "family": "commuting_flows", "source": "LODES7_2019_MAIN_AUX_OD_WAC", "baseline": False,
         "transform": "jobs arriving from home tracts outside the 5-mile workplace support / all jobs in the workplace support",
         "business_hypothesis": "External commuter inflow captures imported workplace activity; not observed retail visits",
         "support": "state-isolated 5-mile 2019 TIGER tract representative points, containing tract forced; origin may be in any state",
         "source_release": "retained LODES7 archive; data reference 2019; source and creation dates must precede 2024",
         "missingness": "unknown workplace geography or unmatched OD/WAC job margins fails closed; zero total jobs remains null"},
        {"feature_id": FLOW_FEATURES[1], "family": "commuting_flows", "source": "LODES7_2019_MAIN_AUX_OD_WAC", "baseline": False,
         "transform": "job-weighted Euclidean distance in NAD83 Albers between workplace/home tract internal points in kilometers, conditional on at least95percent geocoded jobs",
         "business_hypothesis": "Commute reach indicates workplace draw; coarse straight-line tract proxy, not actual route distance or travel time",
         "support": "same workplace support; MI/WI origin/destination tract points only for distance, national origins retained in coverage denominator",
         "source_release": "retained LODES7 archive; data reference 2019; 2019 TIGER 2010-era tracts",
         "missingness": "origins outside acquired MI/WI geometry are not zero distance; coverage below0.95 yields null; positive cross-block within-tract trips have unresolved sub-tract distance"},
    ]


def _job_count(value):
    require(isinstance(value, str) and value.isdigit(), "MODEL16_LODES_JOBS", "public LODES job count is missing or invalid")
    return int(value)


def _block(value, fips=None):
    require(len(value) == 15 and value.isdigit() and (fips is None or value.startswith(fips)),
            "MODEL16_LODES_BLOCK", "public LODES block geography does not reconcile")
    return value


def _validate_creation(value):
    require(len(value) == 8 and value.isdigit() and 2019 <= int(value[:4]) <= 2023,
            "MODEL16_LODES_CREATEDATE", "public LODES row was not created before the earliest forecast cutoff")


def validate_lodes_archive(root, state, verify):
    version_path = Path(root) / f"lodes7-{state}-version.txt"
    checksum_path = Path(root) / f"lodes7-{state}-checksums.txt"
    verify(version_path)
    verify(checksum_path)
    version = version_path.read_text()
    require("Data Vintage: 20211018_1647" in version and "Release Format Version 7.5" in version,
            "MODEL16_LODES_VERSION", "LODES archive version differs from the frozen 2021 release")
    checksums = {}
    for line in checksum_path.read_text().splitlines():
        fields = line.split()
        if len(fields) == 2:
            checksums[fields[1].lstrip("*")] = fields[0]
    names = [f"{state}_od_{kind}_JT00_2019.csv" for kind in ("main", "aux")] + [f"{state}_wac_S000_JT00_2019.csv"]
    for name in names:
        require(name in checksums, "MODEL16_LODES_OFFICIAL_CHECKSUM_MISSING", "official LODES file checksum is missing")
        digest = hashlib.sha256()
        with gzip.open(Path(root) / (name + ".gz"), "rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        require(digest.hexdigest() == checksums[name], "MODEL16_LODES_OFFICIAL_CHECKSUM", "LODES uncompressed bytes differ from Census checksum")
    return {"archive_data_vintage": "20211018_1647", "format_version": "7.5", "official_uncompressed_checksums_verified": len(names)}


def read_lodes_state(root, state, verify):
    """Only job totals and geography enter aggregates; no worker disaggregations."""
    fips = {"mi": "26", "wi": "55"}[state]
    flows = defaultdict(lambda: defaultdict(int))
    counts, creation_dates = {}, set()
    for kind in ("main", "aux"):
        path = Path(root) / f"{state}_od_{kind}_JT00_2019.csv.gz"
        receipt = verify(path)
        require(receipt.get("http_last_modified") and parsedate_to_datetime(receipt["http_last_modified"]).year <= 2023,
                "MODEL16_LODES_RELEASE", "LODES original archive lacks pre-forecast publication evidence")
        seen = set()
        with gzip.open(path, "rt", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            require({"w_geocode", "h_geocode", "S000", "createdate"} <= set(reader.fieldnames or []),
                    "MODEL16_LODES_OD_SCHEMA", "LODES OD schema differs from frozen columns")
            for row in reader:
                workplace = _block(row["w_geocode"], fips)
                home = _block(row["h_geocode"])
                require((home.startswith(fips)) == (kind == "main"), "MODEL16_LODES_MAIN_AUX", "LODES within-state/other-state source semantics changed")
                key = workplace + home
                require(key not in seen, "MODEL16_LODES_DUPLICATE", "LODES block OD pair repeats within source")
                seen.add(key)
                _validate_creation(row["createdate"])
                creation_dates.add(row["createdate"])
                flows[workplace[:11]][home[:11]] += _job_count(row["S000"])
        counts[kind + "_block_pairs"] = len(seen)
    workplace_totals = defaultdict(int)
    path = Path(root) / f"{state}_wac_S000_JT00_2019.csv.gz"
    receipt = verify(path)
    require(receipt.get("http_last_modified") and parsedate_to_datetime(receipt["http_last_modified"]).year <= 2023,
            "MODEL16_LODES_RELEASE", "LODES WAC archive lacks pre-forecast publication evidence")
    seen = set()
    with gzip.open(path, "rt", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        require({"w_geocode", "C000", "createdate"} <= set(reader.fieldnames or []), "MODEL16_LODES_WAC_SCHEMA", "LODES WAC schema differs from frozen columns")
        for row in reader:
            workplace = _block(row["w_geocode"], fips)
            require(workplace not in seen, "MODEL16_LODES_WAC_DUPLICATE", "LODES workplace block repeats")
            seen.add(workplace)
            _validate_creation(row["createdate"])
            creation_dates.add(row["createdate"])
            workplace_totals[workplace[:11]] += _job_count(row["C000"])
    od_totals = {workplace: sum(origins.values()) for workplace, origins in flows.items()}
    require(od_totals == dict(workplace_totals), "MODEL16_LODES_JOB_MARGIN", "complete OD main+aux job totals do not reconcile with WAC per workplace tract")
    counts.update({"wac_blocks": len(seen), "workplace_tracts": len(workplace_totals), "jobs": sum(workplace_totals.values()),
                   "createdates": sorted(creation_dates), "od_wac_margin_exact": True, "reference_year": 2019,
                   "field_allowlist": {"od": ["w_geocode", "h_geocode", "S000", "createdate"], "wac": ["w_geocode", "C000", "createdate"]}})
    return {key: dict(values) for key, values in flows.items()}, counts


def flow_vector(flows, members, points):
    members = set(members)
    jobs, external, known_distance_jobs, distance_sum = 0, 0, 0, 0.0
    for workplace in sorted(members):
        for home, count in sorted(flows.get(workplace, {}).items()):
            jobs += count
            if home not in members:
                external += count
            if workplace in points and home in points:
                known_distance_jobs += count
                x1, y1 = points[workplace]
                x2, y2 = points[home]
                distance_sum += count * math.hypot(x1-x2, y1-y2) / 1000
    coverage = known_distance_jobs/jobs if jobs else None
    return {FLOW_FEATURES[0]: external/jobs if jobs else None,
            FLOW_FEATURES[1]: distance_sum/known_distance_jobs if known_distance_jobs and coverage >= MIN_DISTANCE_JOB_COVERAGE else None}, {
            "distance_job_coverage": coverage, "workplace_tracts_in_support": len(members),
            "zero_workplace_jobs": jobs == 0, "within_tract_distance": "zero tract-point distance; unresolved sub-tract travel"}


class LodesContext:
    def __init__(self, root, spatial_by_state, transformer, verify):
        self.spatial = spatial_by_state
        self.flows, self.source_quality, self.points = {}, {}, {}
        for state, spatial in spatial_by_state.items():
            for record in spatial.records:
                self.points[record["GEOID"]] = transformer.transform(float(record["INTPTLON"]), float(record["INTPTLAT"]))
        for state in ("MI", "WI"):
            release = validate_lodes_archive(root, state.lower(), verify)
            flows, quality = read_lodes_state(root, state.lower(), verify)
            require(set(flows) <= self.points.keys(), "MODEL16_LODES_WORKPLACE_GEOMETRY", "LODES workplace tract geometry is missing")
            self.flows[state] = flows
            self.source_quality[state] = {**quality, **release}

    def vector(self, row):
        state = row["state"]
        spatial = self.spatial[state]
        anchor, ids = spatial.membership(float(row["longitude"]), float(row["latitude"]))
        if anchor is None:
            return dict.fromkeys(FLOW_FEATURES), {"anchor_found": False}
        members = [spatial.records[index]["GEOID"] for index in ids]
        result, quality = flow_vector(self.flows[state], members, self.points)
        return result, {"anchor_found": True, **quality}
