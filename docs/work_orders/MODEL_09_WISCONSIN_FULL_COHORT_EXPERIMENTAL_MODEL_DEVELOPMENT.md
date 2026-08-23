# MODEL-09: Wisconsin Full-Cohort Experimental Model Development

## Authority and outcome boundary

Master Control Room authorized this Lane B task to develop the first Wisconsin full-cohort experimental public-data customer-fit proxy. Exact substantive H is accepted or rejected by `MODEL: Customer-Fit Proxy Decisions & Acceptance`. MODEL-09 may select an experimental preferred formulation or conclude that no defensible customer-fit model is justified. It cannot self-accept, create acceptance-record-only A, merge, deploy, or begin follow-on work.

This is development, not independent validation, final site selection, Site Scanner, production readiness, causal evidence, or Sprouts' proprietary customer model. Every resampling result is development-only.

## Evidence and identity boundary

The complete accepted PIPE-04 READY cohort is required: 63 MODEL-10-eligible Wisconsin observations are included and the two MODEL-10-quarantined observations remain excluded. PIPE-04 is the only target source. `Isolated Sales` is the only permitted target. `Impacted Sales`, Michigan, Detroit, all other non-Wisconsin targets, unrelated fields, and original-workbook reconstruction are denied.

MODEL-10 remains the immutable authority for source-observation identity, physical-location identity, canonical target-blind coordinate, market and vintage lineage, historical linkage, quarantine, eligibility, and cohort membership. Target values cannot alter those facts. Repeated vintages belonging to one MODEL-10 physical location are assigned to the same development fold.

Once an authorized target affects features considered, transformations, coefficients, model structure, comparison, selection, calibration, or diagnostics, that observation is recorded as `DEVELOPMENT_CONSUMED` for the MODEL-09 successor only. Historical MODEL-05, MODEL-07, MODEL-10, and PIPE-04 records remain unchanged, and consumed evidence cannot later be described as untouched validation evidence for this model version.

## Public feature authority and analysis unit

The analysis unit is one PIPE-04-eligible Wisconsin source observation. The accepted target-blind MODEL-10 canonical physical-location anchor supplies location, and repeated observations share the same target-blind feature vector. Public inputs are limited to the checksum-pinned 2020-2024 ACS 5-year Detailed Table B11001 household estimate/MOE and 2024 TIGER Wisconsin tract geography already governed by repository manifests.

Whole-tract household estimates are aggregated using the accepted target-blind anchor-to-tract-internal-point radii of 3, 5, and 7 miles in EPSG:5070. The containing anchor tract is forced into each radius under the accepted PIPE-01/GEO-03 rule. Any missing or invalid member-tract estimate/MOE makes the observation noncomputable; no neutral, favorable, or zero imputation is permitted. Complete-cohort failure rejects the development run.

The public feature contract keeps three concepts explicit:

- `household_opportunity_5mi`: raw five-mile B11001 household mass;
- target-blind spatial-concentration features: the three-mile share of seven-mile households and the log inner-versus-outer household-density gradient, used only as an experimental customer-fit proxy;
- `modeled_target_mass`: the target-conditioned fitted level, never relabeled as household opportunity or customer fit.

The concentration proxy describes public household geography only. B11001 contains no demographic preference or proprietary customer attributes.

## Bounded comparison fixed before real target-conditioned execution

The repository contract fixes four candidates before real analytical execution:

1. `baseline_opportunity`: intercept plus standardized log five-mile household opportunity.
2. `challenger_spatial_concentration`: baseline plus the two target-blind concentration features.
3. `challenger_spatial_vintage`: spatial concentration plus fixed 2025/2026 observation-vintage indicators.
4. `challenger_market_sensitive`: spatial/vintage terms plus ridge-controlled source-market intercept indicators.

All candidates model `log1p(Isolated Sales)`. Numeric scaling is learned on each training fold only. Estimation weights each observation by the inverse number of observations in its MODEL-10 physical-location group, so every location contributes total weight one. The deterministic five-fold comparison assigns complete physical-location groups, not rows, to folds. Metrics first average actual and predicted levels within each physical-location group, so every location receives one unit of diagnostic weight regardless of vintage count. A separate leave-one-source-market-out diagnostic examines transport sensitivity and excludes the complete physical-location group of every held-out row from training, including when source-market lineage changed across vintages. Candidate count, terms, folds, penalties, transformations, and selection tolerances are fixed by `MODEL09_WISCONSIN_EXPERIMENTAL_MODEL_CONTRACT_V1`; target-conditioned alteration requires a new substantive H.

