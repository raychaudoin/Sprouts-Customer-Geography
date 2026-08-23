"""Exact successor-row XLSX projection for PIPE-04 Isolated Sales access."""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping, Sequence

from sprouts_customer_geography.pipe01.errors import ConformanceError, require
from sprouts_customer_geography.pipe02.xlsx_projection import (
    RawCell,
    _load_shared_strings,
    _local_name,
    _parse_reference,
    _parse_stream,
    _relationship_target,
)


@dataclass
class TargetAccessAudit:
    structural_payload_decode_calls: int = 0
    authorized_isolated_sales_decode_calls: int = 0
    impacted_sales_decode_calls: int = 0
    non_wisconsin_target_decode_calls: int = 0
    unrelated_cells_ignored: int = 0

    def disclosure_safe(self) -> dict[str, int | bool]:
        return {
            "authorized_row_count": self.authorized_isolated_sales_decode_calls,
            "isolated_sales_materialized": self.authorized_isolated_sales_decode_calls > 0,
            "impacted_sales_decode_calls": self.impacted_sales_decode_calls,
            "non_wisconsin_target_decode_calls": self.non_wisconsin_target_decode_calls,
            "unrelated_target_values_materialized": False,
        }


class Model10WisconsinProjectionPolicy:
    """Default-deny projection for exact MODEL-10 successor source rows."""

    PROJECTION_ID = "MODEL09_MINIMUM_MODEL10_WISCONSIN_DEVELOPMENT_TARGET_PROJECTION_V1"
    VERSION = "1.0.0"
    ALLOWED_FIELDS = frozenset({"source_observation_lineage", "forecast_vintage", "isolated_sales"})

    def __init__(self, authority: Mapping[str, Any], workbook_handle: str, source_workbook_identity: str):
        require(authority.get("projection_id") == self.PROJECTION_ID and authority.get("version") == self.VERSION, "TARGET_PROJECTION_IDENTITY_MISMATCH", "target projection identity/version mismatch")
        require(authority.get("workbook_handle") == workbook_handle and authority.get("source_workbook_identity") == source_workbook_identity, "TARGET_SOURCE_HANDLE_MISMATCH", "projection references another source")
        require(authority.get("default_deny") is True and authority.get("allowed_state") == "wisconsin", "TARGET_PROJECTION_NOT_DEFAULT_DENY", "projection must be default-deny Wisconsin-only")
        require(authority.get("permitted_target_field") == "Isolated Sales" and authority.get("denied_target_field") == "Impacted Sales", "TARGET_FIELD_POLICY_MISMATCH", "only Isolated Sales is permitted")
        require(
            authority.get("successor_lineage_field") == "source_seed_point_id"
            and authority.get("forecast_vintage_field") == "forecast_vintage"
            and authority.get("source_row_field") == "source_row"
            and authority.get("historical_model04_equality_required") is False,
            "TARGET_LINEAGE_POLICY_MISMATCH",
            "projection must use successor lineage without MODEL-04 equality",
        )
        sheet = authority.get("sheet_name")
        header_row = authority.get("header_row")
        columns = authority.get("columns")
        headers = authority.get("headers")
        require(isinstance(sheet, str) and sheet, "TARGET_SHEET_AUTHORITY_UNRESOLVED", "target sheet is missing")
        require(isinstance(header_row, int) and header_row >= 1, "TARGET_HEADER_ROW_INVALID", "target header row is invalid")
        require(isinstance(columns, Mapping) and set(columns) == {"lineage_key", "forecast_vintage", "isolated_sales"}, "TARGET_COLUMN_AUTHORITY_INVALID", "exact minimum columns are required")
        require(isinstance(headers, Mapping) and set(headers) == set(columns), "TARGET_HEADER_AUTHORITY_INVALID", "exact minimum headers are required")
        normalized = {key: str(value).strip().upper() for key, value in columns.items()}
        require(all(re.fullmatch(r"[A-Z]{1,3}", value) for value in normalized.values()) and len(set(normalized.values())) == 3, "TARGET_COLUMN_AUTHORITY_INVALID", "columns must be distinct Excel letters")
        self.workbook_handle = workbook_handle
        self.source_workbook_identity = source_workbook_identity
        self.sheet_name = sheet
        self.header_row = header_row
        self.columns = normalized
        self.headers = {key: str(value) for key, value in headers.items()}
        require(self.headers["isolated_sales"] == "Isolated Sales" and "Impacted Sales" not in self.headers.values(), "TARGET_HEADER_AUTHORITY_INVALID", "header allowlist must exclude Impacted Sales")


