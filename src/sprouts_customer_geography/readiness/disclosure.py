"""Fail-closed disclosure contract for the Development Readiness Mailbox.

The mailbox is deliberately code-valued.  It is not a general reporting
channel: adding a field or a value requires a versioned contract change.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from sprouts_customer_geography.pipe01.errors import ConformanceError, require
from sprouts_customer_geography.readiness.repository import INITIATIVE_FAMILIES


SCHEMA_VERSION = "1.0.0"
SNAPSHOT_ID = "development-readiness-v1"
SCHEMA_ID = "urn:sprouts-customer-geography:readiness:development-readiness:v1"
SCHEMA_CANONICAL_SHA256 = "69a95a6afe512cf77f310b0a12b4a85099a5699102b7fae18784ad0d69d2799f"

WORKTREE_STATES = (
    "CLEAN",
    "KNOWN_PRESERVED_WORK",
    "ATTENTION_NEEDED",
)
PUSH_STATES = (
    "SYNCHRONIZED",
    "UNPUSHED_SAFE_WORK",
    "UNKNOWN",
)
SAFE_WORK_STATES = (
    "UNCOMMITTED",
    "UNPUSHED",
    "UNCOMMITTED_AND_UNPUSHED",
    "PRESERVED",
)
PROJECT_PROFILE_STATES = (
    "READY",
    "STALE",
    "MISSING",
    "INVALID",
)
ASSET_CATALOG_STATES = (
    "READY",
    "STALE",
    "UNRESOLVED",
)
INVENTORY_STATES = (
    "READY",
    "INCOMPLETE",
    "UNRESOLVED",
)
REGISTRATION_STATES = (
    "REGISTERED_RECOVERABLE",
    "REGISTERED_UNRECOVERABLE",
    "UNREGISTERED",
    "NOT_VERIFIED",
)
PRESERVATION_STATES = (
    "PRESERVED",
    "ATTENTION_NEEDED",
    "NOT_VERIFIED",
)
RECOVERY_STATES = (
    "SUCCEEDED",
    "FAILED",
    "NOT_VERIFIED",
)
PREREQUISITE_CODES = (
    "REPOSITORY_READINESS",
    "PROTECTED_PROJECT_PROFILE",
    "PROTECTED_ASSET_CATALOG",
    "ORIGINAL_SOURCE_INVENTORY",
    "EVIDENCE_LEDGER",
    "MODEL13_AUTHORITY",
    "APP01_INPUT_PACKAGE",
    "MODEL14_PRESERVATION",
    "MODEL15_PRESERVATION",
    "FRESH_SESSION_RECOVERY",
)
PREREQUISITE_STATES = (
    "READY",
    "NEEDS_RUNWAY",
    "BLOCKED",
    "NOT_APPLICABLE",
)

TOP_LEVEL_FIELDS = frozenset(
    {
        "schema_version",
        "snapshot_id",
        "generated_at_utc",
        "repository",
        "protected_state",
        "preservation",
        "recovery",
        "prerequisites",
    }
)
REPOSITORY_FIELDS = frozenset(
    {"verified_commit", "worktree_state", "active_initiatives", "safe_work"}
)
ACTIVE_INITIATIVE_FIELDS = frozenset(
    {"initiative_id", "worktree_state", "push_state"}
)
SAFE_WORK_FIELDS = frozenset({"initiative_id", "state"})
PROTECTED_STATE_FIELDS = frozenset(
    {
        "project_profile",
        "asset_catalog",
        "original_source_inventory",
        "evidence_ledger",
        "model13_authority",
        "app01_inputs",
    }
)
PRESERVATION_FIELDS = frozenset({"model14", "model15"})
RECOVERY_FIELDS = frozenset({"fresh_session"})
PREREQUISITE_FIELDS = frozenset({"code", "status"})

COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
INITIATIVE_ID_PATTERN = (
    rf"^(?:{'|'.join(sorted(INITIATIVE_FAMILIES))})-[0-9]{{2,4}}[A-Z]?$"
)
INITIATIVE_ID_RE = re.compile(INITIATIVE_ID_PATTERN)
TIMESTAMP_RE = re.compile(
    r"^[0-9]{4}-(0[1-9]|1[0-2])-([0-2][0-9]|3[01])"
    r"T([01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]Z$"
)
TRAVERSAL_RE = re.compile(r"(?:^|[\\/])\.\.(?:[\\/]|$)|%2e", re.IGNORECASE)
FILE_URI_RE = re.compile(r"(?:^|\s)file:(?:/{0,3})", re.IGNORECASE)
ABSOLUTE_PATH_RE = re.compile(
    r"(?:^|[\s\"'(])(?:[a-z]:[\\/]|\\\\|//|/)", re.IGNORECASE
)
FILE_NAME_RE = re.compile(
    r"(?:^|[\\/\s])[^\\/\s]+\."
    r"(?:xlsx?|csv|tsv|json|geojson|ya?ml|sqlite3?|db|parquet|zip|log|txt|"
    r"pdf|docx?|pptx?)$",
    re.IGNORECASE,
)
COORDINATE_RE = re.compile(
    r"(?:\b(?:lat(?:itude)?|lon(?:gitude)?)\b|"
    r"\b(?:point|linestring|polygon)\s*\(|"
    r"(?<![\w.])[-+]?(?:\d{1,3}(?:\.\d+)?)[,;\s]+"
    r"[-+]?(?:\d{1,3}(?:\.\d+)?)(?![\w.]))",
    re.IGNORECASE,
)
TARGET_VALUE_RE = re.compile(
    r"\b(?:target(?:[_ -]?value)?|isolated[_ -]?sales|impacted[_ -]?sales|"
    r"sales|revenue|volume|forecast(?:ed)?[_ -]?value)\b",
    re.IGNORECASE,
)
ROW_IDENTITY_RE = re.compile(
    r"(?:\b(?:seed[_ -]?point[_ -]?id|source[_ -]?(?:row|observation)|"
    r"row[_ -]?(?:id|number)|lineage[_ -]?id|geoid)\b|"
    r"^m[0-9]+obs-[a-z0-9-]+$|^(?:row|record|observation|lineage)[_-]?[a-z0-9-]*[0-9]+$|"
    r"^[A-Z]{1,3}[1-9][0-9]{0,6}$|^[0-9]{11,15}$)",
    re.IGNORECASE,
)
DIGEST_RE = re.compile(r"(?<![0-9a-f])[0-9a-f]{32,128}(?![0-9a-f])", re.IGNORECASE)


class _DuplicateJsonKey(ValueError):
    pass


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    document: dict[str, Any] = {}
    for key, value in pairs:
        if key in document:
            raise _DuplicateJsonKey
        document[key] = value
    return document


def load_json_safely(path: Path, *, error_code: str) -> Any:
    """Load JSON while rejecting duplicate keys without echoing paths or values."""

    try:
        return json.loads(
            Path(path).read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_json_keys,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, _DuplicateJsonKey) as exc:
        raise ConformanceError(
            error_code,
            "JSON artifact is unreadable or contains ambiguous duplicate object keys",
        ) from exc


def _keys(value: Mapping[Any, Any]) -> set[Any]:
    return set(value.keys())


def _require_object(value: Any, location: str) -> Mapping[str, Any]:
    require(
        isinstance(value, Mapping),
        "READINESS_OBJECT_REQUIRED",
        f"{location} must be a JSON object",
    )
    return value


def _require_exact_fields(
    value: Any,
    expected: frozenset[str],
    location: str,
) -> Mapping[str, Any]:
    document = _require_object(value, location)
    actual = _keys(document)
    require(
        expected <= actual,
        "READINESS_REQUIRED_FIELD_MISSING",
        f"{location} is missing a required field",
    )
    require(
        actual <= expected,
        "READINESS_FIELD_PROHIBITED",
        f"{location} contains a field outside the disclosure allowlist",
    )
    return document


def _require_array(value: Any, location: str, maximum: int) -> list[Any]:
    require(
        isinstance(value, list),
        "READINESS_ARRAY_REQUIRED",
        f"{location} must be a JSON array",
    )
    require(
        len(value) <= maximum,
        "READINESS_ARRAY_LIMIT_EXCEEDED",
        f"{location} exceeds its disclosure-safe item limit",
    )
    return value


def _require_enum(value: Any, allowed: tuple[str, ...], location: str) -> None:
    require(
        isinstance(value, str) and value in allowed,
        "READINESS_VALUE_NOT_ALLOWLISTED",
        f"{location} is not an allowlisted code",
    )


def _reject_string_disclosure(value: str, location: str) -> None:
    if location == "repository.verified_commit":
        return
    require(
        TRAVERSAL_RE.search(value) is None,
        "READINESS_PATH_TRAVERSAL_REJECTED",
        f"path traversal is prohibited at {location}",
    )
    require(
        FILE_URI_RE.search(value) is None,
        "READINESS_FILE_URI_REJECTED",
        f"file URIs are prohibited at {location}",
    )
    require(
        ABSOLUTE_PATH_RE.search(value) is None,
        "READINESS_ABSOLUTE_PATH_REJECTED",
        f"absolute and UNC paths are prohibited at {location}",
    )
    require(
        "\\" not in value and "/" not in value and FILE_NAME_RE.search(value) is None,
        "READINESS_FILE_PATH_REJECTED",
        f"file and directory paths are prohibited at {location}",
    )
    require(
        COORDINATE_RE.search(value) is None,
        "READINESS_COORDINATE_REJECTED",
        f"coordinate-like values are prohibited at {location}",
    )
    require(
        TARGET_VALUE_RE.search(value) is None,
        "READINESS_TARGET_VALUE_REJECTED",
        f"target-like values are prohibited at {location}",
    )
    require(
        ROW_IDENTITY_RE.search(value) is None,
        "READINESS_ROW_IDENTITY_REJECTED",
        f"row-level identities are prohibited at {location}",
    )
    require(
        DIGEST_RE.search(value) is None,
        "READINESS_DIGEST_REJECTED",
        f"digest-like values are prohibited at {location}",
    )


def _reject_disclosure_classes(value: Any, location: str = "document") -> None:
    if isinstance(value, Mapping):
        for key, member in value.items():
            _reject_disclosure_classes(member, str(key) if location == "document" else f"{location}.{key}")
        return
    if isinstance(value, list):
        for index, member in enumerate(value):
            _reject_disclosure_classes(member, f"{location}[{index}]")
        return
    require(
        not isinstance(value, (bool, int, float)),
        "READINESS_NUMBER_REJECTED",
        f"numeric and boolean values are prohibited at {location}",
    )
    require(
        isinstance(value, str),
        "READINESS_SCALAR_TYPE_REJECTED",
        f"{location} must use an allowlisted string code",
    )
    _reject_string_disclosure(value, location)


def _validate_timestamp(value: Any) -> None:
    require(
        isinstance(value, str) and TIMESTAMP_RE.fullmatch(value) is not None,
        "READINESS_TIMESTAMP_INVALID",
        "generated_at_utc must be a second-precision UTC timestamp",
    )
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise ConformanceError(
            "READINESS_TIMESTAMP_INVALID",
            "generated_at_utc is not a valid calendar timestamp",
        ) from exc


def _validate_shape(document: Mapping[str, Any]) -> None:
    repository = _require_exact_fields(
        document["repository"], REPOSITORY_FIELDS, "repository"
    )
    active = _require_array(
        repository["active_initiatives"], "repository.active_initiatives", 64
    )
    for index, entry in enumerate(active):
        _require_exact_fields(
            entry,
            ACTIVE_INITIATIVE_FIELDS,
            f"repository.active_initiatives[{index}]",
        )
    safe_work = _require_array(repository["safe_work"], "repository.safe_work", 64)
    for index, entry in enumerate(safe_work):
        _require_exact_fields(
            entry, SAFE_WORK_FIELDS, f"repository.safe_work[{index}]"
        )
    _require_exact_fields(
        document["protected_state"], PROTECTED_STATE_FIELDS, "protected_state"
    )
    _require_exact_fields(
        document["preservation"], PRESERVATION_FIELDS, "preservation"
    )
    _require_exact_fields(document["recovery"], RECOVERY_FIELDS, "recovery")
    prerequisites = _require_array(document["prerequisites"], "prerequisites", 10)
    for index, entry in enumerate(prerequisites):
        _require_exact_fields(
            entry, PREREQUISITE_FIELDS, f"prerequisites[{index}]"
        )


_SUPPORTED_SCHEMA_KEYWORDS = frozenset(
    {
        "$defs",
        "$id",
        "$ref",
        "$schema",
        "additionalProperties",
        "const",
        "description",
        "enum",
        "items",
        "maxItems",
        "minItems",
        "pattern",
        "properties",
        "required",
        "title",
        "type",
        "uniqueItems",
    }
)


def _schema_failure(message: str) -> None:
    raise ConformanceError("READINESS_SCHEMA_INVALID", message)


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise ConformanceError(
            "READINESS_SCHEMA_INVALID", "schema is not a canonical JSON value"
        ) from exc


def _resolve_schema_ref(root: Mapping[str, Any], reference: Any) -> Mapping[str, Any]:
    if not isinstance(reference, str) or not reference.startswith("#/"):
        _schema_failure("schema contains an unsupported reference")
    current: Any = root
    for raw_part in reference[2:].split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if not isinstance(current, Mapping) or part not in current:
            _schema_failure("schema contains an unresolved reference")
        current = current[part]
    if not isinstance(current, Mapping):
        _schema_failure("schema reference does not resolve to an object")
    return current


def _validate_schema_node(
    node: Any,
    root: Mapping[str, Any],
    location: str,
) -> None:
    if not isinstance(node, Mapping):
        _schema_failure(f"{location} must be a schema object")
    unknown = set(node) - _SUPPORTED_SCHEMA_KEYWORDS
    if unknown:
        _schema_failure(f"{location} contains an unsupported schema keyword")
    if "$ref" in node:
        if set(node) != {"$ref"}:
            _schema_failure(f"{location} combines a reference with unsupported siblings")
        _resolve_schema_ref(root, node["$ref"])
        return

    declared_type = node.get("type")
    if declared_type is not None and declared_type not in {"object", "array", "string"}:
        _schema_failure(f"{location} uses an unsupported JSON type")
    if "pattern" in node:
        if not isinstance(node["pattern"], str):
            _schema_failure(f"{location}.pattern must be a string")
        try:
            re.compile(node["pattern"])
        except re.error as exc:
            raise ConformanceError(
                "READINESS_SCHEMA_INVALID", f"{location}.pattern is invalid"
            ) from exc
    if "enum" in node:
        values = node["enum"]
        if not isinstance(values, list) or not values:
            _schema_failure(f"{location}.enum must be a non-empty array")
        rendered = [_canonical_json(value) for value in values]
        if len(rendered) != len(set(rendered)):
            _schema_failure(f"{location}.enum contains duplicate values")

    if declared_type == "object":
        properties = node.get("properties")
        required = node.get("required")
        if not isinstance(properties, Mapping) or not isinstance(required, list):
            _schema_failure(f"{location} lacks a closed object contract")
        if node.get("additionalProperties") is not False:
            _schema_failure(f"{location} permits unspecified object fields")
        if not all(isinstance(item, str) for item in required):
            _schema_failure(f"{location}.required contains a non-string field")
        if len(required) != len(set(required)) or not set(required) <= set(properties):
            _schema_failure(f"{location}.required differs from its properties")
        for name, child in properties.items():
            if not isinstance(name, str):
                _schema_failure(f"{location}.properties contains a non-string field")
            _validate_schema_node(child, root, f"{location}.properties.{name}")
    elif any(key in node for key in ("properties", "required", "additionalProperties")):
        _schema_failure(f"{location} uses object keywords without object type")

    if declared_type == "array":
        if "items" not in node:
            _schema_failure(f"{location} lacks an item contract")
        maximum = node.get("maxItems")
        if not isinstance(maximum, int) or isinstance(maximum, bool) or maximum < 0:
            _schema_failure(f"{location}.maxItems is invalid")
        minimum = node.get("minItems", 0)
        if (
            not isinstance(minimum, int)
            or isinstance(minimum, bool)
            or minimum < 0
            or minimum > maximum
        ):
            _schema_failure(f"{location}.minItems is invalid")
        if node.get("uniqueItems") is not True:
            _schema_failure(f"{location} must require unique items")
        _validate_schema_node(node["items"], root, f"{location}.items")
    elif any(key in node for key in ("items", "maxItems", "minItems", "uniqueItems")):
        _schema_failure(f"{location} uses array keywords without array type")

    definitions = node.get("$defs")
    if definitions is not None:
        if not isinstance(definitions, Mapping):
            _schema_failure(f"{location}.$defs must be an object")
        for name, child in definitions.items():
            if not isinstance(name, str):
                _schema_failure(f"{location}.$defs contains a non-string name")
            _validate_schema_node(child, root, f"{location}.$defs.{name}")


def _schema_document_failure(location: str) -> None:
    raise ConformanceError(
        "READINESS_SCHEMA_DOCUMENT_MISMATCH",
        f"mailbox document does not satisfy the checked-in schema at {location}",
    )


def _validate_schema_instance(
    value: Any,
    node: Mapping[str, Any],
    root: Mapping[str, Any],
    location: str = "document",
) -> None:
    if "$ref" in node:
        _validate_schema_instance(value, _resolve_schema_ref(root, node["$ref"]), root, location)
        return
    declared_type = node.get("type")
    if declared_type == "object" and not isinstance(value, Mapping):
        _schema_document_failure(location)
    if declared_type == "array" and not isinstance(value, list):
        _schema_document_failure(location)
    if declared_type == "string" and not isinstance(value, str):
        _schema_document_failure(location)
    if "const" in node and value != node["const"]:
        _schema_document_failure(location)
    if "enum" in node and value not in node["enum"]:
        _schema_document_failure(location)
    if "pattern" in node and (
        not isinstance(value, str) or re.search(node["pattern"], value) is None
    ):
        _schema_document_failure(location)

    if declared_type == "object":
        properties = node["properties"]
        required = set(node["required"])
        if not required <= set(value):
            _schema_document_failure(location)
        if node.get("additionalProperties") is False and not set(value) <= set(properties):
            _schema_document_failure(location)
        for name, child in properties.items():
            if name in value:
                _validate_schema_instance(value[name], child, root, f"{location}.{name}")
    if declared_type == "array":
        if len(value) < node.get("minItems", 0):
            _schema_document_failure(location)
        if len(value) > node["maxItems"]:
            _schema_document_failure(location)
        rendered = [_canonical_json(item) for item in value]
        if node.get("uniqueItems") is True and len(rendered) != len(set(rendered)):
            _schema_document_failure(location)
        for index, item in enumerate(value):
            _validate_schema_instance(item, node["items"], root, f"{location}[{index}]")


def _expected_prerequisites(document: Mapping[str, Any]) -> dict[str, str]:
    repository = document["repository"]
    protected = document["protected_state"]
    preservation = document["preservation"]
    recovery = document["recovery"]
    return {
        "REPOSITORY_READINESS": (
            "READY"
            if repository["worktree_state"] != "ATTENTION_NEEDED"
            else "NEEDS_RUNWAY"
        ),
        "PROTECTED_PROJECT_PROFILE": (
            "READY" if protected["project_profile"] == "READY" else "NEEDS_RUNWAY"
        ),
        "PROTECTED_ASSET_CATALOG": (
            "READY" if protected["asset_catalog"] == "READY" else "NEEDS_RUNWAY"
        ),
        "ORIGINAL_SOURCE_INVENTORY": (
            "READY"
            if protected["original_source_inventory"] == "READY"
            else "NEEDS_RUNWAY"
        ),
        "EVIDENCE_LEDGER": (
            "READY" if protected["evidence_ledger"] == "READY" else "NEEDS_RUNWAY"
        ),
        "MODEL13_AUTHORITY": (
            "READY"
            if protected["model13_authority"] == "REGISTERED_RECOVERABLE"
            else "NEEDS_RUNWAY"
        ),
        "APP01_INPUT_PACKAGE": (
            "READY"
            if protected["app01_inputs"] == "REGISTERED_RECOVERABLE"
            else "NEEDS_RUNWAY"
        ),
        "MODEL14_PRESERVATION": (
            "READY" if preservation["model14"] == "PRESERVED" else "NEEDS_RUNWAY"
        ),
        "MODEL15_PRESERVATION": (
            "READY" if preservation["model15"] == "PRESERVED" else "NEEDS_RUNWAY"
        ),
        "FRESH_SESSION_RECOVERY": (
            "READY" if recovery["fresh_session"] == "SUCCEEDED" else "NEEDS_RUNWAY"
        ),
    }


def _validate_cross_field_consistency(document: Mapping[str, Any]) -> None:
    repository = document["repository"]
    active = {entry["initiative_id"]: entry for entry in repository["active_initiatives"]}
    safe = {entry["initiative_id"]: entry["state"] for entry in repository["safe_work"]}

    expected_safe: dict[str, str] = {}
    for initiative_id, entry in active.items():
        uncommitted = entry["worktree_state"] != "CLEAN"
        unpushed = entry["push_state"] == "UNPUSHED_SAFE_WORK"
        if uncommitted and unpushed:
            expected_safe[initiative_id] = "UNCOMMITTED_AND_UNPUSHED"
        elif uncommitted:
            expected_safe[initiative_id] = "UNCOMMITTED"
        elif unpushed:
            expected_safe[initiative_id] = "UNPUSHED"
    require(
        set(safe) == set(expected_safe),
        "READINESS_SAFE_WORK_SET_MISMATCH",
        "safe_work does not exactly represent active repository work",
    )
    require(
        safe == expected_safe,
        "READINESS_SAFE_WORK_STATE_MISMATCH",
        "safe_work state contradicts its active initiative state",
    )

    preservation = document["preservation"]
    for initiative_id, field in (("MODEL-14", "model14"), ("MODEL-15", "model15")):
        entry = active.get(initiative_id)
        if entry is None or entry["worktree_state"] == "CLEAN":
            continue
        expected_state = (
            "KNOWN_PRESERVED_WORK"
            if preservation[field] == "PRESERVED"
            else "ATTENTION_NEEDED"
        )
        require(
            entry["worktree_state"] == expected_state,
            "READINESS_PRESERVATION_STATE_CONTRADICTION",
            "initiative worktree state contradicts its preservation state",
        )

    overall = repository["worktree_state"]
    visible_attention = any(
        entry["worktree_state"] == "ATTENTION_NEEDED" for entry in active.values()
    )
    unknown_push = any(entry["push_state"] == "UNKNOWN" for entry in active.values())
    preserved_ids = {
        initiative_id
        for initiative_id, field in (("MODEL-14", "model14"), ("MODEL-15", "model15"))
        if preservation[field] == "PRESERVED"
    }
    all_visible_work_preserved = bool(expected_safe) and all(
        active[initiative_id]["worktree_state"] == "KNOWN_PRESERVED_WORK"
        or (
            active[initiative_id]["worktree_state"] == "CLEAN"
            and initiative_id in preserved_ids
        )
        for initiative_id in expected_safe
    )
    if overall == "CLEAN":
        require(
            not expected_safe and not visible_attention and not unknown_push,
            "READINESS_REPOSITORY_STATE_CONTRADICTION",
            "clean repository state contradicts active work or unresolved push state",
        )
    elif overall == "KNOWN_PRESERVED_WORK":
        require(
            all_visible_work_preserved and not visible_attention and not unknown_push,
            "READINESS_REPOSITORY_STATE_CONTRADICTION",
            "known-preserved repository state lacks consistently preserved active work",
        )
    else:
        # ATTENTION_NEEDED may also summarize a deliberately hidden untrusted task ref.
        require(
            overall == "ATTENTION_NEEDED",
            "READINESS_REPOSITORY_STATE_CONTRADICTION",
            "repository state is not an allowlisted aggregate",
        )

    prerequisites = document["prerequisites"]
    codes = tuple(entry["code"] for entry in prerequisites)
    require(
        codes == PREREQUISITE_CODES,
        "READINESS_PREREQUISITE_SET_INVALID",
        "all prerequisite codes must appear exactly once in canonical order",
    )
    expected_prerequisites = _expected_prerequisites(document)
    require(
        all(
            entry["status"] == expected_prerequisites[entry["code"]]
            for entry in prerequisites
        ),
        "READINESS_PREREQUISITE_STATUS_MISMATCH",
        "prerequisite status does not match its source readiness state",
    )


def validate_development_readiness(
    document: Mapping[str, Any],
    *,
    schema: Mapping[str, Any] | None = None,
) -> Mapping[str, Any]:
    """Validate one mailbox snapshot against the closed disclosure contract."""

    if schema is not None:
        validate_development_readiness_schema(schema)
        _validate_schema_instance(document, schema, schema)
    normalized = _require_exact_fields(document, TOP_LEVEL_FIELDS, "document")
    _validate_shape(normalized)
    _reject_disclosure_classes(normalized)

    require(
        normalized["schema_version"] == SCHEMA_VERSION,
        "READINESS_SCHEMA_VERSION_INVALID",
        "schema_version differs from the supported disclosure contract",
    )
    require(
        normalized["snapshot_id"] == SNAPSHOT_ID,
        "READINESS_SNAPSHOT_ID_INVALID",
        "snapshot_id differs from the standing mailbox identity",
    )
    _validate_timestamp(normalized["generated_at_utc"])

    repository = normalized["repository"]
    commit = repository["verified_commit"]
    require(
        isinstance(commit, str) and COMMIT_RE.fullmatch(commit) is not None,
        "READINESS_COMMIT_INVALID",
        "verified_commit must be an exact lowercase 40-hex repository commit",
    )
    _require_enum(repository["worktree_state"], WORKTREE_STATES, "repository.worktree_state")

    active_ids: set[str] = set()
    for index, entry in enumerate(repository["active_initiatives"]):
        initiative_id = entry["initiative_id"]
        require(
            isinstance(initiative_id, str)
            and INITIATIVE_ID_RE.fullmatch(initiative_id) is not None,
            "READINESS_INITIATIVE_ID_INVALID",
            "initiative_id must be a repository-safe task or initiative identifier",
        )
        require(
            initiative_id not in active_ids,
            "READINESS_DUPLICATE_INITIATIVE",
            "active initiatives must be unique by identifier",
        )
        active_ids.add(initiative_id)
        _require_enum(
            entry["worktree_state"],
            WORKTREE_STATES,
            f"repository.active_initiatives[{index}].worktree_state",
        )
        _require_enum(
            entry["push_state"],
            PUSH_STATES,
            f"repository.active_initiatives[{index}].push_state",
        )

    safe_ids: set[str] = set()
    for index, entry in enumerate(repository["safe_work"]):
        initiative_id = entry["initiative_id"]
        require(
            isinstance(initiative_id, str)
            and INITIATIVE_ID_RE.fullmatch(initiative_id) is not None,
            "READINESS_INITIATIVE_ID_INVALID",
            "safe work must use a repository-safe task or initiative identifier",
        )
        require(
            initiative_id in active_ids,
            "READINESS_SAFE_WORK_ORPHANED",
            "safe work must refer to an active initiative identifier",
        )
        require(
            initiative_id not in safe_ids,
            "READINESS_DUPLICATE_SAFE_WORK",
            "safe work entries must be unique by identifier",
        )
        safe_ids.add(initiative_id)
        _require_enum(
            entry["state"],
            SAFE_WORK_STATES,
            f"repository.safe_work[{index}].state",
        )

    protected_state = normalized["protected_state"]
    _require_enum(
        protected_state["project_profile"],
        PROJECT_PROFILE_STATES,
        "protected_state.project_profile",
    )
    _require_enum(
        protected_state["asset_catalog"],
        ASSET_CATALOG_STATES,
        "protected_state.asset_catalog",
    )
    _require_enum(
        protected_state["original_source_inventory"],
        INVENTORY_STATES,
        "protected_state.original_source_inventory",
    )
    _require_enum(
        protected_state["evidence_ledger"],
        INVENTORY_STATES,
        "protected_state.evidence_ledger",
    )
    _require_enum(
        protected_state["model13_authority"],
        REGISTRATION_STATES,
        "protected_state.model13_authority",
    )
    _require_enum(
        protected_state["app01_inputs"],
        REGISTRATION_STATES,
        "protected_state.app01_inputs",
    )

    preservation = normalized["preservation"]
    _require_enum(preservation["model14"], PRESERVATION_STATES, "preservation.model14")
    _require_enum(preservation["model15"], PRESERVATION_STATES, "preservation.model15")
    _require_enum(
        normalized["recovery"]["fresh_session"],
        RECOVERY_STATES,
        "recovery.fresh_session",
    )

    prerequisite_codes: set[str] = set()
    for index, entry in enumerate(normalized["prerequisites"]):
        _require_enum(
            entry["code"], PREREQUISITE_CODES, f"prerequisites[{index}].code"
        )
        _require_enum(
            entry["status"],
            PREREQUISITE_STATES,
            f"prerequisites[{index}].status",
        )
        require(
            entry["code"] not in prerequisite_codes,
            "READINESS_DUPLICATE_PREREQUISITE",
            "prerequisite codes must be unique",
        )
        prerequisite_codes.add(entry["code"])
    _validate_cross_field_consistency(normalized)
    return normalized


def validate_development_readiness_schema(schema: Mapping[str, Any]) -> None:
    """Reject any schema artifact that differs from the checked-in v1 contract."""

    candidate = _require_object(schema, "schema")
    require(
        candidate.get("$schema") == "https://json-schema.org/draft/2020-12/schema",
        "READINESS_SCHEMA_INVALID",
        "schema must declare JSON Schema 2020-12",
    )
    require(
        candidate.get("$id") == SCHEMA_ID,
        "READINESS_SCHEMA_INVALID",
        "schema identity differs from the v1 disclosure contract",
    )
    _validate_schema_node(candidate, candidate, "schema")
    digest = hashlib.sha256(_canonical_json(candidate).encode("utf-8")).hexdigest()
    require(
        digest == SCHEMA_CANONICAL_SHA256,
        "READINESS_SCHEMA_INVALID",
        "schema differs from the checked-in v1 disclosure contract",
    )


def load_and_validate_development_readiness(
    document_path: Path,
    schema_path: Path | None = None,
) -> Mapping[str, Any]:
    """Load a JSON mailbox snapshot and optionally bind it to the schema artifact."""

    document = load_json_safely(
        document_path, error_code="READINESS_DOCUMENT_UNREADABLE"
    )
    schema: Mapping[str, Any] | None = None
    if schema_path is not None:
        schema = load_json_safely(
            schema_path, error_code="READINESS_SCHEMA_UNREADABLE"
        )
    return validate_development_readiness(document, schema=schema)
