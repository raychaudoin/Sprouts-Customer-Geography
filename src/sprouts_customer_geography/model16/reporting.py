"""Explicit public projection of protected MODEL-16 aggregate results.

This module has no file, workbook, network, or target access. The caller supplies
the already-public target-blind catalog and private completed results. Never
serialize a DevelopmentResult directly: its parameters, predictions, identities,
fold membership, and fingerprints are intentionally outside this projection.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import math
from numbers import Real
import re
from typing import Any, Mapping, Sequence

from sprouts_customer_geography.pipe01.errors import require

BASELINE = "clean_model13_baseline"
CORE_CANDIDATES = frozenset({BASELINE, "ridge", "lasso", "elastic_net", "spline_ridge", "pca_ridge", "random_forest", "extra_trees", "gradient_boosting", "state_partial_pooling", "simple_log_ensemble", "baseline_terms_ridge"})
ARCHITECTURES = frozenset({"baseline_elastic_net", "ridge", "elastic_net", "spline_ridge", "pca_ridge", "random_forest", "extra_trees", "gradient_boosting", "state_partial_pooling", "simple_log_ensemble"})
EXPERIMENTS = frozenset({"core_library", "family_add", "family_remove", "family_reference"})
REJECTIONS = frozenset({"NO_MATERIAL_POOLED_IMPROVEMENT", "MI_DETERIORATION", "WI_DETERIORATION", "IMPROVEMENT_NOT_REPEATABLE_ACROSS_FOLDS", "LOW_FEATURE_STABILITY", "WORST_LOCATION_SENSITIVITY", "ANY_LOCATION_SENSITIVITY", "MARKET_CONCENTRATION_SENSITIVITY", "ENSEMBLE_CONSTITUENT_UNAVAILABLE", "ENSEMBLE_NOT_BETTER_THAN_CONSTITUENTS", "ENSEMBLE_GAIN_INCONSISTENT", "SOURCE_FAMILY_DEPENDENCE"})
UNAVAILABLE_REASONS = frozenset({
    "MODEL16_ARCHITECTURE_UNDECLARED", "MODEL16_ARRAY_SHAPE_INVALID", "MODEL16_BASELINE_FEATURES_EMPTY", "MODEL16_BASELINE_FEATURES_INVALID", "MODEL16_BASELINE_RETAINED_FEATURE_MISSING", "MODEL16_BOTH_STATES_REQUIRED", "MODEL16_CANDIDATE_FEATURES_INVALID", "MODEL16_CANDIDATE_ID_DUPLICATE", "MODEL16_CATALOG_DIMENSION_MISMATCH", "MODEL16_CROSS_MARKET_GROUP_UNRESOLVED", "MODEL16_CROSS_STATE_GROUP", "MODEL16_EMPTY_PARAMETER_GRID", "MODEL16_FAMILY_BOUND_EXCEEDED", "MODEL16_FEATURE_DIMENSION_MISMATCH", "MODEL16_FEATURE_NAME_DUPLICATE", "MODEL16_FOLDS_INVALID", "MODEL16_FREEZE_INVALID", "MODEL16_GROUP_STATE_INVALID", "MODEL16_GROUPS_EMPTY", "MODEL16_HOLDOUT_FEATURE_CATALOG_CHANGED", "MODEL16_HOLDOUT_IN_DEVELOPMENT", "MODEL16_HOLDOUT_ROLE_INVALID", "MODEL16_INFINITE_FEATURE", "MODEL16_INNER_LOCATION_LEAKAGE", "MODEL16_LIBRARY_INVALID", "MODEL16_LIBRARY_MISSING", "MODEL16_LIBRARY_UNREADABLE", "MODEL16_MARKET_LENGTH_MISMATCH", "MODEL16_METADATA_LENGTH_MISMATCH", "MODEL16_METRIC_PREDICTIONS_INVALID", "MODEL16_NO_COMPUTABLE_TRAIN_FEATURES", "MODEL16_OUTER_LOCATION_LEAKAGE", "MODEL16_PCA_RANK_ZERO", "MODEL16_PREDICT_FEATURE_DIMENSION_MISMATCH", "MODEL16_PREDICT_FEATURE_ORDER_MISMATCH", "MODEL16_PREDICT_STATE_INVALID", "MODEL16_PREDICTION_NONFINITE", "MODEL16_PREPROCESSOR_CONSTANT", "MODEL16_PURSUED_COHORT_INVALID", "MODEL16_PURSUED_IN_DEVELOPMENT", "MODEL16_PURSUED_SEED_IDENTITY_MEMBERSHIP_REQUIRED", "MODEL16_SOLVER_NONCONVERGENCE", "MODEL16_STATE_FOLD_SUPPORT_INSUFFICIENT", "MODEL16_TARGET_INVALID", "MODEL16_TEMPORAL_COHORT_INVALID", "MODEL16_TRANSFORM_NONFINITE",
})
METRICS = ("spearman", "kendall_tau_b", "log_rmse", "level_mae", "calibration_slope", "calibration_intercept", "top_quartile_overlap", "location_weighted_row_log_rmse", "location_weighted_row_level_mae")
DOMAINS = ("pooled", "MI", "WI")
SUBSETS = ("all", "independent_development_location", "matched_development_location", "independent_of_all_seedpoints", "matched_seedpoint_location")
_PUBLIC_SLUG = re.compile(r"^[a-z][a-z0-9_]{0,79}$")


def _number(value: Any, *, integer: bool = False) -> float | int | None:
    if value is None:
        return None
    require(isinstance(value, Real) and not isinstance(value, bool) and math.isfinite(float(value)), "MODEL16_PUBLIC_NUMBER_INVALID", "public metrics require finite aggregate numbers")
    if integer:
        require(float(value).is_integer() and value >= 0, "MODEL16_PUBLIC_COUNT_INVALID", "public counts require nonnegative integers")
        return int(value)
    return float(value)


def _boolean(value: Any) -> bool:
    if type(value) is bool:
        return value
    # NumPy is an optional caller type here, not a reporting dependency.
    if type(value).__module__ == "numpy" and type(value).__name__ in {"bool", "bool_"}:
        return bool(value)
    require(False, "MODEL16_PUBLIC_BOOLEAN_INVALID", "public flags require boolean values")


def _metrics(raw: Mapping[str, Any] | None, *, differences: bool = False) -> dict[str, Any] | None:
    if raw is None:
        return None
    require(isinstance(raw, Mapping), "MODEL16_PUBLIC_METRICS_INVALID", "aggregate metrics must be a mapping")
    result = {name: _number(raw.get(name)) for name in METRICS if name in raw}
    if not differences:
        for key in ("observations", "physical_locations"):
            require(key in raw, "MODEL16_PUBLIC_COUNT_MISSING", "aggregate cohort counts are required")
            result[key] = _number(raw[key], integer=True)
        require(result["physical_locations"] <= result["observations"], "MODEL16_PUBLIC_COUNT_INVALID", "physical-location counts cannot exceed observations")
        result["rank_defined"] = _boolean(raw.get("rank_defined"))
    return result


def _domains(raw: Mapping[str, Any], *, differences: bool = False) -> dict[str, Any]:
    require(isinstance(raw, Mapping) and all(domain in raw for domain in DOMAINS), "MODEL16_PUBLIC_DOMAINS_INVALID", "pooled and both state aggregates are required")
    return {domain: _metrics(raw[domain], differences=differences) for domain in DOMAINS}


def aggregate_evidence_counts(observations: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Retain only role/state/year counts; identities never leave this function."""
    counts: Counter = Counter()
    groups: dict[tuple, set] = defaultdict(set)
    for row in observations:
        key = (row.get("state"), row.get("forecast_year"), row.get("evidence_class"), row.get("role"))
        require(key[0] in {"MI", "WI"} and key[1] in {2024, 2025, 2026} and key[2] in {"SEED_POINT", "PURSUED_SITE"} and key[3] in {"development", "temporal_test", "pursued_test", "excluded", "unresolved"}, "MODEL16_PUBLIC_EVIDENCE_DOMAIN_INVALID", "the evidence-count dimensions are outside the public allowlist")
        require(isinstance(row.get("physical_location_id"), str) and bool(row["physical_location_id"]), "MODEL16_PUBLIC_EVIDENCE_GROUP_MISSING", "location counts require protected exact grouping")
        counts[key] += 1
        groups[key].add(row["physical_location_id"])
    return [{"state": key[0], "forecast_year": key[1], "evidence_class": key[2], "role": key[3], "observations": count, "physical_locations": len(groups[key])} for key, count in sorted(counts.items())]