A challenger qualifies only if grouped out-of-fold Spearman correlation improves over baseline by at least 0.03 and grouped log-RMSE is no worse than 5% above baseline. Among qualifiers, higher Spearman, then lower log-RMSE, then lower complexity controls selection. If none qualifies, MODEL-09 records an explicit no-customer-fit-model conclusion. Kendall tau-b, Spearman, log-RMSE, level MAE, fold ranges, leave-one-market-out behavior, feature completeness, repeated-location counts, and ACS MOE quality are development diagnostics, not validation gates.

## Protected execution and disclosure

Execution accepts only an explicitly supplied opaque-handle MODEL-09 registry outside Git. It verifies exact PIPE-04 READY identity and content, exact MODEL-10 fixed identity/cohort agreement, accepted ACS/TIGER checksums and vintages, protected-root containment, and an immutable output run. An incomplete marker is written first and READY last.

Actual targets, coordinates, identities, observation-level features/predictions/residuals, fitted coefficients, fold assignments, protected hashes/nonces, and reconstructable target-conditioned evidence remain outside Git/GitHub. Repository-safe code, contracts, schemas, fictional tests, and non-reconstructable aggregate development evidence may be reviewed at H.

## Completion evidence

The final code-matched protected run is READY at protected package version 1.0.3. Its explicit supersession chain preserves three earlier READY runs: 1.0.1 added a durable consumption marker, 1.0.2 corrected diagnostic weighting and market-holdout grouping, and 1.0.3 added inverse group-size estimation weights so each physical location contributes total fitting weight one. One earlier fail-closed attempt remains incomplete as required by immutable interruption handling; it failed before target consumption. The controlling run contains a protected `DEVELOPMENT_CONSUMED` marker and complete observation-level evidence outside Git.

Disclosure-safe real development accounting:

- 63 of 63 eligible observations included; two MODEL-10-quarantined observations excluded;
- 41 physical-location groups, including 20 repeated-location groups, across 14 source-market lineage values;
- 63 Isolated Sales values consumed; zero Impacted Sales and zero non-Wisconsin target values accessed;
- 63 complete public feature rows; maximum five-mile relative ACS B11001 MOE was 0.0386;
- target content changed neither identity nor cohort membership;
- household opportunity, concentration-only customer-fit proxy contribution, and modeled target mass remain separate in protected outputs.

Development-only comparison:

| Candidate | Grouped Spearman | Grouped Kendall tau-b | Log RMSE | Leave-one-market-out Spearman |
|---|---:|---:|---:|---:|
| Opportunity baseline | 0.6599 | 0.5000 | 0.1046 | 0.7136 |
| Spatial concentration | 0.7000 | 0.5146 | 0.1019 | 0.6904 |
| Spatial + vintage | 0.6678 | 0.4854 | 0.1039 | 0.6810 |
| Market-sensitive ridge | 0.6760 | 0.4805 | 0.1043 | 0.6974 |

`challenger_spatial_concentration` is the preferred experimental formulation under the fixed rule and the only qualifier. Its grouped Spearman improved by 0.0401 over baseline, clearing the 0.03 minimum, while log RMSE was about 0.974 times baseline. The vintage and market-sensitive challengers did not qualify.

The preference remains development-only and requires caution. Across the five physical-location-grouped folds, Spearman ranged from 0.6667 to 0.8571 for the preferred candidate versus 0.5238 to 0.8810 for baseline. However, its group-safe leave-one-market-out Spearman was 0.6904, below the 0.7136 baseline, so market transport is not established. The market-sensitive terms are source-lineage adjustments, not customer-fit features, and their challenger also fell below baseline on the group-safe market-holdout diagnostic. The preferred model's experimental customer-fit factor is limited to the two public spatial-concentration terms. B11001 contains household totals only, so this model does not establish demographic preference fit. No result is independently validated, production ready, causal, or evidence of proprietary-model equivalence.

At H the task manifest is `COMPLETED_AWAITING_ACCEPTANCE`, execution `COMPLETED`, and capability acceptance `NOT_REVIEWED`. Exact-H CI must succeed before H is routed to the MODEL acceptance owner.
