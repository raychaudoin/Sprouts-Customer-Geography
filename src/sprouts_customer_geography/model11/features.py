"""Target-blind MODEL-11 feature construction and immutable Phase 1 freeze."""

from __future__ import annotations

import copy
import csv
import json
import math
import os
import re
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from sprouts_customer_geography.model09.features import (
    RADII_M,
    TractEvidence,
    _anchor_tract,
    build_public_features,
    load_public_tract_evidence,
    verify_model10_package,
)
from sprouts_customer_geography.pipe01.canonical import content_digest, file_sha256, write_json_exclusive
from sprouts_customer_geography.pipe01.errors import require
from sprouts_customer_geography.pipe01.production import Geo03ProductionTransformer
from sprouts_customer_geography.pipe01.spatial import parse_internal_point, project_internal_point
from sprouts_customer_geography.pipe02.resolver import _is_within

from .resolver import ProtectedHandleResolver


CONTRACT_ID = "MODEL11_WISCONSIN_MULTIVARIATE_MODEL_CONTRACT_V1"
FREEZE_PACKAGE_ID = "MODEL11_TARGET_BLIND_FEATURE_FREEZE_PACKAGE_V1"
FREEZE_SCHEMA = "model11-target-blind-feature-freeze-package-v1"
DATA03_CONTRACT_ID = "DATA03_WISCONSIN_MULTIVARIATE_ACS_FEATURE_SOURCE_CONTRACT_V1"
DATA03_REPORT_ID = "DATA03_WISCONSIN_MULTIVARIATE_ACS_MATERIALIZATION_REPORT_V1"
ACCEPTED_LINEAGE = (
    "dec2bd9af1aff15b7d7751211594dd056bc0e434",
    "87f83ac2bf02609cac97c6beb322e768f8fae62b",
    "54779055cbfe317b5e80c92d4b672c6e9be59a97",
    "ed5796e737c1c39671a081f78644577de00a17b2",
    "9709ee5a9541a7fd52c80af063c1f6461967a4e9",
    "f49e7d8e0129febd883a7335d56ccc74523d43a7",
    "f199624d16eb42e3e6c6b4d8eb73b8dcd3109dc8",
    "4f4dbf8fdf1f5de9633baa9c088bfece2f44b9e2",
    "c9f97d2a3314a64db583ec9b0ea4f53aeb0b5c1b",
    "5b96203ac7849fdd48601dc0129d1bbbe1b91d0e",
    "195e1f9e9599e4812417954b57356327b80c5051",
    "0bc3a6c159d8672254f552f93d18265e539eb10e",
)


def _load_object(path: Path, code: str) -> dict[str, Any]:
    require(path.is_file(), code, "required JSON authority is absent")
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), code, "required JSON authority must be an object")
    return value


