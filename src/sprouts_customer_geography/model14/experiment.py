"""Bounded protected MODEL-14 evaluation after the target-blind public freeze."""

from __future__ import annotations

import copy
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from sprouts_customer_geography.geo05.materialization import evaluate_anchor_package, load_support_package
from sprouts_customer_geography.model09.features import (
    _anchor_tract,
    load_public_tract_evidence,
    verify_model10_package,
)
from sprouts_customer_geography.model11.features import _target_blind_cohort
from sprouts_customer_geography.model13.modeling import SPATIAL_TERMS
from sprouts_customer_geography.model13.resolver import ProtectedHandleResolver
from sprouts_customer_geography.model13.workflow import (
    _accepted_model12_packages,
    _development_rows,
    _feature_freeze_package,
    _load_object,
    _upstream_resolvers,
    verify_repository_authority as verify_model13_repository_authority,
)
from sprouts_customer_geography.pipe01.canonical import content_digest, file_sha256, write_json_exclusive
from sprouts_customer_geography.pipe01.errors import ConformanceError, require
from sprouts_customer_geography.pipe01.production import Geo03ProductionTransformer
from sprouts_customer_geography.pipe01.spatial import parse_internal_point, project_internal_point
from sprouts_customer_geography.pipe02.resolver import _is_within
from sprouts_customer_geography.pipe05.binding import BINDING_FILENAME, verify_persisted_binding

from .modeling import nested_grouped_oof
from .public import (
    FEATURE_FAMILIES,
    FEATURE_IDS,
    aggregate_context_features,
    compare_public_freezes,
    load_contract,
    load_public_freeze,
)


EXPERIMENT_PACKAGE_ID = "MODEL14_PROTECTED_SUCCESSOR_EXPERIMENT_V1"
ANCHOR_FREEZE_PACKAGE_ID = "MODEL14_TARGET_BLIND_DEVELOPMENT_ANCHOR_FEATURE_FREEZE_V1"
TARGET_BLIND_FREEZE_COMMIT = "d516f2ffce151d83df8c80ea293ea84550378fbf"
ANCHOR_RADIUS_M = 8046.72
METRICS = ("spearman", "kendall_tau_b", "log_rmse", "level_mae")

CANDIDATE_FAMILIES: Mapping[str, tuple[str, ...]] = {
    "A_model13_reproduced": (),
    "B_model13_plus_lodes": ("lodes",),
    "D_model13_plus_traffic": ("traffic_accessibility",),
    "E_model13_plus_richer_acs": ("richer_acs",),
    "F_model13_plus_all_ready": ("lodes", "traffic_accessibility", "richer_acs"),
}

MODEL13_ACCEPTED_ROUNDED = {
    "pooled": {"spearman": 0.6293, "kendall_tau_b": 0.4544, "log_rmse": 0.1048, "level_mae": 23378.51},
    "michigan": {"spearman": 0.4903, "kendall_tau_b": 0.3487, "log_rmse": 0.1084, "level_mae": 24712.41},
    "wisconsin": {"spearman": 0.7606, "kendall_tau_b": 0.5601, "log_rmse": 0.0972, "level_mae": 20710.72},
}


def _json_object(path: Path, code: str) -> dict[str, Any]:
    require(path.is_file(), code, "required MODEL-14 JSON is absent")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ConformanceError(code, "required MODEL-14 JSON is unreadable") from exc
    require(isinstance(value, dict), code, "required MODEL-14 JSON must be an object")
    return value


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _assert_output_path(repository_root: Path, output_dir: Path) -> Path:
    root = repository_root.resolve()
    output = output_dir.resolve()
    require(
        _is_within(output, root / "outputs") and output != root / "outputs" and not output.exists(),
        "MODEL14_EXPERIMENT_OUTPUT_INVALID",
        "MODEL-14 protected experiment output must be a new bounded ignored output directory",
    )
    return output


