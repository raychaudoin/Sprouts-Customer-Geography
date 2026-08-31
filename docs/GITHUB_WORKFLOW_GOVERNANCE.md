# GitHub Workflow and Execution Governance

## Purpose

This document defines the repository-safe handoff and implementation lifecycle for the owner-approved two-Project workflow. It replaces lanes, universal routine task manifests, Issue status cockpits, permanent capability-routing chats, acceptance-only commits, duplicate metadata CI, and exact-next-destination choreography for future work.

Historical Work Orders, manifests, acceptance records, Issues, and chat references remain evidence of the authority that existed when those changes were made. Do not rewrite them merely to match this model, and do not treat their legacy lifecycle fields as current execution requirements.

## Authority and roles

Ray remains the business decision-maker.

The Brainstorming Project, `Sprouts Customer Geography`, owns objective selection with Ray, GitHub inspection, prerequisite and runway preparation, Initiative Brief and Work Order authoring, launch, and post-implementation review. It cannot inspect the desktop repository or protected-local data.

The Development Project, `Sprouts-Customer-Geography-Development`, owns repository/local inspection, preservation of existing work, implementation within prepared authority, testing, bounded correction, branch/PR maintenance, and publication of repository-safe results and readiness. Development does not invent missing authority.

GitHub carries repository-safe authority and evidence between Projects. Repository contents control over derivative summaries. GitHub must not be used to infer protected-local facts, and local facts must not be published outside the readiness allowlist.

## Brainstorming-to-Development runway

Before preparing meaningful new work, Brainstorming must read current GitHub state and the latest Development Readiness Mailbox. The mailbox timestamp and verified baseline are part of the decision: a stale snapshot is not current readiness.

If a required source, permission, protected asset registration, evidence inventory, methodology decision, or other prerequisite is incomplete, Brainstorming must prepare that runway with Ray. It may authorize a bounded prerequisite initiative, supply the missing repository-safe authority, or defer the objective. It must not silently delegate an incomplete pathway to Development.

Meaningful work uses two durable artifacts:

1. **Initiative Brief Issue.** One concise Issue states the business objective, why it is timely, prepared pathway and prerequisites, permitted evidence/access, scope, exclusions, success criteria, decisions reserved for Ray, Work Order path, and protected-disclosure warning. It is authority for the stated initiative, not a synchronized task-status cockpit.
2. **Detailed Work Order.** One repository-safe Work Order supplies the exact implementation authorization, inputs, method constraints, validation, branch/PR expectations, stop point, and safe completion evidence. It must contain enough context for Development to execute without a chat transcript or permanent routing conversation.

The launcher sent to Development is intentionally short: initiative ID/title, Issue, branch, Work Order, and the exact stop point. Detailed authority remains in the durable artifacts.

Routine, reversible maintenance may use existing durable authority when Brainstorming expressly pre-authorizes that path. A universal JSON task manifest or lifecycle-state mutation is not required. Meaningful or sensitive work requires explicit prepared authority. Exact-final-version review is mandatory for consequential model/product decisions; other implementation follows the review and merge disposition expressly stated by its Initiative Brief and Work Order.

## Development preflight

Development must read the Initiative Brief and Work Order first, then inspect current GitHub and local repository state before changing anything. It must:

- verify branch/Issue/PR continuity and the current protected-`main` baseline;
- inspect and preserve unrelated local branches, worktrees, uncommitted work, and unpushed repository-safe work;
- read the latest mailbox and, when authorized, recover the durable protected-local profile/ledger through trusted registration;
- confirm that every prerequisite for the first implementation stage exists; and
- reconcile current authority with referenced config, schemas, method documents, prior accepted commits, and relevant CI.

Development may resolve ordinary in-scope implementation friction directly. If an external account or repository permission is missing, request only the minimum access restoration. If completion requires missing scope, methodology, evidence, protected access, product semantics, destructive action, dependency, deployment, or publication authority, stop the dependent stage and report that precise runway gap to Brainstorming.

## Implementation lifecycle

1. Preserve local work and use the authorized task-specific branch or isolated worktree.
2. Implement only the prepared objective. Use synthetic fixtures before authorized protected-local inputs.
3. Run focused validation, disclosure/confidentiality checks, relevant regression coverage, and normal CI. Apply bounded corrections on the same branch and PR while authority is unchanged.
4. Commit and push concise substantive changes; open or maintain one implementation PR linked to the Initiative Brief Issue.
5. After meaningful local work and before returning control to Brainstorming, generate the Development Readiness Mailbox with the allowlisted publisher and validate it. Never hand-edit a readiness snapshot or use free-form AI prose as a substitute.
6. Stop at the Work Order's exact endpoint. Unless merge is expressly authorized, the normal return is one final substantive PR head with passing CI.