def verify_repository_authority(repository_root: Path, *, require_git_lineage: bool = True) -> dict[str, Any]:
    contract = _load_object(repository_root / "config/model/model11_wisconsin_multivariate_model_contract.json", "MODEL11_CONTRACT_MISSING")
    data03 = _load_object(repository_root / "config/data/data03_wisconsin_multivariate_acs_feature_source_contract.json", "DATA03_CONTRACT_MISSING")
    model09 = _load_object(repository_root / "config/model/model09_wisconsin_experimental_model_contract.json", "MODEL09_CONTRACT_MISSING")
    model10 = _load_object(repository_root / "config/model/model10_wisconsin_cohort_identity_lineage_contract.json", "MODEL10_CONTRACT_MISSING")
    pipe04 = _load_object(repository_root / "config/pipe04/model10_wisconsin_development_binding_contract.json", "PIPE04_CONTRACT_MISSING")
    require(contract.get("artifact_id") == CONTRACT_ID and contract.get("version") == "1.0.0", "MODEL11_CONTRACT_MISMATCH", "MODEL-11 contract identity/version differs")
    require(data03.get("artifact_id") == DATA03_CONTRACT_ID and data03.get("content_sha256") == contract["accepted_authority"]["data03_content_sha256"], "DATA03_CONTRACT_MISMATCH", "accepted DATA-03 contract differs")
    require(model09.get("artifact_id") == contract["accepted_authority"]["model09_contract_id"], "MODEL09_CONTRACT_MISMATCH", "accepted MODEL-09 contract differs")
    require(model10.get("artifact_id") == contract["accepted_authority"]["model10_contract_id"], "MODEL10_CONTRACT_MISMATCH", "accepted MODEL-10 contract differs")
    require(pipe04.get("artifact_id") == contract["accepted_authority"]["pipe04_contract_id"], "PIPE04_CONTRACT_MISMATCH", "accepted PIPE-04 contract differs")
    require([item.get("measure_id") for item in contract.get("candidate_measures", [])] == data03.get("output_contract", {}).get("measure_order"), "DATA03_CANDIDATE_MENU_MISMATCH", "MODEL-11 menu differs from exact DATA-03 order")
    require(len(contract.get("candidate_measures", [])) == 13 and len(contract.get("candidates", [])) == 3, "MODEL11_BOUNDED_CONTRACT_MISMATCH", "MODEL-11 menu or candidate bound differs")
    if require_git_lineage:
        for commit in ACCEPTED_LINEAGE:
            present = subprocess.run(["git", "cat-file", "-e", commit + "^{commit}"], cwd=repository_root, capture_output=True, text=True)
            require(present.returncode == 0, "ACCEPTED_GIT_LINEAGE_MISSING", "accepted predecessor commit lineage is absent")
        ancestor = subprocess.run(["git", "merge-base", "--is-ancestor", "f49e7d8e0129febd883a7335d56ccc74523d43a7", "HEAD"], cwd=repository_root, capture_output=True, text=True)
        require(ancestor.returncode == 0, "ACCEPTED_GIT_LINEAGE_MISSING", "authorized canonical main is not an ancestor of execution HEAD")
    return contract


def _target_blind_cohort(model10: Mapping[str, Any], contract: Mapping[str, Any]) -> list[dict[str, Any]]:
    records = model10.get("records")
    require(isinstance(records, list), "MODEL10_COHORT_UNRESOLVED", "MODEL-10 records are absent")
    quarantined = [row for row in records if row.get("quarantined") is True]
    eligible = [row for row in records if row.get("model09_development_eligible") is True and row.get("quarantined") is False]
    expected = contract["cohort"]
    require(len(eligible) == expected["eligible_observation_count"] and len(quarantined) == expected["quarantined_observation_count"], "MODEL10_COHORT_COUNT_MISMATCH", "MODEL-10 eligible or quarantine count differs")
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    anchors: dict[str, tuple[float, float]] = {}
    for source in eligible:
        observation_id = source.get("source_observation_id")
        physical_id = source.get("successor_physical_location_id")
        anchor = source.get("successor_canonical_anchor")
        coordinate = anchor.get("observed_coordinate") if isinstance(anchor, Mapping) else None
        require(isinstance(observation_id, str) and observation_id not in seen and isinstance(physical_id, str) and isinstance(coordinate, Mapping), "MODEL10_IDENTITY_INVALID", "MODEL-10 identity or anchor is invalid")
        latitude = coordinate.get("latitude")
        longitude = coordinate.get("longitude")
        require(all(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) for value in (latitude, longitude)), "MODEL10_CANONICAL_ANCHOR_INVALID", "MODEL-10 canonical anchor is invalid")
        pair = (float(latitude), float(longitude))
        require(physical_id not in anchors or anchors[physical_id] == pair, "REPEATED_LOCATION_ANCHOR_MISMATCH", "one MODEL-10 physical location has inconsistent anchors")
        anchors[physical_id] = pair
        output.append({
            "source_observation_id": observation_id,
            "successor_physical_location_id": physical_id,
            "market": source.get("market"),
            "forecast_vintage": source.get("forecast_vintage"),
            "canonical_latitude": pair[0],
            "canonical_longitude": pair[1],
        })
        seen.add(observation_id)
    require(len(anchors) == expected["physical_location_count"] and all(row["market"] is not None and row["forecast_vintage"] in (2024, 2025, 2026) for row in output), "MODEL10_COHORT_COUNT_MISMATCH", "MODEL-10 physical-location or lineage count differs")
    return sorted(output, key=lambda row: row["source_observation_id"])


