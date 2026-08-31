"""Durable protected-local project profile and auditable evidence ledger.

The profile and SQLite ledger live outside Git worktrees.  They retain exact
local paths and protected identifiers, while the readiness publisher exposes
only a separately validated allowlist of status codes.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePath
from typing import Any, Iterable, Mapping

from sprouts_customer_geography.pipe01.errors import ConformanceError, require


PROFILE_VERSION = "1.0.0"
LEDGER_SCHEMA_VERSION = 1
PROJECT_ID = "sprouts-customer-geography"
PROFILE_FILENAME = "scg_project_profile.json"
LEDGER_FILENAME = "evidence.sqlite3"
STATE_ROOT_ENV = "SCG_PROJECT_STATE_HOME"

SAFE_ID_RE = re.compile(r"^[A-Z][A-Z0-9]*(?:[-_][A-Z0-9]+)*$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
WINDOWS_ABSOLUTE_RE = re.compile(r"^(?:[A-Za-z]:[\\/]|\\\\)")

EVENT_TYPES = frozenset(
    {
        "asset_located",
        "identity_read",
        "machine_target_read",
        "visible",
        "analytically_used",
        "validation_used",
        "development_used",
        "disclosed",
    }
)
EVENT_STATES = frozenset({"true", "false", "uncertain"})
PRESERVATION_STATES = frozenset({"frozen", "preserved-paused", "attention-needed"})


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _is_within(candidate: Path, parent: Path) -> bool:
    try:
        candidate.relative_to(parent)
        return True
    except ValueError:
        return False


def _require_external_state_root(root: Path) -> None:
    git_ancestor = next((parent for parent in (root, *root.parents) if (parent / ".git").exists()), None)
    require(git_ancestor is None, "PROJECT_STATE_INSIDE_WORKTREE", "the durable project profile must remain outside Git worktrees")


def _require_bounded_state_root(root: Path, repository_root: Path) -> None:
    _require_external_state_root(root)
    repository = Path(repository_root).expanduser().resolve()
    filesystem_root = Path(root.anchor).resolve()
    home = Path.home().resolve()
    require(root != filesystem_root and root != home, "PROJECT_STATE_ROOT_SCOPE_INVALID", "durable project state requires a bounded user-local directory")
    require(
        not _is_within(root, repository) and not _is_within(repository, root),
        "PROJECT_STATE_INSIDE_WORKTREE",
        "durable project state may not overlap the repository worktree",
    )


def _require_regular_state_file(path: Path, root: Path, *, missing_code: str) -> None:
    require(not path.is_symlink(), "PROJECT_STATE_SYMLINK_REJECTED", "protected-local state files may not be symbolic links")
    require(path.is_file(), missing_code, "a required protected-local state file is missing")
    require(path.resolve().parent == root, "PROJECT_STATE_PATH_CONTAINMENT_FAILED", "a protected-local state file escapes its bounded root")


def _require_dedicated_state_directory(root: Path, *, allow_uninitialized: bool) -> None:
    if not root.exists():
        require(allow_uninitialized, "PROJECT_STATE_PROFILE_MISSING", "the durable project profile is missing")
        return
    require(root.is_dir(), "PROJECT_STATE_ROOT_SCOPE_INVALID", "durable project state requires a dedicated directory")
    try:
        names = {entry.name for entry in root.iterdir()}
    except OSError as exc:
        raise ConformanceError("PROJECT_STATE_IO_FAILED", "the protected-local state directory could not be verified") from exc
    if allow_uninitialized and not names:
        return
    allowed = {
        PROFILE_FILENAME,
        LEDGER_FILENAME,
        f"{LEDGER_FILENAME}-journal",
        f"{LEDGER_FILENAME}-wal",
        f"{LEDGER_FILENAME}-shm",
    }
    require(
        {PROFILE_FILENAME, LEDGER_FILENAME} <= names and names <= allowed,
        "PROJECT_STATE_ROOT_NOT_DEDICATED",
        "the protected-local state directory contains an unexpected or incomplete layout",
    )


def _secure_directory(path: Path) -> None:
    """Create a private state directory without disclosing its location on failure."""

    try:
        path.mkdir(parents=True, exist_ok=True)
        if os.name != "nt":
            path.chmod(0o700)
    except OSError as exc:
        raise ConformanceError("PROJECT_STATE_IO_FAILED", "the protected-local state directory could not be secured") from exc


def _secure_file(path: Path) -> None:
    """Apply owner-only POSIX permissions; Windows relies on the user-profile ACL."""

    if os.name == "nt":
        return
    try:
        path.chmod(0o600)
    except OSError as exc:
        raise ConformanceError("PROJECT_STATE_IO_FAILED", "a protected-local state file could not be secured") from exc


def _safe_id(value: str, code: str) -> str:
    require(isinstance(value, str) and SAFE_ID_RE.fullmatch(value) is not None, code, "logical identifiers must use the bounded uppercase identifier format")
    return value


def _relative_path(value: str) -> str:
    require(isinstance(value, str) and bool(value), "PROJECT_STATE_RELATIVE_PATH_INVALID", "registered asset paths must be non-empty relative paths")
    require(not WINDOWS_ABSOLUTE_RE.match(value) and not value.startswith(("/", "~", "file:")), "PROJECT_STATE_RELATIVE_PATH_INVALID", "registered asset paths must be relative")
    pure = PurePath(value)
    require(not pure.is_absolute() and ".." not in pure.parts, "PROJECT_STATE_PATH_TRAVERSAL_REJECTED", "registered asset paths may not traverse outside an authorized root")
    return value


def default_state_root(environ: Mapping[str, str] | None = None) -> Path:
    """Return the deterministic machine-local profile location.

    The explicit override supports a later authorized relocation, but normal
    recovery needs no caller-supplied path.
    """

    env = os.environ if environ is None else environ
    override = env.get(STATE_ROOT_ENV)
    if override:
        return Path(override).expanduser()
    if env.get("LOCALAPPDATA"):
        return Path(env["LOCALAPPDATA"]) / "SproutsCustomerGeography" / "ProjectState"
    if env.get("XDG_STATE_HOME"):
        return Path(env["XDG_STATE_HOME"]) / PROJECT_ID
    return Path.home() / ".local" / "state" / PROJECT_ID


def _atomic_json(path: Path, document: Mapping[str, Any]) -> None:
    _secure_directory(path.parent)
    payload = json.dumps(document, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")) + "\n"
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", dir=path.parent, prefix=".profile-", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _secure_file(path)
    except OSError as exc:
        raise ConformanceError("PROJECT_STATE_IO_FAILED", "the protected-local profile could not be written") from exc
    finally:
        if temporary is not None and temporary.exists():
            try:
                temporary.unlink()
            except OSError:
                pass


SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS protected_roots (
    root_id TEXT PRIMARY KEY,
    absolute_path TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('ready', 'stale', 'unresolved')),
    registered_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS assets (
    asset_id TEXT PRIMARY KEY,
    root_id TEXT NOT NULL REFERENCES protected_roots(root_id),
    relative_path TEXT NOT NULL,
    asset_kind TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('registered', 'stale', 'unresolved')),
    immutable_original INTEGER NOT NULL CHECK (immutable_original IN (0, 1)),
    registered_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_inventory (
    source_id TEXT PRIMARY KEY,
    asset_id TEXT NOT NULL REFERENCES assets(asset_id),
    forecast_vintage TEXT NOT NULL,
    target_definition TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('ready', 'incomplete', 'unresolved')),
    registered_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS physical_locations (
    location_id TEXT PRIMARY KEY,
    reconciliation_status TEXT NOT NULL CHECK (reconciliation_status IN ('reconciled', 'quarantined', 'unresolved')),
    registered_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence_units (
    evidence_unit_id TEXT PRIMARY KEY,
    physical_location_id TEXT NOT NULL REFERENCES physical_locations(location_id),
    forecast_vintage TEXT NOT NULL,
    target_definition TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('ready', 'excluded', 'unresolved')),
    registered_at TEXT NOT NULL,
    UNIQUE (physical_location_id, forecast_vintage, target_definition)
);

CREATE TABLE IF NOT EXISTS source_row_aliases (
    alias_id TEXT PRIMARY KEY,
    evidence_unit_id TEXT NOT NULL REFERENCES evidence_units(evidence_unit_id),
    source_id TEXT NOT NULL REFERENCES source_inventory(source_id),
    source_row_reference TEXT NOT NULL,
    revision_parent_alias_id TEXT REFERENCES source_row_aliases(alias_id),
    registered_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence_events (
    event_id TEXT PRIMARY KEY,
    subject_kind TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    event_type TEXT NOT NULL CHECK (event_type IN ('asset_located', 'identity_read', 'machine_target_read', 'visible', 'analytically_used', 'validation_used', 'development_used', 'disclosed')),
    event_state TEXT NOT NULL CHECK (event_state IN ('true', 'false', 'uncertain')),
    occurred_at TEXT NOT NULL,
    detail_code TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS model_candidates (
    model_id TEXT PRIMARY KEY,
    parent_model_id TEXT REFERENCES model_candidates(model_id),
    status TEXT NOT NULL CHECK (status IN ('candidate', 'frozen', 'accepted', 'retired')),
    registered_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS model_evidence_membership (
    model_id TEXT NOT NULL REFERENCES model_candidates(model_id),
    evidence_unit_id TEXT NOT NULL REFERENCES evidence_units(evidence_unit_id),
    usage_role TEXT NOT NULL CHECK (usage_role IN ('validation', 'development', 'benchmark', 'excluded')),
    registered_at TEXT NOT NULL,
    PRIMARY KEY (model_id, evidence_unit_id, usage_role)
);

CREATE TABLE IF NOT EXISTS protected_artifacts (
    artifact_id TEXT PRIMARY KEY,
    asset_id TEXT NOT NULL REFERENCES assets(asset_id),
    artifact_kind TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('registered', 'recoverable', 'stale', 'unresolved')),
    registered_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS incidents (
    incident_id TEXT PRIMARY KEY,
    incident_kind TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('recorded', 'open', 'resolved')),
    summary_code TEXT NOT NULL,
    recorded_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS backup_state (
    backup_id TEXT PRIMARY KEY,
    status TEXT NOT NULL CHECK (status IN ('ready', 'stale', 'missing', 'unresolved')),
    verified_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS preservation_state (
    initiative_id TEXT PRIMARY KEY,
    status TEXT NOT NULL CHECK (status IN ('frozen', 'preserved-paused', 'attention-needed')),
    reference_commit TEXT,
    verified_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS session_recoveries (
    recovery_id TEXT PRIMARY KEY,
    recovered_at TEXT NOT NULL,
    repository_commit TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('passed', 'failed'))
);
"""

