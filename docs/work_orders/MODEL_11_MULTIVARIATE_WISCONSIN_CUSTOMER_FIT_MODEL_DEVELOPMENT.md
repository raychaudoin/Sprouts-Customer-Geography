# MODEL-11: Multivariate Wisconsin Customer-Fit Model Development

## Authority and outcome boundary

Master Control Room authorized this Lane B task to determine whether the accepted DATA-03 public candidate measures materially improve the accepted Wisconsin development-only MODEL-09 customer-fit proxy. Exact substantive H is accepted or rejected by `MODEL: Customer-Fit Proxy Decisions & Acceptance`. MODEL-11 cannot self-accept, create acceptance-record-only A, merge, validate independently, deploy, or begin follow-on work.

This is development evidence only. It creates no production or operational Demand Heat authority, establishes neither independent validation nor market transport, and makes no Sprouts proprietary-model-equivalence claim.

## Fixed evidence and target boundary

MODEL-11 reuses the exact accepted MODEL-10 / PIPE-04 cohort consumed by MODEL-09: 63 eligible Wisconsin source observations in 41 physical-location groups, with the two MODEL-10-quarantined observations excluded. MODEL-10 identity, lineage, canonical anchors, eligibility, quarantine, and membership remain immutable. PIPE-04 READY is the sole target source. Only `Isolated Sales` may be read; `Impacted Sales`, non-Wisconsin targets, quarantined observations, unrelated fields, and original-workbook reconstruction are denied.

The already-consumed observations remain development evidence. Reuse does not create independent evidence or restore holdout status.

## Target-blind Phase 1 freeze

Before target access, MODEL-11 materializes one immutable target-blind feature freeze from accepted MODEL-10 canonical anchors and accepted public inputs. The freeze verifies exact accepted MODEL-09, DATA-03, MODEL-10, PIPE-04, ACS 2024, TIGER 2024, and GEO-03 identities. It contains the complete eligible cohort and is written incomplete-first with READY last outside Git.

The existing MODEL-09 3/5/7-mile household and spatial-concentration features are reproduced unchanged. Every DATA-03 candidate is constructed at one primary five-mile context using the same EPSG:5070 tract-internal-point membership and forced containing-tract rule. No DATA-03 radius variants or gradients are authorized.

For a share, valid underlying tract numerators and denominators are summed once over five-mile members and the context proportion is calculated from those totals. Tract percentages are never averaged. For a direct dollar, median, or average, the feature is accurately named a weighted tract-profile proxy, not an exact five-mile statistic:

- median household income and per-capita income use accepted B11001 household mass as the tract weight;
- median home value uses owner-occupied housing units;
- median gross rent uses renter-occupied units derived as occupied minus owner-occupied units; and
- average household size uses occupied housing units.

Every selected member tract must have valid source evidence and a positive aggregate denominator or weight. Otherwise the measure is excluded for the complete cohort with a target-blind reason; no observation is dropped and no value is imputed. All 63 observations remain accounted for. Direct currency proxies are transformed with `log1p`; proportions and average household size retain their natural scale. Fold-learned scaling is not part of the freeze.

The fixed redundancy rule operates only on the 41 unique physical-location feature vectors, without target access. It follows the contract's fixed priority order and removes the later-priority feature when absolute Pearson correlation is at least 0.95. Spatial-concentration terms are never removed by this rule. The freeze records complete-cohort eligibility, exclusions, collinearity pairs, transformation semantics, and aggregate quality/MOE diagnostics. Neither target values nor market/vintage labels influence feature eligibility.

## Bounded target-conditioned comparison

Exactly three architectures are frozen:

1. `model09_spatial_concentration_reference`: the accepted MODEL-09 preferred terms and fixed ridge penalty 0.1, unchanged.
2. `challenger_multivariate_ridge`: the MODEL-09 opportunity and spatial terms plus every eligible frozen DATA-03 feature, with the alpha grid `[0.1, 1.0, 10.0, 100.0]`.
3. `challenger_multivariate_elastic_net`: the same bounded pool with alpha grid `[0.01, 0.1, 1.0, 10.0]` and l1-ratio grid `[0.25, 0.5, 0.75]`.

No subset enumeration, random search, target-correlation screening, black-box model, market predictor, or vintage predictor is permitted. All candidates model `log1p(Isolated Sales)`. Household opportunity remains a separate term and is excluded from the customer-fit contribution.

The deterministic outer comparison uses five MODEL-10-physical-location folds and inverse within-location observation-count fitting weights. Inner tuning uses only grouped training rows and deterministic grouped folds; scaling, regularization, and elastic-net selection are learned inside training data. Reported metrics first average actual and predicted levels to one pair per physical location. The required diagnostics are grouped Spearman, grouped Kendall tau-b, log RMSE, level MAE, fold ranges, leave-one-source-market-out with complete physical-location exclusion, selected-feature frequency, coefficient-sign stability, coefficient instability, target-blind collinearity, and individual physical-location sensitivity measured from each group's strictly outer-held-out error. All are development diagnostics.

## Locked reference and selection gate

The reference implementation must reproduce the accepted MODEL-09 `challenger_spatial_concentration` aggregate metrics within the fixed contract tolerance. MODEL-09 history and protected artifacts are not rewritten.

A multivariate challenger qualifies only when its grouped out-of-fold Spearman is at least 0.03 above the reference and its grouped log RMSE is no more than 1.05 times the reference. Qualifiers are ordered by higher Spearman, lower log RMSE, then fewer effective degrees of freedom. If none qualifies, the required conclusion is `NO_MULTIVARIATE_IMPROVEMENT_JUSTIFIED` and MODEL-09 remains preferred. The gate cannot be changed after target access.

After selection, the exact selected challenger architecture is refit on all 63 observations using only its fixed nested-selection procedure. No additional feature or hyperparameter search follows selection. If no challenger qualifies, the protected output records MODEL-09 retention rather than manufacturing a new successor fit.

## Output and disclosure semantics

Protected outputs keep three concepts separate: raw five-mile household opportunity; the multiplicative customer-fit contribution of non-opportunity terms only; and inverse-log fitted target mass. Full fitted target mass is never relabeled customer fit.

Targets, identities, coordinates, observation features, fold assignments, coefficients, intercepts, selected target-conditioned parameters, predictions, residuals, detailed target correlations, protected handles and paths, and reconstructable artifacts remain outside Git/GitHub. Repository-safe surfaces contain only the contract, implementation, schemas, fictional tests, and non-reconstructable aggregate development evidence consistent with MODEL-09 precedent.

At substantive H the one MODEL-11 manifest is `COMPLETED_AWAITING_ACCEPTANCE`, execution is `COMPLETED`, capability acceptance is `NOT_REVIEWED`, the real feature freeze and development run are READY, all 63 observations are accounted for, required validation and exact-H CI pass, and the reviewed diff contains no protected detail. Exact H then stops for the named MODEL owner.
