"""Synthetic-only protected registration and one-time holdout journal tests."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sprouts_customer_geography.model16.evidence import (
    HoldoutTicket, OUTPUT_ID, SOURCE_IDS, StageJournal,
    register_assets, register_evidence_package,
)
from sprouts_customer_geography.pipe01.errors import ConformanceError
from sprouts_customer_geography.readiness.store import initialize_project_state


class Model16EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="model16-synthetic-evidence-")
        self.root = Path(self.temp.name)
        self.repository = self.root / "repository"
        self.repository.mkdir()
        self.source = self.root / "protected" / "inputs"
        self.source.mkdir(parents=True)
        self.output = self.root / "protected" / "output"
        self.store = initialize_project_state(self.root / "state", repository_root=self.repository)
        self.mapping = {logical: f"fictional-{index}.xlsx" for index, logical in enumerate(sorted(SOURCE_IDS))}
        for filename in self.mapping.values():
            (self.source / filename).write_bytes(b"FICTIONAL ORIGINAL; NOT A WORKBOOK")

    def tearDown(self):
        self.temp.cleanup()

    def register(self):
        return register_assets(self.store, self.source, self.mapping, self.output, repository_root=self.repository)

    def journal(self):
        self.register()
        return StageJournal(self.output)

    def frozen(self):
        journal = self.journal()
        feature_digest = journal.save_feature_freeze({"sources": ["fictional-public-vintage"], "features": ["fictional-economic-feature"]})
        model = {"baseline_id": "fictional_baseline", "challenger_id": "fictional_challenger", "feature_freeze_digest": feature_digest, "folds": [0, 1, 2]}
        model_digest = journal.save_freeze(model)
        return journal, model, model_digest

    @staticmethod
    def observations():
        # The pursued forecast intentionally shares location/year with a seed.
        return [
            {"observation_id": "fictional-seed-2025", "source_asset_id": "MI_SEED_FORECASTS_2024_2026_V1", "source_row": 2, "evidence_class": "SEED_POINT", "state": "MI", "forecast_year": 2025, "physical_location_id": "fictional-location-alpha", "role": "development", "seedpoint_id": "fictional-seed-alpha"},
            {"observation_id": "fictional-seed-2026", "source_asset_id": "MI_SEED_FORECASTS_2024_2026_V1", "source_row": 3, "evidence_class": "SEED_POINT", "state": "MI", "forecast_year": 2026, "physical_location_id": "fictional-location-alpha", "role": "temporal_test", "seedpoint_id": "fictional-seed-alpha"},
            {"observation_id": "fictional-pursuit-2025", "source_asset_id": "MI_WI_PURSUED_SITES_2025_ISOLATED_V1", "source_row": 2, "evidence_class": "PURSUED_SITE", "state": "MI", "forecast_year": 2025, "physical_location_id": "fictional-location-alpha", "role": "pursued_test", "seedpoint_id": None},
        ]

    @classmethod
    def candidates(cls):
        return {"fictional_baseline": {"status": "frozen", "membership": {row["observation_id"]: row["role"] for row in cls.observations()}}}

    def test_registration_is_exact_immutable_in_place_and_does_not_scan(self):
        before = {logical: (self.source / filename).read_bytes() for logical, filename in self.mapping.items()}
        with patch.object(Path, "iterdir", side_effect=AssertionError("directory scan prohibited")), patch.object(Path, "glob", side_effect=AssertionError("glob prohibited")), patch.object(Path, "rglob", side_effect=AssertionError("recursive scan prohibited")):
            result = self.register()
            self.register()
        self.assertEqual(set(result), SOURCE_IDS | {OUTPUT_ID})
        for logical, filename in self.mapping.items():
            self.assertEqual(result[logical], (self.source / filename).resolve())
            self.assertEqual((self.source / filename).read_bytes(), before[logical])
        with self.store._connect() as connection:
            originals = connection.execute("SELECT COUNT(*) FROM assets WHERE immutable_original=1").fetchone()[0]
            located = connection.execute("SELECT COUNT(*) FROM evidence_events WHERE event_type='asset_located'").fetchone()[0]
        self.assertEqual(originals, 3)
        self.assertEqual(located, 3)

    def test_registration_rejects_wrong_scope_missing_or_rebound_assets(self):
        with self.assertRaisesRegex(ConformanceError, "MODEL16_OUTPUT_SCOPE_INVALID"):
            register_assets(self.store, self.source, self.mapping, self.root / "elsewhere", repository_root=self.repository)
        changed = dict(self.mapping)
        changed[next(iter(changed))] = "../escape.xlsx"
        with self.assertRaisesRegex(ConformanceError, "MODEL16_SOURCE_BASENAME_INVALID"):
            register_assets(self.store, self.source, changed, self.output, repository_root=self.repository)
        self.register()
        alternate = self.source / "fictional-alternate.xlsx"
        alternate.write_bytes(b"FICTIONAL ALTERNATE")
        changed = dict(self.mapping)
        changed[next(iter(changed))] = alternate.name
        with self.assertRaisesRegex(ConformanceError, "PROJECT_STATE_IMMUTABLE_ORIGINAL_REJECTED"):
            register_assets(self.store, self.source, changed, self.output, repository_root=self.repository)
        self.assertEqual(self.store.readiness_facts()["original_source_inventory"], "incomplete")

    def test_freeze_chronology_and_cardinality(self):
        journal = self.journal()
        with self.assertRaisesRegex(ConformanceError, "MODEL16_FREEZE_REQUIRED"):
            journal.begin_holdout("seed_2026")
        with self.assertRaisesRegex(ConformanceError, "MODEL16_FEATURE_FREEZE_REQUIRED"):
            journal.save_freeze({"baseline_id": "fictional", "challenger_id": None})
        feature = journal.save_feature_freeze({"features": ["fictional"]})
        with self.assertRaisesRegex(ConformanceError, "MODEL16_CHALLENGER_FREEZE_INVALID"):
            journal.save_freeze({"baseline_id": "fictional", "challenger_id": ["one", "two"], "feature_freeze_digest": feature})
        with self.assertRaisesRegex(ConformanceError, "MODEL16_FEATURE_FREEZE_MISMATCH"):
            journal.save_freeze({"baseline_id": "fictional", "challenger_id": None, "feature_freeze_digest": "0" * 64})
        frozen = journal.save_freeze({"baseline_id": "fictional", "challenger_id": None, "feature_freeze_digest": feature})
        with self.assertRaisesRegex(ConformanceError, "MODEL16_FREEZE_MISMATCH"):
            journal.begin_holdout("seed_2026", freeze_digest="0" * 64)
        self.assertEqual(journal.freeze_digest(), frozen)
        self.assertIsNone(journal.recover_result("seed_2026"))

    def test_saved_freezes_are_immutable_and_same_document_is_idempotent(self):
        journal, model, digest = self.frozen()
        self.assertEqual(StageJournal(self.output).save_freeze(model), digest)
        with self.assertRaisesRegex(ConformanceError, "MODEL16_FREEZE_IMMUTABLE"):
            journal.save_freeze({**model, "challenger_id": None})
        with self.assertRaisesRegex(ConformanceError, "MODEL16_FREEZE_IMMUTABLE"):
            journal.save_feature_freeze({"features": ["after-target-change"]})

    def test_interrupted_opening_is_consumed_even_without_result(self):
        journal, _, digest = self.frozen()
        ticket = journal.begin_holdout("seed_2026", freeze_digest=digest)
        del journal  # Simulate process loss after claim and before target access.
        recovered = StageJournal(self.output)
        with self.assertRaisesRegex(ConformanceError, "MODEL16_HOLDOUT_ALREADY_CONSUMED"):
            recovered.begin_holdout("seed_2026")
        self.assertIsNone(recovered.recover_result("seed_2026"))
        # The independent second source has a separate one-time permission.
        self.assertEqual(recovered.begin_holdout("pursued").stage, "pursued")
        self.assertEqual(ticket.freeze_digest, digest)

    def test_concurrent_opening_grants_only_one_ticket(self):
        self.frozen()
        def attempt(_):
            try:
                return StageJournal(self.output).begin_holdout("pursued")
            except ConformanceError as exc:
                return exc.code
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(attempt, range(6)))
        self.assertEqual(sum(isinstance(result, HoldoutTicket) for result in results), 1)
        self.assertEqual(results.count("MODEL16_HOLDOUT_ALREADY_CONSUMED"), 5)

    def test_completion_retry_recovers_without_any_new_opening(self):
        journal, _, _ = self.frozen()
        ticket = journal.begin_holdout("seed_2026")
        result = {"pooled": {"fictional_rank": 0.4}, "evaluated_models": ["fictional_baseline", "fictional_challenger"]}
        self.assertEqual(journal.complete_holdout(ticket, result), result)
        recovered = StageJournal(self.output)
        self.assertEqual(recovered.recover_result("seed_2026"), result)
        self.assertEqual(recovered.complete_holdout(ticket, result), result)
        with self.assertRaisesRegex(ConformanceError, "MODEL16_HOLDOUT_ALREADY_CONSUMED"):
            recovered.begin_holdout("seed_2026")
        with self.assertRaisesRegex(ConformanceError, "MODEL16_HOLDOUT_RESULT_IMMUTABLE"):
            recovered.complete_holdout(ticket, {"replacement": True})
        with self.assertRaisesRegex(ConformanceError, "MODEL16_HOLDOUT_TICKET_INVALID"):
            recovered.complete_holdout(replace(ticket, claim_id="forged"), result)

    def test_rollback_before_begin_commit_does_not_consume_access(self):
        journal, _, _ = self.frozen()
        original = journal._append
        def interrupted(connection, action, payload):
            original(connection, action, payload)
            raise RuntimeError("synthetic process interruption before commit")
        with patch.object(journal, "_append", side_effect=interrupted):
            with self.assertRaises(RuntimeError):
                journal.begin_holdout("seed_2026")
        self.assertEqual(StageJournal(self.output).begin_holdout("seed_2026").stage, "seed_2026")

    def test_journal_rejects_mutation_and_tampered_commitments(self):
        journal, _, _ = self.frozen()
        with closing(sqlite3.connect(journal.path)) as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("UPDATE events SET payload='{}' WHERE action='feature_freeze'")
            connection.execute("DROP TRIGGER event_no_update")
            connection.execute("UPDATE events SET payload='{}' WHERE action='feature_freeze'")
            connection.execute("CREATE TRIGGER event_no_update BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT, 'immutable journal'); END")
            connection.commit()
        with self.assertRaisesRegex(ConformanceError, "MODEL16_JOURNAL_TAMPERED"):
            StageJournal(self.output)

    def test_same_location_seed_and_pursued_keep_distinct_exact_membership(self):
        self.register()
        rows, candidates = self.observations(), self.candidates()
        document = register_evidence_package(self.store, self.output, rows, candidates)
        rerun = register_evidence_package(self.store, self.output, rows, candidates)
        self.assertEqual(document, rerun)
        self.assertEqual(document["bounded_readiness"], "READY")
        self.assertFalse(document["project_wide_completeness_claimed"])
        mapped = {row["observation_id"]: row for row in document["observations"]}
        seed, pursuit = mapped["fictional-seed-2025"], mapped["fictional-pursuit-2025"]
        self.assertEqual(seed["ledger_evidence_unit_id"], pursuit["ledger_evidence_unit_id"])
        self.assertNotEqual(seed["ledger_alias_id"], pursuit["ledger_alias_id"])
        self.assertEqual(pursuit["seedpoint_id"], None)
        self.assertEqual(seed["role"], "development")
        self.assertEqual(pursuit["role"], "pursued_test")
        with self.store._connect() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM source_row_aliases").fetchone()[0], 3)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM evidence_units").fetchone()[0], 2)
        self.assertEqual(self.store.readiness_facts()["evidence_ledger"], "incomplete")
        self.assertEqual(self.store.readiness_facts()["original_source_inventory"], "incomplete")

    def test_membership_rejects_holdout_development_invention_and_gaps(self):
        self.register()
        candidates = self.candidates()
        candidates["fictional_baseline"]["membership"]["fictional-pursuit-2025"] = "development"
        with self.assertRaisesRegex(ConformanceError, "MODEL16_MODEL_MEMBERSHIP_LEAKAGE"):
            register_evidence_package(self.store, self.output, self.observations(), candidates)
        candidates = self.candidates()
        del candidates["fictional_baseline"]["membership"]["fictional-seed-2026"]
        with self.assertRaisesRegex(ConformanceError, "MODEL16_MODEL_MEMBERSHIP_INCOMPLETE"):
            register_evidence_package(self.store, self.output, self.observations(), candidates)
        rows = self.observations()
        rows[2]["seedpoint_id"] = "invented-seed-id"
        with self.assertRaisesRegex(ConformanceError, "MODEL16_EVIDENCE_ROLE_LEAKAGE"):
            register_evidence_package(self.store, self.output, rows, self.candidates())

    def test_not_used_holdouts_do_not_create_use_events(self):
        self.register()
        candidates = self.candidates()
        for observation in ("fictional-seed-2026", "fictional-pursuit-2025"):
            candidates["fictional_baseline"]["membership"][observation] = "not_used"
        register_evidence_package(self.store, self.output, self.observations(), candidates)
        with self.store._connect() as connection:
            validation_events = connection.execute("SELECT COUNT(*) FROM evidence_events WHERE event_type='validation_used'").fetchone()[0]
        self.assertEqual(validation_events, 0)

    def test_excluded_unit_state_uses_all_aliases_and_preserves_location_identity(self):
        self.register()
        rows = self.observations()
        rows[1]["role"] = "excluded"
        rows[2]["role"] = "excluded"
        candidates = {"fictional_baseline": {"status": "candidate", "membership": {row["observation_id"]: row["role"] for row in rows}}}
        document = register_evidence_package(self.store, self.output, rows, candidates)
        by_observation = {row["observation_id"]: row for row in document["observations"]}
        with self.store._connect() as connection:
            statuses = dict(connection.execute("SELECT evidence_unit_id,status FROM evidence_units"))
            reconciliation = {row[0] for row in connection.execute("SELECT reconciliation_status FROM physical_locations")}
        self.assertEqual(statuses[by_observation["fictional-seed-2025"]["ledger_evidence_unit_id"]], "ready")
        self.assertEqual(statuses[by_observation["fictional-pursuit-2025"]["ledger_evidence_unit_id"]], "ready")
        self.assertEqual(statuses[by_observation["fictional-seed-2026"]["ledger_evidence_unit_id"]], "excluded")
        self.assertEqual(reconciliation, {"reconciled"})


if __name__ == "__main__":
    unittest.main()
