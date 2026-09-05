# GOV-16 — Post-Review Correction Specification

## Status

This is the current substantive correction specification for the existing GOV-16 initiative before cutover. It does not create a new initiative.

It supersedes earlier GOV-16 correction iterations where they conflict with this specification.

The operative authority for execution is the current GOV-16 Work Order together with the Approved Governance Implementation Target. GitHub comments, PR descriptions, checks, labels, and mailbox records are coordination/evidence only unless the operative authority expressly incorporates them.

## Correct durable instruction architecture

The project uses four durable instruction surfaces:

### Brainstorming

1. Brainstorming Project Custom Instructions — concise constitutional rules.
2. Brainstorming Operating Standard — detailed playbook.

### Development

1. `AGENTS.md` — concise repository constitutional executor contract.
2. Development Operating Standard — detailed repository-execution playbook.

The Development Project has no ChatGPT Project Custom Instructions.

Operating Standards may elaborate their constitutional layer but may not contradict or override it.

None of the four durable instruction surfaces may contain volatile project state such as current SHAs, PR/Issue numbers, active-task status, temporary branch names, live mailbox status, temporary blockers, current model inventory, or current reasoning-menu labels.

## Brainstorming governance target

The exact approved Brainstorming-side texts are:

- `docs/governance/BRAINSTORMING_PROJECT_CUSTOM_INSTRUCTIONS.md`
- `docs/governance/BRAINSTORMING_OPERATING_STANDARD.md`

Development must preserve their governance meaning when reconciling repository-side implementation.

Brainstorming owns governance semantics, runway preparation, authority/evidence boundaries, Initiative Brief and Work Order preparation, active-mailbox Launch Records, dynamic execution-profile recommendations, review of durable evidence, and recommendations for acceptance/remediation/promotion/next work.

Development owns repository-connected implementation inside supplied authority and may make technical/editorial choices that do not change approved governance meaning.

## Two distinct GitHub mailbox functions

### Development Readiness Mailbox

The existing machine-generated, closed-schema Development Readiness Mailbox remains the safe readiness/capability surface. It answers what local/repository prerequisites are safely known to be ready. It is not task authority and not task chronology.

### Active initiative/candidate mailbox

The active GitHub Issue/PR conversation carries concise chronological coordination/evidence records.

- Before a PR exists, the Initiative Issue may be the active mailbox.
- Once a PR exists, the PR conversation becomes the active candidate mailbox.
- Do not duplicate new candidate chronology into both Issue and PR.

Use three concise typed records:

- `LAUNCH` — written by Brainstorming before meaningful Development or review work begins.
- `RESULT` — written by Development after implementation/remediation.
- `REVIEW` — written by independent review against an exact candidate.

These records exist so Brainstorming can recover what happened, by which role/surface, against which candidate, and what control point comes next without Ray transporting long completion/review reports.

Launch, Result, and Review Records cannot create/enlarge authority, accept work, authorize merge/protected actions, or override the Work Order or repository truth.

## Minimum record semantics

### Launch Record

Concise fields/meaning:

- record type `LAUNCH`;
- initiative/current action;
- controlling Work Order;
- destination/role or review surface;
- PR and exact candidate head when applicable;
- requested action and material exclusions;
- current task-specific execution profile when relevant;
- expected next control point.

### Result Record

Concise fields/meaning:

- record type `RESULT`;
- initiative/action performed;
- exact resulting PR/head candidate;
- concise changed-scope summary;
- validation/CI performed or pending;
- safeguards/exclusions preserved;
- unresolved gap/deviation if any;
- required next control point.

### Review Record

Concise fields/meaning:

- record type `REVIEW`;
- review role/surface;
- exact PR/base/head reviewed;
- disposition such as `PASS` or `REWORK REQUIRED`;
- material findings/deviations;
- safety/evidence concerns;
- next control point.

Repository implementation may choose a compact Markdown format/template as long as these semantics remain clear and records stay concise.

## Dynamic tool/model/reasoning selection

Brainstorming must dynamically recommend the tool/surface, current model, and reasoning level for each meaningful Development launch.

Ray's ChatGPT Pro membership is the only durable availability assumption.

