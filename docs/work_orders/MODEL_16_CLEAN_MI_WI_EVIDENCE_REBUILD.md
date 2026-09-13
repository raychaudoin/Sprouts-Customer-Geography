# MODEL-16 — Clean MI/WI Evidence + Broad Public-Data Successor Rebuild

## Objective

Build the strongest defensible Michigan/Wisconsin customer-geography model possible from Ray's clean Sprouts evidence package and a broad, target-blind search of useful free, lawful, publicly available data.

This is not merely a rerun of MODEL-13 on cleaner rows. It is a serious successor-model effort with three business questions:

1. Which free public-data signals best explain Sprouts-oriented customer geography across Michigan and Wisconsin?
2. Which appropriately constrained model performs best without overfitting the small evidence set?
3. Does the frozen rebuilt model hold up on later Seed Points and separately prepared pursued-site forecasts it has never seen?

This initiative may produce a recommended successor candidate, but it does not accept, promote, merge, deploy, or replace MODEL-13 by itself.

## Controlling baseline

- Canonical repository baseline: `main` after GOV-16 cutover.
- MODEL-13 remains the accepted model until Ray explicitly accepts a successor.
- MODEL-14 Generation 2 remains a frozen exploratory result and must not be overwritten.
- Preserved MODEL-15 work remains historical and must not be silently reused as authority.

## Authorized protected evidence package

Ray has prepared three immutable local workbooks together inside one bounded `rebuild-evidence` directory under the authorized Sprouts protected root.

Register them in the protected project catalog and evidence ledger using these logical asset IDs only:

- `MI_SEED_FORECASTS_2024_2026_V1`
- `WI_SEED_FORECASTS_2024_2026_V1`
- `MI_WI_PURSUED_SITES_2025_ISOLATED_V1`

Do not copy the workbooks, paths, filenames, values, addresses, coordinates, row identities, or revealing hashes into Git/GitHub.

Use only the exact directory Ray provides in the launcher. Do not scan other protected folders or recursively search for substitutes.

## Expected source shape

Validate before target-conditioned work:

- Michigan Seed Points: 139 rows — 49 from 2024, 52 from 2025, 38 from 2026.
- Wisconsin Seed Points: 65 rows — 21 from 2024, 20 from 2025, 24 from 2026.
- Pursued sites: 36 rows — 17 Michigan, 19 Wisconsin, all 2025 isolated forecasts.
- Each workbook has one data sheet and 12 source columns.
- The Michigan Seed Point workbook uses `City2`; normalize it to canonical `City` without changing the source workbook.
- The pursued-site workbook places human-readable site names in `Seedpoint_ID`. Treat these as `source_site_name`, not Seed Point IDs. Keep canonical `seedpoint_id` null for pursued sites.
- All admitted rows must have complete year, state, latitude, longitude, MSA, and `Isolated Sales`.

If these aggregate expectations do not match, stop before modeling and report the safe discrepancy.

## Allowed target and prohibited forecast fields

The only permitted target is `Isolated Sales`.

`Impacted Sales` is prohibited from analytical use. Do not use it as a target, feature, filter, tie-breaker, diagnostic, selection signal, interpretive input, or QA shortcut. Project the allowed fields before target loading so impacted values do not enter analytical memory or artifacts.

Cannibalization-adjusted and site-characteristic-adjusted forecasts have already been excluded from the pursued-site file and must not be reintroduced from other sources.

## Identity and duplicate rules

### Seed Points

- Canonical observation identity begins with state-qualified Seed Point ID plus forecast year.
- The same Seed Point/location in different years is a legitimate separate observation because year matters.
- Never use a 2,000-foot rule to merge or remove same-year Seed Points.
- Within one year, exact repeated state + Seed Point ID or exact repeated coordinates are duplicate candidates and must fail closed for reconciliation.
- Link the same physical location across years through exact Seed Point identity and coordinate evidence, retaining every legitimate yearly observation.

### Pursued sites

- Treat each cleaned row as one pursued-site forecast.
- Do not invent Seed Point IDs.
- Use supplied site name, address when present, state, and coordinates for target-blind identity.
- Exact duplicate coordinates or duplicate normalized site identities inside the pursued-site source must fail closed.

### Cross-source identity

- Determine whether a pursued site and Seed Point represent the same underlying physical location using target-blind evidence only.
- Distance may flag a candidate match but may not decide identity by itself.
- Preserve evidence-class distinction (`SEED_POINT` versus `PURSUED_SITE`) even when physical identity is shared.
- Every observation from the same physical location must remain in the same validation group.
- A pursued-site score matching a development location may not be represented as an independent external test. Report matched and unmatched pursued-site results separately.