REQUIRED_TABLE_COLUMNS = {
    "metadata": {"key", "value"},
    "protected_roots": {"root_id", "absolute_path", "status", "registered_at", "updated_at"},
    "assets": {"asset_id", "root_id", "relative_path", "asset_kind", "status", "immutable_original", "registered_at", "updated_at"},
    "source_inventory": {"source_id", "asset_id", "forecast_vintage", "target_definition", "status", "registered_at"},
    "physical_locations": {"location_id", "reconciliation_status", "registered_at"},
    "evidence_units": {"evidence_unit_id", "physical_location_id", "forecast_vintage", "target_definition", "status", "registered_at"},
    "source_row_aliases": {"alias_id", "evidence_unit_id", "source_id", "source_row_reference", "revision_parent_alias_id", "registered_at"},
    "evidence_events": {"event_id", "subject_kind", "subject_id", "event_type", "event_state", "occurred_at", "detail_code"},
    "model_candidates": {"model_id", "parent_model_id", "status", "registered_at"},
    "model_evidence_membership": {"model_id", "evidence_unit_id", "usage_role", "registered_at"},
    "protected_artifacts": {"artifact_id", "asset_id", "artifact_kind", "status", "registered_at"},
    "incidents": {"incident_id", "incident_kind", "status", "summary_code", "recorded_at"},
    "backup_state": {"backup_id", "status", "verified_at"},
    "preservation_state": {"initiative_id", "status", "reference_commit", "verified_at"},
    "session_recoveries": {"recovery_id", "recovered_at", "repository_commit", "status"},
}


