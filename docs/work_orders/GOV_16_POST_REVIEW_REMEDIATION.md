# GOV-16 — Post-Review Remediation Work Order

## Status and authority

This is the operative same-initiative remediation Work Order for GOV-16 after the clean-room `REWORK REQUIRED` disposition.

It does not create a new initiative.

It operates under GitHub Initiative #44 and PR #45 and must be read together with:

- `docs/governance/GOV_16_POST_REVIEW_CORRECTION_SPEC.md`
- `docs/governance/GOV_16_APPROVED_GOVERNANCE_IMPLEMENTATION_TARGET.md`
- `docs/governance/BRAINSTORMING_PROJECT_CUSTOM_INSTRUCTIONS.md`
- `docs/governance/BRAINSTORMING_OPERATING_STANDARD.md`

The two Brainstorming documents are the exact approved Brainstorming-side texts. The Approved Governance Implementation Target defines the semantics Development must preserve when reconciling repository-side `AGENTS.md`, the Development Operating Standard, references, validators/tests, and supporting mechanics.

Development may make technical/editorial implementation choices that preserve those semantics. It may not redesign them.

## Objective

Implement the already-approved GOV-16 correction so PR #45 is technically sound and semantically faithful to the final governance target.

## First bounded prerequisite — readiness refresh

The currently published Development Readiness Mailbox predates the current GOV-16 branch head.

Before relying on local readiness for this remediation:

1. inspect current GitHub and local GOV-16 state;
2. preserve existing unrelated local work;
3. regenerate the Development Readiness Mailbox through the allowlisted publisher against current local/GitHub state;
4. validate the refreshed mailbox;
5. confirm the local prerequisites needed for this governance-only remediation are available.

A mailbox state showing incomplete original-source inventory or evidence ledger is not by itself a blocker to this governance remediation because this Work Order does not authorize MODEL-15 analytical reconciliation. If the refresh instead reveals a real preservation, repository-integrity, or required-profile problem that makes this remediation unsafe, stop the dependent stage and report the exact gap.

## Required implementation

Implement the approved four-surface architecture:

### Brainstorming

- `docs/governance/BRAINSTORMING_PROJECT_CUSTOM_INSTRUCTIONS.md` remains the approved constitutional text.
- `docs/governance/BRAINSTORMING_OPERATING_STANDARD.md` remains the approved detailed playbook.

Development must not rewrite their governance meaning. Repository-formatting/reference corrections are permitted only when semantics are unchanged.

### Development

- `AGENTS.md` becomes the concise Development constitutional executor contract.
- Add a Development Operating Standard as the detailed execution playbook.
- Remove `docs/governance/DEVELOPMENT_PROJECT_CUSTOM_INSTRUCTIONS.md` as an active proposed instruction surface; deletion is preferred unless a clearly historical/non-applicable artifact is technically necessary.

The Development Project has no ChatGPT Project Custom Instructions.

## Repository reconciliation

Update repository-side operating-model, readiness/protected-evidence documentation, templates, references, validators/tests, and related mechanics so they consistently implement the approved target.

Do not reintroduce:

- Lane A/Lane B;
- universal routine task manifests;
- Issue status cockpits;
- permanent acceptance/routing chats;
- exact-next-destination choreography;
- acceptance-only A commits;
- duplicate CI solely for acceptance metadata;
- per-session/worktree pointer restoration as normal workflow.

Historical records may remain historical evidence.

## Dynamic execution-profile semantics

Repository-side governance must reflect that Brainstorming dynamically recommends the tool/surface, model, and reasoning for each meaningful Development launch.

The only durable availability assumption is Ray's ChatGPT Pro membership.

Do not hard-code current model names, model inventories, or reasoning levels into durable governance.

Development follows the task-specific profile supplied in the current launch where available. Model choice does not expand scope or authority.

## Durable-state rule

The four durable instruction surfaces must contain no volatile state such as current SHAs, PR/Issue numbers, active-task status, temporary branch names, live mailbox status, temporary blockers, or current model availability.

## Preserved GOV-16 mechanics

Preserve the already-approved:

- two-way GitHub handoff;
- Initiative Brief + detailed Work Order + short launcher pattern;
- Development Readiness Mailbox and closed disclosure schema;
- durable protected-local project profile/ledger;
- distinct evidence-event semantics;
- Brainstorming runway-preparation responsibility;
- Development prohibition on inventing missing governance authority;
- exact-final-version acceptance model;
- confidentiality, provenance, missingness, target-blindness, grouped-validation, reproducibility, protected-field/egress, protected-characteristic, PR/CI, and Git safety controls.

## Exclusions

Do not:

- resume or modify MODEL-14 analytics;
- resume MODEL-15 protected reconciliation or model execution;
- open fresh targets;
- alter MODEL-13, APP-01, or PBI-02 analytical/product behavior;
- merge PR #45;
- begin any follow-on initiative.

## Validation

At minimum:

- run focused governance/readiness tests;
- run validators/tests for the four-surface instruction architecture and absence of volatile state;
- verify the Development Custom Instructions assumption is removed;
- verify the dynamic execution-profile policy is present without hard-coded model inventory;
- preserve mailbox disclosure-safety tests;
- preserve fresh-session recovery behavior;
- run relevant regression/confidentiality checks showing excluded analytical/product behavior did not change;
- run required full repository CI on the final substantive PR head;
- regenerate and validate the Development Readiness Mailbox against that final source head.

## PR maintenance

Update PR #45 so its description reflects the new final substantive head and no longer describes the superseded `36c0e7a...` implementation as final.

Keep the same initiative, branch, and PR.

## Stop point

Stop with PR #45 open and unmerged at one final substantive commit with passing required CI and a validated mailbox bound to that exact source head.

Return only a short repository-safe completion report with:

- exact final substantive commit;
- PR #45 state;
- exact-head CI result;
- mailbox head/baseline and validation result;
- confirmation the four-surface architecture is implemented;
- confirmation no volatile state/current model inventory is embedded in durable instruction surfaces;
- confirmation the mistaken Development Custom Instructions surface is removed/non-applicable;
- confirmation MODEL-14/MODEL-15 remained preserved and no fresh targets were opened;
- any material deviation from the approved target.

The next step is a focused independent clean-room fidelity recheck. Do not merge.
