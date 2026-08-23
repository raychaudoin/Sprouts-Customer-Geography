"""Exact-row XLSX projection for authorized Wisconsin development evidence."""

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


WISCONSIN_MARKETS = frozenset({"milwaukee", "madison"})


@dataclass
class DevelopmentTargetAccessAudit:
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


class WisconsinDevelopmentProjectionPolicy:
    """Default-deny minimum projection for one exact target workbook."""

    PROJECTION_ID = "MODEL09_MINIMUM_WISCONSIN_DEVELOPMENT_TARGET_PROJECTION_V1"
    VERSION = "1.0.0"
    ALLOWED_FIELDS = frozenset({"lineage_key", "forecast_vintage", "isolated_sales"})

    def __init__(
        self,
        authority: Mapping[str, Any],
        workbook_handle: str,
        source_workbook_identity: str,
    ):
        require(
            authority.get("projection_id") == self.PROJECTION_ID
            and authority.get("version") == self.VERSION,
            "TARGET_PROJECTION_IDENTITY_MISMATCH",
            "minimum target projection identity/version mismatch",
        )
        require(
            authority.get("workbook_handle") == workbook_handle
            and authority.get("source_workbook_identity") == source_workbook_identity,
            "TARGET_SOURCE_HANDLE_MISMATCH",
            "projection references another exact target source",
        )
        require(
            authority.get("default_deny") is True,
            "TARGET_PROJECTION_NOT_DEFAULT_DENY",
            "target projection must be default-deny",
        )
        require(
            authority.get("allowed_state") == "wisconsin"
            and set(authority.get("allowed_markets", [])) == WISCONSIN_MARKETS,
            "TARGET_COHORT_POLICY_MISMATCH",
            "projection must be restricted to Milwaukee and Madison, Wisconsin",
        )
        require(
            authority.get("permitted_target_field") == "Isolated Sales"
            and authority.get("denied_target_field") == "Impacted Sales",
            "TARGET_FIELD_POLICY_MISMATCH",
            "only Isolated Sales may be projected and Impacted Sales must be denied",
        )
        require(
            authority.get("model04_lineage_field") == "source_seed_point_id"
            and authority.get("forecast_vintage_field") == "vintage_year"
            and authority.get("source_row_field") == "source_row",
            "TARGET_LINEAGE_POLICY_MISMATCH",
            "projection must use accepted MODEL-04 lineage, vintage, and row identity",
        )
        sheet_name = authority.get("sheet_name")
        header_row = authority.get("header_row")
        columns = authority.get("columns")
        headers = authority.get("headers")
        require(
            isinstance(sheet_name, str) and bool(sheet_name),
            "TARGET_SHEET_AUTHORITY_UNRESOLVED",
            "exact target sheet authority is missing",
        )
        require(
            isinstance(header_row, int) and header_row >= 1,
            "TARGET_HEADER_ROW_INVALID",
            "exact target header row is missing",
        )
        require(
            isinstance(columns, Mapping)
            and set(columns) == {"lineage_key", "forecast_vintage", "isolated_sales"},
            "TARGET_COLUMN_AUTHORITY_INVALID",
            "exact minimum projection columns are required",
        )
        require(
            isinstance(headers, Mapping) and set(headers) == set(columns),
            "TARGET_HEADER_AUTHORITY_INVALID",
            "exact minimum projection headers are required",
        )
        normalized = {key: str(value).strip().upper() for key, value in columns.items()}
        require(
            all(re.fullmatch(r"[A-Z]{1,3}", value) for value in normalized.values())
            and len(set(normalized.values())) == 3,
            "TARGET_COLUMN_AUTHORITY_INVALID",
            "minimum projection columns must be distinct Excel column letters",
        )
        self.workbook_handle = workbook_handle
        self.source_workbook_identity = source_workbook_identity
        self.sheet_name = sheet_name
        self.header_row = header_row
        self.columns = normalized
        self.headers = {key: str(value) for key, value in headers.items()}
        require(
            self.headers["isolated_sales"] == "Isolated Sales"
            and "Impacted Sales" not in self.headers.values(),
            "TARGET_HEADER_AUTHORITY_INVALID",
            "the target header allowlist must contain Isolated Sales and exclude Impacted Sales",
        )

    def authorize(
        self,
        *,
        field: str,
        market: str,
        quarantined: bool,
        row_allowed: bool,
    ) -> None:
        require(
            field in self.ALLOWED_FIELDS,
            "TARGET_FIELD_DENIED",
            "requested field is outside the minimum projection allowlist",
        )
        require(
            market in WISCONSIN_MARKETS,
            "TARGET_MARKET_DENIED",
            "only Milwaukee and Madison target evidence is authorized",
        )
        require(
            not quarantined,
            "TARGET_QUARANTINE_DENIED",
            "ambiguous or quarantined target evidence is prohibited",
        )
        require(
            row_allowed,
            "TARGET_ROW_DENIED",
            "row is absent from the target-blind MODEL-04 cohort",
        )


