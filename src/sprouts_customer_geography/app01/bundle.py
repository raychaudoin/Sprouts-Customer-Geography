"""Deterministic APP-01 presentation and Evidence Context bundle construction."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from .errors import App01Error, require
from .inputs import (
    EXPECTED_COMPUTABLE_COUNT,
    EXPECTED_GEOMETRY_SHA256,
    EXPECTED_NONCOMPUTABLE_COUNT,
    EXPECTED_SUPPORT_TRUNCATION_COUNT,
    EXPECTED_TRACT_COUNT,
    AcceptedGeometry,
    LocalSettings,
    load_accepted_geometry,
    load_local_settings,
    resolve_data04,
    resolve_model13,
)


EXPECTED_METRICS = (
    "Customer Fit Percentile",
    "5-Mile Household Opportunity",
    "Modeled Target Mass Percentile",
    "Median Household Income",
    "Per Capita Income",
    "Civilian Labor Force Share",
    "Employment Rate",
    "Bachelor's Degree or Higher Share",
    "Owner-Occupied Housing Share",
    "Vacant Housing Unit Share",
    "Median Home Value",
    "Median Gross Rent",
    "Average Household Size",
    "No-Vehicle Household Share",
    "Drive-Alone Commuter Share",
    "Work-from-Home Commuter Share",
)
MODEL_COMPUTABLE = "MODEL_SCORE_COMPUTABLE"
SYNTHETIC_CANARY = "APP01_SYNTHETIC_EGRESS_CANARY_8D4F2A91"
SYNTHETIC_WARNING_CANARY = "APP01_SYNTHETIC_WARNING_CANARY_31C7E5B4"
SYNTHETIC_SELECTION_CANARY = "APP01_SYNTHETIC_SELECTION_CANARY_6A92D8C3"
SYNTHETIC_EVIDENCE_CANARY = "APP01_SYNTHETIC_EVIDENCE_CANARY_4B1E7C95"


INTERPRETATIONS = {
    "customer_fit_percentile": "Read as relative statewide public-data proxy context. It is not Sprouts' proprietary customer model, a site recommendation, or a sales forecast.",
    "household_opportunity_5_mile": "Read as household opportunity mass around the public tract anchor. It is not customer fit and does not imply site performance.",
    "modeled_target_mass_percentile": "Read as a relative accepted modeled output among computable tracts. It is not a site-level forecast, recommendation, or promise of sales.",
    "median_household_income": "Descriptive household-income context for the tract. Higher or lower values are not inherently favorable and this is not Average Household Income or Area Median Income.",
    "per_capita_income": "Descriptive income-per-person context for the tract. It is not household income or customer fit.",
    "civilian_labor_force_share": "Descriptive labor-force participation context for the accepted age-16-plus universe.",
    "employment_rate": "Descriptive employment within the civilian labor force. It is not an employment-to-population rate.",
    "bachelors_or_higher_share": "Descriptive educational-attainment context for people age 25 and over; it is not a desirability score.",
    "owner_occupancy_share": "Descriptive housing-tenure context. Higher or lower values are not inherently favorable.",
    "vacancy_share": "Descriptive housing-availability context. It does not by itself indicate market strength or weakness.",
    "median_home_value": "Descriptive owner-occupied home-value context; it is not a property appraisal or candidate-site valuation.",
    "median_gross_rent": "Descriptive monthly gross-rent context for cash-rent-paying renter households.",
    "average_household_size": "Descriptive occupied-household scale; it does not indicate income or customer fit.",
    "no_vehicle_household_share": "Descriptive household vehicle-access context; it is not a routing or traffic conclusion.",
    "drive_alone_commuter_share": "Descriptive commute-mode context for workers age 16 and over; it is not a traffic conclusion.",
    "work_from_home_commuter_share": "Descriptive work-from-home commute-mode context for workers age 16 and over.",
}


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8") + b"\n"


def _number(value: str, code: str) -> float | None:
    if value == "":
        return None
    try:
        parsed = float(value)
    except ValueError as exc:
        raise App01Error(code, "validated presentation input contains an unexpected numeric token") from exc
    require(math.isfinite(parsed), code, "validated presentation input contains a nonfinite value")
    return parsed


def _type7(values: Sequence[float], proportion: float) -> float:
    require(values, "APP01_DOMAIN_EMPTY", "a presentation metric has no valid statewide values")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * proportion
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + fraction * (ordered[upper] - ordered[lower])


def _domains(metrics: Sequence[Mapping[str, Any]], rows: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for index, metric in enumerate(metrics):
        valid = [float(row["values"][index]) for row in rows if row["values"][index] is not None]
        require(valid, "APP01_DOMAIN_EMPTY", "a presentation metric has no valid statewide values")
        if metric["scale_policy"] == "fixed_0_100":
            minimum, maximum = 0.0, 100.0
        else:
            minimum, maximum = _type7(valid, 0.02), _type7(valid, 0.98)
        require(math.isfinite(minimum) and math.isfinite(maximum) and minimum <= maximum, "APP01_DOMAIN_INVALID", "presentation domain is invalid")
        output[str(metric["metric_key"])] = {
            "minimum": minimum,
            "maximum": maximum,
            "policy": metric["scale_policy"],
            "valid_value_count": len(valid),
        }
    return output


def _load_metrics(repository_root: Path) -> tuple[dict[str, Any], ...]:
    path = repository_root / "config" / "arch01" / "arch01_metric_catalog.json"
    try:
        catalog = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise App01Error("APP01_METRIC_CATALOG_INVALID", "accepted presentation metric catalog is unreadable") from exc
    require(isinstance(catalog, Mapping) and catalog.get("artifact_id") == "ARCH01_MICHIGAN_PRESENTATION_METRIC_CATALOG_V1", "APP01_METRIC_CATALOG_INVALID", "accepted presentation metric catalog identity differs")
    source = catalog.get("metrics")
    require(isinstance(source, list) and len(source) == 16, "APP01_METRIC_CATALOG_INVALID", "accepted presentation metric count differs")
    require(tuple(metric.get("display_name") for metric in source) == EXPECTED_METRICS, "APP01_METRIC_CATALOG_INVALID", "accepted presentation metric order differs")
    require(tuple(metric.get("sort_order") for metric in source) == tuple(range(1, 17)), "APP01_METRIC_CATALOG_INVALID", "accepted presentation sort order differs")
    require(not any(metric.get("display_name") in {"Average Household Income", "Area Median Income"} for metric in source), "APP01_METRIC_CATALOG_INVALID", "accepted presentation catalog contains a prohibited income field")
    output: list[dict[str, Any]] = []
    for metric in source:
        enriched = dict(metric)
        enriched.pop("synthetic_range", None)
        key = str(metric["metric_key"])
        enriched["interpretation"] = INTERPRETATIONS[key]
        enriched["source_vintage"] = (
            "Accepted MODEL-13 Michigan presentation output"
            if metric["input_binding"]["logical_input"] == "model13_tract_output"
            else "U.S. Census Bureau ACS 2020–2024 5-Year Detailed Tables, 2024 vintage"
        )
        output.append(enriched)
    return tuple(output)


def _fraction(seed: str) -> float:
    value = int.from_bytes(sha256(seed.encode("utf-8")).digest()[:8], "big")
    return value / ((1 << 64) - 1)


def _synthetic_value(geoid: str, metric: Mapping[str, Any], index: int) -> float:
    catalog = {
        "customer_fit_percentile": (0.0, 100.0),
        "household_opportunity_5_mile": (12_000.0, 210_000.0),
        "modeled_target_mass_percentile": (0.0, 100.0),
        "median_household_income": (25_000.0, 160_000.0),
        "per_capita_income": (15_000.0, 80_000.0),
        "civilian_labor_force_share": (35.0, 80.0),
        "employment_rate": (75.0, 100.0),
        "bachelors_or_higher_share": (5.0, 75.0),
        "owner_occupancy_share": (20.0, 90.0),
        "vacancy_share": (1.0, 30.0),
        "median_home_value": (60_000.0, 600_000.0),
        "median_gross_rent": (500.0, 2_500.0),
        "average_household_size": (1.5, 4.0),
        "no_vehicle_household_share": (0.0, 25.0),
        "drive_alone_commuter_share": (30.0, 90.0),
        "work_from_home_commuter_share": (0.0, 35.0),
    }
    low, high = catalog[str(metric["metric_key"])]
    return low + _fraction(f"APP01:{geoid}:{index}") * (high - low)


def _ranked_subset(geoids: Sequence[str], label: str, count: int) -> set[str]:
    return set(sorted(geoids, key=lambda geoid: sha256(f"{label}:{geoid}".encode("utf-8")).digest())[:count])


def _synthetic_rows(geometry: AcceptedGeometry, metrics: Sequence[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    noncomputable = _ranked_subset(geometry.geoids, "noncomputable", EXPECTED_NONCOMPUTABLE_COUNT)
    truncated = _ranked_subset(geometry.geoids, "support-truncated", EXPECTED_SUPPORT_TRUNCATION_COUNT)
    model_warning_geoid = sorted(noncomputable)[0]
    unavailable_geoid = next(geoid for geoid in geometry.geoids if geoid not in noncomputable)
    valid_geoid = next(geoid for geoid in geometry.geoids if geoid not in noncomputable and geoid != unavailable_geoid)
    quality_context_geoid = next(geoid for geoid in geometry.geoids if geoid not in noncomputable and geoid not in {unavailable_geoid, valid_geoid})
    rows: list[dict[str, Any]] = []
    for geoid in geometry.geoids:
        values: list[float | None] = []
        statuses: list[str] = []
        details: list[str | None] = []
        moes: list[float | None] = []
        for index, metric in enumerate(metrics):
            value = _synthetic_value(geoid, metric, index)
            status = "valid"
            detail: str | None = None
            moe: float | None = None
            if index in {0, 2} and geoid in noncomputable:
                value = None
                status = "noncomputable"
                detail = SYNTHETIC_WARNING_CANARY if geoid == model_warning_geoid else "synthetic_model_input_unavailable"
            elif index >= 3:
                moe = max(0.1, abs(value) * (0.02 + _fraction(f"MOE:{geoid}:{index}") * 0.08))
                if geoid == unavailable_geoid and index == 3:
                    value = None
                    moe = None
                    status = "missing"
                    detail = "synthetic_source_value_unavailable"
                elif _fraction(f"STATUS:{geoid}:{index}") < 0.008:
                    value = None
                    moe = None
                    status = "inapplicable" if index in {11, 12} else "missing"
                    detail = "synthetic_inapplicable" if status == "inapplicable" else "synthetic_source_value_unavailable"
                if geoid == quality_context_geoid and index == 11:
                    moe = None
                    status = "inapplicable"
                    detail = "synthetic_moe_inapplicable_estimate_retained"
            values.append(value)
            statuses.append(status)
            details.append(detail)
            moes.append(moe)
        if geoid == valid_geoid:
            values[0] = 98.7654321
            values[1] = 987_654.321
            values[2] = 97.654321
        rows.append({
            "geoid": geoid,
            "values": values,
            "statuses": statuses,
            "status_details": details,
            "moes": moes,
            "support_truncation": geoid in truncated,
            "computability_status": "MODEL_SCORE_NONCOMPUTABLE" if geoid in noncomputable else MODEL_COMPUTABLE,
        })
    audit = {
        "single_valid_geoid": valid_geoid,
        "model_warning_geoid": model_warning_geoid,
        "data_unavailable_geoid": unavailable_geoid,
        "quality_context_geoid": quality_context_geoid,
        "multiple_geoids": [valid_geoid, unavailable_geoid],
        "selection_canary": SYNTHETIC_SELECTION_CANARY,
    }
    return rows, audit


def _synthetic_evidence() -> list[dict[str, Any]]:
    centers = (
        (42.7335, -84.5555),
        (43.0125, -83.6875),
        (42.3314, -83.0458),
        (42.9634, -85.6681),
        (44.3148, -85.6024),
        (46.5436, -87.3954),
    )
    rows: list[dict[str, Any]] = []
    for index, (latitude, longitude) in enumerate(centers):
        rows.append({
            "evidence_id": SYNTHETIC_EVIDENCE_CANARY if index == 0 else f"SYNTHETIC-EVIDENCE-{index + 1:02d}",
            "latitude": latitude,
            "longitude": longitude,
            "isolated_sales": 987_654.321 if index == 0 else 400_000 + index * 15_000,
            "frozen_prediction": 876_543.21 if index == 0 else 410_000 + index * 12_000,
            "successor_prediction": 765_432.1 if index == 0 else 420_000 + index * 10_000,
            "absolute_log_error": 0.123 + index * 0.01,
            "household_opportunity": 150_000 + index * 8_500,
            "customer_fit_proxy": 0.55 + index * 0.03,
            "modeled_target_mass": 82_500 + index * 4_000,
            "support_truncation": index == 5,
            "qa_status": "SYNTHETIC_VALIDATION_ONLY",
        })
    return rows


def _production_rows(
    metrics: Sequence[Mapping[str, Any]],
    model_rows: Sequence[Mapping[str, str]],
    data_rows: Sequence[Mapping[str, str]],
) -> list[dict[str, Any]]:
    data_by_geoid = {row["tract_geoid"]: row for row in data_rows}
    rows: list[dict[str, Any]] = []
    for model in model_rows:
        geoid = model["geoid"]
        public = data_by_geoid[geoid]
        values: list[float | None] = []
        statuses: list[str] = []
        details: list[str | None] = []
        moes: list[float | None] = []
        for metric in metrics:
            binding = metric["input_binding"]
            if binding["logical_input"] == "model13_tract_output":
                column = str(binding["column"])
                value = _number(model[column], "APP01_MODEL13_VALUE_INVALID")
                if metric["metric_key"] == "household_opportunity_5_mile":
                    valid = value is not None
                else:
                    valid = model["computability_status"] == MODEL_COMPUTABLE and value is not None
                values.append(value if valid else None)
                statuses.append("valid" if valid else "noncomputable")
                details.append(None if valid else (model["qa_missingness_status"] or "model_input_unavailable"))
                moes.append(None)
            else:
                measure_id = str(binding["measure_id"])
                status = public[f"{measure_id}_status"]
                estimate = _number(public[f"{measure_id}_estimate"], "APP01_DATA04_VALUE_INVALID")
                moe = _number(public[f"{measure_id}_moe"], "APP01_DATA04_VALUE_INVALID")
                values.append(estimate)
                statuses.append(status)
                details.append(public[f"{measure_id}_status_detail"] or None)
                moes.append(moe)
        rows.append({
            "geoid": geoid,
            "values": values,
            "statuses": statuses,
            "status_details": details,
            "moes": moes,
            "support_truncation": None if model["support_truncation_5mi"] == "" else model["support_truncation_5mi"] == "True",
            "computability_status": model["computability_status"],
        })
    return rows


def _production_evidence(seed_rows: Sequence[Mapping[str, str]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for row in seed_rows:
        output.append({
            "evidence_id": row["protected_physical_location_id"],
            "latitude": _number(row["latitude"], "APP01_MODEL13_SEED_INVALID"),
            "longitude": _number(row["longitude"], "APP01_MODEL13_SEED_INVALID"),
            "isolated_sales": _number(row["mean_isolated_sales"], "APP01_MODEL13_SEED_INVALID"),
            "frozen_prediction": _number(row["frozen_model12_prediction"], "APP01_MODEL13_SEED_INVALID"),
            "successor_prediction": _number(row["successor_oof_prediction"], "APP01_MODEL13_SEED_INVALID"),
            "absolute_log_error": _number(row["successor_oof_absolute_log_error"], "APP01_MODEL13_SEED_INVALID"),
            "household_opportunity": _number(row["household_opportunity"], "APP01_MODEL13_SEED_INVALID"),
            "customer_fit_proxy": _number(row["customer_fit_proxy"], "APP01_MODEL13_SEED_INVALID"),
            "modeled_target_mass": _number(row["modeled_target_mass"], "APP01_MODEL13_SEED_INVALID"),
            "support_truncation": row["support_truncation"] == "True",
            "qa_status": row["qa_status"],
        })
    return output


@dataclass(frozen=True)
class BundleSet:
    presentation_bytes: bytes
    evidence_bytes: bytes
    geometry_bytes: bytes
    health: Mapping[str, Any]


def build_bundle_set(
    repository_root: Path,
    *,
    synthetic: bool = False,
    settings_path: Path | None = None,
) -> BundleSet:
    """Build a deterministic in-memory runtime without writing protected artifacts."""
    root = repository_root.resolve()
    geometry = load_accepted_geometry(root)
    metrics = _load_metrics(root)
    if synthetic:
        rows, audit_states = _synthetic_rows(geometry, metrics)
        evidence_rows = _synthetic_evidence()
        model_preflight: Mapping[str, Any] = {
            "state": "SYNTHETIC_VALIDATION",
            "tract_count": EXPECTED_TRACT_COUNT,
            "computable_count": EXPECTED_COMPUTABLE_COUNT,
            "noncomputable_count": EXPECTED_NONCOMPUTABLE_COUNT,
            "support_truncation_count": EXPECTED_SUPPORT_TRUNCATION_COUNT,
            "seed_context_ready": True,
        }
        data_preflight: Mapping[str, Any] = {
            "state": "SYNTHETIC_VALIDATION",
            "tract_count": EXPECTED_TRACT_COUNT,
            "measure_count": 13,
        }
        data_mode = "synthetic_validation"
        classification = "synthetic_public"
        notice = "Synthetic validation data · public geometry · not for business decisions"
        canary = {
            "active": True,
            "tokens": [
                SYNTHETIC_CANARY,
                SYNTHETIC_WARNING_CANARY,
                SYNTHETIC_SELECTION_CANARY,
                SYNTHETIC_EVIDENCE_CANARY,
                "98.7654321",
                "987654.321",
            ],
            "external_transmission_permitted": False,
        }
    else:
        settings: LocalSettings = load_local_settings(root, settings_path)
        model = resolve_model13(root, geometry, settings.model13_candidates)
        data = resolve_data04(root, geometry, settings.data04_candidates)
        rows = _production_rows(metrics, model.tract_rows, data.rows)
        evidence_rows = _production_evidence(model.seed_rows)
        model_preflight = model.disclosure_safe_dict()
        data_preflight = data.disclosure_safe_dict()
        audit_states = None
        data_mode = "accepted_real"
        classification = "protected_local"
        notice = "Accepted local MODEL-13 and DATA-04 presentation inputs"
        canary = {"active": False, "tokens": [], "external_transmission_permitted": False}

    require(len(rows) == EXPECTED_TRACT_COUNT and tuple(row["geoid"] for row in rows) == geometry.geoids, "APP01_BUNDLE_RECONCILIATION_FAILED", "presentation rows and accepted geometry do not reconcile")
    domains = _domains(metrics, rows)
    availability = {
        str(metric["metric_key"]): {
            "available": sum(row["values"][index] is not None for row in rows),
            "unavailable": sum(row["values"][index] is None for row in rows),
        }
        for index, metric in enumerate(metrics)
    }
    presentation = {
        "$schema": "app01-presentation-bundle-v1",
        "artifact_id": "APP01_MICHIGAN_PRESENTATION_BUNDLE_V1",
        "version": "1.0.0",
        "data_mode": data_mode,
        "classification": classification,
        "notice": notice,
        "egress_canary": canary,
        "source_bindings": {
            "architecture": "ARCH01_LOCAL_FIRST_PRESENTATION_RUNTIME_POLICY_V1",
            "metric_catalog": "ARCH01_MICHIGAN_PRESENTATION_METRIC_CATALOG_V1",
            "model13_contract": "MODEL13_MICHIGAN_POWER_BI_OUTPUT_CONTRACT_V1",
            "data04_contract": "DATA04_MICHIGAN_PUBLIC_DATA_PARITY_SOURCE_CONTRACT_V1",
            "geometry": "PBI01_MICHIGAN_2024_TIGER_TRACT_PRESENTATION_GEOMETRY_V1",
            "geometry_sha256": EXPECTED_GEOMETRY_SHA256,
        },
        "tract_count": EXPECTED_TRACT_COUNT,
        "metric_count": len(metrics),
        "metrics": list(metrics),
        "domains": domains,
        "availability": availability,
        "qa": {
            "model13": model_preflight,
            "data04": data_preflight,
            "geometry": {"state": "READY", "tract_count": EXPECTED_TRACT_COUNT, "key_reconciliation": "passed"},
            "model_computable_count": EXPECTED_COMPUTABLE_COUNT,
            "model_noncomputable_count": EXPECTED_NONCOMPUTABLE_COUNT,
            "support_truncated_count": EXPECTED_SUPPORT_TRUNCATION_COUNT,
        },
        "audit_states": audit_states,
        "rows": rows,
    }
    evidence = {
        "$schema": "app01-evidence-context-bundle-v1",
        "artifact_id": "APP01_SPROUTS_EVIDENCE_CONTEXT_BUNDLE_V1",
        "version": "1.0.0",
        "data_mode": data_mode,
        "local_only": True,
        "external_transmission_permitted": False,
        "row_count": len(evidence_rows),
        "rows": evidence_rows,
    }
    presentation_bytes = _json_bytes(presentation)
    evidence_bytes = _json_bytes(evidence)
    health = {
        "state": "ready",
        "binding": "loopback",
        "data_mode": data_mode,
        "tract_count": EXPECTED_TRACT_COUNT,
        "metric_count": len(metrics),
        "model_computable_count": EXPECTED_COMPUTABLE_COUNT,
        "model_noncomputable_count": EXPECTED_NONCOMPUTABLE_COUNT,
        "support_truncated_count": EXPECTED_SUPPORT_TRUNCATION_COUNT,
        "seed_context_ready": True,
        "geometry_reconciled": True,
        "protected_values_served": not synthetic,
    }
    return BundleSet(
        presentation_bytes=presentation_bytes,
        evidence_bytes=evidence_bytes,
        geometry_bytes=geometry.canonical_bytes,
        health=health,
    )