PRs use the Initiative identifier and an imperative summary. The PR body states the authorized objective/exclusions, exact final commit, validation, readiness publication, safe protected-state confirmation, and review/merge posture. It does not contain lane fields, a routine manifest requirement, an acceptance-only commit, or exact-destination choreography.

## Development-to-Brainstorming return

Development returns three repository-safe evidence surfaces:

- the implementation PR, exact commit, and CI evidence;
- the refreshed Development Readiness Mailbox on its stable mailbox surface; and
- a short completion summary for decision-relevant local facts that the schema intentionally cannot publish.

The completion summary must remain non-protected. It may say that an authorized asset was recoverable, a stage was blocked by an absent registration, or prior local work was preserved. It must not include protected paths, filenames when revealing, addresses, coordinates, row identities, target values, registry contents, credentials, revealing hashes, or reconstructable lineage.

Brainstorming reads all three before deciding review, cutover, prerequisite preparation, or a future initiative. Development does not begin the next initiative on its own.

## Development Readiness Mailbox

The mailbox is a standing capability/readiness snapshot, not an initiative status registry. Its schema, tracked snapshot location, publication surface, local publisher, validation rules, and recovery procedure are defined in the [Development Readiness Mailbox runbook](governance/DEVELOPMENT_READINESS_MAILBOX.md).

Only strict, versioned, allowlisted fields and bounded enum/identifier values may be published. Unknown fields and prohibited disclosure classes fail closed. Every snapshot records its generation time and verified repository/local baseline so staleness is obvious.

The mailbox publisher may read Git metadata plus approved profile/ledger readiness facts, but it must sanitize all output before publication. Raw worktree paths, filenames, Git status lines, database rows, exception contents, and protected artifact metadata must never flow directly into the snapshot.

## Protected-local recovery

The durable project profile and evidence ledger live outside Git worktrees. The normal recovery path uses a deterministic machine-local state location; relocation uses an explicit override rather than arbitrary discovery. Registered assets resolve by stable logical ID beneath allowlisted roots. Path traversal and outside-root resolution fail closed.

Do not recursively open arbitrary JSON, spreadsheets, directories, or protected outputs to discover project state. Original protected sources remain immutable, and the ledger should store lineage and events without raw target values unless a separately authorized technical requirement demands them.

Evidence events remain independent and auditable: located; identity-read; machine-target-read; visible; analytically-used; validation-used; development-used; and disclosed. No event auto-promotes another. In particular, machine-target-read does not imply visibility, analytical use, or development use.

## Exact-final-version acceptance

Consequential model and product decisions use this lifecycle:

1. Development produces the final substantive commit.
2. Required CI succeeds on that exact commit.
3. Ray or the named reviewer accepts or rejects that exact commit.
4. Any later substantive change invalidates the decision and requires review of the revised commit.
5. The unchanged accepted commit may merge through protected `main`.

There is no acceptance-record-only commit and no duplicate CI run solely for metadata. Acceptance may be recorded on the Initiative/PR or another repository-safe review surface without changing the accepted tree. A passing check, mailbox refresh, PR state, merge, or historical lifecycle field does not create acceptance.

Ordinary reversible implementation may merge after required CI without a separate Ray acceptance transition only when the Initiative Brief/Work Order expressly pre-authorizes that disposition. Otherwise, stop at the final PR for review.

## Branch protection and Git safety

`main` remains protected: pull requests and required `repository-validation` are mandatory; strict up-to-date behavior applies; force pushes and deletion are blocked; and no bypass is authorized. Do not change rulesets or CI policy without explicit authority.

- Branches normally use `task/<initiative-id-lowercase>-<short-slug>`.
- Commits and PR titles use `<INITIATIVE-ID>: <imperative summary>`.
- Corrections and retries remain on the same branch and PR while objective and authority are unchanged.
- Do not force-push, destructively reset, delete user work, rebase, squash, merge, cherry-pick, or publish beyond the authorized boundary.
- Before final return, inspect status and the full diff for unrelated work, large generated data, secrets, protected material, and unexpected files.

## Retired machinery and transition

For future work, do not require or recreate:

- Lane A or Lane B classification;
- universal routine task manifests or lifecycle-only status updates;
- Issues synchronized as task-status cockpits;
- permanent capability-acceptance or routing chats;
- exact-next-destination handoff choreography;
- substantive H plus acceptance-only A commits;
- duplicate CI after acceptance metadata only;
- checkers whose sole purpose is moving task lifecycle fields; or
- per-worktree/session protected registry-pointer restoration as normal operation.

These retirements do not weaken protected/public boundaries, provenance, explicit missingness, deterministic reproduction, target-blind freezes, grouped validation, protected-field allowlists, egress controls, protected-characteristic restrictions, branch/PR/CI controls, or exact-final-version acceptance for consequential decisions.
