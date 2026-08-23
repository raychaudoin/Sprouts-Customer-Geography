"""PIPE-03 target-blind cohort reconciliation and protected finalization."""

from __future__ import annotations

import copy
import json
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from sprouts_customer_geography.model06 import (
    COMMITMENT_ID,
    COMMITMENT_VERSION,
    PACKAGE_ID as MODEL04_PACKAGE_ID,
    PACKAGE_VERSION as MODEL04_PACKAGE_VERSION,
    PREREGISTRATION_ID,
    PREREGISTRATION_VERSION,
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
from sprouts_customer_geography.pipe01.orchestration import (
    Model04Binding,
    load_model04_binding,
    load_repository_authorities,
)
from sprouts_customer_geography.pipe02.resolver import _is_within

from .resolver import ProtectedHandleResolver
from .xlsx_projection import (
    DevelopmentTargetAccessAudit,
    WISCONSIN_MARKETS,
    WisconsinDevelopmentProjectionPolicy,
    project_authorized_isolated_sales,
)


BINDING_PACKAGE_ID = "PIPE03_WISCONSIN_DEVELOPMENT_TARGET_ACCESS_BINDING_V1"
BINDING_PACKAGE_VERSION = "1.0.0"
BINDING_SCHEMA_VERSION = "pipe03-wisconsin-development-target-access-binding-v1"
PROJECTION_ID = WisconsinDevelopmentProjectionPolicy.PROJECTION_ID
PROJECTION_VERSION = WisconsinDevelopmentProjectionPolicy.VERSION
EXPECTED_MODEL04_COMMITMENT = (
    "b5db257f31a790d3ca72ed784d42d7db2e878c8fa6723b869f6c14234153bdfb"
)
EXPECTED_MODEL05_SHA256 = (
    "a73b1c165e4ef26b3d0ee984af7cf8ca3ae917aeda003cb62dbb6e2ef4d28620"
)
MODEL08_DOCUMENT = "docs/work_orders/MODEL_08_WISCONSIN_EVIDENCE_EXPANSION_STRATEGY.md"


def _load_json_object(path: Path, code: str) -> dict[str, Any]:
    require(path.is_file(), code, "required protected JSON artifact is absent")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        from sprouts_customer_geography.pipe01.errors import ConformanceError

        raise ConformanceError(code, "required protected JSON artifact is unreadable") from exc
    require(
        isinstance(value, dict),
        code,
        "required protected JSON artifact must be an object",
    )
    return value


def derive_eligible_wisconsin_cohort(
    model04: Model04Binding,
) -> tuple[list[dict[str, Any]], int, int]:
    """Establish membership exclusively from accepted target-blind MODEL-04."""
    cohort: list[dict[str, Any]] = []
    quarantined_count = 0
    non_wisconsin_count = 0
    seen_observations: set[tuple[str, int]] = set()
    seen_source_rows: set[tuple[str, str, int]] = set()
    for record in model04.package["records"]:
        market = str(record.get("market", "")).strip().lower()
        if market not in WISCONSIN_MARKETS:
            non_wisconsin_count += 1
            continue
        if bool(record.get("quarantined")) or record.get("identity_state") == "AMBIGUOUS_IDENTITY":
            require(
                record.get("quarantined") is True
                and record.get("identity_state") == "AMBIGUOUS_IDENTITY"
                and record.get("evidence_role") == "AMBIGUOUS_QUARANTINE",
                "AMBIGUOUS_LINEAGE_INVALID",
                "ambiguous Wisconsin identity must remain quarantined",
            )
            quarantined_count += 1
            continue
        required_text = {
            "physical_location_id": record.get("physical_location_id"),
            "source_workbook_identity": record.get("source_workbook_identity"),
            "source_sheet": record.get("source_sheet"),
            "lineage_key": record.get("source_seed_point_id"),
            "identity_state": record.get("identity_state"),
            "evidence_role": record.get("evidence_role"),
            "target_view_state": record.get("target_view_state"),
        }
        require(
            all(isinstance(value, str) and bool(value) for value in required_text.values()),
            "WISCONSIN_LINEAGE_INCOMPLETE",
            "eligible Wisconsin evidence has incomplete identity or lineage",
        )
        source_row = record.get("source_row")
        vintage = record.get("vintage_year")
        require(
            isinstance(source_row, int)
            and source_row >= 2
            and isinstance(vintage, int),
            "WISCONSIN_LINEAGE_INCOMPLETE",
            "eligible Wisconsin evidence has invalid source-row or vintage identity",
        )
        require(
            record.get("target_view_state") in {"SEALED", "DEVELOPMENT_CONSUMED"},
            "TARGET_VIEW_STATE_INVALID",
            "historical target-view state is outside the accepted progression",
        )
        observation_key = (str(record["source_seed_point_id"]), vintage)
        source_key = (
            str(record["source_workbook_identity"]),
            str(record["source_sheet"]),
            source_row,
        )
        require(
            observation_key not in seen_observations,
            "WISCONSIN_OBSERVATION_DUPLICATE",
            "eligible Wisconsin lineage/vintage identity is duplicate",
        )
        require(
            source_key not in seen_source_rows,
            "WISCONSIN_SOURCE_ROW_DUPLICATE",
            "eligible Wisconsin source-row identity is duplicate",
        )
        seen_observations.add(observation_key)
        seen_source_rows.add(source_key)
        cohort.append(
            {
                "physical_location_id": str(record["physical_location_id"]),
                "source_workbook_identity": str(record["source_workbook_identity"]),
                "source_sheet": str(record["source_sheet"]),
                "source_row": source_row,
                "lineage_key": str(record["source_seed_point_id"]),
                "forecast_vintage": vintage,
                "market": market,
                "identity_state": str(record["identity_state"]),
                "evidence_role": str(record["evidence_role"]),
                "target_view_state": str(record["target_view_state"]),
            }
        )
    require(
        bool(cohort),
        "WISCONSIN_COHORT_EMPTY",
        "accepted MODEL-04 has no eligible Wisconsin observations",
    )
    return cohort, quarantined_count, non_wisconsin_count


def _assert_default_deny_package(value: Any) -> None:
    forbidden_keys = {
        "impacted_sales",
        "target_value",
        "forecast_value",
        "prediction_value",
        "coordinates",
        "latitude",
        "longitude",
    }
    if isinstance(value, Mapping):
        for key, child in value.items():
            require(
                str(key).strip().lower() not in forbidden_keys,
                "PROTECTED_FIELD_IN_BINDING_REJECTED",
                "a denied target, prediction, or coordinate field entered PIPE-03",
            )
            _assert_default_deny_package(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            _assert_default_deny_package(child)


def _validate_semantic_package(package: Mapping[str, Any]) -> None:
    required = {
        "$schema",
        "package_id",
        "version",
        "binding_run_id",
        "state",
        "model04_authority",
        "model05_authority",
        "model08_authority",
        "target_source_authorities",
        "eligible_wisconsin_cohort",
        "minimum_target_projection",
        "consumption_semantics",
        "protected_handle_registry_identity",
        "finalization",
        "supersedes",
        "supersession_policy",
    }
    require(
        set(package) == required,
        "BINDING_PACKAGE_SCHEMA_INVALID",
        "protected binding package fields differ from the exact PIPE-03 contract",
    )
    require(
        package.get("$schema") == BINDING_SCHEMA_VERSION
        and package.get("package_id") == BINDING_PACKAGE_ID
        and bool(re.fullmatch(r"1\.0\.[0-9]+", str(package.get("version", ""))))
        and package.get("state") == "ready",
        "BINDING_IDENTITY_MISMATCH",
        "binding schema, package identity, or state differs",
    )
    model04 = package.get("model04_authority")
    require(
        isinstance(model04, Mapping)
        and model04.get("package_id") == MODEL04_PACKAGE_ID
        and model04.get("package_version") == MODEL04_PACKAGE_VERSION
        and model04.get("commitment_sha256") == EXPECTED_MODEL04_COMMITMENT
        and model04.get("commitment_reconciled") is True,
        "MODEL04_BINDING_IDENTITY_MISMATCH",
        "binding does not prove the exact accepted MODEL-04 authority",
    )
    model05 = package.get("model05_authority")
    require(
        isinstance(model05, Mapping)
        and model05.get("preregistration_id") == PREREGISTRATION_ID
        and model05.get("version") == PREREGISTRATION_VERSION
        and model05.get("content_sha256") == EXPECTED_MODEL05_SHA256,
        "MODEL05_BINDING_IDENTITY_MISMATCH",
        "binding does not retain exact accepted MODEL-05 consumption authority",
    )
    model08 = package.get("model08_authority")
    require(
        isinstance(model08, Mapping)
        and model08.get("strategy_document") == MODEL08_DOCUMENT
        and model08.get("wisconsin_first") is True
        and model08.get("target_blind_identity") is True,
        "MODEL08_BINDING_IDENTITY_MISMATCH",
        "binding does not retain accepted MODEL-08 Wisconsin-first authority",
    )
    cohort = package.get("eligible_wisconsin_cohort")
    require(
        isinstance(cohort, list) and bool(cohort),
        "WISCONSIN_COHORT_EMPTY",
        "binding contains no eligible Wisconsin cohort",
    )
    cohort_keys: set[tuple[str, int]] = set()
    source_identities: set[str] = set()
    for row in cohort:
        require(
            isinstance(row, Mapping)
            and row.get("market") in WISCONSIN_MARKETS
            and row.get("identity_state") != "AMBIGUOUS_IDENTITY",
            "WISCONSIN_COHORT_POLICY_MISMATCH",
            "cohort includes denied market or ambiguous identity",
        )
        key = (str(row.get("lineage_key")), int(row.get("forecast_vintage")))
        require(
            key not in cohort_keys,
            "WISCONSIN_OBSERVATION_DUPLICATE",
            "cohort lineage/vintage identity is duplicate",
        )
        cohort_keys.add(key)
        source_identities.add(str(row.get("source_workbook_identity")))
    sources = package.get("target_source_authorities")
    require(
        isinstance(sources, list) and bool(sources),
        "TARGET_SOURCE_AUTHORITIES_UNRESOLVED",
        "binding contains no exact target-source authority",
    )
    bound_source_identities = {
        str(source.get("source_workbook_identity"))
        for source in sources
        if isinstance(source, Mapping)
    }
    require(
        len(sources) == len(bound_source_identities)
        and all(
            isinstance(source, Mapping)
            and bool(source.get("authority_id"))
            and bool(source.get("provenance_class"))
            and bool(source.get("workbook_handle"))
            for source in sources
        )
        and
        bound_source_identities == source_identities
        and all(source.get("whole_workbook_hash_computed") is False for source in sources),
        "TARGET_SOURCE_COMPLETENESS_FAILED",
        "exact target sources do not cover the cohort and only the cohort",
    )
    projection = package.get("minimum_target_projection")
    require(
        isinstance(projection, Mapping)
        and projection.get("projection_id") == PROJECTION_ID
        and projection.get("version") == PROJECTION_VERSION
        and projection.get("default_deny") is True
        and set(projection.get("allowed_fields", []))
        == WisconsinDevelopmentProjectionPolicy.ALLOWED_FIELDS,
        "TARGET_PROJECTION_IDENTITY_MISMATCH",
        "minimum target projection identity or allowlist differs",
    )
    rows = projection.get("rows")
    require(
        isinstance(rows, list) and len(rows) == len(cohort),
        "TARGET_PROJECTION_COMPLETENESS_FAILED",
        "target projection does not cover the cohort exactly",
    )
    cohort_identity_by_key = {
        (str(row["lineage_key"]), int(row["forecast_vintage"])):
        str(row["physical_location_id"])
        for row in cohort
    }
    projection_keys: set[tuple[str, int]] = set()
    for row in rows:
        require(
            isinstance(row, Mapping)
            and isinstance(row.get("isolated_sales"), str)
            and bool(row.get("isolated_sales")),
            "TARGET_PROJECTION_ROW_INVALID",
            "target projection row is incomplete",
        )
        key = (str(row.get("lineage_key")), int(row.get("forecast_vintage")))
        require(
            key not in projection_keys
            and cohort_identity_by_key.get(key) == str(row.get("physical_location_id")),
            "TARGET_PHYSICAL_IDENTITY_MISMATCH",
            "target content cannot duplicate or change cohort physical-location identity",
        )
        projection_keys.add(key)
    require(
        projection_keys == cohort_keys,
        "TARGET_PROJECTION_COMPLETENESS_FAILED",
        "target rows differ from target-blind cohort identity",
    )
    audit = projection.get("target_access_audit")
    require(
        isinstance(audit, Mapping)
        and audit.get("authorized_row_count") == len(cohort)
        and audit.get("isolated_sales_materialized") is True
        and audit.get("impacted_sales_decode_calls") == 0
        and audit.get("non_wisconsin_target_decode_calls") == 0
        and audit.get("unrelated_target_values_materialized") is False,
        "TARGET_ACCESS_AUDIT_FAILED",
        "target access exceeded the exact authorized projection",
    )
    consumption = package.get("consumption_semantics")
    require(
        isinstance(consumption, Mapping)
        and consumption.get("binding_marks_development_consumed") is False
        and consumption.get("prior_evidence_metadata_preserved") is True
        and consumption.get("analytical_influence_triggers_model09_consumption") is True,
        "EVIDENCE_CONSUMPTION_SEMANTICS_INVALID",
        "binding changed accepted evidence-role or consumption semantics",
    )
    finalization = package.get("finalization")
    require(
        isinstance(finalization, Mapping)
        and finalization.get("cohort_established_before_target_projection") is True
        and finalization.get("mandatory_reconciliations_passed") is True
        and finalization.get("ready_marker_written_last") is True,
        "BINDING_FINALIZATION_CONFORMANCE_FAILED",
        "binding finalization assertions are incomplete",
    )
    _assert_default_deny_package(package)


class ProtectedDevelopmentBindingRun:
    """One immutable PIPE-03 protected-local binding run."""

    def __init__(
        self,
        protected_root: Path,
        repository_root: Path,
        *,
        binding_run_id: str | None = None,
        package_version: str = BINDING_PACKAGE_VERSION,
        supersedes: str | None = None,
    ):
        self.protected_root = protected_root.resolve()
        self.repository_root = repository_root.resolve()
        require(
            not _is_within(self.protected_root, self.repository_root),
            "PROTECTED_ROOT_INSIDE_REPOSITORY",
            "PIPE-03 output root must remain outside Git",
        )
        self.binding_run_id = binding_run_id or f"p3bind-{uuid.uuid4()}"
        require(
            self.binding_run_id.startswith("p3bind-")
            and all(character.isalnum() or character in "-_" for character in self.binding_run_id),
            "BINDING_RUN_ID_INVALID",
            "binding run ID must be opaque and filesystem-safe",
        )
        require(bool(package_version), "BINDING_VERSION_INVALID", "package version is required")
        require(
            bool(re.fullmatch(r"1\.0\.[0-9]+", package_version)),
            "BINDING_VERSION_INVALID",
            "PIPE-03 package version must remain within the 1.0 patch line",
        )
        if supersedes is not None:
            require(
                package_version != BINDING_PACKAGE_VERSION,
                "BINDING_SUPERSESSION_VERSION_REQUIRED",
                "a correction must use a new package version",
            )
            require(
                supersedes.startswith("p3bind-"),
                "BINDING_SUPERSESSION_INVALID",
                "supersession must name an earlier PIPE-03 run",
            )
        self.package_version = package_version
        self.supersedes = supersedes
        self.run_dir = self.protected_root / "pipe03-bindings" / self.binding_run_id
        require(
            not self.run_dir.exists(),
            "BINDING_ALREADY_EXISTS",
            "never overwrite an incomplete or finalized protected binding",
        )
        self.run_dir.mkdir(parents=True, exist_ok=False)
        write_json_exclusive(
            self.run_dir / "binding_state.json",
            {
                "binding_run_id": self.binding_run_id,
                "state": "incomplete",
                "finalization_state": "not_started",
                "package_version": package_version,
                "supersedes": supersedes,
            },
        )

    def finalize(self, semantic_package: Mapping[str, Any]) -> dict[str, Any]:
        require(
            semantic_package.get("version") == self.package_version
            and semantic_package.get("package_id") == BINDING_PACKAGE_ID
            and semantic_package.get("binding_run_id") == self.binding_run_id
            and semantic_package.get("supersedes") == self.supersedes,
            "BINDING_IDENTITY_MISMATCH",
            "staged package identity/version/supersession differs",
        )
        _validate_semantic_package(semantic_package)
        semantic = copy.deepcopy(dict(semantic_package))
        protected_hash = content_digest(semantic)
        stable_identity = f"pipe03-binding:sha256:{protected_hash}"
        package = {
            **semantic,
            "protected_content_sha256": protected_hash,
            "stable_binding_identity": stable_identity,
            "protected_content_hash_semantics": (
                "SHA-256 of canonical UTF-8 JSON before adding protected_content_sha256, "
                "stable_binding_identity, and protected_content_hash_semantics."
            ),
        }
        package_path = self.run_dir / "pipe03_wisconsin_development_target_access_binding.json"
        write_json_exclusive(package_path, package)
        manifest = {
            "binding_run_id": self.binding_run_id,
            "package_id": BINDING_PACKAGE_ID,
            "package_version": self.package_version,
            "binding_schema_version": BINDING_SCHEMA_VERSION,
            "state": "ready",
            "finalization_state": "complete",
            "supersedes": self.supersedes,
            "protected_content_sha256": protected_hash,
            "stable_binding_identity": stable_identity,
            "package_file_sha256": file_sha256(package_path),
        }
        write_json_exclusive(self.run_dir / "binding_manifest.json", manifest)
        nonce = new_nonce()
        commitment = freeze_commitment(content_digest(manifest), nonce)
        with (self.run_dir / "binding_nonce.bin").open("xb") as handle:
            handle.write(nonce)
            handle.flush()
            os.fsync(handle.fileno())
        write_json_exclusive(
            self.run_dir / "commitment_evidence.json",
            {
                "domain": DOMAIN_SEPARATOR.decode("utf-8"),
                "commitment_sha256": commitment,
            },
        )
        # The usable marker is deliberately the final write.
        write_json_exclusive(
            self.run_dir / "READY.json",
            {
                "binding_run_id": self.binding_run_id,
                "package_id": BINDING_PACKAGE_ID,
                "package_version": self.package_version,
                "state": "ready",
                "finalization_state": "complete",
                "protected_content_sha256": protected_hash,
                "stable_binding_identity": stable_identity,
                "commitment_sha256": commitment,
            },
        )
        return {
            "protected_content_sha256": protected_hash,
            "stable_binding_identity": stable_identity,
            "commitment_sha256": commitment,
        }


def protected_binding_is_ready(run_dir: Path) -> bool:
    return (run_dir / "READY.json").is_file()


@dataclass(frozen=True)
class BindingResult:
    binding_run_id: str
    protected_content_sha256: str
    stable_binding_identity: str
    commitment_sha256: str
    run_dir: Path
    eligible_observation_count: int
    quarantined_observation_count: int
    source_authority_count: int
    target_access_audit: DevelopmentTargetAccessAudit


def execute_protected_binding(
    *,
    repository_root: Path,
    resolver: ProtectedHandleResolver,
    binding_run_id: str | None = None,
    package_version: str = BINDING_PACKAGE_VERSION,
    supersedes: str | None = None,
) -> BindingResult:
    """Build one binding after target-blind cohort identity is complete."""
    root = repository_root.resolve()
    request = resolver.binding_request
    output = resolver.resolve(str(request["binding_output_root_handle"]), "pipe03_output_root")
    staged = ProtectedDevelopmentBindingRun(
        output.path,
        root,
        binding_run_id=binding_run_id,
        package_version=package_version,
        supersedes=supersedes,
    )

    model04_package = resolver.resolve(str(request["model04_package_handle"]), "model04_package")
    model04_verification = resolver.resolve(
        str(request["model04_verification_material_handle"]),
        "model04_verification_material",
    )
    commitment_path = root / "config/model/model04_validation_identity_role_anchor_commitment.json"
    commitment = _load_json_object(commitment_path, "MODEL04_COMMITMENT_AUTHORITY_MISSING")
    require(
        commitment.get("artifact_id") == COMMITMENT_ID
        and commitment.get("version") == COMMITMENT_VERSION
        and commitment.get("commitment_sha256") == EXPECTED_MODEL04_COMMITMENT,
        "MODEL04_COMMITMENT_AUTHORITY_MISMATCH",
        "repository MODEL-04 commitment differs from accepted authority",
    )
    model04 = load_model04_binding(
        model04_package.path,
        model04_verification.path,
        commitment_path,
    )
    cohort, quarantined_count, _non_wisconsin_count = derive_eligible_wisconsin_cohort(model04)

    authorities = load_repository_authorities(root)
    require(
        authorities.preregistration["artifact_id"] == PREREGISTRATION_ID
        and authorities.preregistration["version"] == PREREGISTRATION_VERSION
        and authorities.preregistration["content_sha256"] == EXPECTED_MODEL05_SHA256,
        "MODEL05_AUTHORITY_MISMATCH",
        "MODEL-05 preregistration identity/version/hash differs",
    )
    model08_path = root / MODEL08_DOCUMENT
    require(
        model08_path.is_file(),
        "MODEL08_AUTHORITY_MISSING",
        "accepted MODEL-08 strategy record is absent",
    )

    requested_by_source: dict[str, list[Mapping[str, Any]]] = {}
    for row in cohort:
        requested_by_source.setdefault(str(row["source_workbook_identity"]), []).append(row)
    require(
        set(requested_by_source) == set(resolver.target_source_authorities),
        "TARGET_SOURCE_COMPLETENESS_FAILED",
        "exact target-source authorities must cover the cohort and only the cohort",
    )

    projected_rows: list[dict[str, Any]] = []
    bound_sources: list[dict[str, Any]] = []
    combined_audit = DevelopmentTargetAccessAudit()
    for workbook_identity in sorted(requested_by_source):
        source = resolver.target_source_authorities[workbook_identity]
        workbook = resolver.resolve(
            str(source["workbook_handle"]),
            "wisconsin_development_target_workbook",
        )
        policy = WisconsinDevelopmentProjectionPolicy(
            source["projection"],
            workbook.handle,
            workbook_identity,
        )
        values, audit = project_authorized_isolated_sales(
            workbook.path,
            policy,
            requested_by_source[workbook_identity],
        )
        projected_rows.extend(values)
        for field in combined_audit.__dataclass_fields__:
            setattr(combined_audit, field, getattr(combined_audit, field) + getattr(audit, field))
        bound_sources.append(
            {
                "authority_id": source["authority_id"],
                "provenance_class": source["provenance_class"],
                "source_workbook_identity": workbook_identity,
                "workbook_handle": workbook.handle,
                "whole_workbook_hash_computed": False,
                "sheet_name": policy.sheet_name,
                "projection_id": policy.PROJECTION_ID,
                "projection_version": policy.VERSION,
            }
        )

    denied_scope = [
        "Impacted Sales",
        "Michigan",
        "Detroit",
        "every non-Wisconsin target",
        "ambiguous or unresolved lineage",
        "unrelated workbook fields",
        "unrelated target rows",
        "exploratory access outside MODEL-09",
        "broad workbook previews",
        "broad filesystem discovery",
    ]
    semantic_package = {
        "$schema": BINDING_SCHEMA_VERSION,
        "package_id": BINDING_PACKAGE_ID,
        "version": package_version,
        "binding_run_id": staged.binding_run_id,
        "state": "ready",
        "model04_authority": {
            "package_id": MODEL04_PACKAGE_ID,
            "package_version": MODEL04_PACKAGE_VERSION,
            "package_handle": model04_package.handle,
            "verification_material_handle": model04_verification.handle,
            "commitment_artifact_id": COMMITMENT_ID,
            "commitment_artifact_version": COMMITMENT_VERSION,
            "commitment_sha256": EXPECTED_MODEL04_COMMITMENT,
            "commitment_reconciled": True,
            "cohort_selection_target_blind": True,
        },
        "model05_authority": {
            "preregistration_id": PREREGISTRATION_ID,
            "version": PREREGISTRATION_VERSION,
            "content_sha256": EXPECTED_MODEL05_SHA256,
            "consumption_rule_preserved": True,
        },
        "model08_authority": {
            "strategy_document": MODEL08_DOCUMENT,
            "repository_file_sha256": file_sha256(model08_path),
            "wisconsin_first": True,
            "target_blind_identity": True,
            "ambiguous_identity_quarantined": True,
        },
        "target_source_authorities": bound_sources,
        "eligible_wisconsin_cohort": cohort,
        "minimum_target_projection": {
            "projection_id": PROJECTION_ID,
            "version": PROJECTION_VERSION,
            "default_deny": True,
            "allowed_fields": sorted(WisconsinDevelopmentProjectionPolicy.ALLOWED_FIELDS),
            "denied_scope": denied_scope,
            "rows": projected_rows,
            "target_access_audit": combined_audit.disclosure_safe(),
        },
        "consumption_semantics": {
            "binding_marks_development_consumed": False,
            "prior_evidence_metadata_preserved": True,
            "analytical_influence_triggers_model09_consumption": True,
            "consumed_evidence_cannot_regain_untouched_validation_status": True,
        },
        "protected_handle_registry_identity": resolver.registry_identity,
        "finalization": {
            "cohort_established_before_target_projection": True,
            "mandatory_reconciliations_passed": True,
            "impacted_sales_accessed": False,
            "non_wisconsin_targets_accessed": False,
            "ready_marker_written_last": True,
        },
        "supersedes": supersedes,
        "supersession_policy": (
            "Never overwrite a PIPE-03 binding. A correction requires a new patch "
            "version, opaque run ID, and explicit supersedes lineage."
        ),
    }
    finalized = staged.finalize(semantic_package)
    return BindingResult(
        staged.binding_run_id,
        finalized["protected_content_sha256"],
        finalized["stable_binding_identity"],
        finalized["commitment_sha256"],
        staged.run_dir,
        len(cohort),
        quarantined_count,
        len(bound_sources),
        combined_audit,
    )


def build_disclosure_safe_result(result: BindingResult) -> dict[str, Any]:
    report = {
        "completion_state": "PIPE-03 protected binding ready",
        "package_id": BINDING_PACKAGE_ID,
        "version": BINDING_PACKAGE_VERSION,
        "eligible_wisconsin_observation_count": result.eligible_observation_count,
        "quarantined_observation_count": result.quarantined_observation_count,
        "target_source_authority_count": result.source_authority_count,
        "isolated_sales_values_materialized": result.target_access_audit.authorized_isolated_sales_decode_calls,
        "impacted_sales_values_materialized": 0,
        "non_wisconsin_target_values_materialized": 0,
        "cohort_selection_target_blind": True,
        "binding_marks_development_consumed": False,
        "protected_output_outside_git": True,
        "protected_details_disclosed": False,
    }
    serialized = json.dumps(report, sort_keys=True).lower()
    for forbidden in (
        "source_row",
        "cell_address",
        "physical_location_id",
        "nonce",
        "commitment_sha256",
        "protected_content_sha256",
        "stable_binding_identity",
        "latitude",
        "longitude",
        "\\\\",
        ":\\",
    ):
        require(
            forbidden not in serialized,
            "DISCLOSURE_SAFE_REPORT_VIOLATION",
            "protected detail entered the disclosure-safe PIPE-03 report",
        )
    return report