def load_data03_components(source: Path, report_path: Path, ready_path: Path, contract: Mapping[str, Any]) -> dict[str, dict[str, dict[str, Any]]]:
    report = _load_object(report_path, "DATA03_REPORT_UNRESOLVED")
    ready = _load_object(ready_path, "DATA03_READY_UNRESOLVED")
    normalized = report.get("normalized_output", {})
    require(report.get("report_id") == DATA03_REPORT_ID and report.get("state") == "VERIFIED" and report.get("contract_id") == DATA03_CONTRACT_ID and report.get("contract_content_sha256") == contract["accepted_authority"]["data03_content_sha256"], "DATA03_REPORT_MISMATCH", "DATA-03 verification report differs")
    require(report.get("source_vintage") == "2024" and report.get("tract_count") == 1542 and source.name == normalized.get("filename") and file_sha256(source) == normalized.get("byte_sha256"), "DATA03_SOURCE_IDENTITY_MISMATCH", "DATA-03 normalized source identity differs")
    require(ready.get("state") == "READY" and ready.get("normalized_output_sha256") == normalized.get("byte_sha256") and ready.get("report_sha256") == file_sha256(report_path), "DATA03_READY_MISMATCH", "DATA-03 READY marker differs")
    expected_components = {component for item in contract["candidate_measures"] for component in item.get("numerators", [])}
    expected_components.update(item.get("denominator") for item in contract["candidate_measures"] if item.get("denominator"))
    expected_components.update({"median_household_income", "per_capita_income", "median_home_value", "median_gross_rent", "average_household_size", "occupied_housing_units_total", "owner_occupied_housing_units"})
    by_tract: dict[str, dict[str, dict[str, Any]]] = {}
    row_count = 0
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        require(reader.fieldnames == normalized.get("columns"), "DATA03_SOURCE_SCHEMA_MISMATCH", "DATA-03 normalized columns differ")
        for row in reader:
            row_count += 1
            component = str(row["component_id"])
            if component not in expected_components:
                continue
            geoid = str(row["tract_geoid"])
            values = by_tract.setdefault(geoid, {})
            require(component not in values, "DATA03_COMPONENT_DUPLICATE", "DATA-03 tract component is duplicate")
            try:
                estimate = float(row["estimate"]) if row["estimate"] != "" else None
                moe = float(row["moe"]) if row["moe"] != "" else None
            except ValueError:
                estimate = moe = None
            values[component] = {"estimate": estimate, "moe": moe, "status": row["status"]}
    require(row_count == normalized.get("row_count") and len(by_tract) == report.get("tract_count"), "DATA03_SOURCE_COVERAGE_MISMATCH", "DATA-03 normalized coverage differs")
    require(all(expected_components <= set(values) for values in by_tract.values()), "DATA03_COMPONENT_COVERAGE_MISMATCH", "DATA-03 required component coverage differs")
    return by_tract


def _valid(component: Mapping[str, Any]) -> bool:
    return component.get("status") == "valid" and all(isinstance(component.get(key), (int, float)) and math.isfinite(float(component[key])) for key in ("estimate", "moe"))


