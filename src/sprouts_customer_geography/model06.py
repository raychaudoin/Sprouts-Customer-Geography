"""MODEL-06 target-blind dependency materialization.

This module deliberately does not use an Excel object model.  The projection
reader materializes only header cells and body cells A:I from the expected
worksheet XML.  It never loads formulas, styles, comments, charts, cached
formula results, or body values outside the authorized projection.
"""

from __future__ import annotations

import copy
import io
import json
import math
import os
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence
from xml.parsers import expat

from sprouts_customer_geography.pipe01.canonical import (
    canonical_bytes,
    content_digest,
    file_sha256,
    write_json_exclusive,
)
from sprouts_customer_geography.pipe01.commitment import (
    DOMAIN_SEPARATOR,
    freeze_commitment,
    new_nonce,
)
from sprouts_customer_geography.pipe01.errors import ConformanceError, require


PACKAGE_ID = "MODEL04_VALIDATION_IDENTITY_ROLE_ANCHOR_PACKAGE_V1"
PACKAGE_VERSION = "1.0.0"
COMMITMENT_ID = "MODEL04_VALIDATION_IDENTITY_ROLE_ANCHOR_COMMITMENT_V1"
COMMITMENT_VERSION = "1.0.0"
PREREGISTRATION_ID = "MODEL05_PROSPECTIVE_VALIDATION_PREREGISTRATION_V1"
PREREGISTRATION_VERSION = "1.0.0"
IDENTITY_VERSION = "MODEL04_TARGET_BLIND_PHYSICAL_LOCATION_IDENTITY_V1"
ANCHOR_VERSION = "MODEL04_EARLIEST_OBSERVED_MEMBER_ANCHOR_V1"
PACKAGE_SCHEMA = "model04-validation-identity-role-anchor-package-v1"
COMMITMENT_DOMAIN = DOMAIN_SEPARATOR.decode("utf-8")

SHEET_MEMBER = "xl/worksheets/sheet1.xml"
SHARED_STRINGS_MEMBER = "xl/sharedStrings.xml"
AUTHORIZED_BODY_MAX_COLUMN = 9
TARGET_HEADER_TOKENS = {"isolatedsales", "impactedsales"}
IDENTITY_STATES = {
    "SAME_UNDERLYING_LOCATION",
    "PROBABLE_SAME_LOCATION",
    "AMBIGUOUS_IDENTITY",
    "GENUINELY_NEW_LOCATION",
}
EVIDENCE_ROLES = {
    "DEVELOPMENT_REFERENCE",
    "TEMPORAL_VALIDATION",
    "PROSPECTIVE_MILWAUKEE_HOLDOUT",
    "EXTERNAL_MADISON_HOLDOUT",
    "AMBIGUOUS_QUARANTINE",
}
IDENTITY_REASON_CODES = {
    "EXACT_OBSERVED_COORDINATE",
    "COHERENT_STABLE_NON_TARGET_LINEAGE",
    "COARSER_PRECISION_UNIQUE_MUTUAL_NEAREST_WITHIN_10M",
    "CONFLICTING_OR_10_TO_500M_IDENTITY_EVIDENCE",
    "MORE_THAN_500M_WITHOUT_STABLE_LINEAGE_OR_CONFLICT",
}


HEADER_ALIASES = {
    "vintage": {"year", "vintage", "yearvintage", "forecastyear"},
    "seed_point_id": {"seedpointid", "seedpoint_id", "seedid", "source_seed_point_id", "sourceid", "id"},
    "address": {"address", "streetaddress", "siteaddress"},
    "city": {"city"},
    "state": {"state", "st"},
    "zip": {"zip", "zipcode", "postalcode", "zippostalcode"},
    "latitude": {"latitude", "lat"},
    "longitude": {"longitude", "lon", "lng", "long"},
    "market": {"msa", "market", "msamarket", "marketmsa"},
}


def _fail(code: str, detail: str) -> None:
    raise ConformanceError(code, detail)


def _column_number(reference: str) -> int:
    match = re.fullmatch(r"([A-Z]+)([1-9][0-9]*)", reference.upper())
    if not match:
        _fail("TARGET_BLIND_MATERIALIZATION_NOT_ENFORCEABLE", "invalid worksheet cell reference")
    number = 0
    for character in match.group(1):
        number = number * 26 + ord(character) - ord("A") + 1
    return number


def _row_number(reference: str) -> int:
    match = re.fullmatch(r"[A-Z]+([1-9][0-9]*)", reference.upper())
    if not match:
        _fail("TARGET_BLIND_MATERIALIZATION_NOT_ENFORCEABLE", "invalid worksheet cell reference")
    return int(match.group(1))


def _normalized_header(value: Any) -> str:
    return re.sub(r"[^a-z0-9_]", "", str(value or "").strip().lower().replace(" ", ""))


