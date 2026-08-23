# GitHub Workflow & Execution Governance

## Purpose and boundary

This document is the detailed lifecycle authority for repository-safe execution. It preserves immutable task identity, task states, confidentiality boundaries, task-branch continuity, and pre-merge acceptance. GitHub Issues, branches, pull requests, commits, CI, comments, and rulesets are implementation or coordination evidence only; they do not become business or capability authority.

Each authorized task has one JSON manifest under `governance/tasks/`, validated against `schemas/governance/task_manifest.schema.json`. It is a compact durable authority record, not a chat transcript or protected-local registry. Every future material repository/GitHub execution or other acceptance-bearing durable implementation uses exactly one governed task manifest. Pure read-only exploratory Work does not require one merely because it occurred; an accepted controlling result must later be reconciled into an existing durable authority artifact or a justified work-order/current-state record.

## Authority and lane classification

- Ray remains the business decision-maker and manual transition point.
- Master Control Room (MCR) owns task authorization, lane assignment, sequencing, Lane A acceptance, and merge authorization.
- The named Capability Decisions & Acceptance owner accepts or rejects Lane B methodology/business changes at exact substantive commit H.
- Work remains read-only unless separately authorized. Codex performs bounded implementation and explicitly authorized Git/GitHub writes.
- Repository authority controls over all derivative GitHub evidence.

Lane A is routine technical work. It is permitted only when work exactly implements already accepted authority or preserves existing behavior, adds no business or analytical interpretation, needs no protected evidence or target access, is reproducible from repository-safe evidence, and has no unresolved interpretation question. Lane A does not require a separate capability chat, but MCR must explicitly accept exact H before canonical merge.

Lane B is capability-sensitive work. It includes any analytical methodology, model, feature, weight, threshold, transformation, normalization, validation, scoring, ranking, or customer-fit change; source authority, vintage, provenance, licensing, or missingness-policy change; geography inventory, CRS, membership, boundary, or aggregation-rule change; protected evidence or target-access authority; material product behavior, output semantics, eligibility logic, or decision rule; production-sensitive architecture, dependency, security, confidentiality, deployment, or external publication; destructive migration, history rewrite, force push, visibility, ruleset, branch-protection, or CI-policy change; legal, contractual, or compliance consequence; and any ambiguity over whether behavior is unchanged. The named capability owner accepts or rejects exact H, after which MCR may authorize only the accepted-record continuation and merge.

When classification is uncertain, use Lane B. Lane choice never weakens confidentiality, testing, branch protection, or explicit-authorization requirements.

## Execution permission envelope and blocker semantics

Unless an authorization expressly excludes an operation, an authorized governed task implicitly authorizes the non-destructive same-task execution operations needed to complete its exact scope. The default envelope includes:

- repository and connected-GitHub recovery plus exact-task access/readiness preflight;
- creation and maintenance of the authorized manifest and one disclosure-safe Issue when public posture is safe;
- creation and use of the task branch or worktree;
- task-scoped repository edits, commits, pushes, and authorized PR creation or maintenance;
- approved repository-safe tests and checks, required CI, retries of approved tests or CI, and environment-only retries;
- bounded mechanical corrections that do not alter authority, substantive behavior, protected access, or scope;
- derivative Issue/PR posture updates; and
- exact-H verification and preparation for the correct acceptance owner.

Separate tools or Git/GitHub actions within this envelope do not create additional Ray permission transitions. The envelope does not authorize scope expansion, lane change, new business/methodology/analytical/product behavior, protected evidence or target access, destructive Git operations, history rewrite, force push, direct unprotected publication, unscoped dependencies, new integrations/plugins/bots/webhooks/Projects/dispatch/synchronization, substantive post-H changes, deployment, publication beyond the authorized normal repository merge, or follow-on work.

Executors must classify execution blockers as exactly one of the following:

