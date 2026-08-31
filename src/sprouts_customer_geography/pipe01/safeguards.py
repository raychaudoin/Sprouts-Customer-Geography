"""Defense-in-depth checks against committing protected PIPE-01 derivatives."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .errors import ConformanceError


PROTECTED_ARTIFACT_FILENAMES = {
    "context_membership.json",
    "baseline_prediction.json",
    "household_opportunity.json",
    "freeze_manifest.json",
    "freeze_nonce.bin",
    "model04_identity_role_anchor_package.json",
    "commitment_nonce.bin",
    "pipe02_protected_validation_access_binding.json",
    "pipe03_wisconsin_development_target_access_binding.json",
    "binding_nonce.bin",
    "binding_manifest.json",
    "model10_wisconsin_cohort_identity_lineage_package.json",
    "model10_commitment_nonce.bin",
    "model10_commitment_evidence.json",
    "pipe04_model10_wisconsin_development_binding.json",
    "pipe05_model12_michigan_isolated_sales_binding.json",
    "materialization_state.json",
    "model12_michigan_physical_location_identity_package.json",
    "model12_michigan_public_feature_package.json",
    "model12_michigan_frozen_scoring_package.json",
    "model12_michigan_field_scoring_package.json",
    "commitment_evidence.json",
    "READY.json",
    "scg_project_profile.json",
    "evidence.sqlite3",
}
PROTECTED_DIRECTORY_NAMES = {
    "protected",
    "protected-local",
    "confidential-local",
    "live-freeze",
    "protected-bindings",
    "pipe03-bindings",
    ".pipe02-local",
    ".pipe03-local",
    "model10-materializations",
    ".model10-local",
    "pipe04-bindings",
    ".pipe04-local",
    "pipe05-bindings",
    ".pipe05-local",
    "model12-materializations",
    "model12-field-scorer-runs",
    ".model12-local",
    "projectstate",
    "sproutscustomergeography",
}

SAFE_PROTECTED_PATHS = {
    "schemas/pipe01/context_membership.json",
    "tests/fixtures/synthetic/context_membership.json",
}


def assert_no_protected_tracked_paths(paths: Iterable[str]) -> None:
    violations = []
    for raw in paths:
        path = Path(raw)
        lowered_parts = {part.lower() for part in path.parts}
        normalized = path.as_posix().lower()
        protected_names = {name.lower() for name in PROTECTED_ARTIFACT_FILENAMES}
        protected_state_file = path.name.lower().startswith(("evidence.sqlite3", "scg_project_profile.json"))
        if (
            path.name.lower() in protected_names
            or protected_state_file
            or lowered_parts & PROTECTED_DIRECTORY_NAMES
        ) and normalized not in SAFE_PROTECTED_PATHS:
            violations.append(raw)
    if violations:
        raise ConformanceError(
            "PROTECTED_TRACKED_PATH_REJECTED",
            f"{len(violations)} designated protected artifact path(s) were detected",
        )
