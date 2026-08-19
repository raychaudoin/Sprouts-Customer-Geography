"""Repository-safe PIPE-01 analytical contracts."""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from typing import Any

from sprouts_customer_geography.constants import (
    HOUSEHOLD_MOE_VARIABLE,
    HOUSEHOLD_VARIABLE,
    JACCARD_STRESS_THRESHOLD,
    MEMBERSHIP_SPEC_ID,
    PRIMARY_COMPLETENESS,
    RADII_M,
    RADIUS_5_M,
    SECONDARY_COMPLETENESS,
    SOURCE_CRS,
    TARGET_CRS,
)

from .canonical import content_digest, content_id
from .errors import require
from .spatial import (
    CoordinateTransformer,
    ordinary_membership,
    parse_internal_point,
    planar_distance_m,
    project_internal_point,
    validate_transformer,
)


FORBIDDEN_TARGET_KEYS = {
    "target",
    "target_value",
    "target_rank",
    "forecast",
    "forecast_value",
    "isolated_sales",
    "impacted_sales",
    "residual",
    "kendall_tau",
    "kendall_tau_b",
    "correlation",
}


def reject_target_inputs(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = str(key).strip().lower()
            require(normalized not in FORBIDDEN_TARGET_KEYS, "TARGET_INPUT_REJECTED", f"target-derived field is prohibited: {key}")
            reject_target_inputs(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            reject_target_inputs(child)


class PretargetPipeline:
    """Pure deterministic calculations; filesystem finalization lives in ``run``."""

    def __init__(self, accepted_transform_fingerprint: str, transformer: CoordinateTransformer):
        validate_transformer(transformer, accepted_transform_fingerprint)
        self.transformer = transformer
        self.accepted_transform_fingerprint = accepted_transform_fingerprint

    @staticmethod
    def build_inventory(market_id: str, geoids: Iterable[str], source_lineage: Mapping[str, Any], qa_expected_count: int | None = None) -> dict[str, Any]:
        require(bool(market_id), "MARKET_ID_MISSING", "market/configuration identity is required")
        values = [str(geoid) for geoid in geoids]
        require(all(value.isdigit() and len(value) == 11 for value in values), "GEOID_INVALID", "tract GEOIDs must be 11 digits")
        require(len(values) == len(set(values)), "DUPLICATE_GEOID", "tract inventory contains duplicate GEOIDs")
        ordered = sorted(values)
        digest = content_digest({"market_id": market_id, "ordered_geoids": ordered, "source_lineage": dict(source_lineage)})
        rows = [
            {
                "market_id": market_id,
                "tract_geoid": geoid,
                "ordinal_position": position,
                "inventory_digest": digest,
                "source_lineage": dict(source_lineage),
            }
            for position, geoid in enumerate(ordered, start=1)
        ]
        return {
            "artifact_id": content_id("tract_inventory", rows),
            "market_id": market_id,
            "inventory_digest": digest,
            "actual_count": len(rows),
            "qa_expected_count": qa_expected_count,
            "qa_count_matches": None if qa_expected_count is None else len(rows) == qa_expected_count,
            "readiness_basis": "ordered_inventory_digest_and_row_validation",
            "rows": rows,
        }

    def build_internal_point_evidence(self, inventory: Mapping[str, Any], tiger_rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
        market_id = inventory["market_id"]
        inventory_geoids = [row["tract_geoid"] for row in inventory["rows"]]
        by_geoid: dict[str, Mapping[str, Any]] = {}
        for row in tiger_rows:
            geoid = str(row.get("tract_geoid", ""))
            require(geoid not in by_geoid, "DUPLICATE_TIGER_GEOID", f"duplicate internal-point source row: {geoid}")
            by_geoid[geoid] = row
        require(set(by_geoid) == set(inventory_geoids), "TRACT_INVENTORY_SOURCE_MISMATCH", "internal-point rows do not exactly cover canonical inventory")
        evidence_rows = []
        for geoid in inventory_geoids:
            source = by_geoid[geoid]
            require(source.get("market_id") == market_id, "STRUCTURAL_MARKET_MISMATCH", f"market mismatch for tract {geoid}")
            point = parse_internal_point(source.get("INTPTLAT"), source.get("INTPTLON"))
            projected = project_internal_point(point, self.transformer)
            evidence_rows.append(
                {
                    "market_id": market_id,
                    "tract_geoid": geoid,
                    "raw_INTPTLAT": point.raw_latitude,
                    "raw_INTPTLON": point.raw_longitude,
                    "parsed_latitude": point.latitude,
                    "parsed_longitude": point.longitude,
                    "coordinate_state": point.coordinate_state,
                    "source_crs": SOURCE_CRS,
                    "target_crs": TARGET_CRS,
                    "transformation_state": "transformed" if projected is not None else "noncomputable",
                    "transformation_fingerprint": self.accepted_transform_fingerprint,
                    "projected_x_m": None if projected is None else projected[0],
                    "projected_y_m": None if projected is None else projected[1],
                    "source_lineage": source.get("source_lineage"),
                }
            )
        return {"artifact_id": content_id("tract_internal_point_evidence", evidence_rows), "market_id": market_id, "rows": evidence_rows}

    def build_membership(self, inventory: Mapping[str, Any], evidence: Mapping[str, Any], context: Mapping[str, Any]) -> dict[str, Any]:
        reject_target_inputs(context)
        market_id = inventory["market_id"]
        require(context.get("market_id") == market_id == evidence.get("market_id"), "STRUCTURAL_MARKET_MISMATCH", "context, inventory and evidence market IDs must agree")
        require(context.get("context_spec_id"), "CONTEXT_SPEC_ID_MISSING", "GEO-02 context_spec_id is required")
        require(context.get("context_instance_id"), "CONTEXT_INSTANCE_ID_MISSING", "GEO-02 context_instance_id is required")
        anchor_geoid = context.get("anchor_tract_geoid")
        require(isinstance(anchor_geoid, str) and len(anchor_geoid) == 11, "ANCHOR_IDENTITY_MISSING_OR_AMBIGUOUS", "one valid GEO-02 anchor tract identity is required")
        inventory_geoids = [row["tract_geoid"] for row in inventory["rows"]]
        require(anchor_geoid in inventory_geoids, "ANCHOR_TRACT_ABSENT", "anchor tract is absent from canonical inventory")
        anchor_point = parse_internal_point(context.get("anchor_latitude"), context.get("anchor_longitude"))
        require(anchor_point.coordinate_state == "valid", "ANCHOR_COORDINATE_INVALID", "valid target-blind seed coordinate is required")
        projected_anchor = project_internal_point(anchor_point, self.transformer)
        require(projected_anchor is not None, "ANCHOR_TRANSFORM_FAILED", "anchor coordinate could not be transformed")
        by_geoid = {row["tract_geoid"]: row for row in evidence["rows"]}
        require(set(by_geoid) == set(inventory_geoids), "TRACT_INVENTORY_EVIDENCE_MISMATCH", "evidence does not exactly cover inventory")

        rows: list[dict[str, Any]] = []
        for radius in RADII_M:
            for geoid in inventory_geoids:
                tract = by_geoid[geoid]
                require(tract.get("source_crs") == SOURCE_CRS, "EVIDENCE_SOURCE_CRS_MISMATCH", f"source CRS mismatch for tract {geoid}")
                require(tract.get("target_crs") == TARGET_CRS, "EVIDENCE_TARGET_CRS_MISMATCH", f"target CRS mismatch for tract {geoid}")
                require(tract.get("transformation_fingerprint") == self.accepted_transform_fingerprint, "EVIDENCE_TRANSFORM_FINGERPRINT_MISMATCH", f"transform fingerprint mismatch for tract {geoid}")
                projected_tract = None
                if tract["transformation_state"] == "transformed":
                    projected_values = (tract.get("projected_x_m"), tract.get("projected_y_m"))
                    if all(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) for value in projected_values):
                        projected_tract = projected_values
                distance = None if projected_tract is None else planar_distance_m(projected_anchor, projected_tract)
                ordinary = None if distance is None else ordinary_membership(distance, radius)
                is_anchor = geoid == anchor_geoid
                forced = bool(is_anchor and ordinary is not True)
                final = True if forced else ordinary
                if forced:
                    reason = "valid_anchor_forced_inclusion_internal_point_gap" if distance is None else "valid_anchor_forced_inclusion_outside_radius"
                elif ordinary is True:
                    reason = "ordinary_radius_membership"
                elif ordinary is False:
                    reason = "ordinary_outside_radius"
                else:
                    reason = "nonanchor_membership_noncomputable"
                rows.append(
                    {
                        "membership_spec_id": MEMBERSHIP_SPEC_ID,
                        "context_spec_id": context["context_spec_id"],
                        "context_instance_id": context["context_instance_id"],
                        "market_id": market_id,
                        "radius_m": radius,
                        "tract_geoid": geoid,
                        "distance_m": distance,
                        "distance_computable": distance is not None,
                        "ordinary_membership": ordinary,
                        "forced_anchor_inclusion": forced,
                        "final_membership": final,
                        "reason_code": reason,
                        "lineage": {"inventory_digest": inventory["inventory_digest"], "internal_point_artifact_id": evidence["artifact_id"]},
                    }
                )
        keys = [(row["membership_spec_id"], row["context_instance_id"], row["radius_m"], row["tract_geoid"]) for row in rows]
        require(len(keys) == len(set(keys)), "MEMBERSHIP_GRAIN_DUPLICATE", "duplicate membership contribution key")
        self.validate_nesting(rows)
        return {"artifact_id": content_id("context_membership", rows), "rows": rows}

    @staticmethod
    def validate_nesting(rows: Iterable[Mapping[str, Any]]) -> None:
        by_tract: dict[tuple[str, str], dict[float, bool | None]] = {}
        for row in rows:
            key = (str(row["context_instance_id"]), str(row["tract_geoid"]))
            by_tract.setdefault(key, {})[float(row["radius_m"])] = row["final_membership"]
        for key, memberships in by_tract.items():
            require(set(memberships) == set(RADII_M), "MEMBERSHIP_RADIUS_SET_INVALID", f"radius set invalid for {key}")
            small, medium, large = (memberships[radius] for radius in RADII_M)
            if small is True:
                require(medium is True, "MEMBERSHIP_NESTING_VIOLATION", f"3-mile member absent at 5 miles: {key}")
            if medium is True:
                require(large is True, "MEMBERSHIP_NESTING_VIOLATION", f"5-mile member absent at 7 miles: {key}")

    @staticmethod
    def validate_spatial_evidence(context_spatial_evidence: Mapping[str, Any]) -> dict[str, Any]:
        forbidden = {key for key in context_spatial_evidence if "membership_jaccard" in key.lower()}
        require(not forbidden, "COMPETING_MEMBERSHIP_JACCARD_REJECTED", "GEO-02 geometric Jaccard must not be replaced")
        required = {"context_spec_id", "context_instance_id", "market_edge_state", "geometric_completeness", "geometric_jaccard", "spatial_components", "geo02_lineage"}
        missing = sorted(required - context_spatial_evidence.keys())
        require(not missing, "GEO02_SPATIAL_EVIDENCE_INCOMPLETE", f"missing fields: {missing}")
        completeness = context_spatial_evidence["geometric_completeness"]
        jaccard = context_spatial_evidence["geometric_jaccard"]
        require(isinstance(completeness, (int, float)) and not isinstance(completeness, bool) and 0 <= completeness <= 1, "COMPLETENESS_INVALID", "geometric completeness must be within [0,1]")
        require(isinstance(jaccard, (int, float)) and not isinstance(jaccard, bool) and 0 <= jaccard <= 1, "JACCARD_INVALID", "geometric Jaccard must be within [0,1]")
        return {**dict(context_spatial_evidence), "jaccard_dependence_stress": jaccard >= JACCARD_STRESS_THRESHOLD}

    @staticmethod
    def build_acs_evidence(inventory: Mapping[str, Any], acs_rows: Iterable[Mapping[str, Any]], source_lineage: Mapping[str, Any]) -> dict[str, Any]:
        market_id = inventory["market_id"]
        inventory_geoids = [row["tract_geoid"] for row in inventory["rows"]]
        by_geoid: dict[str, Mapping[str, Any]] = {}
        for row in acs_rows:
            geoid = str(row.get("tract_geoid", ""))
            require(geoid not in by_geoid, "DUPLICATE_ACS_GEOID", f"duplicate ACS source row: {geoid}")
            by_geoid[geoid] = row
        require(set(by_geoid) == set(inventory_geoids), "ACS_INVENTORY_MISMATCH", "ACS evidence does not exactly cover canonical inventory")
        output = []
        for geoid in inventory_geoids:
            source = by_geoid[geoid]
            estimate = source.get("estimate")
            moe = source.get("moe")
            status = str(source.get("status", "missing"))
            require(status in {"valid", "missing", "suppressed", "inapplicable", "invalid"}, "ACS_STATUS_INVALID", f"unrecognized ACS status for tract {geoid}")
            estimate_valid = status == "valid" and isinstance(estimate, int) and not isinstance(estimate, bool) and estimate >= 0
            moe_valid = status == "valid" and isinstance(moe, int) and not isinstance(moe, bool) and moe >= 0
            output.append(
                {
                    "market_id": market_id,
                    "tract_geoid": geoid,
                    "estimate_variable": HOUSEHOLD_VARIABLE,
                    "moe_variable": HOUSEHOLD_MOE_VARIABLE,
                    "total_household_estimate": estimate,
                    "total_household_moe": moe,
                    "annotation": source.get("annotation"),
                    "status": status,
                    "estimate_valid": estimate_valid,
                    "moe_valid": moe_valid,
                    "evidence_valid": estimate_valid and moe_valid,
                    "source_lineage": dict(source_lineage),
                }
            )
        return {"artifact_id": content_id("acs_b11001_evidence", output), "market_id": market_id, "rows": output}

    @staticmethod
    def aggregate_households(membership: Mapping[str, Any], acs_evidence: Mapping[str, Any]) -> dict[str, Any]:
        acs = {row["tract_geoid"]: row for row in acs_evidence["rows"]}
        output = []
        by_radius: dict[float, list[Mapping[str, Any]]] = {radius: [] for radius in RADII_M}
        for row in membership["rows"]:
            by_radius[float(row["radius_m"])].append(row)
        for radius, rows in by_radius.items():
            noncomputable_membership = [row["tract_geoid"] for row in rows if row["final_membership"] is None]
            members = [row["tract_geoid"] for row in rows if row["final_membership"] is True]
            invalid_acs = [geoid for geoid in members if geoid not in acs or not acs[geoid]["evidence_valid"]]
            if noncomputable_membership:
                state, total, reason = "noncomputable", None, "NONCOMPUTABLE_TRACT_MEMBERSHIP"
            elif invalid_acs:
                state, total, reason = "noncomputable", None, "INVALID_MEMBER_ACS_EVIDENCE"
            else:
                state = "complete"
                total = sum(acs[geoid]["total_household_estimate"] for geoid in members)
                reason = "WHOLE_TRACT_FINAL_MEMBERSHIP_SUM"
            context_instance_ids = {row["context_instance_id"] for row in rows}
            require(len(context_instance_ids) == 1, "CONTEXT_LINEAGE_MIXED", "aggregation cannot mix context instances")
            output.append(
                {
                    "context_instance_id": next(iter(context_instance_ids)),
                    "radius_m": radius,
                    "aggregation_method": "whole_tract_final_membership_once",
                    "household_opportunity": total,
                    "calculation_state": state,
                    "reason_code": reason,
                    "member_count": len(members),
                    "membership_artifact_id": membership["artifact_id"],
                    "acs_artifact_id": acs_evidence["artifact_id"],
                }
            )
        return {"artifact_id": content_id("household_opportunity", output), "rows": output}

    @staticmethod
    def build_baseline_prediction(households: Mapping[str, Any], model_spec: Mapping[str, Any]) -> dict[str, Any]:
        reject_target_inputs(model_spec)
        required = {"model_spec_id", "model_spec_version", "preregistration_id", "preregistration_version", "prediction_semantics", "accepted"}
        missing = sorted(required - model_spec.keys())
        require(not missing, "MODEL_SPEC_INCOMPLETE", f"missing fields: {missing}")
        require(model_spec["accepted"] is True, "MODEL_SPEC_NOT_ACCEPTED", "MODEL-05 artifact must be accepted")
        require(model_spec["prediction_semantics"] == "raw_5_mile_whole_tract_household_opportunity", "MODEL_SEMANTICS_UNAUTHORIZED", "only the accepted raw 5-mile household-opportunity candidate is implemented")
        require(not model_spec.get("numerical_parameters"), "UNAUTHORIZED_MODEL_PARAMETERS", "coefficients/scaling/transforms are not allowed for the raw baseline")
        candidates = [row for row in households["rows"] if row["radius_m"] == RADIUS_5_M]
        require(len(candidates) == 1, "PRIMARY_CONTEXT_MISSING", "exactly one 5-mile household artifact is required")
        candidate = candidates[0]
        require(candidate["calculation_state"] == "complete", "BASELINE_NONCOMPUTABLE", "5-mile household opportunity is not complete")
        artifact = {
            "context_instance_id": candidate["context_instance_id"],
            "radius_m": RADIUS_5_M,
            "role": "primary",
            "prediction_candidate": candidate["household_opportunity"],
            "prediction_semantics": model_spec["prediction_semantics"],
            "model_spec_id": model_spec["model_spec_id"],
            "model_spec_version": model_spec["model_spec_version"],
            "preregistration_id": model_spec["preregistration_id"],
            "preregistration_version": model_spec["preregistration_version"],
            "household_artifact_id": households["artifact_id"],
        }
        return {**artifact, "artifact_id": content_id("baseline_prediction", artifact)}

    @staticmethod
    def build_eligibility(spatial: Mapping[str, Any], household: Mapping[str, Any], quarantined: bool) -> dict[str, Any]:
        completeness = spatial["geometric_completeness"]
        primary_household = next(row for row in household["rows"] if row["radius_m"] == RADIUS_5_M)
        reasons: list[str] = []
        if quarantined:
            status = "quarantined"
            reasons.append("MODEL04_QUARANTINE")
        elif primary_household["calculation_state"] != "complete":
            status = "noncomputable"
            reasons.append(primary_household["reason_code"])
        elif completeness >= PRIMARY_COMPLETENESS:
            status = "primary_statistic_eligible"
        elif completeness >= SECONDARY_COMPLETENESS:
            status = "secondary_truncated_stratum"
            reasons.append("GEOMETRIC_COMPLETENESS_0_75_TO_LT_0_90")
        else:
            status = "qa_only"
            reasons.append("GEOMETRIC_COMPLETENESS_LT_0_75")
        if spatial["jaccard_dependence_stress"]:
            reasons.append("GEOMETRIC_JACCARD_GTE_0_25")
        artifact = {
            "context_instance_id": spatial["context_instance_id"],
            "eligibility_status": status,
            "primary_statistic_eligible": status == "primary_statistic_eligible",
            "secondary_truncated_stratum": status == "secondary_truncated_stratum",
            "qa_only": status == "qa_only",
            "quarantined": quarantined,
            "noncomputable": status == "noncomputable",
            "reason_codes": reasons,
        }
        return {**artifact, "artifact_id": content_id("eligibility_readiness", artifact)}
