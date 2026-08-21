# GitHub Workflow & Execution Governance

## Purpose and boundary

This document governs repository-safe execution. It preserves immutable task identity, task states, confidentiality boundaries, task-branch continuity, and separate capability acceptance. GitHub branches, pull requests, commits, CI, and rulesets are implementation or coordination evidence only; they do not become business or capability authority.

Each authorized task has one JSON manifest under `governance/tasks/`, validated against `schemas/governance/task_manifest.schema.json`. It is a compact durable authority record, not a chat transcript or protected-local registry. Every future material repository/GitHub execution or other acceptance-bearing durable implementation uses exactly one governed task manifest. Pure read-only exploratory Work does not require one merely because it occurred; an accepted controlling result must later be reconciled into an existing durable authority artifact or a justified work-order/current-state record.

## Immutable identities, branches, and states

- Task IDs, corrections, retries, and bounded rework retain the same identity while authority is unchanged.
- Branches are `task/<task-id-lowercase>-<short-slug>`; one authorized task uses one branch while its authority is unchanged.
- Commits and PR titles are `<TASK-ID>: <imperative summary>`.
- The only task states are `AUTHORIZED`, `IN_PROGRESS`, `BLOCKED_FAIL_CLOSED`, `COMPLETED_AWAITING_ACCEPTANCE`, `ACCEPTED_CLOSED`, and `REJECTED_OR_REWORK_REQUIRED`.
- A task is `ACCEPTED_CLOSED` only with explicit, repository-safe capability acceptance metadata from its owner. Execution completion, a commit, test, PR, or merge never self-accepts a capability.

## Current GitHub workflow

The current governed integration path is:

`authorized task → task branch → PR → repository-validation → protected-main merge → separate capability acceptance`

`main` is protected by the `main-integration` ruleset (ID `21113123`). Pull requests are required; approvals are `0`; the bypass list is empty; force pushes and deletion are blocked; and `repository-validation` is required with strict, up-to-date behavior. Do not bypass these protections or change rulesets/CI without separate authorization.

A PR remains implementation evidence only. After a merged PR, its optional post-acceptance note may record a disclosure-safe capability decision made elsewhere, but editing that note does not create capability acceptance. A local administrative acceptance commit does not automatically justify a publication task; do not publish each acceptance-only commit. A later substantive repository-state update may carry accepted state forward.

GitHub Issues remain deferred unless a concrete business/backlog use case is separately authorized. They are not task authority, a mirrored task registry, or a required workflow layer; no Issue synchronization is authorized.

## Short-launch recovery

Where durable detailed authority already exists, a short launcher may contain only task ID, exact thread title, tool/surface, model, reasoning, and exact current step identity. Resolve: (1) `AGENTS.md`; (2) exactly one matching task manifest; (3) exactly one detailed work order when required; (4) referenced accepted config/schema authority; and (5) relevant GitHub PR evidence when applicable. Fail closed when a record is missing, multiple controlling records match, the manifest is not executable, a required work order is missing/stale/superseded, authority conflicts, evidence is inaccessible, or retrieval is ambiguous. Do not use this option for first execution of a new task without a durable detailed execution record; a full self-contained Master Control Room prompt is the default/fallback.

## Repository-safe manifest boundary

Manifests may record only repository-safe authority, scope, opaque dependency IDs, branch, completion evidence, and acceptance metadata. They must never contain protected paths, targets, forecasts, identities tied to locations, coordinates, nonces, protected digests, workbook details, protected registries/packages, or reconstructable protected lineage. Existing tracked-path safeguards remain independent defenses.
