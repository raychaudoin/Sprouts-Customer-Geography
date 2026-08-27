"""Synthetic and static safeguards for MODEL-14 Overture Generation-2 evaluation."""

from __future__ import annotations

import copy
from contextlib import redirect_stdout
import io
import inspect
import json
import math
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from sprouts_customer_geography.model13.modeling import state_balanced_grouped_folds
from sprouts_customer_geography.model14 import generation2_experiment as generation2
from sprouts_customer_geography.model14 import cli as model14_cli
from sprouts_customer_geography.model14 import modeling as immutable_modeling
from sprouts_customer_geography.model14.modeling import fit_training_fold_preprocessor
from sprouts_customer_geography.model14.overture_generation2 import (
    FEATURE_IDS,
    INTENSITY_FEATURES,
    MIX_DIVERSITY_FEATURES,
)
from sprouts_customer_geography.pipe01.errors import ConformanceError


BASELINE_ID = "A_model13_reproduced_generation2"
ALL_ID = "B_model13_plus_all_generation2_commercial"
INTENSITY_ID = "C_model13_plus_generation2_intensity"
MIX_ID = "D_model13_plus_generation2_mix_diversity"


def _metric_block(offset: float = 0.0) -> dict[str, float]:
    return {
        "spearman": 0.60 + offset,
        "kendall_tau_b": 0.43 + offset,
        "log_rmse": 0.11 - offset / 10.0,
        "level_mae": 24_000.0 - offset * 1_000.0,
    }


def _candidate_result(
    terms: list[str],
    *,
    offset: float = 0.0,
    selected_commercial: str | None = None,
) -> dict[str, object]:
    aggregate = {
        domain: _metric_block(offset - index * 0.01)
        for index, domain in enumerate(generation2.DOMAINS)
    }
    ranges = {
        domain: {
            metric: {
                "minimum": value - (100.0 if metric == "level_mae" else 0.01),
                "maximum": value + (100.0 if metric == "level_mae" else 0.01),
            }
            for metric, value in metrics.items()
        }
        for domain, metrics in aggregate.items()
    }
    selection = {term: 0.8 for term in terms}
    sign_stability = {term: 0.75 for term in terms}
    coefficients = {term: 0.0 for term in terms}
    if selected_commercial is not None:
        coefficients[selected_commercial] = 0.2
    family_terms: dict[str, list[str]] = {}
    for term in terms:
        family = (
            "model13_accepted"
            if term not in FEATURE_IDS
            else "overture_" + generation2.FEATURE_SUBFAMILIES[term]
        )
        family_terms.setdefault(family, []).append(term)
    family_stability = {
        family: {
            "term_count": len(values),
            "selected_in_any_fold_count": len(values),
            "selected_in_every_fold_count": 0,
            "mean_selection_frequency": 0.8,
            "mean_dominant_sign_agreement": 0.75,
        }
        for family, values in family_terms.items()
    }
    return {
        "candidate_id": "synthetic",
        "terms": terms,
        "aggregate_oof": aggregate,
        "outer_fold_metric_ranges": ranges,
        "stability": {
            "selection_frequency": selection,
            "coefficient_sign_stability": sign_stability,
            "coefficient_standard_deviation": {term: 0.01 for term in terms},
            "stability_score": 0.78,
        },
        "feature_family_stability": family_stability,
        "mean_outer_effective_degrees_of_freedom": 4.0,
        "outer_effective_degrees_of_freedom_range": [3, 5],
        "final_standardized_coefficients": coefficients,
        "predictions": [101.0, 202.0],
        "analytical_observation_id": "synthetic-sensitive-row-id",
    }