1. **Recoverable execution blocker.** Resolution remains wholly inside current task authority and the default envelope, such as an in-scope test or CI failure, formatting/lint/schema correction, transient network/tool failure, environment retry, non-destructive worktree/temporary-directory correction, repository/GitHub refresh, or authority-preserving mechanical correction. Recover or retry directly on the same task, Issue, branch, and PR; record material retry/correction evidence in derivative posture when useful. Ray involvement is not required unless recovery reveals an access or authority blocker.
2. **Access blocker.** A required authentication, account, connector, repository permission, user-side permission, or other external access dependency is unavailable and cannot be restored within existing executor capability. First verify the access cause and check repository/connected-GitHub evidence for an allowed existing path. Then request only the minimum user-side action needed to restore the exact blocked capability, without broadening scope. Resume the same task identity and current step after restoration unless authority changed.
3. **Authority blocker.** Resolution requires a decision or permission outside the task envelope, including scope or lane change; methodology, business, analytical, product, source, geography, or scoring authority; protected evidence or target access; destructive action; a new dependency or integration; deployment; publication outside the authorized merge; substantive post-H modification; or follow-on work. Stop, recover and cite the conflicting/current authority, and route only the minimum decision to the correct owner. Do not continue through a workaround or create a new task without MCR authorization.

Before asking Ray for permission, information, evidence, or action, determine whether the action is already in the task envelope, whether repository/GitHub recovery already provides the information, whether the blocker is mechanically recoverable, and whether a genuine access or authority blocker remains. Uncertainty and ordinary execution friction are not by themselves Ray transitions.

Repository-first recovery precedes recommending, authorizing, accepting, sequencing, resuming, or escalating governed work whenever relevant repository/GitHub access is available. Recover current orientation; inspect the exact task authority and relevant accepted config/schema/work-order authority; inspect active task, Issue, branch, PR, CI, and blocker state; and identify conflicting active tasks, settled decisions, protected or sealed stages, unmet prerequisites, and already-durable evidence. Repository authority controls over derivative GitHub posture. If required evidence is inaccessible, stale, ambiguous, or conflicting, fail closed rather than guessing or asking Ray to transport accessible evidence. GitHub must not be used to infer local-only state.

## Immutable identities, branches, and states

- Task IDs, corrections, retries, and bounded rework retain the same identity while authority is unchanged.
- Branches are `task/<task-id-lowercase>-<short-slug>`; one authorized task uses one branch while its authority is unchanged.
- Commits and PR titles are `<TASK-ID>: <imperative summary>`.
- The only task states are `AUTHORIZED`, `IN_PROGRESS`, `BLOCKED_FAIL_CLOSED`, `COMPLETED_AWAITING_ACCEPTANCE`, `ACCEPTED_CLOSED`, and `REJECTED_OR_REWORK_REQUIRED`.
- A task is `ACCEPTED_CLOSED` only with explicit, repository-safe capability acceptance metadata from its owner. Execution completion, a commit, test, PR, or merge never self-accepts a capability.

Corrections, retries, interruptions, and bounded rework remain under the same task identity while authority is unchanged. Before H acceptance they continue on the same branch and PR. After H acceptance, any substantive change invalidates acceptance and returns exact revised H to the correct owner. A changed scope or authority requires MCR direction and may require a new task; Codex must not infer that decision.

## Common H/A lifecycle

The current governed integration path is:

`MCR authorization and lane → one manifest/Issue/branch/PR → substantive H → CI on H → exact-H acceptance → acceptance-record-only A → CI on A → MCR-authorized protected merge → accepted canonical main`

1. MCR authorizes the exact task and assigns Lane A or Lane B.
2. Create one repository-safe manifest, one task branch, and one PR. When public posture is safe, create or reuse one exact-identity disclosure-safe Issue cockpit.
3. Complete substantive implementation at exact commit H. At H the manifest is `COMPLETED_AWAITING_ACCEPTANCE`, execution is `COMPLETED`, capability acceptance is `NOT_REVIEWED`, and H does not fabricate its own SHA.
4. Required `repository-validation` succeeds on the exact H at the PR head.
5. The correct acceptance owner explicitly accepts or rejects exact H: MCR for Lane A, or the named capability owner for Lane B. A passing check, PR, merge, Issue, or comment never creates acceptance.
6. No substantive change is permitted after accepted H without reacceptance. MCR controls authorization to continue with the acceptance record and merge.
7. Codex may create acceptance-record-only commit A only when authorized. A records `implementation_commit = H`, sets the current task manifest to `ACCEPTED_CLOSED` with capability acceptance `ACCEPTED`, and records the repository-safe acceptance disposition, owner/source, date, and next destination. The H..A diff may touch only explicitly authorized acceptance/closure surfaces for the current task; it must not change substantive implementation.
8. Required `repository-validation` reruns and succeeds on A. Verify H..A before merge.
9. MCR authorizes or executes normal protected merge as applicable. Canonical `main` lands already accepted. Do not use auto-merge unless separately authorized.
10. Close the Issue with the canonical merge and next destination. There is no post-merge acceptance-only commit or publication loop.

