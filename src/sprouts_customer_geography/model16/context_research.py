"""Target-blind public context discovery jobs.

Discovery is not admission: only the separately frozen catalog may admit features.
All requests are national/state-independent documentation or public source bytes;
no protected location, identifier, or target is included in a request.
"""
from pathlib import Path
from urllib.parse import urlencode
import hashlib
import json


EPA_FIELDS = (
    "OBJECTID", "GEOID10", "GEOID20", "STATEFP", "HH", "Workers", "TotEmp",
    "E5_Ret", "E5_Off", "E5_Ind", "E5_Svc", "E5_Ent", "Ac_Unpr",
    "D3A", "D3AAO", "D3B", "D4A", "D4D", "D5AR", "D5BR",
)


CONTEXT_PUBLIC_HOSTS = {
    "www.epa.gov", "geodata.epa.gov", "edg.epa.gov", "lehd.ces.census.gov",
    "www.ers.usda.gov", "www2.census.gov", "www.census.gov",
    "www.fhwa.dot.gov", "www.michigan.gov", "wisconsindot.gov",
    "www.mrlc.gov", "eogdata.mines.edu", "docs.overturemaps.org",
    "wiki.openstreetmap.org",
}


def context_jobs(cache: Path) -> list[tuple[str, str, Path]]:
    """Return the initial bounded discovery set; cache hash receipts bind bytes."""
    root = Path(cache) / "context"
    entries = [
        ("EPA_SLD_DOCUMENTATION", "https://www.epa.gov/smartgrowth/smart-location-mapping", "epa-sld.html"),
        ("EPA_SLD_SERVICE", "https://geodata.epa.gov/arcgis/rest/services/OA/SmartLocationDatabase/MapServer?f=pjson", "epa-sld-service.json"),
        ("LODES_DATA_DOCUMENTATION", "https://lehd.ces.census.gov/data/", "lodes-data.html"),
        ("LODES8_VERSION", "https://lehd.ces.census.gov/data/lodes/LODES8/version.txt", "lodes8-version.txt"),
        ("USDA_FARA_DOWNLOAD_DOCUMENTATION", "https://www.ers.usda.gov/data-products/food-access-research-atlas/download-the-data", "usda-fara-download.html"),
        ("CBP2021_COUNTY", "https://www2.census.gov/programs-surveys/cbp/datasets/2021/cbp21co.zip", "cbp21co.zip"),
        ("CBP2022_COUNTY", "https://www2.census.gov/programs-surveys/cbp/datasets/2022/cbp22co.zip", "cbp22co.zip"),
        ("CBP2023_COUNTY", "https://www2.census.gov/programs-surveys/cbp/datasets/2023/cbp23co.zip", "cbp23co.zip"),
        ("CBP2023_DIRECTORY", "https://www2.census.gov/programs-surveys/cbp/datasets/2023/", "cbp2023-directory.html"),
        ("CBP_RELEASE_DOCUMENTATION", "https://www.census.gov/programs-surveys/cbp/news.html", "cbp-news.html"),
        ("FHWA_TRAFFIC_DOCUMENTATION", "https://www.fhwa.dot.gov/policyinformation/tables/tmasdata/", "fhwa-tmas.html"),
        ("MI_DOT_TRAFFIC_DOCUMENTATION", "https://www.michigan.gov/mdot/travel/traffic-data", "mi-dot-traffic.html"),
        ("WI_DOT_TRAFFIC_DOCUMENTATION", "https://wisconsindot.gov/Pages/projects/data-plan/traf-counts/default.aspx", "wi-dot-traffic.html"),
        ("NLCD_DOCUMENTATION", "https://www.mrlc.gov/data", "nlcd-data.html"),
        ("VIIRS_DOCUMENTATION", "https://eogdata.mines.edu/products/vnl/", "viirs-vnl.html"),
        ("BPS_DOCUMENTATION", "https://www.census.gov/construction/bps/index.html", "bps.html"),
        ("OVERTURE_RELEASE_DOCUMENTATION", "https://docs.overturemaps.org/release/latest/", "overture-releases.html"),
        ("EPA_SLD_LAYER_SCHEMA", "https://geodata.epa.gov/arcgis/rest/services/OA/SmartLocationDatabase/MapServer/1?f=pjson", "epa-sld-layer.json"),
        ("EPA_SLD2021_GUIDE", "https://www.epa.gov/system/files/documents/2023-10/epa_sld_3.0_technicaldocumentationuserguide_may2021_0.pdf", "epa-sld2021-guide.pdf"),
        ("EPA_SLD2021_ORIGINAL_PACKAGE", "https://edg.epa.gov/EPADataCommons/public/OA/SLD/SmartLocationDatabaseV3.zip", "epa-sld-v3-original.zip"),
        ("USDA_FARA2019_CSV", "https://www.ers.usda.gov/media/5627/2019-large-retailer-access-map-lram-formerly-known-as-the-food-access-research-atlas-fara-data.zip?v=23010", "fara2019.zip"),
        ("USDA_FARA_HISTORY", "https://www.ers.usda.gov/data-products/food-access-research-atlas/update-and-revision-history", "usda-fara-history.html"),
        ("USDA_FARA_DEFINITIONS", "https://www.ers.usda.gov/data-products/food-access-research-atlas/documentation", "usda-fara-definitions.html"),
        ("LODES_ARCHIVE", "https://lehd.ces.census.gov/data/lodes/", "lodes-archive.html"),
        ("CBP2021_DIRECTORY", "https://www2.census.gov/programs-surveys/cbp/datasets/2021/", "cbp2021-directory.html"),
        ("CBP2022_DIRECTORY", "https://www2.census.gov/programs-surveys/cbp/datasets/2022/", "cbp2022-directory.html"),
        ("BPS_ANNUAL_DOCUMENTATION", "https://www.census.gov/construction/bps/annual.html", "bps-annual.html"),
        ("OSM_HISTORY_DOCUMENTATION", "https://wiki.openstreetmap.org/wiki/Planet.osm/full", "osm-history.html"),
        ("OVERTURE_DOWNLOAD_DOCUMENTATION", "https://docs.overturemaps.org/getting-data/", "overture-download.html"),
        ("VIIRS_V22_DOWNLOAD_DOCUMENTATION", "https://eogdata.mines.edu/nighttime_light/annual/v22/", "viirs-v22-directory.html"),
        ("TIGER2019_MI_TRACT", "https://www2.census.gov/geo/tiger/TIGER2019/TRACT/tl_2019_26_tract.zip", "tl_2019_26_tract.zip"),
        ("TIGER2019_WI_TRACT", "https://www2.census.gov/geo/tiger/TIGER2019/TRACT/tl_2019_55_tract.zip", "tl_2019_55_tract.zip"),
        ("LODES7_ARCHIVE", "https://lehd.ces.census.gov/data/lodes/LODES7/", "lodes7-archive.html"),
        ("LODES8_ARCHIVE", "https://lehd.ces.census.gov/data/lodes/LODES8/", "lodes8-archive.html"),
        ("LODES7_GUIDE", "https://lehd.ces.census.gov/data/lodes/LODES7/LODESTechDoc7.5.pdf", "lodes7-guide.pdf"),
        ("BPS_HISTORICAL_DOCUMENTATION", "https://www.census.gov/construction/bps/historical.html", "bps-historical.html"),
        ("BPS_COUNTY_DIRECTORY", "https://www2.census.gov/econ/bps/County/", "bps-county-directory.html"),
        ("BPS2021_COUNTY", "https://www2.census.gov/econ/bps/County/co2021a.txt", "bps-co2021a.txt"),
        ("BPS2022_COUNTY", "https://www2.census.gov/econ/bps/County/co2022a.txt", "bps-co2022a.txt"),
        ("BPS2023_COUNTY", "https://www2.census.gov/econ/bps/County/co2023a.txt", "bps-co2023a.txt"),
        ("BPS2022_REVISION_NOTICE", "https://www2.census.gov/econ/bps/County/co2022aupdatednotice.txt", "bps2022-revision-notice.txt"),
    ]
    for state in ("mi", "wi"):
        base = f"https://lehd.ces.census.gov/data/lodes/LODES7/{state}"
        entries.append((f"LODES7_{state.upper()}_OD_DIRECTORY", base + "/od/", f"lodes7-{state}-od-directory.html"))
        entries.append((f"LODES7_{state.upper()}_VERSION", base + "/version.txt", f"lodes7-{state}-version.txt"))
        entries.append((f"LODES7_{state.upper()}_CHECKSUMS", base + f"/lodes_{state}.sha256sum", f"lodes7-{state}-checksums.txt"))
        for kind in ("main", "aux"):
            filename = f"{state}_od_{kind}_JT00_2019.csv.gz"
            entries.append((f"LODES7_2019_{state.upper()}_OD_{kind.upper()}", base + "/od/" + filename, filename))
        filename = f"{state}_wac_S000_JT00_2019.csv.gz"
        entries.append((f"LODES7_2019_{state.upper()}_WAC", base + "/wac/" + filename, filename))
    service = "https://geodata.epa.gov/arcgis/rest/services/OA/SmartLocationDatabase/MapServer/1/query?"
    for state in ("26", "55"):
        entries.append((f"EPA_SLD2021_{state}_IDS", service + urlencode({"where": f"STATEFP='{state}'", "returnIdsOnly": "true", "f": "json"}), f"epa-sld2021-{state}-ids.json"))
        # Two deterministic 5,000-row pages cover these states; ID reconciliation
        # fails closed if source coverage ever grows beyond this bounded request.
        for offset in (0, 5000):
            query = {"where": f"STATEFP='{state}'", "outFields": ",".join(EPA_FIELDS),
                     "returnGeometry": "true", "outSR": "4326", "orderByFields": "OBJECTID",
                     "resultOffset": str(offset), "resultRecordCount": "5000", "f": "geojson"}
            entries.append((f"EPA_SLD2021_{state}_{offset}", service + urlencode(query), f"epa-sld2021-{state}-{offset}.geojson"))
    return [(name, url, root / filename) for name, url, filename in entries]