def _paired_fold_fixture() -> tuple[list[dict[str, object]], list[float], list[float]]:
    rows: list[dict[str, object]] = []
    baseline: list[float] = []
    candidate: list[float] = []
    for state_index, state in enumerate(("MI", "WI")):
        for group_index in range(10):
            actual = 100.0 + state_index * 200.0 + group_index * 10.0
            group = f"{state}:synthetic-{group_index:02d}"
            for repeat in range(2):
                rows.append(
                    {
                        "analytical_observation_id": f"{group}:{repeat}",
                        "successor_physical_location_id": group,
                        "state": state,
                        "isolated_sales": actual,
                        "features": {"synthetic": float(group_index)},
                    }
                )
                baseline.append(1_000.0 - actual)
                candidate.append(actual)
    return rows, baseline, candidate


def _accepted_cohort_fixture() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for state, group_count, repeat_group_count in (
        ("MI", 82, 51),
        ("WI", 41, 22),
    ):
        for group_index in range(group_count):
            repeat_count = 2 if group_index < repeat_group_count else 1
            rows.extend(
                {
                    "successor_physical_location_id": (
                        f"{state}:synthetic-fitting-{group_index:03d}"
                    ),
                    "state": state,
                    "fitting_eligible": True,
                }
                for _ in range(repeat_count)
            )
    for group_index, repeat_count in enumerate((2, 2, 1)):
        rows.extend(
            {
                "successor_physical_location_id": (
                    f"MI:synthetic-excluded-{group_index:03d}"
                ),
                "state": "MI",
                "fitting_eligible": False,
                "fitting_exclusion_reason": (
                    "GEO05_ANCHOR_TRACT_MISSING_OR_AMBIGUOUS"
                ),
            }
            for _ in range(repeat_count)
        )
    return rows


def _safe_result_fixture() -> dict[str, object]:
    baseline_terms = ["accepted_one", "accepted_two"]
    candidates = {
        BASELINE_ID: _candidate_result(list(baseline_terms)),
        ALL_ID: _candidate_result(
            [*baseline_terms, *FEATURE_IDS],
            offset=0.03,
            selected_commercial=FEATURE_IDS[0],
        ),
        INTENSITY_ID: _candidate_result(
            [*baseline_terms, *INTENSITY_FEATURES],
            offset=0.02,
            selected_commercial=INTENSITY_FEATURES[0],
        ),
        MIX_ID: _candidate_result(
            [*baseline_terms, *MIX_DIVERSITY_FEATURES],
            offset=0.01,
            selected_commercial=MIX_DIVERSITY_FEATURES[0],
        ),
    }
    paired_metric = {
        metric: {
            "minimum": -0.01,
            "maximum": 0.02,
            "mean": 0.005,
            "median": 0.0,
            "improving_fold_count": 3,
            "nonworsening_fold_count": 4,
        }
        for metric in generation2.METRICS
    }
    paired_folds = {
        candidate_id: {
            domain: {
                "paired_outer_fold_count": 5,
                "candidate_minus_baseline": copy.deepcopy(paired_metric),
            }
            for domain in generation2.DOMAINS
        }
        for candidate_id in (ALL_ID, INTENSITY_ID, MIX_ID)
    }
    zero_delta = {
        domain: {metric: 0.0 for metric in generation2.METRICS}
        for domain in generation2.DOMAINS
    }
    return {
        "source": {
            "publisher": "Overture Maps Foundation",
            "release": "2026-07-22.0",
            "schema_version": "v1.18.0",
            "source_authority_status": "EXPERIMENTAL",
        },
        "frozen_commercial_feature_catalog": [
            {
                "feature_id": FEATURE_IDS[0],
                "subfamily": "intensity_count",
                "aggregation": "synthetic aggregate",
            }
        ],
        "frozen_rules": {"radius_m": 8046.72, "additional_radius_search": False},
        "baseline_terms": baseline_terms,
        "baseline_reproduction": {"state": "MATCH"},
        "tract_coverage_and_missingness": {
            "tract_count": 4559,
            "michigan_tract_count": 3017,
            "wisconsin_tract_count": 1542,
            "tracts_dropped": False,
        },
        "development_anchor_coverage": {
            "all_commercial": {
                "candidate_feature_count": 15,
                "by_state": {
                    "MI": {"physical_location_count": 82},
                    "WI": {"physical_location_count": 41},
                },
            }
        },
        "candidates": candidates,
        "strongest_expanded_candidate_id": ALL_ID,
        "paired_fold_stability": paired_folds,
        "expanded_candidate_disposition_screen": {
            candidate_id: {
                "disposition": "possible improvement",
                "evidence": ["Synthetic aggregate evidence."],
            }
            for candidate_id in (ALL_ID, INTENSITY_ID, MIX_ID)
        },
        "paired_outlier_sensitivity": {
            "selection_basis": "synthetic maximum grouped error",
            "same_location_removed_from_baseline_and_candidate": True,
            "excluded_physical_location_count": 1,
            "retained_physical_location_count": 122,
            "candidate_maximum_physical_location_absolute_log_error": 0.2,
            "candidate_minus_baseline_before_removal": {
                metric: 0.01 for metric in generation2.METRICS
            },
            "candidate_minus_baseline_after_removal": {
                metric: 0.005 for metric in generation2.METRICS
            },
            "incremental_metric_delta_change_after_removal": {
                metric: -0.005 for metric in generation2.METRICS
            },
            "protected_location_identity_disclosed": False,
        },
        "ablations": {
            "only_frozen_primary_candidates_reused": True,
            "all_commercial_family_ablations": {
                "remove_intensity_count": {
                    "removed_feature_count": 11,
                    "all_minus_ablation_metric_delta": zero_delta,
                },
                "remove_mix_diversity": {
                    "removed_feature_count": 4,
                    "all_minus_ablation_metric_delta": zero_delta,
                },
            },
        },
        "evidence_disposition": "possible improvement",
        "disposition_evidence": [
            "Synthetic aggregate fixture; Generation 2 remains exploratory."
        ],
        # These simulate protected-only fields that must not flow into the safe result.
        "predictions": [1.0, 2.0],
        "rows": [{"isolated_sales": 999.0}],
        "successor_physical_location_id": "MI:synthetic-sensitive",
        "canonical_latitude": 42.0,
        "canonical_longitude": -84.0,
        "registry_locator": "synthetic-local-authority",
        "protected_content_sha256": "synthetic-protected-digest",
    }