class _ClosingConnection(sqlite3.Connection):
    """SQLite context manager that also releases the file handle on exit."""

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> bool:
        try:
            return bool(super().__exit__(exc_type, exc_value, traceback))
        finally:
            self.close()


@dataclass(frozen=True)
class ResolvedAsset:
    asset_id: str
    asset_kind: str
    path: Path


@dataclass(frozen=True)
class ProjectState:
    state_root: Path
    profile_path: Path
    ledger_path: Path

    def _connect(self) -> sqlite3.Connection:
        _require_regular_state_file(self.ledger_path, self.state_root, missing_code="PROJECT_STATE_LEDGER_MISSING")
        connection = sqlite3.connect(self.ledger_path, factory=_ClosingConnection)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def verify(self) -> None:
        try:
            with self._connect() as connection:
                version = connection.execute("SELECT value FROM metadata WHERE key = 'schema_version'").fetchone()
                user_version = connection.execute("PRAGMA user_version").fetchone()
                integrity = connection.execute("PRAGMA integrity_check").fetchone()
                foreign_key_violations = connection.execute("PRAGMA foreign_key_check").fetchall()
                tables = {
                    row[0]
                    for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
                    if not row[0].startswith("sqlite_")
                }
                column_sets = {
                    table: {row[1] for row in connection.execute(f'PRAGMA table_info("{table}")').fetchall()}
                    for table in REQUIRED_TABLE_COLUMNS
                    if table in tables
                }
        except sqlite3.Error as exc:
            raise ConformanceError("PROJECT_STATE_LEDGER_INVALID", "the protected-local evidence ledger could not be verified") from exc
        require(version is not None and version[0] == str(LEDGER_SCHEMA_VERSION), "PROJECT_STATE_LEDGER_VERSION_MISMATCH", "the protected-local evidence ledger version differs")
        require(user_version is not None and user_version[0] == LEDGER_SCHEMA_VERSION, "PROJECT_STATE_LEDGER_VERSION_MISMATCH", "the protected-local evidence ledger version differs")
        require(integrity is not None and integrity[0] == "ok", "PROJECT_STATE_LEDGER_INVALID", "the protected-local evidence ledger integrity check failed")
        require(not foreign_key_violations, "PROJECT_STATE_LEDGER_FOREIGN_KEY_INVALID", "the protected-local evidence ledger contains broken references")
        require(set(REQUIRED_TABLE_COLUMNS) <= tables, "PROJECT_STATE_LEDGER_SCHEMA_INVALID", "the protected-local evidence ledger schema is incomplete")
        require(
            all(column_sets.get(table) == columns for table, columns in REQUIRED_TABLE_COLUMNS.items()),
            "PROJECT_STATE_LEDGER_SCHEMA_INVALID",
            "the protected-local evidence ledger schema differs",
        )

    def set_profile_status(self, status: str) -> None:
        require(status in {"ready", "stale"}, "PROJECT_STATE_PROFILE_STATUS_INVALID", "project-profile status is invalid")
        with self._connect() as connection:
            connection.execute("INSERT OR REPLACE INTO metadata(key, value) VALUES ('profile_status', ?)", (status,))

    def set_source_inventory_completeness(self, status: str) -> None:
        require(status in {"ready", "incomplete", "unresolved"}, "PROJECT_STATE_SOURCE_COMPLETENESS_INVALID", "source-inventory completeness status is invalid")
        with self._connect() as connection:
            connection.execute("INSERT OR REPLACE INTO metadata(key, value) VALUES ('source_inventory_completeness', ?)", (status,))

    def set_evidence_ledger_completeness(self, status: str) -> None:
        require(status in {"ready", "incomplete", "unresolved"}, "PROJECT_STATE_EVIDENCE_COMPLETENESS_INVALID", "evidence-ledger completeness status is invalid")
        with self._connect() as connection:
            connection.execute("INSERT OR REPLACE INTO metadata(key, value) VALUES ('evidence_ledger_completeness', ?)", (status,))

    def register_root(self, root_id: str, absolute_path: Path, *, status: str = "ready", repository_root: Path) -> None:
        _safe_id(root_id, "PROJECT_STATE_ROOT_ID_INVALID")
        require(status in {"ready", "stale", "unresolved"}, "PROJECT_STATE_ROOT_STATUS_INVALID", "protected-root status is invalid")
        raw = Path(absolute_path).expanduser()
        require(raw.is_absolute(), "PROJECT_STATE_ROOT_PATH_INVALID", "protected roots must use absolute paths")
        resolved = raw.resolve()
        repository = Path(repository_root).expanduser().resolve()
        filesystem_root = Path(resolved.anchor).resolve()
        home = Path.home().resolve()
        require(resolved != filesystem_root and resolved != home, "PROJECT_STATE_ROOT_SCOPE_INVALID", "protected roots must use a bounded project location")
        require(
            not _is_within(resolved, self.state_root) and not _is_within(self.state_root, resolved),
            "PROJECT_STATE_ROOT_SCOPE_INVALID",
            "protected asset roots may not overlap durable project state",
        )
        require(
            not _is_within(resolved, repository) and not _is_within(repository, resolved),
            "PROJECT_STATE_ROOT_INSIDE_WORKTREE",
            "protected roots may not overlap the repository worktree",
        )
        require(status != "ready" or resolved.is_dir(), "PROJECT_STATE_ROOT_UNRESOLVED", "a ready protected root must resolve to a directory")
        now = utc_now()
        with self._connect() as connection:
            existing = connection.execute("SELECT absolute_path FROM protected_roots WHERE root_id = ?", (root_id,)).fetchone()
            immutable_count = connection.execute(
                "SELECT COUNT(*) FROM assets WHERE root_id = ? AND immutable_original = 1",
                (root_id,),
            ).fetchone()[0]
            require(
                existing is None or not immutable_count or existing["absolute_path"] == str(resolved),
                "PROJECT_STATE_IMMUTABLE_ORIGINAL_REJECTED",
                "an immutable original registration cannot be retargeted",
            )
            connection.execute(
                """INSERT INTO protected_roots(root_id, absolute_path, status, registered_at, updated_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(root_id) DO UPDATE SET absolute_path=excluded.absolute_path, status=excluded.status, updated_at=excluded.updated_at""",
                (root_id, str(resolved), status, now, now),
            )

    def register_asset(
        self,
        asset_id: str,
        root_id: str,
        relative_path: str,
        asset_kind: str,
        *,
        status: str = "registered",
        immutable_original: bool = False,
    ) -> None:
        _safe_id(asset_id, "PROJECT_STATE_ASSET_ID_INVALID")
        _safe_id(root_id, "PROJECT_STATE_ROOT_ID_INVALID")
        _safe_id(asset_kind, "PROJECT_STATE_ASSET_KIND_INVALID")
        relative = _relative_path(relative_path)
        require(status in {"registered", "stale", "unresolved"}, "PROJECT_STATE_ASSET_STATUS_INVALID", "protected-asset status is invalid")
        now = utc_now()
        try:
            with self._connect() as connection:
                existing = connection.execute(
                    "SELECT root_id, relative_path, asset_kind, immutable_original FROM assets WHERE asset_id = ?",
                    (asset_id,),
                ).fetchone()
                if existing is not None and existing["immutable_original"]:
                    require(
                        (existing["root_id"], existing["relative_path"], existing["asset_kind"], existing["immutable_original"])
                        == (root_id, relative, asset_kind, int(immutable_original)),
                        "PROJECT_STATE_IMMUTABLE_ORIGINAL_REJECTED",
                        "an immutable original registration cannot be retargeted",
                    )
                connection.execute(
                    """INSERT INTO assets(asset_id, root_id, relative_path, asset_kind, status, immutable_original, registered_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(asset_id) DO UPDATE SET root_id=excluded.root_id, relative_path=excluded.relative_path,
                           asset_kind=excluded.asset_kind, status=excluded.status, immutable_original=excluded.immutable_original,
                           updated_at=excluded.updated_at""",
                    (asset_id, root_id, relative, asset_kind, status, int(immutable_original), now, now),
                )
        except sqlite3.IntegrityError as exc:
            raise ConformanceError("PROJECT_STATE_ROOT_UNRESOLVED", "an asset references an unregistered protected root") from exc

    def resolve_asset(self, asset_id: str, *, must_exist: bool = True, require_ready: bool = True) -> ResolvedAsset:
        _safe_id(asset_id, "PROJECT_STATE_ASSET_ID_INVALID")
        with self._connect() as connection:
            row = connection.execute(
                """SELECT a.asset_id, a.relative_path, a.asset_kind, a.status AS asset_status,
                          r.absolute_path, r.status AS root_status
                   FROM assets a JOIN protected_roots r ON r.root_id = a.root_id WHERE a.asset_id = ?""",
                (asset_id,),
            ).fetchone()
        require(row is not None, "PROJECT_STATE_ASSET_UNREGISTERED", "the requested protected asset is not registered")
        if require_ready:
            require(
                row["root_status"] == "ready" and row["asset_status"] == "registered",
                "PROJECT_STATE_ASSET_UNRESOLVED",
                "the requested protected asset registration is not ready",
            )
        root = Path(row["absolute_path"]).resolve()
        relative = _relative_path(row["relative_path"])
        candidate = (root / Path(relative)).resolve()
        require(_is_within(candidate, root), "PROJECT_STATE_PATH_CONTAINMENT_FAILED", "a registered asset escapes its authorized protected root")
        if must_exist:
            if row["asset_kind"].endswith("_DIRECTORY") or row["asset_kind"].endswith("_ROOT") or relative == ".":
                require(candidate.is_dir(), "PROJECT_STATE_ASSET_UNRESOLVED", "the registered protected directory is unavailable")
            else:
                require(candidate.is_file(), "PROJECT_STATE_ASSET_UNRESOLVED", "the registered protected file is unavailable")
        return ResolvedAsset(row["asset_id"], row["asset_kind"], candidate)

    def register_source(self, source_id: str, asset_id: str, forecast_vintage: str, target_definition: str, status: str) -> None:
        for value, code in ((source_id, "PROJECT_STATE_SOURCE_ID_INVALID"), (asset_id, "PROJECT_STATE_ASSET_ID_INVALID"), (forecast_vintage, "PROJECT_STATE_VINTAGE_INVALID"), (target_definition, "PROJECT_STATE_TARGET_DEFINITION_INVALID")):
            _safe_id(value, code)
        require(status in {"ready", "incomplete", "unresolved"}, "PROJECT_STATE_SOURCE_STATUS_INVALID", "source inventory status is invalid")
        with self._connect() as connection:
            asset = connection.execute(
                "SELECT immutable_original FROM assets WHERE asset_id = ?",
                (asset_id,),
            ).fetchone()
            require(
                asset is not None and asset["immutable_original"] == 1,
                "PROJECT_STATE_SOURCE_IMMUTABILITY_REQUIRED",
                "source inventory must reference an immutable original asset",
            )
            existing = connection.execute(
                "SELECT asset_id, forecast_vintage, target_definition FROM source_inventory WHERE source_id = ?",
                (source_id,),
            ).fetchone()
            require(
                existing is None
                or (existing["asset_id"], existing["forecast_vintage"], existing["target_definition"])
                == (asset_id, forecast_vintage, target_definition),
                "PROJECT_STATE_SOURCE_PROVENANCE_REJECTED",
                "a source registration cannot be retargeted; register a revision instead",
            )
            connection.execute(
                """INSERT INTO source_inventory(source_id, asset_id, forecast_vintage, target_definition, status, registered_at)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(source_id) DO UPDATE SET asset_id=excluded.asset_id, forecast_vintage=excluded.forecast_vintage,
                       target_definition=excluded.target_definition, status=excluded.status""",
                (source_id, asset_id, forecast_vintage, target_definition, status, utc_now()),
            )

    def register_evidence_unit(
        self,
        location_id: str,
        reconciliation_status: str,
        evidence_unit_id: str,
        forecast_vintage: str,
        target_definition: str,
        status: str,
    ) -> None:
        for value, code in ((location_id, "PROJECT_STATE_LOCATION_ID_INVALID"), (evidence_unit_id, "PROJECT_STATE_EVIDENCE_ID_INVALID"), (forecast_vintage, "PROJECT_STATE_VINTAGE_INVALID"), (target_definition, "PROJECT_STATE_TARGET_DEFINITION_INVALID")):
            _safe_id(value, code)
        require(reconciliation_status in {"reconciled", "quarantined", "unresolved"}, "PROJECT_STATE_RECONCILIATION_STATUS_INVALID", "physical-location reconciliation status is invalid")
        require(status in {"ready", "excluded", "unresolved"}, "PROJECT_STATE_EVIDENCE_STATUS_INVALID", "evidence-unit status is invalid")
        now = utc_now()
        with self._connect() as connection:
            connection.execute("INSERT OR IGNORE INTO physical_locations(location_id, reconciliation_status, registered_at) VALUES (?, ?, ?)", (location_id, reconciliation_status, now))
            existing = connection.execute(
                "SELECT physical_location_id, forecast_vintage, target_definition FROM evidence_units WHERE evidence_unit_id = ?",
                (evidence_unit_id,),
            ).fetchone()
            require(
                existing is None
                or (existing["physical_location_id"], existing["forecast_vintage"], existing["target_definition"])
                == (location_id, forecast_vintage, target_definition),
                "PROJECT_STATE_EVIDENCE_PROVENANCE_REJECTED",
                "an evidence-unit registration cannot be rebound; register a revision instead",
            )
            connection.execute(
                """INSERT INTO evidence_units(evidence_unit_id, physical_location_id, forecast_vintage, target_definition, status, registered_at)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(evidence_unit_id) DO UPDATE SET physical_location_id=excluded.physical_location_id,
                       forecast_vintage=excluded.forecast_vintage, target_definition=excluded.target_definition, status=excluded.status""",
                (evidence_unit_id, location_id, forecast_vintage, target_definition, status, now),
            )

    def register_source_alias(self, alias_id: str, evidence_unit_id: str, source_id: str, source_row_reference: str, revision_parent_alias_id: str | None = None) -> None:
        for value, code in ((alias_id, "PROJECT_STATE_ALIAS_ID_INVALID"), (evidence_unit_id, "PROJECT_STATE_EVIDENCE_ID_INVALID"), (source_id, "PROJECT_STATE_SOURCE_ID_INVALID")):
            _safe_id(value, code)
        if revision_parent_alias_id is not None:
            _safe_id(revision_parent_alias_id, "PROJECT_STATE_ALIAS_ID_INVALID")
        require(isinstance(source_row_reference, str) and bool(source_row_reference), "PROJECT_STATE_SOURCE_ROW_INVALID", "source-row aliases require a protected-local row reference")
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO source_row_aliases(alias_id, evidence_unit_id, source_id, source_row_reference, revision_parent_alias_id, registered_at) VALUES (?, ?, ?, ?, ?, ?)",
                (alias_id, evidence_unit_id, source_id, source_row_reference, revision_parent_alias_id, utc_now()),
            )

    def record_event(
        self,
        subject_kind: str,
        subject_id: str,
        event_type: str,
        event_state: str,
        detail_code: str,
        *,
        event_id: str | None = None,
        occurred_at: str | None = None,
        ignore_existing: bool = False,
    ) -> str:
        for value, code in ((subject_kind, "PROJECT_STATE_SUBJECT_KIND_INVALID"), (subject_id, "PROJECT_STATE_SUBJECT_ID_INVALID"), (detail_code, "PROJECT_STATE_DETAIL_CODE_INVALID")):
            _safe_id(value, code)
        require(event_type in EVENT_TYPES, "PROJECT_STATE_EVENT_TYPE_INVALID", "evidence event type is invalid")
        require(event_state in EVENT_STATES, "PROJECT_STATE_EVENT_STATE_INVALID", "evidence event state is invalid")
        chosen_id = event_id or f"EVENT_{uuid.uuid4().hex.upper()}"
        _safe_id(chosen_id, "PROJECT_STATE_EVENT_ID_INVALID")
        verb = "INSERT OR IGNORE" if ignore_existing else "INSERT"
        with self._connect() as connection:
            connection.execute(
                f"{verb} INTO evidence_events(event_id, subject_kind, subject_id, event_type, event_state, occurred_at, detail_code) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (chosen_id, subject_kind, subject_id, event_type, event_state, occurred_at or utc_now(), detail_code),
            )
        return chosen_id

    def register_model(self, model_id: str, status: str, parent_model_id: str | None = None) -> None:
        _safe_id(model_id, "PROJECT_STATE_MODEL_ID_INVALID")
        if parent_model_id is not None:
            _safe_id(parent_model_id, "PROJECT_STATE_MODEL_ID_INVALID")
        require(status in {"candidate", "frozen", "accepted", "retired"}, "PROJECT_STATE_MODEL_STATUS_INVALID", "model genealogy status is invalid")
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO model_candidates(model_id, parent_model_id, status, registered_at) VALUES (?, ?, ?, ?)
                   ON CONFLICT(model_id) DO UPDATE SET parent_model_id=excluded.parent_model_id, status=excluded.status""",
                (model_id, parent_model_id, status, utc_now()),
            )

    def register_model_membership(self, model_id: str, evidence_unit_id: str, usage_role: str) -> None:
        _safe_id(model_id, "PROJECT_STATE_MODEL_ID_INVALID")
        _safe_id(evidence_unit_id, "PROJECT_STATE_EVIDENCE_ID_INVALID")
        require(usage_role in {"validation", "development", "benchmark", "excluded"}, "PROJECT_STATE_USAGE_ROLE_INVALID", "model-evidence usage role is invalid")
        with self._connect() as connection:
            connection.execute("INSERT OR REPLACE INTO model_evidence_membership(model_id, evidence_unit_id, usage_role, registered_at) VALUES (?, ?, ?, ?)", (model_id, evidence_unit_id, usage_role, utc_now()))

    def model_membership(self, model_id: str) -> tuple[tuple[str, str], ...]:
        _safe_id(model_id, "PROJECT_STATE_MODEL_ID_INVALID")
        with self._connect() as connection:
            rows = connection.execute("SELECT evidence_unit_id, usage_role FROM model_evidence_membership WHERE model_id = ? ORDER BY evidence_unit_id, usage_role", (model_id,)).fetchall()
        return tuple((row["evidence_unit_id"], row["usage_role"]) for row in rows)

    def event_states(self, subject_id: str) -> Mapping[str, str]:
        _safe_id(subject_id, "PROJECT_STATE_SUBJECT_ID_INVALID")
        with self._connect() as connection:
            rows = connection.execute("SELECT event_type, event_state FROM evidence_events WHERE subject_id = ? ORDER BY occurred_at, event_id", (subject_id,)).fetchall()
        return {row["event_type"]: row["event_state"] for row in rows}

    def set_preservation(self, initiative_id: str, status: str, reference_commit: str | None = None) -> None:
        require(re.fullmatch(r"[A-Z]+-[0-9]{2,4}[A-Z]?", initiative_id) is not None, "PROJECT_STATE_INITIATIVE_ID_INVALID", "preservation state requires a safe initiative identifier")
        require(status in PRESERVATION_STATES, "PROJECT_STATE_PRESERVATION_STATUS_INVALID", "initiative preservation status is invalid")
        require(reference_commit is None or COMMIT_RE.fullmatch(reference_commit) is not None, "PROJECT_STATE_COMMIT_INVALID", "preservation commit must be a full lowercase Git object ID")
        with self._connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO preservation_state(initiative_id, status, reference_commit, verified_at) VALUES (?, ?, ?, ?)",
                (initiative_id, status, reference_commit, utc_now()),
            )

    def preservation(self) -> Mapping[str, str]:
        with self._connect() as connection:
            rows = connection.execute("SELECT initiative_id, status FROM preservation_state ORDER BY initiative_id").fetchall()
        return {row["initiative_id"]: row["status"] for row in rows}

    def preservation_details(self) -> Mapping[str, tuple[str, str | None]]:
        with self._connect() as connection:
            rows = connection.execute("SELECT initiative_id, status, reference_commit FROM preservation_state ORDER BY initiative_id").fetchall()
        return {row["initiative_id"]: (row["status"], row["reference_commit"]) for row in rows}

    def register_artifact(self, artifact_id: str, asset_id: str, artifact_kind: str, status: str) -> None:
        for value, code in ((artifact_id, "PROJECT_STATE_ARTIFACT_ID_INVALID"), (asset_id, "PROJECT_STATE_ASSET_ID_INVALID"), (artifact_kind, "PROJECT_STATE_ARTIFACT_KIND_INVALID")):
            _safe_id(value, code)
        require(status in {"registered", "recoverable", "stale", "unresolved"}, "PROJECT_STATE_ARTIFACT_STATUS_INVALID", "protected-artifact status is invalid")
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO protected_artifacts(artifact_id, asset_id, artifact_kind, status, registered_at) VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(artifact_id) DO UPDATE SET asset_id=excluded.asset_id, artifact_kind=excluded.artifact_kind, status=excluded.status""",
                (artifact_id, asset_id, artifact_kind, status, utc_now()),
            )

    def record_incident(self, incident_id: str, incident_kind: str, status: str, summary_code: str) -> None:
        for value, code in ((incident_id, "PROJECT_STATE_INCIDENT_ID_INVALID"), (incident_kind, "PROJECT_STATE_INCIDENT_KIND_INVALID"), (summary_code, "PROJECT_STATE_SUMMARY_CODE_INVALID")):
            _safe_id(value, code)
        require(status in {"recorded", "open", "resolved"}, "PROJECT_STATE_INCIDENT_STATUS_INVALID", "incident status is invalid")
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO incidents(incident_id, incident_kind, status, summary_code, recorded_at) VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(incident_id) DO UPDATE SET status=excluded.status, summary_code=excluded.summary_code""",
                (incident_id, incident_kind, status, summary_code, utc_now()),
            )

    def set_backup_state(self, backup_id: str, status: str) -> None:
        _safe_id(backup_id, "PROJECT_STATE_BACKUP_ID_INVALID")
        require(status in {"ready", "stale", "missing", "unresolved"}, "PROJECT_STATE_BACKUP_STATUS_INVALID", "backup status is invalid")
        with self._connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO backup_state(backup_id, status, verified_at) VALUES (?, ?, ?)",
                (backup_id, status, utc_now()),
            )

    def record_recovery(self, repository_commit: str, status: str = "passed", *, fresh_session: bool = False) -> None:
        require(COMMIT_RE.fullmatch(repository_commit) is not None, "PROJECT_STATE_COMMIT_INVALID", "recovery state requires a full lowercase Git object ID")
        require(status in {"passed", "failed"}, "PROJECT_STATE_RECOVERY_STATUS_INVALID", "session recovery status is invalid")
        prefix = "FRESH_SESSION" if fresh_session else "RECOVERY"
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO session_recoveries(recovery_id, recovered_at, repository_commit, status) VALUES (?, ?, ?, ?)",
                (f"{prefix}_{uuid.uuid4().hex.upper()}", utc_now(), repository_commit, status),
            )

    def fresh_session_recovery_status(self, repository_commit: str) -> str | None:
        require(COMMIT_RE.fullmatch(repository_commit) is not None, "PROJECT_STATE_COMMIT_INVALID", "recovery state requires a full lowercase Git object ID")
        with self._connect() as connection:
            row = connection.execute(
                """SELECT status FROM session_recoveries
                   WHERE recovery_id GLOB 'FRESH_SESSION_*' AND repository_commit = ?
                   ORDER BY recovered_at DESC, recovery_id DESC LIMIT 1""",
                (repository_commit,),
            ).fetchone()
        return None if row is None else str(row["status"])

    def readiness_facts(self) -> Mapping[str, str]:
        facts: dict[str, str] = {}
        try:
            self.verify()
        except ConformanceError:
            facts["project_profile"] = "invalid"
            facts.update(
                asset_catalog="unresolved",
                original_source_inventory="unresolved",
                evidence_ledger="unresolved",
                model13_authority="unresolved",
                app01_inputs="unresolved",
            )
            return facts
        with self._connect() as connection:
            profile_status = connection.execute("SELECT value FROM metadata WHERE key = 'profile_status'").fetchone()
            source_completeness = connection.execute("SELECT value FROM metadata WHERE key = 'source_inventory_completeness'").fetchone()
            evidence_completeness = connection.execute("SELECT value FROM metadata WHERE key = 'evidence_ledger_completeness'").fetchone()
            roots = connection.execute("SELECT status FROM protected_roots").fetchall()
            assets = connection.execute("SELECT asset_id, status FROM assets ORDER BY asset_id").fetchall()
            sources = connection.execute("SELECT status FROM source_inventory").fetchall()
            evidence_count = connection.execute("SELECT COUNT(*) FROM evidence_units").fetchone()[0]
            membership_count = connection.execute("SELECT COUNT(*) FROM model_evidence_membership").fetchone()[0]
        facts["project_profile"] = profile_status[0] if profile_status is not None and profile_status[0] in {"ready", "stale"} else "invalid"
        unresolved_assets = False
        for row in assets:
            try:
                self.resolve_asset(row["asset_id"], require_ready=False)
            except ConformanceError:
                unresolved_assets = True
        if not assets or unresolved_assets or any(row["status"] == "unresolved" for row in (*roots, *assets)):
            facts["asset_catalog"] = "unresolved"
        elif any(row["status"] == "stale" for row in (*roots, *assets)):
            facts["asset_catalog"] = "stale"
        else:
            facts["asset_catalog"] = "ready"
        source_posture = "incomplete" if source_completeness is None else source_completeness[0]
        if source_posture == "unresolved" or any(row["status"] == "unresolved" for row in sources):
            facts["original_source_inventory"] = "unresolved"
        elif source_posture == "ready" and sources and all(row["status"] == "ready" for row in sources):
            facts["original_source_inventory"] = "ready"
        else:
            facts["original_source_inventory"] = "incomplete"
        evidence_posture = "incomplete" if evidence_completeness is None else evidence_completeness[0]
        if evidence_posture == "unresolved":
            facts["evidence_ledger"] = "unresolved"
        elif evidence_posture == "ready" and evidence_count and membership_count:
            facts["evidence_ledger"] = "ready"
        else:
            facts["evidence_ledger"] = "incomplete"
        for field, asset_id in (("model13_authority", "MODEL13_AUTHORITY_PACKAGE"), ("app01_inputs", "APP01_PROTECTED_INPUT_PACKAGE")):
            try:
                self.resolve_asset(asset_id)
                facts[field] = "registered-recoverable"
            except ConformanceError as exc:
                facts[field] = "not-registered" if "UNREGISTERED" in str(exc) else "registered-unresolved"
        return facts


def initialize_project_state(state_root: Path | None = None, *, repository_root: Path) -> ProjectState:
    raw_root = (state_root or default_state_root()).expanduser()
    require(not raw_root.is_symlink(), "PROJECT_STATE_SYMLINK_REJECTED", "the durable project state root may not be a symbolic link")
    root = raw_root.resolve()
    _require_bounded_state_root(root, repository_root)
    _require_dedicated_state_directory(root, allow_uninitialized=True)
    _secure_directory(root)
    profile_path = root / PROFILE_FILENAME
    ledger_path = root / LEDGER_FILENAME
    profile = {
        "ledger_file": LEDGER_FILENAME,
        "profile_version": PROFILE_VERSION,
        "project_id": PROJECT_ID,
    }
    require(not profile_path.is_symlink() and not ledger_path.is_symlink(), "PROJECT_STATE_SYMLINK_REJECTED", "protected-local state files may not be symbolic links")
    require(not profile_path.exists() or profile_path.is_file(), "PROJECT_STATE_PROFILE_INVALID", "the durable project profile is not a regular file")
    require(not ledger_path.exists() or ledger_path.is_file(), "PROJECT_STATE_LEDGER_INVALID", "the protected-local evidence ledger is not a regular file")
    profile_exists = profile_path.is_file()
    ledger_exists = ledger_path.is_file()
    require(profile_exists == ledger_exists, "PROJECT_STATE_PARTIAL_INITIALIZATION", "the protected-local project state is incomplete")
    if profile_exists:
        try:
            existing = json.loads(profile_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ConformanceError("PROJECT_STATE_PROFILE_INVALID", "the durable project profile is unreadable") from exc
        require(existing == profile, "PROJECT_STATE_PROFILE_INVALID", "the durable project profile identity differs")
        _secure_file(profile_path)
    else:
        _atomic_json(profile_path, profile)
    if not ledger_exists:
        try:
            with sqlite3.connect(ledger_path, factory=_ClosingConnection) as connection:
                connection.executescript(SCHEMA_SQL)
                connection.execute("INSERT INTO metadata(key, value) VALUES ('schema_version', ?)", (str(LEDGER_SCHEMA_VERSION),))
                connection.execute("INSERT INTO metadata(key, value) VALUES ('profile_status', 'ready')")
                connection.execute("INSERT INTO metadata(key, value) VALUES ('source_inventory_completeness', 'incomplete')")
                connection.execute("INSERT INTO metadata(key, value) VALUES ('evidence_ledger_completeness', 'incomplete')")
                connection.execute(f"PRAGMA user_version = {LEDGER_SCHEMA_VERSION}")
        except sqlite3.Error as exc:
            raise ConformanceError("PROJECT_STATE_LEDGER_INVALID", "the protected-local evidence ledger could not be initialized") from exc
    _secure_file(ledger_path)
    store = ProjectState(root, profile_path, ledger_path)
    store.verify()
    return store


def recover_project_state(state_root: Path | None = None, *, repository_root: Path) -> ProjectState:
    raw_root = (state_root or default_state_root()).expanduser()
    require(not raw_root.is_symlink(), "PROJECT_STATE_SYMLINK_REJECTED", "the durable project state root may not be a symbolic link")
    root = raw_root.resolve()
    _require_bounded_state_root(root, repository_root)
    _require_dedicated_state_directory(root, allow_uninitialized=False)
    profile_path = root / PROFILE_FILENAME
    _require_regular_state_file(profile_path, root, missing_code="PROJECT_STATE_PROFILE_MISSING")
    try:
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ConformanceError("PROJECT_STATE_PROFILE_INVALID", "the durable project profile is unreadable") from exc
    expected = {"ledger_file": LEDGER_FILENAME, "profile_version": PROFILE_VERSION, "project_id": PROJECT_ID}
    require(profile == expected, "PROJECT_STATE_PROFILE_INVALID", "the durable project profile identity differs")
    ledger_path = root / str(profile["ledger_file"])
    _require_regular_state_file(ledger_path, root, missing_code="PROJECT_STATE_LEDGER_MISSING")
    _secure_directory(root)
    _secure_file(profile_path)
    _secure_file(ledger_path)
    store = ProjectState(root, profile_path, ledger_path)
    store.verify()
    return store


def migrate_model15_parser_incident(store: ProjectState) -> None:
    """Record the authorized incident semantics without opening target sources."""

    now = utc_now()
    store.record_incident("MODEL15_PARSER_INCIDENT", "PARSER_BOUNDARY", "recorded", "MACHINE_READ_POSSIBLE_NO_USE")
    states = {
        "machine_target_read": "uncertain",
        "visible": "false",
        "analytically_used": "false",
        "development_used": "false",
        "disclosed": "false",
    }
    for event_type, event_state in states.items():
        store.record_event(
            "INCIDENT",
            "MODEL15_PARSER_INCIDENT",
            event_type,
            event_state,
            "AUTHORIZED_GOV16_MIGRATION",
            event_id=f"MODEL15_{event_type.upper()}_MIGRATION",
            occurred_at=now,
            ignore_existing=True,
        )


def bootstrap_from_app01_settings(
    repository_root: Path,
    *,
    state_root: Path | None = None,
    settings_path: Path | None = None,
) -> ProjectState:
    """Bootstrap exact current registrations from one trusted settings file.

    This deliberately reads no candidate package contents and performs no
    filesystem search.  The settings file is a one-time trusted pointer source;
    subsequent sessions recover the durable profile directly.
    """

    repository = Path(repository_root).resolve()
    path = settings_path or repository / "presentation" / "app01" / "local" / "settings.json"
    require(path.is_file(), "PROJECT_STATE_BOOTSTRAP_SETTINGS_MISSING", "the trusted APP-01 local settings file is missing")
    try:
        settings = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ConformanceError("PROJECT_STATE_BOOTSTRAP_SETTINGS_INVALID", "the trusted APP-01 local settings file is unreadable") from exc
    require(isinstance(settings, Mapping) and set(settings) <= {"model13_candidates", "model13_registry", "data04_candidates"}, "PROJECT_STATE_BOOTSTRAP_SETTINGS_INVALID", "trusted APP-01 settings contain unsupported fields")
    candidates = settings.get("model13_candidates")
    require(isinstance(candidates, list) and len(candidates) == 1 and isinstance(candidates[0], str) and bool(candidates[0]), "PROJECT_STATE_BOOTSTRAP_CANDIDATE_AMBIGUOUS", "bootstrap requires exactly one trusted MODEL-13 package registration")
    candidate = Path(candidates[0]).expanduser()
    if not candidate.is_absolute():
        candidate = repository / candidate
    candidate = candidate.resolve()
    require(candidate.is_dir(), "PROJECT_STATE_BOOTSTRAP_CANDIDATE_UNRESOLVED", "the trusted MODEL-13 package registration is unavailable")

    store = initialize_project_state(state_root, repository_root=repository)
    store.register_root("CURRENT_PROTECTED_PROJECT_ROOT", candidate, repository_root=repository)
    store.register_asset("MODEL13_AUTHORITY_PACKAGE", "CURRENT_PROTECTED_PROJECT_ROOT", ".", "PROTECTED_PACKAGE_DIRECTORY", immutable_original=True)
    store.register_asset("APP01_PROTECTED_INPUT_PACKAGE", "CURRENT_PROTECTED_PROJECT_ROOT", ".", "PROTECTED_PACKAGE_DIRECTORY", immutable_original=True)
    store.set_preservation("MODEL-14", "frozen", "2759647ee814ac4d65dc3958e54277247288bacf")
    store.set_preservation("MODEL-15", "preserved-paused", "e464d5ea2453d7387102d64154bb52f410b12670")
    migrate_model15_parser_incident(store)
    return store


def register_synthetic_evidence(
    store: ProjectState,
    *,
    source_id: str,
    asset_id: str,
    evidence: Iterable[tuple[str, str, str]],
) -> None:
    """Small helper used by synthetic tests and later explicit migrations."""

    store.register_source(source_id, asset_id, "SYNTHETIC_V1", "SYNTHETIC_MEASURE", "ready")
    store.register_model("SYNTHETIC_MODEL", "candidate")
    for location_id, evidence_unit_id, usage_role in evidence:
        store.register_evidence_unit(location_id, "reconciled", evidence_unit_id, "SYNTHETIC_V1", "SYNTHETIC_MEASURE", "ready")
        store.register_model_membership("SYNTHETIC_MODEL", evidence_unit_id, usage_role)