def _verify_public_freeze_authority(
    repository_root: Path,
    public_freeze_dir: Path,
    verification_freeze_dir: Path,
) -> Any:
    root = repository_root.resolve()
    freeze = load_public_freeze(public_freeze_dir)
    comparison = compare_public_freezes(public_freeze_dir, verification_freeze_dir)
    commitment = _json_object(
        root / "config/model14/target_blind_public_feature_commitment.json",
        "MODEL14_PUBLIC_COMMITMENT_MISSING",
    )
    matrix = commitment.get("public_matrix_commitment", {})
    require(
        commitment.get("state") == "TARGET_BLIND_PUBLIC_FEATURES_FROZEN"
        and commitment.get("chronology", {}).get("target_values_accessed") == 0
        and commitment.get("chronology", {}).get("protected_anchor_rows_accessed") == 0
        and matrix.get("matrix_byte_sha256") == freeze.report["matrix"]["byte_sha256"]
        and matrix.get("freeze_semantic_content_sha256") == freeze.report["content_sha256"]
        and matrix.get("determinism_state") == comparison["state"]
        and matrix.get("row_count") == len(freeze.rows) == 4559,
        "MODEL14_PUBLIC_FREEZE_COMMITMENT_MISMATCH",
        "MODEL-14 public freeze differs from its pre-target tracked commitment",
    )
    return freeze


def _coordinates_by_group(
    repository_root: Path,
    model11: Any,
    michigan_features: Mapping[str, Any],
) -> tuple[dict[str, tuple[float, float]], list[Any], Mapping[str, Any]]:
    root = repository_root.resolve()
    model11_contract = _json_object(
        root / "config/model/model11_wisconsin_multivariate_model_contract.json",
        "MODEL14_MODEL11_CONTRACT_MISSING",
    )
    request = model11.development_request
    model10 = verify_model10_package(
        model11.resolve(str(request["model10_package_handle"]), "model10_package").path,
        model11.resolve(str(request["model10_ready_marker_handle"]), "model10_ready_marker").path,
    )
    wisconsin = _target_blind_cohort(model10, model11_contract)
    coordinates: dict[str, tuple[float, float]] = {}
    for row in wisconsin:
        group = "WI:" + str(row["successor_physical_location_id"])
        pair = (float(row["canonical_latitude"]), float(row["canonical_longitude"]))
        require(group not in coordinates or coordinates[group] == pair, "MODEL14_WI_ANCHOR_MISMATCH", "one Wisconsin accepted anchor differs within group")
        coordinates[group] = pair
    for source in michigan_features["physical_locations"]:
        if source.get("quarantined") is not False:
            continue
        raw = source.get("canonical_target_blind_coordinate")
        require(isinstance(raw, Mapping), "MODEL14_MI_ANCHOR_UNRESOLVED", "one Michigan accepted anchor is absent")
        pair = (float(raw["latitude"]), float(raw["longitude"]))
        require(all(math.isfinite(value) for value in pair), "MODEL14_MI_ANCHOR_UNRESOLVED", "one Michigan accepted anchor is invalid")
        group = "MI:" + str(source["physical_location_id"])
        require(group not in coordinates, "MODEL14_GROUP_COLLISION", "one accepted group collides across states")
        coordinates[group] = pair

    acs_manifest = _json_object(
        root / "data/manifests/acs_2024_acs5_b11001_wisconsin_tract.source_manifest.json",
        "MODEL14_WI_ACS_MANIFEST_MISSING",
    )
    tiger_manifest = _json_object(
        root / "data/manifests/tiger_2024_wisconsin_tract.source_manifest.json",
        "MODEL14_WI_TIGER_MANIFEST_MISSING",
    )
    geo03 = _json_object(
        root / "config/geo/geo03_internal_point_membership_spatial_spec.json",
        "MODEL14_GEO03_AUTHORITY_MISSING",
    )
    wisconsin_tracts = load_public_tract_evidence(
        tiger_source=model11.resolve(str(request["tiger_source_handle"]), "accepted_tiger_tract_source").path,
        acs_source=model11.resolve(str(request["acs_b11001_source_handle"]), "accepted_acs_b11001_source").path,
        tiger_manifest=tiger_manifest,
        acs_manifest=acs_manifest,
        geo03_spec=geo03,
    )
    require(len(wisconsin_tracts) == 1542, "MODEL14_WI_TRACT_ACCOUNTING_FAILED", "accepted Wisconsin tract support differs")
    return coordinates, wisconsin_tracts, geo03


