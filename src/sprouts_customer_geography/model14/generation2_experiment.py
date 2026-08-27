"""Protected exploratory MODEL-14 Generation-2 evaluation.

The public Overture definitions and two tract freezes are verified before any
accepted protected resolver is opened.  The protected development-anchor
feature package is then recomputed from frozen tract components and sealed
with its own READY marker before the already-consumed MODEL-13 targets are
loaded.  Nothing in this module changes the frozen public generation.
"""

from __future__ import annotations

import copy
import json
import math
import subprocess
from pathlib import Path
from statistics import median
from typing import Any, Mapping, Sequence

from sprouts_customer_geography.geo05.materialization import (
    evaluate_anchor_package,
    load_support_package,
)
from sprouts_customer_geography.model09.features import _anchor_tract
from sprouts_customer_geography.model09.modeling import grouped_metrics
from sprouts_customer_geography.model13.modeling import (
    GROUP_FIELD,
    SPATIAL_TERMS,
    state_balanced_grouped_folds,
)
from sprouts_customer_geography.model13.resolver import ProtectedHandleResolver
from sprouts_customer_geography.model13.workflow import (
    _accepted_model12_packages,
    _development_rows,
    _feature_freeze_package,
    _load_object,
    _upstream_resolvers,
    verify_repository_authority as verify_model13_repository_authority,
)
from sprouts_customer_geography.pipe01.canonical import (
    content_digest,
    file_sha256,
    write_json_exclusive,
)
from sprouts_customer_geography.pipe01.errors import ConformanceError, require
from sprouts_customer_geography.pipe01.production import Geo03ProductionTransformer
from sprouts_customer_geography.pipe01.spatial import (
    parse_internal_point,
    project_internal_point,
)
from sprouts_customer_geography.pipe05.binding import (
    BINDING_FILENAME,
    verify_persisted_binding,
)

from .experiment import (
    _assert_output_path,
    _attach_features,
    _coordinates_by_group,
    _finite,
    _verify_baseline_reproduction,
)
from .modeling import nested_grouped_oof
from .overture_generation2 import (
    COMPONENT_FILENAME,
    FEATURE_IDS,
    FEATURE_SUBFAMILIES,
    INTENSITY_FEATURES,
    MATRIX_FILENAME,
    MIX_DIVERSITY_FEATURES,
    aggregate_commercial_features,
    load_generation2_commitment,
    load_generation2_contract,
    load_generation2_public_freeze,
    verify_generation2_commitment_against_freezes,
)


GENERATION2_PUBLIC_CHECKPOINT = "3a72aff98a5f916f6df0de743d5d90fa025233c3"
GENERATION2_CONTRACT_CONTENT_SHA256 = (
    "a3e4d2797a212a268c5413a8bd0415d38c6d8414e1e8810033711c816c86e2a7"
)
GENERATION2_COMMITMENT_CONTENT_SHA256 = (
    "d9c5c1c30a8701e104609271b02a8b1ede0aa7b8e903419a309ae8db31abdff3"
)
GENERATION2_COMPONENT_FILE_SHA256 = (
    "1de6160abcd62046d666ba3727d4267c884213e90ff669b189b2678eddf64c42"
)
GENERATION2_MATRIX_FILE_SHA256 = (
    "b1b9faa9186f99b61026539e2e404d998f0b7583b1713fff3f53a9a324873a8a"
)
GENERATION2_FREEZE_SEMANTIC_CONTENT_SHA256 = (
    "5b00f4c22f384a6b6a6793f540a520d66ec44c66b41411d1b147858639452e80"
)
GENERATION2_EXPERIMENT_PACKAGE_ID = (
    "MODEL14_OVERTURE_GENERATION2_PROTECTED_EXPLORATORY_EXPERIMENT_V1"
)
GENERATION2_ANCHOR_FREEZE_PACKAGE_ID = (
    "MODEL14_OVERTURE_GENERATION2_TARGET_BLIND_DEVELOPMENT_ANCHOR_FREEZE_V1"
)
GENERATION2_SAFE_RESULT_PACKAGE_ID = (
    "MODEL14_OVERTURE_GENERATION2_DISCLOSURE_SAFE_PRE_H_RESULT_V1"
)
GENERATION2_ANCHOR_DIRECTORY = "generation2_anchor_feature_freeze"
GENERATION2_ANCHOR_FILENAME = (
    "model14_overture_generation2_target_blind_development_anchor_features.json"
)
GENERATION2_PROTECTED_RESULT_FILENAME = (
    "model14_overture_generation2_protected_experiment.json"
)
GENERATION2_SAFE_RESULT_FILENAME = (
    "model14_overture_generation2_disclosure_safe_pre_h_result.json"
)
ANCHOR_RADIUS_M = 8046.72
METRICS = ("spearman", "kendall_tau_b", "log_rmse", "level_mae")
DOMAINS = ("pooled", "michigan", "wisconsin")
ALPHA_GRID = (0.01, 0.1, 1.0, 10.0)
L1_RATIO_GRID = (0.25, 0.5, 0.75)
OUTER_FOLD_COUNT = 5
INNER_FOLD_COUNT = 4

CANDIDATE_SUBFAMILIES: Mapping[str, tuple[str, ...]] = {
    "A_model13_reproduced_generation2": (),
    "B_model13_plus_all_generation2_commercial": (
        "intensity_count",
        "mix_diversity",
    ),
    "C_model13_plus_generation2_intensity": ("intensity_count",),
    "D_model13_plus_generation2_mix_diversity": ("mix_diversity",),
}


