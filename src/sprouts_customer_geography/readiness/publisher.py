"""Build and atomically publish the schema-bound readiness snapshot."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Mapping

from sprouts_customer_geography.pipe01.errors import ConformanceError, require
from sprouts_customer_geography.readiness.disclosure import (
    SCHEMA_VERSION,
    SNAPSHOT_ID,
    load_json_safely,
    validate_development_readiness,
)
from sprouts_customer_geography.readiness.mailbox_contract import (
    MAILBOX_BRANCH,
    MAILBOX_ENFORCEMENT_PATHS,
    MAILBOX_FILENAME,
)
from sprouts_customer_geography.readiness.repository import InitiativeWorktree, probe_repository, verify_initiative_commit
from sprouts_customer_geography.readiness.store import ProjectState, default_state_root, recover_project_state, utc_now


def _protected_state(store: ProjectState | None, failure: ConformanceError | None) -> dict[str, str]:
    if store is not None:
        facts = store.readiness_facts()
        return {
            "project_profile": facts["project_profile"].upper(),
            "asset_catalog": facts["asset_catalog"].upper(),
            "original_source_inventory": facts["original_source_inventory"].upper(),
            "evidence_ledger": facts["evidence_ledger"].upper(),
            "model13_authority": {
                "registered-recoverable": "REGISTERED_RECOVERABLE",
                "registered-unresolved": "REGISTERED_UNRECOVERABLE",
                "not-registered": "UNREGISTERED",
            }[facts["model13_authority"]],
            "app01_inputs": {
                "registered-recoverable": "REGISTERED_RECOVERABLE",
                "registered-unresolved": "REGISTERED_UNRECOVERABLE",
                "not-registered": "UNREGISTERED",
            }[facts["app01_inputs"]],
        }
    profile = "MISSING" if failure is not None and failure.code in {"PROJECT_STATE_PROFILE_MISSING", "PROJECT_STATE_LEDGER_MISSING"} else "INVALID"
    return {
        "project_profile": profile,
        "asset_catalog": "UNRESOLVED",
        "original_source_inventory": "UNRESOLVED",
        "evidence_ledger": "UNRESOLVED",
        "model13_authority": "NOT_VERIFIED",
        "app01_inputs": "NOT_VERIFIED",
    }


def _active_entry(item: InitiativeWorktree, preservation: Mapping[str, str]) -> dict[str, str]:
    if item.worktree_state == "clean":
        worktree_state = "CLEAN"
    elif preservation.get(item.initiative_id) in {"frozen", "preserved-paused"}:
        worktree_state = "KNOWN_PRESERVED_WORK"
    else:
        worktree_state = "ATTENTION_NEEDED"
    push_state = {
        "not-detected": "SYNCHRONIZED",
        "detected": "UNPUSHED_SAFE_WORK",
        "unknown": "UNKNOWN",
    }[item.push_state]
    return {
        "initiative_id": item.initiative_id,
        "push_state": push_state,
        "worktree_state": worktree_state,
    }


def _safe_work_entry(item: InitiativeWorktree) -> dict[str, str]:
    if item.worktree_state != "clean" and item.push_state == "detected":
        state = "UNCOMMITTED_AND_UNPUSHED"
    elif item.worktree_state != "clean":
        state = "UNCOMMITTED"
    elif item.push_state == "detected":
        state = "UNPUSHED"
    else:
        state = "PRESERVED"
    return {"initiative_id": item.initiative_id, "state": state}


def _prerequisites(document: Mapping[str, Any]) -> list[dict[str, str]]:
    repository = document["repository"]
    protected = document["protected_state"]
    preservation = document["preservation"]
    recovery = document["recovery"]
    pairs = (
        ("REPOSITORY_READINESS", "READY" if repository["worktree_state"] != "ATTENTION_NEEDED" else "NEEDS_RUNWAY"),
        ("PROTECTED_PROJECT_PROFILE", "READY" if protected["project_profile"] == "READY" else "NEEDS_RUNWAY"),
        ("PROTECTED_ASSET_CATALOG", "READY" if protected["asset_catalog"] == "READY" else "NEEDS_RUNWAY"),
        ("ORIGINAL_SOURCE_INVENTORY", "READY" if protected["original_source_inventory"] == "READY" else "NEEDS_RUNWAY"),
        ("EVIDENCE_LEDGER", "READY" if protected["evidence_ledger"] == "READY" else "NEEDS_RUNWAY"),
        ("MODEL13_AUTHORITY", "READY" if protected["model13_authority"] == "REGISTERED_RECOVERABLE" else "NEEDS_RUNWAY"),
        ("APP01_INPUT_PACKAGE", "READY" if protected["app01_inputs"] == "REGISTERED_RECOVERABLE" else "NEEDS_RUNWAY"),
        ("MODEL14_PRESERVATION", "READY" if preservation["model14"] == "PRESERVED" else "NEEDS_RUNWAY"),
        ("MODEL15_PRESERVATION", "READY" if preservation["model15"] == "PRESERVED" else "NEEDS_RUNWAY"),
        ("FRESH_SESSION_RECOVERY", "READY" if recovery["fresh_session"] == "SUCCEEDED" else "NEEDS_RUNWAY"),
    )
    return [{"code": code, "status": status} for code, status in pairs]


def build_readiness_document(repository_root: Path, *, state_root: Path | None = None) -> Mapping[str, Any]:
    """Build a safe snapshot even when protected-local state is unavailable.

    Missing protected state affects only protected-dependent readiness codes;
    repository state remains inspectable and publishable.
    """

    store: ProjectState | None = None
    state_failure: ConformanceError | None = None
    try:
        store = recover_project_state(state_root, repository_root=repository_root)
    except ConformanceError as exc:
        state_failure = exc
    preservation = {} if store is None else dict(store.preservation())
    if store is not None:
        for initiative_id, (status, reference_commit) in store.preservation_details().items():
            if not verify_initiative_commit(repository_root, initiative_id, reference_commit):
                preservation[initiative_id] = "attention-needed"
    repository = probe_repository(repository_root, preservation)
    protected = _protected_state(store, state_failure)
    fresh_recovery = None if store is None else store.fresh_session_recovery_status(repository.verified_commit)
    preservation_document = {
        "model14": "PRESERVED" if preservation.get("MODEL-14") == "frozen" else ("NOT_VERIFIED" if store is None else "ATTENTION_NEEDED"),
        "model15": "PRESERVED" if preservation.get("MODEL-15") == "preserved-paused" else ("NOT_VERIFIED" if store is None else "ATTENTION_NEEDED"),
    }
    document: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "snapshot_id": SNAPSHOT_ID,
        "generated_at_utc": utc_now(),
        "repository": {
            "verified_commit": repository.verified_commit,
            "worktree_state": repository.worktree_state.replace("-", "_").upper(),
            "active_initiatives": [_active_entry(item, preservation) for item in repository.active_initiatives],
            "safe_work": [_safe_work_entry(item) for item in repository.safe_work],
        },
        "protected_state": protected,
        "preservation": preservation_document,
        "recovery": {
            "fresh_session": (
                "SUCCEEDED"
                if fresh_recovery == "passed"
                else (
                    "FAILED"
                    if fresh_recovery == "failed"
                    else "NOT_VERIFIED"
                )
            )
        },
        "prerequisites": [],
    }
    document["prerequisites"] = _prerequisites(document)
    return document


def _atomic_write(path: Path, document: Mapping[str, Any]) -> None:
    payload = json.dumps(document, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")) + "\n"
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", dir=path.parent, prefix=".readiness-", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except OSError as exc:
        raise ConformanceError("READINESS_PUBLICATION_FAILED", "the validated mailbox snapshot could not be written") from exc
    finally:
        if temporary is not None and temporary.exists():
            try:
                temporary.unlink()
            except OSError:
                pass


def _run_git(repository: Path, arguments: list[str], *, code: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            ["git", *arguments],
            cwd=repository,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise ConformanceError(code, "Git state required for mailbox publication is unavailable") from exc
    if check:
        require(result.returncode == 0, code, "Git state required for mailbox publication is unavailable")
    return result


def _git_path(repository: Path, arguments: list[str], *, code: str) -> Path:
    raw = _run_git(repository, arguments, code=code).stdout.strip()
    require(bool(raw), code, "Git state required for mailbox publication is unavailable")
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = repository / candidate
    return candidate.resolve()


def _validate_mailbox_destination(repository: Path, output_path: Path, state_root: Path | None) -> Path:
    output = Path(output_path).expanduser()
    require(output.name == MAILBOX_FILENAME, "READINESS_OUTPUT_PATH_REJECTED", "the mailbox output must use the fixed snapshot filename")
    require(output.parent.is_dir() and not output.is_symlink(), "READINESS_OUTPUT_PATH_REJECTED", "the mailbox output must target an existing dedicated worktree root")
    mailbox_root = _git_path(output.parent.resolve(), ["rev-parse", "--show-toplevel"], code="READINESS_MAILBOX_WORKTREE_INVALID")
    source_root = _git_path(repository, ["rev-parse", "--show-toplevel"], code="READINESS_SOURCE_WORKTREE_INVALID")
    target = mailbox_root / MAILBOX_FILENAME
    require(_same_path(output.parent, mailbox_root), "READINESS_OUTPUT_PATH_REJECTED", "the mailbox output must be the dedicated worktree root snapshot")
    require(not _same_path(mailbox_root, source_root), "READINESS_OUTPUT_PATH_REJECTED", "the mailbox must be published from a separate dedicated worktree")

    source_common = _git_path(source_root, ["rev-parse", "--git-common-dir"], code="READINESS_SOURCE_WORKTREE_INVALID")
    mailbox_common = _git_path(mailbox_root, ["rev-parse", "--git-common-dir"], code="READINESS_MAILBOX_WORKTREE_INVALID")
    require(_same_path(source_common, mailbox_common), "READINESS_MAILBOX_REPOSITORY_MISMATCH", "the mailbox worktree must belong to the source repository")
    branch = _run_git(mailbox_root, ["symbolic-ref", "--quiet", "--short", "HEAD"], code="READINESS_MAILBOX_BRANCH_INVALID").stdout.strip()
    require(branch == MAILBOX_BRANCH, "READINESS_MAILBOX_BRANCH_INVALID", "the mailbox output requires the dedicated readiness-mailbox branch")
    source_status = _run_git(source_root, ["status", "--porcelain=v1", "--untracked-files=all"], code="READINESS_SOURCE_STATUS_INVALID").stdout
    require(not source_status.strip(), "READINESS_SOURCE_DIRTY", "the snapshot source worktree must be clean at its verified commit")
    status = _run_git(mailbox_root, ["status", "--porcelain=v1", "--untracked-files=all"], code="READINESS_MAILBOX_STATUS_INVALID").stdout
    require(not status.strip(), "READINESS_MAILBOX_DIRTY", "the mailbox worktree contains existing changes")

    remote_ref = _run_git(
        mailbox_root,
        ["show-ref", "--verify", "--quiet", "refs/remotes/origin/readiness-mailbox"],
        code="READINESS_MAILBOX_REMOTE_INVALID",
        check=False,
    )
    require(remote_ref.returncode in {0, 1}, "READINESS_MAILBOX_REMOTE_INVALID", "the mailbox remote baseline could not be verified")
    if remote_ref.returncode == 0:
        head = _run_git(mailbox_root, ["rev-parse", "HEAD"], code="READINESS_MAILBOX_REMOTE_INVALID").stdout.strip()
        remote = _run_git(mailbox_root, ["rev-parse", "refs/remotes/origin/readiness-mailbox"], code="READINESS_MAILBOX_REMOTE_INVALID").stdout.strip()
        require(head == remote, "READINESS_MAILBOX_DIVERGED", "the mailbox worktree is not synchronized with its remote baseline")

    for enforcement_path in MAILBOX_ENFORCEMENT_PATHS:
        source_blob = _run_git(
            source_root,
            ["rev-parse", f"HEAD:{enforcement_path}"],
            code="READINESS_MAILBOX_ENFORCEMENT_STALE",
            check=False,
        )
        mailbox_blob = _run_git(
            mailbox_root,
            ["rev-parse", f"HEAD:{enforcement_path}"],
            code="READINESS_MAILBOX_ENFORCEMENT_STALE",
            check=False,
        )
        require(
            source_blob.returncode == 0
            and mailbox_blob.returncode == 0
            and source_blob.stdout.strip() == mailbox_blob.stdout.strip(),
            "READINESS_MAILBOX_ENFORCEMENT_STALE",
            "the mailbox validation runtime differs from the verified source baseline",
        )

    protected_root = (state_root or default_state_root()).expanduser().resolve()
    resolved_target = target.resolve()
    require(not _is_within_path(resolved_target, protected_root), "READINESS_OUTPUT_PATH_REJECTED", "the mailbox output may not overlap protected-local state")
    require(not _is_within_path(resolved_target, source_root), "READINESS_OUTPUT_PATH_REJECTED", "the mailbox output may not be written into the source worktree")
    return target


def _is_within_path(candidate: Path, parent: Path) -> bool:
    try:
        candidate.relative_to(parent)
        return True
    except ValueError:
        return False


def _same_path(first: Path, second: Path) -> bool:
    try:
        return os.path.samefile(first, second)
    except OSError:
        return os.path.normcase(str(first.resolve())) == os.path.normcase(str(second.resolve()))


def publish_readiness(repository_root: Path, output_path: Path, *, state_root: Path | None = None) -> Mapping[str, Any]:
    repository = Path(repository_root).resolve()
    destination = _validate_mailbox_destination(repository, Path(output_path), state_root)
    schema_path = repository / "schemas" / "readiness" / "development_readiness.schema.json"
    require(schema_path.is_file(), "READINESS_SCHEMA_MISSING", "the versioned readiness disclosure schema is missing")
    schema = load_json_safely(schema_path, error_code="READINESS_SCHEMA_UNREADABLE")
    document = build_readiness_document(repository, state_root=state_root)
    validate_development_readiness(document, schema=schema)
    _atomic_write(destination, document)
    return document
