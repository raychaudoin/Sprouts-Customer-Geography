# GOV-16 — Approved Governance Implementation Target

## Purpose

This document defines the governance semantics Brainstorming has approved for repository implementation.

Development may make technical, editorial, structural, and testing choices necessary to integrate these requirements cleanly into the actual repository.

Development may not alter their meaning.

This document is operative GOV-16 correction authority together with `docs/governance/GOV_16_POST_REVIEW_CORRECTION_SPEC.md` and the GOV-16 Work Order. GitHub Issue comments are mailbox/evidence only unless one of those operative authority surfaces expressly incorporates them.

## Authority architecture

The durable instruction architecture is:

### Brainstorming side

- Brainstorming Project Custom Instructions = constitutional layer.
- Brainstorming Operating Standard = practical playbook.

### Development side

- `AGENTS.md` = repository constitutional executor layer.
- Development Operating Standard = practical repository-execution playbook.

The Development Project itself has no ChatGPT Project Custom Instructions.

The constitutional layer controls when there is conflict with its corresponding Operating Standard.

Operating Standards elaborate but do not override constitutional rules.

None of these four durable instruction surfaces may contain volatile project state such as current SHAs, PR/Issue numbers, task status, temporary branch names, live mailbox status, temporary blockers, or current model availability.

## Approved Brainstorming texts

The exact approved Brainstorming-side texts are:

- `docs/governance/BRAINSTORMING_PROJECT_CUSTOM_INSTRUCTIONS.md`
- `docs/governance/BRAINSTORMING_OPERATING_STANDARD.md`

These are the semantic source for Development’s repository-side reconciliation. Development may update repository references or formatting around them but must not change their governance meaning.

## Roles

### Brainstorming

Brainstorming owns:

- product/model decision support with Ray;
- governance semantics;
- runway preparation;
- prerequisite identification;
- authority/evidence boundaries;
- Initiative Brief and Work Order authoring;
- short Development launch generation;
- dynamic tool/model/reasoning recommendation;
- review of repository-safe results;
- recommendations for acceptance, promotion, remediation, and next work.

### Development

Development owns:

- technical repository implementation;
- local/GitHub reconciliation;
- local-work preservation;
- implementation choices within the approved pathway;
- tests and CI;
- protected-local recovery when authorized;
- evidence-event recording;
- readiness-mailbox refresh/validation;
- commits/pushes/PR maintenance within supplied authority;
- repository-safe completion evidence.

Development does not invent missing governance authority.

If completion requires new evidence, access, methodology, scope, permissions, product semantics, analytical authority, deployment, publication, or destructive action not supplied by the operative authority, Development returns the precise gap.

## GitHub handoff

GitHub is the repository-safe intermediary between Brainstorming and Development.

For meaningful work:

1. Brainstorming reads current GitHub and the validated Development Readiness Mailbox.
2. Brainstorming/Ray decide the objective.
3. Brainstorming prepares prerequisites and authority.
4. Brainstorming records approved intent in an Initiative Brief and detailed authority in the designated operative Work Order/decision record.
5. Ray receives a short launcher.
6. Development reads the durable authority, validates it against GitHub/local reality, and executes.
7. Development records repository-safe implementation evidence in the PR.
8. Development refreshes/validates the Readiness Mailbox.
9. Brainstorming reads those results before the next decision.

A GitHub comment does not become operative authority merely because it contains instructions. Repository implementation must preserve a clear designated authority surface.

## Development Readiness Mailbox

Retain the GOV-16 readiness-mailbox design.

The mailbox must:

- publish only allowlisted repository-safe readiness facts;
- expose freshness and source-baseline binding;
- be machine-generated through the approved publisher;
- reject unknown/disallowed fields and protected disclosure classes;
- avoid protected paths, revealing filenames, addresses, coordinates, target values, row identities, registry contents, credentials, or reconstructable protected lineage.

Brainstorming relies only on mailbox state that has passed the appropriate validator and is appropriately bound to the relevant source baseline.

The mailbox exists to let Brainstorming prepare future runways proactively.

## Protected-local durable state

Retain the durable local project profile/ledger design.

It must support recovery of authorized project state without routine Ray path restoration and without arbitrary recursive inspection of protected candidate files.

It must support evidence units and events sufficient to determine which protected evidence influenced which model lineage.

Preserve distinct semantics for:

- located;
- identity-read;
- target machine-read;
- target visible;
- analytically used;
- validation-used;
- development-used;
- disclosed.

Do not automatically promote one event into another.

## Runway-preparation invariant

Missing prerequisites should normally be discovered by Brainstorming through GitHub + readiness evidence before the main Development launch.