def _sum_components(tract_geoids: list[str], components: Mapping[str, Mapping[str, Mapping[str, Any]]], names: list[str]) -> tuple[float, float] | None:
    selected = [components[geoid][name] for geoid in tract_geoids for name in names]
    if not all(_valid(item) for item in selected):
        return None
    return sum(float(item["estimate"]) for item in selected), math.sqrt(sum(float(item["moe"]) ** 2 for item in selected))


def _aggregate_measure(spec: Mapping[str, Any], tract_geoids: list[str], components: Mapping[str, Mapping[str, Mapping[str, Any]]], household_weights: Mapping[str, float]) -> dict[str, Any]:
    measure = str(spec["measure_id"])
    if spec["kind"] == "share":
        numerator = _sum_components(tract_geoids, components, list(spec["numerators"]))
        denominator = _sum_components(tract_geoids, components, [str(spec["denominator"])])
        if numerator is None or denominator is None or denominator[0] <= 0 or numerator[0] < 0 or numerator[0] > denominator[0]:
            return {"status": "noncomputable", "value": None, "moe": None}
        proportion = numerator[0] / denominator[0]
        radicand = numerator[1] ** 2 - proportion**2 * denominator[1] ** 2
        if radicand < 0:
            radicand = numerator[1] ** 2 + proportion**2 * denominator[1] ** 2
        return {"status": "valid", "value": proportion, "moe": math.sqrt(radicand) / denominator[0]}
    direct = measure
    weighted: list[tuple[float, float, float]] = []
    for geoid in tract_geoids:
        component = components[geoid][direct]
        if not _valid(component):
            return {"status": "noncomputable", "value": None, "moe": None}
        if measure in ("median_household_income", "per_capita_income"):
            weight = float(household_weights[geoid])
        elif measure == "median_home_value":
            weight_component = components[geoid]["owner_occupied_housing_units"]
            if not _valid(weight_component):
                return {"status": "noncomputable", "value": None, "moe": None}
            weight = float(weight_component["estimate"])
        elif measure == "median_gross_rent":
            occupied = components[geoid]["occupied_housing_units_total"]
            owner = components[geoid]["owner_occupied_housing_units"]
            if not (_valid(occupied) and _valid(owner)):
                return {"status": "noncomputable", "value": None, "moe": None}
            weight = float(occupied["estimate"]) - float(owner["estimate"])
        else:
            occupied = components[geoid]["occupied_housing_units_total"]
            if not _valid(occupied):
                return {"status": "noncomputable", "value": None, "moe": None}
            weight = float(occupied["estimate"])
        if weight < 0:
            return {"status": "noncomputable", "value": None, "moe": None}
        weighted.append((float(component["estimate"]), float(component["moe"]), weight))
    total_weight = sum(item[2] for item in weighted)
    if total_weight <= 0:
        return {"status": "noncomputable", "value": None, "moe": None}
    value = sum(value * weight for value, _, weight in weighted) / total_weight
    moe = math.sqrt(sum((weight * item_moe) ** 2 for _, item_moe, weight in weighted)) / total_weight
    return {"status": "valid", "value": value, "moe": moe}


def _pearson(left: list[float], right: list[float]) -> float:
    left_mean = sum(left) / len(left)
    right_mean = sum(right) / len(right)
    numerator = sum((x - left_mean) * (y - right_mean) for x, y in zip(left, right))
    denominator = math.sqrt(sum((x - left_mean) ** 2 for x in left) * sum((y - right_mean) ** 2 for y in right))
    return 0.0 if denominator <= 1e-15 else numerator / denominator


