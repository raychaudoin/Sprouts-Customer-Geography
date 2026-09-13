"""Public-only, pinned source acquisition; no protected coordinates in requests."""
from __future__ import annotations

import argparse
import concurrent.futures
import csv
import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from sprouts_customer_geography.pipe01.errors import require
from .context_research import context_jobs, CONTEXT_PUBLIC_HOSTS

STATES = {"MI": "26", "WI": "55"}
VINTAGES = (2022, 2023, 2024)
EXTRA_TABLES = ("B01003", "B17001", "B19001", "B25024", "B25070", "B08303")
PUBLIC_HOSTS = {"www2.census.gov", "api.census.gov", *CONTEXT_PUBLIC_HOSTS}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest_file(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def verify_receipt(path: Path, *, expected_url: str | None = None, latest_allowed_year: int | None = None) -> dict:
    """Require source-bound receipt, exact bytes, and optional historical cutoff."""
    path = Path(path)
    receipt = path.with_name(path.name + ".receipt.json")
    require(path.is_file() and receipt.is_file(), "MODEL16_PUBLIC_RECEIPT_MISSING", "public source bytes and receipt must both exist")
    try:
        info = json.loads(receipt.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise ValueError("MODEL16_PUBLIC_RECEIPT_INVALID") from None
    require(isinstance(info, dict) and isinstance(info.get("url"), str) and isinstance(info.get("sha256"), str)
            and re.fullmatch(r"[a-f0-9]{64}", info["sha256"]) is not None
            and isinstance(info.get("byte_length"), int) and not isinstance(info["byte_length"], bool),
            "MODEL16_PUBLIC_RECEIPT_INVALID", "public acquisition receipt lacks required evidence")
    for url in (info["url"], info.get("resolved_url", info["url"])):
        require(isinstance(url, str) and urlparse(url).scheme == "https" and urlparse(url).hostname in PUBLIC_HOSTS,
                "MODEL16_PUBLIC_HOST_DENIED", "recorded public source is outside the allowlist")
    require(expected_url is None or info["url"] == expected_url, "MODEL16_PUBLIC_SOURCE_MISMATCH", "public source URL differs from the requested source")
    require(path.stat().st_size == info["byte_length"] > 0 and digest_file(path) == info["sha256"],
            "MODEL16_PUBLIC_BYTES_CHANGED", "public source bytes differ from their acquisition receipt")
    if latest_allowed_year is not None:
        try:
            modified = parsedate_to_datetime(info["http_last_modified"])
            require(modified.tzinfo is not None, "MODEL16_PUBLIC_DATE_INVALID", "source revision date lacks a timezone")
        except (KeyError, TypeError, ValueError, OverflowError):
            raise ValueError("MODEL16_PUBLIC_DATE_INVALID") from None
        cutoff = datetime(latest_allowed_year + 1, 1, 1, tzinfo=timezone.utc)
        require(modified < cutoff, "MODEL16_PUBLIC_FUTURE_REVISION", "verified public bytes were revised after the historical cutoff")
    return info


def _recover_receipted_partial(destination: Path, url: str) -> dict | None:
    """Complete the old receipt-before-rename transaction without redownloading."""
    receipt = destination.with_name(destination.name + ".receipt.json")
    if not receipt.exists():
        return None
    try:
        info = json.loads(receipt.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise ValueError("MODEL16_PUBLIC_RECEIPT_INVALID") from None
    require(isinstance(info, dict) and info.get("url") == url and isinstance(info.get("sha256"), str)
            and isinstance(info.get("byte_length"), int) and info["byte_length"] > 0,
            "MODEL16_PUBLIC_RECEIPT_INVALID", "interrupted acquisition receipt cannot be reconciled")
    matches = [partial for partial in sorted(destination.parent.glob(destination.name + ".partial-*"))
               if partial.is_file() and partial.stat().st_size == info["byte_length"] and digest_file(partial) == info["sha256"]]
    require(bool(matches), "MODEL16_PUBLIC_INTERRUPTED_BYTES_UNRESOLVED", "receipted download bytes must be recovered before continuing")
    require(not destination.exists(), "MODEL16_PUBLIC_DESTINATION_ALREADY_EXISTS", "recovery cannot overwrite public cache state")
    os.replace(matches[0], destination)
    return verify_receipt(destination, expected_url=url)


def download(url: str, destination: Path) -> dict:
    """Reuse only hash-verified bytes and preserve interrupted attempt files."""
    require(urlparse(url).scheme == "https" and urlparse(url).hostname in PUBLIC_HOSTS,
            "MODEL16_PUBLIC_HOST_DENIED", "public download is outside the frozen allowlist")
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    receipt = destination.with_name(destination.name + ".receipt.json")
    if destination.exists():
        return verify_receipt(destination, expected_url=url)
    recovered = _recover_receipted_partial(destination, url)
    if recovered is not None:
        return recovered
    last = None
    for attempt in range(3):
        if receipt.exists():
            try:
                return verify_receipt(destination, expected_url=url) if destination.exists() else _recover_receipted_partial(destination, url)
            except OSError as exc:
                last = exc
                continue
        partial = destination.with_name(destination.name + f".partial-{time.time_ns()}")
        try:
            request = Request(url, headers={"User-Agent": "Sprouts-Customer-Geography-MODEL16/1.0 public-data-research"})
            with urlopen(request, timeout=60) as response, partial.open("xb") as output:
                require(urlparse(response.geturl()).scheme == "https" and urlparse(response.geturl()).hostname in PUBLIC_HOSTS,
                        "MODEL16_PUBLIC_REDIRECT_DENIED", "public source redirected outside the allowlist")
                for block in iter(lambda: response.read(1024 * 1024), b""):
                    output.write(block)
                output.flush()
                os.fsync(output.fileno())
                info = {"url": url, "resolved_url": response.geturl(), "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
                        "http_last_modified": response.headers.get("Last-Modified"), "sha256": digest_file(partial),
                        "byte_length": partial.stat().st_size}
            require(info["byte_length"] > 0, "MODEL16_PUBLIC_DOWNLOAD_EMPTY", "public source returned an empty payload")
            with receipt.open("xb") as out:
                out.write(canonical(info) + b"\n")
                out.flush()
                os.fsync(out.fileno())
            return _recover_receipted_partial(destination, url)
        except OSError as exc:
            last = exc
    raise OSError("MODEL16_PUBLIC_DOWNLOAD_FAILED") from last


def source_jobs(repository: Path, cache: Path):
    data03 = json.loads((repository / "config/data/data03_wisconsin_multivariate_acs_feature_source_contract.json").read_text())
    tables = sorted({"B11001", *EXTRA_TABLES, *(t["table_id"] for t in data03["tables"])})
    result = []
    for table in ("B11001", "B01003", "B25002"):
        name = f"acsdt5y2021-{table.lower()}.dat"
        result.append((f"ACS2021_{table}", f"https://www2.census.gov/programs-surveys/acs/summary_file/2021/table-based-SF/data/5YRData/{name}", cache / name))
        result.append((f"ACS2021_{table}_SCHEMA", f"https://api.census.gov/data/2021/acs/acs5/groups/{table}.json", cache / f"acs2021-{table.lower()}.metadata.json"))
    for vintage in VINTAGES:
        for table in tables:
            name = f"acsdt5y{vintage}-{table.lower()}.dat"
            result.append((f"ACS{vintage}_{table}", f"https://www2.census.gov/programs-surveys/acs/summary_file/{vintage}/table-based-SF/data/5YRData/{name}", cache / name))
            result.append((f"ACS{vintage}_{table}_SCHEMA", f"https://api.census.gov/data/{vintage}/acs/acs5/groups/{table}.json", cache / f"acs{vintage}-{table.lower()}.metadata.json"))
    # Each geometry snapshot was publicly available before its forecast year.
    for year in (2023, 2024, 2025):
        for state in STATES.values():
            name = f"tl_{year}_{state}_tract.zip"
            result.append((f"TIGER{year}_{state}", f"https://www2.census.gov/geo/tiger/TIGER{year}/TRACT/{name}", cache / name))
    return result + context_jobs(cache)


def acquire(repository: Path, cache: Path):
    jobs = source_jobs(repository, cache)
    records = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(download, url, path): (name, path) for name, url, path in jobs}
        for future in concurrent.futures.as_completed(futures):
            name, path = futures[future]
            try:
                record = {"source_id": name, **future.result()}
            except Exception as exc:
                if path.parent.name != "context":
                    raise
                record = {"source_id": name, "status": "ACQUISITION_FAILED", "error_type": type(exc).__name__, "http_code": getattr(exc.__cause__, "code", None)}
                records.append(record)
                print(json.dumps(record), flush=True)
                continue
            records.append(record)
            if name.startswith("CONTEXT"):
                print(json.dumps({"public_source": name, "bytes": record["byte_length"], "state": "retrieved_not_admitted"}), flush=True)
    return sorted(records, key=lambda row: row["source_id"])


def read_acs_table(path: Path, table: str) -> dict[str, dict[str, str]]:
    path = Path(path)
    matched = re.fullmatch(r"acsdt5y(20[0-9]{2})-([a-z0-9]+)\.dat", path.name)
    require(matched is not None and matched.group(2) == table.lower(), "MODEL16_ACS_SOURCE_IDENTITY_INVALID", "ACS source filename and requested table differ")
    vintage = int(matched.group(1))
    expected_url = f"https://www2.census.gov/programs-surveys/acs/summary_file/{vintage}/table-based-SF/data/5YRData/{path.name}"
    verify_receipt(path, expected_url=expected_url, latest_allowed_year=vintage + 1)
    result = {}
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, delimiter="|")
        require(reader.fieldnames and len(reader.fieldnames) == len(set(reader.fieldnames)) and "GEO_ID" in reader.fieldnames
                and {f"{table}_E001", f"{table}_M001"} <= set(reader.fieldnames),
                "MODEL16_ACS_SCHEMA_INVALID", "public ACS table schema is missing")
        for row in reader:
            require(None not in row and all(value is not None for value in row.values()), "MODEL16_ACS_ROW_WIDTH_INVALID", "public ACS row width differs from its schema")
            geo = row["GEO_ID"]
            if geo.startswith(("1400000US26", "1400000US55")):
                geoid = geo[9:]
                require(len(geoid) == 11 and geoid.isdigit() and geoid not in result,
                        "MODEL16_ACS_GEOID_INVALID", "public ACS keys do not reconcile")
                result[geoid] = {key: value for key, value in row.items() if key.startswith(table + "_")}
    require(bool(result), "MODEL16_ACS_EMPTY", "public ACS state selection is empty")
    return result


def read_acs_metadata(path: Path, table: str, vintage: int) -> dict:
    """Version-specific schema bytes are verified but never used as predictors."""
    path = Path(path)
    require(path.name == f"acs{vintage}-{table.lower()}.metadata.json", "MODEL16_ACS_METADATA_IDENTITY_INVALID", "ACS schema identity differs")
    verify_receipt(path, expected_url=f"https://api.census.gov/data/{vintage}/acs/acs5/groups/{table}.json")
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise ValueError("MODEL16_ACS_METADATA_INVALID") from None
    require(isinstance(result, dict) and isinstance(result.get("variables"), dict), "MODEL16_ACS_METADATA_INVALID", "ACS variable metadata is absent")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--cache", type=Path, required=True)
    args = parser.parse_args()
    records = acquire(args.repository, args.cache)
    (args.cache / "acquisition.json").write_bytes(canonical(records) + b"\n")


if __name__ == "__main__":
    main()
