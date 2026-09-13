"""Protected MODEL-16 registration, exact membership, and one-use journal.

Nothing in this module reads a workbook or searches a protected directory.
All returned paths, identifiers, digests, journal contents, and sidecars remain
protected-local. Public callers must publish separately allowlisted aggregates.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
from typing import Any, Iterator, Mapping, Sequence
import uuid

from sprouts_customer_geography.pipe01.errors import ConformanceError, require
from sprouts_customer_geography.readiness.store import ProjectState, utc_now


SOURCE_IDS = frozenset({
    "MI_SEED_FORECASTS_2024_2026_V1", "WI_SEED_FORECASTS_2024_2026_V1",
    "MI_WI_PURSUED_SITES_2025_ISOLATED_V1",
})
OUTPUT_ID = "MODEL16_OUTPUT_PACKAGE"
HOLDOUT_STAGES = frozenset({"seed_2026", "pursued"})
_ROLES = frozenset({"development", "temporal_test", "pursued_test", "excluded", "unresolved"})
_USAGE_ROLES = frozenset({"development", "temporal_test", "pursued_test", "excluded", "not_used"})
_HEX = re.compile(r"^[0-9a-f]{64}$")


def _json(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False, ensure_ascii=False)
    except (ValueError, TypeError) as exc:
        raise ConformanceError("MODEL16_PRIVATE_JSON_INVALID", "protected metadata must be finite JSON") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _within(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _id(kind: str, value: Any) -> str:
    return "MODEL16_" + kind + "_" + _digest(value).upper()


def register_assets(
    store: ProjectState,
    bounded_input_dir: Path,
    filenames: Mapping[str, str],
    output_dir: Path,
    *,
    repository_root: Path,
) -> dict[str, Path]:
    """Register exactly three originals in place, plus a separate output root.

    The caller supplies the user-authorized input directory and exact basename
    mapping. The shared protected root is the input directory's parent. This
    function neither enumerates siblings nor copies, hashes, or opens a source.
    """
    require(set(filenames) == SOURCE_IDS, "MODEL16_SOURCE_SET_INVALID", "the exact three authorized source registrations are required")
    source_raw, output_raw = Path(bounded_input_dir), Path(output_dir)
    require(source_raw.is_absolute() and output_raw.is_absolute(), "MODEL16_REGISTRATION_PATH_INVALID", "bounded registration requires absolute local directories")
    require(not source_raw.is_symlink() and not output_raw.is_symlink(), "MODEL16_REGISTRATION_SYMLINK_REJECTED", "registered directories may not be symbolic links")
    source, output = source_raw.resolve(), output_raw.resolve()
    require(source.is_dir(), "MODEL16_INPUT_DIRECTORY_UNRESOLVED", "the authorized bounded input directory is unavailable")
    protected_root = source.parent
    require(_within(output, protected_root) and output != protected_root and not _within(output, source) and not _within(source, output), "MODEL16_OUTPUT_SCOPE_INVALID", "outputs must be separate within the same bounded protected root")
    exact: dict[str, Path] = {}
    for logical, basename in filenames.items():
        require(isinstance(basename, str) and basename not in {"", ".", ".."} and "/" not in basename and "\\" not in basename and Path(basename).name == basename and Path(basename).suffix.lower() == ".xlsx", "MODEL16_SOURCE_BASENAME_INVALID", "source registrations require exact XLSX basenames")
        candidate = source / basename
        require(not candidate.is_symlink() and candidate.resolve().parent == source and candidate.is_file(), "MODEL16_SOURCE_UNRESOLVED", "an exact authorized original is unavailable or escapes its root")
        exact[logical] = candidate
    require(len(set(exact.values())) == 3, "MODEL16_SOURCE_ALIAS_COLLISION", "each source must reference a distinct original")
    # Validate roots before any directory creation; readiness.store enforces
    # non-overlap with repository/state roots and bounded absolute scope.
    store.register_root("MODEL16_REBUILD_INPUT_ROOT", source, repository_root=repository_root)
    for logical, path in exact.items():
        store.register_asset(logical, "MODEL16_REBUILD_INPUT_ROOT", path.name, "ORIGINAL_SOURCE_FILE", immutable_original=True)
    try:
        output.mkdir(parents=True, exist_ok=True)
        if os.name != "nt":
            output.chmod(0o700)
    except OSError as exc:
        raise ConformanceError("MODEL16_OUTPUT_UNRESOLVED", "the bounded output directory could not be secured") from exc
    store.register_root("MODEL16_REBUILD_OUTPUT_ROOT", output, repository_root=repository_root)
    store.register_asset(OUTPUT_ID, "MODEL16_REBUILD_OUTPUT_ROOT", ".", "PROTECTED_PACKAGE_DIRECTORY")
    resolved = {logical: store.resolve_asset(logical).path for logical in SOURCE_IDS | {OUTPUT_ID}}
    for logical in SOURCE_IDS:
        store.record_event("ASSET", logical, "asset_located", "true", "MODEL16_EXACT_ORIGINAL_LOCATED", event_id=logical + "_LOCATED", ignore_existing=True)
    return resolved


@dataclass(frozen=True)
class HoldoutTicket:
    """Private capability returned only by a successful first opening claim."""

    stage: str
    claim_id: str
    freeze_digest: str


class StageJournal:
    """Durable exclusive holdout consumption with immutable freeze chronology.

    A committed begin consumes access even when the process crashes before the
    workbook read or completion. Only a saved complete result can be recovered;
    begin is never retried. A completed result is not permission to reopen.
    """

    FILENAME = "model16-stage-journal.sqlite3"
    VERSION = "1"
    _ACTIONS = frozenset({"feature_freeze", "model_freeze", "seed_2026.begin", "seed_2026.complete", "pursued.begin", "pursued.complete"})

    def __init__(self, output_dir: Path):
        raw = Path(output_dir)
        require(not raw.is_symlink() and raw.is_dir(), "MODEL16_JOURNAL_ROOT_INVALID", "the registered output directory must already exist")
        self.path = raw.resolve() / self.FILENAME
        require(not self.path.is_symlink(), "MODEL16_JOURNAL_SYMLINK_REJECTED", "the protected journal may not be a symbolic link")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'") if not row[0].startswith("sqlite_")}
            if not tables:
                connection.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
                connection.execute("CREATE TABLE events (ordinal INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT UNIQUE NOT NULL, payload TEXT NOT NULL, checksum TEXT NOT NULL)")
                connection.execute("INSERT INTO metadata VALUES ('version', ?)", (self.VERSION,))
                connection.execute("CREATE TRIGGER event_no_update BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT, 'immutable journal'); END")
                connection.execute("CREATE TRIGGER event_no_delete BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT, 'immutable journal'); END")
            self._verify(connection)
        if os.name != "nt":
            self.path.chmod(0o600)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        require(not self.path.is_symlink(), "MODEL16_JOURNAL_SYMLINK_REJECTED", "the protected journal may not be a symbolic link")
        connection: sqlite3.Connection | None = None
        try:
            connection = sqlite3.connect(self.path, timeout=10, isolation_level=None)
            connection.execute("PRAGMA synchronous=FULL")
            connection.row_factory = sqlite3.Row
            yield connection
            if connection.in_transaction:
                connection.commit()
        except sqlite3.Error as exc:
            if connection is not None and connection.in_transaction:
                connection.rollback()
            raise ConformanceError("MODEL16_JOURNAL_IO_INVALID", "the protected stage journal could not be validated or written") from exc
        except BaseException:
            if connection is not None and connection.in_transaction:
                connection.rollback()
            raise
        finally:
            if connection is not None:
                connection.close()

    def _verify(self, connection: sqlite3.Connection) -> dict[str, dict[str, Any]]:
        require(connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok", "MODEL16_JOURNAL_CORRUPT", "the protected journal integrity check failed")
        tables = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'") if not r[0].startswith("sqlite_")}
        require(tables == {"metadata", "events"}, "MODEL16_JOURNAL_SCHEMA_INVALID", "the protected journal schema differs")
        expected_columns = {"metadata": {"key", "value"}, "events": {"ordinal", "action", "payload", "checksum"}}
        for table, columns in expected_columns.items():
            require({r[1] for r in connection.execute(f'PRAGMA table_info("{table}")')} == columns, "MODEL16_JOURNAL_SCHEMA_INVALID", "the protected journal columns differ")
        require(dict(connection.execute("SELECT key,value FROM metadata")) == {"version": self.VERSION}, "MODEL16_JOURNAL_VERSION_INVALID", "the protected journal version differs")
        triggers = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
        require({"event_no_update", "event_no_delete"} <= triggers, "MODEL16_JOURNAL_SCHEMA_INVALID", "the protected journal immutability controls are missing")
        events: dict[str, dict[str, Any]] = {}
        previous = "0" * 64
        for ordinal, row in enumerate(connection.execute("SELECT * FROM events ORDER BY ordinal"), 1):
            try:
                payload = json.loads(row["payload"])
            except (ValueError, TypeError) as exc:
                raise ConformanceError("MODEL16_JOURNAL_TAMPERED", "protected journal metadata is invalid") from exc
            require(row["ordinal"] == ordinal and row["action"] in self._ACTIONS and row["action"] not in events and isinstance(payload, dict), "MODEL16_JOURNAL_TAMPERED", "protected journal chronology is invalid")
            expected = _digest({"ordinal": ordinal, "action": row["action"], "payload": payload, "previous": previous})
            require(row["checksum"] == expected, "MODEL16_JOURNAL_TAMPERED", "a protected journal commitment differs")
            action = row["action"]
            if action == "model_freeze":
                require("feature_freeze" in events and payload["document"]["feature_freeze_digest"] == events["feature_freeze"]["digest"], "MODEL16_FREEZE_CHRONOLOGY_INVALID", "the model freeze must follow the unchanged feature freeze")
            elif action.endswith(".begin"):
                require("model_freeze" in events and payload["freeze_digest"] == events["model_freeze"]["digest"], "MODEL16_FREEZE_CHRONOLOGY_INVALID", "holdout consumption must follow the unchanged model freeze")
            elif action.endswith(".complete"):
                begin = events.get(action.replace(".complete", ".begin"))
                require(begin is not None and payload["claim_id"] == begin["claim_id"] and payload["freeze_digest"] == begin["freeze_digest"], "MODEL16_HOLDOUT_CHRONOLOGY_INVALID", "holdout completion must match its opening claim")
            events[action] = payload
            previous = expected
        return events

    def _append(self, connection: sqlite3.Connection, action: str, payload: Mapping[str, Any]) -> None:
        row = connection.execute("SELECT ordinal,checksum FROM events ORDER BY ordinal DESC LIMIT 1").fetchone()
        ordinal, previous = (1, "0" * 64) if row is None else (row["ordinal"] + 1, row["checksum"])
        envelope = dict(payload)
        envelope["recorded_at_utc"] = utc_now()
        checksum = _digest({"ordinal": ordinal, "action": action, "payload": envelope, "previous": previous})
        connection.execute("INSERT INTO events (ordinal,action,payload,checksum) VALUES (?,?,?,?)", (ordinal, action, _json(envelope), checksum))

    def _save_freeze(self, action: str, document: Mapping[str, Any]) -> str:
        require(isinstance(document, Mapping), "MODEL16_FREEZE_INVALID", "the freeze must contain protected JSON metadata")
        copied = json.loads(_json(dict(document)))
        digest = _digest(copied)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            events = self._verify(connection)
            if action in events:
                require(events[action]["digest"] == digest and events[action]["document"] == copied, "MODEL16_FREEZE_IMMUTABLE", "a saved freeze cannot be redesigned or replaced")
                return digest
            if action == "model_freeze":
                feature = events.get("feature_freeze")
                require(feature is not None, "MODEL16_FEATURE_FREEZE_REQUIRED", "save the target-blind feature freeze first")
                require(isinstance(copied.get("baseline_id"), str) and bool(copied["baseline_id"]), "MODEL16_BASELINE_FREEZE_REQUIRED", "exactly one baseline must be frozen")
                require("challenger_id" in copied and (copied["challenger_id"] is None or isinstance(copied["challenger_id"], str) and bool(copied["challenger_id"])) and copied["challenger_id"] != copied["baseline_id"], "MODEL16_CHALLENGER_FREEZE_INVALID", "freeze at most one distinct challenger")
                require(copied.get("feature_freeze_digest") == feature["digest"], "MODEL16_FEATURE_FREEZE_MISMATCH", "the model freeze must bind the saved feature catalog")
            self._append(connection, action, {"document": copied, "digest": digest})
        return digest

    def save_feature_freeze(self, document: Mapping[str, Any]) -> str:
        return self._save_freeze("feature_freeze", document)

    def save_freeze(self, document: Mapping[str, Any]) -> str:
        return self._save_freeze("model_freeze", document)

    def _freeze(self, action: str) -> dict[str, Any]:
        with self._connect() as connection:
            events = self._verify(connection)
        require(action in events, "MODEL16_FREEZE_REQUIRED", "the required immutable freeze is not saved")
        return events[action]

    def feature_freeze_digest(self) -> str:
        return self._freeze("feature_freeze")["digest"]

    def freeze_digest(self) -> str:
        return self._freeze("model_freeze")["digest"]

    def begin_holdout(self, stage: str, *, freeze_digest: str | None = None) -> HoldoutTicket:
        require(stage in HOLDOUT_STAGES, "MODEL16_HOLDOUT_STAGE_INVALID", "only the two bounded holdouts may be opened")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            events = self._verify(connection)
            freeze = events.get("model_freeze")
            require(freeze is not None, "MODEL16_FREEZE_REQUIRED", "the baseline and optional challenger must be frozen before holdout access")
            require(freeze_digest is None or freeze_digest == freeze["digest"], "MODEL16_FREEZE_MISMATCH", "holdout opening references a different freeze")
            require(stage + ".begin" not in events, "MODEL16_HOLDOUT_ALREADY_CONSUMED", "holdout access was consumed; only a completed saved result may be recovered")
            ticket = HoldoutTicket(stage, uuid.uuid4().hex, freeze["digest"])
            self._append(connection, stage + ".begin", {"claim_id": ticket.claim_id, "freeze_digest": ticket.freeze_digest})
        return ticket

    def complete_holdout(self, ticket: HoldoutTicket, result: Mapping[str, Any]) -> dict[str, Any]:
        require(isinstance(ticket, HoldoutTicket) and ticket.stage in HOLDOUT_STAGES and isinstance(result, Mapping), "MODEL16_HOLDOUT_COMPLETION_INVALID", "a private opening ticket and JSON result are required")
        copied = json.loads(_json(dict(result)))
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            events = self._verify(connection)
            begin = events.get(ticket.stage + ".begin")
            require(begin is not None and begin["claim_id"] == ticket.claim_id and begin["freeze_digest"] == ticket.freeze_digest, "MODEL16_HOLDOUT_TICKET_INVALID", "completion does not match the consumed opening claim")
            completed = events.get(ticket.stage + ".complete")
            if completed is not None:
                require(completed["result"] == copied, "MODEL16_HOLDOUT_RESULT_IMMUTABLE", "a completed holdout result cannot be replaced")
                return completed["result"]
            self._append(connection, ticket.stage + ".complete", {"claim_id": ticket.claim_id, "freeze_digest": ticket.freeze_digest, "result": copied, "result_digest": _digest(copied)})
        return copied

    def recover_result(self, stage: str) -> dict[str, Any] | None:
        require(stage in HOLDOUT_STAGES, "MODEL16_HOLDOUT_STAGE_INVALID", "only the two bounded holdouts may be recovered")
        with self._connect() as connection:
            events = self._verify(connection)
        completed = events.get(stage + ".complete")
        if completed is None:
            return None
        require(completed["result_digest"] == _digest(completed["result"]), "MODEL16_JOURNAL_TAMPERED", "the completed result commitment differs")
        return completed["result"]


def _write_private_exclusive(path: Path, document: Mapping[str, Any]) -> None:
    payload = (_json(document) + "\n").encode("utf-8")
    try:
        if path.exists():
            require(not path.is_symlink() and path.read_bytes() == payload, "MODEL16_PACKAGE_IMMUTABLE", "the protected evidence package differs from its immutable registration")
            return
        with path.open("xb") as handle:
            if os.name != "nt":
                os.fchmod(handle.fileno(), 0o600)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        raise ConformanceError("MODEL16_PACKAGE_IO_FAILED", "a bounded protected evidence package could not be written") from exc


def register_evidence_package(
    store: ProjectState,
    output_dir: Path,
    observations: Sequence[Mapping[str, Any]],
    candidates: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Append exact private membership without changing global readiness.

    Same-location/year Seed Point and pursued observations share a ledger unit
    but retain separate source aliases, class, role, and model membership in
    this immutable sidecar. A candidate membership map explicitly covers every
    observation; ``not_used`` adds no ledger membership and no use event.
    """
    output = Path(output_dir).resolve()
    require(output == store.resolve_asset(OUTPUT_ID).path, "MODEL16_PACKAGE_ROOT_INVALID", "the package must use its registered protected output root")
    require(bool(observations) and bool(candidates), "MODEL16_PACKAGE_INCOMPLETE", "exact observations and model memberships are required")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    aliases: set[tuple[str, str]] = set()
    group_states: dict[str, str] = {}
    required = {"observation_id", "source_asset_id", "source_row", "evidence_class", "state", "forecast_year", "physical_location_id", "role", "seedpoint_id"}
    for raw in observations:
        require(required <= set(raw), "MODEL16_EVIDENCE_FIELDS_MISSING", "a protected observation lacks exact identity or role metadata")
        row = {key: raw[key] for key in sorted(required)}
        observation, group, logical = row["observation_id"], row["physical_location_id"], row["source_asset_id"]
        require(isinstance(observation, str) and bool(observation) and observation not in seen and isinstance(group, str) and bool(group), "MODEL16_EVIDENCE_IDENTITY_INVALID", "observation identities and physical groups must be explicit and unique")
        require(logical in SOURCE_IDS and row["state"] in {"MI", "WI"} and type(row["forecast_year"]) is int and row["forecast_year"] in {2024, 2025, 2026} and row["role"] in _ROLES, "MODEL16_EVIDENCE_ROLE_INVALID", "source, state, forecast vintage, or role differs from the bounded package")
        require(row["evidence_class"] in {"SEED_POINT", "PURSUED_SITE"}, "MODEL16_EVIDENCE_CLASS_INVALID", "the protected evidence class is unsupported")
        pursued = row["evidence_class"] == "PURSUED_SITE"
        require((pursued and logical == "MI_WI_PURSUED_SITES_2025_ISOLATED_V1" and row["seedpoint_id"] is None and row["forecast_year"] == 2025 and row["role"] in {"pursued_test", "excluded", "unresolved"}) or (not pursued and logical == row["state"] + "_SEED_FORECASTS_2024_2026_V1" and isinstance(row["seedpoint_id"], str) and bool(row["seedpoint_id"]) and row["role"] in ({"temporal_test", "excluded", "unresolved"} if row["forecast_year"] == 2026 else {"development", "excluded", "unresolved"})), "MODEL16_EVIDENCE_ROLE_LEAKAGE", "evidence class or vintage conflicts with its protected role")
        require(group not in group_states or group_states[group] == row["state"], "MODEL16_GROUP_STATE_CONFLICT", "one physical group cannot span states")
        source_row = row["source_row"]
        require(type(source_row) is int and source_row >= 2 or isinstance(source_row, str) and bool(source_row), "MODEL16_SOURCE_ROW_INVALID", "an exact protected source-row reference is required")
        alias = (logical, str(source_row))
        require(alias not in aliases, "MODEL16_SOURCE_ROW_DUPLICATE", "a source row may appear only once in the evidence package")
        aliases.add(alias)
        seen.add(observation)
        group_states[group] = row["state"]
        row["ledger_location_id"] = _id("LOCATION", group)
        row["ledger_evidence_unit_id"] = _id("UNIT", [group, row["forecast_year"], "ISOLATED_SALES"])
        row["ledger_alias_id"] = _id("ALIAS", alias)
        normalized.append(row)
    normalized.sort(key=lambda row: row["observation_id"])
    normalized_candidates: dict[str, dict[str, Any]] = {}
    for candidate, raw in sorted(candidates.items()):
        membership = raw.get("membership")
        require(isinstance(candidate, str) and bool(candidate) and raw.get("status", "candidate") in {"candidate", "frozen"} and isinstance(membership, Mapping) and set(membership) == seen and set(membership.values()) <= _USAGE_ROLES, "MODEL16_MODEL_MEMBERSHIP_INCOMPLETE", "each candidate requires exact complete observation-level membership")
        parent = raw.get("parent_model_id")
        require(parent is None or parent in candidates and parent != candidate, "MODEL16_MODEL_GENEALOGY_INVALID", "candidate genealogy must reference another bounded candidate")
        for row in normalized:
            usage = membership[row["observation_id"]]
            require(usage in {"not_used", "excluded"} or usage == row["role"], "MODEL16_MODEL_MEMBERSHIP_LEAKAGE", "candidate use conflicts with the frozen evidence role")
        normalized_candidates[candidate] = {"ledger_model_id": _id("MODEL", candidate), "parent_model_id": parent, "status": raw.get("status", "candidate"), "membership": dict(sorted(membership.items()))}
    # Validate acyclic genealogy before writing any new ledger rows.
    ordered: list[str] = []
    pending = set(normalized_candidates)
    while pending:
        ready = sorted(key for key in pending if normalized_candidates[key]["parent_model_id"] is None or normalized_candidates[key]["parent_model_id"] in ordered)
        require(bool(ready), "MODEL16_MODEL_GENEALOGY_INVALID", "candidate genealogy contains a cycle")
        ordered.extend(ready)
        pending.difference_update(ready)
    complete = all(row["role"] != "unresolved" for row in normalized)
    document = {"version": "1.0.0", "scope": "MODEL16_BOUNDED_REBUILD_PACKAGE_ONLY", "bounded_readiness": "READY" if complete else "INCOMPLETE", "project_wide_completeness_claimed": False, "target_definition": "ISOLATED_SALES", "observations": normalized, "candidates": normalized_candidates}
    document["content_digest"] = _digest(document)
    filename = "model16-evidence-" + document["content_digest"] + ".json"
    path = output / filename
    # Persist exact membership first. Interruptions can resume idempotent ledger
    # registration from this immutable package without inventing missing facts.
    _write_private_exclusive(path, document)
    unit_roles: dict[str, set[str]] = {}
    for row in normalized:
        unit_roles.setdefault(row["ledger_evidence_unit_id"], set()).add(row["role"])
    # One ledger unit may have multiple evidence-class aliases. Compute its
    # state once from the complete alias set, never from iteration order.
    unit_states = {
        unit: "ready" if roles & {"development", "temporal_test", "pursued_test"}
        else "unresolved" if "unresolved" in roles else "excluded"
        for unit, roles in unit_roles.items()
    }
    for row in normalized:
        source_id = _id("SOURCE", [row["source_asset_id"], row["forecast_year"]])
        store.register_source(source_id, row["source_asset_id"], "VINTAGE_" + str(row["forecast_year"]), "ISOLATED_SALES", "ready")
        unit_state = unit_states[row["ledger_evidence_unit_id"]]
        store.register_evidence_unit(row["ledger_location_id"], "unresolved" if unit_state == "unresolved" else "reconciled", row["ledger_evidence_unit_id"], "VINTAGE_" + str(row["forecast_year"]), "ISOLATED_SALES", unit_state)
        with store._connect() as connection:
            existing = connection.execute("SELECT evidence_unit_id,source_id,source_row_reference,revision_parent_alias_id FROM source_row_aliases WHERE alias_id=?", (row["ledger_alias_id"],)).fetchone()
        expected_alias = (row["ledger_evidence_unit_id"], source_id, str(row["source_row"]), None)
        require(existing is None or tuple(existing) == expected_alias, "MODEL16_SOURCE_ALIAS_REBOUND", "an existing source-row alias differs from this immutable observation")
        if existing is None:
            store.register_source_alias(row["ledger_alias_id"], *expected_alias)
        store.record_event("SOURCE_ALIAS", row["ledger_alias_id"], "identity_read", "true", "MODEL16_IDENTITY_RECONCILED", event_id=row["ledger_alias_id"] + "_IDENTITY_READ", ignore_existing=True)
    by_id = {row["observation_id"]: row for row in normalized}
    for candidate in ordered:
        model = normalized_candidates[candidate]
        parent = model["parent_model_id"]
        store.register_model(model["ledger_model_id"], model["status"], None if parent is None else normalized_candidates[parent]["ledger_model_id"])
        for observation, usage in model["membership"].items():
            if usage == "not_used":
                continue
            row = by_id[observation]
            ledger_usage = "validation" if usage in {"temporal_test", "pursued_test"} else usage
            store.register_model_membership(model["ledger_model_id"], row["ledger_evidence_unit_id"], ledger_usage)
            if usage != "excluded":
                event_subject = _id("MODEL_ALIAS", [candidate, row["ledger_alias_id"]])
                for event_type in ("analytically_used", "development_used" if usage == "development" else "validation_used"):
                    store.record_event("MODEL_SOURCE_ALIAS", event_subject, event_type, "true", "MODEL16_EXACT_OBSERVATION_MEMBERSHIP", event_id=event_subject + "_" + event_type.upper(), ignore_existing=True)
    package_id = _id("PACKAGE", document["content_digest"])
    store.register_asset(package_id, "MODEL16_REBUILD_OUTPUT_ROOT", filename, "EVIDENCE_PACKAGE_FILE")
    store.register_artifact(package_id, package_id, "MODEL16_EXACT_EVIDENCE_MEMBERSHIP", "recoverable")
    # Deliberately leave the global completeness metadata untouched.
    store.verify()
    return document
