"""Default-deny MODEL-16 XLSX intake and target-blind physical identity.

No file discovery, registration, relocation, or publication occurs here. Callers
resolve exact immutable logical assets through the protected-local catalog first.
Projection rows, workbook metadata, digests, identities, matches, and targets are
protected-local objects. Only explicitly returned aggregate counters are public.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any, Callable, Mapping, Sequence
import unicodedata
from xml.etree import ElementTree
import zipfile

from sprouts_customer_geography.pipe01.errors import ConformanceError
from sprouts_customer_geography.pipe02.xlsx_projection import (
    MAIN_NS, RawCell, _load_shared_strings, _local_name, _parse_reference,
    _parse_stream, _relationship_target,
)


SOURCE_ROLES = {
    "MI_SEED_FORECASTS_2024_2026_V1": ("SEED_POINT", "MI"),
    "WI_SEED_FORECASTS_2024_2026_V1": ("SEED_POINT", "WI"),
    "MI_WI_PURSUED_SITES_2025_ISOLATED_V1": ("PURSUED_SITE", None),
}
EXPECTED_COUNTS = {
    "MI_SEED_FORECASTS_2024_2026_V1": {("MI", 2024): 49, ("MI", 2025): 52, ("MI", 2026): 38},
    "WI_SEED_FORECASTS_2024_2026_V1": {("WI", 2024): 21, ("WI", 2025): 20, ("WI", 2026): 24},
    "MI_WI_PURSUED_SITES_2025_ISOLATED_V1": {("MI", 2025): 17, ("WI", 2025): 19},
}
HEADER_ALIASES = {
    "year": "year", "forecastyear": "year", "forecastvintage": "year",
    "seedpointid": "source_label", "seedpointidentifier": "source_label",
    "address": "address", "streetaddress": "address",
    "city": "city", "city2": "city",
    "state": "state", "stateabbreviation": "state",
    "zip": "postal_code", "zipcode": "postal_code", "postalcode": "postal_code",
    "lat": "latitude", "latitude": "latitude",
    "long": "longitude", "lon": "longitude", "longitude": "longitude",
    "msa": "msa", "msaname": "msa", "metropolitanstatisticalarea": "msa",
    "isolatedsales": "isolated_sales", "impactedsales": "impacted_sales",
    "coordinates": "coordinate_text",
}
SCHEMA_FIELDS = frozenset(HEADER_ALIASES.values())
IDENTITY_FIELDS = frozenset(SCHEMA_FIELDS - {"isolated_sales", "impacted_sales", "coordinate_text"})
NEAR_REVIEW_METRES = 100.0


class IntakeError(ValueError):
    """Safe reason codes only; never include protected cell values or paths."""


def _check(condition: bool, code: str) -> None:
    if not condition:
        raise IntakeError(code)


@dataclass
class AccessAudit:
    header_payload_decodes: int = 0
    identity_payload_decodes: int = 0
    isolated_payload_decodes: int = 0
    impacted_payload_decodes: int = 0
    shared_string_indices_loaded: int = 0
    unrequested_target_payloads_captured: int = 0
    denied_body_payloads_captured: int = 0

    def safe(self) -> dict[str, int]:
        return {key: int(value) for key, value in vars(self).items()}


@dataclass(frozen=True, repr=False)
class WorkbookProjection:
    rows: tuple[dict[str, Any], ...]
    headers: Mapping[str, str]
    columns: Mapping[str, str]
    sheet_name: str
    worksheet_member: str
    workbook_sha256: str
    evidence_class: str
    source_id: str | None
    audit: AccessAudit
    header_row: int = 1


@dataclass(frozen=True, repr=False)
class IdentityResult:
    rows: tuple[dict[str, Any], ...]
    groups: Mapping[str, tuple[str, ...]]
    matches: tuple[dict[str, Any], ...]
    unresolved: tuple[dict[str, Any], ...]
    aggregates: Mapping[str, Any]
    ready: bool


class _SelectiveHandler:
    """Predicate sees only row/column metadata, before any cell text is retained."""

    def __init__(self, allow: Callable[[str, int], bool], *, target_column: str | None = None):
        self.allow = allow
        self.target_column = target_column
        self.rows: dict[int, dict[str, RawCell]] = {}
        self.present_cells: set[tuple[str, int]] = set()
        self.current: dict[str, Any] | None = None
        self.capture = False

    def start(self, name: str, attributes: Mapping[str, str]) -> None:
        local = _local_name(name)
        if local == "c":
            column, row = _parse_reference(attributes.get("r", ""))
            _check((column, row) not in self.present_cells, "MODEL16_DUPLICATE_CELL")
            self.present_cells.add((column, row))
            self.current = {"address": attributes["r"], "column": column, "row": row,
                            "cell_type": attributes.get("t", "n"), "formula": False,
                            "allowed": bool(self.allow(column, row)), "parts": []}
            self.capture = False
        elif self.current is not None and local == "f":
            self.current["formula"] = True
            self.capture = False
        elif self.current is not None and local in {"v", "t"}:
            self.capture = self.current["allowed"]

    def data(self, value: str) -> None:
        if self.current is not None and self.capture:
            self.current["parts"].append(value)

    def end(self, name: str) -> None:
        local = _local_name(name)
        if local in {"v", "t", "f"}:
            self.capture = False
        if local == "c" and self.current is not None:
            c = self.current
            if c["allowed"]:
                self.rows.setdefault(c["row"], {})[c["column"]] = RawCell(
                    c["address"], c["column"], c["row"], c["cell_type"], "".join(c["parts"]),
                    c["formula"], c["column"] == self.target_column and c["row"] > 1)
            self.current, self.capture = None, False


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    except OSError:
        raise IntakeError("MODEL16_WORKBOOK_UNREADABLE") from None
    return digest.hexdigest()


def _open(path: str | Path) -> zipfile.ZipFile:
    try:
        archive = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile):
        raise IntakeError("MODEL16_WORKBOOK_CONTAINER_INVALID") from None
    if len(archive.namelist()) != len(set(archive.namelist())):
        archive.close()
        raise IntakeError("MODEL16_DUPLICATE_ARCHIVE_MEMBER")
    return archive


def _read_sheet(archive: zipfile.ZipFile, member: str, handler: _SelectiveHandler) -> None:
    try:
        with archive.open(member) as stream:
            _parse_stream(stream, handler)
    except (KeyError, OSError, ConformanceError):
        raise IntakeError("MODEL16_WORKSHEET_STRUCTURE_INVALID") from None


def _strings(archive: zipfile.ZipFile, cells: Sequence[RawCell], audit: AccessAudit) -> dict[int, str]:
    requested = set()
    for cell in cells:
        if cell.cell_type == "s":
            _check(bool(cell.payload) and str(cell.payload).isdigit(), "MODEL16_SHARED_STRING_INDEX_INVALID")
            requested.add(int(cell.payload))
    try:
        result = _load_shared_strings(archive, requested)
    except ConformanceError:
        raise IntakeError("MODEL16_SHARED_STRINGS_INVALID") from None
    audit.shared_string_indices_loaded += len(requested)
    return result


def _decode(cell: RawCell, strings: Mapping[int, str], audit: AccessAudit, purpose: str) -> str:
    _check(purpose in {"header", "identity", "isolated"}, "MODEL16_DECODE_PURPOSE_DENIED")
    _check(not cell.formula_present, "MODEL16_PROJECTED_FORMULA_DENIED")
    _check(cell.cell_type in {"n", "s", "str", "inlineStr"}, "MODEL16_PROJECTED_CELL_TYPE_INVALID")
    if purpose == "isolated":
        _check(cell.target_body, "MODEL16_TARGET_PROJECTION_MISMATCH")
        audit.isolated_payload_decodes += 1
    elif purpose == "identity":
        _check(not cell.target_body, "MODEL16_IDENTITY_TARGET_DECODE_DENIED")
        audit.identity_payload_decodes += 1
    else:
        _check(cell.row == 1, "MODEL16_BODY_AS_HEADER_DENIED")
        audit.header_payload_decodes += 1
    return strings[int(cell.payload)] if cell.cell_type == "s" else str(cell.payload or "")


def _normalized_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKC", value).casefold())


def _year(value: str) -> int:
    try:
        number = Decimal(str(value).strip())
    except InvalidOperation:
        raise IntakeError("MODEL16_YEAR_INVALID") from None
    _check(number.is_finite() and number == number.to_integral_value() and int(number) in {2024, 2025, 2026}, "MODEL16_YEAR_INVALID")
    return int(number)


def _coordinate(value: str, *, latitude: bool) -> tuple[float, str]:
    try:
        number = Decimal(value.strip())
    except InvalidOperation:
        raise IntakeError("MODEL16_COORDINATE_INVALID") from None
    limit = 90 if latitude else 180
    _check(number.is_finite() and -limit <= number <= limit, "MODEL16_COORDINATE_INVALID")
    return float(number), format(number.normalize(), "f")


def inspect_workbook(path: str | Path, evidence_class: str, *, source_id: str | None = None) -> WorkbookProjection:
    """Project one exact 12-column workbook without decoding either sales body.

    Source digest is raw-byte integrity evidence; no target cell value is parsed
    or retained. Redundant Coordinates text is denied along with both targets.
    """
    _check(evidence_class in {"SEED_POINT", "PURSUED_SITE"}, "MODEL16_EVIDENCE_CLASS_INVALID")
    if source_id is not None:
        _check(source_id in SOURCE_ROLES and SOURCE_ROLES[source_id][0] == evidence_class, "MODEL16_SOURCE_ROLE_INVALID")
    digest_before = _digest(Path(path))
    audit = AccessAudit()
    with _open(path) as archive:
        try:
            root = ElementTree.fromstring(archive.read("xl/workbook.xml"))
            sheets = root.find(f"{{{MAIN_NS}}}sheets")
            _check(sheets is not None and len(list(sheets)) == 1, "MODEL16_WORKSHEET_COUNT_MISMATCH")
            sheet_name = list(sheets)[0].attrib["name"]
            member = _relationship_target(archive, sheet_name)
        except (KeyError, ElementTree.ParseError, ConformanceError):
            raise IntakeError("MODEL16_WORKBOOK_STRUCTURE_INVALID") from None
        headers_only = _SelectiveHandler(lambda column, row: row == 1)
        _read_sheet(archive, member, headers_only)
        header_cells = headers_only.rows.get(1, {})
        _check(set(header_cells) == set("ABCDEFGHIJKL"), "MODEL16_TWELVE_COLUMN_SCHEMA_REQUIRED")
        shared = _strings(archive, list(header_cells.values()), audit)
        headers, columns = {}, {}
        for column, cell in sorted(header_cells.items()):
            label = _decode(cell, shared, audit, "header").strip()
            canonical = HEADER_ALIASES.get(_normalized_header(label))
            _check(canonical is not None and canonical not in columns, "MODEL16_HEADER_SCHEMA_MISMATCH")
            headers[column], columns[canonical] = label, column
        _check(set(columns) == SCHEMA_FIELDS, "MODEL16_HEADER_SCHEMA_MISMATCH")
        allowed = {columns[field] for field in IDENTITY_FIELDS}
        identities = _SelectiveHandler(lambda column, row: row > 1 and column in allowed)
        _read_sheet(archive, member, identities)
        identity_cells = [cell for row in identities.rows.values() for cell in row.values()]
        shared = _strings(archive, identity_cells, audit)
        rows = []
        body_row_numbers = sorted({row for _, row in identities.present_cells if row > 1})
        for row_number in body_row_numbers:
            cells = identities.rows.get(row_number, {})
            decoded = {field: _decode(cells[columns[field]], shared, audit, "identity").strip() if columns[field] in cells else "" for field in sorted(IDENTITY_FIELDS)}
            if not any(decoded.values()):
                _check((columns["isolated_sales"], row_number) not in identities.present_cells, "MODEL16_TARGET_WITHOUT_IDENTITY")
                continue
            _check(all(decoded[field] for field in ("year", "source_label", "state", "latitude", "longitude", "msa")), "MODEL16_REQUIRED_IDENTITY_FIELD_MISSING")
            _check((columns["isolated_sales"], row_number) in identities.present_cells, "MODEL16_ISOLATED_TARGET_CELL_ABSENT")
            state = {"mi": "MI", "michigan": "MI", "wi": "WI", "wisconsin": "WI"}.get(decoded["state"].casefold())
            _check(state is not None, "MODEL16_STATE_INVALID")
            lat, lat_key = _coordinate(decoded["latitude"], latitude=True)
            lon, lon_key = _coordinate(decoded["longitude"], latitude=False)
            label = decoded["source_label"]
            rows.append({"source_id": source_id, "source_row": row_number, "evidence_class": evidence_class,
                         "year": _year(decoded["year"]), "state": state,
                         "seedpoint_id": label if evidence_class == "SEED_POINT" else None,
                         "source_site_name": label if evidence_class == "PURSUED_SITE" else None,
                         "address": decoded["address"], "city": decoded["city"], "postal_code": decoded["postal_code"],
                         "latitude": lat, "longitude": lon, "coordinate_key": (lat_key, lon_key), "msa": decoded["msa"],
                         "isolated_sales_cell": f"{columns['isolated_sales']}{row_number}"})
    _check(bool(rows), "MODEL16_SOURCE_EMPTY")
    _check(_digest(Path(path)) == digest_before, "MODEL16_SOURCE_CHANGED_DURING_PROJECTION")
    return WorkbookProjection(tuple(rows), headers, columns, sheet_name, member, digest_before, evidence_class, source_id, audit)


def validate_sources(sources: Mapping[str, WorkbookProjection]) -> dict[str, Any]:
    """Validate exact bounded source shape before any target-conditioned work."""
    _check(set(sources) == set(SOURCE_ROLES), "MODEL16_SOURCE_SET_MISMATCH")
    report = []
    for source_id in SOURCE_ROLES:
        projection = sources[source_id]
        role, state = SOURCE_ROLES[source_id]
        _check(projection.source_id in {None, source_id} and projection.evidence_class == role, "MODEL16_SOURCE_ROLE_INVALID")
        _check(all(row["evidence_class"] == role and (state is None or row["state"] == state) for row in projection.rows), "MODEL16_SOURCE_STATE_CLASS_MISMATCH")
        observed = Counter((row["state"], row["year"]) for row in projection.rows)
        _check(dict(observed) == EXPECTED_COUNTS[source_id], "MODEL16_SOURCE_COUNTS_MISMATCH")
        _check(projection.audit.isolated_payload_decodes == projection.audit.impacted_payload_decodes == projection.audit.denied_body_payloads_captured == 0, "MODEL16_IDENTITY_TARGET_BLINDNESS_VIOLATION")
        report.append({"evidence_class": role, "observations": len(projection.rows),
                       "by_state_year": [{"state": state_key, "year": year, "observations": count} for (state_key, year), count in sorted(observed.items())]})
    return {"bounded_source_set_validated": True, "workbooks": len(sources), "observations": sum(len(p.rows) for p in sources.values()), "sources": report,
            "isolated_values_read": 0, "impacted_values_read": 0}


def load_targets(path: str | Path, projection: WorkbookProjection, *, source_rows: set[int], role: str,
                 holdout_freeze_id: str | None = None) -> tuple[dict[int, float], AccessAudit]:
    """Read exactly authorized Isolated Sales cells, after row/role checks.

    The caller owns durable one-open locking and validates a real persisted
    freeze before supplying its opaque ID. This function never grants access.
    """
    _check(role in {"development", "temporal_2026", "pursued_sites"}, "MODEL16_TARGET_ROLE_INVALID")
    _check(isinstance(source_rows, set) and source_rows and all(isinstance(row, int) and not isinstance(row, bool) for row in source_rows), "MODEL16_EXACT_TARGET_ROW_MASK_REQUIRED")
    by_row = {int(row["source_row"]): row for row in projection.rows}
    _check(source_rows <= set(by_row), "MODEL16_TARGET_ROW_OUTSIDE_PROJECTION")
    selected = [by_row[row] for row in sorted(source_rows)]
    if role == "development":
        _check(all(row["evidence_class"] == "SEED_POINT" and row["year"] in {2024, 2025} for row in selected), "MODEL16_HOLDOUT_ROW_IN_DEVELOPMENT")
    else:
        _check(isinstance(holdout_freeze_id, str) and bool(holdout_freeze_id.strip()), "MODEL16_HOLDOUT_FREEZE_REQUIRED")
        if role == "temporal_2026":
            _check(all(row["evidence_class"] == "SEED_POINT" and row["year"] == 2026 for row in selected), "MODEL16_TEMPORAL_TARGET_ROLE_MISMATCH")
        else:
            _check(all(row["evidence_class"] == "PURSUED_SITE" and row["year"] == 2025 for row in selected), "MODEL16_PURSUED_TARGET_ROLE_MISMATCH")
    _check(_digest(Path(path)) == projection.workbook_sha256, "MODEL16_SOURCE_CHANGED_SINCE_PROJECTION")
    audit = AccessAudit()
    column = projection.columns["isolated_sales"]
    _check(column != projection.columns["impacted_sales"], "MODEL16_TARGET_COLUMNS_COLLIDE")
    handler = _SelectiveHandler(lambda col, row: col == column and row in source_rows, target_column=column)
    with _open(path) as archive:
        _read_sheet(archive, projection.worksheet_member, handler)
        _check(set(handler.rows) == source_rows and all(set(cells) == {column} for cells in handler.rows.values()), "MODEL16_TARGET_MASK_INCOMPLETE")
        cells = [handler.rows[row][column] for row in sorted(source_rows)]
        strings = _strings(archive, cells, audit)
        values = {}
        for cell in cells:
            raw = _decode(cell, strings, audit, "isolated")
            try:
                value = float(raw)
            except (ValueError, OverflowError):
                raise IntakeError("MODEL16_ISOLATED_TARGET_INVALID") from None
            _check(math.isfinite(value) and value > 0, "MODEL16_ISOLATED_TARGET_INVALID")
            values[cell.row] = value
    _check(_digest(Path(path)) == projection.workbook_sha256, "MODEL16_SOURCE_CHANGED_DURING_TARGET_READ")
    _check(audit.isolated_payload_decodes == len(source_rows) and audit.impacted_payload_decodes == audit.unrequested_target_payloads_captured == audit.denied_body_payloads_captured == 0, "MODEL16_TARGET_ACCESS_AUDIT_MISMATCH")
    return values, audit


def _key(kind: str, values: Any) -> str:
    return "MODEL16_" + kind + "_" + hashlib.sha256(json.dumps(values, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()[:24]


def _normalize_identity(value: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", unicodedata.normalize("NFKC", value).casefold()).split())


def _normalize_address(value: str) -> str:
    tokens = _normalize_identity(value).split()
    aliases = {"street": "st", "road": "rd", "avenue": "ave", "boulevard": "blvd", "drive": "dr", "lane": "ln",
               "highway": "hwy", "parkway": "pkwy", "north": "n", "south": "s", "east": "e", "west": "w"}
    return " ".join(aliases.get(token, token) for token in tokens)


def _distance_metres(left: Mapping[str, Any], right: Mapping[str, Any]) -> float:
    lat1, lat2 = math.radians(left["latitude"]), math.radians(right["latitude"])
    dlat, dlon = lat2 - lat1, math.radians(right["longitude"] - left["longitude"])
    central = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371008.8 * 2 * math.asin(min(1.0, math.sqrt(central)))


def reconcile_identity(sources: Mapping[str, WorkbookProjection], *, require_expected_shape: bool = True) -> IdentityResult:
    """Preserve yearly observations and evidence class; never use seed proximity.

    Exact coordinates link physical evidence. Same Seed Point ID with changing
    coordinates, conflicting statewide address matches, and cross-source near
    candidates remain unresolved. No distance threshold establishes independence.
    """
    if require_expected_shape:
        validate_sources(sources)
    _check(set(sources) <= set(SOURCE_ROLES) and bool(sources), "MODEL16_SOURCE_SET_MISMATCH")
    rows = []
    for source_id in sorted(sources):
        projection = sources[source_id]
        _check(projection.source_id in {None, source_id}, "MODEL16_SOURCE_ROLE_INVALID")
        for item in projection.rows:
            row = dict(item)
            _check("isolated_sales" not in row and "impacted_sales" not in row, "MODEL16_IDENTITY_TARGET_FIELD_PRESENT")
            row["source_id"] = source_id
            identity = [row["state"], row["seedpoint_id"], row["year"]] if row["evidence_class"] == "SEED_POINT" else [row["state"], row["source_site_name"], row["address"], row["year"], row["source_row"]]
            row["observation_id"] = _key("OBS", [source_id, row["evidence_class"], identity])
            row["physical_location_id"] = _key("LOC", [row["state"], row["coordinate_key"]])
            row["role"] = "pursued_sites" if row["evidence_class"] == "PURSUED_SITE" else ("temporal_2026" if row["year"] == 2026 else "development")
            row["identity_status"] = "RESOLVED"
            rows.append(row)
    seeds = [row for row in rows if row["evidence_class"] == "SEED_POINT"]
    pursued = [row for row in rows if row["evidence_class"] == "PURSUED_SITE"]
    _check(len({row["observation_id"] for row in rows}) == len(rows), "MODEL16_SAME_YEAR_SEED_ID_DUPLICATE")
    seed_year_ids, seed_year_coords, site_coords, site_identities = set(), set(), set(), set()
    for row in seeds:
        identity = row["state"], row["seedpoint_id"], row["year"]
        coordinate = row["state"], tuple(row["coordinate_key"]), row["year"]
        _check(identity not in seed_year_ids, "MODEL16_SAME_YEAR_SEED_ID_DUPLICATE")
        _check(coordinate not in seed_year_coords, "MODEL16_SAME_YEAR_SEED_COORDINATE_DUPLICATE")
        seed_year_ids.add(identity)
        seed_year_coords.add(coordinate)
    for row in pursued:
        _check(row["seedpoint_id"] is None, "MODEL16_PURSUED_SEED_ID_INVENTED")
        coordinate = row["state"], tuple(row["coordinate_key"])
        identity = row["state"], _normalize_identity(row["source_site_name"])
        _check(coordinate not in site_coords, "MODEL16_PURSUED_COORDINATE_DUPLICATE")
        _check(identity not in site_identities, "MODEL16_PURSUED_IDENTITY_DUPLICATE")
        site_coords.add(coordinate)
        site_identities.add(identity)
    unresolved, matches = [], []
    seed_by_id: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in seeds:
        seed_by_id[(row["state"], row["seedpoint_id"])].append(row)
    for members in seed_by_id.values():
        if len({tuple(row["coordinate_key"]) for row in members}) > 1:
            unresolved.append({"reason": "SEED_ID_COORDINATE_CONFLICT", "observations": sorted(row["observation_id"] for row in members)})
    seed_locations: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in seeds:
        seed_locations[row["physical_location_id"]].append(row)
    for site in pursued:
        exact = seed_locations.get(site["physical_location_id"], [])
        if exact:
            matches.append({"pursued_observation": site["observation_id"], "seed_observations": sorted(row["observation_id"] for row in exact),
                            "physical_location_id": site["physical_location_id"], "evidence": "EXACT_SOURCE_COORDINATES", "matched_development": any(row["year"] in {2024, 2025} for row in exact)})
        site_address = _normalize_address(site["address"])
        site_name = _normalize_identity(site["source_site_name"])
        for group, members in sorted(seed_locations.items()):
            seed = members[0]
            if seed["state"] != site["state"] or group == site["physical_location_id"]:
                continue
            evidence = []
            if site_address and any(_normalize_address(row["address"]) == site_address for row in members):
                evidence.append("NORMALIZED_ADDRESS_MATCH_WITH_COORDINATE_CONFLICT")
            if site_name and any(_normalize_identity(row["seedpoint_id"]) == site_name for row in members):
                evidence.append("NORMALIZED_SOURCE_LABEL_MATCH_WITH_COORDINATE_CONFLICT")
            if _distance_metres(site, seed) <= NEAR_REVIEW_METRES:
                evidence.append("NEAR_COORDINATE_REVIEW_ONLY")
            if evidence:
                unresolved.append({"reason": "CROSS_SOURCE_PHYSICAL_IDENTITY_UNRESOLVED", "evidence": evidence,
                                   "observations": [site["observation_id"], *sorted(row["observation_id"] for row in members)]})
        site["matched_seedpoint_location"] = bool(exact)
        site["matched_development_location"] = any(row["year"] in {2024, 2025} for row in exact)
        site["independence_status"] = "MATCHED_SEEDPOINT" if exact else "NO_MATCH_IN_FROZEN_IDENTITY_EVIDENCE"
    unresolved_ids = {identity for finding in unresolved for identity in finding["observations"]}
    for row in rows:
        if row["observation_id"] in unresolved_ids:
            row["identity_status"] = "UNRESOLVED"
            if row["evidence_class"] == "PURSUED_SITE":
                row["independence_status"] = "UNRESOLVED"
    groups: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        groups[row["physical_location_id"]].append(row["observation_id"])
    counts: dict[tuple[str, int, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        counts[(row["state"], row["year"], row["evidence_class"], row["role"])].append(row)
    aggregates = {"observations": len(rows), "physical_locations": len(groups), "unresolved_findings": len(unresolved), "unresolved_observations": len(unresolved_ids),
                  "matched_pursued_observations": len(matches), "matched_development_pursued_observations": sum(match["matched_development"] for match in matches),
                  "by_state_year_role": [{"state": state, "year": year, "evidence_class": evidence_class, "role": role, "observations": len(members), "physical_locations": len({r['physical_location_id'] for r in members})} for (state, year, evidence_class, role), members in sorted(counts.items())],
                  "isolated_values_read": 0, "impacted_values_read": 0}
    return IdentityResult(tuple(rows), {group: tuple(sorted(members)) for group, members in sorted(groups.items())}, tuple(matches), tuple(unresolved), aggregates, not unresolved)
