# GOV-16 — Post-Review Remediation Work Order

## Status and authority

This is the operative same-initiative remediation Work Order for GOV-16 before coordinated cutover.

It does not create a new initiative.

It operates under the existing GOV-16 Initiative Brief and PR and must be read together with:

- `docs/governance/GOV_16_POST_REVIEW_CORRECTION_SPEC.md`
- `docs/governance/GOV_16_APPROVED_GOVERNANCE_IMPLEMENTATION_TARGET.md`
- `docs/governance/BRAINSTORMING_PROJECT_CUSTOM_INSTRUCTIONS.md`
- `docs/governance/BRAINSTORMING_OPERATING_STANDARD.md`
- the latest exact-candidate `REVIEW` Record in PR #45

The two Brainstorming documents are the exact approved Brainstorming-side texts. The Approved Governance Implementation Target defines the semantics Development must preserve when reconciling repository-side `AGENTS.md`, the Development Operating Standard, references, validators/tests, active-mailbox mechanics, and supporting repository implementation.

Development may make technical/editorial implementation choices that preserve those semantics. It may not redesign or enlarge them.

GitHub comments, PR descriptions, checks, labels, and Launch/Result/Review Records are coordination/evidence only. They cannot enlarge this Work Order or override repository truth.

## Objective

Remediate only the two findings from the focused independent review of exact candidate `264a43bc4bf5eb2809bbb9b5153a7d1615c8a20c`:

1. make evidence-event and fresh-session-recovery recency deterministic and safe when timestamps tie; and
2. remove current repository guidance that implies the Initiative Issue itself grants execution or merge authority.

Preserve all other approved GOV-16 behavior and safeguards.

## Current execution profile

Intended surface: **Codex** in the repository-connected Development Project.

Brainstorming performed a fresh full-suite evaluation using current official OpenAI guidance for ChatGPT Pro on Codex. The current Pro-relevant Codex candidate set is GPT-5.6 Luna, GPT-5.6 Terra, GPT-5.6 Sol, and GPT-6 Astra as Astra rolls out.

For this remediation Brainstorming recommends:

- Model: **GPT-5.6 Sol**
- Reasoning: **Extra High**

Task-specific comparison:

- **Luna:** too light for a correctness-sensitive protected-readiness ledger migration and authority-consistency repair.
- **Terra:** suitable for routine engineering but below the reliability margin warranted by this evidence-ordering defect.
- **Sol:** designed for complex coding/professional work. Extra High is warranted because the prior candidate passed CI yet still contained a subtle recency defect that could misstate protected evidence consumption or readiness.
- **Astra:** strongest option and explicitly considered. The remediation is now narrowly specified with exact failing invariants and required tests; Astra's additional end-to-end capability is not necessary enough to displace Sol Extra High as the lightest adequate option. If Astra is the only stronger option available because Sol/Extra High is unavailable, return to Brainstorming rather than inferring a substitute.

If model availability materially changes before execution, stop and let Brainstorming refresh the recommendation. Model choice does not expand authority.

## Finding 1 — deterministic ledger recency

### Problem

The reviewed candidate orders evidence events by `(occurred_at, event_id)` and fresh-session recovery by `(recovered_at, recovery_id)`. Timestamps have one-second resolution while generated IDs are random UUID-derived strings. Therefore same-second writes can be returned in an order unrelated to the actual write chronology.

This can misstate:

- the current state of evidence events such as `development_used`; and
- the current fresh-session recovery status used by readiness publication.

### Required invariant

For records that share the same semantic timestamp, the ledger must have a durable chronological tie-breaker that reflects write chronology and is independent of logical/random IDs.

The latest-state queries must use that durable chronology so a later same-second write wins over an earlier same-second write.

The implementation may use a versioned monotonic sequence, insertion ordinal, or another technically sound mechanism. Development chooses the implementation, but it must satisfy all requirements below.

### History and migration safety

Preserve every existing evidence event and session-recovery record. Do not delete, rewrite, collapse, or silently replace historical rows merely to establish ordering.

A versioned ledger-schema migration is authorized only as needed to add durable ordering metadata and supporting invariants. The migration must be transactional/fail-closed and must preserve existing logical IDs, timestamps, states, detail codes, repository commits, and other recorded history.

Do not reopen or inspect original protected source/target files for this migration. This remediation may operate only on the existing durable project profile/ledger through its trusted interface.

Do **not** invent chronology for preexisting rows when their true same-timestamp order is not recoverable from data that was durably recorded before this repair. In particular, do not use UUID lexical order, arbitrary iteration order, or an undocumented migration enumeration as semantic history.

For a preexisting latest-timestamp tie whose members conflict and whose actual order cannot be proven:

- evidence-event state must resolve conservatively through an existing or suitably extended non-optimistic/uncertain path rather than silently choosing one conflicting state; and
- fresh-session recovery must not publish stale success. It must resolve to a safe unknown/not-verified or other fail-closed posture consistent with the readiness contract until a later unambiguous recovery record exists.

If all ambiguous tied legacy records agree on the same state, that shared state may be returned because ordering does not change the result.

New writes after migration must always receive sufficient durable ordering metadata to resolve same-timestamp chronology correctly.

### Regression coverage

At minimum add tests proving:

- later same-second `development_used=true` supersedes earlier same-second `false`;
- later same-second `development_used=false` supersedes earlier same-second `true`;
- random/adversarial event IDs cannot change the result;
- later same-second fresh-session `failed` supersedes earlier same-second `passed`;
- later same-second fresh-session `passed` supersedes earlier same-second `failed`;
- random/adversarial recovery IDs cannot change the result;
- migration preserves historical rows and fields;
- a conflicting legacy same-timestamp tie with no durable chronology does not silently resolve by ID/order accident;
- a later post-migration unambiguous record supersedes a legacy ambiguous state;
- readiness publication cannot report `FRESH_SESSION_RECOVERY=READY` from an ambiguous/stale-success tie.