class _RowsHandler:
    def __init__(self, *, header_row: int, authorized_rows: set[int], allowed_columns: set[str], target_column: str, audit: TargetAccessAudit):
        self.header_row = header_row
        self.authorized_rows = authorized_rows
        self.allowed_columns = allowed_columns
        self.target_column = target_column
        self.audit = audit
        self.rows: dict[int, dict[str, RawCell]] = {}
        self._cell: dict[str, Any] | None = None
        self._capture = False

    def start(self, name: str, attributes: Mapping[str, str]) -> None:
        local = _local_name(name)
        if local == "c":
            address = attributes.get("r", "")
            column, row = _parse_reference(address)
            relevant = column in self.allowed_columns and (row == self.header_row or row in self.authorized_rows)
            self._cell = {"address": address, "column": column, "row": row, "cell_type": attributes.get("t", "n"), "payload_parts": [], "formula_present": False, "relevant": relevant, "target_body": column == self.target_column and row != self.header_row}
            self._capture = False
        elif self._cell is not None and local == "f":
            self._cell["formula_present"] = True
            self._capture = False
        elif self._cell is not None and local in {"v", "t"}:
            self._capture = bool(self._cell["relevant"])

    def data(self, value: str) -> None:
        if self._cell is not None and self._capture:
            self._cell["payload_parts"].append(value)

    def end(self, name: str) -> None:
        local = _local_name(name)
        if local in {"v", "t", "f"}:
            self._capture = False
        if local != "c" or self._cell is None:
            return
        cell = self._cell
        if cell["relevant"]:
            row_cells = self.rows.setdefault(cell["row"], {})
            require(cell["column"] not in row_cells, "XLSX_DUPLICATE_CELL_REJECTED", "duplicate permitted cell")
            row_cells[cell["column"]] = RawCell(cell["address"], cell["column"], cell["row"], cell["cell_type"], "".join(cell["payload_parts"]), bool(cell["formula_present"]), bool(cell["target_body"]))
        else:
            self.audit.unrelated_cells_ignored += 1
        self._cell = None


def _structural_value(cell: RawCell, shared_strings: Mapping[int, str], audit: TargetAccessAudit) -> str:
    require(not cell.formula_present, "PERMITTED_STRUCTURAL_FORMULA_REJECTED", "join and vintage evidence must be values")
    audit.structural_payload_decode_calls += 1
    payload = cell.payload or ""
    if cell.cell_type == "s":
        require(payload.isdigit() and int(payload) in shared_strings, "XLSX_SHARED_STRING_INDEX_INVALID", "shared string is unresolved")
        return shared_strings[int(payload)]
    require(cell.cell_type in {"n", "inlineStr", "str", "b"}, "XLSX_CELL_TYPE_UNSUPPORTED", "structural cell type is unsupported")
    return payload


def _decimal_value(cell: RawCell, audit: TargetAccessAudit) -> str:
    require(cell.target_body and cell.cell_type == "n" and not cell.formula_present and bool(cell.payload), "ISOLATED_SALES_CELL_INVALID", "Isolated Sales must be a stored number")
    try:
        value = Decimal(str(cell.payload))
    except InvalidOperation as exc:
        raise ConformanceError("ISOLATED_SALES_VALUE_INVALID", "Isolated Sales is not finite decimal") from exc
    require(value.is_finite(), "ISOLATED_SALES_VALUE_INVALID", "Isolated Sales is not finite decimal")
    audit.authorized_isolated_sales_decode_calls += 1
    if value == 0:
        return "0"
    rendered = format(value.normalize(), "f")
    return rendered.rstrip("0").rstrip(".") if "." in rendered else rendered