def _load_selected_shared_strings(archive: zipfile.ZipFile, needed: set[int]) -> dict[int, str]:
    if not needed:
        return {}
    try:
        stream = archive.open(SHARED_STRINGS_MEMBER, "r")
    except KeyError as exc:
        raise ConformanceError(
            "TARGET_BLIND_MATERIALIZATION_NOT_ENFORCEABLE",
            "authorized cells reference shared strings but sharedStrings.xml is absent",
        ) from exc
    selected: dict[int, str] = {}
    state: dict[str, Any] = {"index": -1, "selected": False, "in_text": False, "chunks": []}

    def local(name: str) -> str:
        return name.rsplit("}", 1)[-1]

    def start(name: str, _attributes: Mapping[str, str]) -> None:
        element = local(name)
        if element == "si":
            state["index"] += 1
            state["selected"] = state["index"] in needed
            state["chunks"] = []
        elif element == "t" and state["selected"]:
            state["in_text"] = True

    def end(name: str) -> None:
        element = local(name)
        if element == "t":
            state["in_text"] = False
        elif element == "si":
            if state["selected"]:
                selected[state["index"]] = "".join(state["chunks"])
            state["selected"] = False
            state["chunks"] = []

    def characters(value: str) -> None:
        if state["selected"] and state["in_text"]:
            state["chunks"].append(value)

    parser = expat.ParserCreate(namespace_separator="}")
    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.CharacterDataHandler = characters
    with stream:
        for block in iter(lambda: stream.read(64 * 1024), b""):
            parser.Parse(block, False)
        parser.Parse(b"", True)
    if set(selected) != needed:
        _fail("TARGET_BLIND_MATERIALIZATION_NOT_ENFORCEABLE", "shared-string reference is unresolved")
    return selected


@dataclass(frozen=True)
class ProjectedWorkbook:
    source_identity: str
    rows: tuple[dict[str, Any], ...]
    projection_sha256: str
    access_report: Mapping[str, Any]


def read_target_blind_projection(
    path: Path | bytes,
    source_identity: str,
    *,
    header_alias_overrides: Mapping[str, Sequence[str]] | None = None,
) -> ProjectedWorkbook:
    """Read Sheet1 headers and A:I body cells without materializing target values."""

    if isinstance(path, bytes):
        archive_source: Path | io.BytesIO = io.BytesIO(path)
    else:
        require(path.is_file(), "PROTECTED_SOURCE_MISSING", f"authorized source is absent: {path.name}")
        archive_source = path
    raw_cells: dict[str, tuple[str, Any]] = {}
    header_references: list[str] = []
    needed_shared: set[int] = set()
    body_rows_seen: set[int] = set()
    max_body_column_observed = 0

    with zipfile.ZipFile(archive_source, "r") as archive:
        try:
            stream = archive.open(SHEET_MEMBER, "r")
        except KeyError as exc:
            raise ConformanceError(
                "TARGET_BLIND_MATERIALIZATION_NOT_ENFORCEABLE",
                "expected Sheet1 worksheet member is absent",
            ) from exc
        state: dict[str, Any] = {
            "reference": None,
            "authorized": False,
            "cell_type": "n",
            "capture": False,
            "chunks": [],
        }

        def local(name: str) -> str:
            return name.rsplit("}", 1)[-1]

        def start(name: str, attributes: Mapping[str, str]) -> None:
            nonlocal max_body_column_observed
            element = local(name)
            if element == "c":
                reference = attributes.get("r", "").upper()
                column = _column_number(reference)
                row = _row_number(reference)
                if row > 1:
                    max_body_column_observed = max(max_body_column_observed, column)
                state["reference"] = reference
                state["authorized"] = row == 1 or column <= AUTHORIZED_BODY_MAX_COLUMN
                state["cell_type"] = attributes.get("t", "n") if state["authorized"] else None
                state["capture"] = False
                state["chunks"] = []
            elif state["authorized"] and element == "f":
                # Fail before any formula character data or cached value is retained.
                _fail("TARGET_BLIND_MATERIALIZATION_NOT_ENFORCEABLE", "formula present in authorized projection")
            elif state["authorized"] and element in {"v", "t"}:
                state["capture"] = True
                state["chunks"] = []

        def end(name: str) -> None:
            element = local(name)
            if element in {"v", "t"} and state["authorized"] and state["capture"]:
                value = "".join(state["chunks"])
                # Rich inline strings can contain multiple t elements.
                if state.get("raw_value") is None:
                    state["raw_value"] = value
                else:
                    state["raw_value"] += value
                state["capture"] = False
                state["chunks"] = []
            elif element == "c":
                if state["authorized"]:
                    reference = state["reference"]
                    cell_type = state["cell_type"]
                    raw_value = state.get("raw_value")
                    if cell_type == "s" and raw_value is not None:
                        try:
                            needed_shared.add(int(raw_value))
                        except (TypeError, ValueError) as exc:
                            raise ConformanceError(
                                "TARGET_BLIND_MATERIALIZATION_NOT_ENFORCEABLE",
                                "invalid shared-string reference in authorized projection",
                            ) from exc
                    raw_cells[reference] = (cell_type, raw_value)
                    row = _row_number(reference)
                    if row == 1:
                        header_references.append(reference)
                    else:
                        body_rows_seen.add(row)
                state.update({"reference": None, "authorized": False, "cell_type": "n", "capture": False, "chunks": [], "raw_value": None})

        def characters(value: str) -> None:
            if state["authorized"] and state["capture"]:
                state["chunks"].append(value)

        parser = expat.ParserCreate(namespace_separator="}")
        parser.StartElementHandler = start
        parser.EndElementHandler = end
        parser.CharacterDataHandler = characters
        with stream:
            for block in iter(lambda: stream.read(64 * 1024), b""):
                parser.Parse(block, False)
            parser.Parse(b"", True)
        shared = _load_selected_shared_strings(archive, needed_shared)

    def decode(cell: tuple[str, Any] | None) -> Any:
        if cell is None:
            return None
        cell_type, raw_value = cell
        if raw_value is None:
            return None
        if cell_type == "s":
            return shared[int(raw_value)]
        if cell_type in {"inlineStr", "str", "b"}:
            return raw_value
        if cell_type == "n":
            text = str(raw_value)
            try:
                number = float(text)
            except ValueError:
                _fail("TARGET_BLIND_MATERIALIZATION_NOT_ENFORCEABLE", "nonnumeric cell marked numeric")
            return int(number) if number.is_integer() else number
        return raw_value

    headers_by_column = {
        _column_number(reference): decode(raw_cells[reference]) for reference in header_references
    }
    target_headers = {
        column: _normalized_header(value)
        for column, value in headers_by_column.items()
        if _normalized_header(value) in TARGET_HEADER_TOKENS
    }
    if not target_headers or any(column <= AUTHORIZED_BODY_MAX_COLUMN for column in target_headers):
        _fail(
            "TARGET_BLIND_MATERIALIZATION_NOT_ENFORCEABLE",
            "forecast target headers were not confirmed exclusively outside A:I",
        )

    aliases_by_field = {field: set(aliases) for field, aliases in HEADER_ALIASES.items()}
    if header_alias_overrides is not None:
        require(
            isinstance(header_alias_overrides, Mapping)
            and set(header_alias_overrides) <= set(aliases_by_field),
            "TARGET_BLIND_HEADER_ALIAS_OVERRIDE_INVALID",
            "target-blind header alias override fields differ from the accepted identity projection",
        )
        for field, raw_aliases in header_alias_overrides.items():
            require(
                isinstance(raw_aliases, Sequence)
                and not isinstance(raw_aliases, (str, bytes))
                and bool(raw_aliases)
                and all(isinstance(alias, str) and bool(alias.strip()) for alias in raw_aliases),
                "TARGET_BLIND_HEADER_ALIAS_OVERRIDE_INVALID",
                "target-blind header alias overrides must contain nonempty strings",
            )
            aliases_by_field[field].update(_normalized_header(alias) for alias in raw_aliases)

    field_columns: dict[str, int] = {}
    for field, aliases in aliases_by_field.items():
        matches = [
            column
            for column, value in headers_by_column.items()
            if column <= AUTHORIZED_BODY_MAX_COLUMN and _normalized_header(value) in aliases
        ]
        if len(matches) != 1:
            _fail(
                "TARGET_BLIND_MATERIALIZATION_NOT_ENFORCEABLE",
                f"authorized field {field!r} does not map uniquely within A:I; "
                f"authorized headers={{{', '.join(f'{column}: {headers_by_column.get(column)!r}' for column in range(1, AUTHORIZED_BODY_MAX_COLUMN + 1))}}}",
            )
        field_columns[field] = matches[0]
    if set(field_columns.values()) != set(range(1, AUTHORIZED_BODY_MAX_COLUMN + 1)):
        _fail("TARGET_BLIND_MATERIALIZATION_NOT_ENFORCEABLE", "A:I is not the exact identity projection")

    projected: list[dict[str, Any]] = []
    for row_number in sorted(body_rows_seen):
        values = {
            field: decode(raw_cells.get(f"{_column_letters(column)}{row_number}"))
            for field, column in field_columns.items()
        }
        if all(value is None or str(value).strip() == "" for value in values.values()):
            continue
        values["source_row"] = row_number
        projected.append(values)
    projection_digest = content_digest(projected)
    return ProjectedWorkbook(
        source_identity=source_identity,
        rows=tuple(projected),
        projection_sha256=projection_digest,
        access_report={
            "source_identity": source_identity,
            "worksheet_member": SHEET_MEMBER,
            "sheet_logical_name": "Sheet1",
            "body_projection": "A:I",
            "body_rows_materialized": len(projected),
            "maximum_authorized_body_column": "I",
            "outside_projection_body_values_materialized": 0,
            "formula_values_materialized": 0,
            "styles_comments_charts_metadata_loaded": False,
            "target_headers_confirmed_outside_projection": sorted(target_headers.values()),
            "max_body_column_observed_by_reference_only": max_body_column_observed,
            "header_alias_override_fields": sorted(header_alias_overrides or {}),
        },
    )


