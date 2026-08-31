# Repository Agent Contract

This file is the canonical repository-level instruction contract for Sprouts Customer Geography. Follow higher-priority system, developer, administrator, platform, and explicit user instructions first. When authority is ambiguous or an action could destroy, expose, or analytically consume protected state, fail closed and request the minimum missing decision.

## Product and business boundary

Sprouts Customer Geography is a public-data proxy and decision-support capability for understanding likely Sprouts-oriented household geography, including demographic fit, target-household mass, pocket continuity, seed surroundings, directional change, candidate displacement, and market context. Milwaukee is the first pilot; later markets must use configuration rather than copied applications or repositories.

The product is not a final site-selection engine, a substitute for human judgment, an extension of the existing Sprouts Site Scanner, or a reproduction of Sprouts' proprietary customer model.

## Two-Project authority model

Ray remains the business decision-maker. GitHub is the repository-safe intermediary between two Projects:

- **Brainstorming — `Sprouts Customer Geography`.** This cloud Project decides objectives with Ray, inspects current GitHub and the Development Readiness Mailbox, prepares missing runway and prerequisites, writes one concise Initiative Brief Issue plus a detailed repository-safe Work Order for meaningful work, sends a short Development launcher, and reviews the resulting PR, CI, mailbox, and safe local summary. It has no desktop-repository or protected-local access.
- **Development — `Sprouts-Customer-Geography-Development`.** This repository-connected Project reads the Initiative Brief and Work Order, inspects GitHub and local state, verifies that the prepared pathway exists, preserves current work, executes the approved objective, validates it, maintains its branch/PR, and returns repository-safe evidence and readiness. It may load registered protected-local state only when the Work Order expressly permits that access.

Development has broad implementation discretion inside the prepared pathway. It does not invent missing scope, evidence, access, methodology, permissions, product semantics, or analytical authority. If the pathway is incomplete, stop the dependent stage, identify the precise gap, publish only schema-approved readiness facts, and return the gap to Brainstorming. Ordinary in-scope test failures, retries, bounded mechanical corrections, commits, pushes, and PR maintenance do not require a new Ray transition.

GitHub Issues, Work Orders, branches, pull requests, commits, checks, and the mailbox are repository-safe authority or evidence only as specified. They never make protected information public and never convert implementation evidence into an analytical or business decision.

## Recovery and durable state

Before meaningful execution, recover current state in this order:

1. the exact Initiative Brief Issue and detailed Work Order named by the launcher;
2. this repository's `README.md` current orientation and this contract;
3. the accepted `config/`, `schemas/`, and method documentation referenced by that authority;
4. relevant GitHub branches, PRs, commits, checks, and ruleset evidence;
5. the current Development Readiness Mailbox and its staleness/baseline metadata; and
6. when authorized, the protected-local project profile and ledger through their registered recovery interface.

Historical task manifests, Work Orders, acceptance records, and capability-chat references remain historical evidence. Read them when current authority references them, but do not create or update a universal task manifest, task-status cockpit, lifecycle field, or permanent routing chat merely to execute future routine work.

Repository authority controls over derivative GitHub summaries. Local-only facts must be verified locally, never inferred from GitHub. Material conflict, missing or stale authority, inaccessible evidence, ambiguous retrieval, or an incomplete prerequisite must fail closed for the affected stage.

The durable protected-local profile and ledger live outside Git worktrees. Recover them from trusted registration and deterministic project layout, with an explicit relocation override only when needed. Resolve only registered logical asset IDs beneath authorized roots. Do not recursively inspect arbitrary JSON, spreadsheets, directories, or protected outputs to discover what they might be, and do not routinely ask Ray to restore known paths.

## Required readiness return

After meaningful local work and before returning control to Brainstorming, Development must refresh the Development Readiness Mailbox through the repository's allowlisted publisher and run its validator. The mailbox must be generated from approved repository/profile/ledger facts; it must never be hand-edited or replaced by an AI free-form readiness summary.

Publish only schema-approved fields and bounded values. The publisher must reject unknown fields and prohibited disclosure classes, including revealing paths or filenames, addresses, coordinates, SeedPointIDs or other row identities, target-like values, protected registry contents, credentials, revealing hashes, and reconstructable protected lineage. Make the refresh time and verified repository/local baseline explicit. If a safe refresh cannot be completed, do not improvise a substitute; report the failure and the last verified mailbox state.

## Scope control

Stay within the Initiative Brief and Work Order. Favor the smallest useful increment; distinguish prerequisites from housekeeping; avoid broad cleanup, speculative frameworks, and market-specific forks. Record unrelated discoveries as bounded recommendations. Never begin a follow-on initiative, merge, deploy, publish, or analytically consume additional evidence unless the current authority explicitly permits it.

Before asking Ray for information or action, inspect the authorized repository, GitHub, mailbox, and registered local state to determine whether the answer is already durably available. Ask only questions that materially change safe execution. Missing runway is a Brainstorming preparation problem, not implied authority for Development to solve it.

## Confidentiality and protected information

Treat every tracked file, Issue, PR, comment, check output, and mailbox value as public disclosure. Unless explicitly authorized, never commit or publish real Sprouts seed points; internal Sprouts direction; live-pursuit candidate addresses or coordinates; owner or broker contacts; credentials; proprietary demographic data; live Site Scanner databases; emails; internal documents; production exports with confidential fields; protected paths, registries, identities, target values, model parameters, or screenshots exposing protected information.

