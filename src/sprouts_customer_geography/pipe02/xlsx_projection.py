"""Streaming XLSX structure projection with sealed target payloads skipped."""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from xml.parsers import expat
from xml.etree import ElementTree

from sprouts_customer_geography.pipe01.errors import ConformanceError, require
from sprouts_customer_geography.pipe02.resolver import (
    CURRENT_2026_TEMPORAL_SOURCE,
    PRIOR_VINTAGE_TEMPORAL_SOURCE,
    REQUIRED_TARGET_SOURCE_ROLES,
)


CELL_REFERENCE = re.compile(r"^([A-Z]{1,3})([1-9][0-9]*)$")
YEAR = re.compile(r"(?<![0-9])((?:19|20)[0-9]{2})(?![0-9])")
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


def _local_name(name: str) -> str:
    return name.rsplit(":", 1)[-1]


def _normalized_column(value: str) -> str:
    column = str(value).strip().upper()
    require(bool(re.fullmatch(r"[A-Z]{1,3}", column)), "TARGET_COLUMN_INVALID", "projection columns must be exact Excel column letters")
    return column


def _parse_reference(value: str) -> tuple[str, int]:
    matched = CELL_REFERENCE.fullmatch(value)
    require(matched is not None, "XLSX_CELL_REFERENCE_INVALID", "worksheet contains an invalid cell reference")
    assert matched is not None
    return matched.group(1), int(matched.group(2))


@dataclass(frozen=True)
class RawCell:
    address: str
    column: str
    row: int
    cell_type: str
    payload: str | None
    formula_present: bool
    target_body: bool


@dataclass
class TargetAccessAudit:
    permitted_payload_decode_calls: int = 0
    target_payload_decode_calls: int = 0
    target_cells_addressed: int = 0
    ignored_cell_payloads: int = 0

    def disclosure_safe(self) -> dict[str, int | bool]:
        return {
            "permitted_payload_decode_calls": self.permitted_payload_decode_calls,
            "target_payload_decode_calls": self.target_payload_decode_calls,
            "target_cells_addressed": self.target_cells_addressed,
            "target_values_materialized": self.target_payload_decode_calls != 0,
        }


class _WorksheetHandler:
    """Collect only the three explicitly allowed columns.

    Character data is never appended while a body cell in the target column is
    active.  Consequently the target payload is not returned by the XML layer,
    retained by this handler, logged, hashed individually, or decoded.
    """

    def __init__(
        self,
        header_row: int,
        allowed_columns: set[str],
        target_column: str,
        audit: TargetAccessAudit,
        *,
        target_rows: set[int] | None = None,
    ):
        self.header_row = header_row
        self.allowed_columns = allowed_columns
        self.target_column = target_column
        self.audit = audit
        self.target_rows = target_rows or set()
        self.rows: dict[int, dict[str, RawCell]] = {}
        self._cell: dict[str, Any] | None = None
        self._capture_text = False

    def start(self, name: str, attributes: Mapping[str, str]) -> None:
        local = _local_name(name)
        if local == "c":
            address = attributes.get("r", "")
            column, row = _parse_reference(address)
            target_body = column == self.target_column and row != self.header_row
            relevant = column in self.allowed_columns and (not target_body or row in self.target_rows)
            self._cell = {
                "address": address,
                "column": column,
                "row": row,
                "cell_type": attributes.get("t", "n"),
                "payload_parts": [],
                "formula_present": False,
                "relevant": relevant,
                "target_body": target_body,
            }
            self._capture_text = False
        elif self._cell is not None and local == "f":
            self._cell["formula_present"] = True
            self._capture_text = False
        elif self._cell is not None and local in {"v", "t"}:
            self._capture_text = bool(self._cell["relevant"] and not self._cell["target_body"])

    def data(self, value: str) -> None:
        if self._cell is not None and self._capture_text:
            self._cell["payload_parts"].append(value)

    def end(self, name: str) -> None:
        local = _local_name(name)
        if local in {"v", "t", "f"}:
            self._capture_text = False
        if local != "c" or self._cell is None:
            return
        cell = self._cell
        if cell["relevant"]:
            if cell["target_body"]:
                require(cell["cell_type"] not in {"s", "inlineStr", "str"}, "TARGET_CELL_STORAGE_UNSAFE", "target body strings cannot be safely addressed without shared-payload risk")
                payload = None
                self.audit.target_cells_addressed += 1
            else:
                payload = "".join(cell["payload_parts"])
            row_cells = self.rows.setdefault(cell["row"], {})
            require(cell["column"] not in row_cells, "XLSX_DUPLICATE_CELL_REJECTED", "worksheet contains a duplicate permitted cell reference")
            row_cells[cell["column"]] = RawCell(
                cell["address"],
                cell["column"],
                cell["row"],
                cell["cell_type"],
                payload,
                bool(cell["formula_present"]),
                bool(cell["target_body"]),
            )
        else:
            self.audit.ignored_cell_payloads += 1
        self._cell = None
        self._capture_text = False


