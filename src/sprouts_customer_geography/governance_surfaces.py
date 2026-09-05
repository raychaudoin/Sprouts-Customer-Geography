"""Repository checks for the durable GOV-16 instruction and mailbox model."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Mapping


DURABLE_SURFACE_PATHS = (
    "docs/governance/BRAINSTORMING_PROJECT_CUSTOM_INSTRUCTIONS.md",
    "docs/governance/BRAINSTORMING_OPERATING_STANDARD.md",
    "AGENTS.md",
    "docs/governance/DEVELOPMENT_OPERATING_STANDARD.md",
)

RETIRED_DEVELOPMENT_CUSTOM_INSTRUCTIONS = "docs/governance/DEVELOPMENT_PROJECT_CUSTOM_INSTRUCTIONS.md"

_VOLATILE_PATTERNS = (
    ("GOVERNANCE_SURFACE_SHA_VOLATILE", re.compile(r"(?<![0-9a-f])[0-9a-f]{40}(?![0-9a-f])", re.IGNORECASE)),
    ("GOVERNANCE_SURFACE_PR_ISSUE_VOLATILE", re.compile(r"\b(?:PR|Issue)\s+#\d+\b", re.IGNORECASE)),
    ("GOVERNANCE_SURFACE_BRANCH_VOLATILE", re.compile(r"\btask/[a-z0-9][a-z0-9._/-]*", re.IGNORECASE)),
    ("GOVERNANCE_SURFACE_MODEL_INVENTORY_VOLATILE", re.compile(r"\bGPT-\d+(?:\.\d+)?(?:\s+[A-Za-z]+)?\b", re.IGNORECASE)),
    (
        "GOVERNANCE_SURFACE_TASK_STATE_VOLATILE",
        re.compile(r"\b(?:IN_PROGRESS|COMPLETED_AWAITING_ACCEPTANCE|ACCEPTED_CLOSED)\b"),
    ),
)

_SURFACE_REQUIREMENTS = {
    "docs/governance/BRAINSTORMING_PROJECT_CUSTOM_INSTRUCTIONS.md": (
        "Brainstorming Operating Standard",
        "full current set of models and reasoning options",
        "Once a PR exists, the PR conversation becomes the active candidate mailbox",
        "Development writes a concise Result Record",
        "Independent review writes a concise Review Record",
    ),
    "docs/governance/BRAINSTORMING_OPERATING_STANDARD.md": (
        "entire current Pro-eligible suite",
        "The active mailbox uses concise Launch, Result, and Review Records",
        "After implementation or remediation, Development writes a concise Result Record",
        "Independent review writes a concise Review Record",
    ),
    "AGENTS.md": (
        "constitutional executor contract",
        "Development Operating Standard",
        "the operative Work Order is canonical current execution authority",
        "Once a PR exists, write new candidate chronology only to the PR conversation",
        "Development must post a Result Record",
        "Independent review must post a Review Record",
    ),
    "docs/governance/DEVELOPMENT_OPERATING_STANDARD.md": (
        "AGENTS.md` is the constitutional executor contract",
        "full-suite",
        "Once a PR exists, the PR conversation is the active candidate mailbox",
        "write a concise Result Record to the active mailbox",
        "Post a concise Review Record to the active PR mailbox",
    ),
}

_REPOSITORY_REQUIREMENTS = {
    "docs/governance/ACTIVE_MAILBOX_RECORDS.md": (
        "Development Readiness Mailbox",
        "Write new candidate chronology only to the PR",
        "Record type: `LAUNCH`",
        "Record type: `RESULT`",
        "Record type: `REVIEW`",
        "cannot create or enlarge authority",
    ),
    "docs/governance/TWO_PROJECT_OPERATING_MODEL.md": (
        "Four durable instruction surfaces",
        "The Development Project has no ChatGPT Project Custom Instructions",
        "new candidate chronology is not mirrored to the Issue",
        "full-suite comparison",
    ),
    "docs/governance/DEVELOPMENT_READINESS_MAILBOX.md": (
        "This readiness surface is separate from the [active Initiative/PR mailbox]",
        "The active mailbox is evidence/coordination",
    ),
    "docs/GITHUB_WORKFLOW_GOVERNANCE.md": (
        "active Issue/PR mailbox",
        "Once a PR exists, the PR conversation becomes the active candidate mailbox",
        "Development identifies the action performed, exact resulting PR/head",
        "Records remain concise",
    ),
}


class GovernanceSurfaceError(ValueError):
    """Closed-code conformance failure for durable governance surfaces."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"{code}: {message}")


def validate_durable_surface_texts(texts: Mapping[str, str]) -> None:
    expected = set(DURABLE_SURFACE_PATHS)
    if set(texts) != expected:
        raise GovernanceSurfaceError(
            "GOVERNANCE_SURFACE_SET_INVALID",
            "the four durable instruction surfaces are missing or ambiguous",
        )
    for path, text in texts.items():
        for token in _SURFACE_REQUIREMENTS[path]:
            if token not in text:
                raise GovernanceSurfaceError(
                    "GOVERNANCE_SURFACE_SEMANTICS_MISSING",
                    f"required governance semantics are missing from {path}",
                )
        for code, pattern in _VOLATILE_PATTERNS:
            if pattern.search(text):
                raise GovernanceSurfaceError(code, f"volatile state is present in {path}")


def validate_governance_surfaces(repository: Path) -> dict[str, str]:
    root = Path(repository).resolve()
    texts: dict[str, str] = {}
    for path in DURABLE_SURFACE_PATHS:
        candidate = root / path
        if not candidate.is_file() or candidate.is_symlink():
            raise GovernanceSurfaceError(
                "GOVERNANCE_SURFACE_MISSING",
                f"required durable instruction surface is unavailable: {path}",
            )
        texts[path] = candidate.read_text(encoding="utf-8")
    validate_durable_surface_texts(texts)

    retired = root / RETIRED_DEVELOPMENT_CUSTOM_INSTRUCTIONS
    if retired.exists():
        raise GovernanceSurfaceError(
            "GOVERNANCE_DEVELOPMENT_CUSTOM_INSTRUCTIONS_ACTIVE",
            "Development Project Custom Instructions must not be an active surface",
        )

    for path, tokens in _REPOSITORY_REQUIREMENTS.items():
        candidate = root / path
        if not candidate.is_file() or candidate.is_symlink():
            raise GovernanceSurfaceError(
                "GOVERNANCE_SUPPORTING_GUIDANCE_MISSING",
                f"required governance guidance is unavailable: {path}",
            )
        text = candidate.read_text(encoding="utf-8")
        for token in tokens:
            if token not in text:
                raise GovernanceSurfaceError(
                    "GOVERNANCE_SUPPORTING_SEMANTICS_MISSING",
                    f"required governance semantics are missing from {path}",
                )

    readme = (root / "README.md").read_text(encoding="utf-8")
    if RETIRED_DEVELOPMENT_CUSTOM_INSTRUCTIONS in readme:
        raise GovernanceSurfaceError(
            "GOVERNANCE_RETIRED_SURFACE_REFERENCED",
            "README still presents the retired Development Custom Instructions surface",
        )

    return {
        "active_mailbox_records": "passed",
        "development_custom_instructions": "absent",
        "durable_instruction_surfaces": "passed",
        "volatile_surface_state": "absent",
    }
