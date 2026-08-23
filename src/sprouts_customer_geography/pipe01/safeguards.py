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
    "materialization_state.json",
    "READY.json",
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
}


def assert_no_protected_tracked_paths(paths: Iterable[str]) -> None:
    violations = []
    for raw in paths:
        path = Path(raw)
        lowered_parts = {part.lower() for part in path.parts}
        if path.name.lower() in PROTECTED_ARTIFACT_FILENAMES or lowered_parts & PROTECTED_DIRECTORY_NAMES:
            # Schema definitions and synthetic fixtures are explicitly repository-safe.
            if "schemas" not in lowered_parts and "synthetic" not in lowered_parts:
                violations.append(raw)
    if violations:
        raise ConformanceError("PROTECTED_TRACKED_PATH_REJECTED", f"designated protected artifact path(s): {sorted(violations)}")