Use synthetic or clearly fictional fixtures and ignored local overlays for confidential data. Keep secrets and protected values out of logs, command output, fixtures, notebooks, reports, screenshots, and exception text. Original protected sources remain immutable. Avoid copying raw targets into the ledger unless a separately authorized technical need makes that unavoidable. If protected material appears in a tracked or publishable surface, stop, preserve it without copying or deleting it, and report the exposure risk.

Protected evidence events are distinct and auditable: asset located, identity fields read, target decoded by a machine, target visible to a human/model, analytically used, validation-used, development-used, and disclosed. One event must not silently imply another. In particular, machine target reading alone does not create development consumption.

See [data governance](docs/DATA_GOVERNANCE.md) and the [Development Readiness Mailbox runbook](docs/governance/DEVELOPMENT_READINESS_MAILBOX.md).

## Public-data provenance

Each accepted source needs a manifest or equivalent record, as applicable, with source name, official location, access method, dataset and schema versions, release/vintage, retrieval date, geography vintage, license/terms, attribution, query/extraction parameters, practical checksums, known omissions, transformation lineage, refresh expectations, and fallback behavior.

Keep raw downloads and large caches outside Git unless a specific small, legal fixture is authorized. Preserve reconstructability through source records, scripts, configuration, documentation, synthetic fixtures, and tests rather than copied downloaded environments.

## Analytical and scoring safeguards

Any authorized analytical implementation must:

- distinguish demographic fit from household mass and descriptive measures from modeled conclusions;
- retain components, source vintages, uncertainty, and quality flags;
- never silently convert missing values to neutral, favorable, or zero values, and fail closed when missing inputs would mislead;
- document normalization, transformations, weights, calibration, and model/evidence membership;
- preserve target-blind feature and evaluation freezes plus physical-location-grouped validation;
- exclude protected characteristics from scoring inputs absent explicit review and authority;
- describe outputs as public-data proxies, never Sprouts' proprietary model; and
- use seed points as evidence, not automatic ground truth.

Consequential model or product decisions require exact-final-version acceptance under the workflow below. Historical acceptance remains controlling until replaced through an authorized decision.

## Architecture boundary

- Perform reproducible public-data preparation and complex spatial analysis upstream; expose stable presentation-output contracts.
- Keep protected adapters and inputs outside tracked source; preserve protected-field allowlists and egress controls.
- Use market configuration, replaceable public-source adapters, and an extension boundary for future proprietary adapters.
- Do not introduce cloud services, databases, APIs, orchestration frameworks, dependencies, deployment, or publishing rights without explicit authority.
- Avoid hidden spatial or analytical logic in presentation layers when upstream computation is more testable.

Treat the architecture as a guardrail, not an irrevocable production design. See [architecture](docs/ARCHITECTURE.md).

## Systematic problem-solving and validation

Identify the business problem, failure family, shared invariant, root cause, adjacent variants, boundaries, invalid and missing inputs, retry and interruption behavior, generalization limit, and residual risk. Prefer one bounded general rule or validation contract over record-specific exceptions.

Use meaningful tests proportionate to the authorized work. As relevant, cover source schemas, geography, join keys, reproducibility, synthetic spatial fixtures, boundary direction, missing data, uncertainty, quality flags, stable output schemas, duplicates, stale sources, interruption, reruns, path traversal, registered-asset containment, disclosure rejection, and fail-closed behavior. Use synthetic fixtures before protected-local inputs. Do not create meaningless tests merely to report a passing suite.

## GitHub lifecycle and exact-final-version acceptance

- Work on the authorized task-specific branch or isolated worktree; do not edit `main` directly.
- Preserve unrelated local work. Do not force-push, destructively reset, delete user work, rebase, squash, merge, cherry-pick, or promote without explicit authorization.
- Use one Initiative Brief Issue for a meaningful objective and one implementation PR. The Issue is a concise authority brief, not a synchronized status cockpit.
- Use concise task-specific commits. Before completion, review status and the complete diff for unrelated changes, large data, secrets, protected material, and accidental generated output.
- Required CI must pass on the exact final substantive commit.
- For a consequential model or product decision, Ray or the named reviewer accepts or rejects that exact commit. Any later substantive change invalidates the decision and requires review of the revised commit. The unchanged accepted commit may then merge through protected `main`.
- Do not create an acceptance-record-only commit or rerun duplicate CI solely to record acceptance. Ordinary reversible implementation may merge after CI only when the Initiative Brief/Work Order expressly pre-authorizes that path.
- Never infer acceptance or merge permission from a passing check, PR state, Issue comment, mailbox refresh, or historical status field.

See [GitHub workflow governance](docs/GITHUB_WORKFLOW_GOVERNANCE.md) for the detailed lifecycle.

## Handoff and completion reports

Brainstorming launches Development with a short message that names the Initiative, Issue, branch, and Work Order. The durable artifacts carry the detailed authority. A permanent routing chat, exact-next-destination choreography, copied chat transcript, or recipient-to-recipient delegation chain is not required.

Development returns a short report containing only decision-relevant evidence: outcome; exact final commit and PR; validation/CI; mailbox location, refresh result, and baseline; safe local recovery/readiness facts; protected-state preservation; blockers or deviations; and whether the PR is ready for exact-final-version review. Do not paste protected facts or repeat long repository evidence. Return control to Brainstorming for review and future runway preparation; do not self-authorize the next initiative.
