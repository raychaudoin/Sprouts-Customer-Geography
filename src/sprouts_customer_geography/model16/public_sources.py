"""Disclosure-safe complete source manifest and fail-closed cache verification.

Only official public source bytes are opened here. No protected input or target is
required. Server modification dates are evidence, not claims of archived capture.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlparse

from sprouts_customer_geography.pipe01.errors import require
from .public_data import PUBLIC_HOSTS, canonical, digest_file, source_jobs


MANIFEST_PATH = "config/model16/PUBLIC_SOURCE_MANIFEST.json"
ACS_FORECASTS = {2021: [2024], 2022: [2024, 2025, 2026], 2023: [2025, 2026]}
SUPPLEMENTAL_DATA = {
    "EPA_SLD2021_ORIGINAL_PACKAGE", "USDA_FARA2019_CSV",
    "TIGER2019_MI_TRACT", "TIGER2019_WI_TRACT",
    *{f"CBP{year}_COUNTY" for year in (2021, 2022, 2023)},
    *{f"BPS{year}_COUNTY" for year in (2021, 2022, 2023)},
    *{f"LODES7_2019_{state}_{kind}" for state in ("MI", "WI") for kind in ("OD_MAIN", "OD_AUX", "WAC")},
}


def before_forecast(receipt, forecasts):
    """A raw distribution timestamp must precede every assigned forecast year."""
    stamp = receipt.get("http_last_modified")
    require(bool(stamp), "MODEL16_SOURCE_AVAILABILITY_MISSING", "raw source requires dated availability evidence")
    try:
        value = parsedate_to_datetime(stamp)
    except (ValueError, TypeError) as exc:
        raise ValueError("MODEL16_SOURCE_AVAILABILITY_INVALID") from exc
    require(value.tzinfo is not None and all(value < datetime(year, 1, 1, tzinfo=timezone.utc) for year in forecasts),
            "MODEL16_SOURCE_AFTER_HISTORICAL_CUTOFF", "retrieved source revision postdates an assigned historical cutoff")


def classify(source_id, receipt=None):
    """Definitions are target-blind and independent of source values/outcomes."""
    result = {"analytical_role": "RESEARCH_DOCUMENTATION_ONLY", "admitted_forecast_years": [],
              "reason": "Research or source QA evidence; no direct scoring input.",
              "terms_and_attribution": "Publisher-specific documentation; no raw-data analytical reuse is asserted for discovery alone.",
              "schema": "Official documentation or discovery response, retained by SHA-256.",
              "geography_vintage": "not applicable to documentation", "data_vintage": "documentation at retrieval"}
    match = re.fullmatch(r"ACS(202[1-4])_(B\d+)(_SCHEMA)?", source_id)
    if match:
        year, table, metadata = int(match[1]), match[2], bool(match[3])
        result.update(data_vintage=f"{year-4}-{year} ACS five-year estimates", geography_vintage=f"ACS {year} published tract identifiers; analytical polygons fixed TIGER2023",
                      schema=f"ACS detailed table {table}; {'API group variables/labels/estimate+MOE definitions' if metadata else 'table-based summary file, pipe-delimited GEO_ID and E/M columns'}",
                      terms_and_attribution="US Census Bureau public statistical data; attribution to ACS five-year detailed tables. No credentials, individual records or protected-class scoring inputs.",
                      extraction="National complete public table; local filter GEO_ID prefixes 1400000US26 and 1400000US55; allowlisted economic/household fields only.")
        if year == 2024:
            result.update(analytical_role="REJECTED_PRIMARY_TEMPORAL_REVISION", reason="ACS2024 retrieved data files carry January 29, 2026 server modification dates, after the 2026 pre-year cutoff; corresponding metadata is not used either.")
        else:
            forecasts = ACS_FORECASTS[year]
            if receipt is not None and not metadata:
                before_forecast(receipt, forecasts)
            result.update(analytical_role="ADMITTED_SCHEMA" if metadata else "ADMITTED_CORE_DATA", admitted_forecast_years=forecasts,
                          reason="2024 uses ACS2022; 2025 and 2026 both use ACS2023. ACS2021/2022 supply preceding-vintage growth. No 2026 ACS vintage gain.",
                          availability_evidence="Year-specific official table package and its recorded pre-cutoff Last-Modified; API schema is current metadata for that exact year and is never a target-year observation." if not metadata else "Current year-specific metadata validates field meaning only; observations come from separately dated raw tables.")
        return result
    match = re.fullmatch(r"TIGER(202[3-5])_(26|55)", source_id)
    if match:
        year = int(match[1])
        result.update(data_vintage=year, geography_vintage=f"TIGER/Line {year} tract polygons and published internal points",
                      schema="Zipped Census shapefile, NAD83, GEOID/INTPTLAT/INTPTLON/ALAND; state-wide MI/WI selections",
                      terms_and_attribution="US Census Bureau TIGER/Line public geographic data; Census attribution.")
        if year == 2023:
            if receipt is not None:
                before_forecast(receipt, [2024, 2025, 2026])
            result.update(analytical_role="ADMITTED_CORE_GEOMETRY", admitted_forecast_years=[2024, 2025, 2026],
                          reason="Fixed comparable geometry for all cohorts; recorded November 2023 distribution date precedes all forecast cutoffs.",
                          availability_evidence="Official TIGER2023 files, Last-Modified November 23, 2023.")
        else:
            result.update(analytical_role="REJECTED_PRIMARY_GEOMETRY", reason="TIGER2024 retrieved revisions are June 27, 2025, after the 2025 cutoff. TIGER2025 is timely only for 2026, but excluded to retain the single pre-development geometry contract across all cohorts.")
        return result
    if source_id in SUPPLEMENTAL_DATA:
        result.update(analytical_role="ADMITTED_SUPPLEMENTAL_DATA", admitted_forecast_years=[2024, 2025, 2026],
                      reason="Historical source and selected-field semantics verified in PUBLIC_SOURCE_RESEARCH.md and supplemental_public_source_quality.json before targets.",
                      terms_and_attribution="US government publicly distributed statistical/geographic product; retain agency and upstream attribution. No paid raw data acquired.")
        if source_id.startswith("EPA_"):
            result.update(data_vintage="SLD v3 original 2021: LEHD2017, HERE2018, GTFS/network2020", geography_vintage="Original 2019 block groups (2010-era identifiers), original polygons authoritative",
                          schema="Original FileGDB version3, explicit EPA_FIELDS projection; no SLC composites or protected-characteristic fields",
                          terms_and_attribution="EPA publicly supplied indicators. Road/access quantities have third-party HERE/TravelTime lineage; no raw licensed network or service is acquired or redistributed.",
                          availability_evidence="Original ZIP Last-Modified June8,2021 and archive member timestamps no later than2021; original public indicators, not current-service backdating.")
        elif source_id.startswith("USDA_"):
            result.update(data_vintage="2019 food access, 2010 resident denominators", geography_vintage="2010 Census tracts, spatially joined to containing historical polygon",
                          schema="Original FARA2019 CSV inside datedZIP; CensusTract,Pop2010,OHU2010,lapophalf,lahunvhalf only",
                          availability_evidence="Official April2021 original readme and April21,2021 ZIP members; current product URL renamed LRAM. HTTP modification date absent, never invented.")
        elif source_id.startswith("TIGER2019"):
            result.update(data_vintage=2019, geography_vintage="TIGER2019 2010-era tracts", schema="Historical tract shapefile and published internal points for FARA/LODES spatial joins",
                          availability_evidence="Official ZIP Last-Modified August9,2019.")
        elif source_id.startswith("CBP"):
            year = int(source_id[3:7])
            result.update(admitted_forecast_years=[year+3], data_vintage=year, geography_vintage=f"CBP{year} county identifiers", schema="County CSV: fipstate,fipscty,naics,est only; suppression-sensitive employment/payroll unused",
                          availability_evidence="Exact official ZIP Last-Modified, verified before assigned forecast year; CBP2021/22/23 map to forecast2024/25/26.")
        elif source_id.startswith("BPS"):
            year = int(source_id[3:7])
            result.update(admitted_forecast_years=[year+3], data_vintage=year, geography_vintage=f"BPS{year} county identifiers; MI Balance of State000 excluded",
                          schema="Official30-column annual county file, total permitted units and direct reporting units; estimated totals not mistaken for direct reporting",
                          availability_evidence="Exact official current-byte Last-Modified checked preforecast. Three-year lag preserves2022revision dated2024 for2025forecast.")
        elif source_id.startswith("LODES"):
            result.update(data_vintage="2019 employment, release20211018_1647, format7.5", geography_vintage="2010-era Census workplace/home blocks aggregated to historical tracts",
                          schema="LODES7 OD JT00 main+aux S000, WAC S000JT00 C000; geocodes/totaljobs/createdate only",
                          availability_evidence="Archived LODES7 state version20211018_1647, file createdate20211018, dated2021official SHA256 manifests; verify uncompressed CSV checksums and OD/WAC margins.")
        if receipt is not None and source_id != "USDA_FARA2019_CSV":
            before_forecast(receipt, result["admitted_forecast_years"])
        result["transformation_lineage"] = "public_context.py, lodes_context.py, bps_context.py explicit feature catalog; no target-dependent transforms upstream of nested folds."
    elif source_id.startswith("EPA_SLD2021_") and source_id != "EPA_SLD2021_GUIDE":
        result.update(analytical_role="CURRENT_SERVICE_QA_ONLY", reason="Original2021 FileGDB is authoritative; live service has fewer groups. Compared common selected values, never used to backdate geography or drop original groups.")
    return result


def build_manifest(repository, cache):
    repo, cache = Path(repository), Path(cache)
    jobs = source_jobs(repo, cache)
    acquisition = json.loads((cache / "acquisition.json").read_text())
    by_id = {row["source_id"]: row for row in acquisition}
    require(len(by_id) == len(acquisition) and len({j[0] for j in jobs}) == len(jobs), "MODEL16_PUBLIC_SOURCE_DUPLICATE", "source identifiers must be unique")
    require(set(by_id) == {j[0] for j in jobs}, "MODEL16_PUBLIC_SOURCE_INVENTORY_DRIFT", "acquisition must cover the exact bounded inventory")
    records = []
    for source_id, url, path in jobs:
        observed = by_id[source_id]
        row = {"source_id": source_id, "url": url, "cache_path": path.relative_to(cache).as_posix(), **classify(source_id)}
        if observed.get("status") == "ACQUISITION_FAILED":
            require(not path.exists(), "MODEL16_PUBLIC_FAILED_SOURCE_HAS_BYTES", "failed discovery must not silently supply input bytes")
            row.update(acquisition_status="ACQUISITION_FAILED", analytical_role="NOT_ADMITTED_ACQUISITION_FAILED", http_code=observed.get("http_code"), error_type=observed.get("error_type"),
                       reason="Recorded endpoint failure; no data acquired or analytical efficacy conclusion. See bounded research alternatives/limitations.")
        else:
            receipt = json.loads(path.with_name(path.name + ".receipt.json").read_text())
            require(receipt.get("url") == url and receipt == {key: value for key, value in observed.items() if key != "source_id"}, "MODEL16_PUBLIC_SOURCE_RECEIPT_DRIFT", "acquisition and cache receipt must agree exactly")
            require(urlparse(receipt["resolved_url"]).scheme == "https" and urlparse(receipt["resolved_url"]).hostname in PUBLIC_HOSTS,
                    "MODEL16_PUBLIC_REDIRECT_DENIED", "resolved source must retain approved public host")
            require(path.stat().st_size == receipt["byte_length"] and digest_file(path) == receipt["sha256"], "MODEL16_PUBLIC_BYTES_CHANGED", "public source bytes differ from their receipt")
            row.update(classify(source_id, receipt))
            row.update(acquisition_status="RETRIEVED_HASH_VERIFIED", receipt=receipt)
        records.append(row)
    return {"artifact_id": "MODEL16_COMPLETE_PUBLIC_SOURCE_MANIFEST_V1", "schema_version": 1,
            "scope": "Every bounded acquisition record; public-only provenance, not protected values or an outcome report.",
            "source_count": len(records), "counts_by_acquisition_status": dict(sorted(Counter(r["acquisition_status"] for r in records).items())),
            "counts_by_analytical_role": dict(sorted(Counter(r["analytical_role"] for r in records).items())),
            "cutoff": "Exact retrieved data revision must have source evidence predating January1 of each assigned forecast year. A reference-year label alone is insufficient. Current metadata validates schema, not historical observed values.",
            "reconstruction": "Run public_data acquisition into ignoredcache, then public_sources --cache to reproduce this manifest; verify_manifest rehashes every retrieved file and compares the complete saved definition.",
            "refresh": "No refresh after feature freeze. New source bytes require a new authorized generation; failures do not become zero features.",
            "limitations": "HTTP Last-Modified and original release/archive member evidence are publisher attestations, not proof of a historical archived capture. No historical snapshot is claimed where only current documentation was fetched.",
            "supplemental_record": "config/model16/source_research.json", "research": "docs/model16/PUBLIC_SOURCE_RESEARCH.md",
            "source_records": sorted(records, key=lambda row: row["source_id"])}


def verify_manifest(repository, cache):
    repo = Path(repository)
    expected = json.loads((repo / MANIFEST_PATH).read_text())
    actual = build_manifest(repo, cache)
    require(actual == expected, "MODEL16_PUBLIC_MANIFEST_DRIFT", "current public sources differ from the saved admission manifest")
    return actual


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--cache", type=Path, required=True)
    args = parser.parse_args()
    manifest = build_manifest(args.repository, args.cache)
    (args.repository / MANIFEST_PATH).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"stage": "PUBLIC_SOURCE_MANIFEST", "sources": manifest["source_count"], "counts": manifest["counts_by_acquisition_status"]}))


if __name__ == "__main__":
    main()
