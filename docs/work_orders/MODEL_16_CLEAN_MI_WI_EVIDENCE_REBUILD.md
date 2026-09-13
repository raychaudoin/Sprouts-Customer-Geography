# MODEL-16 — Clean Michigan/Wisconsin Evidence Rebuild

## Objective

Rebuild the Michigan/Wisconsin customer-geography model from the complete clean evidence package Ray prepared, while preserving honest independent tests of the rebuilt model.

The business questions are:

1. Can the current accepted model be reproduced or improved when it is rebuilt from a clean, explicitly defined evidence set?
2. Which combination of accepted public-data features and bounded model methods performs best without overfitting?
3. Does the frozen rebuilt model generalize to later Seed Points and separately prepared pursued-site forecasts?

This is a rebuild and experiment. It does not accept, promote, or replace MODEL-13 by itself.

## Controlling baseline

- Canonical repository baseline: `main` after GOV-16 cutover.
- MODEL-13 remains the accepted model until Ray explicitly accepts a successor.
- MODEL-14 Generation 2 remains a frozen exploratory result and must not be overwritten.
- Preserved MODEL-15 local work must not be lost or silently reused as authority.

## Authorized protected evidence package

Ray has prepared three immutable local workbooks together inside one bounded rebuild-evidence directory under the authorized Sprouts protected root.

Register them in the protected project catalog and evidence ledger using these logical asset IDs only:

- `MI_SEED_FORECASTS_2024_2026_V1`
- `WI_SEED_FORECASTS_2024_2026_V1`
- `MI_WI_PURSUED_SITES_2025_ISOLATED_V1`

Do not copy the workbooks, their paths, filenames, values, addresses, coordinates, row identities, or hashes into Git/GitHub. Do not relocate them unless the trusted protected-local profile requires a registered immutable copy inside the same authorized protected root; if so, preserve originals and use a deterministic registered copy operation.

Use only the exact directory Ray supplied in the Development launcher. Do not scan other protected folders or search recursively for substitutes.

## Expected source shape

Validate before any target-conditioned work:

- Michigan Seed Points: 139 rows — 49 from 2024, 52 from 2025, 38 from 2026.
- Wisconsin Seed Points: 65 rows — 21 from 2024, 20 from 2025, 24 from 2026.
- Pursued sites: 36 rows — 17 Michigan, 19 Wisconsin, all 2025 isolated forecasts.
- Each workbook has one data sheet and 12 source columns.
- The Michigan Seed Point workbook uses `City2`; normalize it to canonical `City` without changing the source workbook.
- The pursued-site workbook places human-readable site names in `Seedpoint_ID`. Treat these as `source_site_name`, not Seed Point IDs. Keep canonical `seedpoint_id` null for pursued sites.
- All three sources must have complete `Year`, state, latitude, longitude, MSA, and `Isolated Sales` for admitted rows.

If these aggregate expectations do not match, stop before modeling and report the safe discrepancy.

## Allowed target and prohibited fields

The only permitted target is `Isolated Sales`.

`Impacted Sales` is prohibited from modeling use. Do not use it as a target, feature, filter, tie-breaker, diagnostic, selection signal, or interpretive input. Project the allowed columns before target loading so impacted values do not enter analytical memory or artifacts.

Do not use protected characteristics as scoring inputs.

## Identity and duplicate rules

### Seed Points

- The canonical observation identity begins with state-qualified Seed Point ID plus forecast year.
- The same Seed Point/location in different years is a legitimate separate observation because the forecast year matters.
- Never use a 2,000-foot rule to merge or remove same-year Seed Points.
- Within one year, exact repeated state + Seed Point ID or exact repeated coordinates are duplicate candidates and must fail closed for reconciliation.
- Link the same physical location across years through the exact Seed Point identity and coordinates, retaining each yearly observation.

### Pursued sites

- Treat each cleaned row as one pursued-site forecast.
- Do not invent Seed Point IDs.
- Use the supplied site name, address when present, state, and coordinates for target-blind identity.
- Exact duplicate coordinates or duplicate normalized site identities within the pursued-site source must fail closed.

### Cross-source identity

- Determine whether a pursued site and a Seed Point represent the same underlying physical location using target-blind evidence only.
- Distance may flag a candidate match but may not decide identity by itself.
- Preserve the distinction between evidence class (`SEED_POINT` versus `PURSUED_SITE`) even when physical identity is shared.
- Every observation from the same physical location must remain in the same validation group.
- A pursued-site score matching a Seed Point location may not be represented as an independent external test of a model trained on that location. Report matched and unmatched pursued-site results separately.

## Evidence roles and chronology

Freeze identity rules, feature definitions, transformations, eligibility, missingness treatment, folds, metrics, candidate set, and selection rules before reading any held-out target values.

Use the evidence in these roles for Generation 1:

### Development evidence

Use 2024 and 2025 Seed Point isolated forecasts for model fitting and model selection.

All yearly observations for one physical location must remain in one fold. Give each physical location equal total fitting weight; divide that weight across its admitted yearly observations.

### Independent temporal test

Keep all 2026 Seed Point isolated forecasts sealed until the candidate definitions and selection rule are frozen. The 2026 Seed Points are a separate later-location test and must not influence feature choice, model tuning, thresholds, exclusions, or stopping.

### Independent pursued-site test

Keep all pursued-site isolated forecasts sealed until the same freeze. Report the pursued-site results separately from Seed Points and separately for:

- pursued sites independent of every development location;
- pursued sites linked to a Seed Point physical location;
- Michigan and Wisconsin.