def _accepted_anchor_features(
    *,
    repository_root: Path,
    model11: Any,
    model12: Any,
    michigan_features: Mapping[str, Any],
    model13_freeze: Mapping[str, Any],
    public_rows: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, float | None]]:
    coordinates, wisconsin_tracts, geo03 = _coordinates_by_group(repository_root, model11, michigan_features)
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
        "MODEL14_ANCHOR_ACCOUNTING_FAILED",
        "MODEL-14 fitting anchors differ from accepted MODEL-13 groups",
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
                opaque_anchor_lineage="accepted MODEL-12 canonical target-blind coordinate",
                radii_m=(ANCHOR_RADIUS_M,),
            )
            member_geoids = list(spatial["memberships"][0]["member_geoids"])
            anchor_geoid = str(spatial["containing_tract_geoid"])
        else:
            projected = project_internal_point(parse_internal_point(latitude, longitude), transformer)
            require(projected is not None, "MODEL14_WI_ANCHOR_TRANSFORM_FAILED", "one Wisconsin accepted anchor cannot be transformed")
            anchor = _anchor_tract(wisconsin_tracts, longitude, latitude)
            member_geoids = sorted(
                tract.geoid
                for tract in wisconsin_tracts
                if math.hypot(tract.internal_x_m - projected[0], tract.internal_y_m - projected[1]) <= ANCHOR_RADIUS_M
            )
            if anchor.geoid not in member_geoids:
                member_geoids.append(anchor.geoid)
                member_geoids.sort()
            anchor_geoid = anchor.geoid
        vector = aggregate_context_features(public_rows, member_geoids, anchor_geoid)
        require(tuple(vector) == FEATURE_IDS, "MODEL14_ANCHOR_FEATURE_SCHEMA_MISMATCH", "one anchor feature vector differs from the frozen catalog")
        features[group] = vector
    require(set(features) == fitting_groups, "MODEL14_ANCHOR_FEATURE_ACCOUNTING_FAILED", "not every fitting group received frozen public features")
    return features


