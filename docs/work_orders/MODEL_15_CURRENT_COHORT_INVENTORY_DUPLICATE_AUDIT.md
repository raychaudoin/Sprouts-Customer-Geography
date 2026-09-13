# MODEL-15 — Current MI/WI Sprouts Cohort Inventory and Duplicate Audit

## Purpose

Answer two business questions before any further model improvement work:

1. Which Michigan and Wisconsin Sprouts examples are actually being used by the currently accepted customer-geography model?
2. Are any physical locations or forecasts being duplicated, double-counted, or overweighted because the same underlying evidence appears more than once?

This is a bounded integrity audit of the accepted MODEL-13 development/fitting cohort. It is not a model-change task.

## Initiative and current baseline

- Initiative: MODEL-15 / Issue #43.
- Repository baseline for this authority: canonical `main` at `71beaa5e3d82625de9aa2c300dca3a56ff2a9399` after GOV-16 cutover.
- Development Readiness Mailbox reports the protected project profile and MODEL-13 authority as recoverable/ready, fresh-session recovery succeeded, and preserved MODEL-15 local work exists.
- Published accepted MODEL-13 accounting is 196 fitting observations / 123 physical locations, with Michigan 133 / 82 and Wisconsin 63 / 41. Treat those numbers as a baseline to reproduce or explain, not as a substitute for reconstructing the actual accepted cohort.

## Execution authority

Development is authorized to use the trusted protected-local project profile, asset catalog, evidence ledger, and registered accepted MODEL-13 authority needed to reconstruct the already-consumed fitting cohort.

Development may recover and preserve the existing MODEL-15 local work and use or complete bounded local helper tooling necessary for this audit. It may reconcile that preserved work with current canonical `main` without discarding unrelated safe work.

Development must not require Ray to restore filesystem paths or manually identify protected files. If the trusted registered state is insufficient, stop and report the exact missing readiness fact rather than falling back to arbitrary recursive discovery.

## Required analysis

Reconstruct the accepted MI/WI fitting cohort from authoritative local records and produce the following accounting:

- total fitting observations and unique physical locations, pooled and by state;
- every physical location represented more than once in the fitting cohort;
- for each repeated physical location, distinguish:
  - legitimate distinct forecast vintages / target definitions;
  - the same physical-location × forecast-vintage × target-definition represented more than once;
  - overlap caused by multiple protected source generations or lineage aliases;
  - unresolved identity ambiguity that cannot safely be classified;
- number of exact or suspected duplicate groups and number of observations implicated;
- whether any duplicate/overlap changes the effective weighting of a physical location in fitting or evaluation, while preserving the existing physical-location-grouped validation definition;
- whether the reconstructed cohort matches the published accepted MODEL-13 accounting, and if not, explain the discrepancy without changing the cohort.

The canonical evidence unit for duplicate analysis is state-qualified physical location × forecast vintage × target definition. Physical location alone is also required as a business-facing rollup so Ray can see whether a store appears multiple times even when the vintages are legitimately distinct.

## Protected evidence rules

- Restrict the audit to evidence already consumed by the accepted MODEL-13 fitting cohort and the identity/lineage metadata necessary to reconcile it.
- Do not open or consume fresh target evidence.
- Do not expand into pursued-site Sprouts forecasts/scores, Seed Point changes, sealed/prospective/validation-only evidence, or other unused target rows in this phase.
- Machine access does not imply analytical use. Preserve distinct evidence-event semantics for located, identity-read, target machine-read, target visible, analytically used, validation-used, development-used, and disclosed.
- Do not put protected paths, target values, source-row identities, addresses, coordinates, registries, or reconstructable protected lineage into Git or GitHub.
- Any private user-facing duplicate list should use only the minimum already-permitted familiar business identifier needed for Ray to understand which physical sites are implicated; do not disclose target values.

## Decision boundary

Do not remove duplicates, choose among competing source rows, alter the accepted cohort, refit the model, rerun performance metrics on a corrected cohort, or modify MODEL-14 based on this audit.

If duplicates or ambiguous overlaps are found, stop after documenting what they are and their scope. Brainstorming/Ray will decide the correction rule and whether a model rerun is warranted.

If no duplicates are found, report that clearly and show the accounting that supports the conclusion.

## Pursued-site forecasts

The separate Sprouts forecasts/scores for sites Ray was actively pursuing are intentionally outside this audit. Do not classify them as fitting evidence or add them to the cohort. Their inventory and possible use will be handled after this current-cohort integrity question is settled.

## Repository and result handling

- Issue #43 is the active mailbox unless/until a PR is created.
- A PR is not required merely to perform the protected-local audit. If repository changes are genuinely needed for reproducible audit tooling, keep them narrowly limited to MODEL-15 audit tooling/tests and open a PR; the PR conversation then becomes the active mailbox.
- Post one concise repository-safe `RESULT` Record to the active mailbox when the audit is complete or blocked.
- The `RESULT` must include only safe aggregate findings: reconstructed observation/location counts, count of repeated-location groups, count of same-vintage/target duplicate groups, count of source-generation overlap groups, count of unresolved groups, whether published MODEL-13 accounting reproduced, whether any fitting/evaluation weighting concern exists, and any readiness blocker.
- Return a private user-facing business summary to Ray explaining: what is in the model, whether anything is double-counted, and what decision (if any) is needed next.

## Validation / success criteria

Success requires:

1. the accepted fitting cohort is reconstructed from authoritative registered state rather than inferred from public summaries;
2. pooled, Michigan, and Wisconsin observation/location accounting is explicit;
3. repeated physical locations are separated from true duplicate physical-location × vintage × target records;
4. multiple-source-generation overlap is explicitly tested rather than assumed;
5. unresolved identity cases fail closed rather than being silently merged or counted as clean;
6. no fresh target evidence is consumed;
7. no model, metric, or MODEL-14 result is changed;
8. protected information remains outside public Git/GitHub; and
9. Ray receives a plain-English answer to business questions 1 and 2.

## Current execution profile

Recommended surface: repository-connected Development / Codex.

Recommended model: GPT-6 Astra, High reasoning, if available. This audit combines protected-state recovery, identity/lineage reconciliation, and potentially subtle duplicate classification; a false clean bill of health would materially distort later model decisions. Astra is preferred because the reliability benefit is material for this long-horizon, consequence-sensitive reconciliation. Luna and Terra are too light for the identity/evidence-integrity judgment required here. GPT-5.6 Sol is capable and is the fallback.

Fallback: GPT-5.6 Sol, Extra High reasoning (or the highest Sol reasoning setting available on the Development surface).

Fresh official OpenAI availability guidance was checked for this launch on 2026-09-12. If the actual Development surface materially differs at launch, use the strongest available fallback above rather than inventing a different execution profile.

## Stop point

Stop when Ray can be told, in plain business language:

- exactly how many MI/WI Sprouts examples and unique physical locations the accepted model is using;
- how many physical locations appear more than once and why;
- whether any records are true/suspected duplicates or source-generation overlaps; and
- whether a correction decision is needed before we continue improving the model.