def _verify_public_checkpoint(repository_root: Path) -> dict[str, Any]:
    """Require the committed public freeze checkpoint to precede this run."""
    try:
        completed = subprocess.run(
            [
                "git",
                "-C",
                str(repository_root.resolve()),
                "merge-base",
                "--is-ancestor",
                GENERATION2_PUBLIC_CHECKPOINT,
                "HEAD",
            ],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as exc:
        raise ConformanceError(
            "MODEL14_G2_PUBLIC_CHECKPOINT_UNVERIFIABLE",
            "the Generation-2 public checkpoint cannot be verified",
        ) from exc
    require(
        completed.returncode == 0,
        "MODEL14_G2_PUBLIC_CHECKPOINT_NOT_ANCESTOR",
        "the required Generation-2 public checkpoint is not an ancestor of HEAD",
    )
    return {
        "state": "VERIFIED_ANCESTOR",
        "checkpoint": GENERATION2_PUBLIC_CHECKPOINT,
    }


def _verify_candidate_authority(contract: Mapping[str, Any]) -> None:
    expected = {key: list(value) for key, value in CANDIDATE_SUBFAMILIES.items()}
    require(
        contract.get("candidate_sets") == expected
        and contract.get("generation1_combination_justified") is False
        and contract.get("generation") == 2
        and contract.get("exploratory") is True
        and contract.get("confirmatory") is False,
        "MODEL14_G2_CANDIDATE_AUTHORITY_MISMATCH",
        "Generation-2 candidate sets differ from the frozen bounded matrix",
    )


def _candidate_terms(
    baseline_terms: Sequence[str],
    subfamilies: Sequence[str],
) -> list[str]:
    selected = [
        feature
        for feature in FEATURE_IDS
        if FEATURE_SUBFAMILIES[feature] in set(subfamilies)
    ]
    terms = [*map(str, baseline_terms), *selected]
    require(
        len(terms) == len(set(terms)),
        "MODEL14_G2_CANDIDATE_TERM_DUPLICATE",
        "one Generation-2 candidate repeats a feature",
    )
    return terms


def _term_families(baseline_terms: Sequence[str]) -> dict[str, str]:
    return {
        **{str(term): "model13_accepted" for term in baseline_terms},
        **{
            feature: "overture_" + FEATURE_SUBFAMILIES[feature]
            for feature in FEATURE_IDS
        },
    }


def _accepted_anchor_features(
    *,
    repository_root: Path,
    model11: Any,
    model12: Any,
    michigan_features: Mapping[str, Any],
    model13_freeze: Mapping[str, Any],
    component_rows: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, float | None]]:
    """Recompute accepted 5-mile anchors from tract-local frozen components."""
    coordinates, wisconsin_tracts, geo03 = _coordinates_by_group(
        repository_root,
        model11,
        michigan_features,
    )
    transformer = Geo03ProductionTransformer(geo03)
    support = load_support_package(
        repository_root.resolve(),
        model12.public_dependencies["geo05_support_dir"],
    )
    fitting_groups = {
        str(row["successor_physical_location_id"])
        for row in model13_freeze["observations"]
        if row.get("fitting_eligible") is True
    }
    require(
        len(fitting_groups) == 123
        and sum(group.startswith("MI:") for group in fitting_groups) == 82
        and sum(group.startswith("WI:") for group in fitting_groups) == 41
        and fitting_groups <= set(coordinates),
        "MODEL14_G2_ANCHOR_ACCOUNTING_FAILED",
        "Generation-2 fitting anchors differ from accepted MODEL-13 groups",
    )

    features: dict[str, dict[str, float | None]] = {}
    for group in sorted(fitting_groups):
        latitude, longitude = coordinates[group]
        if group.startswith("MI:"):
            spatial = evaluate_anchor_package(
                support,
                latitude=latitude,
                longitude=longitude,
                opaque_anchor_identity=group,
                opaque_anchor_lineage=(
                    "accepted MODEL-12 canonical target-blind coordinate"
                ),
                radii_m=(ANCHOR_RADIUS_M,),
            )
            member_geoids = list(spatial["memberships"][0]["member_geoids"])
            anchor_geoid = str(spatial["containing_tract_geoid"])
        else:
            projected = project_internal_point(
                parse_internal_point(latitude, longitude),
                transformer,
            )
            require(
                projected is not None,
                "MODEL14_G2_WI_ANCHOR_TRANSFORM_FAILED",
                "one Wisconsin accepted anchor cannot be transformed",
            )
            anchor = _anchor_tract(wisconsin_tracts, longitude, latitude)
            member_geoids = sorted(
                tract.geoid
                for tract in wisconsin_tracts
                if math.hypot(
                    tract.internal_x_m - projected[0],
                    tract.internal_y_m - projected[1],
                )
                <= ANCHOR_RADIUS_M
            )
            if anchor.geoid not in member_geoids:
                member_geoids.append(anchor.geoid)
                member_geoids.sort()
            anchor_geoid = anchor.geoid
        vector = aggregate_commercial_features(
            component_rows,
            member_geoids,
            anchor_geoid,
        )
        require(
            tuple(vector) == FEATURE_IDS,
            "MODEL14_G2_ANCHOR_FEATURE_SCHEMA_MISMATCH",
            "one Generation-2 anchor vector differs from the frozen catalog",
        )
        features[group] = vector

    require(
        set(features) == fitting_groups,
        "MODEL14_G2_ANCHOR_FEATURE_ACCOUNTING_FAILED",
        "not every fitting group received frozen Generation-2 features",
    )
    return features


