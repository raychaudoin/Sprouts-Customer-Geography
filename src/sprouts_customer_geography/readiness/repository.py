"""Sanitized Git worktree probe for the Development Readiness Mailbox."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from sprouts_customer_geography.pipe01.errors import ConformanceError, require


COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
TASK_BRANCH_RE = re.compile(r"^refs/heads/(?:task|codex)/([a-z]+)-([0-9]{2,4}[a-z]?)(?:-|$)")
LOCAL_TASK_REF_RE = re.compile(r"^refs/heads/(?:task|codex)/")
INITIATIVE_FAMILIES = frozenset(
    {
        "APP",
        "ARCH",
        "BI",
        "DATA",
        "DEPLOY",
        "GEO",
        "GOV",
        "INTEGRATION",
        "MARKETS",
        "MODEL",
        "PBI",
        "PIPE",
        "STORE",
        "VALIDATE",
    }
)


@dataclass(frozen=True)
class InitiativeWorktree:
    initiative_id: str
    worktree_state: str
    push_state: str


@dataclass(frozen=True)
class RepositoryProbe:
    verified_commit: str
    worktree_state: str
    active_initiatives: tuple[InitiativeWorktree, ...]
    safe_work: tuple[InitiativeWorktree, ...]


def _git(repository: Path, *arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", *arguments],
            cwd=repository,
            check=check,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ConformanceError("READINESS_GIT_PROBE_FAILED", "repository readiness could not be verified") from exc


def _initiative_id(branch: str) -> str | None:
    match = TASK_BRANCH_RE.fullmatch(branch) or TASK_BRANCH_RE.match(branch)
    if match is None:
        return None
    family = match.group(1).upper()
    if family not in INITIATIVE_FAMILIES:
        return None
    return f"{family}-{match.group(2).upper()}"


def verify_initiative_commit(repository_root: Path, initiative_id: str, expected_commit: str | None) -> bool:
    """Verify a recorded preservation commit without publishing branch names."""

    if expected_commit is None or COMMIT_RE.fullmatch(expected_commit) is None:
        return False
    match = re.fullmatch(r"([A-Z]+)-([0-9]{2,4}[A-Z]?)", initiative_id)
    if match is None:
        return False
    initiative_prefix = f"{match.group(1).lower()}-{match.group(2).lower()}-"
    prefixes = tuple(
        f"refs/{location}/{namespace}/{initiative_prefix}"
        for location in ("heads", "remotes/origin")
        for namespace in ("task", "codex")
    )
    refs = _git(
        Path(repository_root).resolve(),
        "for-each-ref",
        "--format=%(objectname) %(refname)",
        "refs/heads/task",
        "refs/heads/codex",
        "refs/remotes/origin/task",
        "refs/remotes/origin/codex",
    ).stdout.splitlines()
    observed = []
    for line in refs:
        try:
            commit, refname = line.split(" ", 1)
        except ValueError:
            continue
        if refname.startswith(prefixes):
            observed.append(commit)
    return bool(observed) and set(observed) == {expected_commit}


def _parse_worktrees(output: str) -> tuple[tuple[Path, str | None], ...]:
    records: list[tuple[Path, str | None]] = []
    path: Path | None = None
    branch: str | None = None
    for line in (*output.splitlines(), ""):
        if not line:
            if path is not None:
                records.append((path, branch))
            path = None
            branch = None
        elif line.startswith("worktree "):
            path = Path(line.removeprefix("worktree "))
        elif line.startswith("branch "):
            branch = line.removeprefix("branch ")
    return tuple(records)


def _worktree_state(path: Path) -> str:
    status = _git(path, "status", "--porcelain=v1", "--untracked-files=normal").stdout
    return "uncommitted" if status.strip() else "clean"


def _push_state(path: Path) -> str:
    upstream = _git(path, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}", check=False)
    if upstream.returncode == 0 and upstream.stdout.strip():
        counts = _git(path, "rev-list", "--left-right", "--count", "@{upstream}...HEAD", check=False)
        if counts.returncode != 0:
            return "unknown"
        try:
            behind, ahead = (int(value) for value in counts.stdout.split())
        except (TypeError, ValueError):
            return "unknown"
        if behind:
            return "unknown"
        return "detected" if ahead else "not-detected"
    against_main = _git(path, "rev-list", "--left-right", "--count", "origin/main...HEAD", check=False)
    if against_main.returncode != 0:
        return "unknown"
    try:
        behind, ahead = (int(value) for value in against_main.stdout.split())
    except (TypeError, ValueError):
        return "unknown"
    if behind:
        return "unknown"
    return "detected" if ahead else "not-detected"


def _parse_local_task_refs(output: str) -> tuple[tuple[str, str | None], ...]:
    refs: list[tuple[str, str | None]] = []
    for line in output.splitlines():
        refname, separator, upstream = line.partition("\t")
        if not separator or LOCAL_TASK_REF_RE.match(refname) is None:
            continue
        refs.append((refname, upstream or None))
    return tuple(refs)


def _local_task_refs(repository: Path) -> tuple[tuple[str, str | None], ...]:
    result = _git(
        repository,
        "for-each-ref",
        "--format=%(refname)%09%(upstream)",
        "refs/heads/task",
        "refs/heads/codex",
    )
    return _parse_local_task_refs(result.stdout)


def _push_state_for_ref(repository: Path, refname: str, upstream: str | None) -> str:
    comparison = upstream
    if comparison is None:
        remote_ref = refname.replace("refs/heads/", "refs/remotes/origin/", 1)
        remote = _git(
            repository,
            "show-ref",
            "--verify",
            "--quiet",
            remote_ref,
            check=False,
        )
        comparison = remote_ref if remote.returncode == 0 else "refs/remotes/origin/main"
    counts = _git(
        repository,
        "rev-list",
        "--left-right",
        "--count",
        f"{comparison}...{refname}",
        check=False,
    )
    if counts.returncode != 0:
        return "unknown"
    try:
        behind, ahead = (int(value) for value in counts.stdout.split())
    except (TypeError, ValueError):
        return "unknown"
    if behind:
        return "unknown"
    return "detected" if ahead else "not-detected"


def _merge_initiative(
    previous: InitiativeWorktree | None,
    item: InitiativeWorktree,
) -> InitiativeWorktree:
    if previous is None:
        return item
    worktree_state = (
        "uncommitted"
        if "uncommitted" in {previous.worktree_state, item.worktree_state}
        else "clean"
    )
    if "detected" in {previous.push_state, item.push_state}:
        push_state = "detected"
    elif "unknown" in {previous.push_state, item.push_state}:
        push_state = "unknown"
    else:
        push_state = "not-detected"
    return InitiativeWorktree(item.initiative_id, worktree_state, push_state)


def probe_repository(repository_root: Path, preservation: dict[str, str] | None = None) -> RepositoryProbe:
    """Inspect linked worktrees and local task refs without returning raw identifiers."""

    repository = Path(repository_root).resolve()
    require((repository / ".git").exists(), "READINESS_REPOSITORY_INVALID", "the readiness publisher requires a Git worktree")
    commit = _git(repository, "rev-parse", "HEAD").stdout.strip()
    require(COMMIT_RE.fullmatch(commit) is not None, "READINESS_REPOSITORY_COMMIT_INVALID", "repository HEAD is not a full Git object ID")
    parsed = _parse_worktrees(_git(repository, "worktree", "list", "--porcelain").stdout)
    require(parsed, "READINESS_WORKTREE_STATE_INVALID", "no Git worktrees were available for readiness verification")

    initiatives: list[InitiativeWorktree] = []
    unclassified_attention = False
    linked_refs = {branch for _, branch in parsed if branch is not None}
    for path, branch in parsed:
        state = _worktree_state(path)
        initiative = _initiative_id(branch or "")
        if initiative is None:
            task_push_state = (
                _push_state(path)
                if branch is not None and LOCAL_TASK_REF_RE.match(branch) is not None
                else "not-detected"
            )
            unclassified_attention = (
                unclassified_attention
                or state != "clean"
                or task_push_state != "not-detected"
            )
            continue
        push_state = _push_state(path)
        initiatives.append(InitiativeWorktree(initiative, state, push_state))
        unclassified_attention = unclassified_attention or push_state == "unknown"

    for refname, upstream in _local_task_refs(repository):
        if refname in linked_refs:
            continue
        push_state = _push_state_for_ref(repository, refname, upstream)
        initiative = _initiative_id(refname)
        if initiative is None:
            unclassified_attention = unclassified_attention or push_state != "not-detected"
            continue
        if push_state != "not-detected" or initiative in (preservation or {}):
            initiatives.append(InitiativeWorktree(initiative, "clean", push_state))
        unclassified_attention = unclassified_attention or push_state == "unknown"

    combined: dict[str, InitiativeWorktree] = {}
    for item in initiatives:
        combined[item.initiative_id] = _merge_initiative(
            combined.get(item.initiative_id), item
        )

    ordered = tuple(combined[key] for key in sorted(combined))
    safe_work = tuple(item for item in ordered if item.worktree_state != "clean" or item.push_state == "detected")
    if unclassified_attention:
        overall = "attention-needed"
    elif not safe_work:
        overall = "clean"
    else:
        preserved = preservation or {}
        overall = "known-preserved-work" if all(preserved.get(item.initiative_id) in {"frozen", "preserved-paused"} for item in safe_work) else "attention-needed"
    return RepositoryProbe(commit, overall, ordered, safe_work)
