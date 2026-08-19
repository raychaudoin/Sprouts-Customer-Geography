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
}
PROTECTED_DIRECTORY_NAMES = {"protected", "protected-local", "confidential-local", "live-freeze"}


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