def _parse_stream(stream: Any, handler: _WorksheetHandler) -> None:
    parser = expat.ParserCreate(namespace_separator=":")
    parser.StartElementHandler = handler.start
    parser.EndElementHandler = handler.end
    parser.CharacterDataHandler = handler.data
    try:
        while True:
            block = stream.read(64 * 1024)
            if not block:
                break
            parser.Parse(block, False)
        parser.Parse(b"", True)
    except (expat.ExpatError, OSError) as exc:
        raise ConformanceError("XLSX_WORKSHEET_XML_INVALID", "authorized target worksheet structure is unreadable") from exc


def _relationship_target(archive: zipfile.ZipFile, sheet_name: str) -> str:
    try:
        workbook_root = ElementTree.fromstring(archive.read("xl/workbook.xml"))
        relationship_root = ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    except (KeyError, ElementTree.ParseError) as exc:
        raise ConformanceError("XLSX_STRUCTURE_INVALID", "workbook or relationship metadata is absent or invalid") from exc
    sheets = workbook_root.find(f"{{{MAIN_NS}}}sheets")
    require(sheets is not None, "XLSX_STRUCTURE_INVALID", "workbook sheet inventory is absent")
    matches = [sheet for sheet in sheets if sheet.attrib.get("name") == sheet_name]
    require(len(matches) == 1, "TARGET_SHEET_AUTHORITY_MISMATCH", "the exact authorized target sheet does not resolve uniquely")
    relationship_id = matches[0].attrib.get(f"{{{REL_NS}}}id")
    require(bool(relationship_id), "XLSX_STRUCTURE_INVALID", "authorized sheet relationship is absent")
    targets = [item.attrib.get("Target") for item in relationship_root.findall(f"{{{PACKAGE_REL_NS}}}Relationship") if item.attrib.get("Id") == relationship_id]
    require(len(targets) == 1 and isinstance(targets[0], str), "XLSX_STRUCTURE_INVALID", "authorized sheet relationship does not resolve uniquely")
    target = str(targets[0]).replace("\\", "/")
    if target.startswith("/"):
        member = target.lstrip("/")
    elif target.startswith("xl/"):
        member = target
    else:
        member = f"xl/{target}"
    parts = [part for part in member.split("/") if part not in {"", "."}]
    require(".." not in parts and parts[:1] == ["xl"], "XLSX_RELATIONSHIP_CONTAINMENT_FAILED", "worksheet relationship escapes the XLSX workbook container")
    return "/".join(parts)


def _load_shared_strings(archive: zipfile.ZipFile, requested: set[int]) -> dict[int, str]:
    if not requested:
        return {}
    try:
        stream = archive.open("xl/sharedStrings.xml")
    except KeyError as exc:
        raise ConformanceError("XLSX_SHARED_STRINGS_MISSING", "permitted cells reference an absent shared-string table") from exc
    values: dict[int, list[str]] = {}
    current_index = -1
    in_text = False

    parser = expat.ParserCreate(namespace_separator=":")

    def start(name: str, attributes: Mapping[str, str]) -> None:
        nonlocal current_index, in_text
        local = _local_name(name)
        if local == "si":
            current_index += 1
        elif local == "t":
            in_text = current_index in requested

    def data(value: str) -> None:
        if in_text:
            values.setdefault(current_index, []).append(value)

    def end(name: str) -> None:
        nonlocal in_text
        if _local_name(name) == "t":
            in_text = False

    parser.StartElementHandler = start
    parser.CharacterDataHandler = data
    parser.EndElementHandler = end
    try:
        with stream:
            while True:
                block = stream.read(64 * 1024)
                if not block:
                    break
                parser.Parse(block, False)
            parser.Parse(b"", True)
    except (OSError, expat.ExpatError) as exc:
        raise ConformanceError("XLSX_SHARED_STRINGS_INVALID", "shared-string structure is unreadable") from exc
    require(requested <= set(values), "XLSX_SHARED_STRING_INDEX_INVALID", "permitted cell shared-string index is unresolved")
    return {index: "".join(parts) for index, parts in values.items()}