Add migration/version checks and compatibility coverage appropriate to the chosen implementation.

## Finding 2 — Initiative Issue authority consistency

### Required semantic rule

The Initiative Brief Issue records the approved business objective, boundaries, prerequisites, Work Order pointer, and pre-PR coordination evidence. It may serve as the active mailbox before a PR exists.

The Issue body itself does **not** create or enlarge execution authority, acceptance authority, protected-action authority, publication authority, or merge authority.

The operative Work Order is the canonical current execution authority. Consequential acceptance or other reserved decisions belong to the designated authoritative decision/Work Order mechanism, not to Issue/PR comments, labels, checks, or status text.

### Required repository reconciliation

Correct the current Initiative Brief template and current workflow/governance documentation so they do not say or imply that an Issue itself “authorizes” the initiative or is execution authority.

At minimum reconcile:

- `.github/ISSUE_TEMPLATE/initiative-brief.yml`;
- `docs/GITHUB_WORKFLOW_GOVERNANCE.md`;
- any current non-historical governance/template text that uses equivalent Issue-as-authority language; and
- related merge-preauthorization wording.

Merge or ordinary reversible continuation may be pre-authorized only through the operative Work Order or another explicitly designated authoritative decision mechanism. An Initiative Issue may summarize that posture or point to the authority, but it cannot independently grant it.

Do not rewrite historical Issues, historical Work Orders, historical acceptance records, or archived governance merely for consistency.

### Focused consistency validation

Add or extend a focused repository check/test so current active governance/template surfaces cannot regress to wording that makes an Issue, PR description, comment, Result/Review Record, check, or label an independent authority source.

The check must be targeted enough not to treat historical evidence as current governance or to ban ordinary descriptive use of the word `authority` where the hierarchy is clear.

## Preserved GOV-16 architecture

Do not change the approved:

- four durable instruction surfaces;
- Development Readiness Mailbox as machine-generated readiness evidence;
- Issue-to-PR active-mailbox transition;
- concise `LAUNCH`, `RESULT`, and `REVIEW` record semantics;
- Brainstorming-owned runway preparation and full-suite execution-profile selection;
- Development implementation discretion inside prepared authority;
- prohibition on Development inventing missing governance authority;
- durable protected-local profile/ledger and distinct evidence-event semantics;
- exact-final-version review model;
- public/protected disclosure boundary;
- provenance, explicit missingness, target-blindness, physical-location-grouped validation, reproducibility, egress/allowlist controls, protected-characteristic restrictions, PR/CI controls, and Git preservation safeguards.

## Local-state and readiness handling

Before changing the durable ledger, inspect and preserve current local state using the trusted project profile/ledger interface and preserve unrelated work.

The existing readiness snapshot is valid evidence for the reviewed candidate but becomes stale once this remediation changes the source head. After final remediation:

1. establish one final substantive source commit;
2. run the required exact-head repository validation;
3. run fresh-session recovery as required by the readiness contract;
4. regenerate the Development Readiness Mailbox from that exact final source head;
5. validate and push the mailbox refresh; and
6. confirm the published snapshot names that exact source head.

The existing incomplete original-source inventory/evidence-ledger completeness posture remains a nonblocking `NEEDS_RUNWAY` condition for this governance remediation unless this repair itself uncovers a new safety/integrity blocker. Do not promote those prerequisites to `READY` as part of this task.

## Exclusions

Do not:

- resume or modify MODEL-14 analytics;
- resume MODEL-15 protected reconciliation or model execution;
- open fresh targets;
- alter MODEL-13, APP-01, or PBI-02 analytical/product behavior;
- infer or repair source-evidence chronology beyond the ordering defect authorized above;
- reopen original protected sources;
- merge PR #45;
- begin any follow-on initiative;
- turn active-mailbox records into authority or a workflow state machine.

## Validation

At minimum:

- run focused ledger recency/migration tests described above;
- run focused governance-authority consistency checks;
- run readiness/disclosure/fresh-session recovery tests affected by the ledger change;
- preserve all existing confidentiality and path-containment tests;
- run relevant regression checks demonstrating excluded analytical/product behavior is unchanged;
- inspect the complete diff for protected or unrelated material;
- run required full Repository Validation on the final substantive PR head;
- regenerate and validate the Development Readiness Mailbox against that exact head.

Any substantive repair after independent re-review requires another exact-candidate review.

## PR maintenance and active mailbox

Keep the same initiative, branch, and PR #45.

The PR conversation remains the active candidate mailbox. Do not mirror remediation chronology into Issue #44.

Update the PR description to the new final substantive head and current validation/mailbox evidence.

Before returning control to Brainstorming, post a new concise `RESULT` Record to PR #45 containing:

- exact final candidate head;
- concise description of the ledger-ordering and authority-wording repairs;
- validation/CI status;
- refreshed readiness-mailbox commit/source binding;
- preserved safeguards/exclusions;
- any unresolved gap/deviation; and
- next control point: focused independent re-review of the new exact candidate.

The prior `REVIEW — REWORK REQUIRED` Record remains historical evidence for the reviewed `264a43bc...` candidate and must not be edited or replaced.

## Stop point

Stop with PR #45 open and unmerged at one new final substantive commit with passing required exact-head CI and a validated Development Readiness Mailbox bound to that exact source head.

Post the new concise `RESULT` Record to the PR mailbox and return only a minimal user-facing acknowledgment that durable result evidence was posted.

The next control point is focused independent re-review of the new exact candidate, followed by a new concise `REVIEW` Record in PR #45. Do not merge.