## A/merge continuation permission envelope

After the correct owner accepts exact H, one MCR authorization to proceed with the A/merge continuation covers creation of acceptance-record-only A; recording `implementation_commit = H` and repository-safe acceptance metadata; derivative Issue/PR acceptance updates; local validation and required CI on A; retries of approved CI or environment failures that do not change substantive H; H..A allowed-diff verification; normal protected merge when every accepted gate passes; verification of canonical `main`; and Issue closure with derivative closure posture. Do not ask Ray separately for these mechanical operations.

This continuation applies only while H remains the accepted substantive commit, A changes only explicitly authorized acceptance/closure surfaces, required checks pass, and the continuation authorizes normal protected merge. Any substantive post-H change invalidates acceptance and is an authority blocker requiring revised-H acceptance.

## Main integration and validation policy

`main` is protected by the `main-integration` ruleset (ID `21113123`). Pull requests are required; approvals are `0`; the bypass list is empty; force pushes and deletion are blocked; and `repository-validation` is required with strict, up-to-date behavior. Do not bypass these protections or change rulesets/CI without separate authorization.

The `repository-validation` workflow policy remains unchanged. It installs the repository package and runs the governance check, PIPE-01 check, PIPE-02 check, and full unit-test discovery for pull requests targeting `main`.

## Disclosure-safe Issue cockpit

When public disclosure is safe, one GitHub Issue is the normal derivative cockpit for a governed task. Search open and closed Issues for the exact task ID/title before creation, create at most one, and update it idempotently. Record only the task ID/title, lane, concise objective, current posture, current decision, exact next manual transition, manifest path, branch, PR/CI links, H and accepted A/merge references when appropriate, last-updated source/date, and an explicit public-disclosure/non-authority warning. Use comments only for material transitions. Do not paste full reports or protected information.

An Issue is not required when even an opaque public posture would reveal protected information. Do not create one in that case. An Issue never authorizes work or acceptance, overrides repository authority, or becomes a synchronized or mirrored registry. No bot, hook, or synchronization mechanism is authorized.

## Short-launch recovery

Where durable detailed authority already exists, continuation/resumption normally uses a short launcher containing only task ID, exact thread title, tool/surface, model, reasoning, and exact current step identity. Resolve the repository recovery order in `AGENTS.md`, exactly one matching manifest, exactly one detailed work order when required, referenced accepted config/schema authority, and relevant GitHub evidence. Fail closed when a record is missing, multiple controlling records match, the manifest is not executable, a required work order is missing/stale/superseded, authority conflicts, evidence is inaccessible, or retrieval is ambiguous. Use a full self-contained MCR prompt for genuinely new work or when durable authority is insufficient. Ray remains the manual decision/transition point, not the routine carrier of recoverable task state.

## Operating measurements and access readiness

Ordinary Lane A work normally targets no more than two Ray transitions: initial authorization and accepted-record/merge continuation after exact-H acceptance. Count infrastructure or access interruptions separately, but still include them in total transitions. A one-time access restoration is an interruption; recurring restoration is evidence of workflow failure, not a normal lifecycle stage.

Before repository edits, verify authenticated repository access, repository visibility to the GitHub integration, exact-identity Issue/branch/PR absence or continuity, and required Issue/PR write capability. If required access is unavailable, fail closed before making repository changes.

## Repository-safe manifest boundary

Manifests may record only repository-safe authority, scope, opaque dependency IDs, branch, completion evidence, and acceptance metadata. They must never contain protected paths, targets, forecasts, identities tied to locations, coordinates, nonces, protected digests, workbook details, protected registries/packages, or reconstructable protected lineage. Existing tracked-path safeguards remain independent defenses.