def _sensitivity(raw: Mapping[str, Any]) -> dict[str, Any]:
    worst = raw["worst_error_location_removed"]
    result = {"worst_error_location_removed": {"candidate": _domains(worst["candidate"]), "baseline": _domains(worst["baseline"])}}
    ratios, deltas = [], []
    for item in raw.get("each_market_removed", []):
        candidate = _metrics(item["candidate"]["pooled"])
        baseline = _metrics(item["baseline"]["pooled"])
        if baseline["log_rmse"] > 0:
            ratios.append(candidate["log_rmse"] / baseline["log_rmse"])
        if candidate["spearman"] is not None and baseline["spearman"] is not None:
            deltas.append(candidate["spearman"] - baseline["spearman"])
    result["market_omission_summary"] = {"assessments": len(raw.get("each_market_removed", [])), "maximum_error_ratio": _number(max(ratios)) if ratios else None, "minimum_rank_delta": _number(min(deltas)) if deltas else None}
    if "all_location_omission_summary" in raw:
        summary = raw["all_location_omission_summary"]
        require(isinstance(summary, Mapping) and {"evaluated_locations", "maximum_error_ratio", "minimum_rank_delta"} <= set(summary), "MODEL16_PUBLIC_SENSITIVITY_INVALID", "all-location sensitivity requires bounded aggregate fields")
        result["all_location_omission_summary"] = {"evaluated_locations": _number(summary["evaluated_locations"], integer=True), "maximum_error_ratio": _number(summary["maximum_error_ratio"]), "minimum_rank_delta": _number(summary["minimum_rank_delta"])}
    return result