def _decode_cell_payload(cell: RawCell, shared_strings: Mapping[int, str], audit: TargetAccessAudit) -> str:
    if cell.target_body:
        audit.target_payload_decode_calls += 1
        raise ConformanceError("TARGET_VALUE_DECODE_REJECTED", "target body payload decoding is prohibited during PIPE-02")
    audit.permitted_payload_decode_calls += 1
    require(not cell.formula_present, "PERMITTED_STRUCTURAL_FORMULA_REJECTED", "lineage, vintage, and header evidence must be stored as values rather than formulas")
    payload = cell.payload or ""
    if cell.cell_type == "s":
        require(payload.isdigit(), "XLSX_SHARED_STRING_INDEX_INVALID", "permitted shared-string cell contains an invalid index")
        return shared_strings.get(int(payload), "")
    require(cell.cell_type in {"n", "inlineStr", "str", "b"}, "XLSX_CELL_TYPE_UNSUPPORTED", "permitted structural cell type is unsupported")
    return payload


def _vintage_year(value: str) -> int:
    matches = YEAR.findall(str(value).strip())
    require(len(matches) == 1, "FORECAST_VINTAGE_INVALID", "permitted forecast-vintage cell must resolve to exactly one year")
    return int(matches[0])


class MinimumTargetProjectionPolicy:
    """Default-deny policy for the MODEL-07 temporal target address projection."""

    PROJECTION_ID = "MODEL07_MINIMUM_TEMPORAL_TARGET_PROJECTION_V1"
    VERSION = "1.0.0"
    ALLOWED_FIELDS = frozenset({"lineage_key", "forecast_vintage", "isolated_sales_address"})

    def __init__(self, authority: Mapping[str, Any], workbook_handle: str, source_role: str):
        require(source_role in REQUIRED_TARGET_SOURCE_ROLES, "TARGET_SOURCE_ROLE_UNKNOWN", "target projection has an unknown source role")
        require(authority.get("source_role") == source_role, "TARGET_SOURCE_ROLE_MISMATCH", "target projection authority is bound to another source role")
        require(authority.get("projection_id") == self.PROJECTION_ID and authority.get("version") == self.VERSION, "TARGET_PROJECTION_IDENTITY_MISMATCH", "minimum target projection identity/version mismatch")
        require(authority.get("workbook_handle") == workbook_handle, "TARGET_SOURCE_HANDLE_MISMATCH", "projection references another target-source handle")
        require(authority.get("default_deny") is True, "TARGET_PROJECTION_NOT_DEFAULT_DENY", "target projection must be default-deny")
        require(authority.get("allowed_market") == "milwaukee" and authority.get("allowed_role") == "TEMPORAL_VALIDATION", "TARGET_COHORT_POLICY_MISMATCH", "projection cohort must be Milwaukee TEMPORAL_VALIDATION only")
        if source_role == PRIOR_VINTAGE_TEMPORAL_SOURCE:
            require(authority.get("permitted_pair_role") == "most_recent_eligible_prior", "TARGET_PAIR_ROLE_POLICY_MISMATCH", "prior-vintage source must permit only the frozen prior pair role")
            require(authority.get("vintage_rule") == "MOST_RECENT_ELIGIBLE_PRIOR_TO_2026", "TARGET_VINTAGE_POLICY_MISMATCH", "prior-vintage source must use the accepted prior-vintage rule")
            require("target_year" not in authority, "TARGET_YEAR_POLICY_MISMATCH", "prior-vintage source cannot claim the 2026 target-year authority")
        else:
            require(authority.get("permitted_pair_role") == "corresponding_2026", "TARGET_PAIR_ROLE_POLICY_MISMATCH", "2026 source must permit only the corresponding-2026 pair role")
            require(authority.get("target_year") == 2026, "TARGET_YEAR_POLICY_MISMATCH", "2026 source projection target year must be 2026")
            require("vintage_rule" not in authority, "TARGET_VINTAGE_POLICY_MISMATCH", "2026 source cannot claim the prior-vintage rule")
        sheet_name = authority.get("sheet_name")
        require(isinstance(sheet_name, str) and bool(sheet_name), "TARGET_SHEET_AUTHORITY_UNRESOLVED", "exact target sheet authority is missing")
        header_row = authority.get("header_row")
        require(isinstance(header_row, int) and header_row >= 1, "TARGET_HEADER_ROW_INVALID", "exact target header row is missing")
        columns = authority.get("columns")
        headers = authority.get("headers")
        require(isinstance(columns, Mapping) and set(columns) == {"lineage_key", "forecast_vintage", "isolated_sales"}, "TARGET_COLUMN_AUTHORITY_INVALID", "exact minimum projection columns are required")
        require(isinstance(headers, Mapping) and set(headers) == set(columns), "TARGET_HEADER_AUTHORITY_INVALID", "exact minimum projection headers are required")
        self.workbook_handle = workbook_handle
        self.source_role = source_role
        self.permitted_pair_role = str(authority["permitted_pair_role"])
        self.sheet_name = sheet_name
        self.header_row = header_row
        self.columns = {key: _normalized_column(str(value)) for key, value in columns.items()}
        require(len(set(self.columns.values())) == 3, "TARGET_COLUMN_AUTHORITY_INVALID", "minimum projection columns must be distinct")
        self.headers = {key: str(value) for key, value in headers.items()}
        require(all(bool(value) for value in self.headers.values()), "TARGET_HEADER_AUTHORITY_INVALID", "minimum projection header values must be nonempty")
        require(authority.get("model04_lineage_field") == "source_seed_point_id", "TARGET_LINEAGE_POLICY_MISMATCH", "target join must use the frozen MODEL-04 source seed-point lineage")
        self.target_year = 2026 if source_role == CURRENT_2026_TEMPORAL_SOURCE else None

    def authorize(self, *, field: str, market: str, role: str, quarantined: bool, row_allowed: bool) -> None:
        require(field in self.ALLOWED_FIELDS, "TARGET_FIELD_DENIED", "requested field is not in the minimum projection allowlist")
        require(market == "milwaukee", "TARGET_MARKET_DENIED", "only Milwaukee temporal target addressing is authorized")
        require(role == "TEMPORAL_VALIDATION", "TARGET_ROLE_DENIED", "only TEMPORAL_VALIDATION target addressing is authorized")
        require(not quarantined, "TARGET_QUARANTINE_DENIED", "ambiguous/quarantined target addressing is prohibited")
        require(row_allowed, "TARGET_ROW_DENIED", "row is not in the frozen MODEL-04 temporal allowlist")