## Evidence roles and holdout discipline

Freeze identity rules, public-source rules, feature definitions, transformations, eligibility, missingness treatment, folds, metrics, model library, tuning ranges, and selection criteria before opening held-out targets.

### Development evidence

Use 2024 and 2025 Seed Point isolated forecasts for fitting and model selection.

All yearly observations for one physical location must remain in one fold. Give each physical location equal total fitting weight, divided across its admitted yearly observations.

### Independent temporal test

Keep all 2026 Seed Point isolated forecasts sealed until one baseline and at most one challenger are frozen. These targets may not influence source choice, feature engineering, model tuning, thresholds, exclusions, candidate selection, or stopping.

### Independent pursued-site test

Keep all pursued-site isolated forecasts sealed until the same freeze. Report pursued-site results separately for:

- pursued sites independent of every development location;
- pursued sites linked to a Seed Point physical location;
- Michigan and Wisconsin.

Do not use pursued-site results to improve Generation 1. Any later use of pursued-site evidence for development requires a new descendant generation and explicit Ray authority.

Ray authorizes controlled access to 2026 Seed Point and pursued-site isolated targets only after the required freeze and only for the bounded one-time evaluations.

## Public-data ambition and admissibility policy

The goal is the best model supported by free public data, not the preservation of the old feature set.

Development may investigate and admit any source that is:

- free to obtain and use for this project;
- public and lawfully accessible;
- reproducibly downloadable or queryable;
- documented with source, release/vintage, schema, geography, transformation, and licensing/terms posture;
- usable across Michigan and Wisconsin or harmonizable without changing meaning;
- temporally defensible for the forecast years being modeled;
- stable enough to reproduce later;
- materially relevant to customer geography, market opportunity, surroundings, access, movement, competition, or growth.

Do not exclude a source merely because it is unconventional, politically sensitive, or requires careful interpretation. Evaluate sources empirically under the same validation rules.

Do not use paid/proprietary sources, credential-gated commercial datasets, scraped content that violates source terms, or data whose provenance or reuse rights cannot be established.

### Priority public-data families

The source search must consider, at minimum, the following families. These examples are not exclusive; other qualifying free public sources may be used if frozen and documented before target-conditioned feature selection.

1. **Households and population**
   - Census ACS detailed/subject/profile tables, Decennial Census, population estimates, household size/type, age structure, income distribution, tenure, vehicle access, commuting, housing burden, education, migration, and multi-year change.

2. **Employment, daytime population, and movement**
   - LEHD/LODES resident workers, workplace jobs, origin-destination flows, job sectors, inflow/outflow balance, commute distances, and daytime/residential balance.
   - CTPP or other free public commuting-flow products where geographically usable.

3. **Businesses, retail context, competition, and co-tenancy**
   - Overture Maps Places, OpenStreetMap, Census business data where geography is fit for purpose, public business-license/open-data sources where semantics can be harmonized, and target-blind category/taxonomy rules.
   - Grocery, natural/organic, mass retail, restaurant, fitness, health, shopping, commercial intensity, co-tenancy, competition, category mix, distance, density, and gravity-style measures.

4. **Roads, traffic, and accessibility**
   - TIGER/Line roads, FHWA products, Michigan and Wisconsin DOT public traffic counts/AADT/hourly counts where cross-state semantics can be made comparable, ramps/interchanges, intersections, network centrality, and road-class exposure.
   - Reproducible open-routing travel-time or network-distance catchments derived from public road networks.

5. **Time-of-day and directional movement**
   - Public hourly traffic data, commuting-direction flows, LODES OD patterns, and other lawful free sources that meaningfully describe when and from where people move.
   - Do not use paid cellphone-location or proprietary mobility feeds.

6. **Land use, buildings, and urban form**
   - NLCD, EPA Smart Location Database/National Walkability Index, public building footprints, developed-land intensity, intersection density, parcel/building context where public and comparable, urban-area classification, and mixed-use intensity.

7. **Growth and market momentum**
   - ACS vintage deltas, Census Building Permits Survey, population estimates, BEA/BLS regional indicators, public development/permit data where MI/WI semantics can be harmonized, housing growth, vacancy, and employment growth.

8. **Remote sensing and other structural market signals**
   - Public nighttime-light products such as VIIRS and other reproducible free measures with a defensible business relationship.

9. **Public food-access and store-network context**
   - USDA public food-access/retailer resources and historically defensible public store-location data.
   - Existing Sprouts-store or competitor-store networks may be used only with an as-of-vintage policy that avoids future leakage.

### Source-vintage and leakage rules