def _holdout(raw: Mapping[str, Any] | None, role: str, models: set[str]) -> dict[str, Any] | None:
    if raw is None:
        return None
    evaluation = raw.get("evaluation", raw)
    require(evaluation.get("role") == role and evaluation.get("generation") == 1 and evaluation.get("refit") is False, "MODEL16_PUBLIC_HOLDOUT_INVALID", "only completed frozen Generation 1 evaluations may be reported")
    require(set(evaluation["models"]) == models, "MODEL16_PUBLIC_HOLDOUT_MODELS_INVALID", "holdout models must match the single frozen baseline and optional challenger")
    output = {"role": role, "generation": 1, "refit": False, "models": {}}
    for candidate in sorted(models):
        subsets = evaluation["models"][candidate]["subsets"]
        expected = set(SUBSETS if role == "pursued_sites" else SUBSETS[:3])
        require(set(subsets) == expected, "MODEL16_PUBLIC_HOLDOUT_SUBSETS_INVALID", "holdout results require exact independent and matched subsets")
        output["models"][candidate] = {"subsets": {name: None if subsets[name] is None else _domains(subsets[name]) for name in SUBSETS if name in subsets}}
    if "excluded_count" in raw:
        output["excluded_observations"] = _number(raw["excluded_count"], integer=True)
    return output