class _AuthorizedRowsHandler:
    """Retain only headers and exact MODEL-04-authorized source rows."""

    def __init__(
        self,
        *,
        header_row: int,
        authorized_rows: set[int],
        allowed_columns: set[str],
        target_column: str,
        audit: DevelopmentTargetAccessAudit,
    ):
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
            relevant = column in self.allowed_columns and (
                row == self.header_row or row in self.authorized_rows
            )
            self._cell = {
                "address": address,
                "column": column,
                "row": row,
                "cell_type": attributes.get("t", "n"),
                "payload_parts": [],
                "formula_present": False,
                "relevant": relevant,
                "target_body": column == self.target_column and row != self.header_row,
            }
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
            require(
                cell["column"] not in row_cells,
                "XLSX_DUPLICATE_CELL_REJECTED",
                "worksheet contains a duplicate permitted cell reference",
            )
            row_cells[cell["column"]] = RawCell(
                cell["address"],
                cell["column"],
                cell["row"],
                cell["cell_type"],
                "".join(cell["payload_parts"]),
                bool(cell["formula_present"]),
                bool(cell["target_body"]),
            )
        else:
            self.audit.unrelated_cells_ignored += 1
        self._cell = None
        self._capture = False


def _structural_value(
    cell: RawCell,
    shared_strings: Mapping[int, str],
    audit: DevelopmentTargetAccessAudit,
) -> str:
    require(
        not cell.formula_present,
        "PERMITTED_STRUCTURAL_FORMULA_REJECTED",
        "lineage, vintage, and header evidence must be stored as values",
    )
    audit.structural_payload_decode_calls += 1
    payload = cell.payload or ""
    if cell.cell_type == "s":
        require(
            payload.isdigit() and int(payload) in shared_strings,
            "XLSX_SHARED_STRING_INDEX_INVALID",
            "permitted shared-string index is unresolved",
        )
        return shared_strings[int(payload)]
    require(
        cell.cell_type in {"n", "inlineStr", "str", "b"},
        "XLSX_CELL_TYPE_UNSUPPORTED",
        "permitted structural cell type is unsupported",
    )
    return payload


def _canonical_decimal(
    cell: RawCell,
    audit: DevelopmentTargetAccessAudit,
) -> str:
    require(
        cell.target_body
        and cell.cell_type == "n"
        and not cell.formula_present
        and bool(cell.payload),
        "ISOLATED_SALES_CELL_INVALID",
        "authorized Isolated Sales must be a stored numeric value",
    )
    try:
        value = Decimal(str(cell.payload))
    except InvalidOperation as exc:
        raise ConformanceError(
            "ISOLATED_SALES_VALUE_INVALID",
            "authorized Isolated Sales is not a finite decimal value",
        ) from exc
    require(
        value.is_finite(),
        "ISOLATED_SALES_VALUE_INVALID",
        "authorized Isolated Sales is not a finite decimal value",
    )
    audit.authorized_isolated_sales_decode_calls += 1
    if value == 0:
        return "0"
    normalized = value.normalize()
    rendered = format(normalized, "f")
    return rendered.rstrip("0").rstrip(".") if "." in rendered else rendered