def project_authorized_isolated_sales(workbook_path: Path, policy: Model10WisconsinProjectionPolicy, requested_rows: Sequence[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], TargetAccessAudit]:
    """Decode only exact MODEL-10 successor rows and Isolated Sales cells."""
    audit = TargetAccessAudit()
    by_row: dict[int, Mapping[str, Any]] = {}
    observation_ids: set[str] = set()
    for item in requested_rows:
        lineage = item.get("source_observation_lineage")
        require(isinstance(lineage, Mapping), "MODEL10_SOURCE_LINEAGE_INCOMPLETE", "successor lineage is absent")
        require(lineage.get("source_workbook_identity") == policy.source_workbook_identity and lineage.get("source_sheet") == policy.sheet_name, "TARGET_SOURCE_IDENTITY_MISMATCH", "successor row is routed to another source")
        row = lineage.get("source_row")
        observation_id = item.get("source_observation_id")
        require(isinstance(row, int) and row > policy.header_row and row not in by_row, "TARGET_SOURCE_ROW_INVALID", "successor source row is missing reserved or duplicate")
        require(isinstance(observation_id, str) and observation_id.startswith("sobs-") and observation_id not in observation_ids, "MODEL10_SOURCE_OBSERVATION_INVALID", "successor observation is missing or duplicate")
        require(item.get("model09_development_eligible") is True and item.get("quarantined") is False and str(item.get("market", "")).strip(), "TARGET_ROW_DENIED", "only MODEL-10-eligible Wisconsin rows are permitted")
        observation_ids.add(observation_id)
        by_row[row] = item
    require(by_row, "WISCONSIN_COHORT_EMPTY", "no eligible Wisconsin target rows supplied")

    try:
        archive = zipfile.ZipFile(workbook_path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise ConformanceError("TARGET_WORKBOOK_FORMAT_UNSUPPORTED", "target source is not readable XLSX") from exc
    with archive:
        worksheet_member = _relationship_target(archive, policy.sheet_name)
        handler = _RowsHandler(header_row=policy.header_row, authorized_rows=set(by_row), allowed_columns=set(policy.columns.values()), target_column=policy.columns["isolated_sales"], audit=audit)
        try:
            with archive.open(worksheet_member) as stream:
                _parse_stream(stream, handler)
        except KeyError as exc:
            raise ConformanceError("TARGET_SHEET_CONTENT_UNRESOLVED", "target worksheet is absent") from exc
        structural = [cell for cells in handler.rows.values() for cell in cells.values() if not cell.target_body]
        indexes = {int(cell.payload or "") for cell in structural if cell.cell_type == "s" and (cell.payload or "").isdigit()}
        shared = _load_shared_strings(archive, indexes)
        headers = handler.rows.get(policy.header_row, {})
        for semantic, column in policy.columns.items():
            cell = headers.get(column)
            require(cell is not None, "TARGET_HEADER_UNRESOLVED", "target projection header is absent")
            require(_structural_value(cell, shared, audit) == policy.headers[semantic], "TARGET_HEADER_MISMATCH", "target header differs from authority")

        output: list[dict[str, Any]] = []
        for row, item in sorted(by_row.items()):
            cells = handler.rows.get(row, {})
            lineage_cell = cells.get(policy.columns["lineage_key"])
            vintage_cell = cells.get(policy.columns["forecast_vintage"])
            target_cell = cells.get(policy.columns["isolated_sales"])
            require(lineage_cell is not None and vintage_cell is not None and target_cell is not None, "TARGET_ROW_UNRESOLVED", "exact successor target row is incomplete")
            lineage_value = _structural_value(lineage_cell, shared, audit)
            expected_lineage = str(item["source_observation_lineage"]["source_seed_point_id"])
            require(lineage_value == expected_lineage, "TARGET_SUCCESSOR_LINEAGE_UNRESOLVED", "target row differs from MODEL-10 successor lineage")
            vintage_text = _structural_value(vintage_cell, shared, audit)
            years = re.findall(r"(?<![0-9])((?:19|20)[0-9]{2})(?![0-9])", vintage_text)
            require(len(years) == 1 and int(years[0]) == int(item["forecast_vintage"]), "FORECAST_VINTAGE_INVALID", "target row vintage differs from MODEL-10")
            output.append({"source_observation_id": str(item["source_observation_id"]), "forecast_vintage": int(item["forecast_vintage"]), "isolated_sales": _decimal_value(target_cell, audit)})
    require(audit.authorized_isolated_sales_decode_calls == len(requested_rows) and audit.impacted_sales_decode_calls == 0 and audit.non_wisconsin_target_decode_calls == 0, "TARGET_ACCESS_AUDIT_FAILED", "target access exceeded authorized projection")
    return output, audit