def _recommendation(challenger: str | None, temporal: Mapping[str, Any] | None, pursued: Mapping[str, Any] | None, library: Mapping[str, Any]) -> dict[str, Any]:
    result = {"successor_accepted": False, "merge_authorized": False, "generation_2_authorized": False, "accepted_model_unchanged": "MODEL-13"}
    if challenger is None:
        return {**result, "decision": "RETAIN_MODEL13", "reasons": ["NO_DEVELOPMENT_CHALLENGER_PASSED"], "plain_english": "Retain MODEL-13 as the accepted model. No bounded challenger cleared the development gates, so this rebuild does not support replacing it. Any further development requires separate authority."}
    if temporal is None or pursued is None:
        return {**result, "decision": "CONTINUE_DEVELOPMENT", "reasons": ["FINAL_EVALUATION_INCOMPLETE"], "plain_english": "Replacement is not supported while final evidence is incomplete. MODEL-13 remains accepted; complete the authorized frozen evaluations before making a successor decision."}
    selection = library["selection"]
    policy = library["holdout_evaluation"]
    min_independent = int(policy["minimum_independent_locations_for_replacement_evidence"])
    min_state = int(policy["minimum_state_locations_for_domain_claim"])
    reasons = []
    independent_temporal = temporal["models"][challenger]["subsets"]["independent_development_location"]
    if independent_temporal is None or independent_temporal["pooled"]["physical_locations"] < min_independent:
        reasons.append("TEMPORAL_INDEPENDENT_INSUFFICIENT_LOCATIONS")
    for label, evaluation, subset in (("TEMPORAL", temporal, "all"), ("PURSUED_INDEPENDENT", pursued, "independent_of_all_seedpoints")):
        c = evaluation["models"][challenger]["subsets"][subset]
        b = evaluation["models"][BASELINE]["subsets"][subset]
        if c is None or b is None or c["pooled"]["physical_locations"] < min_independent:
            reasons.append(label + "_INSUFFICIENT_LOCATIONS")
            continue
        pooled = c["pooled"]
        base = b["pooled"]
        rank_delta = None if pooled["spearman"] is None or base["spearman"] is None else pooled["spearman"] - base["spearman"]
        rank_route = rank_delta is not None and rank_delta >= selection["minimum_rank_improvement"] and pooled["log_rmse"] <= base["log_rmse"] * selection["rank_route_max_error_ratio"]
        error_route = rank_delta is not None and rank_delta >= selection["error_route_min_rank_delta"] and pooled["log_rmse"] <= base["log_rmse"] * selection["error_route_max_error_ratio"]
        if not (rank_route or error_route):
            reasons.append(label + "_MATERIAL_IMPROVEMENT_NOT_CONFIRMED")
        for state in ("MI", "WI"):
            state_c, state_b = c[state], b[state]
            if state_c is None or state_b is None or state_c["physical_locations"] < min_state:
                reasons.append(label + "_" + state + "_INSUFFICIENT_LOCATIONS")
            elif state_c["spearman"] is None or state_b["spearman"] is None or state_c["spearman"] < state_b["spearman"] - selection["maximum_state_rank_deterioration"] or state_c["log_rmse"] > state_b["log_rmse"] * selection["maximum_state_error_ratio"]:
                reasons.append(label + "_" + state + "_NONINFERIORITY_NOT_CONFIRMED")
    if reasons:
        return {**result, "decision": "CONTINUE_DEVELOPMENT", "reasons": reasons, "plain_english": "Retain MODEL-13 for now. The frozen challenger does not establish enough consistent independent evidence for replacement. Further development would require a newly authorized descendant generation; Generation 1 is closed to retuning."}
    return {**result, "decision": "REPLACEMENT_SUPPORTED_FOR_REVIEW", "reasons": ["DEVELOPMENT_AND_BOUNDED_HOLDOUT_EVIDENCE_SUPPORT_SUCCESSOR_REVIEW"], "plain_english": "The bounded evidence supports considering the frozen challenger as a MODEL-13 replacement. Independent review and Ray's acceptance of the exact candidate remain required; this report does not replace the accepted model or establish production readiness."}