Do not use pursued-site targets to improve Generation 1 after seeing their results. Any later decision to consume pursued-site evidence for development requires a new descendant generation and an explicit Ray decision.

Ray explicitly authorizes controlled access to the 2026 Seed Point and pursued-site isolated targets only after the required freeze, for the bounded evaluations above.

## Public feature and model candidates

First reproduce the accepted public-feature processing and estimator behavior on the clean development evidence as the baseline.

Predeclare and compare a bounded candidate set that includes at minimum:

1. the accepted MODEL-13 public feature set and estimator;
2. the accepted MODEL-13 feature set plus the 11 frozen MODEL-14 commercial intensity/count features, excluding the four mix/diversity features;
3. ridge and elastic-net versions of those two target-blind feature sets, with tuning nested entirely inside grouped development folds.

Development may make ordinary implementation choices inside these candidate definitions, but may not add a new public source, change geography semantics, use future-vintage public data selected because of target performance, introduce a high-capacity nonlinear model, or alter the target definition without returning to Brainstorming/Ray.

Use existing accepted/frozen public source definitions and vintages for Generation 1 so evidence-set effects can be interpreted. Do not silently refresh source vintages.

## Metrics and selection

Use deterministic physical-location-grouped nested validation on the 2024–2025 development evidence.

Report, pooled and separately for Michigan/Wisconsin:

- Spearman rank correlation;
- Kendall tau-b;
- log RMSE;
- level MAE;
- paired-fold differences against the clean MODEL-13-method baseline;
- coefficient/selection stability where applicable;
- sensitivity to the worst-error physical location;
- effective observation and physical-location counts.

Select at most one frozen challenger before opening held-out targets. The selection must consider ranking and error together, state consistency, fold consistency, stability, and parsimony. A numerically stronger pooled result that materially degrades one state or depends on one location is not a credible improvement.

After the freeze, evaluate the baseline and frozen challenger once on the 2026 Seed Point test and once on the pursued-site test. Do not retune.

## Required protected-local records

Create durable protected-local records sufficient to answer, for every model candidate:

- exact source workbook logical ID;
- observation/evidence-unit membership;
- evidence class and role;
- state, forecast year, and physical-location group;
- whether the observation was development-used, temporal-test-used, pursued-site-test-used, excluded, or unresolved;
- candidate/model genealogy;
- target-access and analytical-use events.

The original source inventory and evidence ledger should become `READY` for this bounded rebuild package only when these records are complete and validated. Do not claim project-wide completeness beyond the registered package.

## Repository work

Development may:

- create a normal task branch and PR from current canonical `main`;
- implement loaders, schema validation, identity reconciliation, evidence registration, modeling/evaluation code, tests, reports, and safe aggregate outputs;
- preserve and reuse accepted public feature code where appropriate;
- run deterministic local validation and required CI;
- commit, push, and maintain the task PR;
- refresh and validate the Development Readiness Mailbox against the final candidate;
- perform bounded mechanical remediation that does not change the business/methodological rules above.

Development must not:

- modify or overwrite accepted MODEL-13 artifacts;
- modify the frozen MODEL-14 result;
- use the prior MODEL-15 reconstruction as evidence authority unless reconciled to this new package;
- expose protected data in Git/GitHub;
- use impacted forecasts;
- access any protected target outside the three registered workbooks;
- promote, accept, deploy, or merge a successor model;
- begin a second generation after seeing held-out results.

## Tests and validation

At minimum, test:

- exact source schema and expected aggregate row counts;
- `City2` to `City` normalization;
- pursued-site names never becoming Seed Point IDs;
- field allowlists that exclude `Impacted Sales` values;
- duplicate and identity rules above;
- no distance-based same-year Seed Point merging;
- different Seed Point years retained as distinct observations;
- physical-location grouping and equal total location weight;
- holdout target blindness before freeze;
- cross-source matched-location segregation;
- deterministic materialization and reruns;
- missingness preservation with no silent zero-fill;
- no protected material in tracked files, logs, PR text, reports, or readiness output;
- exact-head Repository Validation.

## Required result

Return a plain-English business summary and repository-safe detailed report covering:

1. the admitted evidence counts and physical-location counts by state, year, and evidence role;
2. any exact duplicates, identity conflicts, exclusions, or cross-source location matches;
3. development-validation results for every bounded candidate;
4. the one frozen challenger and why it was selected, or why no challenger was credible;
5. one-time 2026 Seed Point test results;
6. one-time pursued-site test results, including independent and matched-location subsets;
7. whether the clean rebuild supports replacing MODEL-13, continuing model development, or retaining MODEL-13;
8. the exact decisions reserved for Ray.

Do not describe exploratory results as independent confirmation. Do not recommend promotion if the evidence does not support it.

## Stop point

Stop with one open, unmerged PR at one final substantive head, required exact-head CI passing, the bounded evidence inventory/ledger complete, and the Development Readiness Mailbox refreshed and validated against that head.

Post a concise `RESULT` Record to the PR. Return to Brainstorming for independent review and Ray's decision. Do not merge.

## Execution profile

- Surface: Codex
- Preferred model: GPT-6 Astra
- Reasoning: High
- Fallback: GPT-5.6 Sol with Extra High reasoning

Rationale: this task combines protected evidence registration, subtle cross-source identity resolution, model reconstruction, nested grouped validation, and consequential holdout discipline. Astra materially reduces the risk of false identity matches, hidden leakage, and invalid model-selection conclusions; Sol Extra High is the strongest practical fallback if Astra is unavailable.