def research_record(cache: Path) -> dict:
    """Create a disclosure-safe record from this bounded public job inventory."""
    cache = Path(cache)
    acquisition = json.loads((cache / "acquisition.json").read_text())
    by_id = {row["source_id"]: row for row in acquisition}
    records = []
    for source_id, url, path in context_jobs(cache):
        record = {"source_id": source_id, "requested_url": url}
        receipt_path = path.with_name(path.name + ".receipt.json")
        if path.is_file() and receipt_path.is_file():
            receipt = json.loads(receipt_path.read_text())
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            if receipt.get("url") != url or receipt.get("sha256") != digest.hexdigest():
                raise ValueError("MODEL16_PUBLIC_RESEARCH_RECEIPT_MISMATCH")
            record.update({"status": "RETRIEVED_HASH_VERIFIED", "receipt": receipt})
        else:
            prior = by_id.get(source_id, {})
            record.update({"status": prior.get("status", "NOT_RETRIEVED"), "http_code": prior.get("http_code"), "error_type": prior.get("error_type")})
        records.append(record)
    return {"artifact_id": "MODEL16_PUBLIC_SUPPLEMENTAL_SOURCE_RESEARCH_V1", "schema_version": 1,
            "scope": "target-blind public source discovery only; retrieval does not imply analytical admission",
            "jobs": len(records), "retrieved": sum(row["status"] == "RETRIEVED_HASH_VERIFIED" for row in records),
            "source_records": records,
            "analytical_product_ids": ["EPA_SLD2021_ORIGINAL_PACKAGE", "CBP2021_COUNTY", "CBP2022_COUNTY", "CBP2023_COUNTY", "USDA_FARA2019_CSV", "TIGER2019_MI_TRACT", "TIGER2019_WI_TRACT",
                *[f"LODES7_2019_{state}_{kind}" for state in ("MI", "WI") for kind in ("OD_MAIN", "OD_AUX", "WAC")],
                "BPS2021_COUNTY", "BPS2022_COUNTY", "BPS2023_COUNTY"],
            "service_qa_only": "EPA_SLD2021 state service queries; original 2021 FileGDB is authoritative",
            "definitions": "src/sprouts_customer_geography/model16/public_context.py:feature_catalog",
            "research_and_nonadmission_reasons": "docs/model16/PUBLIC_SOURCE_RESEARCH.md",
            "protected_target_access_by_research": False}