def build_public_report(development: Any, temporal_result: Mapping[str, Any] | None, pursued_result: Mapping[str, Any] | None, *, public_catalog: Mapping[str, Any], observations: Sequence[Mapping[str, Any]] | None = None, public_missingness: Mapping[str, Mapping[str, Any]] | None = None) -> dict[str, Any]:
    """Build a closed report from known analytical outputs and public metadata."""
    families = {feature["family"] for feature in public_catalog["features"]}
    require(all(isinstance(family, str) and _PUBLIC_SLUG.fullmatch(family) for family in families), "MODEL16_PUBLIC_CATALOG_INVALID", "source family labels must come from the public feature catalog")
    allowed = CORE_CANDIDATES | {f"family_{operation}__{family}" for operation in ("add", "remove") for family in families}
    selection = development.selection
    challenger = selection.get("challenger_id")
    require(selection.get("baseline_id") == BASELINE and (challenger is None or challenger in allowed and challenger != BASELINE) and selection.get("generation") == 1 and selection.get("post_holdout_retuning_allowed") is False, "MODEL16_PUBLIC_SELECTION_INVALID", "only the frozen bounded Generation 1 selection may be reported")
    models = {BASELINE} | ({challenger} if challenger is not None else set())
    diagnostics = []
    seen = set()
    for raw in development.diagnostics:
        name = raw["candidate_id"]
        require(name in allowed and name not in seen and raw["architecture"] in ARCHITECTURES and raw["experiment"] in EXPERIMENTS and raw.get("family") in families | {None} and raw["status"] in {"EVALUATED", "UNAVAILABLE"}, "MODEL16_PUBLIC_CANDIDATE_INVALID", "a candidate label or status is outside the frozen public library")
        seen.add(name)
        item = {"candidate_id": name, "architecture": raw["architecture"], "experiment": raw["experiment"], "family": raw.get("family"), "status": raw["status"], "frozen": name in models}
        if raw["status"] == "UNAVAILABLE":
            # An unknown free-form exception is never echoed. Known finite
            # modeling reason codes preserve the actual candidate failure.
            item["reason"] = raw.get("reason") if raw.get("reason") in UNAVAILABLE_REASONS else "BOUNDED_CANDIDATE_UNAVAILABLE"
        else:
            rejections = raw.get("qualification_rejections", [])
            require(set(rejections) <= REJECTIONS, "MODEL16_PUBLIC_QUALIFICATION_INVALID", "qualification reasons are outside the bounded allowlist")
            item.update(aggregate_oof=_domains(raw["aggregate_oof"]), fold_metrics=[_domains(fold) for fold in raw["fold_metrics"]], paired_fold_differences=[_domains(fold, differences=True) for fold in raw["paired_fold_differences"]], stability_score=_number(raw["stability"]["score"]), qualification_rejections=list(rejections), sensitivity=_sensitivity(raw["sensitivity"]))
            robustness = []
            for diagnostic in raw.get("same_architecture_family_robustness", []):
                require(diagnostic["family"] in families and diagnostic["status"] in {"BASELINE_ONLY_FAMILY", "EVALUATED", "UNAVAILABLE"} and type(diagnostic["passes"]) is bool, "MODEL16_PUBLIC_FAMILY_INVALID", "family diagnostics require bounded public labels")
                projected = {"family": diagnostic["family"], "status": diagnostic["status"], "passes": diagnostic["passes"]}
                if diagnostic["status"] == "EVALUATED":
                    projected["aggregate_oof"] = _domains(diagnostic["aggregate_oof"])
                elif diagnostic["status"] == "UNAVAILABLE":
                    projected["reason"] = diagnostic.get("reason") if diagnostic.get("reason") in UNAVAILABLE_REASONS else "BOUNDED_CANDIDATE_UNAVAILABLE"
                robustness.append(projected)
            item["same_architecture_family_robustness"] = robustness
        diagnostics.append(item)
    require(models <= seen, "MODEL16_PUBLIC_FROZEN_MODEL_MISSING", "every frozen model must have reported development diagnostics")
    contributions = []
    for raw in development.family_contributions:
        require(raw["family"] in families and raw["operation"] in {"family_add", "family_remove"} and raw["candidate_id"] in seen and raw["reference_id"] in seen, "MODEL16_PUBLIC_FAMILY_INVALID", "source contribution must reference reported public candidates")
        contributions.append({"family": raw["family"], "operation": raw["operation"], "candidate_id": raw["candidate_id"], "reference_id": raw["reference_id"], "differences": _domains(raw["differences"], differences=True), "paired_fold_differences": [_domains(fold, differences=True) for fold in raw["paired_fold_differences"]]})
    missingness = {}
    public_features = {feature["feature_id"] for feature in public_catalog["features"]}
    require(all(isinstance(feature, str) and _PUBLIC_SLUG.fullmatch(feature) for feature in public_features), "MODEL16_PUBLIC_CATALOG_INVALID", "feature labels must come from the public feature catalog")
    for feature, counts in (public_missingness or {}).items():
        require(feature in public_features and isinstance(counts, Mapping) and set(counts) <= {"development", "temporal_test", "pursued_test", "excluded", "unresolved", "all"}, "MODEL16_PUBLIC_MISSINGNESS_INVALID", "missingness counts must use public feature and evidence-role labels")
        projected_counts = {}
        for role, count in sorted(counts.items()):
            if isinstance(count, Mapping):
                require(set(count) <= {"all", "MI", "WI"}, "MODEL16_PUBLIC_MISSINGNESS_INVALID", "missingness domains must use both states or their pooled count")
                projected_counts[role] = {state: _number(number, integer=True) for state, number in sorted(count.items())}
            else:
                projected_counts[role] = _number(count, integer=True)
        missingness[feature] = projected_counts
    temporal = _holdout(temporal_result, "temporal_2026", models)
    pursued = _holdout(pursued_result, "pursued_sites", models)
    report = {"artifact_id": "MODEL16_PUBLIC_BOUNDED_RESULTS_V1", "generation": 1, "metric_unit": "physical_location_mean", "development_years": [2024, 2025], "selection": {"baseline_id": BASELINE, "challenger_id": challenger, "decision": "CHALLENGER_FROZEN" if challenger else "NO_CREDIBLE_CHALLENGER"}, "feature_catalog": {"features": len(public_catalog["features"]), "family_feature_counts": dict(sorted(Counter(feature["family"] for feature in public_catalog["features"]).items()))}, "candidates": diagnostics, "source_family_contributions": contributions, "temporal_2026": temporal, "pursued_sites": pursued, "evidence_counts": [] if observations is None else aggregate_evidence_counts(observations), "recommendation": _recommendation(challenger, temporal, pursued, development.library), "limitations": ["Public-data customer-geography proxy; no proprietary-model equivalence or production-readiness claim.", "Matched physical locations are not independent external evidence; temporal rank metrics do not measure within-location change.", "Development candidate selection is not independent confirmation; all preprocessing and tuning remained inside location-grouped nested validation.", "Parameters, exact memberships, predictions, source identities, protected hashes and local paths remain protected.", "Source vintages, coverage limits and fixed-snapshot structural features must be interpreted with the public source report."]}
    report["feature_missingness_by_role"] = dict(sorted(missingness.items()))
    return report


