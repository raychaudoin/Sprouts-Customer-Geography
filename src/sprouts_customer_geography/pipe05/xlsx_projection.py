"""Minimum exact-row XLSX projection for PIPE-05 Isolated Sales binding."""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping, Sequence

from sprouts_customer_geography.model06 import AUTHORIZED_BODY_MAX_COLUMN, HEADER_ALIASES, _column_number, _normalized_header
from sprouts_customer_geography.pipe01.errors import ConformanceError, require
from sprouts_customer_geography.pipe02.xlsx_projection import RawCell, _load_shared_strings, _local_name, _parse_reference, _parse_stream, _relationship_target


@dataclass
class TargetAccessAudit:
    structural_payload_decode_calls: int = 0
    authorized_isolated_sales_cell_examinations: int = 0
    valid_isolated_sales_decode_calls: int = 0
    missing_isolated_sales_count: int = 0
    invalid_isolated_sales_count: int = 0
    impacted_sales_body_decode_calls: int = 0
    other_outcome_body_decode_calls: int = 0
    quarantined_target_body_decode_calls: int = 0
    non_michigan_target_decode_calls: int = 0
    unrelated_cells_ignored: int = 0

    def disclosure_safe(self, authorized_row_count: int) -> dict[str, int | bool]:
        return {
            "authorized_row_count": authorized_row_count,
            "isolated_sales_cells_examined": self.authorized_isolated_sales_cell_examinations,
            "valid_isolated_sales_binding_count": self.valid_isolated_sales_decode_calls,
            "missing_isolated_sales_count": self.missing_isolated_sales_count,
            "invalid_isolated_sales_count": self.invalid_isolated_sales_count,
            "impacted_sales_body_decode_calls": self.impacted_sales_body_decode_calls,
            "other_outcome_body_decode_calls": self.other_outcome_body_decode_calls,
            "quarantined_target_body_decode_calls": self.quarantined_target_body_decode_calls,
            "non_michigan_target_decode_calls": self.non_michigan_target_decode_calls,
            "broad_preview_performed": False,
            "whole_workbook_hash_computed": False,
        }


class _HeaderHandler:
    """Capture only worksheet header cells; never capture body payloads."""

    def __init__(self, header_row: int):
        self.header_row = header_row
        self.cells: dict[str, RawCell] = {}
        self._cell: dict[str, Any] | None = None
        self._capture = False

    def start(self, name: str, attributes: Mapping[str, str]) -> None:
        local = _local_name(name)
        if local == "c":
            address = attributes.get("r", "")
            column, row = _parse_reference(address)
            self._cell = {"address": address, "column": column, "row": row, "cell_type": attributes.get("t", "n"), "payload_parts": [], "formula_present": False, "relevant": row == self.header_row}
            self._capture = False
        elif self._cell is not None and local == "f":
            if self._cell["relevant"]:
                self._cell["formula_present"] = True
            self._capture = False
        elif self._cell is not None and local in {"v", "t"}:
            self._capture = bool(self._cell["relevant"] and not self._cell["formula_present"])

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
            require(cell["column"] not in self.cells, "XLSX_DUPLICATE_CELL_REJECTED", "duplicate header cell")
            self.cells[cell["column"]] = RawCell(cell["address"], cell["column"], cell["row"], cell["cell_type"], "".join(cell["payload_parts"]), bool(cell["formula_present"]), False)
        self._cell = None


def _decode_structural(cell: RawCell, shared_strings: Mapping[int, str], audit: TargetAccessAudit | None = None) -> str:
    require(not cell.formula_present, "PERMITTED_STRUCTURAL_FORMULA_REJECTED", "join vintage and header evidence must be stored values")
    if audit is not None:
        audit.structural_payload_decode_calls += 1
    payload = cell.payload or ""
    if cell.cell_type == "s":
        require(payload.isdigit() and int(payload) in shared_strings, "XLSX_SHARED_STRING_INDEX_INVALID", "shared string is unresolved")
        return shared_strings[int(payload)]
    require(cell.cell_type in {"n", "inlineStr", "str", "b"}, "XLSX_CELL_TYPE_UNSUPPORTED", "structural cell type is unsupported")
    return payload


