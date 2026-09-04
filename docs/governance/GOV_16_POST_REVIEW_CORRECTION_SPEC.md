# GOV-16 Post-Review Correction Specification

## Status

This is a substantive correction to the existing GOV-16 initiative after clean-room review and before cutover. It does not create a new initiative. GitHub Issue #44 and PR #45 remain the governing Initiative Brief and implementation PR.

This specification supersedes only the parts of the existing GOV-16 Work Order and PR implementation that assume the repository-connected Development Project can have ChatGPT Project Custom Instructions. That assumption is false.

All other approved GOV-16 design decisions remain unchanged unless this specification expressly changes them.

## Correct instruction architecture

The project uses four durable instruction surfaces with a strict constitutional/playbook split.

### Brainstorming Project

The cloud Project `Sprouts Customer Geography` has:

1. **Brainstorming Project Custom Instructions** — concise, always-on constitutional rules.
2. **Brainstorming Operating Standard** — the detailed playbook for applying those rules.

The Custom Instructions define durable purpose, role boundaries, non-negotiable safety/authority rules, GitHub/readiness-mailbox principles, runway-preparation responsibility, and when Ray must decide.

The Brainstorming Operating Standard defines the practical workflow for recovering state, reviewing GitHub and the Development Readiness Mailbox, preparing prerequisites, making decisions with Ray, creating Initiative Briefs and Work Orders, launching Development, reviewing results, remediation, exact-version acceptance, publication/promotion decisions, and closeout.

The Operating Standard may elaborate on the Custom Instructions but may not contradict or override them.

The Brainstorming Custom Instructions should require consulting the Brainstorming Operating Standard before consequential or authority-bearing actions.

### Development Project

The repository-connected Development Project does **not** have ChatGPT Project Custom Instructions.

Its corresponding durable instruction surfaces are:

1. **`AGENTS.md`** — the concise repository-level constitutional executor contract.
2. **Development Operating Standard** — the detailed repository-execution playbook.

`AGENTS.md` defines durable role boundaries, non-negotiable safety rules, Git/protected-data rules, the prohibition on inventing missing authority, and when Development must stop and return a precise gap.

The Development Operating Standard defines the practical workflow for startup/recovery, Initiative Brief + Work Order reading, GitHub/local reconciliation, local-work preservation, protected-local recovery, scoped execution, testing, mailbox refresh, PR maintenance, remediation, exact-version handling, and completion/return to Brainstorming.

`AGENTS.md` should require consulting the Development Operating Standard before consequential or authority-bearing execution.

## No volatile state in durable instruction surfaces

None of these four instruction surfaces may contain volatile project state, including:

- current task/initiative status;
- current SHA values;
- current PR or Issue numbers;
- temporary branch names;
- live mailbox status;
- current model availability/readiness;
- temporary blockers;
- present-tense claims about MODEL-13/14/15 or other active work.

Those facts must be recovered from the actual project systems when needed: GitHub, the Development Readiness Mailbox, repository-safe current-state records, the local repository, and the protected-local profile/ledger as applicable.

## Brainstorming responsibility remains unchanged and is reinforced

Brainstorming owns preparing the runway before launching Development.

Before meaningful work, Brainstorming must use current GitHub plus a fresh validated Development Readiness Mailbox to determine:

- relevant accepted repository authority;
- active/conflicting initiatives;
- preserved local work reported safely by the mailbox;
- prerequisite readiness;
- permitted evidence/access classes;
- scope and exclusions;
- success criteria;
- decisions reserved for Ray.

An incomplete prerequisite is a Brainstorming runway-preparation problem. Brainstorming must prepare or separately authorize the missing prerequisite, request a bounded readiness refresh, or defer the objective. Development must not be given broad governance discretion to invent missing access, evidence, permissions, methodology, product semantics, or scope.

## GitHub two-way handoff remains unchanged

The approved two-way flow remains:

1. Development completes meaningful work and refreshes the repository-safe Development Readiness Mailbox.
2. Brainstorming reads GitHub and the validated mailbox.
3. Ray and Brainstorming decide the next substantive objective.
4. Brainstorming writes the Initiative Brief and detailed Work Order to GitHub.
5. Ray receives only a short launcher.
6. Development reads the Initiative Brief and Work Order, checks GitHub and local state, validates the prepared pathway, and executes only that authority.
7. Development records repository-safe results in the PR and refreshes the mailbox before return.
8. Brainstorming reviews GitHub and the safe local summary before the next decision.

## Required PR #45 corrections

Revise the current GOV-16 implementation so that:

1. `docs/governance/BRAINSTORMING_PROJECT_CUSTOM_INSTRUCTIONS.md` remains, but is tightened if needed so it is concise, constitutional, durable, and free of volatile state.
2. Add `docs/governance/BRAINSTORMING_OPERATING_STANDARD.md` containing the detailed Brainstorming playbook.
3. Remove `docs/governance/DEVELOPMENT_PROJECT_CUSTOM_INSTRUCTIONS.md` as a proposed active instruction surface. If retained for historical traceability, it must be clearly marked superseded/non-applicable; deletion is preferred if nothing requires it.
4. `AGENTS.md` becomes the Development constitutional layer and remains concise/durable.
5. Add `docs/governance/DEVELOPMENT_OPERATING_STANDARD.md` containing the detailed Development playbook.
6. Update `docs/OPERATING_MODEL.md`, protected-evidence/readiness documentation, README links, templates, tests, and any other references so the hierarchy is explicit and consistent.
7. No current task state, SHA, PR number, mailbox status, or temporary model readiness may be embedded in the four durable instruction surfaces.
8. The readiness mailbox, Initiative Brief + Work Order handoff, durable protected-local profile/ledger, evidence semantics, and retired old-governance constructs remain as already approved.

## Brainstorming Custom Instructions content standard

Keep them concise enough to function as always-on constitutional rules. They should cover only durable points such as:

- project purpose and public-proxy boundary;
- Ray as substantive business decision-maker;
- Brainstorming as decision/runway/prompt-authoring workspace;
- cloud boundary: GitHub and repository-safe readiness only, no claim of desktop/protected inspection;
- mandatory current-state recovery from GitHub + validated mailbox before meaningful runway preparation;
- Brainstorming responsibility to prepare prerequisites rather than silently delegating missing authority;
- Initiative Brief + Work Order + short-launch pattern;
- Ray-reserved decision classes;
- confidentiality and key analytical safeguards;
- requirement to consult the Brainstorming Operating Standard before consequential actions;
- requirement to review exact PR/CI/mailbox evidence before acceptance or next-step recommendation.

Do not duplicate the detailed procedural playbook in Custom Instructions.

## Brainstorming Operating Standard content standard

The Brainstorming Operating Standard should explain, in practical order:

- how to recover current GitHub orientation and validate mailbox freshness/baseline;
- how to reconcile proposed work with accepted authority, active initiatives, and readiness;
- how to identify and prepare missing prerequisites;
- how to decide with Ray what should happen next;
- when to create an Initiative Brief versus continuing an existing initiative;
- how to write a complete repository-safe Work Order;
- how to create the short Development launcher;
- how to handle Development-reported runway gaps;
- how to review PR/CI/mailbox results;
- how to handle remediation without making Ray splice prompts;
- how consequential exact-version acceptance works;
- when publication/promotion requires Ray;
- how to close an initiative and select the next substantive action;
- how to avoid recreating lanes, status cockpits, acceptance-only commits, routing choreography, or other retired ceremony.

## Development Operating Standard content standard

The Development Operating Standard should explain, in practical order:

- startup reading order: Initiative Brief, Work Order, GitHub, local repo, `AGENTS.md`, Development Operating Standard, relevant accepted config/schema/method authority, mailbox, then authorized protected-local state;
- preserving uncommitted/unpushed local work;
- comparing GitHub/local/mailbox baselines;
- validating that Brainstorming's prepared pathway exists locally;
- executing only the supplied scope while retaining implementation discretion;
- returning precise gaps rather than inventing authority;
- protected-local recovery and evidence-event recording;
- synthetic-first behavior where appropriate;
- testing/CI expectations;
- bounded remediation/correction handling;
- PR maintenance and exact-final-version stop points;
- readiness-mailbox refresh/validation before return;
- short completion reporting;
- prohibition on follow-on work, deployment, publication, destructive action, or new authority without Brainstorming/Ray.

## Validation and review consequence

This correction is substantive governance content after the prior clean-room PASS. Therefore:

- produce a revised exact PR #45 head;
- run relevant focused governance/readiness tests and full required CI on that exact head;
- regenerate and validate the readiness-mailbox snapshot against the revised exact source head;
- preserve all existing analytical exclusions and paused work;
- do not merge;
- return the revised exact head and validation evidence for a focused clean-room fidelity recheck.

The prior clean-room PASS applies only to the prior exact head and does not authorize cutover of a revised head.

## Preserved exclusions

Do not resume or modify MODEL-14 analytics.
Do not resume MODEL-15 protected reconciliation or model execution.
Do not open fresh targets.
Do not alter MODEL-13/APP-01/PBI-02 analytical/product behavior as part of this correction.
Do not weaken the confidentiality or analytical safeguards already accepted in GOV-16.

## Stop point

Stop at revised PR #45 exact substantive head with passing CI and a validated mailbox bound to that exact head.

Return a short completion report with:

- revised exact commit SHA;
- PR #45 state;
- CI result;
- mailbox exact head and validation result;
- confirmation the four-surface instruction architecture is implemented;
- confirmation durable instruction surfaces contain no volatile state;
- confirmation MODEL-14/MODEL-15 remain preserved and no fresh targets were opened;
- any material deviation from this correction specification.

The next step is a focused clean-room fidelity review of the revised exact head.