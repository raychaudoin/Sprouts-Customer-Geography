"""Synthetic orchestration: the persisted freeze, not an argument, gates targets."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import numpy as np

from sprouts_customer_geography.model16 import workflow as w
from sprouts_customer_geography.model16.evidence import StageJournal, OUTPUT_ID
from sprouts_customer_geography.model16.modeling import load_library, SPATIAL_TERMS, run_development
from sprouts_customer_geography.pipe01.errors import ConformanceError


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="model16-fictional-workflow-")
        self.output = Path(self.temp.name).resolve()
        self.paths = {OUTPUT_ID: self.output}
        self.journal = StageJournal(self.output)
        self.journal.save_feature_freeze({"synthetic": True})
        features = [{"feature_id": name, "family": "household_mass", "baseline": True} for name in SPATIAL_TERMS]
        self.identity = {"rows": [], "ready": True}
        self.package = {"catalog": {"features": features}, "matrix": {}, "eligibility": {}}
        for state in ("MI", "WI"):
            for i in range(6):
                for year, role in ((2024, "development"), (2025, "development"), (2026, "temporal_test")):
                    self.add(state, i, year, role)
            for i in range(6, 9):
                self.add(state, i, 2025, "pursued_test")
        self.library = deepcopy(load_library())
        self.library.update(outer_folds=3, inner_folds=2)
        self.library["candidates"] = [self.library["candidates"][0], self.library["candidates"][1]]
        self.library["candidates"][0]["grid"] = {"alpha": [.1], "l1_ratio": [.5]}
        self.library["candidates"][1]["grid"] = {"alpha": [10.]}
        self.library["family_experiments"]["alpha_grid"] = [10.]

    def add(self, state, i, year, role):
        key, group = f"FICTIONAL_{state}_{i}_{year}_{role}", f"FICTIONAL_{state}_{i}"
        self.identity["rows"].append({"observation_id": key, "physical_location_id": group, "state": state,
            "forecast_year": year, "role": role, "evidence_class": "PURSUED_SITE" if role == "pursued_test" else "SEED_POINT", "msa": "FICTIONAL_MARKET_"+state})
        self.package["matrix"][key] = {"features": dict(zip(SPATIAL_TERMS, (3+i*.2, .3+i*.01, np.sin(i))))}
        self.package["eligibility"][key] = {"eligible": True, "reason": "COMPUTABLE"}

    def tearDown(self):
        self.temp.cleanup()

    def access(self, store, paths, identity, rows, stage, freeze_id=None):
        if stage != "development":
            self.assertIsNotNone(freeze_id)
            self.assertEqual(freeze_id, self.journal.freeze_digest())
        return {"stage": stage, "values": {row["observation_id"]: 100.+i*10 for i, row in enumerate(rows)}, "audits": {"fictional": {"impacted_values_read": 0}}}

    def verified(self):
        return patch.object(w, "verify_feature_freeze", return_value=(self.journal, self.identity, self.package))

    def test_complete_generation_and_rerun_never_reopens_holdouts(self):
        with self.verified(), patch.object(w, "read_exact_targets", side_effect=self.access) as access, patch("sprouts_customer_geography.model16.modeling.run_development", side_effect=lambda data, **kw: run_development(data, self.library)):
            developed = w.develop(Path.cwd(), Mock(), self.paths)
            self.assertTrue(developed["ready"])
            self.assertEqual(access.call_count, 1)
            w.holdout(Path.cwd(), Mock(), self.paths, "seed_2026")
            w.holdout(Path.cwd(), Mock(), self.paths, "pursued")
            self.assertEqual(access.call_count, 3)
            replay = w.holdout(Path.cwd(), Mock(), self.paths, "seed_2026")
            self.assertFalse(replay["targets_reopened"])
            w.develop(Path.cwd(), Mock(), self.paths)
            self.assertEqual(access.call_count, 3)
        self.assertIsNotNone(self.journal.recover_result("seed_2026"))
        self.assertIsNotNone(self.journal.recover_result("pursued"))

    def test_no_target_opening_without_persisted_model_freeze(self):
        with self.verified(), patch.object(w, "read_exact_targets") as access:
            with self.assertRaisesRegex(ConformanceError, "MODEL16_FREEZE_REQUIRED"):
                w.holdout(Path.cwd(), Mock(), self.paths, "seed_2026")
            access.assert_not_called()

    def test_preflight_failure_does_not_consume_opening(self):
        with self.verified(), patch.object(w, "read_exact_targets", side_effect=self.access), patch("sprouts_customer_geography.model16.modeling.run_development", side_effect=lambda data, **kw: run_development(data, self.library)):
            w.develop(Path.cwd(), Mock(), self.paths)
        with self.verified(), patch.object(w, "read_exact_targets") as access, patch("sprouts_customer_geography.model16.modeling.evaluate_frozen", side_effect=ValueError("FICTIONAL_PREFLIGHT_FAILURE")):
            with self.assertRaisesRegex(ValueError, "FICTIONAL_PREFLIGHT_FAILURE"):
                w.holdout(Path.cwd(), Mock(), self.paths, "seed_2026")
            access.assert_not_called()
        self.journal.begin_holdout("seed_2026")

    def test_nonfinite_preflight_does_not_consume_opening(self):
        with self.verified(), patch.object(w, "read_exact_targets", side_effect=self.access), patch("sprouts_customer_geography.model16.modeling.run_development", side_effect=lambda data, **kw: run_development(data, self.library)):
            w.develop(Path.cwd(), Mock(), self.paths)
        with self.verified(), patch.object(w, "read_exact_targets") as access, patch("sprouts_customer_geography.model16.modeling.evaluate_frozen", return_value={"prediction": float("inf")}):
            with self.assertRaises(ValueError):
                w.holdout(Path.cwd(), Mock(), self.paths, "seed_2026")
            access.assert_not_called()
        self.journal.begin_holdout("seed_2026")

    def test_recovered_model_requires_same_feature_freeze(self):
        with self.verified(), patch.object(w, "read_exact_targets", side_effect=self.access), patch("sprouts_customer_geography.model16.modeling.run_development", side_effect=lambda data, **kw: run_development(data, self.library)):
            w.develop(Path.cwd(), Mock(), self.paths)
        path = self.output / "development-result-integrity.json"
        commitment = json.loads(path.read_text())
        commitment["feature_freeze_digest"] = "fictional-other-freeze"
        path.write_text(json.dumps(commitment))
        with self.verified(), patch.object(w, "read_exact_targets") as access:
            with self.assertRaisesRegex(ConformanceError, "MODEL16_DEVELOPMENT_FREEZE_MISMATCH"):
                w.develop(Path.cwd(), Mock(), self.paths)
            access.assert_not_called()

    def test_consumed_failed_read_cannot_be_retried(self):
        with self.verified(), patch.object(w, "read_exact_targets", side_effect=self.access), patch("sprouts_customer_geography.model16.modeling.run_development", side_effect=lambda data, **kw: run_development(data, self.library)):
            w.develop(Path.cwd(), Mock(), self.paths)
        with self.verified(), patch.object(w, "read_exact_targets", side_effect=ValueError("FICTIONAL_READ_FAILURE")):
            with self.assertRaisesRegex(ValueError, "FICTIONAL_READ_FAILURE"):
                w.holdout(Path.cwd(), Mock(), self.paths, "pursued")
        with self.verified(), patch.object(w, "read_exact_targets") as access:
            with self.assertRaisesRegex(ConformanceError, "MODEL16_HOLDOUT_ALREADY_CONSUMED"):
                w.holdout(Path.cwd(), Mock(), self.paths, "pursued")
            access.assert_not_called()

    def test_noncomputable_observations_stay_accounted_but_not_fitted(self):
        row = self.identity["rows"][0]
        self.package["eligibility"][row["observation_id"]]["eligible"] = False
        all_rows = w.selected_rows(self.identity, self.package, "development", eligible_only=False)
        eligible = w.selected_rows(self.identity, self.package, "development", eligible_only=True)
        self.assertEqual(len(all_rows)-len(eligible), 1)
        self.assertEqual(len(self.identity["rows"]), 42)

    def test_protected_output_is_immutable_and_finite(self):
        path = self.output / "fictional.json"
        w.write_private(path, {"finite": 1})
        w.write_private(path, {"finite": 1})
        with self.assertRaisesRegex(ConformanceError, "MODEL16_OUTPUT_REPLAY_MISMATCH"):
            w.write_private(path, {"finite": 2})
        with self.assertRaises(ValueError):
            w.write_private(self.output / "nonfinite.json", {"x": float("nan")})

    def test_catalog_is_unique_and_explicitly_excludes_protected_inputs(self):
        catalog = w.combined_catalog(Path.cwd())
        names = [item["feature_id"] for item in catalog["features"]]
        self.assertEqual(len(names), len(set(names)))
        self.assertIn("no direct age, sex, race", catalog["protected_characteristics"])
        self.assertTrue(all(item["family"] and item["transform"] for item in catalog["features"]))
        self.assertEqual(catalog, json.loads(json.dumps(catalog)))

    def test_target_blind_preflight_checks_every_split_and_both_holdouts(self):
        from sprouts_customer_geography.model16.preflight import validate_preflight
        result = validate_preflight(self.identity, self.package, self.library)
        self.assertEqual(result["split_checks"], 13)
        self.assertEqual(result["real_targets_read"], 0)

    def test_preflight_detects_missing_only_in_validation_without_target_access(self):
        from sprouts_customer_geography.model16.preflight import validate_preflight
        from sprouts_customer_geography.model16.modeling import ModelingError
        row = next(row for row in self.identity["rows"] if row["role"] == "temporal_test")
        self.package["matrix"][row["observation_id"]]["features"][SPATIAL_TERMS[0]] = None
        with self.assertRaisesRegex(ModelingError, "MODEL16_BASELINE_RETAINED_FEATURE_MISSING"):
            validate_preflight(self.identity, self.package, self.library)


class FeatureFreezeGuardTests(unittest.TestCase):
    def test_prior_true_or_uncertain_target_read_blocks_first_freeze(self):
        for state in ("true", "uncertain"):
            with patch.object(w, "StageJournal") as journal, patch.object(w, "read_json") as read:
                journal.return_value._verify.return_value = {}
                store = Mock()
                store.event_states.return_value = {"machine_target_read": state}
                with self.assertRaisesRegex(ConformanceError, "MODEL16_TARGETS_READ_BEFORE_FEATURE_FREEZE"):
                    w.feature_freeze(Path.cwd(), store, {OUTPUT_ID: Path("fictional-unused")})
                read.assert_not_called()

    def test_existing_freeze_replay_checks_commitments_without_resetting_history(self):
        with patch.object(w, "StageJournal") as journal, patch.object(w, "verify_feature_freeze") as verify:
            journal.return_value._verify.return_value = {"feature_freeze": {"fictional": True}}
            store = Mock()
            result = w.feature_freeze(Path.cwd(), store, {OUTPUT_ID: Path("fictional-unused")})
            self.assertTrue(result["recovered_completed_freeze"])
            self.assertFalse(result["targets_reopened"])
            verify.assert_called_once()
            store.event_states.assert_not_called()


if __name__ == "__main__":
    unittest.main()
