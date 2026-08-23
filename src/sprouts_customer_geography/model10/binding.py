"""MODEL-10 target-blind successor identity reconciliation and finalization."""

from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from sprouts_customer_geography.model06 import (
    COMMITMENT_ID as MODEL04_COMMITMENT_ID,
    COMMITMENT_VERSION as MODEL04_COMMITMENT_VERSION,
    PACKAGE_ID as MODEL04_PACKAGE_ID,
    PACKAGE_VERSION as MODEL04_PACKAGE_VERSION,
    ProjectedWorkbook,
    _haversine_m,
    _normalized_text,
    build_identity_package,
    read_target_blind_projection,
)
from sprouts_customer_geography.pipe01.canonical import (
    content_digest,
    file_sha256,
    write_json_exclusive,
)
from sprouts_customer_geography.pipe01.commitment import (
    DOMAIN_SEPARATOR,
    freeze_commitment,
    new_nonce,
)
from sprouts_customer_geography.pipe01.errors import require
from sprouts_customer_geography.pipe01.orchestration import load_model04_binding
from sprouts_customer_geography.pipe02.resolver import _is_within

from .resolver import ProtectedHandleResolver


PACKAGE_ID = "MODEL10_WISCONSIN_COHORT_IDENTITY_LINEAGE_PACKAGE_V1"
PACKAGE_VERSION = "1.0.0"
COMMITMENT_ID = "MODEL10_WISCONSIN_COHORT_IDENTITY_LINEAGE_COMMITMENT_V1"
COMMITMENT_VERSION = "1.0.0"
CONTRACT_ID = "MODEL10_WISCONSIN_COHORT_IDENTITY_LINEAGE_CONTRACT_V1"
CONTRACT_VERSION = "1.0.0"
PACKAGE_SCHEMA_VERSION = "model10-wisconsin-cohort-identity-lineage-package-v1"
PROJECTION_ID = "MODEL04_TARGET_BLIND_A_I_IDENTITY_PROJECTION_V1"
MODEL04_DOCUMENT = "config/model/model04_validation_identity_role_anchor_commitment.json"
MODEL10_CONTRACT_DOCUMENT = "config/model/model10_wisconsin_cohort_identity_lineage_contract.json"
MODEL07_DOCUMENT = "docs/work_orders/MODEL_07_MILWAUKEE_TEMPORAL_VALIDATION_GATE.md"
MODEL08_DOCUMENT = "docs/work_orders/MODEL_08_WISCONSIN_EVIDENCE_EXPANSION_STRATEGY.md"
WISCONSIN_VINTAGES = frozenset({2024, 2025, 2026})


def _load_object(path: Path, code: str) -> dict[str, Any]:
    require(path.is_file(), code, "required authority is absent")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        require(False, code, "required authority is unreadable")
    require(isinstance(value, dict), code, "required authority must be an object")
    return value


def _source_observation_id(record: Mapping[str, Any]) -> str:
    lineage = {
        "domain": "sprouts-customer-geography/model10/source-observation/v1",
        "source_workbook_identity": record["source_workbook_identity"],
        "source_sheet": record["source_sheet"],
        "source_row": record["source_row"],
        "source_seed_point_id": record["source_seed_point_id"],
        "forecast_vintage": record["vintage_year"],
    }
    return "sobs-" + content_digest(lineage)[:24]


def _successor_location_id(records: Sequence[Mapping[str, Any]], *, quarantined: bool) -> str:
    anchor = min(
        records,
        key=lambda record: (
            record["vintage_year"],
            record["source_workbook_identity"],
            record["source_sheet"],
            record["source_row"],
            record["source_seed_point_id"],
        ),
    )
    identity = {
        "domain": "sprouts-customer-geography/model10/quarantined-location/v1"
        if quarantined
        else "sprouts-customer-geography/model10/physical-location/v1",
        "source_observation_id": _source_observation_id(anchor),
        "observed_coordinate": anchor["observed_coordinate"],
    }
    return ("m10qloc-" if quarantined else "m10loc-") + content_digest(identity)[:24]


