"""Target-blind Michigan source projection and physical-location identity."""

from __future__ import annotations

from collections import defaultdict
import math
import re
from typing import Any, Mapping, Sequence

from sprouts_customer_geography.model06 import ProjectedWorkbook, build_identity_package, read_target_blind_projection
from sprouts_customer_geography.pipe01.canonical import content_digest
from sprouts_customer_geography.pipe01.errors import require

from .resolver import ProtectedHandleResolver


IDENTITY_PACKAGE_ID = "MODEL12_MICHIGAN_PHYSICAL_LOCATION_IDENTITY_PACKAGE_V1"
IDENTITY_PACKAGE_VERSION = "1.0.0"
IDENTITY_VERSION = "MODEL04_TARGET_BLIND_PHYSICAL_LOCATION_IDENTITY_V1"
SOURCE_PROJECTION_ID = "MODEL12_TARGET_BLIND_IDENTITY_PROJECTION_V1"


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _normalized(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", _text(value).lower())


def _year(value: Any) -> int:
    match = re.search(r"(?:19|20)[0-9]{2}", _text(value))
    require(match is not None, "MODEL12_VINTAGE_INVALID", "forecast vintage does not contain a four-digit year")
    return int(match.group(0))


def load_target_blind_projection(resolver: ProtectedHandleResolver) -> ProjectedWorkbook:
    """Materialize only the registry-authorized identity projection from the exact source."""

    source = resolver.resolve_source()
    source_identity = str(resolver.source_authority["source_authority_id"])
    projection = read_target_blind_projection(
        source.path,
        source_identity,
        header_alias_overrides=resolver.header_alias_overrides,
    )
    report = projection.access_report
    require(
        report.get("outside_projection_body_values_materialized") == 0
        and report.get("formula_values_materialized") == 0
        and report.get("styles_comments_charts_metadata_loaded") is False
        and bool(report.get("target_headers_confirmed_outside_projection")),
        "MODEL12_TARGET_BLIND_PROJECTION_INVALID",
        "target-blind source access proof is incomplete",
    )
    require(bool(projection.rows), "MODEL12_SOURCE_EMPTY", "target-blind source projection is empty")
    vintages = {_year(row.get("vintage")) for row in projection.rows}
    states = {_normalized(row.get("state")) for row in projection.rows}
    require(vintages == {2024, 2025, 2026}, "MODEL12_SOURCE_VINTAGE_INCOMPLETE", "complete 2024 2025 and 2026 source coverage is required")
    require(states <= {"mi", "michigan"} and bool(states), "MODEL12_NON_MICHIGAN_SOURCE_REJECTED", "target-blind source contains non-Michigan evidence")
    seen_rows: set[int] = set()
    for row in projection.rows:
        source_row = row.get("source_row")
        require(isinstance(source_row, int) and source_row > 1 and source_row not in seen_rows, "MODEL12_SOURCE_OBSERVATION_DUPLICATE", "source projection row identity is missing or duplicate")
        require(bool(_text(row.get("market"))), "MODEL12_MARKET_LINEAGE_MISSING", "source market lineage is missing")
        seen_rows.add(source_row)
    return projection


def _source_observation_id(source_authority_id: str, row: Mapping[str, Any]) -> str:
    semantic = {
        "domain": "sprouts-customer-geography/model12/source-observation/v1",
        "source_authority_id": source_authority_id,
        "source_projection_row": int(row["source_row"]),
        "source_seed_point_id": _text(row.get("seed_point_id")),
        "forecast_vintage": _year(row.get("vintage")),
    }
    return "m12obs-" + content_digest(semantic)[:24]


def _physical_location_id(anchor_observation_id: str, coordinate: Mapping[str, Any], quarantined: bool) -> str:
    semantic = {
        "domain": "sprouts-customer-geography/model12/quarantined-location/v1"
        if quarantined
        else "sprouts-customer-geography/model12/physical-location/v1",
        "anchor_source_observation_id": anchor_observation_id,
        "observed_coordinate": {
            "latitude": float(coordinate["latitude"]),
            "longitude": float(coordinate["longitude"]),
        },
    }
    return ("m12qloc-" if quarantined else "m12loc-") + content_digest(semantic)[:24]


def build_michigan_identity_package(
    projection: ProjectedWorkbook,
    *,
    registry_identity: str,
    contract_authority: Mapping[str, Any],
) -> dict[str, Any]:
    """Reuse accepted identity rules statewide without target or Wisconsin linkage."""

    original_by_row: dict[int, dict[str, Any]] = {}
    statewide_rows: list[dict[str, Any]] = []
    for raw in projection.rows:
        row = dict(raw)
        source_row = int(row["source_row"])
        require(source_row not in original_by_row, "MODEL12_SOURCE_OBSERVATION_DUPLICATE", "source observation identity is duplicate")
        original_by_row[source_row] = dict(row)
        # The accepted MODEL-04 implementation partitions its historical roles by
        # two Wisconsin market labels. MODEL-12 supplies one internal sentinel so
        # the exact matching rules operate in a Michigan-state partition, then
        # restores the exact source market as protected lineage below.
        row["market"] = "Milwaukee"
        statewide_rows.append(row)
    statewide = ProjectedWorkbook(
        source_identity=projection.source_identity,
        rows=tuple(statewide_rows),
        projection_sha256=projection.projection_sha256,
        access_report=projection.access_report,
    )
    base = build_identity_package([statewide])
    base_records = list(base.get("records", []))
    require(len(base_records) == len(projection.rows), "MODEL12_COMPLETE_SOURCE_ACCOUNTING_FAILED", "identity output does not account for every projected observation")

    observation_ids: dict[int, str] = {}
    for source_row, original in original_by_row.items():
        observation_id = _source_observation_id(projection.source_identity, original)
        require(observation_id not in observation_ids.values(), "MODEL12_SOURCE_OBSERVATION_DUPLICATE", "source-observation identity is duplicate")
        observation_ids[source_row] = observation_id

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in base_records:
        grouped[str(record["physical_location_id"])].append(dict(record))

    observations: list[dict[str, Any]] = []
    physical_locations: list[dict[str, Any]] = []
    for _, records in sorted(
        grouped.items(),
        key=lambda item: min((int(record["vintage_year"]), int(record["source_row"])) for record in item[1]),
    ):
        ordered = sorted(records, key=lambda record: (int(record["vintage_year"]), int(record["source_row"]), str(record["source_seed_point_id"])))
        quarantined = any(record.get("quarantined") is True for record in ordered)
        require(all((record.get("quarantined") is True) == quarantined for record in ordered), "MODEL12_IDENTITY_GROUP_STATE_MISMATCH", "one physical-location group mixes resolved and quarantined identity")
        anchor = ordered[0].get("canonical_anchor")
        if quarantined:
            anchor_record = ordered[0]
            anchor_coordinate = anchor_record["observed_coordinate"]
            canonical_coordinate = None
        else:
            require(isinstance(anchor, Mapping), "MODEL12_CANONICAL_ANCHOR_MISSING", "resolved physical location lacks its accepted canonical anchor")
            anchor_record = next((record for record in ordered if int(record["source_row"]) == int(anchor["source_row"])), None)
            require(isinstance(anchor_record, Mapping), "MODEL12_CANONICAL_ANCHOR_MISSING", "accepted canonical anchor does not resolve to a source observation")
            anchor_coordinate = {"latitude": float(anchor["latitude"]), "longitude": float(anchor["longitude"])}
            canonical_coordinate = dict(anchor_coordinate)
        anchor_observation_id = observation_ids[int(anchor_record["source_row"])]
        physical_id = _physical_location_id(anchor_observation_id, anchor_coordinate, quarantined)
        member_ids: list[str] = []
        markets: set[str] = set()
        vintages: set[int] = set()
        reasons: set[str] = set()
        for record in ordered:
            source_row = int(record["source_row"])
            original = original_by_row[source_row]
            observation_id = observation_ids[source_row]
            market = _text(original.get("market"))
            vintage = _year(original.get("vintage"))
            observed = record["observed_coordinate"]
            member_ids.append(observation_id)
            markets.add(market)
            vintages.add(vintage)
            reasons.add(str(record["identity_rule_reason_code"]))
            observations.append(
                {
                    "source_observation_id": observation_id,
                    "source_observation_lineage": {
                        "source_authority_id": projection.source_identity,
                        "source_projection_id": SOURCE_PROJECTION_ID,
                        "source_projection_row": source_row,
                        "source_seed_point_id": _text(original.get("seed_point_id")),
                        "forecast_vintage_original": _text(original.get("vintage")),
                    },
                    "forecast_vintage": vintage,
                    "source_market_lineage": market,
                    "physical_location_id": physical_id,
                    "identity_state": str(record["identity_state"]),
                    "identity_rule_reason_code": str(record["identity_rule_reason_code"]),
                    "quarantined": quarantined,
                    "quarantine_reason": "CONFLICTING_OR_10_TO_500M_IDENTITY_EVIDENCE" if quarantined else None,
                    "observed_coordinate": {
                        "latitude": float(observed["latitude"]),
                        "longitude": float(observed["longitude"]),
                    },
                    "canonical_target_blind_coordinate": canonical_coordinate,
                    "target_access_state": "NOT_ACCESSED_BY_MODEL12",
                }
            )
        physical_locations.append(
            {
                "physical_location_id": physical_id,
                "identity_state": "AMBIGUOUS_IDENTITY" if quarantined else "RESOLVED_TARGET_BLIND_IDENTITY",
                "identity_rule_reason_codes": sorted(reasons),
                "quarantined": quarantined,
                "quarantine_reason": "CONFLICTING_OR_10_TO_500M_IDENTITY_EVIDENCE" if quarantined else None,
                "canonical_target_blind_coordinate": canonical_coordinate,
                "canonical_anchor_source_observation_id": None if quarantined else anchor_observation_id,
                "canonical_anchor_selection_semantics": None if quarantined else "EARLIEST_VINTAGE_THEN_SOURCE_LINEAGE",
                "source_observation_ids": member_ids,
                "source_vintages": sorted(vintages),
                "source_market_lineage_values": sorted(markets),
            }
        )

    observations.sort(key=lambda row: (int(row["forecast_vintage"]), int(row["source_observation_lineage"]["source_projection_row"]), str(row["source_observation_id"])))
    physical_locations.sort(key=lambda row: min(observations.index(item) for item in observations if item["physical_location_id"] == row["physical_location_id"]))
    package = {
        "$schema": "model12-michigan-physical-location-identity-package-v1",
        "package_id": IDENTITY_PACKAGE_ID,
        "version": IDENTITY_PACKAGE_VERSION,
        "state": "ready",
        "contract_authority": dict(contract_authority),
        "source_authority": {
            "source_authority_id": projection.source_identity,
            "source_projection_id": SOURCE_PROJECTION_ID,
            "projection_sha256": projection.projection_sha256,
            "whole_source_file_hash_computed": False,
            "complete_forecast_vintages": [2024, 2025, 2026],
        },
        "target_blind_projection": {
            **dict(projection.access_report),
            "target_body_values_accessed": 0,
            "target_body_values_materialized": 0,
            "body_values_outside_projection_materialized": 0,
            "target_content_invariance_by_construction": True,
        },
        "identity_rules": {
            "reused_identity_version": IDENTITY_VERSION,
            "physical_location_matching_partition": "michigan_state",
            "probable_same_max_m": 10.0,
            "coherent_stable_non_target_lineage_max_m": 500.0,
            "ambiguity_band_m": {"exclusive_minimum": 10.0, "inclusive_maximum": 500.0},
            "genuinely_new_minimum_m_exclusive": 500.0,
            "seed_id_novelty_alone_is_novelty": False,
            "source_market_label_is_identity_partition": False,
            "target_evidence_permitted": False,
            "wisconsin_historical_linkage_required": False,
            "new_threshold_or_tolerance_introduced": False,
        },
        "source_observations": observations,
        "physical_locations": physical_locations,
        "aggregate_conformance": {
            "source_observation_count": len(observations),
            "physical_location_count": len(physical_locations),
            "quarantined_source_observation_count": sum(row["quarantined"] for row in observations),
            "quarantined_physical_location_count": sum(row["quarantined"] for row in physical_locations),
            "forecast_vintages": sorted({row["forecast_vintage"] for row in observations}),
            "complete_source_observation_accounting": len(observations) == len(projection.rows),
        },
        "target_access": {
            "target_body_values_accessed": 0,
            "target_body_values_materialized": 0,
            "target_ordering_used": False,
            "target_ranking_used": False,
            "target_summary_computed": False,
            "pipe_target_binding_created": False,
        },
        "protected_handle_registry_identity": registry_identity,
    }
    validate_identity_package(package)
    return package


def validate_identity_package(package: Mapping[str, Any]) -> None:
    require(package.get("package_id") == IDENTITY_PACKAGE_ID and package.get("version") == IDENTITY_PACKAGE_VERSION and package.get("state") == "ready", "MODEL12_IDENTITY_PACKAGE_MISMATCH", "MODEL-12 identity package identity or state differs")
    observations = package.get("source_observations")
    locations = package.get("physical_locations")
    require(isinstance(observations, list) and observations and isinstance(locations, list) and locations, "MODEL12_IDENTITY_PACKAGE_SCHEMA_INVALID", "MODEL-12 identity observations or physical locations are absent")
    observation_ids = [row.get("source_observation_id") for row in observations]
    location_ids = [row.get("physical_location_id") for row in locations]
    require(len(observation_ids) == len(set(observation_ids)) and len(location_ids) == len(set(location_ids)), "MODEL12_IDENTITY_PACKAGE_DUPLICATE", "MODEL-12 identity package contains duplicate identities")
    by_location = {str(row["physical_location_id"]): row for row in locations}
    for observation in observations:
        location = by_location.get(str(observation.get("physical_location_id")))
        require(location is not None and observation["source_observation_id"] in location["source_observation_ids"], "MODEL12_IDENTITY_MEMBERSHIP_MISMATCH", "source observation is not accounted by its physical location")
        require(observation.get("target_access_state") == "NOT_ACCESSED_BY_MODEL12", "MODEL12_TARGET_ACCESS_VIOLATION", "target evidence entered MODEL-12 identity")
        require((observation.get("canonical_target_blind_coordinate") is None) is bool(observation.get("quarantined")), "MODEL12_CANONICAL_ANCHOR_STATE_MISMATCH", "quarantine and canonical anchor state differ")
    covered = [value for location in locations for value in location["source_observation_ids"]]
    require(sorted(covered) == sorted(observation_ids) and len(covered) == len(set(covered)), "MODEL12_COMPLETE_SOURCE_ACCOUNTING_FAILED", "source observations are missing duplicated or multiply assigned")
    aggregate = package.get("aggregate_conformance", {})
    require(
        aggregate.get("source_observation_count") == len(observations)
        and aggregate.get("physical_location_count") == len(locations)
        and aggregate.get("quarantined_source_observation_count") == sum(bool(row["quarantined"]) for row in observations)
        and aggregate.get("quarantined_physical_location_count") == sum(bool(row["quarantined"]) for row in locations)
        and aggregate.get("forecast_vintages") == [2024, 2025, 2026]
        and aggregate.get("complete_source_observation_accounting") is True,
        "MODEL12_IDENTITY_AGGREGATE_MISMATCH",
        "MODEL-12 identity aggregate accounting differs",
    )
    target = package.get("target_access", {})
    require(target and all(value == 0 if isinstance(value, int) and not isinstance(value, bool) else value is False for value in target.values()), "MODEL12_TARGET_ACCESS_VIOLATION", "target-derived evidence entered MODEL-12 identity")


def execute_identity_projection(resolver: ProtectedHandleResolver, contract_authority: Mapping[str, Any]) -> dict[str, Any]:
    projection = load_target_blind_projection(resolver)
    return build_michigan_identity_package(
        projection,
        registry_identity=resolver.registry_identity,
        contract_authority=contract_authority,
    )