def project_target_addresses(
    workbook_path: Path,
    policy: MinimumTargetProjectionPolicy,
    requested_pairs: Sequence[Mapping[str, Any]],
    *,
    decoder: Callable[[RawCell, Mapping[int, str], TargetAccessAudit], str] = _decode_cell_payload,
) -> tuple[list[dict[str, Any]], TargetAccessAudit]:
    """Resolve authorized target addresses without returning target payloads."""
    audit = TargetAccessAudit()
    requested: dict[tuple[str, int], Mapping[str, Any]] = {}
    for item in requested_pairs:
        require(item.get("source_role") == policy.source_role, "TARGET_SOURCE_ROLE_MISMATCH", "requested target pair is routed to another source role")
        require(item.get("pair_role") == policy.permitted_pair_role, "TARGET_PAIR_ROLE_POLICY_MISMATCH", "requested target pair role is not permitted by this source")
        key = (str(item["lineage_key"]), int(item["vintage_year"]))
        if policy.source_role == PRIOR_VINTAGE_TEMPORAL_SOURCE:
            require(key[1] < 2026, "TARGET_VINTAGE_POLICY_MISMATCH", "prior-vintage target evidence must precede 2026")
        else:
            require(key[1] == 2026, "TARGET_YEAR_POLICY_MISMATCH", "2026 target evidence must use vintage year 2026")
        require(key not in requested, "TARGET_LINEAGE_PAIR_DUPLICATE", "frozen MODEL-04 target join pair is duplicate")
        requested[key] = item
    require(bool(requested), "TEMPORAL_COHORT_EMPTY", "no permitted temporal target rows were supplied")

    try:
        archive = zipfile.ZipFile(workbook_path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise ConformanceError("TARGET_WORKBOOK_FORMAT_UNSUPPORTED", "authorized target source is not a readable XLSX container") from exc
    with archive:
        worksheet_member = _relationship_target(archive, policy.sheet_name)
        # First pass reads only permitted headers plus lineage/vintage evidence.
        # It deliberately does not retain any body target address, because the
        # MODEL-04 allowlist has not yet been matched to worksheet rows.
        handler = _WorksheetHandler(
            policy.header_row,
            set(policy.columns.values()),
            policy.columns["isolated_sales"],
            audit,
            target_rows=set(),
        )
        try:
            with archive.open(worksheet_member) as stream:
                _parse_stream(stream, handler)
        except KeyError as exc:
            raise ConformanceError("TARGET_SHEET_CONTENT_UNRESOLVED", "authorized target worksheet content is absent") from exc

        relevant_cells = [cell for cells in handler.rows.values() for cell in cells.values() if not cell.target_body]
        shared_indexes = {
            int(cell.payload or "")
            for cell in relevant_cells
            if cell.cell_type == "s" and (cell.payload or "").isdigit()
        }
        shared_strings = _load_shared_strings(archive, shared_indexes)

        header_cells = handler.rows.get(policy.header_row, {})
        for semantic, column in policy.columns.items():
            cell = header_cells.get(column)
            require(cell is not None, "TARGET_HEADER_UNRESOLVED", "authorized projection header cell is absent")
            actual = decoder(cell, shared_strings, audit)
            require(actual == policy.headers[semantic], "TARGET_HEADER_MISMATCH", "authorized projection header differs from its accepted schema identity")

        resolved_rows: dict[tuple[str, int], int] = {}
        for row_number, cells in sorted(handler.rows.items()):
            if row_number == policy.header_row:
                continue
            lineage_cell = cells.get(policy.columns["lineage_key"])
            vintage_cell = cells.get(policy.columns["forecast_vintage"])
            if lineage_cell is None or vintage_cell is None:
                continue
            lineage = decoder(lineage_cell, shared_strings, audit)
            vintage = _vintage_year(decoder(vintage_cell, shared_strings, audit))
            key = (lineage, vintage)
            if key not in requested:
                continue
            require(key not in resolved_rows, "TARGET_LINEAGE_PAIR_AMBIGUOUS", "authorized target join pair resolves to multiple rows")
            resolved_rows[key] = row_number

        missing = sorted(key for key in requested if key not in resolved_rows)
        require(not missing, "TARGET_LINEAGE_PAIR_UNRESOLVED", "one or more frozen MODEL-04 target join pairs did not resolve")

        # Second pass retains addresses only for rows already authorized by the
        # frozen MODEL-04 join. All unrelated target-column cells remain ignored.
        target_handler = _WorksheetHandler(
            policy.header_row,
            {policy.columns["isolated_sales"]},
            policy.columns["isolated_sales"],
            audit,
            target_rows=set(resolved_rows.values()),
        )
        try:
            with archive.open(worksheet_member) as stream:
                _parse_stream(stream, target_handler)
        except KeyError as exc:
            raise ConformanceError("TARGET_SHEET_CONTENT_UNRESOLVED", "authorized target worksheet content is absent") from exc
        resolved: dict[tuple[str, int], str] = {}
        for key, row_number in resolved_rows.items():
            target_cell = target_handler.rows.get(row_number, {}).get(policy.columns["isolated_sales"])
            require(target_cell is not None and target_cell.target_body, "TARGET_CELL_ADDRESS_UNRESOLVED", "authorized Isolated Sales cell address is absent")
            # The decoder is deliberately not called for target_cell.
            resolved[key] = target_cell.address

    missing = sorted(key for key in requested if key not in resolved)
    require(not missing, "TARGET_LINEAGE_PAIR_UNRESOLVED", "one or more frozen MODEL-04 target join pairs did not resolve")
    require(audit.target_payload_decode_calls == 0, "TARGET_VALUE_ACCESS_DETECTED", "target payload decoding occurred during PIPE-02")
    output = [
        {
            "source_role": policy.source_role,
            "pair_role": str(item["pair_role"]),
            "physical_location_id": str(item["physical_location_id"]),
            "lineage_key": str(item["lineage_key"]),
            "vintage_year": int(item["vintage_year"]),
            "isolated_sales_cell_address": resolved[(str(item["lineage_key"]), int(item["vintage_year"]))],
        }
        for item in requested_pairs
    ]
    return output, audit