def inspect_minimum_projection_authority(
    workbook_path: Path,
    *,
    workbook_handle: str,
    source_authority_id: str,
    header_alias_overrides: Mapping[str, Sequence[str]] | None = None,
) -> dict[str, Any]:
    """Read header cells only and return one protected default-deny projection."""

    try:
        archive = zipfile.ZipFile(workbook_path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise ConformanceError("TARGET_WORKBOOK_FORMAT_UNSUPPORTED", "target source is not readable XLSX") from exc
    with archive:
        member = _relationship_target(archive, "Sheet1")
        handler = _HeaderHandler(1)
        try:
            with archive.open(member) as stream:
                _parse_stream(stream, handler)
        except KeyError as exc:
            raise ConformanceError("TARGET_SHEET_CONTENT_UNRESOLVED", "target worksheet is absent") from exc
        indexes = {int(cell.payload or "") for cell in handler.cells.values() if cell.cell_type == "s" and (cell.payload or "").isdigit()}
        shared = _load_shared_strings(archive, indexes)
        decoded = {column: _decode_structural(cell, shared) for column, cell in handler.cells.items()}

    aliases_by_field = {field: set(aliases) for field, aliases in HEADER_ALIASES.items()}
    for field, aliases in (header_alias_overrides or {}).items():
        require(field in aliases_by_field and isinstance(aliases, Sequence) and not isinstance(aliases, (str, bytes)), "TARGET_HEADER_AUTHORITY_INVALID", "identity header alias override differs")
        aliases_by_field[field].update(_normalized_header(alias) for alias in aliases)

    selected: dict[str, str] = {}
    for field in ("seed_point_id", "vintage"):
        matches = [column for column, value in decoded.items() if _column_number(f"{column}1") <= AUTHORIZED_BODY_MAX_COLUMN and _normalized_header(value) in aliases_by_field[field]]
        require(len(matches) == 1, "TARGET_HEADER_AUTHORITY_INVALID", "minimum join header does not resolve uniquely")
        selected[field] = matches[0]
    isolated = [column for column, value in decoded.items() if _column_number(f"{column}1") > AUTHORIZED_BODY_MAX_COLUMN and _normalized_header(value) == "isolatedsales"]
    impacted = [column for column, value in decoded.items() if _column_number(f"{column}1") > AUTHORIZED_BODY_MAX_COLUMN and _normalized_header(value) == "impactedsales"]
    require(len(isolated) == len(impacted) == 1 and isolated[0] != impacted[0], "TARGET_HEADER_AUTHORITY_INVALID", "permitted and denied target headers must each resolve once outside the identity projection")
    require(len({selected["seed_point_id"], selected["vintage"], isolated[0], impacted[0]}) == 4, "TARGET_COLUMN_AUTHORITY_INVALID", "minimum and denied target columns must be distinct")
    return {
        "projection_id": MichiganIsolatedSalesProjectionPolicy.PROJECTION_ID,
        "version": MichiganIsolatedSalesProjectionPolicy.VERSION,
        "workbook_handle": workbook_handle,
        "source_authority_id": source_authority_id,
        "default_deny": True,
        "allowed_state": "michigan",
        "permitted_target_field": "Isolated Sales",
        "denied_target_field": "Impacted Sales",
        "source_observation_lineage_field": "source_seed_point_id",
        "forecast_vintage_field": "forecast_vintage",
        "source_row_field": "source_projection_row",
        "sheet_name": "Sheet1",
        "worksheet_member": member,
        "header_row": 1,
        "columns": {"lineage_key": selected["seed_point_id"], "forecast_vintage": selected["vintage"], "isolated_sales": isolated[0]},
        "denied_columns": {"impacted_sales": impacted[0]},
        "headers": {"lineage_key": decoded[selected["seed_point_id"]], "forecast_vintage": decoded[selected["vintage"]], "isolated_sales": "Isolated Sales", "impacted_sales": "Impacted Sales"},
        "whole_workbook_hash_permitted": False,
    }


class MichiganIsolatedSalesProjectionPolicy:
    """Default-deny projection for exact eligible MODEL-12 source rows."""

    PROJECTION_ID = "PIPE05_MINIMUM_MODEL12_MICHIGAN_ISOLATED_SALES_PROJECTION_V1"
    VERSION = "1.0.0"
    ALLOWED_FIELDS = frozenset({"source_observation_lineage", "forecast_vintage", "isolated_sales", "target_status"})

    def __init__(self, authority: Mapping[str, Any], workbook_handle: str, source_authority_id: str):
        expected_fields = {"projection_id", "version", "workbook_handle", "source_authority_id", "default_deny", "allowed_state", "permitted_target_field", "denied_target_field", "source_observation_lineage_field", "forecast_vintage_field", "source_row_field", "sheet_name", "worksheet_member", "header_row", "columns", "denied_columns", "headers", "whole_workbook_hash_permitted"}
        require(set(authority) == expected_fields, "TARGET_PROJECTION_AUTHORITY_INVALID", "target projection fields differ from PIPE-05")
        require(authority.get("projection_id") == self.PROJECTION_ID and authority.get("version") == self.VERSION, "TARGET_PROJECTION_IDENTITY_MISMATCH", "target projection identity or version differs")
        require(authority.get("workbook_handle") == workbook_handle and authority.get("source_authority_id") == source_authority_id, "TARGET_SOURCE_HANDLE_MISMATCH", "projection references another source")
        require(authority.get("default_deny") is True and authority.get("allowed_state") == "michigan" and authority.get("whole_workbook_hash_permitted") is False, "TARGET_PROJECTION_NOT_DEFAULT_DENY", "projection must be default-deny Michigan-only without a workbook hash")
        require(authority.get("permitted_target_field") == "Isolated Sales" and authority.get("denied_target_field") == "Impacted Sales", "TARGET_FIELD_POLICY_MISMATCH", "only Isolated Sales is permitted")
        require(authority.get("source_observation_lineage_field") == "source_seed_point_id" and authority.get("forecast_vintage_field") == "forecast_vintage" and authority.get("source_row_field") == "source_projection_row", "TARGET_LINEAGE_POLICY_MISMATCH", "projection must use exact MODEL-12 source-observation lineage")
        require(authority.get("sheet_name") == "Sheet1" and authority.get("header_row") == 1 and isinstance(authority.get("worksheet_member"), str) and bool(authority.get("worksheet_member")), "TARGET_SHEET_AUTHORITY_UNRESOLVED", "target worksheet authority differs")
        columns = authority.get("columns")
        denied = authority.get("denied_columns")
        headers = authority.get("headers")
        require(isinstance(columns, Mapping) and set(columns) == {"lineage_key", "forecast_vintage", "isolated_sales"} and isinstance(denied, Mapping) and set(denied) == {"impacted_sales"}, "TARGET_COLUMN_AUTHORITY_INVALID", "exact minimum and denied columns are required")
        require(isinstance(headers, Mapping) and set(headers) == {"lineage_key", "forecast_vintage", "isolated_sales", "impacted_sales"}, "TARGET_HEADER_AUTHORITY_INVALID", "exact header authority is required")
        normalized = {key: str(value).upper() for key, value in {**columns, **denied}.items()}
        require(all(re.fullmatch(r"[A-Z]{1,3}", value) for value in normalized.values()) and len(set(normalized.values())) == 4, "TARGET_COLUMN_AUTHORITY_INVALID", "columns must be distinct Excel letters")
        require(headers.get("isolated_sales") == "Isolated Sales" and headers.get("impacted_sales") == "Impacted Sales", "TARGET_HEADER_AUTHORITY_INVALID", "permitted or denied target header differs")
        self.workbook_handle = workbook_handle
        self.source_authority_id = source_authority_id
        self.sheet_name = str(authority["sheet_name"])
        self.worksheet_member = str(authority["worksheet_member"])
        self.header_row = 1
        self.columns = {key: str(value).upper() for key, value in columns.items()}
        self.denied_columns = {key: str(value).upper() for key, value in denied.items()}
        self.headers = {key: str(value) for key, value in headers.items()}


class _RowsHandler:
    def __init__(self, *, policy: MichiganIsolatedSalesProjectionPolicy, eligible_rows: set[int], quarantined_rows: set[int], audit: TargetAccessAudit):
        self.policy = policy
        self.eligible_rows = eligible_rows
        self.quarantined_rows = quarantined_rows
        self.expected_rows = eligible_rows | quarantined_rows
        self.audit = audit
        self.rows: dict[int, dict[str, RawCell]] = {}
        self.body_rows_with_join_or_target_references: set[int] = set()
        self._cell: dict[str, Any] | None = None
        self._capture = False

    def start(self, name: str, attributes: Mapping[str, str]) -> None:
        local = _local_name(name)
        if local == "c":
            address = attributes.get("r", "")
            column, row = _parse_reference(address)
            allowed_columns = set(self.policy.columns.values())
            header_columns = allowed_columns | set(self.policy.denied_columns.values())
            if row != self.policy.header_row and column in allowed_columns:
                self.body_rows_with_join_or_target_references.add(row)
            target_body = row != self.policy.header_row and column == self.policy.columns["isolated_sales"]
            relevant = (row == self.policy.header_row and column in header_columns) or (row in self.eligible_rows and column in allowed_columns)
            if row in self.quarantined_rows and target_body:
                relevant = False
            self._cell = {"address": address, "column": column, "row": row, "cell_type": attributes.get("t", "n"), "payload_parts": [], "formula_present": False, "relevant": relevant, "target_body": target_body}
            self._capture = False
        elif self._cell is not None and local == "f":
            if self._cell["relevant"]:
                self._cell["formula_present"] = True
            self._capture = False
        elif self._cell is not None and local in {"v", "t"}:
            self._capture = bool(self._cell["relevant"] and not self._cell["formula_present"])

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


def _target_value(cell: RawCell | None, audit: TargetAccessAudit) -> tuple[str, str | None, str | None]:
    audit.authorized_isolated_sales_cell_examinations += 1
    if cell is None:
        audit.missing_isolated_sales_count += 1
        return "MISSING", None, "SOURCE_CELL_ABSENT"
    if cell.formula_present:
        audit.invalid_isolated_sales_count += 1
        return "INVALID", None, "FORMULA_TARGET_DENIED"
    payload = cell.payload or ""
    if payload.strip() == "":
        audit.missing_isolated_sales_count += 1
        return "MISSING", None, "SOURCE_CELL_BLANK"
    if cell.cell_type != "n":
        audit.invalid_isolated_sales_count += 1
        return "INVALID", None, "NONNUMERIC_STORAGE"
    try:
        value = Decimal(payload)
    except InvalidOperation:
        audit.invalid_isolated_sales_count += 1
        return "INVALID", None, "NONFINITE_OR_NONDECIMAL_VALUE"
    if not value.is_finite():
        audit.invalid_isolated_sales_count += 1
        return "INVALID", None, "NONFINITE_OR_NONDECIMAL_VALUE"
    audit.valid_isolated_sales_decode_calls += 1
    if value == 0:
        return "VALID", "0", None
    rendered = format(value.normalize(), "f")
    return "VALID", rendered.rstrip("0").rstrip(".") if "." in rendered else rendered, None


def project_authorized_isolated_sales(
    workbook_path: Path,
    policy: MichiganIsolatedSalesProjectionPolicy,
    eligible_observations: Sequence[Mapping[str, Any]],
    quarantined_observations: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], TargetAccessAudit]:
    """Decode only exact eligible MODEL-12 rows and permitted target cells."""

    audit = TargetAccessAudit()
    by_row: dict[int, Mapping[str, Any]] = {}
    observation_ids: set[str] = set()
    for item in eligible_observations:
        lineage = item.get("source_observation_lineage")
        require(isinstance(lineage, Mapping) and lineage.get("source_authority_id") == policy.source_authority_id, "MODEL12_SOURCE_LINEAGE_INCOMPLETE", "accepted source lineage is absent or differs")
        row = lineage.get("source_projection_row")
        observation_id = item.get("source_observation_id")
        require(isinstance(row, int) and row > policy.header_row and row not in by_row, "TARGET_SOURCE_ROW_INVALID", "eligible source row is missing reserved or duplicate")
        require(isinstance(observation_id, str) and observation_id.startswith("m12obs-") and observation_id not in observation_ids, "MODEL12_SOURCE_OBSERVATION_INVALID", "accepted source observation is missing or duplicate")
        require(item.get("target_binding_eligible") is True and item.get("quarantined") is False, "TARGET_ROW_DENIED", "only nonquarantined accepted MODEL-12 rows are eligible")
        observation_ids.add(observation_id)
        by_row[row] = item
    quarantine_by_row: dict[int, Mapping[str, Any]] = {}
    for item in quarantined_observations:
        lineage = item.get("source_observation_lineage")
        row = lineage.get("source_projection_row") if isinstance(lineage, Mapping) else None
        require(isinstance(row, int) and row > policy.header_row and row not in by_row and row not in quarantine_by_row and item.get("quarantined") is True and item.get("target_binding_eligible") is False, "QUARANTINE_ACCOUNTING_INVALID", "quarantined source row accounting differs")
        quarantine_by_row[row] = item
    require(by_row, "MICHIGAN_BINDING_COHORT_EMPTY", "no eligible Michigan target rows supplied")

    try:
        archive = zipfile.ZipFile(workbook_path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise ConformanceError("TARGET_WORKBOOK_FORMAT_UNSUPPORTED", "target source is not readable XLSX") from exc
    with archive:
        member = _relationship_target(archive, policy.sheet_name)
        require(member == policy.worksheet_member, "TARGET_SHEET_AUTHORITY_MISMATCH", "target worksheet member differs from protected authority")
        handler = _RowsHandler(policy=policy, eligible_rows=set(by_row), quarantined_rows=set(quarantine_by_row), audit=audit)
        try:
            with archive.open(member) as stream:
                _parse_stream(stream, handler)
        except KeyError as exc:
            raise ConformanceError("TARGET_SHEET_CONTENT_UNRESOLVED", "target worksheet is absent") from exc
        expected_rows = set(by_row) | set(quarantine_by_row)
        require(handler.body_rows_with_join_or_target_references == expected_rows, "TARGET_SOURCE_ROW_ACCOUNTING_MISMATCH", "source contains an unresolved missing or unexpected target row")
        structural = [cell for cells in handler.rows.values() for cell in cells.values() if not cell.target_body]
        indexes = {int(cell.payload or "") for cell in structural if cell.cell_type == "s" and (cell.payload or "").isdigit()}
        shared = _load_shared_strings(archive, indexes)
        headers = handler.rows.get(policy.header_row, {})
        for semantic, column in {**policy.columns, **policy.denied_columns}.items():
            cell = headers.get(column)
            require(cell is not None and _decode_structural(cell, shared, audit) == policy.headers[semantic], "TARGET_HEADER_MISMATCH", "target projection header differs from authority")

        output: list[dict[str, Any]] = []
        for row, item in sorted(by_row.items()):
            cells = handler.rows.get(row, {})
            lineage_cell = cells.get(policy.columns["lineage_key"])
            vintage_cell = cells.get(policy.columns["forecast_vintage"])
            require(lineage_cell is not None and vintage_cell is not None, "TARGET_ROW_UNRESOLVED", "exact MODEL-12 target row lacks join lineage")
            expected_lineage = str(item["source_observation_lineage"]["source_seed_point_id"])
            require(_decode_structural(lineage_cell, shared, audit) == expected_lineage, "TARGET_SOURCE_OBSERVATION_LINEAGE_UNRESOLVED", "target row differs from accepted MODEL-12 source lineage")
            vintage_text = _decode_structural(vintage_cell, shared, audit)
            years = re.findall(r"(?<![0-9])((?:19|20)[0-9]{2})(?![0-9])", vintage_text)
            require(len(years) == 1 and int(years[0]) == int(item["forecast_vintage"]), "FORECAST_VINTAGE_INVALID", "target row vintage differs from accepted MODEL-12 lineage")
            status, value, reason = _target_value(cells.get(policy.columns["isolated_sales"]), audit)
            output.append({"source_observation_id": str(item["source_observation_id"]), "forecast_vintage": int(item["forecast_vintage"]), "target_status": status, "isolated_sales": value, "target_status_reason": reason})
    require(
        audit.authorized_isolated_sales_cell_examinations == len(eligible_observations)
        and audit.valid_isolated_sales_decode_calls + audit.missing_isolated_sales_count + audit.invalid_isolated_sales_count == len(eligible_observations)
        and audit.impacted_sales_body_decode_calls == 0
        and audit.other_outcome_body_decode_calls == 0
        and audit.quarantined_target_body_decode_calls == 0
        and audit.non_michigan_target_decode_calls == 0,
        "TARGET_ACCESS_AUDIT_FAILED",
        "target access exceeded the exact permitted projection",
    )
    return output, audit