def render_markdown(report: Mapping[str, Any]) -> str:
    """Render only the closed output of build_public_report, never private input."""
    require(report.get("artifact_id") == "MODEL16_PUBLIC_BOUNDED_RESULTS_V1", "MODEL16_PUBLIC_REPORT_INVALID", "the renderer requires the explicit public projection")
    def shown(value):
        return "—" if value is None else str(value) if isinstance(value, int) else f"{value:.4f}"
    lines = ["# MODEL-16 bounded Generation 1 results", "", report["recommendation"]["plain_english"], "", "All development comparisons use 2024–2025 Seed Points with deterministic physical-location-grouped nested validation and equal total fitting weight per location. Metrics below use one mean forecast/prediction pair per location; the JSON includes row-weighted error diagnostics, state results, fold results and calibration.", "", "## Candidate comparison", "", "| Candidate | State/status | Spearman | Kendall | Log RMSE | Level MAE | Top-quartile overlap | Stability |", "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for item in report["candidates"]:
        if item["status"] != "EVALUATED":
            lines.append(f"| {item['candidate_id']} | Unavailable | — | — | — | — | — | — |")
            continue
        for domain in DOMAINS:
            m = item["aggregate_oof"][domain]
            if m is not None:
                values = " | ".join(shown(m.get(key)) for key in ("spearman", "kendall_tau_b", "log_rmse", "level_mae", "top_quartile_overlap"))
                lines.append(f"| {item['candidate_id']} | {domain} | {values} | {shown(item['stability_score'])} |")
    lines += ["", "## Selection and sensitivity", "", f"Frozen baseline: `{report['selection']['baseline_id']}`. Frozen challenger: `{report['selection']['challenger_id'] or 'none'}`.", ""]
    for item in report["candidates"]:
        if item["status"] == "EVALUATED" and item["candidate_id"] != BASELINE:
            rejected = ", ".join(item["qualification_rejections"]) or "cleared development gates"
            lines.append(f"- `{item['candidate_id']}`: {rejected}.")
    lines += ["", "Worst-location omission diagnostics, aggregate sensitivity across all development locations, anonymous market-omission summaries, fold differences, and same-architecture family robustness results are retained in the accompanying public JSON. They describe fixed out-of-fold predictions and do not authorize target-conditioned refits.", "", "## Source-family contribution", "", "Addition error differences below zero favor adding a family. Removal error differences above zero show loss from removing a family. These are development diagnostics, not causal effects.", "", "| Family | Operation | Reference | Pooled Spearman difference | Pooled log RMSE difference |", "| --- | --- | --- | ---: | ---: |"]
    for item in report["source_family_contributions"]:
        m = item["differences"]["pooled"]
        lines.append(f"| {item['family']} | {item['operation']} | {item['reference_id']} | {shown(m.get('spearman'))} | {shown(m.get('log_rmse'))} |")
    for key, title in (("temporal_2026", "One-time 2026 Seed Point evaluation"), ("pursued_sites", "One-time pursued-site evaluation")):
        lines += ["", "## " + title, ""]
        evaluation = report[key]
        if evaluation is None:
            lines += ["Evaluation is incomplete."]
            continue
        lines += ["| Model | Subset | Domain | Observations | Locations | Spearman | Kendall | Log RMSE | Level MAE |", "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
        for name, model in evaluation["models"].items():
            for subset, domains in model["subsets"].items():
                if domains is None:
                    lines.append(f"| {name} | {subset} | Empty | 0 | 0 | — | — | — | — |")
                    continue
                for domain in DOMAINS:
                    m = domains[domain]
                    if m is not None:
                        values = " | ".join(shown(m.get(metric)) for metric in ("observations", "physical_locations", "spearman", "kendall_tau_b", "log_rmse", "level_mae"))
                        lines.append(f"| {name} | {subset} | {domain} | {values} |")
    lines += ["", "## Evidence accounting", "", "| State | Year | Evidence class | Role | Observations | Locations |", "| --- | ---: | --- | --- | ---: | ---: |"]
    for item in report["evidence_counts"]:
        lines.append(f"| {item['state']} | {item['forecast_year']} | {item['evidence_class']} | {item['role']} | {item['observations']} | {item['physical_locations']} |")
    lines += ["", "Counts are within each displayed group; locations repeated across years or evidence classes must not be summed as independent locations.", "", "## Limits", ""]
    lines.extend("- " + limitation for limitation in report["limitations"])
    lines.append("")
    return "\n".join(lines)