def _column_letters(number: int) -> str:
    letters = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        letters = chr(ord("A") + remainder) + letters
    return letters


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _normalized_text(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", _text(value).lower())


def _year(value: Any) -> int:
    text = _text(value)
    match = re.search(r"(?:19|20)[0-9]{2}", text)
    if not match:
        _fail("MODEL04_VINTAGE_INVALID", "vintage does not contain a four-digit year")
    return int(match.group(0))


def _coordinate(value: Any, latitude: bool) -> float:
    try:
        coordinate = float(value)
    except (TypeError, ValueError) as exc:
        raise ConformanceError("MODEL04_COORDINATE_INVALID", "coordinate is missing or nonnumeric") from exc
    lower, upper = (-90.0, 90.0) if latitude else (-180.0, 180.0)
    require(math.isfinite(coordinate) and lower <= coordinate <= upper, "MODEL04_COORDINATE_INVALID", "coordinate is outside WGS84 bounds")
    return coordinate


def _market(value: Any, city: Any) -> str:
    token = f"{_normalized_text(value)}{_normalized_text(city)}"
    if "milwaukee" in token:
        return "milwaukee"
    if "madison" in token:
        return "madison"
    _fail("MODEL04_MARKET_INVALID", "record is not deterministically assigned to Milwaukee or Madison")


def _precision(value: Any) -> int:
    text = _text(value)
    if "." not in text:
        return 0
    return len(text.rstrip("0").split(".", 1)[1])


def _haversine_m(left: Mapping[str, Any], right: Mapping[str, Any]) -> float:
    radius = 6_371_008.8
    lat1, lat2 = math.radians(left["latitude"]), math.radians(right["latitude"])
    delta_lat = lat2 - lat1
    delta_lon = math.radians(right["longitude"] - left["longitude"])
    a = math.sin(delta_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    return 2 * radius * math.asin(min(1.0, math.sqrt(a)))


def _coarser_precision_equal(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    lat_precision = min(left["latitude_precision"], right["latitude_precision"])
    lon_precision = min(left["longitude_precision"], right["longitude_precision"])
    return round(left["latitude"], lat_precision) == round(right["latitude"], lat_precision) and round(
        left["longitude"], lon_precision
    ) == round(right["longitude"], lon_precision)


def _corroborates(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    address = left["address_norm"] and left["address_norm"] == right["address_norm"]
    city_zip = (
        left["city_norm"]
        and left["city_norm"] == right["city_norm"]
        and left["zip_norm"]
        and left["zip_norm"] == right["zip_norm"]
    )
    return bool(address or city_zip)


def _lineage_conflict(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    if left["state_norm"] != right["state_norm"] or left["market"] != right["market"]:
        return True
    same_seed = left["seed_norm"] and left["seed_norm"] == right["seed_norm"]
    same_address = left["address_norm"] and left["address_norm"] == right["address_norm"]
    distance = _haversine_m(left, right)
    return bool((same_seed or same_address) and distance > 500.0)


def _prepare_rows(workbooks: Sequence[ProjectedWorkbook]) -> list[dict[str, Any]]:
    prepared: list[dict[str, Any]] = []
    for workbook_order, workbook in enumerate(workbooks):
        for row in workbook.rows:
            latitude = _coordinate(row["latitude"], True)
            longitude = _coordinate(row["longitude"], False)
            prepared.append(
                {
                    "source_workbook_identity": workbook.source_identity,
                    "source_workbook_order": workbook_order,
                    "source_sheet": "Sheet1",
                    "source_row": int(row["source_row"]),
                    "source_seed_point_id": _text(row["seed_point_id"]),
                    "seed_norm": _normalized_text(row["seed_point_id"]),
                    "vintage_original": _text(row["vintage"]),
                    "vintage_year": _year(row["vintage"]),
                    "address": _text(row["address"]),
                    "address_norm": _normalized_text(row["address"]),
                    "city": _text(row["city"]),
                    "city_norm": _normalized_text(row["city"]),
                    "state": _text(row["state"]).upper(),
                    "state_norm": _normalized_text(row["state"]),
                    "zip": _text(row["zip"]),
                    "zip_norm": _normalized_text(row["zip"]),
                    "market_source": _text(row["market"]),
                    "market": _market(row["market"], row["city"]),
                    "latitude": latitude,
                    "longitude": longitude,
                    "latitude_precision": _precision(row["latitude"]),
                    "longitude_precision": _precision(row["longitude"]),
                }
            )
    require(bool(prepared), "MODEL04_SOURCE_EMPTY", "no projected identity records were found")
    return sorted(
        prepared,
        key=lambda row: (
            row["vintage_year"], row["source_workbook_order"], row["source_row"], row["source_seed_point_id"]
        ),
    )


def _group_distance(row: Mapping[str, Any], members: Sequence[Mapping[str, Any]]) -> float:
    return min(_haversine_m(row, member) for member in members)


def _group_corroborates(row: Mapping[str, Any], members: Sequence[Mapping[str, Any]]) -> bool:
    return any(_corroborates(row, member) for member in members)


def _group_conflicts(row: Mapping[str, Any], members: Sequence[Mapping[str, Any]]) -> bool:
    return any(_lineage_conflict(row, member) for member in members)


def _mutual_nearest_consistent(
    row: Mapping[str, Any],
    group: Mapping[str, Any],
    all_rows: Sequence[Mapping[str, Any]],
) -> bool:
    peers = [
        peer
        for peer in all_rows
        if peer["vintage_year"] == row["vintage_year"]
        and peer["market"] == row["market"]
        and peer["state_norm"] == row["state_norm"]
    ]
    ranked = sorted(
        ((_group_distance(peer, group["members"]), peer) for peer in peers),
        key=lambda item: (item[0], item[1]["source_workbook_order"], item[1]["source_row"]),
    )
    if not ranked:
        return False
    nearest_distance = ranked[0][0]
    nearest = [peer for distance, peer in ranked if math.isclose(distance, nearest_distance, rel_tol=0.0, abs_tol=1e-9)]
    return len(nearest) == 1 and nearest[0] is row


def _same_exact(row: Mapping[str, Any], members: Sequence[Mapping[str, Any]]) -> bool:
    return any(row["latitude"] == member["latitude"] and row["longitude"] == member["longitude"] for member in members)


def _stable_lineage_match(row: Mapping[str, Any], members: Sequence[Mapping[str, Any]]) -> bool:
    candidates = [
        member
        for member in members
        if (row["seed_norm"] and row["seed_norm"] == member["seed_norm"])
        or (row["address_norm"] and row["address_norm"] == member["address_norm"])
    ]
    return bool(candidates) and all(_haversine_m(row, member) <= 500.0 for member in candidates)


def _deterministic_location_id(anchor_member: Mapping[str, Any]) -> str:
    identity = {
        "domain": "sprouts-customer-geography/model04/physical-location/v1",
        "source_workbook_identity": anchor_member["source_workbook_identity"],
        "source_sheet": anchor_member["source_sheet"],
        "source_row": anchor_member["source_row"],
        "source_seed_point_id": anchor_member["source_seed_point_id"],
        "latitude": anchor_member["latitude"],
        "longitude": anchor_member["longitude"],
    }
    return f"ploc-{content_digest(identity)[:24]}"


def _anchor_member(members: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
    earliest = min(member["vintage_year"] for member in members)
    candidates = [member for member in members if member["vintage_year"] == earliest]
    # No accepted coordinate-provenance tiers exist in these two source contracts;
    # all are observed-workbook coordinates, so the accepted deterministic lineage
    # tie-break applies directly. Decimal precision is deliberately absent.
    return min(
        candidates,
        key=lambda member: (
            member["source_workbook_identity"],
            member["source_sheet"],
            member["source_row"],
            member["source_seed_point_id"],
        ),
    )


def build_identity_package(workbooks: Sequence[ProjectedWorkbook]) -> dict[str, Any]:
    rows = _prepare_rows(workbooks)
    groups: list[dict[str, Any]] = []
    record_results: list[dict[str, Any]] = []

    for row in rows:
        eligible = [
            group
            for group in groups
            if group.get("resolved", True)
            and group["market"] == row["market"]
            and group["state_norm"] == row["state_norm"]
        ]
        prior = [
            group
            for group in eligible
            if min(member["vintage_year"] for member in group["members"]) < row["vintage_year"]
        ]
        exact = [group for group in eligible if _same_exact(row, group["members"])]
        stable = [group for group in eligible if _stable_lineage_match(row, group["members"]) and not _group_conflicts(row, group["members"])]
        distances = sorted(((_group_distance(row, group["members"]), group) for group in prior), key=lambda item: item[0])
        probable = [
            (distance, group)
            for distance, group in distances
            if distance <= 10.0
            and _coarser_precision_equal(row, min(group["members"], key=lambda member: _haversine_m(row, member)))
            and _group_corroborates(row, group["members"])
            and not _group_conflicts(row, group["members"])
            and _mutual_nearest_consistent(row, group, rows)
        ]
        ambiguous_band = [(distance, group) for distance, group in distances if 10.0 < distance <= 500.0]

        linked_group: dict[str, Any] | None = None
        if len(exact) == 1 and not _group_conflicts(row, exact[0]["members"]):
            state, reason, linked_group = "SAME_UNDERLYING_LOCATION", "EXACT_OBSERVED_COORDINATE", exact[0]
        elif len(stable) == 1:
            state, reason, linked_group = "SAME_UNDERLYING_LOCATION", "COHERENT_STABLE_NON_TARGET_LINEAGE", stable[0]
        elif len(probable) == 1 and (len(distances) == 1 or probable[0][0] < distances[1][0]):
            state, reason, linked_group = "PROBABLE_SAME_LOCATION", "COARSER_PRECISION_UNIQUE_MUTUAL_NEAREST_WITHIN_10M", probable[0][1]
        elif exact or stable or len(probable) > 1 or ambiguous_band or any(_group_conflicts(row, group["members"]) for group in eligible):
            state, reason = "AMBIGUOUS_IDENTITY", "CONFLICTING_OR_10_TO_500M_IDENTITY_EVIDENCE"
        else:
            state, reason = "GENUINELY_NEW_LOCATION", "MORE_THAN_500M_WITHOUT_STABLE_LINEAGE_OR_CONFLICT"

        if linked_group is None:
            linked_group = {
                "market": row["market"],
                "state_norm": row["state_norm"],
                "members": [],
                "resolved": state != "AMBIGUOUS_IDENTITY",
            }
            groups.append(linked_group)
        linked_group["members"].append(row)
        record_results.append({"row": row, "group": linked_group, "identity_state": state, "reason_code": reason})

    group_ids: dict[int, str] = {}
    group_anchors: dict[int, Mapping[str, Any]] = {}
    for group in groups:
        anchor = _anchor_member(group["members"])
        if group.get("resolved", True):
            group_ids[id(group)] = _deterministic_location_id(anchor)
            group_anchors[id(group)] = anchor
        else:
            group_ids[id(group)] = f"qloc-{content_digest({'domain': 'model04-quarantine-v1', 'lineage': [anchor['source_workbook_identity'], anchor['source_sheet'], anchor['source_row'], anchor['source_seed_point_id']]})[:24]}"

    protected_records: list[dict[str, Any]] = []
    for result in record_results:
        row = result["row"]
        group = result["group"]
        state = result["identity_state"]
        anchor = group_anchors.get(id(group))
        if state == "AMBIGUOUS_IDENTITY":
            role, subrole, quarantined = "AMBIGUOUS_QUARANTINE", "IDENTITY_UNRESOLVED", True
        elif row["source_workbook_identity"] == "MODEL03A_DEVELOPMENT_REFERENCE_WORKBOOK":
            role, subrole, quarantined = "DEVELOPMENT_REFERENCE", "PRIOR_MILWAUKEE_CONSUMED", False
        elif row["market"] == "milwaukee":
            if state in {"SAME_UNDERLYING_LOCATION", "PROBABLE_SAME_LOCATION"}:
                role, subrole = "TEMPORAL_VALIDATION", "MILWAUKEE_2026_REPEATED_LOCATION"
            else:
                role, subrole = "PROSPECTIVE_MILWAUKEE_HOLDOUT", "MILWAUKEE_2026_GENUINELY_NEW"
            quarantined = False
        else:
            role, quarantined = "EXTERNAL_MADISON_HOLDOUT", False
            if row["vintage_year"] == 2026 and state == "GENUINELY_NEW_LOCATION":
                subrole = "MADISON_2026_GENUINELY_NEW_LOCATION"
            elif state in {"SAME_UNDERLYING_LOCATION", "PROBABLE_SAME_LOCATION"}:
                subrole = "MADISON_REPEATED_LOCATION_EVIDENCE"
            else:
                subrole = "MADISON_HISTORICAL_LOCATION_EVIDENCE"
        protected_records.append(
            {
                "package_id": PACKAGE_ID,
                "package_version": PACKAGE_VERSION,
                "identity_version": IDENTITY_VERSION,
                "physical_location_id": group_ids[id(group)],
                "source_workbook_identity": row["source_workbook_identity"],
                "source_sheet": row["source_sheet"],
                "source_row": row["source_row"],
                "source_seed_point_id": row["source_seed_point_id"],
                "vintage": row["vintage_original"],
                "vintage_year": row["vintage_year"],
                "market": row["market"],
                "identity_state": state,
                "identity_rule_reason_code": result["reason_code"],
                "linked_prior_physical_location_id": group_ids[id(group)] if state in {"SAME_UNDERLYING_LOCATION", "PROBABLE_SAME_LOCATION"} else None,
                "quarantined": quarantined,
                "evidence_role": role,
                "evidence_subrole": subrole,
                "observed_coordinate": {"latitude": row["latitude"], "longitude": row["longitude"], "provenance": "SOURCE_WORKBOOK_OBSERVED_MEMBER"},
                "canonical_anchor": None if anchor is None else {
                    "latitude": anchor["latitude"],
                    "longitude": anchor["longitude"],
                    "source_workbook_identity": anchor["source_workbook_identity"],
                    "source_sheet": anchor["source_sheet"],
                    "source_row": anchor["source_row"],
                    "source_seed_point_id": anchor["source_seed_point_id"],
                    "anchor_version": ANCHOR_VERSION,
                    "selection_semantics": "EARLIEST_VINTAGE_THEN_ACCEPTED_PROVENANCE_TIER_THEN_SOURCE_LINEAGE",
                },
                "canonical_anchor_state": "FAILED_CLOSED_AMBIGUOUS_IDENTITY" if anchor is None else "SELECTED_ACTUAL_OBSERVED_MEMBER",
                "target_view_state": "DEVELOPMENT_CONSUMED" if role == "DEVELOPMENT_REFERENCE" else "SEALED",
            }
        )

    package = {
        "$schema": PACKAGE_SCHEMA,
        "package_id": PACKAGE_ID,
        "package_version": PACKAGE_VERSION,
        "identity_version": IDENTITY_VERSION,
        "canonical_anchor_version": ANCHOR_VERSION,
        "status": "materialized_pending_model06_acceptance",
        "target_blind_projection": {
            "worksheet": "Sheet1",
            "body_columns": "A:I",
            "excluded_body_columns": "J onward",
            "sealed_targets_supplied_or_used": False,
            "source_access_reports": [dict(workbook.access_report) for workbook in workbooks],
        },
        "source_projection_identities": [
            {
                "source_workbook_identity": workbook.source_identity,
                "projection_sha256": workbook.projection_sha256,
                "projection_hash_semantics": "SHA-256 of canonical UTF-8 JSON for authorized A:I projected rows only",
            }
            for workbook in workbooks
        ],
        "identity_rules": {
            "states": sorted(IDENTITY_STATES),
            "probable_same_max_m": 10.0,
            "ambiguity_band_m": {"exclusive_minimum": 10.0, "inclusive_maximum": 500.0},
            "genuinely_new_minimum_m_exclusive": 500.0,
            "seed_id_novelty_alone_is_novelty": False,
            "target_evidence_permitted": False,
        },
        "evidence_role_semantics": sorted(EVIDENCE_ROLES),
        "records": protected_records,
        "supersedes": None,
        "supersession_policy": "Never overwrite this immutable package. A correction creates a successor package with explicit supersedes lineage and new content identity and commitment evidence.",
        "materialization_provenance": {
            "capability": "MODEL-06",
            "implementation": "sprouts_customer_geography.model06",
            "mode": "deterministic target-blind canonical JSON materialization",
            "wall_clock_excluded_from_semantic_content": True,
        },
    }
    semantic = copy.deepcopy(package)
    package["protected_content_sha256"] = content_digest(semantic)
    package["protected_content_hash_semantics"] = "SHA-256 of canonical UTF-8 JSON after removing protected_content_sha256 and protected_content_hash_semantics; recursively sorted keys, compact separators, Unicode preserved, no NaN."
    # Recalculate with both self-description fields removed, matching validation.
    semantic = copy.deepcopy(package)
    semantic.pop("protected_content_sha256")
    semantic.pop("protected_content_hash_semantics")
    package["protected_content_sha256"] = content_digest(semantic)
    return package


def validate_identity_package(package: Mapping[str, Any]) -> dict[str, Any]:
    required = {"package_id", "package_version", "identity_version", "canonical_anchor_version", "records", "supersedes", "protected_content_sha256", "protected_content_hash_semantics"}
    require(required <= set(package), "MODEL04_PACKAGE_SCHEMA_INVALID", f"missing package fields: {sorted(required - set(package))}")
    require(package["package_id"] == PACKAGE_ID and package["package_version"] == PACKAGE_VERSION, "MODEL04_PACKAGE_IDENTITY_MISMATCH", "package identity/version mismatch")
    semantic = copy.deepcopy(dict(package))
    expected = semantic.pop("protected_content_sha256")
    semantic.pop("protected_content_hash_semantics")
    require(content_digest(semantic) == expected, "MODEL04_CONTENT_HASH_MISMATCH", "protected semantic content hash mismatch")
    records = package["records"]
    require(isinstance(records, list) and records, "MODEL04_PACKAGE_SCHEMA_INVALID", "records must be nonempty")
    for record in records:
        require(record["identity_state"] in IDENTITY_STATES, "MODEL04_IDENTITY_STATE_INVALID", "identity state is not accepted")
        require(record["identity_rule_reason_code"] in IDENTITY_REASON_CODES, "MODEL04_IDENTITY_REASON_INVALID", "identity reason is not accepted")
        require(record["evidence_role"] in EVIDENCE_ROLES, "MODEL04_ROLE_INVALID", "evidence role is not accepted")
        require(record["quarantined"] is (record["identity_state"] == "AMBIGUOUS_IDENTITY"), "MODEL04_QUARANTINE_MISMATCH", "ambiguity must map exactly to quarantine")
        require(record["target_view_state"] in {"SEALED", "DEVELOPMENT_CONSUMED"}, "MODEL04_TARGET_STATE_INVALID", "initial target state is invalid")
        observed = record["observed_coordinate"]
        anchor = record["canonical_anchor"]
        group = [other for other in records if other["physical_location_id"] == record["physical_location_id"]]
        if record["identity_state"] == "AMBIGUOUS_IDENTITY":
            require(anchor is None and record["canonical_anchor_state"] == "FAILED_CLOSED_AMBIGUOUS_IDENTITY", "MODEL04_AMBIGUOUS_ANCHOR_NOT_CLOSED", "ambiguous identity must not receive an anchor")
        else:
            require(isinstance(anchor, Mapping) and any(other["observed_coordinate"]["latitude"] == anchor["latitude"] and other["observed_coordinate"]["longitude"] == anchor["longitude"] for other in group), "MODEL04_SYNTHETIC_ANCHOR_REJECTED", "anchor is not an actual observed member")
            earliest_year = min(other["vintage_year"] for other in group)
            expected = min(
                (other for other in group if other["vintage_year"] == earliest_year),
                key=lambda other: (
                    other["source_workbook_identity"],
                    other["source_sheet"],
                    other["source_row"],
                    other["source_seed_point_id"],
                ),
            )
            require(
                anchor["source_workbook_identity"] == expected["source_workbook_identity"]
                and anchor["source_sheet"] == expected["source_sheet"]
                and anchor["source_row"] == expected["source_row"]
                and anchor["source_seed_point_id"] == expected["source_seed_point_id"]
                and anchor["latitude"] == expected["observed_coordinate"]["latitude"]
                and anchor["longitude"] == expected["observed_coordinate"]["longitude"],
                "MODEL04_ANCHOR_SELECTION_MISMATCH",
                "anchor does not follow earliest-vintage and deterministic lineage tie-break semantics",
            )
        if record["identity_state"] == "AMBIGUOUS_IDENTITY":
            require(record["evidence_role"] == "AMBIGUOUS_QUARANTINE", "MODEL04_ROLE_INVALID", "ambiguous identity is not quarantined")
        elif record["source_workbook_identity"] == "MODEL03A_DEVELOPMENT_REFERENCE_WORKBOOK":
            require(record["evidence_role"] == "DEVELOPMENT_REFERENCE", "MODEL04_ROLE_INVALID", "prior Milwaukee evidence role changed")
        elif record["market"] == "milwaukee" and record["identity_state"] in {"SAME_UNDERLYING_LOCATION", "PROBABLE_SAME_LOCATION"}:
            require(record["evidence_role"] == "TEMPORAL_VALIDATION", "MODEL04_ROLE_INVALID", "repeated Milwaukee evidence role changed")
        elif record["market"] == "milwaukee":
            require(record["evidence_role"] == "PROSPECTIVE_MILWAUKEE_HOLDOUT", "MODEL04_ROLE_INVALID", "new Milwaukee evidence role changed")
        elif record["market"] == "madison":
            require(record["evidence_role"] == "EXTERNAL_MADISON_HOLDOUT", "MODEL04_ROLE_INVALID", "Madison evidence role changed")
        require(math.isfinite(float(observed["latitude"])) and math.isfinite(float(observed["longitude"])), "MODEL04_COORDINATE_INVALID", "observed coordinate is invalid")
    return {
        "state": "passed",
        "record_count": len(records),
        "physical_location_count": len({record["physical_location_id"] for record in records}),
        "quarantine_count": sum(record["quarantined"] for record in records),
        "roles_present": sorted({record["evidence_role"] for record in records}),
    }


def validate_preregistration(document: Mapping[str, Any]) -> dict[str, Any]:
    required = {"artifact_id", "version", "canonical_schema_version", "content_sha256", "dependencies", "spatial_contexts", "prospective_candidate_state", "ranking_and_level", "validation", "target_governance", "supersedes"}
    require(required <= set(document), "MODEL05_PREREGISTRATION_SCHEMA_INVALID", f"missing preregistration fields: {sorted(required - set(document))}")
    require(document["artifact_id"] == PREREGISTRATION_ID and document["version"] == PREREGISTRATION_VERSION, "MODEL05_PREREGISTRATION_IDENTITY_MISMATCH", "preregistration identity/version mismatch")
    hashed = copy.deepcopy(dict(document))
    expected = hashed.pop("content_sha256")
    require(content_digest(hashed) == expected, "MODEL05_CONTENT_HASH_MISMATCH", "preregistration canonical content hash mismatch")
    spatial = document["spatial_contexts"]
    require(spatial["primary"] == {"statute_miles": 5, "metres": 8046.72}, "MODEL05_PRIMARY_RADIUS_MISMATCH", "primary radius changed")
    require(spatial["sensitivity"] == [{"statute_miles": 3, "metres": 4828.032}, {"statute_miles": 7, "metres": 11265.408}], "MODEL05_SENSITIVITY_RADIUS_MISMATCH", "sensitivity radii changed")
    require(document["prospective_candidate_state"]["eligible_candidates"] == ["BASELINE_HOUSEHOLD"], "MODEL05_CANDIDATE_MISMATCH", "candidate set changed")
    require(document["prospective_candidate_state"]["champion_state"] == "NO_CUSTOMER_FIT_CHAMPION_CANDIDATE", "MODEL05_CHAMPION_MISMATCH", "champion state changed")
    require(document["ranking_and_level"]["primary_metric"] == "Kendall tau-b" and document["ranking_and_level"]["directional_materiality_threshold"] == 0.20, "MODEL05_RANKING_RULE_MISMATCH", "ranking rule changed")
    require(document["dependence"]["stress_grouping_jaccard_threshold"] == 0.25, "MODEL05_DEPENDENCE_RULE_MISMATCH", "dependence threshold changed")
    require(document["geometric_completeness"]["primary_minimum"] == 0.90 and document["geometric_completeness"]["secondary_minimum"] == 0.75, "MODEL05_COMPLETENESS_RULE_MISMATCH", "completeness thresholds changed")
    require(document["validation"]["stage_order"] == ["MILWAUKEE_TEMPORAL_VALIDATION", "MILWAUKEE_PROSPECTIVE_NEW_LOCATION_VALIDATION", "MADISON_HISTORICAL_REPEATED_LOCATION_EXTERNAL_VALIDATION", "MADISON_2026_GENUINELY_NEW_LOCATION_EXTERNAL_VALIDATION"], "MODEL05_STAGE_ORDER_MISMATCH", "validation stage order changed")
    require(document["target_governance"]["state_progression"] == ["SEALED", "EVALUATION_AUTHORIZED", "EVALUATED_FROZEN", "DIAGNOSTICS_CONSUMED", "DEVELOPMENT_CONSUMED"], "MODEL05_TARGET_STATE_MISMATCH", "target state progression changed")
    return {"state": "passed", "content_sha256": expected, "dependency_count": len(document["dependencies"])}


def build_commitment_evidence(package_path: Path, nonce: bytes) -> dict[str, Any]:
    package_file_digest = file_sha256(package_path)
    commitment = freeze_commitment(package_file_digest, nonce)
    return {
        "$schema": "../../schemas/model/model04_validation_identity_role_anchor_commitment.schema.json",
        "artifact_id": COMMITMENT_ID,
        "version": COMMITMENT_VERSION,
        "protected_package_id": PACKAGE_ID,
        "protected_package_version": PACKAGE_VERSION,
        "domain": COMMITMENT_DOMAIN,
        "commitment_sha256": commitment,
        "commitment_semantics": "SHA-256(domain_separator || NUL || protected 256-bit nonce || NUL || bytes.fromhex(SHA-256(canonical protected package file bytes))).",
        "protected_package_digest_disclosed": False,
        "nonce_disclosed": False,
        "supersedes": None,
        "supersession_policy": "A correction creates a successor protected package and new commitment event with explicit supersedes lineage; neither package nor commitment is overwritten.",
    }


def verify_commitment(package_path: Path, nonce: bytes, evidence: Mapping[str, Any]) -> None:
    require(evidence.get("domain") == COMMITMENT_DOMAIN, "MODEL04_COMMITMENT_DOMAIN_MISMATCH", "PIPE commitment domain mismatch")
    expected = freeze_commitment(file_sha256(package_path), nonce)
    require(evidence.get("commitment_sha256") == expected, "MODEL04_COMMITMENT_MISMATCH", "protected package commitment does not verify")


def write_protected_materialization(
    protected_root: Path,
    repository_root: Path,
    package: Mapping[str, Any],
) -> tuple[Path, Path, dict[str, Any]]:
    protected_root = protected_root.resolve()
    repository_root = repository_root.resolve()
    try:
        protected_root.relative_to(repository_root)
    except ValueError:
        pass
    else:
        _fail("PROTECTED_ROOT_INSIDE_REPOSITORY", "MODEL-06 protected root must be outside Git")
    package_dir = protected_root / "materializations" / "model04-v1"
    package_path = package_dir / "model04_identity_role_anchor_package.json"
    nonce_path = package_dir / "commitment_nonce.bin"
    if package_dir.exists():
        require(package_path.is_file() and nonce_path.is_file(), "MODEL04_EXISTING_MATERIALIZATION_INCOMPLETE", "existing protected materialization is incomplete")
        existing = json.loads(package_path.read_text(encoding="utf-8"))
        require(existing == package, "MODEL04_EXISTING_MATERIALIZATION_CONFLICT", "existing protected package differs; correction/supersession is required")
        nonce = nonce_path.read_bytes()
    else:
        package_dir.mkdir(parents=True, exist_ok=False)
        write_json_exclusive(package_path, package)
        nonce = new_nonce()
        with nonce_path.open("xb") as handle:
            handle.write(nonce)
            handle.flush()
            os.fsync(handle.fileno())
    evidence = build_commitment_evidence(package_path, nonce)
    verify_commitment(package_path, nonce, evidence)
    return package_path, nonce_path, evidence


def write_repository_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = canonical_bytes(value).decode("utf-8") + "\n"
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        require(existing == value, "REPOSITORY_AUTHORITY_CONFLICT", f"existing authority differs: {path.name}")
    else:
        path.write_text(encoded, encoding="utf-8", newline="\n")