- Prefer public data available no later than the forecast year associated with each observation when historical releases exist.
- A later public-data vintage may not silently explain an earlier target.
- If a source is effectively structural and only one stable snapshot exists, Development may create a separately labeled fixed-snapshot feature track only after documenting why it is unlikely to create target leakage.
- A current-snapshot track may be useful for current decision support, but it may not be represented as historically honest temporal validation.
- Any future-vintage source with plausible knowledge of later development, business openings/closures, roads, or store networks must be excluded from the primary historical-validation track.
- Record exact source vintages and transformation chronology.

## Protected-characteristic boundary

Direct protected characteristics must not be model scoring inputs. This includes direct race, ethnicity, religion, and other protected-class measures governed by the project's standing safeguards.

This is not an instruction to avoid strong lawful public signals for optics. Non-protected household, economic, behavioral-proxy, access, employment, housing, growth, business, and movement variables may be used when empirically useful and reproducible.

Protected-characteristic data may be used only for post hoc auditing of model behavior when lawful and separately reported; it may not drive feature selection or score prediction.

## Target-blind feature design

Before opening development targets, create and freeze a public-source/feature catalog containing:

- source and vintage;
- feature family and business hypothesis;
- geography/catchment definition;
- exact transformation;
- missingness semantics;
- expected direction only when justified independently of targets;
- temporal-leakage classification;
- licensing/reproducibility notes.

Feature scales may include tract context, limited radial bands, state-isolated 5-mile support where already accepted, and reproducible drive-time/network catchments. Avoid an uncontrolled combinatorial explosion of nearly identical radii and transformations.

Allowed target-blind transformations include counts, densities, ratios, shares, growth rates, distance decay, gravity measures, diversity indices, accessibility, network measures, and unsupervised dimensionality reduction fit strictly inside folds.

Missing values must remain explicit. Do not silently zero-fill, favorable-fill, or median-fill outside a documented fold-local procedure.

## Model library

The sample is modest, so maximum predictive ambition must be paired with strong overfitting controls.

At minimum, compare:

1. clean MODEL-13-method baseline using the accepted feature definitions where temporally admissible;
2. regularized linear models: ridge, lasso where stable, and elastic net;
3. generalized additive or spline-based models with bounded degrees of freedom;
4. partial least squares or another low-dimensional linear latent-factor method where appropriate;
5. conservatively tuned tree ensembles such as gradient boosting, histogram gradient boosting, random forest, Extra Trees, XGBoost, LightGBM, or CatBoost when available and reproducible;
6. a hierarchical/partial-pooling approach for state/market differences if technically appropriate;
7. a simple ensemble only if it consistently improves grouped development validation without state-specific collapse or instability.

Development may add another low- or medium-capacity method if it is predeclared before held-out access and justified for this sample size.

Do not use deep neural networks, unrestricted high-capacity learners, target encoding that leaks across folds, or automated model/feature search that cannot be reproduced and audited.

All tuning, feature selection, scaling, imputation, dimensionality reduction, and ensemble weighting must occur inside deterministic physical-location-grouped nested validation.

## Candidate construction and source-family testing

The broad search must remain interpretable enough to determine what actually helps.

Required candidate structure:

- one clean baseline;
- source-family additions and removals;
- bounded ablations for major public-data families;
- at least one simpler regularized candidate;
- at least one conservatively tuned nonlinear candidate;
- at most one frozen challenger before held-out access.

A feature family should not survive solely because one target-driven specification looked good. Report family-level contribution, stability, and whether the result holds in both states.

## Metrics and business evaluation

Use deterministic physical-location-grouped nested validation on 2024–2025 development evidence.

Report pooled and separately for Michigan/Wisconsin:

- Spearman rank correlation;
- Kendall tau-b;
- log RMSE;
- level MAE;
- calibration slope/intercept or equivalent calibration diagnostics;
- top-quartile ranking overlap or another predeclared high-opportunity ranking measure;
- paired-fold differences against the clean baseline;
- coefficient, feature-selection, or feature-importance stability as appropriate;
- source-family ablations;
- sensitivity to the worst-error physical location;
- effective observation and physical-location counts.

A credible challenger must:

- improve ranking and/or error in a meaningful, repeatable way;
- avoid material deterioration in either Michigan or Wisconsin;
- avoid dependence on one fold, market, source family, or location;
- remain reproducible and reasonably parsimonious for the evidence size;
- survive the one-time held-out tests well enough to support its intended business use.

Select at most one frozen challenger before opening held-out targets. Evaluate the baseline and challenger once on 2026 Seed Points and once on pursued sites. Do not retune afterward.

## Required protected-local records