class Model14OvertureGeneration2ExperimentTests(unittest.TestCase):
    def test_pre_h_report_records_exact_safe_generation2_result(self) -> None:
        repository_root = Path(__file__).resolve().parents[1]
        report = (
            repository_root
            / "docs"
            / "experiments"
            / "MODEL_14_OVERTURE_GENERATION2_PRE_H_REPORT.md"
        ).read_text(encoding="utf-8")

        for required in (
            "2026-07-22.0",
            "v1.18.0",
            "Baseline reproduction: **MATCH**",
            "Evidence disposition: **possible improvement**",
            "0.6599",
            "0.5297",
            "0.7548",
            "0.4793",
            "0.1010",
            "22,540.35",
            "MASTER CONTROL ROOM: Sprouts Customer Geography",
        ):
            self.assertIn(required, report)

        report_lower = report.lower()
        for forbidden in (
            "successor_physical_location_id",
            "analytical_observation_id",
            "isolated_sales",
            "canonical_latitude",
            "canonical_longitude",
            "model13_authority_registry",
            "protected_content_sha256",
        ):
            self.assertNotIn(forbidden, report_lower)

    def test_exact_accepted_development_cohort_is_required(self) -> None:
        rows = _accepted_cohort_fixture()
        generation2._verify_development_cohort(rows)
        changed = copy.deepcopy(rows)
        changed[-1]["fitting_exclusion_reason"] = "synthetic-other-reason"
        with self.assertRaisesRegex(
            ConformanceError,
            "MODEL14_G2_DEVELOPMENT_COHORT_MISMATCH",
        ):
            generation2._verify_development_cohort(changed)

    def test_exact_frozen_candidate_terms_exclude_generation1_combinations(self) -> None:
        baseline = ["accepted_one", "accepted_two"]
        self.assertEqual(
            generation2.CANDIDATE_SUBFAMILIES,
            {
                BASELINE_ID: (),
                ALL_ID: ("intensity_count", "mix_diversity"),
                INTENSITY_ID: ("intensity_count",),
                MIX_ID: ("mix_diversity",),
            },
        )
        self.assertEqual(generation2._candidate_terms(baseline, ()), baseline)
        self.assertEqual(
            generation2._candidate_terms(
                baseline,
                ("intensity_count", "mix_diversity"),
            ),
            [*baseline, *FEATURE_IDS],
        )
        self.assertEqual(
            generation2._candidate_terms(baseline, ("intensity_count",)),
            [*baseline, *INTENSITY_FEATURES],
        )
        self.assertEqual(
            generation2._candidate_terms(baseline, ("mix_diversity",)),
            [*baseline, *MIX_DIVERSITY_FEATURES],
        )
        self.assertTrue(all(feature.startswith("overture_") for feature in FEATURE_IDS))
        self.assertNotIn("lodes", json.dumps(generation2.CANDIDATE_SUBFAMILIES))

        authority = {
            "candidate_sets": {
                key: list(value)
                for key, value in generation2.CANDIDATE_SUBFAMILIES.items()
            },
            "generation1_combination_justified": False,
            "generation": 2,
            "exploratory": True,
            "confirmatory": False,
        }
        generation2._verify_candidate_authority(authority)
        changed = copy.deepcopy(authority)
        changed["generation1_combination_justified"] = True
        with self.assertRaisesRegex(
            ConformanceError,
            "MODEL14_G2_CANDIDATE_AUTHORITY_MISMATCH",
        ):
            generation2._verify_candidate_authority(changed)

    def test_public_checkpoint_and_commitment_gates_precede_resolver(self) -> None:
        arguments = {
            "repository_root": Path.cwd(),
            "registry_path": Path("synthetic-registry-never-opened"),
            "public_freeze_dir": Path("synthetic-public-freeze-one"),
            "verification_freeze_dir": Path("synthetic-public-freeze-two"),
            "output_dir": Path("outputs/synthetic-generation2-never-created"),
        }
        with patch.object(
            generation2,
            "_verify_public_checkpoint",
            side_effect=ConformanceError(
                "MODEL14_G2_PUBLIC_CHECKPOINT_NOT_ANCESTOR",
                "synthetic gate failure",
            ),
        ), patch.object(
            generation2.ProtectedHandleResolver,
            "load",
        ) as resolver:
            with self.assertRaisesRegex(
                ConformanceError,
                "MODEL14_G2_PUBLIC_CHECKPOINT_NOT_ANCESTOR",
            ):
                generation2.execute_generation2_protected_experiment(**arguments)
            resolver.assert_not_called()

        public_report = {
            "content_sha256": generation2.GENERATION2_FREEZE_SEMANTIC_CONTENT_SHA256,
            "files": {
                generation2.COMPONENT_FILENAME: {
                    "sha256": generation2.GENERATION2_COMPONENT_FILE_SHA256,
                },
                generation2.MATRIX_FILENAME: {
                    "sha256": generation2.GENERATION2_MATRIX_FILE_SHA256,
                },
            },
        }
        with patch.object(
            generation2,
            "_verify_public_checkpoint",
            return_value={"state": "VERIFIED_ANCESTOR"},
        ), patch.object(
            generation2,
            "verify_generation2_commitment_against_freezes",
            return_value={
                "state": "GENERATION2_TARGET_BLIND_COMMITMENT_VERIFIED",
                "generation2_target_values_accessed": 0,
                "generation2_protected_anchor_rows_accessed": 0,
            },
        ), patch.object(
            generation2,
            "load_generation2_public_freeze",
            return_value=SimpleNamespace(report=public_report),
        ), patch.object(
            generation2,
            "load_generation2_contract",
            return_value={"content_sha256": "synthetic-wrong-contract-hash"},
        ), patch.object(
            generation2,
            "load_generation2_commitment",
            return_value={
                "content_sha256": generation2.GENERATION2_COMMITMENT_CONTENT_SHA256,
            },
        ), patch.object(
            generation2.ProtectedHandleResolver,
            "load",
        ) as resolver:
            with self.assertRaisesRegex(
                ConformanceError,
                "MODEL14_G2_EXACT_PUBLIC_FREEZE_MISMATCH",
            ):
                generation2.execute_generation2_protected_experiment(**arguments)
            resolver.assert_not_called()

        with patch.object(
            generation2,
            "_verify_public_checkpoint",
            return_value={"state": "VERIFIED_ANCESTOR"},
        ), patch.object(
            generation2,
            "verify_generation2_commitment_against_freezes",
            side_effect=ConformanceError(
                "MODEL14_G2_COMMITMENT_FREEZE_MISMATCH",
                "synthetic commitment failure",
            ),
        ), patch.object(
            generation2.ProtectedHandleResolver,
            "load",
        ) as resolver:
            with self.assertRaisesRegex(
                ConformanceError,
                "MODEL14_G2_COMMITMENT_FREEZE_MISMATCH",
            ):
                generation2.execute_generation2_protected_experiment(**arguments)
            resolver.assert_not_called()

    def test_component_anchor_and_ready_before_target_order_are_explicit(self) -> None:
        anchor_source = inspect.getsource(generation2._accepted_anchor_features)
        self.assertIn("component_rows", anchor_source)
        self.assertIn("aggregate_commercial_features", anchor_source)
        self.assertNotIn("public_freeze.rows", anchor_source)

        writer_source = inspect.getsource(generation2._write_anchor_freeze)
        self.assertLess(
            writer_source.index("write_json_exclusive(package_path"),
            writer_source.index("write_json_exclusive(ready_path"),
        )
        self.assertLess(
            writer_source.index("write_json_exclusive(ready_path"),
            writer_source.index("persisted = _load_object(ready_path"),
        )

        execution_source = inspect.getsource(
            generation2.execute_generation2_protected_experiment
        )
        self.assertLess(
            execution_source.index("verify_generation2_commitment_against_freezes("),
            execution_source.index("ProtectedHandleResolver.load("),
        )
        self.assertLess(
            execution_source.index("_write_anchor_freeze("),
            execution_source.index("verify_persisted_binding("),
        )
        self.assertLess(
            execution_source.index("anchor_ready.is_file()"),
            execution_source.index("_development_rows("),
        )

    def test_paired_fold_deltas_use_identical_fixed_groups(self) -> None:
        rows, baseline, candidate = _paired_fold_fixture()
        first = generation2._paired_fold_metric_deltas(
            rows,
            baseline,
            candidate,
        )
        second = generation2._paired_fold_metric_deltas(
            rows,
            baseline,
            candidate,
        )
        self.assertEqual(first, second)
        assignment = state_balanced_grouped_folds(rows, 5)
        self.assertEqual(len(assignment), 20)
        self.assertEqual(set(assignment.values()), set(range(5)))
        for domain in generation2.DOMAINS:
            self.assertEqual(first[domain]["paired_outer_fold_count"], 5)
            for metric in generation2.METRICS:
                summary = first[domain]["candidate_minus_baseline"][metric]
                self.assertEqual(summary["improving_fold_count"], 5)
                self.assertEqual(summary["nonworsening_fold_count"], 5)

    def test_paired_outlier_removes_same_location_without_identity(self) -> None:
        rows = [
            {
                "successor_physical_location_id": group,
                "state": "MI",
                "isolated_sales": actual,
            }
            for group, actual in (
                ("MI:synthetic-a", 100.0),
                ("MI:synthetic-b", 200.0),
                ("MI:synthetic-c", 300.0),
            )
        ]
        result = generation2._paired_outlier_sensitivity(
            rows,
            [90.0, 190.0, 290.0],
            [100.0, 210.0, 2_000.0],
        )
        self.assertTrue(result["same_location_removed_from_baseline_and_candidate"])
        self.assertEqual(result["excluded_physical_location_count"], 1)
        self.assertEqual(result["retained_physical_location_count"], 2)
        self.assertFalse(result["protected_location_identity_disclosed"])
        serialized = json.dumps(result, sort_keys=True)
        for identity in ("MI:synthetic-a", "MI:synthetic-b", "MI:synthetic-c"):
            self.assertNotIn(identity, serialized)

    def test_baseline_reproduction_is_delegated_and_fails_closed(self) -> None:
        synthetic_candidate = {
            "aggregate_oof": {
                domain: _metric_block() for domain in generation2.DOMAINS
            },
            "predictions": [],
        }
        failure = ConformanceError(
            "MODEL14_BASELINE_REPRODUCTION_FAILED",
            "synthetic baseline mismatch",
        )
        with patch.object(
            generation2,
            "nested_grouped_oof",
            return_value=synthetic_candidate,
        ) as nested, patch.object(
            generation2,
            "_verify_baseline_reproduction",
            side_effect=failure,
        ) as verify:
            with self.assertRaisesRegex(
                ConformanceError,
                "MODEL14_BASELINE_REPRODUCTION_FAILED",
            ):
                generation2._run_candidates([], ["accepted_one"])
        self.assertEqual(nested.call_count, 4)
        verify.assert_called_once_with(synthetic_candidate)
        called_ids = [call.args[1] for call in nested.call_args_list]
        self.assertEqual(called_ids, list(generation2.CANDIDATE_SUBFAMILIES))

    def test_evidence_classification_requires_paired_fold_stability(self) -> None:
        baseline = _candidate_result(["accepted_one"])
        strongest = _candidate_result(
            ["accepted_one", FEATURE_IDS[0]],
            offset=0.04,
            selected_commercial=FEATURE_IDS[0],
        )
        outlier = {
            "incremental_metric_delta_change_after_removal": {
                "spearman": 0.01,
            }
        }
        fold_summary = {
            domain: {
                "candidate_minus_baseline": {
                    "spearman": {
                        "improving_fold_count": 3,
                        "nonworsening_fold_count": 4,
                    }
                }
            }
            for domain in generation2.DOMAINS
        }
        disposition, evidence = generation2._classify_evidence(
            baseline,
            strongest,
            outlier,
            fold_summary,
        )
        self.assertEqual(disposition, "material improvement")
        self.assertTrue(any("improving/nonworsening folds" in item for item in evidence))

        unstable = copy.deepcopy(fold_summary)
        unstable["pooled"]["candidate_minus_baseline"]["spearman"].update(
            improving_fold_count=1,
            nonworsening_fold_count=2,
        )
        disposition, _ = generation2._classify_evidence(
            baseline,
            strongest,
            outlier,
            unstable,
        )
        self.assertEqual(disposition, "no credible improvement")

    def test_strongest_selection_prefers_credible_balanced_candidate(self) -> None:
        baseline = _candidate_result(["accepted_one"])
        pooled_only = _candidate_result(
            ["accepted_one", *FEATURE_IDS],
            offset=0.05,
            selected_commercial=FEATURE_IDS[0],
        )
        balanced = _candidate_result(
            ["accepted_one", *INTENSITY_FEATURES],
            offset=0.03,
            selected_commercial=INTENSITY_FEATURES[0],
        )
        weaker = _candidate_result(
            ["accepted_one", *MIX_DIVERSITY_FEATURES],
            offset=0.01,
            selected_commercial=MIX_DIVERSITY_FEATURES[0],
        )
        pooled_only["aggregate_oof"]["wisconsin"]["spearman"] = 0.30
        candidates = {
            BASELINE_ID: baseline,
            ALL_ID: pooled_only,
            INTENSITY_ID: balanced,
            MIX_ID: weaker,
        }
        dispositions = {
            ALL_ID: {"disposition": "no credible improvement"},
            INTENSITY_ID: {"disposition": "material improvement"},
            MIX_ID: {"disposition": "possible improvement"},
        }
        self.assertEqual(
            generation2._strongest_expanded(candidates, dispositions),
            INTENSITY_ID,
        )

    def test_disclosure_safe_result_is_exploratory_and_omits_protected_detail(self) -> None:
        protected = _safe_result_fixture()
        safe = generation2.build_generation2_disclosure_safe_result(protected)
        self.assertTrue(safe["exploratory"])
        self.assertFalse(safe["confirmatory"])
        self.assertEqual(safe["interpretation_posture"], "NOT_CONFIRMATORY")
        self.assertEqual(safe["review_state"], "NOT_REVIEWED")
        self.assertTrue(safe["accepted_predecessor"]["accepted_and_unchanged"])
        serialized = json.dumps(safe, sort_keys=True)
        for token in (
            "predictions",
            "rows",
            "successor_physical_location_id",
            "analytical_observation_id",
            "isolated_sales",
            "canonical_latitude",
            "canonical_longitude",
            "registry_locator",
            "protected_content_sha256",
            "synthetic-sensitive",
            "synthetic-protected-digest",
        ):
            self.assertNotIn(token, serialized)

        unsafe = copy.deepcopy(protected)
        unsafe["source"]["path"] = "synthetic-local-source"
        with self.assertRaisesRegex(
            ConformanceError,
            "MODEL14_G2_DISCLOSURE_SAFE_RESULT_INVALID",
        ):
            generation2.build_generation2_disclosure_safe_result(unsafe)

    def test_generation2_cli_returns_only_safe_aggregate_fields(self) -> None:
        safe = generation2.build_generation2_disclosure_safe_result(
            _safe_result_fixture()
        )
        output = io.StringIO()
        with patch.dict(
            os.environ,
            {"MODEL13_AUTHORITY_REGISTRY": "synthetic-local-registry"},
        ), patch.object(
            model14_cli,
            "execute_generation2_protected_experiment",
            return_value=safe,
        ), redirect_stdout(output):
            code = model14_cli.main(
                [
                    "protected-overture-generation2-experiment",
                    "--public-freeze",
                    "synthetic-public-one",
                    "--verification-freeze",
                    "synthetic-public-two",
                    "--output",
                    "outputs/synthetic-generation2-cli",
                ]
            )
        self.assertEqual(code, 0)
        result = json.loads(output.getvalue())
        self.assertEqual(result["generation"], 2)
        self.assertTrue(result["exploratory"])
        self.assertFalse(result["confirmatory"])
        self.assertFalse(result["protected_details_disclosed"])
        serialized = json.dumps(result, sort_keys=True)
        for token in (
            "synthetic-local-registry",
            "successor_physical_location_id",
            "isolated_sales",
            "canonical_latitude",
            "canonical_longitude",
        ):
            self.assertNotIn(token, serialized)

    def test_group_and_training_fold_invariants_reuse_immutable_modeling(self) -> None:
        self.assertIs(
            generation2.nested_grouped_oof,
            immutable_modeling.nested_grouped_oof,
        )
        rows = []
        for group, value, repeats in (
            ("MI:synthetic-a", 1.0, 7),
            ("MI:synthetic-b", 3.0, 1),
            ("MI:synthetic-c", 100.0, 1),
        ):
            rows.extend(
                {
                    "successor_physical_location_id": group,
                    "features": {"synthetic": value},
                }
                for _ in range(repeats)
            )
        preprocessor = fit_training_fold_preprocessor(rows, ["synthetic"])
        self.assertEqual(preprocessor.training_group_count, 3)
        self.assertEqual(preprocessor.medians["synthetic"], 3.0)

        modeling_source = inspect.getsource(immutable_modeling.nested_grouped_oof)
        self.assertIn("MODEL14_PHYSICAL_LOCATION_LEAKAGE", modeling_source)
        self.assertIn('"preprocessing_fit_scope": "outer_training_groups_only"', modeling_source)
        self.assertIn('"inner_preprocessing_fit_scope": "inner_training_groups_only"', modeling_source)


if __name__ == "__main__":
    unittest.main()
