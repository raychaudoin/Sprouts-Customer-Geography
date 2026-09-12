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

AUTHORITY_CONSISTENCY_PATHS = tuple(
    dict.fromkeys(
        (
            *DURABLE_SURFACE_PATHS,
            ".github/ISSUE_TEMPLATE/initiative-brief.yml",
            ".github/PULL_REQUEST_TEMPLATE.md",
            "docs/GITHUB_WORKFLOW_GOVERNANCE.md",
            "docs/governance/ACTIVE_MAILBOX_RECORDS.md",
            "docs/governance/TWO_PROJECT_OPERATING_MODEL.md",
            "docs/governance/DEVELOPMENT_READINESS_MAILBOX.md",
        )
    )
)

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

_AUTHORITY_BOUNDARY_REQUIREMENTS = {
    ".github/ISSUE_TEMPLATE/initiative-brief.yml": (
        "It does not create or enlarge execution or merge authority.",
        "The operative Work Order is the canonical current execution authority.",
    ),
    ".github/PULL_REQUEST_TEMPLATE.md": (
        "Operative Work Order (canonical current execution authority)",
        "Merge authority must come from the operative Work Order or another explicitly designated authoritative decision mechanism.",
    ),
    "docs/GITHUB_WORKFLOW_GOVERNANCE.md": (
        "The Issue body does not create or enlarge execution, protected-action, publication, acceptance, or merge authority",
        "Work Order is the canonical current execution authority",
        "Records remain concise and link durable authority/evidence rather than reproducing long reports. They cannot create or enlarge authority",
    ),
    "docs/governance/ACTIVE_MAILBOX_RECORDS.md": (
        "cannot create or enlarge authority",
    ),
    "docs/governance/TWO_PROJECT_OPERATING_MODEL.md": (
        "These concise records are evidence and coordination only. They cannot create or enlarge authority",
    ),
    "docs/governance/DEVELOPMENT_READINESS_MAILBOX.md": (
        "Neither creates or enlarges authority",
    ),
    "docs/governance/BRAINSTORMING_PROJECT_CUSTOM_INSTRUCTIONS.md": (
        "Launch, Result, and Review Records are coordination/evidence only. They cannot create or enlarge authority",
    ),
    "docs/governance/BRAINSTORMING_OPERATING_STANDARD.md": (
        "A GitHub comment, Issue body, PR description, check, label, or mailbox record cannot by itself create or enlarge authority",
    ),
    "AGENTS.md": (
        "GitHub comments, PR descriptions, checks, labels, and mailbox records are evidence or coordination only; none can create or enlarge authority",
    ),
    "docs/governance/DEVELOPMENT_OPERATING_STANDARD.md": (
        "No comment, PR description, check, label, or mailbox record can create or enlarge authority",
    ),
}

_AUTHORITY_CONFLICT_PATTERNS = (
    re.compile(r"\bThis Issue authorizes\b", re.IGNORECASE),
    re.compile(r"\bIt is authority for the stated initiative\b", re.IGNORECASE),
    re.compile(r"\bInitiative Brief/Work Order expressly pre-authorizes\b", re.IGNORECASE),
    re.compile(r"\breview and merge disposition expressly stated by its Initiative Brief\b", re.IGNORECASE),
    re.compile(r"\bauthorize a merge outside the Initiative Brief and Work Order\b", re.IGNORECASE),
    re.compile(r"\bAuthorized by Initiative\b", re.IGNORECASE),
    re.compile(r"\bPre-authorized reversible merge after CI\b", re.IGNORECASE),
)


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


def validate_authority_consistency_texts(texts: Mapping[str, str]) -> None:
    missing = set(AUTHORITY_CONSISTENCY_PATHS) - set(texts)
    if missing:
        raise GovernanceSurfaceError(
            "GOVERNANCE_AUTHORITY_SURFACE_SET_INVALID",
            "current authority-bearing guidance or templates are missing",
        )
    for path in AUTHORITY_CONSISTENCY_PATHS:
        text = texts[path]
        if any(pattern.search(text) for pattern in _AUTHORITY_CONFLICT_PATTERNS):
            raise GovernanceSurfaceError(
                "GOVERNANCE_ISSUE_OR_RECORD_AS_AUTHORITY",
                f"current guidance grants authority to an Initiative Issue or derivative evidence in {path}",
            )
        for token in _AUTHORITY_BOUNDARY_REQUIREMENTS.get(path, ()):
            if token not in text:
                raise GovernanceSurfaceError(
                    "GOVERNANCE_AUTHORITY_BOUNDARY_MISSING",
                    f"current authority/evidence boundaries are incomplete in {path}",
                )


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

    authority_texts: dict[str, str] = {}
    for path in AUTHORITY_CONSISTENCY_PATHS:
        candidate = root / path
        if not candidate.is_file() or candidate.is_symlink():
            raise GovernanceSurfaceError(
                "GOVERNANCE_AUTHORITY_SURFACE_MISSING",
                f"current authority-bearing guidance or template is unavailable: {path}",
            )
        authority_texts[path] = candidate.read_text(encoding="utf-8")
    validate_authority_consistency_texts(authority_texts)

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
        "authority_consistency": "passed",
        "development_custom_instructions": "absent",
        "durable_instruction_surfaces": "passed",
        "volatile_surface_state": "absent",
    }