Create durable protected-local records sufficient to answer, for every model candidate:

- exact source workbook logical ID;
- observation/evidence-unit membership;
- evidence class and role;
- state, forecast year, and physical-location group;
- whether each observation was development-used, temporal-test-used, pursued-site-test-used, excluded, or unresolved;
- candidate/model genealogy;
- target-access and analytical-use events;
- exact public-source/feature catalog and source vintages;
- holdout freeze identity and timing.

The original-source inventory and evidence ledger may become `READY` for this bounded rebuild package only when these records are complete and validated. Do not claim project-wide completeness beyond this package.

## Repository and public-data acquisition authority

Development may:

- create a normal task branch and PR from current canonical `main`;
- research, download, cache, and process qualifying free public sources;
- add documented source manifests, adapters, feature builders, tests, reports, and safe aggregates;
- implement loaders, schema validation, identity reconciliation, evidence registration, modeling/evaluation code, deterministic pipelines, and diagnostics;
- preserve/reuse accepted code where appropriate without treating old features as privileged;
- run local validation and required CI;
- commit, push, and maintain the task PR;
- refresh and validate the Development Readiness Mailbox against the final candidate;
- perform bounded mechanical remediation that does not change the business/evidence/holdout rules above.

Development must not:

- modify or overwrite accepted MODEL-13 artifacts;
- modify the frozen MODEL-14 result;
- use prior MODEL-15 reconstruction as evidence authority unless reconciled to this package;
- expose protected data in Git/GitHub;
- use impacted forecasts or excluded score variants;
- access protected targets outside the three registered workbooks;
- use a paid/proprietary dataset or violate source terms;
- silently refresh source vintages;
- use protected characteristics as scoring inputs;
- open held-out targets before freeze;
- promote, accept, deploy, or merge a successor;
- start Generation 2 after seeing holdout results.

## Tests and validation

At minimum, test:

- exact protected source schema and expected row counts;
- `City2` to `City` normalization;
- pursued-site names never becoming Seed Point IDs;
- field allowlists excluding `Impacted Sales`;
- duplicate and identity rules;
- no distance-based same-year Seed Point merging;
- different Seed Point years retained as distinct observations;
- physical-location grouping and equal total location weight;
- public-source manifests, vintages, licensing notes, schemas, and deterministic materialization;
- source-vintage leakage rules;
- feature freeze chronology;
- fold-local preprocessing/tuning/feature selection;
- holdout blindness before freeze;
- cross-source matched-location segregation;
- deterministic reruns;
- missingness preservation with no silent zero-fill;
- protected-characteristic exclusion from scoring inputs;
- no protected material in tracked files, logs, PR text, reports, or readiness output;
- exact-head Repository Validation.

## Required result

Return a plain-English business summary and repository-safe detailed report covering:

1. admitted protected evidence and physical-location counts by state, year, and role;
2. admitted and rejected public sources, with reasons and vintages;
3. the final target-blind feature catalog and major source families;
4. duplicates, identity conflicts, exclusions, or Seed Point/pursued-site matches;
5. development-validation results for every bounded model candidate;
6. source-family contribution and ablation results;
7. the one frozen challenger and why it was selected, or why no challenger was credible;
8. one-time 2026 Seed Point results;
9. one-time pursued-site results, separated into independent and matched-location subsets;
10. whether evidence supports replacing MODEL-13, continuing development, or retaining MODEL-13;
11. exact limitations and decisions reserved for Ray.

Do not describe development results as independent confirmation. Do not recommend promotion unless both the development and held-out evidence support it.

## Stop point

Stop with one open, unmerged PR at one final substantive head, required exact-head CI passing, the bounded evidence inventory/ledger complete, public-source manifests and feature freeze recorded, and the Development Readiness Mailbox refreshed and validated against that head.

Post a concise `RESULT` Record to the PR. Return to Brainstorming for independent review and Ray's exact-version decision. Do not merge.

## Execution profile

- Surface: Codex
- Preferred model: GPT-6 Astra
- Reasoning: Ultra, if available to this account/surface
- Fallback 1: GPT-6 Astra with the highest available non-Ultra reasoning setting
- Fallback 2: GPT-5.6 Sol with Extra High reasoning

Rationale: this task combines protected-evidence registration, broad public-data research, source-vintage judgment, geospatial feature engineering, subtle identity resolution, multiple model families, nested grouped validation, and consequential holdout discipline. Ultra uses maximum reasoning and may run additional agents for eligible users, which materially improves the chance of a complete source search and coherent end-to-end execution. It does not guarantee a better statistical model; the model must still earn improvement through the frozen validation design.