def project_authorized_isolated_sales(
    workbook_path: Path,
    policy: WisconsinDevelopmentProjectionPolicy,
    requested_rows: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], DevelopmentTargetAccessAudit]:
    """Decode only Isolated Sales at exact target-blind MODEL-04 source rows."""
    audit = DevelopmentTargetAccessAudit()
    by_row: dict[int, Mapping[str, Any]] = {}
    keys: set[tuple[str, int]] = set()
    for item in requested_rows:
        require(
            item.get("source_workbook_identity") == policy.source_workbook_identity
            and item.get("source_sheet") == policy.sheet_name,
            "TARGET_SOURCE_IDENTITY_MISMATCH",
            "MODEL-04 row is routed to another exact target source",
        )
        row = item.get("source_row")
        require(
            isinstance(row, int) and row > policy.header_row and row not in by_row,
            "TARGET_SOURCE_ROW_INVALID",
            "MODEL-04 source row is missing, reserved, or duplicate",
        )
        key = (str(item.get("lineage_key")), int(item.get("forecast_vintage")))
        require(
            key not in keys,
            "TARGET_LINEAGE_PAIR_DUPLICATE",
            "MODEL-04 lineage/vintage join is duplicate",
        )
        policy.authorize(
            field="isolated_sales",
            market=str(item.get("market")),
            quarantined=bool(item.get("quarantined")),
            row_allowed=True,
        )
        keys.add(key)
        by_row[row] = item
    require(
        bool(by_row),
        "WISCONSIN_COHORT_EMPTY",
        "no eligible Wisconsin target rows were supplied",
    )

    try:
        archive = zipfile.ZipFile(workbook_path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise ConformanceError(
            "TARGET_WORKBOOK_FORMAT_UNSUPPORTED",
            "authorized target source is not a readable XLSX container",
        ) from exc
    with archive:
        worksheet_member = _relationship_target(archive, policy.sheet_name)
        handler = _AuthorizedRowsHandler(
            header_row=policy.header_row,
            authorized_rows=set(by_row),
            allowed_columns=set(policy.columns.values()),
            target_column=policy.columns["isolated_sales"],
            audit=audit,
        )
        try:
            with archive.open(worksheet_member) as stream:
                _parse_stream(stream, handler)
        except KeyError as exc:
            raise ConformanceError(
                "TARGET_SHEET_CONTENT_UNRESOLVED",
                "authorized target worksheet content is absent",
            ) from exc

        structural = [
            cell
            for cells in handler.rows.values()
            for cell in cells.values()
            if not cell.target_body
        ]
        indexes = {
            int(cell.payload or "")
            for cell in structural
            if cell.cell_type == "s" and (cell.payload or "").isdigit()
        }
        shared_strings = _load_shared_strings(archive, indexes)
        headers = handler.rows.get(policy.header_row, {})
        for semantic, column in policy.columns.items():
            cell = headers.get(column)
            require(
                cell is not None,
                "TARGET_HEADER_UNRESOLVED",
                "authorized projection header cell is absent",
            )
            require(
                _structural_value(cell, shared_strings, audit) == policy.headers[semantic],
                "TARGET_HEADER_MISMATCH",
                "authorized projection header differs from its exact authority",
            )

        output: list[dict[str, Any]] = []
        for row, item in sorted(by_row.items()):
            cells = handler.rows.get(row, {})
            lineage_cell = cells.get(policy.columns["lineage_key"])
            vintage_cell = cells.get(policy.columns["forecast_vintage"])
            target_cell = cells.get(policy.columns["isolated_sales"])
            require(
                lineage_cell is not None
                and vintage_cell is not None
                and target_cell is not None,
                "TARGET_ROW_UNRESOLVED",
                "an exact MODEL-04 target row is incomplete",
            )
            lineage = _structural_value(lineage_cell, shared_strings, audit)
            vintage_text = _structural_value(vintage_cell, shared_strings, audit)
            require(
                lineage == str(item["lineage_key"]),
                "TARGET_LINEAGE_PAIR_UNRESOLVED",
                "target row lineage differs from accepted MODEL-04",
            )
            years = re.findall(r"(?<![0-9])((?:19|20)[0-9]{2})(?![0-9])", vintage_text)
            require(
                len(years) == 1 and int(years[0]) == int(item["forecast_vintage"]),
                "FORECAST_VINTAGE_INVALID",
                "target row vintage differs from accepted MODEL-04",
            )
            output.append(
                {
                    "physical_location_id": str(item["physical_location_id"]),
                    "lineage_key": lineage,
                    "forecast_vintage": int(item["forecast_vintage"]),
                    "isolated_sales": _canonical_decimal(target_cell, audit),
                }
            )
    require(
        audit.authorized_isolated_sales_decode_calls == len(requested_rows)
        and audit.impacted_sales_decode_calls == 0
        and audit.non_wisconsin_target_decode_calls == 0,
        "TARGET_ACCESS_AUDIT_FAILED",
        "target access exceeded the exact authorized projection",
    )
    return output, audit