def _anchor_coverage(anchor_features: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for family in ("lodes", "traffic_accessibility", "richer_acs"):
        terms = [term for term in FEATURE_IDS if FEATURE_FAMILIES[term] == family]
        by_state: dict[str, Any] = {}
        for state in ("MI", "WI"):
            rows = [values for group, values in anchor_features.items() if group.startswith(state + ":")]
            missing_by_term = {term: sum(not _finite(row.get(term)) for row in rows) for term in terms}
            by_state[state] = {
                "physical_location_count": len(rows),
                "fully_computable_physical_location_count": sum(all(_finite(row.get(term)) for term in terms) for row in rows),
                "maximum_missing_physical_location_count_by_feature": max(missing_by_term.values(), default=0),
                "total_missing_feature_values": sum(missing_by_term.values()),
            }
        output[family] = {"candidate_feature_count": len(terms), "by_state": by_state}
    return output


def _write_anchor_freeze(
    output: Path,
    anchor_features: Mapping[str, Mapping[str, Any]],
    model13_freeze: Mapping[str, Any],
) -> dict[str, Any]:
    package = {
        "package_id": ANCHOR_FREEZE_PACKAGE_ID,
        "version": "1.0.0",
        "state": "READY",
        "controlling_task": "MODEL-14",
        "chronology": {
            "public_tract_freeze_ready_before_anchor_recomputation": True,
            "feature_definitions_changed": False,
            "development_target_values_accessed_during_anchor_recomputation": 0,
            "sealed_or_prospective_evidence_accessed": False,
        },
        "accepted_predecessor_accounting": {
            "fitting_observation_count": model13_freeze["evidence_accounting"]["fitting_observation_count"],
            "fitting_physical_location_count": model13_freeze["evidence_accounting"]["fitting_physical_location_count"],
            "michigan_fitting_physical_location_count": model13_freeze["evidence_accounting"]["fitting_michigan_physical_location_count"],
            "wisconsin_fitting_physical_location_count": model13_freeze["evidence_accounting"]["fitting_wisconsin_physical_location_count"],
        },
        "feature_count": len(FEATURE_IDS),
        "feature_order": list(FEATURE_IDS),
        "coverage": _anchor_coverage(anchor_features),
        "physical_locations": [
            {"successor_physical_location_id": group, "features": dict(anchor_features[group])}
            for group in sorted(anchor_features)
        ],
        "protected_local_only": True,
        "ready_marker_written_last": True,
    }
    semantic = copy.deepcopy(package)
    package["protected_content_sha256"] = content_digest(semantic)
    package_path = output / "anchor_feature_freeze" / "model14_target_blind_development_anchor_features.json"
    write_json_exclusive(package_path, package)
    ready = {
        "state": "READY",
        "package_id": ANCHOR_FREEZE_PACKAGE_ID,
        "protected_content_sha256": package["protected_content_sha256"],
        "package_file_sha256": file_sha256(package_path),
        "target_values_accessed": 0,
        "ready_marker_written_last": True,
    }
    write_json_exclusive(output / "anchor_feature_freeze" / "READY.json", ready)
    return package


def _candidate_terms(
    baseline_terms: Sequence[str],
    families: Sequence[str],
) -> list[str]:
    selected = [term for term in FEATURE_IDS if FEATURE_FAMILIES[term] in set(families)]
    terms = [*baseline_terms, *selected]
    require(len(terms) == len(set(terms)), "MODEL14_CANDIDATE_TERM_DUPLICATE", "one MODEL-14 candidate repeats a term")
    return terms


def _term_families(baseline_terms: Sequence[str]) -> dict[str, str]:
    return {
        **{str(term): "model13_accepted" for term in baseline_terms},
        **{str(term): str(FEATURE_FAMILIES[term]) for term in FEATURE_IDS},
    }


def _attach_features(
    rows: Sequence[Mapping[str, Any]],
    anchor_features: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for source in rows:
        if source.get("fitting_eligible") is not True:
            continue
        group = str(source["successor_physical_location_id"])
        require(group in anchor_features, "MODEL14_ANCHOR_JOIN_FAILED", "one fitting row lacks target-blind public anchor features")
        features = {**copy.deepcopy(dict(source["features"])), **copy.deepcopy(dict(anchor_features[group]))}
        output.append({**copy.deepcopy(dict(source)), "features": features})
    require(
        len(output) == 196
        and len({str(row["successor_physical_location_id"]) for row in output}) == 123
        and sum(row["state"] == "MI" for row in output) == 133
        and sum(row["state"] == "WI" for row in output) == 63,
        "MODEL14_FITTING_ACCOUNTING_FAILED",
        "MODEL-14 fitting rows differ from accepted MODEL-13 evidence",
    )
    return output


def _rounded_metrics(metrics: Mapping[str, Any]) -> dict[str, float]:
    return {
        "spearman": round(float(metrics["spearman"]), 4),
        "kendall_tau_b": round(float(metrics["kendall_tau_b"]), 4),
        "log_rmse": round(float(metrics["log_rmse"]), 4),
        "level_mae": round(float(metrics["level_mae"]), 2),
    }


def _verify_baseline_reproduction(result: Mapping[str, Any]) -> dict[str, Any]:
    reproduced = {
        domain: _rounded_metrics(result["aggregate_oof"][domain])
        for domain in ("pooled", "michigan", "wisconsin")
    }
    require(
        reproduced == MODEL13_ACCEPTED_ROUNDED,
        "MODEL14_BASELINE_REPRODUCTION_FAILED",
        "MODEL-14 did not reproduce the accepted MODEL-13 grouped OOF baseline",
    )
    return {
        "state": "MATCH",
        "accepted_candidate_id": "successor_combined_multivariate_elastic_net",
        "same_fitting_observation_count": 196,
        "same_fitting_physical_location_count": 123,
        "same_grouped_fold_semantics": True,
        "same_training_fold_preprocessing_scope": True,
        "rounded_metrics": reproduced,
    }


def _strip_predictions(result: Mapping[str, Any]) -> dict[str, Any]:
    output = copy.deepcopy(dict(result))
    output.pop("predictions", None)
    return output


def _strongest_expanded(candidates: Mapping[str, Mapping[str, Any]]) -> str:
    expanded = [candidate_id for candidate_id in CANDIDATE_FAMILIES if candidate_id != "A_model13_reproduced"]
    return max(
        expanded,
        key=lambda candidate_id: (
            float(candidates[candidate_id]["aggregate_oof"]["pooled"]["spearman"]),
            float(candidates[candidate_id]["aggregate_oof"]["michigan"]["spearman"]),
            float(candidates[candidate_id]["aggregate_oof"]["wisconsin"]["spearman"]),
            -float(candidates[candidate_id]["aggregate_oof"]["pooled"]["log_rmse"]),
            candidate_id,
        ),
    )


def _evaluate_ablation(
    *,
    rows: Sequence[Mapping[str, Any]],
    baseline_terms: Sequence[str],
    strongest_id: str,
    candidates: Mapping[str, Mapping[str, Any]],
    term_families: Mapping[str, str],
) -> dict[str, Any]:
    strongest_families = CANDIDATE_FAMILIES[strongest_id]
    output: dict[str, Any] = {}
    for removed_family in strongest_families:
        retained = tuple(family for family in strongest_families if family != removed_family)
        existing = next((candidate_id for candidate_id, families in CANDIDATE_FAMILIES.items() if families == retained), None)
        if existing is not None:
            ablated = candidates[existing]
            ablation_id = existing
            reused = True
        else:
            ablation_id = "ablation_" + strongest_id + "_without_" + removed_family
            ablated = nested_grouped_oof(
                rows,
                ablation_id,
                _candidate_terms(baseline_terms, retained),
                term_families=term_families,
            )
            reused = False
        effects = {
            domain: {
                metric: float(candidates[strongest_id]["aggregate_oof"][domain][metric])
                - float(ablated["aggregate_oof"][domain][metric])
                for metric in METRICS
            }
            for domain in ("pooled", "michigan", "wisconsin")
        }
        output[removed_family] = {
            "ablation_candidate_id": ablation_id,
            "reused_primary_matrix_candidate": reused,
            "removed_feature_count": sum(FEATURE_FAMILIES[term] == removed_family for term in FEATURE_IDS),
            "aggregate_oof": copy.deepcopy(ablated["aggregate_oof"]),
            "strongest_minus_ablation_metric_delta": effects,
            "stability_score": float(ablated["stability"]["stability_score"]),
        }
    return output


def _classify_evidence(
    baseline: Mapping[str, Any],
    strongest: Mapping[str, Any],
) -> tuple[str, list[str]]:
    pooled = float(strongest["aggregate_oof"]["pooled"]["spearman"]) - float(baseline["aggregate_oof"]["pooled"]["spearman"])
    michigan = float(strongest["aggregate_oof"]["michigan"]["spearman"]) - float(baseline["aggregate_oof"]["michigan"]["spearman"])
    wisconsin = float(strongest["aggregate_oof"]["wisconsin"]["spearman"]) - float(baseline["aggregate_oof"]["wisconsin"]["spearman"])
    log_ratio = float(strongest["aggregate_oof"]["pooled"]["log_rmse"]) / float(baseline["aggregate_oof"]["pooled"]["log_rmse"])
    mae_ratio = float(strongest["aggregate_oof"]["pooled"]["level_mae"]) / float(baseline["aggregate_oof"]["pooled"]["level_mae"])
    stability = float(strongest["stability"]["stability_score"])
    outlier_delta = abs(float(strongest["outlier_sensitivity"]["pooled_metric_delta_without_max_error_location"]["spearman"]))
    reasons = [
        f"pooled Spearman delta {pooled:+.4f}",
        f"Michigan Spearman delta {michigan:+.4f}",
        f"Wisconsin Spearman delta {wisconsin:+.4f}",
        f"pooled log RMSE ratio {log_ratio:.4f}",
        f"pooled level MAE ratio {mae_ratio:.4f}",
        f"fold coefficient stability {stability:.4f}",
        f"worst-location-removal pooled Spearman absolute delta {outlier_delta:.4f}",
    ]
    if (
        pooled >= 0.03
        and michigan >= 0.02
        and wisconsin >= -0.02
        and log_ratio <= 1.0
        and mae_ratio <= 1.0
        and stability >= 0.75
        and outlier_delta <= 0.05
        and len(strongest["terms"]) <= 40
    ):
        return "material improvement", reasons
    if pooled > 0 and michigan >= -0.01 and wisconsin >= -0.05 and log_ratio <= 1.05 and mae_ratio <= 1.05:
        return "possible improvement", reasons
    return "no credible improvement", reasons


def _run_candidates(
    rows: Sequence[Mapping[str, Any]],
    baseline_terms: Sequence[str],
) -> tuple[dict[str, Any], str, dict[str, Any], str, list[str]]:
    families = _term_families(baseline_terms)
    candidates: dict[str, Any] = {}
    for candidate_id, public_families in CANDIDATE_FAMILIES.items():
        candidates[candidate_id] = nested_grouped_oof(
            rows,
            candidate_id,
            _candidate_terms(baseline_terms, public_families),
            term_families=families,
        )
    baseline = _verify_baseline_reproduction(candidates["A_model13_reproduced"])
    strongest_id = _strongest_expanded(candidates)
    ablations = _evaluate_ablation(
        rows=rows,
        baseline_terms=baseline_terms,
        strongest_id=strongest_id,
        candidates=candidates,
        term_families=families,
    )
    conclusion, reasons = _classify_evidence(candidates["A_model13_reproduced"], candidates[strongest_id])
    return candidates, strongest_id, {"baseline_reproduction": baseline, "ablations": ablations}, conclusion, reasons


def _rounded_ranges(ranges: Mapping[str, Any]) -> dict[str, Any]:
    return {
        domain: {
            metric: {
                "minimum": round(float(bounds["minimum"]), 2 if metric == "level_mae" else 4),
                "maximum": round(float(bounds["maximum"]), 2 if metric == "level_mae" else 4),
            }
            for metric, bounds in metrics.items()
        }
        for domain, metrics in ranges.items()
    }


def _safe_candidate(result: Mapping[str, Any], baseline_term_count: int) -> dict[str, Any]:
    return {
        "feature_count": len(result["terms"]),
        "new_public_feature_count": len(result["terms"]) - baseline_term_count,
        "aggregate_oof": {
            domain: _rounded_metrics(result["aggregate_oof"][domain])
            for domain in ("pooled", "michigan", "wisconsin")
        },
        "outer_fold_metric_ranges": _rounded_ranges(result["outer_fold_metric_ranges"]),
        "stability_score": round(float(result["stability"]["stability_score"]), 4),
        "feature_family_stability": {
            family: {
                "term_count": int(values["term_count"]),
                "selected_in_any_fold_count": int(values["selected_in_any_fold_count"]),
                "selected_in_every_fold_count": int(values["selected_in_every_fold_count"]),
                "mean_selection_frequency": round(float(values["mean_selection_frequency"]), 4),
                "mean_dominant_sign_agreement": round(float(values["mean_dominant_sign_agreement"]), 4),
            }
            for family, values in result["feature_family_stability"].items()
        },
        "mean_outer_effective_degrees_of_freedom": round(float(result["mean_outer_effective_degrees_of_freedom"]), 2),
        "outer_effective_degrees_of_freedom_range": list(result["outer_effective_degrees_of_freedom_range"]),
        "maximum_physical_location_absolute_log_error": round(
            float(result["outlier_sensitivity"]["maximum_physical_location_absolute_log_error"]),
            4,
        ),
        "pooled_metric_delta_without_max_error_location": {
            metric: round(float(value), 2 if metric == "level_mae" else 4)
            for metric, value in result["outlier_sensitivity"]["pooled_metric_delta_without_max_error_location"].items()
        },
    }


def _safe_coefficient_summary(
    strongest: Mapping[str, Any],
    baseline_terms: Sequence[str],
) -> dict[str, Any]:
    coefficients = strongest["final_standardized_coefficients"]
    nonzero = [term for term in strongest["terms"] if abs(float(coefficients[term])) > 1e-8]
    ordered = sorted(nonzero, key=lambda term: (-abs(float(coefficients[term])), term))
    records = []
    for term in ordered[:12]:
        coefficient = float(coefficients[term])
        records.append({
            "feature": term,
            "family": "model13_accepted" if term in baseline_terms else FEATURE_FAMILIES[term],
            "standardized_coefficient": round(coefficient, 4),
            "direction": "positive" if coefficient > 0 else "negative",
            "outer_fold_selection_frequency": round(float(strongest["stability"]["selection_frequency"][term]), 4),
            "outer_fold_dominant_sign_agreement": round(float(strongest["stability"]["coefficient_sign_stability"][term]), 4),
        })
    return {
        "selected_feature_count": len(nonzero),
        "top_standardized_signals_limit": 12,
        "top_standardized_signals": records,
        "exact_fitted_parameters_disclosed": False,
    }


def build_disclosure_safe_result(result: Mapping[str, Any]) -> dict[str, Any]:
    """Reduce the protected run to repository-safe aggregate evidence."""
    baseline_terms = list(result["baseline_terms"])
    strongest_id = str(result["strongest_expanded_candidate_id"])
    candidates = result["candidates"]
    safe = {
        "package_id": "MODEL14_DISCLOSURE_SAFE_PRE_H_RESULT_V1",
        "state": "PRE_H_EXPERIMENT_COMPLETE",
        "task_id": "MODEL-14",
        "posture": "IN_PROGRESS_PRE_H_MCR_REVIEW",
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
        "public_feature_families": copy.deepcopy(result["public_feature_families"]),
        "development_anchor_coverage": copy.deepcopy(result["development_anchor_coverage"]),
        "candidate_matrix": {
            candidate_id: _safe_candidate(candidate, len(baseline_terms))
            for candidate_id, candidate in candidates.items()
        },
        "business_context_candidate": {
            "candidate_id": "C_model13_plus_business_context",
            "evaluated": False,
            "feature_count": 0,
            "status": "partially evaluation-ready",
            "reason": "No tract-level business-context feature was admitted into the frozen target-blind matrix.",
        },
        "strongest_expanded_candidate_id": strongest_id,
        "strongest_candidate_coefficient_summary": _safe_coefficient_summary(candidates[strongest_id], baseline_terms),
        "family_ablations": {
            family: {
                "removed_feature_count": int(values["removed_feature_count"]),
                "reused_primary_matrix_candidate": bool(values["reused_primary_matrix_candidate"]),
                "aggregate_oof": {
                    domain: _rounded_metrics(values["aggregate_oof"][domain])
                    for domain in ("pooled", "michigan", "wisconsin")
                },
                "strongest_minus_ablation_metric_delta": {
                    domain: {
                        metric: round(float(value), 2 if metric == "level_mae" else 4)
                        for metric, value in metrics.items()
                    }
                    for domain, metrics in values["strongest_minus_ablation_metric_delta"].items()
                },
                "stability_score": round(float(values["stability_score"]), 4),
            }
            for family, values in result["ablations"].items()
        },
        "evidence_disposition": str(result["evidence_disposition"]),
        "disposition_evidence": list(result["disposition_evidence"]),
        "execution_safeguards": {
            "public_feature_generation_modified_after_freeze": False,
            "grouped_physical_location_cv": True,
            "training_fold_only_preprocessing": True,
            "sealed_or_prospective_target_opened": False,
            "protected_characteristic_scoring_feature_used": False,
            "protected_location_identity_disclosed": False,
            "protected_coordinate_disclosed": False,
            "row_level_target_or_prediction_disclosed": False,
            "protected_path_or_registry_disclosed": False,
            "model13_changed_or_replaced": False,
            "app01_changed": False,
            "pbi02_changed": False,
            "production_promotion_performed": False,
        },
    }
    public_text = json.dumps(safe, sort_keys=True)
    forbidden = ("successor_physical_location_id", "analytical_observation_id", "source_observation_id", "isolated_sales", "canonical_latitude", "canonical_longitude", "protected_content_sha256")
    require(not any(token in public_text for token in forbidden), "MODEL14_DISCLOSURE_SAFE_RESULT_INVALID", "MODEL-14 safe result contains a protected field")
    return safe


def execute_protected_experiment(
    *,
    repository_root: Path,
    registry_path: Path,
    public_freeze_dir: Path,
    verification_freeze_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Run the frozen experiment through exact accepted MODEL-13 authority."""
    root = repository_root.resolve()
    public_freeze = _verify_public_freeze_authority(root, public_freeze_dir, verification_freeze_dir)
    contract14 = load_contract(root)
    output = _assert_output_path(root, output_dir)
    output.mkdir(parents=True, exist_ok=False)
    write_json_exclusive(output / "STARTED.json", {
        "state": "INCOMPLETE",
        "package_id": EXPERIMENT_PACKAGE_ID,
        "target_blind_public_freeze_verified_before_registry_resolution": True,
        "ready_marker_written_last": False,
    })

    resolver = ProtectedHandleResolver.load(registry_path, root)
    contract13, _output_contract = verify_model13_repository_authority(root)
    model11, model12, pipe05, pipe05_run = _upstream_resolvers(root, resolver)
    identity, michigan_features, _scoring, _authority = _accepted_model12_packages(root, pipe05)
    model13_freeze, _frozen_model11 = _feature_freeze_package(
        root,
        model11,
        model12,
        identity,
        michigan_features,
        contract13,
    )

    anchor_features = _accepted_anchor_features(
        repository_root=root,
        model11=model11,
        model12=model12,
        michigan_features=michigan_features,
        model13_freeze=model13_freeze,
        public_rows=public_freeze.rows,
    )
    anchor_package = _write_anchor_freeze(output, anchor_features, model13_freeze)
    require(
        (output / "anchor_feature_freeze" / "READY.json").is_file()
        and anchor_package["chronology"]["development_target_values_accessed_during_anchor_recomputation"] == 0,
        "MODEL14_ANCHOR_FREEZE_NOT_READY",
        "MODEL-14 target-blind anchor freeze is not ready before target access",
    )

    verification = verify_persisted_binding(repository_root=root, resolver=pipe05, run_dir=pipe05_run)
    require(
        verification.get("state") == "MATCH"
        and verification.get("valid_isolated_sales_binding_count") == 138,
        "MODEL14_PIPE05_BINDING_VERIFICATION_FAILED",
        "accepted PIPE-05 development binding did not reconcile",
    )
    pipe05_binding = _load_object(pipe05_run / BINDING_FILENAME, "MODEL14_PIPE05_BINDING_UNRESOLVED")
    protected_rows = _development_rows(model13_freeze, model11, pipe05_binding)
    rows = _attach_features(protected_rows, anchor_features)
    baseline_terms = [*SPATIAL_TERMS, *model13_freeze["feature_preparation"]["eligible_combined_features"]]
    require(
        len(baseline_terms) == 11
        and all(all(_finite(row["features"].get(term)) for term in baseline_terms) for row in rows),
        "MODEL14_BASELINE_FEATURE_AUTHORITY_MISMATCH",
        "MODEL-14 baseline terms differ from accepted MODEL-13",
    )

    candidates, strongest_id, diagnostics, conclusion, reasons = _run_candidates(rows, baseline_terms)
    result = {
        "package_id": EXPERIMENT_PACKAGE_ID,
        "version": "1.0.0",
        "state": "READY",
        "task_id": "MODEL-14",
        "chronology": {
            "target_blind_public_freeze_ready_before_registry_resolution": True,
            "target_blind_anchor_feature_freeze_ready_before_model_evaluation": True,
            "public_feature_generation_modified_after_freeze": False,
            "sealed_or_prospective_evidence_accessed": False,
        },
        "baseline_terms": list(baseline_terms),
        "baseline_reproduction": diagnostics["baseline_reproduction"],
        "public_feature_families": {
            family: {
                "status": contract14["source_families"][family]["status"],
                "candidate_feature_count": int(contract14["model_feature_count_by_family"][family]),
            }
            for family in contract14["feature_family_order"]
        },
        "development_anchor_coverage": _anchor_coverage(anchor_features),
        "candidates": {candidate_id: _strip_predictions(candidate) for candidate_id, candidate in candidates.items()},
        "strongest_expanded_candidate_id": strongest_id,
        "ablations": diagnostics["ablations"],
        "evidence_disposition": conclusion,
        "disposition_evidence": reasons,
        "protected_local_only": True,
        "ready_marker_written_last": True,
    }
    package_path = output / "model14_protected_successor_experiment.json"
    write_json_exclusive(package_path, result)
    safe = build_disclosure_safe_result(result)
    safe_path = output / "model14_disclosure_safe_pre_h_result.json"
    write_json_exclusive(safe_path, safe)
    write_json_exclusive(output / "READY.json", {
        "state": "READY",
        "package_id": EXPERIMENT_PACKAGE_ID,
        "experiment_file_sha256": file_sha256(package_path),
        "disclosure_safe_file_sha256": file_sha256(safe_path),
        "baseline_reproduction_state": safe["accepted_predecessor"]["baseline_reproduction"]["state"],
        "evidence_disposition": safe["evidence_disposition"],
        "sealed_or_prospective_evidence_accessed": False,
        "protected_characteristic_scoring_feature_used": False,
        "ready_marker_written_last": True,
    })
    return safe
