"""Disclosure-safe PIPE acceptance evidence."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sprouts_customer_geography.constants import PIPE_SCHEMA_VERSION

from .canonical import content_id
from .errors import require


PROTECTED_REPORT_KEYS = {
    "anchor_tract_geoid",
    "anchor_latitude",
    "anchor_longitude",
    "tract_geoid",
    "distance_m",
    "household_opportunity",
    "prediction_candidate",
    "target_value",
    "target_rank",
}


def _find_protected_keys(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = str(key).strip().lower()
            if normalized in PROTECTED_REPORT_KEYS:
                found.add(normalized)
            found.update(_find_protected_keys(child))
    elif isinstance(value, (list, tuple)):
        for child in value:
            found.update(_find_protected_keys(child))
    return found


def build_disclosure_safe_report(
    *,
    run_state: str,
    mandatory_passed: bool,
    check_counts: Mapping[str, int],
    dependency_states: Mapping[str, str],
    source_checksum_states: Mapping[str, str],
    inventory_counts: Mapping[str, int | None],
    eligibility_summary: Mapping[str, int],
    commitment: str | None,
) -> dict[str, Any]:
    require(run_state in {"blocked", "incomplete", "frozen", "failed"}, "REPORT_RUN_STATE_INVALID", "invalid disclosure-safe run state")
    report = {
        "schema_version": PIPE_SCHEMA_VERSION,
        "run_state": run_state,
        "mandatory_passed": mandatory_passed,
        "check_counts": dict(check_counts),
        "dependency_states": dict(dependency_states),
        "source_checksum_states": dict(source_checksum_states),
        "inventory_counts": dict(inventory_counts),
        "eligibility_summary": dict(eligibility_summary),
        "target_blind_statement": "Sealed validation targets were not supplied to or used by the PIPE-01 freeze pipeline.",
        "disclosure_safe_commitment": commitment,
    }
    protected = sorted(_find_protected_keys(report))
    require(not protected, "PROTECTED_REPORT_FIELD_REJECTED", f"protected fields cannot enter disclosure-safe report: {protected}")
    return {**report, "report_id": content_id("conformance_report", report)}
