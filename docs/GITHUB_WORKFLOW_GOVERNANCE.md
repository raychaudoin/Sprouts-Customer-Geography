# Local GitHub Workflow & Execution Governance

## Purpose and boundary

This is the repository-safe local workflow foundation for governed execution before a GitHub repository or remote exists. It does not authorize GitHub creation, authentication, remotes, pushes, issues, pull requests, merges, Actions, deployment, or promotion.

Each authorized task has one JSON manifest under `governance/tasks/`, validated against `schemas/governance/task_manifest.schema.json`. The manifest is a compact record for reconciling a self-contained handoff prompt with durable project authority; it is not a chat transcript or a protected-local registry.

## Immutable identities and naming

- Task IDs use the existing prefixes `GOV`, `DATA`, `MODEL`, `GEO`, `BI`, `PIPE`, `STORE`, `MARKETS`, `INTEGRATION`, `DEPLOY`, and `VALIDATE`, followed by a two-digit number and an optional letter. Corrections, retries, fail-closed runs, and bounded rework retain the same task ID unless authority changes.
- Capability chats are named `<CAPABILITY>: <Topic> Decisions & Acceptance`. Execution threads are named `<TASK-ID>: <Short Action>`. A new task or thread follows an authority change, not an inconvenience or failed run.
- Branches are `task/<task-id-lowercase>-<short-slug>`. One authorized task uses one branch while its authority is unchanged.
- Commits and future PR titles are `<TASK-ID>: <imperative summary>`. A future PR is evidence, never acceptance.
- Logical artifact IDs use `<CAPABILITY><NN>_<UPPER_SNAKE_ARTIFACT_NAME>_V<MAJOR>`. Existing accepted artifact names, versions, hashes, and hash semantics are not renamed or reinterpreted.

## States and acceptance

The only task states are `AUTHORIZED`, `IN_PROGRESS`, `BLOCKED_FAIL_CLOSED`, `COMPLETED_AWAITING_ACCEPTANCE`, `ACCEPTED_CLOSED`, and `REJECTED_OR_REWORK_REQUIRED`.

Execution completion, a local commit, a test pass, a completion report, a future PR, or a future merge never closes a capability. A task can be `ACCEPTED_CLOSED` only when the manifest separately records `acceptance_disposition: ACCEPTED`, `completion_state.capability_acceptance: ACCEPTED`, and disclosure-safe `acceptance_metadata` from the capability owner. GOV-02 deliberately remains `COMPLETED_AWAITING_ACCEPTANCE`.

## Repository-safe manifest boundary

Required manifest metadata includes authority, scope/exclusions, accepted logical artifacts, opaque protected dependency IDs, branch, completion/evidence, acceptance destination/disposition, and exact next destination. `implementation_commit` is optional because its final commit cannot truthfully be self-referential within that same commit.

Manifests may contain opaque IDs such as `PROTECTED_FUTURE_INPUT_V1`, but never protected absolute paths, target or forecast values, seed/candidate coordinates, nonces, protected digests, target-cell addresses, protected registries, protected packages, workbook copies, or reconstructable protected lineage. The validator rejects forbidden fields, path-like strings, coordinate pairs, and SHA-256-like strings. Existing tracked-path safeguards remain an independent defense.

## Handoff and future GitHub checkpoint

The two-layer Ray handoff remains required: user-routing metadata stays outside one complete, self-contained recipient prompt. Durable manifest metadata can be reconciled with that prompt, but full chat transcripts stay out of Git.

After GOV-02 capability acceptance, a separately authorized checkpoint may decide whether to create a private GitHub repository, choose an owner/account, establish a remote, verify authentication, push accepted history, configure default branch and protection, enable appropriate CI/workflows, and establish the issue/PR workflow. The local `.github` templates are only future conventions; they do not configure a remote workflow.