def _distance(left: Mapping[str, Any], right: Mapping[str, Any]) -> float:
    return _haversine_m(left["observed_coordinate"], right["observed_coordinate"])


def _same_seed(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    left_seed = _normalized_text(left.get("source_seed_point_id"))
    right_seed = _normalized_text(right.get("source_seed_point_id"))
    return bool(left_seed and left_seed == right_seed)


def _historical_decision(
    successor_records: Sequence[Mapping[str, Any]],
    historical_records: Sequence[Mapping[str, Any]],
) -> tuple[str | None, str | None, str | None]:
    historical_wisconsin = [
        historical
        for historical in historical_records
        if not historical.get("quarantined")
    ]
    exact_ids = {
        str(historical["physical_location_id"])
        for successor in successor_records
        for historical in historical_wisconsin
        if successor["observed_coordinate"]["latitude"]
        == historical["observed_coordinate"]["latitude"]
        and successor["observed_coordinate"]["longitude"]
        == historical["observed_coordinate"]["longitude"]
    }
    if len(exact_ids) == 1:
        return next(iter(exact_ids)), "EXACT_OBSERVED_COORDINATE", None
    if len(exact_ids) > 1:
        return None, None, "CONFLICTING_HISTORICAL_MODEL04_LINKAGE"

    stable_ids = {
        str(historical["physical_location_id"])
        for successor in successor_records
        for historical in historical_wisconsin
        if _same_seed(successor, historical) and _distance(successor, historical) <= 500.0
    }
    if len(stable_ids) == 1:
        return next(iter(stable_ids)), "COHERENT_STABLE_NON_TARGET_LINEAGE", None
    if len(stable_ids) > 1:
        return None, None, "CONFLICTING_HISTORICAL_MODEL04_LINKAGE"

    lineage_conflict = any(
        _same_seed(successor, historical) and _distance(successor, historical) > 500.0
        for successor in successor_records
        for historical in historical_wisconsin
    )
    unresolved_band = any(
        10.0 < _distance(successor, historical) <= 500.0
        for successor in successor_records
        for historical in historical_wisconsin
    )
    if lineage_conflict or unresolved_band:
        return None, None, "CONFLICTING_OR_10_TO_500M_IDENTITY_EVIDENCE"
    return None, None, None


def _historical_roles(
    physical_location_id: str | None,
    historical_records: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    if physical_location_id is None:
        return []
    unique = {
        (
            str(record.get("evidence_role")),
            str(record.get("evidence_subrole")),
            str(record.get("target_view_state")),
        )
        for record in historical_records
        if record.get("physical_location_id") == physical_location_id
    }
    return [
        {
            "evidence_role": role,
            "evidence_subrole": subrole,
            "historical_target_view_state": target_state,
        }
        for role, subrole, target_state in sorted(unique)
    ]


def build_successor_identity_package(
    workbooks: Sequence[ProjectedWorkbook],
    historical_model04_package: Mapping[str, Any],
    *,
    materialization_run_id: str,
    package_version: str = PACKAGE_VERSION,
    source_authorities: Mapping[str, Mapping[str, Any]] | None = None,
    contract_authority: Mapping[str, Any] | None = None,
    registry_identity: str = "protected-registry",
    supersedes: str | None = None,
) -> dict[str, Any]:
    """Build successor identity without accepting any target-derived input."""

    require(
        historical_model04_package.get("package_id") == MODEL04_PACKAGE_ID
        and historical_model04_package.get("package_version") == MODEL04_PACKAGE_VERSION,
        "MODEL04_PACKAGE_IDENTITY_MISMATCH",
        "historical package differs from immutable MODEL-04 authority",
    )
    original_rows: dict[tuple[str, int], Mapping[str, Any]] = {}
    statewide_workbooks: list[ProjectedWorkbook] = []
    for workbook in workbooks:
        statewide_rows: list[dict[str, Any]] = []
        for raw in workbook.rows:
            original = dict(raw)
            key = (workbook.source_identity, int(original["source_row"]))
            require(key not in original_rows, "SUCCESSOR_SOURCE_OBSERVATION_DUPLICATE", "successor source row identity is duplicate")
            require(_normalized_text(original.get("state")) in {"wi", "wisconsin"}, "SUCCESSOR_NON_WISCONSIN_REJECTED", "successor source contains non-Wisconsin evidence")
            require(str(original.get("market") or "").strip(), "SUCCESSOR_MARKET_LINEAGE_MISSING", "successor source market lineage is missing")
            original_rows[key] = original
            # MODEL-04's accepted implementation partitions on its two historical
            # canonical markets. MODEL-10 intentionally supplies one internal
            # sentinel so those same rules operate statewide; exact source market
            # values are restored below as protected observation lineage.
            row = dict(original)
            row["market"] = "Milwaukee"
            statewide_rows.append(row)
        statewide_workbooks.append(
            ProjectedWorkbook(
                source_identity=workbook.source_identity,
                rows=tuple(statewide_rows),
                projection_sha256=workbook.projection_sha256,
                access_report=workbook.access_report,
            )
        )
    successor_base = build_identity_package(statewide_workbooks)
    base_records = list(successor_base["records"])
    require(base_records, "SUCCESSOR_COHORT_EMPTY", "successor target-blind cohort is empty")
    require(
        {int(record["vintage_year"]) for record in base_records} == WISCONSIN_VINTAGES,
        "SUCCESSOR_COHORT_VINTAGE_INCOMPLETE",
        "complete successor 2024 2025 and 2026 cohort is required",
    )
    source_ids = {workbook.source_identity for workbook in workbooks}
    require(len(source_ids) == len(workbooks), "SUCCESSOR_SOURCE_IDENTITY_DUPLICATE", "successor source identities must be unique")
    if source_authorities is not None:
        require(set(source_authorities) == source_ids, "SUCCESSOR_SOURCE_AUTHORITY_MISMATCH", "source authorities must cover every and only projected workbook")
        for workbook in workbooks:
            authority = source_authorities[workbook.source_identity]
            records = [record for record in base_records if record["source_workbook_identity"] == workbook.source_identity]
            require(len(records) == authority["expected_observation_count"], "SUCCESSOR_SOURCE_COUNT_MISMATCH", "protected projected observation count differs from exact authority")
            require({record["vintage_year"] for record in records} == set(authority["expected_forecast_vintages"]), "SUCCESSOR_SOURCE_VINTAGE_MISMATCH", "source vintages differ from exact authority")
            source_markets = {
                str(original_rows[(workbook.source_identity, int(record["source_row"]))]["market"]).strip()
                for record in records
            }
            require(source_markets == set(authority["expected_markets"]), "SUCCESSOR_SOURCE_MARKET_MISMATCH", "source markets differ from exact authority")

    historical_records = list(historical_model04_package.get("records", []))
    require(historical_records, "MODEL04_PACKAGE_SCHEMA_INVALID", "historical MODEL-04 records are absent")
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in base_records:
        grouped.setdefault(str(record["physical_location_id"]), []).append(record)

    output_records: list[dict[str, Any]] = []
    source_observation_ids: set[str] = set()
    for _temporary_id, group in sorted(
        grouped.items(),
        key=lambda item: min(
            (record["vintage_year"], record["source_workbook_identity"], record["source_row"])
            for record in item[1]
        ),
    ):
        internal_ambiguity = any(record["quarantined"] for record in group)
        historical_id: str | None = None
        historical_reason: str | None = None
        quarantine_reason: str | None = None
        if internal_ambiguity:
            quarantine_reason = "CONFLICTING_OR_10_TO_500M_IDENTITY_EVIDENCE"
        else:
            historical_id, historical_reason, quarantine_reason = _historical_decision(group, historical_records)
        quarantined = quarantine_reason is not None
        successor_location_id = historical_id or _successor_location_id(group, quarantined=quarantined)
        roles = _historical_roles(historical_id, historical_records)
        anchor = min(
            group,
            key=lambda record: (
                record["vintage_year"],
                record["source_workbook_identity"],
                record["source_sheet"],
                record["source_row"],
                record["source_seed_point_id"],
            ),
        )
        for record in sorted(group, key=lambda item: (item["vintage_year"], item["source_workbook_identity"], item["source_row"])):
            original = original_rows[(str(record["source_workbook_identity"]), int(record["source_row"]))]
            market_lineage = str(original["market"]).strip()
            observation_id = _source_observation_id(record)
            require(observation_id not in source_observation_ids, "SUCCESSOR_SOURCE_OBSERVATION_DUPLICATE", "successor source-observation identity is duplicate")
            source_observation_ids.add(observation_id)
            identity_state = "AMBIGUOUS_IDENTITY" if quarantined else (
                "SAME_UNDERLYING_LOCATION" if historical_id else record["identity_state"]
            )
            reason = quarantine_reason or historical_reason or record["identity_rule_reason_code"]
            output_records.append(
                {
                    "source_observation_id": observation_id,
                    "source_observation_lineage": {
                        "source_workbook_identity": record["source_workbook_identity"],
                        "source_sheet": record["source_sheet"],
                        "source_row": record["source_row"],
                        "source_seed_point_id": record["source_seed_point_id"],
                        "forecast_vintage_original": record["vintage"],
                    },
                    "market": market_lineage,
                    "forecast_vintage": record["vintage_year"],
                    "successor_physical_location_id": successor_location_id,
                    "physical_location_identity_origin": "HISTORICAL_MODEL04" if historical_id else "MODEL10_SUCCESSOR",
                    "historical_model04_physical_location_id": historical_id,
                    "identity_state": identity_state,
                    "identity_rule_reason_code": reason,
                    "quarantined": quarantined,
                    "quarantine_reason": quarantine_reason,
                    "historical_evidence_role_lineage": roles,
                    "observed_coordinate": record["observed_coordinate"],
                    "successor_canonical_anchor": None if quarantined else {
                        "source_observation_id": _source_observation_id(anchor),
                        "observed_coordinate": anchor["observed_coordinate"],
                        "selection_semantics": "EARLIEST_VINTAGE_THEN_SOURCE_LINEAGE",
                    },
                    "model09_development_eligible": not quarantined,
                    "target_access_state": "NOT_ACCESSED_BY_MODEL10",
                }
            )

    contract = contract_authority or {"artifact_id": CONTRACT_ID, "version": CONTRACT_VERSION}
    package = {
        "$schema": PACKAGE_SCHEMA_VERSION,
        "package_id": PACKAGE_ID,
        "version": package_version,
        "materialization_run_id": materialization_run_id,
        "state": "ready",
        "contract_authority": dict(contract),
        "model04_authority": {
            "package_id": MODEL04_PACKAGE_ID,
            "package_version": MODEL04_PACKAGE_VERSION,
            "identity_version": historical_model04_package.get("identity_version"),
            "immutable_historical_authority": True,
        },
        "target_blind_projection": {
            "projection_id": PROJECTION_ID,
            "worksheet": "Sheet1",
            "body_columns": "A:I",
            "target_body_values_materialized": False,
            "isolated_sales_materialized": False,
            "impacted_sales_materialized": False,
            "source_access_reports": [dict(workbook.access_report) for workbook in workbooks],
        },
        "source_authorities": [
            {
                "source_workbook_identity": workbook.source_identity,
                "projection_sha256": workbook.projection_sha256,
                "whole_workbook_hash_computed": False,
            }
            for workbook in workbooks
        ],
        "identity_rules": {
            "reused_model04_identity_version": "MODEL04_TARGET_BLIND_PHYSICAL_LOCATION_IDENTITY_V1",
            "probable_same_max_m": 10.0,
            "ambiguity_band_m": {"exclusive_minimum": 10.0, "inclusive_maximum": 500.0},
            "genuinely_new_minimum_m_exclusive": 500.0,
            "seed_id_novelty_alone_is_novelty": False,
            "target_evidence_permitted": False,
            "new_threshold_or_tolerance_introduced": False,
            "physical_location_matching_partition": "wisconsin_state",
            "source_market_label_is_identity_partition": False,
        },
        "records": output_records,
        "aggregate_conformance": {
            "observation_count": len(output_records),
            "physical_location_count": len({record["successor_physical_location_id"] for record in output_records}),
            "historically_linked_observation_count": sum(record["historical_model04_physical_location_id"] is not None for record in output_records),
            "quarantined_observation_count": sum(record["quarantined"] for record in output_records),
            "model09_development_eligible_observation_count": sum(record["model09_development_eligible"] for record in output_records),
            "markets": sorted({record["market"] for record in output_records}),
            "forecast_vintages": sorted({record["forecast_vintage"] for record in output_records}),
        },
        "target_access": {
            "isolated_sales_accessed": False,
            "impacted_sales_accessed": False,
            "target_ordering_used": False,
            "forecast_magnitude_used": False,
            "model_predictions_or_residuals_used": False,
            "marks_development_consumed": False,
        },
        "protected_handle_registry_identity": registry_identity,
        "supersedes": supersedes,
        "supersession_policy": "Never overwrite a MODEL-10 package. A correction requires a new patch version opaque run ID commitment and explicit supersedes lineage.",
    }
    validate_successor_package(package)
    return package


def validate_successor_package(package: Mapping[str, Any]) -> None:
    require(package.get("package_id") == PACKAGE_ID, "MODEL10_PACKAGE_IDENTITY_MISMATCH", "MODEL-10 package ID differs")
    require(bool(re.fullmatch(r"1\.0\.[0-9]+", str(package.get("version")))), "MODEL10_PACKAGE_VERSION_INVALID", "MODEL-10 package version is invalid")
    records = package.get("records")
    require(isinstance(records, list) and records, "MODEL10_PACKAGE_SCHEMA_INVALID", "MODEL-10 records are absent")
    require(all(isinstance(record.get("market"), str) and record["market"].strip() for record in records), "MODEL10_MARKET_LINEAGE_MISSING", "MODEL-10 package must retain source market lineage")
    require({record["forecast_vintage"] for record in records} == WISCONSIN_VINTAGES, "MODEL10_VINTAGE_COMPLETENESS_FAILED", "MODEL-10 package must retain 2024 2025 and 2026")
    observation_ids: set[str] = set()
    for record in records:
        observation_id = record.get("source_observation_id")
        require(isinstance(observation_id, str) and observation_id.startswith("sobs-") and observation_id not in observation_ids, "MODEL10_SOURCE_OBSERVATION_INVALID", "source-observation identity is missing or duplicate")
        observation_ids.add(observation_id)
        quarantined = record.get("quarantined") is True
        lineage = record.get("source_observation_lineage")
        require(
            isinstance(lineage, Mapping)
            and isinstance(lineage.get("source_workbook_identity"), str)
            and bool(lineage["source_workbook_identity"])
            and isinstance(lineage.get("source_sheet"), str)
            and bool(lineage["source_sheet"])
            and isinstance(lineage.get("source_row"), int)
            and lineage["source_row"] > 1
            and isinstance(lineage.get("source_seed_point_id"), str)
            and bool(lineage["source_seed_point_id"]),
            "MODEL10_SOURCE_LINEAGE_INCOMPLETE",
            "successor source-observation lineage is incomplete",
        )
        require(record.get("model09_development_eligible") is (not quarantined), "MODEL10_ELIGIBILITY_MISMATCH", "MODEL-09 eligibility must equal nonquarantine state")
        require((record.get("identity_state") == "AMBIGUOUS_IDENTITY") is quarantined, "MODEL10_QUARANTINE_MISMATCH", "identity ambiguity must map exactly to quarantine")
        require(
            (isinstance(record.get("quarantine_reason"), str) and bool(record["quarantine_reason"]))
            if quarantined
            else record.get("quarantine_reason") is None,
            "MODEL10_QUARANTINE_REASON_MISMATCH",
            "quarantine reason must be present exactly for ambiguous identity",
        )
        require(
            record.get("successor_canonical_anchor") is None
            if quarantined
            else isinstance(record.get("successor_canonical_anchor"), Mapping),
            "MODEL10_ANCHOR_STATE_MISMATCH",
            "quarantined identity cannot carry an anchor and resolved identity must carry one",
        )
        require(record.get("target_access_state") == "NOT_ACCESSED_BY_MODEL10", "MODEL10_TARGET_STATE_INVALID", "MODEL-10 cannot access or consume targets")
        historical = record.get("historical_model04_physical_location_id")
        if historical is not None:
            require(record.get("successor_physical_location_id") == historical, "MODEL10_HISTORICAL_LINKAGE_MISMATCH", "supported MODEL-04 physical-location ID was not preserved")
    target = package.get("target_access")
    require(isinstance(target, Mapping) and all(value is False for value in target.values()), "MODEL10_TARGET_ACCESS_VIOLATION", "target-derived evidence entered MODEL-10")
    projection = package.get("target_blind_projection")
    require(
        isinstance(projection, Mapping)
        and projection.get("body_columns") == "A:I"
        and projection.get("target_body_values_materialized") is False
        and projection.get("isolated_sales_materialized") is False
        and projection.get("impacted_sales_materialized") is False,
        "MODEL10_TARGET_BLIND_PROJECTION_INVALID",
        "target-blind projection proof is incomplete",
    )
    rules = package.get("identity_rules")
    require(
        isinstance(rules, Mapping)
        and rules.get("physical_location_matching_partition") == "wisconsin_state"
        and rules.get("source_market_label_is_identity_partition") is False
        and rules.get("target_evidence_permitted") is False,
        "MODEL10_STATEWIDE_IDENTITY_RULE_MISMATCH",
        "statewide identity partition or target-blind rule differs",
    )
    aggregate = package.get("aggregate_conformance")
    require(
        isinstance(aggregate, Mapping)
        and aggregate.get("observation_count") == len(records)
        and aggregate.get("physical_location_count")
        == len({record["successor_physical_location_id"] for record in records})
        and aggregate.get("historically_linked_observation_count")
        == sum(record["historical_model04_physical_location_id"] is not None for record in records)
        and aggregate.get("quarantined_observation_count")
        == sum(record["quarantined"] for record in records)
        and aggregate.get("model09_development_eligible_observation_count")
        == sum(record["model09_development_eligible"] for record in records)
        and aggregate.get("markets") == sorted({record["market"] for record in records})
        and aggregate.get("forecast_vintages")
        == sorted({record["forecast_vintage"] for record in records}),
        "MODEL10_AGGREGATE_CONFORMANCE_MISMATCH",
        "MODEL-10 aggregate conformance differs from protected observation records",
    )


class ProtectedSuccessorRun:
    """One immutable incomplete-first MODEL-10 protected-local run."""

    def __init__(
        self,
        protected_root: Path,
        repository_root: Path,
        *,
        materialization_run_id: str | None = None,
        package_version: str = PACKAGE_VERSION,
        supersedes: str | None = None,
    ):
        self.protected_root = protected_root.resolve()
        self.repository_root = repository_root.resolve()
        require(not _is_within(self.protected_root, self.repository_root), "PROTECTED_ROOT_INSIDE_REPOSITORY", "MODEL-10 output root must remain outside Git")
        self.materialization_run_id = materialization_run_id or "m10run-" + str(uuid.uuid4())
        require(self.materialization_run_id.startswith("m10run-") and all(character.isalnum() or character in "-_" for character in self.materialization_run_id), "MODEL10_RUN_ID_INVALID", "MODEL-10 run ID must be opaque and safe")
        require(bool(re.fullmatch(r"1\.0\.[0-9]+", package_version)), "MODEL10_PACKAGE_VERSION_INVALID", "MODEL-10 package version must remain in 1.0 patch line")
        if supersedes is not None:
            require(package_version != PACKAGE_VERSION, "MODEL10_SUPERSESSION_VERSION_REQUIRED", "correction requires a new patch version")
            require(supersedes.startswith("m10run-"), "MODEL10_SUPERSESSION_INVALID", "supersession must name an earlier MODEL-10 run")
        self.package_version = package_version
        self.supersedes = supersedes
        self.run_dir = self.protected_root / "model10-materializations" / self.materialization_run_id
        require(not self.run_dir.exists(), "MODEL10_RUN_ALREADY_EXISTS", "never overwrite a MODEL-10 run")
        self.run_dir.mkdir(parents=True, exist_ok=False)
        write_json_exclusive(
            self.run_dir / "materialization_state.json",
            {"materialization_run_id": self.materialization_run_id, "state": "incomplete", "package_version": package_version, "supersedes": supersedes},
        )

    def finalize(self, semantic_package: Mapping[str, Any]) -> dict[str, Any]:
        require(
            semantic_package.get("materialization_run_id") == self.materialization_run_id
            and semantic_package.get("version") == self.package_version
            and semantic_package.get("supersedes") == self.supersedes,
            "MODEL10_RUN_IDENTITY_MISMATCH",
            "semantic package differs from staged run",
        )
        validate_successor_package(semantic_package)
        protected_hash = content_digest(semantic_package)
        package = {
            **dict(semantic_package),
            "protected_content_sha256": protected_hash,
            "protected_content_hash_semantics": "SHA-256 of canonical UTF-8 JSON before adding protected_content_sha256 and protected_content_hash_semantics.",
        }
        package_path = self.run_dir / "model10_wisconsin_cohort_identity_lineage_package.json"
        write_json_exclusive(package_path, package)
        nonce = new_nonce()
        nonce_path = self.run_dir / "model10_commitment_nonce.bin"
        with nonce_path.open("xb") as handle:
            handle.write(nonce)
            handle.flush()
            os.fsync(handle.fileno())
        commitment = freeze_commitment(file_sha256(package_path), nonce)
        commitment_evidence = {
            "artifact_id": COMMITMENT_ID,
            "version": COMMITMENT_VERSION,
            "protected_package_id": PACKAGE_ID,
            "protected_package_version": self.package_version,
            "domain": DOMAIN_SEPARATOR.decode("utf-8"),
            "commitment_sha256": commitment,
            "commitment_semantics": "SHA-256(domain separator NUL protected nonce NUL bytes of protected package file SHA-256).",
            "protected_package_digest_disclosed": False,
            "nonce_disclosed": False,
            "observation_content_disclosed": False,
            "supersedes": self.supersedes,
            "supersession_policy": "A correction creates a new patch package run nonce and commitment with explicit supersession.",
        }
        write_json_exclusive(self.run_dir / "model10_commitment_evidence.json", commitment_evidence)
        write_json_exclusive(
            self.run_dir / "READY.json",
            {
                "materialization_run_id": self.materialization_run_id,
                "state": "ready",
                "package_id": PACKAGE_ID,
                "package_version": self.package_version,
                "protected_content_sha256": protected_hash,
                "commitment_sha256": commitment,
            },
        )
        return {"protected_content_sha256": protected_hash, "commitment_sha256": commitment, "commitment_evidence": commitment_evidence}


def protected_materialization_is_ready(run_dir: Path) -> bool:
    return (run_dir / "READY.json").is_file()


@dataclass(frozen=True)
class MaterializationResult:
    materialization_run_id: str
    run_dir: Path
    protected_content_sha256: str
    commitment_sha256: str
    commitment_evidence: Mapping[str, Any]
    observation_count: int
    physical_location_count: int
    historically_linked_observation_count: int
    quarantined_observation_count: int
    eligible_observation_count: int
    source_authority_count: int


def execute_protected_materialization(
    *,
    repository_root: Path,
    resolver: ProtectedHandleResolver,
    materialization_run_id: str | None = None,
    package_version: str = PACKAGE_VERSION,
    supersedes: str | None = None,
) -> MaterializationResult:
    root = repository_root.resolve()
    request = resolver.materialization_request
    output = resolver.resolve(str(request["materialization_output_root_handle"]), "model10_output_root")
    staged = ProtectedSuccessorRun(output.path, root, materialization_run_id=materialization_run_id, package_version=package_version, supersedes=supersedes)

    model04_package = resolver.resolve(str(request["model04_package_handle"]), "model04_package")
    model04_verification = resolver.resolve(str(request["model04_verification_material_handle"]), "model04_verification_material")
    model04_commitment_path = root / MODEL04_DOCUMENT
    model04_commitment = _load_object(model04_commitment_path, "MODEL04_COMMITMENT_AUTHORITY_MISSING")
    require(
        model04_commitment.get("artifact_id") == MODEL04_COMMITMENT_ID
        and model04_commitment.get("version") == MODEL04_COMMITMENT_VERSION,
        "MODEL04_COMMITMENT_AUTHORITY_MISMATCH",
        "MODEL-04 commitment authority differs",
    )
    historical = load_model04_binding(model04_package.path, model04_verification.path, model04_commitment_path).package
    contract = _load_object(root / MODEL10_CONTRACT_DOCUMENT, "MODEL10_CONTRACT_AUTHORITY_MISSING")
    require(contract.get("artifact_id") == CONTRACT_ID and contract.get("version") == CONTRACT_VERSION, "MODEL10_CONTRACT_AUTHORITY_MISMATCH", "MODEL-10 contract identity differs")
    require((root / MODEL07_DOCUMENT).is_file() and (root / MODEL08_DOCUMENT).is_file(), "MODEL_HISTORICAL_AUTHORITY_MISSING", "MODEL-07 or MODEL-08 historical authority is absent")

    workbooks: list[ProjectedWorkbook] = []
    for source_identity in sorted(resolver.successor_source_authorities):
        authority = resolver.successor_source_authorities[source_identity]
        workbook = resolver.resolve(str(authority["workbook_handle"]), "wisconsin_successor_identity_workbook")
        workbooks.append(read_target_blind_projection(workbook.path, source_identity))
    semantic = build_successor_identity_package(
        workbooks,
        historical,
        materialization_run_id=staged.materialization_run_id,
        package_version=package_version,
        source_authorities=resolver.successor_source_authorities,
        contract_authority={"artifact_id": CONTRACT_ID, "version": CONTRACT_VERSION, "repository_file_sha256": file_sha256(root / MODEL10_CONTRACT_DOCUMENT)},
        registry_identity=resolver.registry_identity,
        supersedes=supersedes,
    )
    finalized = staged.finalize(semantic)
    aggregate = semantic["aggregate_conformance"]
    return MaterializationResult(
        staged.materialization_run_id,
        staged.run_dir,
        finalized["protected_content_sha256"],
        finalized["commitment_sha256"],
        finalized["commitment_evidence"],
        aggregate["observation_count"],
        aggregate["physical_location_count"],
        aggregate["historically_linked_observation_count"],
        aggregate["quarantined_observation_count"],
        aggregate["model09_development_eligible_observation_count"],
        len(workbooks),
    )


def build_disclosure_safe_result(result: MaterializationResult) -> dict[str, Any]:
    report = {
        "completion_state": "MODEL-10 protected successor package ready",
        "package_id": PACKAGE_ID,
        "version": PACKAGE_VERSION,
        "observation_count": result.observation_count,
        "physical_location_count": result.physical_location_count,
        "historically_linked_observation_count": result.historically_linked_observation_count,
        "quarantined_observation_count": result.quarantined_observation_count,
        "model09_development_eligible_observation_count": result.eligible_observation_count,
        "source_authority_count": result.source_authority_count,
        "cohort_vintages": [2024, 2025, 2026],
        "statewide_wisconsin_market_lineage_retained": True,
        "target_values_materialized": 0,
        "identity_target_blind": True,
        "protected_output_outside_git": True,
        "protected_details_disclosed": False,
    }
    serialized = json.dumps(report, sort_keys=True).lower()
    for forbidden in ("source_row", "seed_point", "physical_location_id", "nonce", "sha256", "latitude", "longitude", "workbook", "\\\\", ":\\"):
        require(forbidden not in serialized, "MODEL10_DISCLOSURE_SAFE_REPORT_VIOLATION", "protected detail entered MODEL-10 report")
    return report