An incomplete prerequisite is not delegated to Development as open-ended problem solving.

Development may solve technical implementation problems within supplied authority.

Development may not solve missing governance authority by expanding the pathway.

## Initiative / Work Order behavior

Retain Initiative Briefs for meaningful objectives.

Do not turn them into synchronized status cockpits.

Retain detailed Work Orders for meaningful execution where durable detailed authority is needed.

Do not require a universal manifest/state-machine for routine work.

Historical manifests/work orders remain historical evidence and do not need rewriting.

## Dynamic execution-profile policy

Brainstorming must recommend tool/surface, model, and reasoning level dynamically for each meaningful Development launch.

The only durable availability assumption is that Ray has ChatGPT Pro.

When selection is material, Brainstorming should consult current official OpenAI guidance and recommend the **lightest adequate current option** for the specific task.

The recommendation should consider:

- task complexity;
- ambiguity;
- consequence of error;
- repository/coding depth;
- long-horizon reasoning requirements;
- cost/latency.

Durable repository governance must not hard-code current model names, inventories, or reasoning levels.

The launcher should carry the current recommendation and concise rationale.

Development does not substitute a different execution profile merely because it prefers one, unless the selected option is unavailable; if unavailable, it should use an explicitly permitted fallback or report the availability gap.

## Safeguards that must remain

Do not weaken:

- public/protected disclosure separation;
- source/vintage/schema/transformation provenance;
- explicit missingness and prohibition on silent zero-fill;
- target-blind feature/evaluation freezes;
- physical-location-grouped validation;
- deterministic/reproducible runs;
- protected-field allowlists and egress controls;
- protected-characteristic restrictions;
- protected-main/PR/CI safeguards;
- exact-final-version review for consequential decisions;
- Git safety against destructive loss of user work.

## Failure handling

Development should recover technical execution failures that are clearly within supplied authority.

Examples include:

- test retries;
- CI retries;
- transient network/tool issues;
- ordinary branch/worktree reconciliation;
- bounded implementation corrections;
- recoverable registered-asset relocation where trusted recovery rules already authorize it.

Development should stop the dependent stage and return a precise gap for:

- missing evidence authority;
- missing protected access authority;
- unresolved substantive evidence conflict;
- methodology/product-semantic change;
- unprepared prerequisite;
- fresh evidence not authorized;
- destructive/publication/deployment authority;
- genuine risk of losing user work.

Do not convert a governance gap into broad executor discretion.

## Consequential exact-version model

Preserve this lifecycle:

1. final substantive version;
2. validation/CI on that exact version;
3. exact-version acceptance by Ray or named reviewer;
4. any substantive change invalidates that acceptance;
5. unchanged accepted version may merge when authorized.

No acceptance-only A commit.

No duplicate full CI solely for acceptance metadata.

Ordinary reversible work may have merge authority pre-authorized by the operative Work Order.

## Repository implementation requirements

Development should:

- make `AGENTS.md` concise and constitutional;
- create a Development Operating Standard with detailed execution procedures;
- implement/reference the approved Brainstorming Custom Instructions and Operating Standard as repository-safe governance artifacts;
- update operating-model/readiness/protected-evidence documentation for consistency;
- remove or clearly supersede the mistaken Development Project Custom Instructions artifact;
- preserve the readiness mailbox and protected-local mechanics;
- update validators/tests to enforce meaningfully testable invariants;
- avoid tests whose only purpose is recreating retired lifecycle ceremony.

Development may improve organization and wording so long as the semantics above remain unchanged.

## Independent review acceptance criteria

Independent review must verify both:

### Fidelity

- Brainstorming remains responsible for runway preparation.
- Development cannot invent missing governance authority.
- the constitutional/playbook split is implemented correctly;
- no volatile state appears in durable instruction surfaces;
- dynamic model/reasoning policy is present without hard-coded model inventory;
- GitHub is an intermediary/evidence bridge, not accidental authority;
- retired governance machinery has not quietly returned.

### Technical soundness

- readiness mailbox safety and validation remain effective;
- fresh-session local recovery remains effective;
- protected-state controls remain safe;
- repository validation passes;
- analytical/product behavior excluded from GOV-16 remains unchanged.

## Cutover condition

Do not cut over merely because documentation exists.

Cutover is ready only when:

- repository implementation matches this approved target;
- required CI passes on the revised exact substantive version;
- mailbox is regenerated and validated against that version;
- independent review passes;
- Brainstorming Custom Instructions and Brainstorming Operating Standard are ready to activate together;
- no excluded analytical work was resumed.