def build_multivariate_features(cohort: list[Mapping[str, Any]], tracts: list[TractEvidence], components: Mapping[str, Mapping[str, Mapping[str, Any]]], geo03: Mapping[str, Any], contract: Mapping[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    baseline = build_public_features(cohort, tracts, geo03)
    transformer = Geo03ProductionTransformer(geo03)
    by_geoid = {tract.geoid: tract for tract in tracts}
    require(set(by_geoid) == set(components), "DATA03_TIGER_COVERAGE_MISMATCH", "DATA-03 and accepted TIGER tract coverage differ")
    by_group: dict[str, dict[str, Any]] = {}
    for row in baseline:
        group = str(row["successor_physical_location_id"])
        if group in by_group:
            continue
        latitude = float(row["canonical_latitude"])
        longitude = float(row["canonical_longitude"])
        projected = project_internal_point(parse_internal_point(latitude, longitude), transformer)
        require(projected is not None, "ANCHOR_TRANSFORM_FAILED", "MODEL-10 canonical anchor cannot be transformed")
        anchor = _anchor_tract(tracts, longitude, latitude)
        selected = [tract for tract in tracts if math.hypot(tract.internal_x_m - projected[0], tract.internal_y_m - projected[1]) <= float(contract["phase1_feature_freeze"]["primary_context_radius_m"])]
        if anchor not in selected:
            selected.append(anchor)
        selected = sorted(selected, key=lambda tract: tract.geoid)
        household_weights = {tract.geoid: float(tract.households) for tract in selected}
        profiles = {str(spec["measure_id"]): _aggregate_measure(spec, [tract.geoid for tract in selected], components, household_weights) for spec in contract["candidate_measures"]}
        transformed: dict[str, float | None] = {}
        for spec in contract["candidate_measures"]:
            measure = str(spec["measure_id"])
            value = profiles[measure]["value"]
            transformed[measure] = None if value is None else math.log1p(value) if spec["transform"] == "log1p" else float(value)
        by_group[group] = {"profiles": profiles, "transformed": transformed, "member_tract_count_5mi": len(selected)}
    measure_ids = [str(spec["measure_id"]) for spec in contract["candidate_measures"]]
    complete = [measure for measure in measure_ids if all(by_group[group]["transformed"][measure] is not None for group in by_group)]
    exclusions: dict[str, str] = {measure: "incomplete_member_tract_evidence" for measure in measure_ids if measure not in complete}
    unique_groups = sorted(by_group)
    variable: list[str] = []
    for measure in complete:
        values = [float(by_group[group]["transformed"][measure]) for group in unique_groups]
        if max(values) - min(values) <= 1e-12:
            exclusions[measure] = "constant_across_physical_locations"
        else:
            variable.append(measure)
    priority = [str(value) for value in contract["phase1_feature_freeze"]["redundancy"]["priority_order"]]
    threshold = float(contract["phase1_feature_freeze"]["redundancy"]["threshold"])
    kept: list[str] = []
    correlations: list[dict[str, Any]] = []
    for measure in priority:
        if measure not in variable:
            continue
        rejected_by: str | None = None
        for prior in kept:
            correlation = _pearson([float(by_group[group]["transformed"][measure]) for group in unique_groups], [float(by_group[group]["transformed"][prior]) for group in unique_groups])
            correlations.append({"left": prior, "right": measure, "pearson": correlation})
            if abs(correlation) >= threshold:
                rejected_by = prior
                break
        if rejected_by is None:
            kept.append(measure)
        else:
            exclusions[measure] = "redundant_with:" + rejected_by
    output: list[dict[str, Any]] = []
    for row in baseline:
        group = str(row["successor_physical_location_id"])
        state = by_group[group]
        public_features = dict(row["features"])
        public_features.update({measure: state["transformed"][measure] for measure in kept})
        output.append({
            "source_observation_id": row["source_observation_id"],
            "successor_physical_location_id": group,
            "market": row["market"],
            "forecast_vintage": row["forecast_vintage"],
            "features": public_features,
            "data03_feature_profiles": state["profiles"],
            "member_tract_count_5mi": state["member_tract_count_5mi"],
        })
    require(len(output) == contract["cohort"]["eligible_observation_count"] and len(unique_groups) == contract["cohort"]["physical_location_count"], "COMPLETE_COHORT_ACCOUNTING_FAILED", "target-blind feature rows do not cover the fixed cohort")
    quality = {}
    for measure in measure_ids:
        valid_profiles = [by_group[group]["profiles"][measure] for group in unique_groups if by_group[group]["profiles"][measure]["status"] == "valid"]
        relative = [float(item["moe"]) / abs(float(item["value"])) for item in valid_profiles if item["value"] not in (None, 0)]
        quality[measure] = {"valid_physical_location_count": len(valid_profiles), "maximum_relative_moe": max(relative) if relative else None}
    maximum_correlation = max((abs(float(item["pearson"])) for item in correlations), default=0.0)
    return output, {"eligible_data03_features": kept, "excluded_data03_features": exclusions, "pairwise_collinearity": correlations, "maximum_absolute_pairwise_correlation": maximum_correlation, "quality_diagnostics": quality}


class TargetBlindFreezeRun:
    def __init__(self, output_root: Path, repository_root: Path, *, freeze_run_id: str | None = None):
        self.output_root = output_root.resolve()
        require(self.output_root.is_dir() and not _is_within(self.output_root, repository_root.resolve()), "PROTECTED_OUTPUT_INVALID", "MODEL-11 output root must exist outside Git")
        self.freeze_run_id = freeze_run_id or "m11freeze-" + str(uuid.uuid4())
        require(bool(re.fullmatch(r"m11freeze-[A-Za-z0-9_-]+", self.freeze_run_id)), "MODEL11_FREEZE_ID_INVALID", "MODEL-11 feature-freeze identity is invalid")
        root = self.output_root / "model11-feature-freezes"
        root.mkdir(exist_ok=True)
        self.run_dir = root / self.freeze_run_id
        require(not self.run_dir.exists(), "MODEL11_FREEZE_IMMUTABLE", "MODEL-11 feature freeze already exists")
        self.run_dir.mkdir()
        write_json_exclusive(self.run_dir / "freeze_state.json", {"freeze_run_id": self.freeze_run_id, "state": "incomplete", "target_accessed": False, "finalization_state": "not_ready"})

    def finalize(self, semantic: Mapping[str, Any]) -> None:
        protected_hash = content_digest(semantic)
        package = {**copy.deepcopy(dict(semantic)), "protected_content_sha256": protected_hash, "stable_feature_freeze_identity": "model11-feature-freeze:sha256:" + protected_hash}
        package_path = self.run_dir / "model11_target_blind_feature_freeze_package.json"
        write_json_exclusive(package_path, package)
        write_json_exclusive(self.run_dir / "READY.json", {"freeze_run_id": self.freeze_run_id, "package_id": FREEZE_PACKAGE_ID, "state": "ready", "finalization_state": "complete", "target_accessed": False, "protected_content_sha256": protected_hash, "package_file_sha256": file_sha256(package_path)})


@dataclass(frozen=True)
class FeatureFreezeResult:
    eligible_observation_count: int
    physical_location_count: int
    candidate_measure_count: int
    eligible_feature_count: int
    excluded_feature_count: int
    maximum_absolute_pairwise_correlation: float


def execute_target_blind_feature_freeze(*, repository_root: Path, resolver: ProtectedHandleResolver, freeze_run_id: str | None = None) -> FeatureFreezeResult:
    root = repository_root.resolve()
    contract = verify_repository_authority(root)
    request = resolver.development_request
    model10_resource = resolver.resolve(str(request["model10_package_handle"]), "model10_package")
    model10_ready_resource = resolver.resolve(str(request["model10_ready_marker_handle"]), "model10_ready_marker")
    acs_resource = resolver.resolve(str(request["acs_b11001_source_handle"]), "accepted_acs_b11001_source")
    tiger_resource = resolver.resolve(str(request["tiger_source_handle"]), "accepted_tiger_tract_source")
    normalized_resource = resolver.resolve(str(request["data03_normalized_source_handle"]), "data03_normalized_source")
    report_resource = resolver.resolve(str(request["data03_verification_report_handle"]), "data03_verification_report")
    data03_ready_resource = resolver.resolve(str(request["data03_ready_marker_handle"]), "data03_ready_marker")
    output_resource = resolver.resolve(str(request["model11_output_root_handle"]), "model11_output_root")
    staged = TargetBlindFreezeRun(output_resource.path, root, freeze_run_id=freeze_run_id)
    model10 = verify_model10_package(model10_resource.path, model10_ready_resource.path)
    cohort = _target_blind_cohort(model10, contract)
    acs_manifest = _load_object(root / "data/manifests/acs_2024_acs5_b11001_wisconsin_tract.source_manifest.json", "ACS_MANIFEST_MISSING")
    tiger_manifest = _load_object(root / "data/manifests/tiger_2024_wisconsin_tract.source_manifest.json", "TIGER_MANIFEST_MISSING")
    geo03 = _load_object(root / "config/geo/geo03_internal_point_membership_spatial_spec.json", "GEO03_AUTHORITY_MISSING")
    tracts = load_public_tract_evidence(tiger_source=tiger_resource.path, acs_source=acs_resource.path, tiger_manifest=tiger_manifest, acs_manifest=acs_manifest, geo03_spec=geo03)
    components = load_data03_components(normalized_resource.path, report_resource.path, data03_ready_resource.path, contract)
    rows, preparation = build_multivariate_features(cohort, tracts, components, geo03, contract)
    semantic = {
        "$schema": FREEZE_SCHEMA,
        "package_id": FREEZE_PACKAGE_ID,
        "version": "1.0.0",
        "freeze_run_id": staged.freeze_run_id,
        "state": "ready",
        "authority": {"model11_contract_id": CONTRACT_ID, "data03_contract_id": DATA03_CONTRACT_ID, "model10_ready_verified": True, "acs_manifest_id": acs_manifest.get("manifest_id"), "tiger_manifest_id": tiger_manifest.get("manifest_id"), "protected_registry_identity": resolver.registry_identity},
        "evidence_accounting": {"eligible_observation_count": len(rows), "physical_location_count": len({row["successor_physical_location_id"] for row in rows}), "quarantined_observation_count": contract["cohort"]["quarantined_observation_count"], "target_values_accessed": 0, "complete_cohort_accounted": True},
        "feature_preparation": {"target_blind": True, "candidate_measure_count": len(contract["candidate_measures"]), **preparation},
        "observations": rows,
        "finalization": {"target_accessed": False, "market_or_vintage_used_as_predictor": False, "row_dropping": False, "imputation": False, "ready_marker_written_last": True},
    }
    staged.finalize(semantic)
    return FeatureFreezeResult(len(rows), contract["cohort"]["physical_location_count"], len(contract["candidate_measures"]), len(preparation["eligible_data03_features"]), len(preparation["excluded_data03_features"]), float(preparation["maximum_absolute_pairwise_correlation"]))


def build_disclosure_safe_freeze_result(result: FeatureFreezeResult) -> dict[str, Any]:
    return {
        "completion_state": "MODEL-11 target-blind feature freeze ready",
        "phase": "TARGET_BLIND_BEFORE_TARGET_ACCESS",
        "eligible_observation_count": result.eligible_observation_count,
        "physical_location_count": result.physical_location_count,
        "candidate_measure_count": result.candidate_measure_count,
        "eligible_data03_feature_count": result.eligible_feature_count,
        "excluded_data03_feature_count": result.excluded_feature_count,
        "maximum_absolute_pairwise_correlation": round(result.maximum_absolute_pairwise_correlation, 4),
        "target_values_accessed": 0,
        "row_dropping": False,
        "imputation": False,
        "protected_output_outside_git": True,
        "protected_details_disclosed": False,
    }
