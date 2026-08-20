"""Repository-safe governance manifest validation for authorized tasks."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .pipe01.errors import ConformanceError, require


TASK_ID_RE = re.compile(
    r"^(?:GOV|DATA|MODEL|GEO|BI|PIPE|STORE|MARKETS|INTEGRATION|DEPLOY|VALIDATE)-[0-9]{2}[A-Z]?$"
)
BRANCH_RE = re.compile(r"^task/[a-z]+-[0-9]{2}[a-z]?(?:-[a-z0-9]+)+$")
COMMIT_RE = re.compile(r"^(?:GOV|DATA|MODEL|GEO|BI|PIPE|STORE|MARKETS|INTEGRATION|DEPLOY|VALIDATE)-[0-9]{2}[A-Z]?: [a-z].+$")
PR_TITLE_RE = re.compile(r"^(?:GOV|DATA|MODEL|GEO|BI|PIPE|STORE|MARKETS|INTEGRATION|DEPLOY|VALIDATE)-[0-9]{2}[A-Z]?: \S.*$")
LOGICAL_ARTIFACT_RE = re.compile(r"^[A-Z]+[0-9]{2}[A-Z]?_[A-Z0-9_]+_V[1-9][0-9]*$")
PROTECTED_LOGICAL_ID_RE = re.compile(r"^PROTECTED_[A-Z0-9_]+(?:_V[1-9][0-9]*)?$")
ABSOLUTE_PATH_RE = re.compile(r"^(?:[A-Za-z]:[\\/]|\\\\|/|~[\\/])")
SHA256_RE = re.compile(r"\b[a-fA-F0-9]{64}\b")
COORDINATE_PAIR_RE = re.compile(r"\b-?[0-9]{1,3}\.[0-9]{4,}\s*,\s*-?[0-9]{1,3}\.[0-9]{4,}\b")

TASK_STATES = (
    "AUTHORIZED",
    "IN_PROGRESS",
    "BLOCKED_FAIL_CLOSED",
    "COMPLETED_AWAITING_ACCEPTANCE",
    "ACCEPTED_CLOSED",
    "REJECTED_OR_REWORK_REQUIRED",
)
EVIDENCE_TYPES = {"LOCAL_COMMIT", "TEST_PASS", "COMPLETION_REPORT", "FUTURE_PULL_REQUEST", "FUTURE_MERGE"}
PROHIBITED_FIELD_TERMS = {
    "absolute_path",
    "path",
    "coordinate",
    "coordinates",
    "latitude",
    "longitude",
    "nonce",
    "digest",
    "target_cell_address",
    "cell_address",
    "protected_registry",
    "protected_lineage",
    "protected_package",
    "target_value",
    "forecast_value",
}
MANIFEST_FIELDS = {
    "task_id", "title", "capability_owner", "authority_source", "state", "scope", "exclusions",
    "accepted_input_artifacts", "protected_dependency_logical_ids", "implementation_branch",
    "implementation_commit", "completion_state", "acceptance_destination", "acceptance_disposition",
    "acceptance_metadata", "exact_next_destination",
}


def task_id_is_valid(task_id: str) -> bool:
    return isinstance(task_id, str) and bool(TASK_ID_RE.fullmatch(task_id))


def branch_name_is_valid(branch: str, task_id: str | None = None) -> bool:
    if not isinstance(branch, str) or not BRANCH_RE.fullmatch(branch):
        return False
    return task_id is None or branch.startswith(f"task/{task_id.lower()}-")


def task_commit_message_is_valid(message: str, task_id: str | None = None) -> bool:
    if not isinstance(message, str) or not COMMIT_RE.fullmatch(message):
        return False
    return task_id is None or message.startswith(f"{task_id}: ")


def future_pr_title_is_valid(title: str, task_id: str | None = None) -> bool:
    if not isinstance(title, str) or not PR_TITLE_RE.fullmatch(title):
        return False
    return task_id is None or title.startswith(f"{task_id}: ")


def _require_string_list(document: Mapping[str, Any], field: str, pattern: re.Pattern[str] | None = None) -> None:
    value = document[field]
    require(isinstance(value, list) and all(isinstance(item, str) and item for item in value), "TASK_MANIFEST_FIELD_INVALID", f"{field} must be a non-empty-string array")
    if pattern is not None:
        require(all(pattern.fullmatch(item) for item in value), "TASK_MANIFEST_LOGICAL_ID_INVALID", f"{field} contains an invalid logical ID")


def _reject_protected_content(value: Any, location: str = "manifest") -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            require(str(key).lower() not in PROHIBITED_FIELD_TERMS, "TASK_MANIFEST_PROTECTED_FIELD_REJECTED", f"protected field is prohibited at {location}.{key}")
            _reject_protected_content(nested, f"{location}.{key}")
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _reject_protected_content(nested, f"{location}[{index}]")
    elif isinstance(value, str):
        require(not ABSOLUTE_PATH_RE.match(value), "TASK_MANIFEST_ABSOLUTE_PATH_REJECTED", f"absolute path is prohibited at {location}")
        require(not SHA256_RE.search(value), "TASK_MANIFEST_PROTECTED_DIGEST_REJECTED", f"digest-like value is prohibited at {location}")
        require(not COORDINATE_PAIR_RE.search(value), "TASK_MANIFEST_COORDINATE_REJECTED", f"coordinate-like value is prohibited at {location}")


def validate_task_manifest(document: Mapping[str, Any], schema: Mapping[str, Any] | None = None) -> None:
    """Validate a repository-safe manifest and fail closed on protected content."""
    require(isinstance(document, Mapping), "TASK_MANIFEST_INVALID", "task manifest must be a JSON object")
    if schema is not None:
        require(schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema", "TASK_MANIFEST_SCHEMA_INVALID", "schema must declare JSON Schema 2020-12")
        require(tuple(schema["properties"]["state"]["enum"]) == TASK_STATES, "TASK_MANIFEST_SCHEMA_STATE_MISMATCH", "schema state enum differs from the governance contract")
        required = set(schema["required"])
        permitted = set(schema["properties"])
        require(required <= set(document), "TASK_MANIFEST_REQUIRED_FIELD_MISSING", "required manifest field is missing")
        require(set(document) <= permitted, "TASK_MANIFEST_FIELD_PROHIBITED", "manifest contains a field outside the stable schema")

    required_fields = {
        "task_id", "title", "capability_owner", "authority_source", "state", "scope", "exclusions",
        "accepted_input_artifacts", "protected_dependency_logical_ids", "implementation_branch",
        "completion_state", "acceptance_destination", "exact_next_destination",
    }
    require(required_fields <= set(document), "TASK_MANIFEST_REQUIRED_FIELD_MISSING", "required manifest field is missing")
    require(set(document) <= MANIFEST_FIELDS, "TASK_MANIFEST_FIELD_PROHIBITED", "manifest contains a field outside the stable schema")
    require(task_id_is_valid(document["task_id"]), "TASK_ID_INVALID", "task_id must use an approved prefix and immutable ID format")
    require(document["state"] in TASK_STATES, "TASK_STATE_INVALID", "state is not accepted by the governance contract")
    for field in ("title", "capability_owner", "authority_source", "acceptance_destination", "exact_next_destination"):
        require(isinstance(document[field], str) and bool(document[field]), "TASK_MANIFEST_FIELD_INVALID", f"{field} must be a non-empty string")
    _require_string_list(document, "scope")
    _require_string_list(document, "exclusions")
    _require_string_list(document, "accepted_input_artifacts", LOGICAL_ARTIFACT_RE)
    _require_string_list(document, "protected_dependency_logical_ids", PROTECTED_LOGICAL_ID_RE)
    require(branch_name_is_valid(document["implementation_branch"], document["task_id"]), "TASK_BRANCH_INVALID", "implementation_branch must be the task branch for task_id")
    if "implementation_commit" in document:
        require(isinstance(document["implementation_commit"], str) and re.fullmatch(r"[0-9a-f]{7,64}", document["implementation_commit"]), "TASK_COMMIT_INVALID", "implementation_commit must be a lowercase Git object ID")

    completion = document["completion_state"]
    require(isinstance(completion, Mapping) and set(completion) == {"execution", "implementation_evidence", "capability_acceptance"}, "TASK_COMPLETION_STATE_INVALID", "completion_state must contain only the stable completion fields")
    require(completion["execution"] in {"NOT_STARTED", "IN_PROGRESS", "BLOCKED", "COMPLETED"}, "TASK_COMPLETION_EXECUTION_INVALID", "execution completion state is invalid")
    require(isinstance(completion["implementation_evidence"], list) and all(isinstance(item, str) for item in completion["implementation_evidence"]) and set(completion["implementation_evidence"]) <= EVIDENCE_TYPES, "TASK_EVIDENCE_INVALID", "implementation evidence is invalid")
    require(completion["capability_acceptance"] in {"NOT_REVIEWED", "ACCEPTED", "REJECTED_OR_REWORK_REQUIRED"}, "TASK_ACCEPTANCE_STATE_INVALID", "capability acceptance state is invalid")

    if "acceptance_disposition" in document:
        require(document["acceptance_disposition"] in {"ACCEPTED", "REJECTED_OR_REWORK_REQUIRED"}, "TASK_ACCEPTANCE_DISPOSITION_INVALID", "acceptance disposition is invalid")
    if "acceptance_metadata" in document:
        metadata = document["acceptance_metadata"]
        require(isinstance(metadata, Mapping) and set(metadata) == {"capability_owner", "recorded_by", "recorded_on"}, "TASK_ACCEPTANCE_METADATA_INVALID", "acceptance metadata must use only stable disclosure-safe fields")
        require(all(isinstance(metadata[key], str) and metadata[key] for key in metadata), "TASK_ACCEPTANCE_METADATA_INVALID", "acceptance metadata values must be non-empty strings")
        require(bool(re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", metadata["recorded_on"])), "TASK_ACCEPTANCE_METADATA_INVALID", "acceptance metadata date must be ISO-like")

    if document["state"] == "COMPLETED_AWAITING_ACCEPTANCE":
        require(completion["execution"] == "COMPLETED" and completion["capability_acceptance"] == "NOT_REVIEWED", "TASK_COMPLETION_ACCEPTANCE_MISMATCH", "completed work must await separate capability acceptance")
    if document["state"] == "ACCEPTED_CLOSED":
        metadata = document.get("acceptance_metadata")
        require(document.get("acceptance_disposition") == "ACCEPTED" and completion["capability_acceptance"] == "ACCEPTED" and isinstance(metadata, Mapping), "TASK_ACCEPTANCE_METADATA_REQUIRED", "ACCEPTED_CLOSED requires explicit capability acceptance metadata")
    _reject_protected_content(document)


def load_and_validate_task_manifest(manifest_path: Path, schema_path: Path) -> Mapping[str, Any]:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    validate_task_manifest(document, schema)
    return document


def validate_task_retry(previous: Mapping[str, Any], correction: Mapping[str, Any]) -> None:
    """Allow bounded rework under an immutable task ID; reject identity substitution."""
    require(previous["task_id"] == correction["task_id"], "TASK_ID_MUTATION_REJECTED", "corrections and retries must retain the authorized task ID")
    validate_task_manifest(previous)
    validate_task_manifest(correction)