def _anchor_coverage(
    anchor_features: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    output: dict[str, Any] = {}
    subfamily_terms = {
        "intensity_count": INTENSITY_FEATURES,
        "mix_diversity": MIX_DIVERSITY_FEATURES,
        "all_commercial": FEATURE_IDS,
    }
    for subfamily, terms in subfamily_terms.items():
        by_state: dict[str, Any] = {}
        for state in ("MI", "WI"):
            rows = [
                values
                for group, values in anchor_features.items()
                if group.startswith(state + ":")
            ]
            missing = {
                term: sum(not _finite(row.get(term)) for row in rows)
                for term in terms
            }
            by_state[state] = {
                "physical_location_count": len(rows),
                "fully_computable_physical_location_count": sum(
                    all(_finite(row.get(term)) for term in terms) for row in rows
                ),
                "missing_physical_location_count_by_feature": missing,
                "maximum_missing_physical_location_count_by_feature": max(
                    missing.values(),
                    default=0,
                ),
                "total_missing_feature_values": sum(missing.values()),
            }
        output[subfamily] = {
            "candidate_feature_count": len(terms),
            "by_state": by_state,
        }
    return output


def _verify_development_cohort(rows: Sequence[Mapping[str, Any]]) -> None:
    """Require the exact already-consumed MODEL-13 cohort and exclusions."""
    rows = list(rows)
    fitting = [row for row in rows if row.get("fitting_eligible") is True]
    excluded = [row for row in rows if row.get("fitting_eligible") is False]
    fitting_groups = {
        str(row[GROUP_FIELD])
        for row in fitting
    }
    michigan_groups = {
        str(row[GROUP_FIELD])
        for row in fitting
        if row.get("state") == "MI"
    }
    wisconsin_groups = {
        str(row[GROUP_FIELD])
        for row in fitting
        if row.get("state") == "WI"
    }
    excluded_groups = {str(row[GROUP_FIELD]) for row in excluded}
    require(
        len(rows) == 201
        and len({str(row[GROUP_FIELD]) for row in rows}) == 126
        and len(fitting) == 196
        and len(fitting_groups) == 123
        and sum(row.get("state") == "MI" for row in fitting) == 133
        and len(michigan_groups) == 82
        and sum(row.get("state") == "WI" for row in fitting) == 63
        and len(wisconsin_groups) == 41
        and len(excluded) == 5
        and len(excluded_groups) == 3
        and all(row.get("state") == "MI" for row in excluded)
        and all(
            row.get("fitting_exclusion_reason")
            == "GEO05_ANCHOR_TRACT_MISSING_OR_AMBIGUOUS"
            for row in excluded
        ),
        "MODEL14_G2_DEVELOPMENT_COHORT_MISMATCH",
        "Generation-2 evidence differs from the accepted MODEL-13 development cohort",
    )


def _write_anchor_freeze(
    output: Path,
    anchor_features: Mapping[str, Mapping[str, Any]],
    model13_freeze: Mapping[str, Any],
) -> dict[str, Any]:
    package = {
        "package_id": GENERATION2_ANCHOR_FREEZE_PACKAGE_ID,
        "version": "1.0.0",
        "state": "READY",
        "controlling_task": "MODEL-14",
        "generation": 2,
        "exploratory": True,
        "confirmatory": False,
        "prior_generation_results_known": True,
        "chronology": {
            "public_checkpoint_verified_before_resolver": True,
            "tracked_public_commitment_and_two_freezes_verified_before_resolver": True,
            "public_tract_components_ready_before_anchor_recomputation": True,
            "generation2_feature_definitions_changed": False,
            "generation2_target_values_accessed_during_anchor_recomputation": 0,
            "sealed_or_prospective_evidence_accessed": False,
        },
        "accepted_predecessor_accounting": {
            "fitting_observation_count": model13_freeze["evidence_accounting"][
                "fitting_observation_count"
            ],
            "fitting_physical_location_count": model13_freeze[
                "evidence_accounting"
            ]["fitting_physical_location_count"],
            "michigan_fitting_physical_location_count": model13_freeze[
                "evidence_accounting"
            ]["fitting_michigan_physical_location_count"],
            "wisconsin_fitting_physical_location_count": model13_freeze[
                "evidence_accounting"
            ]["fitting_wisconsin_physical_location_count"],
        },
        "feature_count": len(FEATURE_IDS),
        "feature_order": list(FEATURE_IDS),
        "coverage": _anchor_coverage(anchor_features),
        "physical_locations": [
            {
                "successor_physical_location_id": group,
                "features": dict(anchor_features[group]),
            }
            for group in sorted(anchor_features)
        ],
        "protected_local_only": True,
        "ready_marker_written_last": True,
    }
    semantic = copy.deepcopy(package)
    package["protected_content_sha256"] = content_digest(semantic)
    directory = output / GENERATION2_ANCHOR_DIRECTORY
    package_path = directory / GENERATION2_ANCHOR_FILENAME
    write_json_exclusive(package_path, package)
    ready = {
        "state": "READY",
        "package_id": GENERATION2_ANCHOR_FREEZE_PACKAGE_ID,
        "protected_content_sha256": package["protected_content_sha256"],
        "package_file_sha256": file_sha256(package_path),
        "generation2_target_values_accessed": 0,
        "sealed_or_prospective_evidence_accessed": False,
        "ready_marker_written_last": True,
    }
    ready_path = directory / "READY.json"
    write_json_exclusive(ready_path, ready)
    persisted = _load_object(ready_path, "MODEL14_G2_ANCHOR_READY_UNRESOLVED")
    require(
        persisted == ready
        and file_sha256(package_path) == ready["package_file_sha256"],
        "MODEL14_G2_ANCHOR_FREEZE_NOT_READY",
        "Generation-2 target-blind anchor freeze is not immutable and ready",
    )
    return package


def _domain_metrics(
    rows: Sequence[Mapping[str, Any]],
    predictions: Sequence[float],
    state: str | None = None,
) -> dict[str, float]:
    selected = [
        (row, prediction)
        for row, prediction in zip(rows, predictions)
        if state is None or str(row["state"]) == state
    ]
    require(
        selected,
        "MODEL14_G2_METRIC_DOMAIN_EMPTY",
        "one Generation-2 metric domain is empty",
    )
    return grouped_metrics(
        [row for row, _ in selected],
        [float(prediction) for _, prediction in selected],
    )


def _metric_deltas(
    baseline: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> dict[str, float]:
    return {
        metric: float(candidate[metric]) - float(baseline[metric])
        for metric in METRICS
    }


def _paired_fold_metric_deltas(
    rows: Sequence[Mapping[str, Any]],
    baseline_predictions: Sequence[float],
    candidate_predictions: Sequence[float],
    *,
    outer_count: int = OUTER_FOLD_COUNT,
) -> dict[str, Any]:
    """Summarize candidate-minus-baseline deltas on identical outer folds."""
    rows = list(rows)
    baseline_predictions = [float(value) for value in baseline_predictions]
    candidate_predictions = [float(value) for value in candidate_predictions]
    require(
        len(rows) == len(baseline_predictions) == len(candidate_predictions)
        and outer_count == 5
        and all(math.isfinite(value) for value in baseline_predictions)
        and all(math.isfinite(value) for value in candidate_predictions),
        "MODEL14_G2_PAIRED_FOLD_INPUT_INVALID",
        "Generation-2 paired fold inputs are invalid",
    )
    assignment = state_balanced_grouped_folds(rows, outer_count)
    output: dict[str, Any] = {}
    for domain, state in (
        ("pooled", None),
        ("michigan", "MI"),
        ("wisconsin", "WI"),
    ):
        fold_deltas: list[dict[str, float]] = []
        for fold in range(outer_count):
            indices = [
                index
                for index, row in enumerate(rows)
                if assignment[str(row[GROUP_FIELD])] == fold
                and (state is None or str(row["state"]) == state)
            ]
            require(
                indices,
                "MODEL14_G2_PAIRED_FOLD_DOMAIN_EMPTY",
                "one Generation-2 paired outer-fold domain is empty",
            )
            selected_rows = [rows[index] for index in indices]
            baseline_metrics = grouped_metrics(
                selected_rows,
                [baseline_predictions[index] for index in indices],
            )
            candidate_metrics = grouped_metrics(
                selected_rows,
                [candidate_predictions[index] for index in indices],
            )
            fold_deltas.append(_metric_deltas(baseline_metrics, candidate_metrics))
        metrics: dict[str, Any] = {}
        for metric in METRICS:
            values = [fold[metric] for fold in fold_deltas]
            lower_is_better = metric in ("log_rmse", "level_mae")
            metrics[metric] = {
                "minimum": min(values),
                "maximum": max(values),
                "mean": sum(values) / len(values),
                "median": float(median(values)),
                "improving_fold_count": sum(
                    value < -1e-12 if lower_is_better else value > 1e-12
                    for value in values
                ),
                "nonworsening_fold_count": sum(
                    value <= 1e-12 if lower_is_better else value >= -1e-12
                    for value in values
                ),
            }
        output[domain] = {
            "paired_outer_fold_count": outer_count,
            "candidate_minus_baseline": metrics,
        }
    return output


def _paired_outlier_sensitivity(
    rows: Sequence[Mapping[str, Any]],
    baseline_predictions: Sequence[float],
    candidate_predictions: Sequence[float],
) -> dict[str, Any]:
    """Remove the candidate's worst location from both paired OOF vectors."""
    rows = list(rows)
    baseline_predictions = [float(value) for value in baseline_predictions]
    candidate_predictions = [float(value) for value in candidate_predictions]
    require(
        len(rows) == len(baseline_predictions) == len(candidate_predictions),
        "MODEL14_G2_PAIRED_OUTLIER_INPUT_INVALID",
        "Generation-2 paired outlier inputs are invalid",
    )
    grouped: dict[str, tuple[list[float], list[float]]] = {}
    for row, prediction in zip(rows, candidate_predictions):
        actual, predicted = grouped.setdefault(str(row[GROUP_FIELD]), ([], []))
        actual.append(float(row["isolated_sales"]))
        predicted.append(float(prediction))
    require(
        len(grouped) >= 3,
        "MODEL14_G2_PAIRED_OUTLIER_ACCOUNTING_FAILED",
        "Generation-2 paired outlier support is insufficient",
    )
    errors = {
        group: abs(
            math.log1p(sum(actual) / len(actual))
            - math.log1p(max(0.0, sum(predicted) / len(predicted)))
        )
        for group, (actual, predicted) in grouped.items()
    }
    worst_group = max(errors, key=lambda group: (errors[group], group))
    retained = [
        index
        for index, row in enumerate(rows)
        if str(row[GROUP_FIELD]) != worst_group
    ]
    before_baseline = _domain_metrics(rows, baseline_predictions)
    before_candidate = _domain_metrics(rows, candidate_predictions)
    retained_rows = [rows[index] for index in retained]
    after_baseline = _domain_metrics(
        retained_rows,
        [baseline_predictions[index] for index in retained],
    )
    after_candidate = _domain_metrics(
        retained_rows,
        [candidate_predictions[index] for index in retained],
    )
    before_delta = _metric_deltas(before_baseline, before_candidate)
    after_delta = _metric_deltas(after_baseline, after_candidate)
    return {
        "selection_basis": (
            "strongest expanded candidate maximum physical-location absolute "
            "log error"
        ),
        "same_location_removed_from_baseline_and_candidate": True,
        "excluded_physical_location_count": 1,
        "retained_physical_location_count": len(grouped) - 1,
        "candidate_maximum_physical_location_absolute_log_error": errors[
            worst_group
        ],
        "candidate_minus_baseline_before_removal": before_delta,
        "candidate_minus_baseline_after_removal": after_delta,
        "incremental_metric_delta_change_after_removal": {
            metric: after_delta[metric] - before_delta[metric]
            for metric in METRICS
        },
        "protected_location_identity_disclosed": False,
    }


def _strongest_expanded(
    candidates: Mapping[str, Mapping[str, Any]],
    dispositions: Mapping[str, Mapping[str, Any]],
) -> str:
    """Select by evidence disposition, then balanced state and error behavior."""
    baseline = candidates["A_model13_reproduced_generation2"]
    disposition_rank = {
        "no credible improvement": 0,
        "possible improvement": 1,
        "material improvement": 2,
    }
    expanded = [
        candidate_id
        for candidate_id in CANDIDATE_SUBFAMILIES
        if candidate_id != "A_model13_reproduced_generation2"
    ]

    def selection_key(candidate_id: str) -> tuple[Any, ...]:
        candidate = candidates[candidate_id]
        pooled_delta = _metric_deltas(
            baseline["aggregate_oof"]["pooled"],
            candidate["aggregate_oof"]["pooled"],
        )
        michigan_delta = _metric_deltas(
            baseline["aggregate_oof"]["michigan"],
            candidate["aggregate_oof"]["michigan"],
        )
        wisconsin_delta = _metric_deltas(
            baseline["aggregate_oof"]["wisconsin"],
            candidate["aggregate_oof"]["wisconsin"],
        )
        log_ratio = (
            float(candidate["aggregate_oof"]["pooled"]["log_rmse"])
            / float(baseline["aggregate_oof"]["pooled"]["log_rmse"])
        )
        mae_ratio = (
            float(candidate["aggregate_oof"]["pooled"]["level_mae"])
            / float(baseline["aggregate_oof"]["pooled"]["level_mae"])
        )
        guardrails = sum(
            (
                pooled_delta["spearman"] > 0,
                pooled_delta["kendall_tau_b"] >= -0.02,
                michigan_delta["spearman"] >= -0.01,
                wisconsin_delta["spearman"] >= -0.05,
                log_ratio <= 1.05,
                mae_ratio <= 1.05,
            )
        )
        return (
            disposition_rank[str(dispositions[candidate_id]["disposition"])],
            guardrails,
            min(michigan_delta["spearman"], wisconsin_delta["spearman"]),
            pooled_delta["spearman"],
            pooled_delta["kendall_tau_b"],
            -log_ratio,
            -mae_ratio,
            candidate_id,
        )

    return max(
        expanded,
        key=selection_key,
    )


def _candidate_metric_delta(
    left: Mapping[str, Any],
    right: Mapping[str, Any],
) -> dict[str, dict[str, float]]:
    return {
        domain: _metric_deltas(
            right["aggregate_oof"][domain],
            left["aggregate_oof"][domain],
        )
        for domain in DOMAINS
    }


def _fixed_ablations(
    candidates: Mapping[str, Mapping[str, Any]],
    strongest_id: str,
) -> dict[str, Any]:
    baseline_id = "A_model13_reproduced_generation2"
    all_id = "B_model13_plus_all_generation2_commercial"
    intensity_id = "C_model13_plus_generation2_intensity"
    mix_id = "D_model13_plus_generation2_mix_diversity"
    all_ablations = {
        "remove_intensity_count": {
            "ablated_candidate_id": mix_id,
            "removed_feature_count": len(INTENSITY_FEATURES),
            "all_minus_ablation_metric_delta": _candidate_metric_delta(
                candidates[all_id],
                candidates[mix_id],
            ),
        },
        "remove_mix_diversity": {
            "ablated_candidate_id": intensity_id,
            "removed_feature_count": len(MIX_DIVERSITY_FEATURES),
            "all_minus_ablation_metric_delta": _candidate_metric_delta(
                candidates[all_id],
                candidates[intensity_id],
            ),
        },
    }
    if strongest_id == all_id:
        strongest_ablations = copy.deepcopy(all_ablations)
    else:
        family = CANDIDATE_SUBFAMILIES[strongest_id][0]
        strongest_ablations = {
            "remove_" + family: {
                "ablated_candidate_id": baseline_id,
                "removed_feature_count": (
                    len(INTENSITY_FEATURES)
                    if family == "intensity_count"
                    else len(MIX_DIVERSITY_FEATURES)
                ),
                "strongest_minus_ablation_metric_delta": _candidate_metric_delta(
                    candidates[strongest_id],
                    candidates[baseline_id],
                ),
            }
        }
    return {
        "only_frozen_primary_candidates_reused": True,
        "all_commercial_family_ablations": all_ablations,
        "strongest_candidate_family_ablations": strongest_ablations,
    }


def _classify_evidence(
    baseline: Mapping[str, Any],
    strongest: Mapping[str, Any],
    paired_outlier: Mapping[str, Any],
    paired_folds: Mapping[str, Any],
) -> tuple[str, list[str]]:
    pooled = (
        float(strongest["aggregate_oof"]["pooled"]["spearman"])
        - float(baseline["aggregate_oof"]["pooled"]["spearman"])
    )
    pooled_kendall = (
        float(strongest["aggregate_oof"]["pooled"]["kendall_tau_b"])
        - float(baseline["aggregate_oof"]["pooled"]["kendall_tau_b"])
    )
    michigan = (
        float(strongest["aggregate_oof"]["michigan"]["spearman"])
        - float(baseline["aggregate_oof"]["michigan"]["spearman"])
    )
    wisconsin = (
        float(strongest["aggregate_oof"]["wisconsin"]["spearman"])
        - float(baseline["aggregate_oof"]["wisconsin"]["spearman"])
    )
    log_ratio = (
        float(strongest["aggregate_oof"]["pooled"]["log_rmse"])
        / float(baseline["aggregate_oof"]["pooled"]["log_rmse"])
    )
    mae_ratio = (
        float(strongest["aggregate_oof"]["pooled"]["level_mae"])
        / float(baseline["aggregate_oof"]["pooled"]["level_mae"])
    )
    stability = float(strongest["stability"]["stability_score"])
    outlier_change = abs(
        float(
            paired_outlier["incremental_metric_delta_change_after_removal"][
                "spearman"
            ]
        )
    )
    pooled_fold_spearman = paired_folds["pooled"][
        "candidate_minus_baseline"
    ]["spearman"]
    michigan_fold_spearman = paired_folds["michigan"][
        "candidate_minus_baseline"
    ]["spearman"]
    wisconsin_fold_spearman = paired_folds["wisconsin"][
        "candidate_minus_baseline"
    ]["spearman"]
    reasons = [
        f"pooled Spearman delta {pooled:+.4f}",
        f"pooled Kendall tau-b delta {pooled_kendall:+.4f}",
        f"Michigan Spearman delta {michigan:+.4f}",
        f"Wisconsin Spearman delta {wisconsin:+.4f}",
        f"pooled log RMSE ratio {log_ratio:.4f}",
        f"pooled level MAE ratio {mae_ratio:.4f}",
        f"fold coefficient stability {stability:.4f}",
        (
            "paired worst-location-removal incremental pooled Spearman delta "
            f"change {outlier_change:.4f}"
        ),
        (
            "paired pooled Spearman improving/nonworsening folds "
            f"{pooled_fold_spearman['improving_fold_count']}/"
            f"{pooled_fold_spearman['nonworsening_fold_count']} of 5"
        ),
        (
            "paired Michigan/Wisconsin Spearman nonworsening folds "
            f"{michigan_fold_spearman['nonworsening_fold_count']}/"
            f"{wisconsin_fold_spearman['nonworsening_fold_count']} of 5"
        ),
        "Generation 2 is exploratory and is not confirmation.",
    ]
    if (
        pooled >= 0.03
        and pooled_kendall >= 0.0
        and michigan >= 0.02
        and wisconsin >= -0.02
        and log_ratio <= 1.0
        and mae_ratio <= 1.0
        and stability >= 0.75
        and outlier_change <= 0.05
        and pooled_fold_spearman["improving_fold_count"] >= 3
        and pooled_fold_spearman["nonworsening_fold_count"] >= 4
        and michigan_fold_spearman["nonworsening_fold_count"] >= 3
        and wisconsin_fold_spearman["nonworsening_fold_count"] >= 3
        and len(strongest["terms"]) <= 40
    ):
        return "material improvement", reasons
    if (
        pooled > 0
        and pooled_kendall >= -0.02
        and michigan >= -0.01
        and wisconsin >= -0.05
        and log_ratio <= 1.05
        and mae_ratio <= 1.05
        and outlier_change <= 0.10
        and pooled_fold_spearman["improving_fold_count"] >= 3
        and pooled_fold_spearman["nonworsening_fold_count"] >= 3
    ):
        return "possible improvement", reasons
    return "no credible improvement", reasons


def _run_candidates(
    rows: Sequence[Mapping[str, Any]],
    baseline_terms: Sequence[str],
) -> tuple[dict[str, Any], str, dict[str, Any], str, list[str]]:
    families = _term_families(baseline_terms)
    candidates: dict[str, Any] = {}
    for candidate_id, subfamilies in CANDIDATE_SUBFAMILIES.items():
        candidates[candidate_id] = nested_grouped_oof(
            rows,
            candidate_id,
            _candidate_terms(baseline_terms, subfamilies),
            alpha_grid=ALPHA_GRID,
            l1_ratio_grid=L1_RATIO_GRID,
            outer_count=OUTER_FOLD_COUNT,
            inner_count=INNER_FOLD_COUNT,
            term_families=families,
        )
    baseline_id = "A_model13_reproduced_generation2"
    baseline_reproduction = _verify_baseline_reproduction(candidates[baseline_id])
    paired_folds = {
        candidate_id: _paired_fold_metric_deltas(
            rows,
            candidates[baseline_id]["predictions"],
            candidates[candidate_id]["predictions"],
        )
        for candidate_id in CANDIDATE_SUBFAMILIES
        if candidate_id != baseline_id
    }
    paired_outliers = {
        candidate_id: _paired_outlier_sensitivity(
            rows,
            candidates[baseline_id]["predictions"],
            candidates[candidate_id]["predictions"],
        )
        for candidate_id in CANDIDATE_SUBFAMILIES
        if candidate_id != baseline_id
    }
    candidate_dispositions: dict[str, Any] = {}
    for candidate_id in paired_folds:
        conclusion, reasons = _classify_evidence(
            candidates[baseline_id],
            candidates[candidate_id],
            paired_outliers[candidate_id],
            paired_folds[candidate_id],
        )
        candidate_dispositions[candidate_id] = {
            "disposition": conclusion,
            "evidence": reasons,
        }
    strongest_id = _strongest_expanded(candidates, candidate_dispositions)
    paired_outlier = paired_outliers[strongest_id]
    ablations = _fixed_ablations(candidates, strongest_id)
    conclusion = str(candidate_dispositions[strongest_id]["disposition"])
    reasons = list(candidate_dispositions[strongest_id]["evidence"])
    diagnostics = {
        "baseline_reproduction": baseline_reproduction,
        "paired_fold_stability": paired_folds,
        "paired_outlier_sensitivity": paired_outlier,
        "expanded_candidate_disposition_screen": candidate_dispositions,
        "ablations": ablations,
    }
    return candidates, strongest_id, diagnostics, conclusion, reasons


def _strip_predictions(result: Mapping[str, Any]) -> dict[str, Any]:
    output = copy.deepcopy(dict(result))
    output.pop("predictions", None)
    return output


def _rounded_metrics(metrics: Mapping[str, Any]) -> dict[str, float]:
    return {
        "spearman": round(float(metrics["spearman"]), 4),
        "kendall_tau_b": round(float(metrics["kendall_tau_b"]), 4),
        "log_rmse": round(float(metrics["log_rmse"]), 4),
        "level_mae": round(float(metrics["level_mae"]), 2),
    }


def _rounded_delta(metric: str, value: Any) -> float:
    return round(float(value), 2 if metric == "level_mae" else 4)


def _safe_candidate(
    result: Mapping[str, Any],
    baseline: Mapping[str, Any],
    baseline_term_count: int,
) -> dict[str, Any]:
    return {
        "feature_count": len(result["terms"]),
        "new_commercial_feature_count": len(result["terms"]) - baseline_term_count,
        "aggregate_oof": {
            domain: _rounded_metrics(result["aggregate_oof"][domain])
            for domain in DOMAINS
        },
        "candidate_minus_baseline_metric_delta": {
            domain: {
                metric: _rounded_delta(metric, value)
                for metric, value in _metric_deltas(
                    baseline["aggregate_oof"][domain],
                    result["aggregate_oof"][domain],
                ).items()
            }
            for domain in DOMAINS
        },
        "outer_fold_metric_ranges": {
            domain: {
                metric: {
                    "minimum": _rounded_delta(metric, bounds["minimum"]),
                    "maximum": _rounded_delta(metric, bounds["maximum"]),
                }
                for metric, bounds in result["outer_fold_metric_ranges"][
                    domain
                ].items()
            }
            for domain in DOMAINS
        },
        "coefficient_stability_score": round(
            float(result["stability"]["stability_score"]),
            4,
        ),
        "feature_family_stability": {
            family: {
                "term_count": int(values["term_count"]),
                "selected_in_any_fold_count": int(
                    values["selected_in_any_fold_count"]
                ),
                "selected_in_every_fold_count": int(
                    values["selected_in_every_fold_count"]
                ),
                "mean_selection_frequency": round(
                    float(values["mean_selection_frequency"]),
                    4,
                ),
                "mean_dominant_sign_agreement": round(
                    float(values["mean_dominant_sign_agreement"]),
                    4,
                ),
            }
            for family, values in result["feature_family_stability"].items()
        },
        "mean_outer_effective_degrees_of_freedom": round(
            float(result["mean_outer_effective_degrees_of_freedom"]),
            2,
        ),
        "outer_effective_degrees_of_freedom_range": list(
            result["outer_effective_degrees_of_freedom_range"]
        ),
        "exact_fitted_parameters_disclosed": False,
    }


def _safe_paired_folds(diagnostics: Mapping[str, Any]) -> dict[str, Any]:
    return {
        candidate_id: {
            domain: {
                "paired_outer_fold_count": int(values["paired_outer_fold_count"]),
                "candidate_minus_baseline": {
                    metric: {
                        "minimum": _rounded_delta(metric, summary["minimum"]),
                        "maximum": _rounded_delta(metric, summary["maximum"]),
                        "mean": _rounded_delta(metric, summary["mean"]),
                        "median": _rounded_delta(metric, summary["median"]),
                        "improving_fold_count": int(
                            summary["improving_fold_count"]
                        ),
                        "nonworsening_fold_count": int(
                            summary["nonworsening_fold_count"]
                        ),
                    }
                    for metric, summary in values[
                        "candidate_minus_baseline"
                    ].items()
                },
            }
            for domain, values in domains.items()
        }
        for candidate_id, domains in diagnostics.items()
    }


def _safe_metric_delta_tree(value: Any, key: str | None = None) -> Any:
    if isinstance(value, Mapping):
        return {
            str(child_key): _safe_metric_delta_tree(child_value, str(child_key))
            for child_key, child_value in value.items()
        }
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if isinstance(value, int):
        return value
    metric = key if key in METRICS else "spearman"
    return _rounded_delta(metric, value)


def _safe_commercial_coefficients(
    strongest: Mapping[str, Any],
) -> dict[str, Any]:
    coefficients = strongest["final_standardized_coefficients"]
    commercial = [
        feature
        for feature in FEATURE_IDS
        if feature in coefficients and abs(float(coefficients[feature])) > 1e-8
    ]
    ordered = sorted(
        commercial,
        key=lambda feature: (-abs(float(coefficients[feature])), feature),
    )
    signals = []
    for feature in ordered[:12]:
        coefficient = float(coefficients[feature])
        signals.append(
            {
                "feature": feature,
                "subfamily": FEATURE_SUBFAMILIES[feature],
                "standardized_coefficient": round(coefficient, 4),
                "direction": "positive" if coefficient > 0 else "negative",
                "outer_fold_selection_frequency": round(
                    float(strongest["stability"]["selection_frequency"][feature]),
                    4,
                ),
                "outer_fold_dominant_sign_agreement": round(
                    float(
                        strongest["stability"]["coefficient_sign_stability"][
                            feature
                        ]
                    ),
                    4,
                ),
            }
        )
    feature_stability = {
        feature: {
            "subfamily": FEATURE_SUBFAMILIES[feature],
            "outer_fold_selection_frequency": round(
                float(strongest["stability"]["selection_frequency"][feature]),
                4,
            ),
            "outer_fold_dominant_sign_agreement": round(
                float(
                    strongest["stability"]["coefficient_sign_stability"][feature]
                ),
                4,
            ),
        }
        for feature in FEATURE_IDS
        if feature in strongest["terms"]
    }
    return {
        "selected_commercial_feature_count": len(commercial),
        "top_signal_limit": 12,
        "top_standardized_commercial_signals": signals,
        "commercial_feature_stability": feature_stability,
        "exact_fitted_parameters_disclosed": False,
    }


def build_generation2_disclosure_safe_result(
    result: Mapping[str, Any],
) -> dict[str, Any]:
    """Reduce the protected run to aggregate, disclosure-safe evidence."""
    baseline_id = "A_model13_reproduced_generation2"
    strongest_id = str(result["strongest_expanded_candidate_id"])
    candidates = result["candidates"]
    baseline = candidates[baseline_id]
    paired_outlier = result["paired_outlier_sensitivity"]
    safe = {
        "package_id": GENERATION2_SAFE_RESULT_PACKAGE_ID,
        "state": "PRE_H_EXPLORATORY_GENERATION2_COMPLETE",
        "task_id": "MODEL-14",
        "generation": 2,
        "posture": "IN_PROGRESS_PRE_H_MCR_REVIEW",
        "review_state": "NOT_REVIEWED",
        "exploratory": True,
        "confirmatory": False,
        "interpretation_posture": "NOT_CONFIRMATORY",
        "prior_generation_results_known": True,
        "source": copy.deepcopy(result["source"]),
        "frozen_commercial_feature_catalog": copy.deepcopy(
            result["frozen_commercial_feature_catalog"]
        ),
        "frozen_rules": copy.deepcopy(result["frozen_rules"]),
        "accepted_predecessor": {
            "candidate_id": "successor_combined_multivariate_elastic_net",
            "accepted_and_unchanged": True,
            "baseline_reproduction": copy.deepcopy(result["baseline_reproduction"]),
        },
        "evidence_accounting": {
            "protected_observation_count": 201,
            "protected_physical_location_count": 126,
            "fitting_observation_count": 196,
            "fitting_physical_location_count": 123,
            "michigan_fitting_observation_count": 133,
            "michigan_fitting_physical_location_count": 82,
            "wisconsin_fitting_observation_count": 63,
            "wisconsin_fitting_physical_location_count": 41,
            "excluded_michigan_observation_count": 5,
            "excluded_michigan_physical_location_count": 3,
        },
        "tract_coverage_and_missingness": copy.deepcopy(
            result["tract_coverage_and_missingness"]
        ),
        "development_anchor_coverage": copy.deepcopy(
            result["development_anchor_coverage"]
        ),
        "candidate_matrix": {
            candidate_id: _safe_candidate(
                candidate,
                baseline,
                len(result["baseline_terms"]),
            )
            for candidate_id, candidate in candidates.items()
        },
        "paired_fold_stability": _safe_paired_folds(
            result["paired_fold_stability"]
        ),
        "expanded_candidate_disposition_screen": copy.deepcopy(
            result["expanded_candidate_disposition_screen"]
        ),
        "strongest_expanded_candidate_id": strongest_id,
        "strongest_commercial_signal_summary": _safe_commercial_coefficients(
            candidates[strongest_id]
        ),
        "fixed_family_ablations": _safe_metric_delta_tree(result["ablations"]),
        "paired_outlier_sensitivity": {
            "selection_basis": paired_outlier["selection_basis"],
            "same_location_removed_from_baseline_and_candidate": True,
            "excluded_physical_location_count": 1,
            "retained_physical_location_count": int(
                paired_outlier["retained_physical_location_count"]
            ),
            "candidate_maximum_physical_location_absolute_log_error": round(
                float(
                    paired_outlier[
                        "candidate_maximum_physical_location_absolute_log_error"
                    ]
                ),
                4,
            ),
            "candidate_minus_baseline_before_removal": {
                metric: _rounded_delta(metric, value)
                for metric, value in paired_outlier[
                    "candidate_minus_baseline_before_removal"
                ].items()
            },
            "candidate_minus_baseline_after_removal": {
                metric: _rounded_delta(metric, value)
                for metric, value in paired_outlier[
                    "candidate_minus_baseline_after_removal"
                ].items()
            },
            "incremental_metric_delta_change_after_removal": {
                metric: _rounded_delta(metric, value)
                for metric, value in paired_outlier[
                    "incremental_metric_delta_change_after_removal"
                ].items()
            },
            "location_identity_disclosed": False,
        },
        "evidence_disposition": str(result["evidence_disposition"]),
        "disposition_evidence": list(result["disposition_evidence"]),
        "next_destination": "MASTER CONTROL ROOM: Sprouts Customer Geography",
        "execution_safeguards": {
            "public_checkpoint_preceded_authority_resolution": True,
            "tracked_commitment_and_two_public_freezes_verified_first": True,
            "anchor_freeze_ready_before_development_evidence": True,
            "generation2_feature_definitions_modified_after_freeze": False,
            "physical_location_grouped_cv": True,
            "training_fold_only_preprocessing": True,
            "sealed_or_prospective_evidence_opened": False,
            "protected_characteristic_scoring_feature_used": False,
            "location_identity_disclosed": False,
            "coordinate_disclosed": False,
            "row_level_value_disclosed": False,
            "local_authority_locator_disclosed": False,
            "protected_digest_disclosed": False,
            "model13_changed_or_replaced": False,
            "app01_changed": False,
            "pbi02_changed": False,
            "generation1_evidence_changed": False,
            "production_source_authority_promoted": False,
            "production_scoring_promoted": False,
        },
    }
    public_text = json.dumps(safe, sort_keys=True)
    forbidden = (
        "successor_physical_location_id",
        "analytical_observation_id",
        "source_observation_id",
        "isolated_sales",
        "canonical_latitude",
        "canonical_longitude",
        "protected_content_sha256",
        '"predictions"',
        '"residuals"',
        '"registry"',
        '"path"',
    )
    require(
        not any(token in public_text for token in forbidden),
        "MODEL14_G2_DISCLOSURE_SAFE_RESULT_INVALID",
        "Generation-2 safe result contains a protected field",
    )
    return safe


def execute_generation2_protected_experiment(
    *,
    repository_root: Path,
    registry_path: Path,
    public_freeze_dir: Path,
    verification_freeze_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Evaluate only frozen A/B/C/D against accepted MODEL-13 development evidence."""
    root = repository_root.resolve()

    # These public gates deliberately precede output creation and every
    # protected resolver or target-bearing operation.
    checkpoint = _verify_public_checkpoint(root)
    require(
        public_freeze_dir.resolve() != verification_freeze_dir.resolve(),
        "MODEL14_G2_INDEPENDENT_FREEZES_REQUIRED",
        "two independently materialized Generation-2 freezes are required",
    )
    public_verification = verify_generation2_commitment_against_freezes(
        repository_root=root,
        first=public_freeze_dir,
        second=verification_freeze_dir,
    )
    require(
        public_verification.get("state")
        == "GENERATION2_TARGET_BLIND_COMMITMENT_VERIFIED"
        and public_verification.get("generation2_target_values_accessed") == 0
        and public_verification.get("generation2_protected_anchor_rows_accessed")
        == 0,
        "MODEL14_G2_PUBLIC_AUTHORITY_NOT_VERIFIED",
        "Generation-2 public commitment and freezes are not verified",
    )
    public_freeze = load_generation2_public_freeze(public_freeze_dir)
    contract14 = load_generation2_contract(root)
    commitment14 = load_generation2_commitment(root)
    require(
        contract14.get("content_sha256")
        == GENERATION2_CONTRACT_CONTENT_SHA256
        and commitment14.get("content_sha256")
        == GENERATION2_COMMITMENT_CONTENT_SHA256
        and public_freeze.report.get("content_sha256")
        == GENERATION2_FREEZE_SEMANTIC_CONTENT_SHA256
        and public_freeze.report["files"][COMPONENT_FILENAME]["sha256"]
        == GENERATION2_COMPONENT_FILE_SHA256
        and public_freeze.report["files"][MATRIX_FILENAME]["sha256"]
        == GENERATION2_MATRIX_FILE_SHA256,
        "MODEL14_G2_EXACT_PUBLIC_FREEZE_MISMATCH",
        "Generation-2 public authority differs from the checkpointed exact freeze",
    )
    _verify_candidate_authority(contract14)

    output = _assert_output_path(root, output_dir)
    output.mkdir(parents=True, exist_ok=False)
    write_json_exclusive(
        output / "STARTED.json",
        {
            "state": "INCOMPLETE",
            "package_id": GENERATION2_EXPERIMENT_PACKAGE_ID,
            "generation": 2,
            "exploratory": True,
            "confirmatory": False,
            "public_checkpoint": GENERATION2_PUBLIC_CHECKPOINT,
            "public_checkpoint_verified_before_resolver": checkpoint["state"]
            == "VERIFIED_ANCESTOR",
            "tracked_commitment_and_two_public_freezes_verified_before_resolver": True,
            "generation2_target_values_accessed": 0,
            "ready_marker_written_last": False,
        },
    )

    # From this point forward the resolver chain is exactly the already
    # accepted MODEL-13 chain; no discovery, transport, or new authority occurs.
    resolver = ProtectedHandleResolver.load(registry_path, root)
    contract13, _output_contract = verify_model13_repository_authority(root)
    model11, model12, pipe05, pipe05_run = _upstream_resolvers(root, resolver)
    identity, michigan_features, _scoring, _authority = _accepted_model12_packages(
        root,
        pipe05,
    )
    model13_freeze, _frozen_model11 = _feature_freeze_package(
        root,
        model11,
        model12,
        identity,
        michigan_features,
        contract13,
    )
    require(
        model13_freeze.get("feature_preparation", {}).get("target_blind") is True
        and model13_freeze.get("evidence_accounting", {}).get(
            "target_values_accessed"
        )
        == 0
        and all(
            "isolated_sales" not in row
            for row in model13_freeze.get("observations", [])
        ),
        "MODEL14_G2_PRE_ANCHOR_TARGET_BOUNDARY_FAILED",
        "accepted MODEL-13 feature authority is not target-blind before anchor freeze",
    )

    baseline_terms = [
        *SPATIAL_TERMS,
        *model13_freeze["feature_preparation"]["eligible_combined_features"],
    ]
    require(
        len(baseline_terms) == 11
        and len(baseline_terms) == len(set(baseline_terms))
        and not set(baseline_terms) & set(FEATURE_IDS),
        "MODEL14_G2_BASELINE_TERM_AUTHORITY_MISMATCH",
        "Generation-2 baseline terms differ from accepted MODEL-13 authority",
    )
    anchor_features = _accepted_anchor_features(
        repository_root=root,
        model11=model11,
        model12=model12,
        michigan_features=michigan_features,
        model13_freeze=model13_freeze,
        component_rows=public_freeze.components,
    )
    anchor_package = _write_anchor_freeze(
        output,
        anchor_features,
        model13_freeze,
    )
    anchor_ready = output / GENERATION2_ANCHOR_DIRECTORY / "READY.json"
    require(
        anchor_ready.is_file()
        and anchor_package["chronology"][
            "generation2_target_values_accessed_during_anchor_recomputation"
        ]
        == 0,
        "MODEL14_G2_ANCHOR_FREEZE_NOT_READY",
        "Generation-2 target-blind anchor freeze is not ready before target access",
    )

    # This is the first target-bearing phase.  It is limited to the already
    # consumed accepted MODEL-13 development cohort.
    verification = verify_persisted_binding(
        repository_root=root,
        resolver=pipe05,
        run_dir=pipe05_run,
    )
    require(
        verification.get("state") == "MATCH"
        and verification.get("valid_isolated_sales_binding_count") == 138,
        "MODEL14_G2_PIPE05_BINDING_VERIFICATION_FAILED",
        "accepted PIPE-05 development binding did not reconcile",
    )
    pipe05_binding = _load_object(
        pipe05_run / BINDING_FILENAME,
        "MODEL14_G2_PIPE05_BINDING_UNRESOLVED",
    )
    protected_rows = _development_rows(model13_freeze, model11, pipe05_binding)
    _verify_development_cohort(protected_rows)
    rows = _attach_features(protected_rows, anchor_features)
    require(
        all(
            all(_finite(row["features"].get(term)) for term in baseline_terms)
            for row in rows
        ),
        "MODEL14_G2_BASELINE_FEATURE_AUTHORITY_MISMATCH",
        "Generation-2 baseline features differ from accepted MODEL-13",
    )

    candidates, strongest_id, diagnostics, conclusion, reasons = _run_candidates(
        rows,
        baseline_terms,
    )
    commitment = public_freeze.report
    result = {
        "package_id": GENERATION2_EXPERIMENT_PACKAGE_ID,
        "version": "1.0.0",
        "state": "READY",
        "task_id": "MODEL-14",
        "generation": 2,
        "exploratory": True,
        "confirmatory": False,
        "prior_generation_results_known": True,
        "chronology": {
            "public_checkpoint": GENERATION2_PUBLIC_CHECKPOINT,
            "public_checkpoint_verified_before_resolver": True,
            "tracked_commitment_and_two_public_freezes_verified_before_resolver": True,
            "target_blind_anchor_feature_freeze_ready_before_model_evaluation": True,
            "generation2_public_feature_generation_modified_after_freeze": False,
            "sealed_or_prospective_evidence_accessed": False,
        },
        "source": {
            "publisher": contract14["source"]["publisher"],
            "release": contract14["source"]["release"],
            "schema_version": contract14["source"]["schema_version"],
            "taxonomy_semantics": "taxonomy, taxonomy.hierarchy, and basic_category",
            "source_authority_status": "EXPERIMENTAL",
        },
        "frozen_commercial_feature_catalog": [
            {
                "feature_id": item["feature_id"],
                "subfamily": item["subfamily"],
                "aggregation": item["aggregation"],
            }
            for item in contract14["feature_catalog"]
        ],
        "frozen_rules": {
            "geographic_aggregation": {
                "tract_local": True,
                "accepted_state_isolated_five_mile_tract_support": True,
                "radius_m": ANCHOR_RADIUS_M,
                "additional_radius_search": False,
            },
            "quality_status_identity": copy.deepcopy(
                contract14["quality_status_identity_rules"]
            ),
            "taxonomy": copy.deepcopy(contract14["taxonomy_rules"]),
            "missingness": copy.deepcopy(contract14["missingness"]),
        },
        "baseline_terms": list(baseline_terms),
        "baseline_reproduction": diagnostics["baseline_reproduction"],
        "tract_coverage_and_missingness": {
            "tract_count": len(public_freeze.rows),
            "michigan_tract_count": sum(
                row["state"] == "MI" for row in public_freeze.rows.values()
            ),
            "wisconsin_tract_count": sum(
                row["state"] == "WI" for row in public_freeze.rows.values()
            ),
            "accepted_tract_keys_reconciled": True,
            "tracts_dropped": False,
            "coverage": copy.deepcopy(commitment["features"]["coverage"]),
        },
        "development_anchor_coverage": _anchor_coverage(anchor_features),
        "candidates": {
            candidate_id: _strip_predictions(candidate)
            for candidate_id, candidate in candidates.items()
        },
        "strongest_expanded_candidate_id": strongest_id,
        "paired_fold_stability": diagnostics["paired_fold_stability"],
        "expanded_candidate_disposition_screen": diagnostics[
            "expanded_candidate_disposition_screen"
        ],
        "paired_outlier_sensitivity": diagnostics["paired_outlier_sensitivity"],
        "ablations": diagnostics["ablations"],
        "evidence_disposition": conclusion,
        "disposition_evidence": reasons,
        "protected_local_only": True,
        "ready_marker_written_last": True,
    }
    package_path = output / GENERATION2_PROTECTED_RESULT_FILENAME
    write_json_exclusive(package_path, result)
    safe = build_generation2_disclosure_safe_result(result)
    safe_path = output / GENERATION2_SAFE_RESULT_FILENAME
    write_json_exclusive(safe_path, safe)
    write_json_exclusive(
        output / "READY.json",
        {
            "state": "READY",
            "package_id": GENERATION2_EXPERIMENT_PACKAGE_ID,
            "generation": 2,
            "exploratory": True,
            "confirmatory": False,
            "experiment_file_sha256": file_sha256(package_path),
            "disclosure_safe_file_sha256": file_sha256(safe_path),
            "baseline_reproduction_state": safe["accepted_predecessor"][
                "baseline_reproduction"
            ]["state"],
            "evidence_disposition": safe["evidence_disposition"],
            "sealed_or_prospective_evidence_accessed": False,
            "protected_characteristic_scoring_feature_used": False,
            "ready_marker_written_last": True,
        },
    )
    return safe
