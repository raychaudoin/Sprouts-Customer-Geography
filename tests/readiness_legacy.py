from __future__ import annotations

import sqlite3
from contextlib import closing

from sprouts_customer_geography.readiness.store import ProjectState


def downgrade_synthetic_ledger_to_v1(store: ProjectState) -> None:
    """Create the exact relevant v1 shape for synthetic migration tests."""

    with closing(sqlite3.connect(store.ledger_path)) as connection:
        connection.executescript(
            """
            PRAGMA foreign_keys = OFF;
            BEGIN IMMEDIATE;

            DROP TRIGGER evidence_events_write_ordinal_required;
            DROP TRIGGER evidence_events_write_ordinal_immutable;
            DROP TRIGGER session_recoveries_write_ordinal_required;
            DROP TRIGGER session_recoveries_write_ordinal_immutable;
            DROP INDEX evidence_events_write_ordinal_unique;
            DROP INDEX session_recoveries_write_ordinal_unique;

            ALTER TABLE evidence_events RENAME TO evidence_events_v2;
            CREATE TABLE evidence_events (
                event_id TEXT PRIMARY KEY,
                subject_kind TEXT NOT NULL,
                subject_id TEXT NOT NULL,
                event_type TEXT NOT NULL CHECK (event_type IN ('asset_located', 'identity_read', 'machine_target_read', 'visible', 'analytically_used', 'validation_used', 'development_used', 'disclosed')),
                event_state TEXT NOT NULL CHECK (event_state IN ('true', 'false', 'uncertain')),
                occurred_at TEXT NOT NULL,
                detail_code TEXT NOT NULL
            );
            INSERT INTO evidence_events(
                event_id, subject_kind, subject_id, event_type,
                event_state, occurred_at, detail_code
            )
            SELECT event_id, subject_kind, subject_id, event_type,
                   event_state, occurred_at, detail_code
            FROM evidence_events_v2;
            DROP TABLE evidence_events_v2;

            ALTER TABLE session_recoveries RENAME TO session_recoveries_v2;
            CREATE TABLE session_recoveries (
                recovery_id TEXT PRIMARY KEY,
                recovered_at TEXT NOT NULL,
                repository_commit TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('passed', 'failed'))
            );
            INSERT INTO session_recoveries(
                recovery_id, recovered_at, repository_commit, status
            )
            SELECT recovery_id, recovered_at, repository_commit, status
            FROM session_recoveries_v2;
            DROP TABLE session_recoveries_v2;

            DROP TABLE ledger_write_order;
            UPDATE metadata SET value = '1' WHERE key = 'schema_version';
            PRAGMA user_version = 1;
            COMMIT;
            """
        )