When material, Brainstorming consults current official OpenAI guidance and recommends the lightest adequate current option for the task, considering complexity, ambiguity, consequence of error, repository/coding depth, reasoning horizon, and cost/latency.

Durable governance must not hard-code current named models, model inventories, or reasoning levels.

Task-specific Work Orders/launchers may and should carry the current recommendation and concise rationale.

## Runway-preparation invariant

Before meaningful Development work, Brainstorming must recover current GitHub state, active mailbox chronology, and the latest validated Development Readiness Mailbox, then prepare prerequisites, scope, exclusions, evidence/access rules, success criteria, and Ray-reserved decisions.

Incomplete prerequisites are Brainstorming runway-preparation problems. Development may solve technical implementation problems within supplied authority but may not invent missing evidence, access, methodology, scope, permissions, product semantics, analytical authority, deployment authority, or publication authority.

## User-burden invariant

Ray should normally carry only a short launcher between Projects/surfaces.

Development and independent review must write their concise Result/Review Records to the active mailbox so Brainstorming can retrieve them directly.

When a reusable prompt, launcher, Custom Instructions block, Operating Standard, or similar instruction artifact needs revision, regenerate the complete replacement. Never require Ray to splice, patch, or merge fragments manually.

## Repository implementation requirements

Revise PR #45 so that:

1. the repository copies of the approved Brainstorming Custom Instructions and Brainstorming Operating Standard match the active approved texts;
2. `AGENTS.md` is the Development constitutional layer;
3. a Development Operating Standard exists as the detailed execution playbook;
4. the mistaken Development Project Custom Instructions surface is deleted or explicitly historical/non-applicable;
5. repository operating-model/readiness/protected-evidence docs consistently distinguish the Readiness Mailbox from the active Issue/PR mailbox;
6. repository templates/guidance support concise Launch, Result, and Review Records without turning them into an authority engine or status cockpit;
7. Development is required to write a Result Record after meaningful implementation/remediation and independent review is required to write a Review Record when review is requested;
8. once a PR exists, new candidate chronology is written to the PR conversation rather than mirrored into the Initiative Issue;
9. Brainstorming is required to retrieve durable Result/Review evidence rather than rely on Ray as evidence courier when GitHub retrieval is available;
10. dynamic tool/model/reasoning recommendation remains a Brainstorming responsibility without hard-coded model inventory;
11. validators/tests enforce meaningfully testable governance invariants without recreating retired lifecycle ceremony;
12. the approved readiness mailbox, protected-local profile/ledger, evidence semantics, confidentiality controls, and exact-final-version model remain intact.

## Retired machinery must not return

Do not reintroduce as mandatory workflow:

- Lane A/Lane B;
- universal routine task manifests/state machines;
- synchronized Issue status cockpits;
- permanent acceptance/routing chats;
- exact-next-destination choreography;
- acceptance-only A commits;
- duplicate CI solely for acceptance metadata;
- routine per-session/worktree path restoration.

Historical artifacts may remain historical evidence.

## Preserved safety and analytical integrity

Do not weaken:

- public/protected disclosure separation;
- source/vintage/schema/transformation provenance;
- explicit missingness/no silent zero-fill;
- target-blind feature/evaluation freezes;
- physical-location-grouped validation;
- deterministic/reproducible runs;
- protected-field allowlists and egress controls;
- protected-characteristic restrictions;
- protected-main/PR/CI safeguards;
- distinct protected-evidence event semantics;
- exact-final-version review for consequential decisions;
- Git safety against destructive loss of user work.

## Validation and stop point

This is substantive governance correction work. Development must:

- produce a revised exact PR #45 substantive head;
- run focused governance/readiness tests and required full CI on that exact head;
- refresh and validate the Development Readiness Mailbox against that exact source head;
- update the stale PR description to the new evidence;
- write a concise `RESULT` Record to PR #45 before returning control;
- keep MODEL-14 and MODEL-15 analytical work preserved/paused;
- open no fresh targets;
- not merge PR #45.

The next control point after a successful Result Record is focused independent review of the exact final substantive candidate, which must write a `REVIEW` Record to PR #45.
