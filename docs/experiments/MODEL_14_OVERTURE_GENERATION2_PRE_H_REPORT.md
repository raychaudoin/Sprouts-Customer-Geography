# MODEL-14 Overture Commercial Context — Exploratory Generation-2 Pre-H Report

## Posture and chronology

MODEL-14 remains `IN_PROGRESS / IN_PROGRESS / NOT_REVIEWED` and stops at pre-H Master Control Room review. This Generation-2 result is exploratory, not confirmatory, because aggregate Generation-1 outcomes were known before the separately frozen commercial catalog was defined. Nothing in this report accepts Overture source authority, replaces MODEL-13, promotes scoring, changes APP-01, touches PBI-02, creates H, requests capability acceptance, authorizes merge, or begins follow-on work.

Overture Maps Places release `2026-07-22.0`, schema `v1.18.0`, and the 15-feature catalog were frozen at public checkpoint `3a72aff98a5f916f6df0de743d5d90fa025233c3`. Two public materializations were byte-identical before any Generation-2 target access. The bounded evaluator and its exact public-checkpoint, content-digest, candidate-authority, cohort, chronology, grouped-CV, and disclosure gates were committed at `6e4afadeb0dfd76973a1cbdc05cf30c78198805e` before protected evaluation.

Under renewed Master Control Room authority, exactly one accepted MODEL-13 registry was recovered and validated without disclosing its path or contents. The evaluator recomputed the 123 accepted fitting-location commercial vectors from frozen tract components and accepted predecessor memberships, then persisted their target-blind anchor package and READY marker before resolving development targets. Only the already-consumed MODEL-13 cohort was evaluated. No Generation-2 feature, taxonomy rule, quality threshold, radius, aggregation, missingness rule, candidate definition, or hyperparameter grid changed after target access.

## Frozen public commercial family

The source remains an experimental candidate input with no production authority. Eligible source rows required non-null confidence strictly above `0.7`; known temporary or permanent closures were excluded while null status remained unknown and eligible. Released Overture place identity was retained without name, brand, provider, coordinate, or fuzzy deduplication. Taxonomy used only current `taxonomy`, ordered unique `taxonomy.hierarchy`, and `basic_category` semantics; deprecated `categories` and alternate taxonomy values were not used.

The catalog contains four tract-local log counts, seven accepted state-isolated five-mile log counts, one five-mile basic-category diversity measure, and three five-mile commercial-mix shares. No arbitrary radius or category search occurred.

- Michigan: all 3,017 accepted tracts retained. Eleven count features have zero missing values; four denominator-based measures have 29 missing tracts where the complete-source five-mile commercial denominator is zero.
- Wisconsin: all 1,542 accepted tracts retained. Eleven count features have zero missing values; four denominator-based measures have 9 missing tracts for the same semantic reason.
- Development cohort: all 15 features were computable at every fitting location, 82 Michigan and 41 Wisconsin. No observation was dropped and no imputation was needed for this cohort.

## Baseline reproduction

Baseline reproduction: **MATCH**. The exact accepted `successor_combined_multivariate_elastic_net` formulation, 11-term feature universe, 196 observations, 123 physical-location groups, state-balanced five-fold outer and four-fold inner grouping, inverse observation-count location weighting, bounded regularization grid, and training-fold-only preprocessing reproduced accepted MODEL-13 metrics.

Five Michigan observations across three locations remained excluded from fitting only for `GEO05_ANCHOR_TRACT_MISSING_OR_AMBIGUOUS` and remained in protected accounting and QA.

## Frozen A/B/C/D results

- A: accepted MODEL-13 reproduced.
- B: A plus all 15 commercial features.
- C: A plus the 11 commercial intensity/count features.
- D: A plus the 4 commercial mix/diversity features.

Every row below uses the identical eligible sample and grouped folds.

| Candidate | Domain | Spearman | Kendall tau-b | Log RMSE | Level MAE |
| --- | --- | ---: | ---: | ---: | ---: |
| A — reproduced MODEL-13 | Pooled | 0.6293 | 0.4544 | 0.1048 | 23,378.51 |
| A — reproduced MODEL-13 | Michigan | 0.4903 | 0.3487 | 0.1084 | 24,712.41 |
| A — reproduced MODEL-13 | Wisconsin | 0.7606 | 0.5601 | 0.0972 | 20,710.72 |
| B — all commercial | Pooled | 0.6396 | 0.4598 | 0.1049 | 23,341.11 |
| B — all commercial | Michigan | 0.5235 | 0.3701 | 0.1089 | 24,398.82 |
| B — all commercial | Wisconsin | 0.7053 | 0.5259 | 0.0964 | 21,225.71 |
| C — intensity/count | Pooled | **0.6599** | **0.4793** | **0.1010** | **22,540.35** |
| C — intensity/count | Michigan | **0.5297** | **0.3755** | **0.1060** | **24,268.91** |
| C — intensity/count | Wisconsin | 0.7548 | **0.5625** | **0.0900** | **19,083.23** |
| D — mix/diversity | Pooled | 0.5847 | 0.4118 | 0.1067 | 24,194.22 |
| D — mix/diversity | Michigan | 0.4401 | 0.3060 | 0.1083 | 25,162.98 |
| D — mix/diversity | Wisconsin | 0.6642 | 0.4844 | 0.1033 | 22,256.69 |

Candidate B is not credible despite modest pooled and Michigan gains because Wisconsin Spearman falls by `0.0552` and Wisconsin MAE rises by `514.99`. Candidate D reduces ranking and worsens pooled and Wisconsin errors. The predeclared tier-first screen therefore selects C, not the pooled-only or lower-dimensional alternatives.

## Strongest candidate comparison

Candidate C adds 11 commercial intensity/count terms to the 11 accepted MODEL-13 terms.

| Domain | Spearman delta | Kendall delta | Log RMSE delta | Level MAE delta |
| --- | ---: | ---: | ---: | ---: |
| Pooled | +0.0306 | +0.0249 | -0.0038 | -838.17 |
| Michigan | +0.0394 | +0.0267 | -0.0024 | -443.50 |
| Wisconsin | -0.0057 | +0.0024 | -0.0072 | -1,627.49 |

The pooled and Michigan ranking gains are accompanied by better pooled, Michigan, and Wisconsin error measures. Wisconsin Spearman is nearly preserved rather than improved, while Wisconsin Kendall and both error measures improve.

## Ablation, fold, coefficient, and outlier evidence

Removing the intensity/count family from C returns candidate A. Adding the four mix/diversity features to C produces B and changes pooled Spearman by `-0.0203`, Wisconsin Spearman by `-0.0495`, pooled log RMSE by `+0.0039`, and pooled MAE by `+800.77`. Mix/diversity alone is also below baseline. The positive evidence is therefore specific to the frozen intensity/count family rather than the full commercial catalog.

Candidate C has coefficient-stability score `0.8746`. All 11 Overture intensity terms were selected in at least one outer fold, four in every fold, with mean selection frequency `0.7273` and mean dominant-sign agreement `0.9394`. Paired pooled Spearman improves in 3 of 5 folds and is nonworsening in 3 of 5; Michigan improves in 3 of 5; Wisconsin improves in 4 of 5 and is nonworsening in 4 of 5. This supports a real but not uniformly stable exploratory gain.

The strongest disclosure-safe standardized commercial signals are:

| Feature | Direction | Standardized coefficient | Outer-fold selection | Dominant-sign agreement |
| --- | --- | ---: | ---: | ---: |
| Five-mile total commercial-place intensity | Positive | 0.1024 | 1.00 | 1.00 |
| Tract shopping-place intensity | Negative | -0.0583 | 1.00 | 1.00 |
| Five-mile health-care-place intensity | Negative | -0.0413 | 0.80 | 1.00 |
| Tract food-and-drink-place intensity | Positive | 0.0377 | 1.00 | 1.00 |
| Tract total commercial-place intensity | Positive | 0.0171 | 0.80 | 1.00 |
| Tract grocery-place intensity | Negative | -0.0090 | 1.00 | 1.00 |
| Five-mile grocery-place intensity | Negative | -0.0078 | 0.60 | 0.67 |

The positive total-commercial and tract food-and-drink terms fit the intended commercial-ecosystem mechanism. Negative shopping, health-care, and grocery coefficients are conditional on several correlated intensity measures and must not be interpreted causally. The five-mile grocery term has weaker sign stability, and a fitness/wellness term rounds to effectively zero with only 40% fold selection; both are suspicious or weak signals rather than durable conclusions.

Removing the strongest candidate's single worst-error physical location from both C and A changes the incremental pooled Spearman gain from `+0.0306` to `+0.0314`, only `+0.0008`. The result is not driven by that location. No location identity is disclosed.

## Pre-H conclusion and safeguards

Evidence disposition: **possible improvement**.

Candidate C satisfies the pooled and Michigan ranking, Wisconsin transportability, error, coefficient-stability, feature-count, coverage, and outlier safeguards for a promising exploratory successor. It is not classified as material improvement because pooled Spearman is nonworsening in only 3 of 5 paired folds rather than the predeclared 4-fold material threshold. Generation 2 is not confirmation and cannot support source acceptance or MODEL-13 replacement without Master Control Room decisions on source formalization and a confirmatory strategy.

- No sealed, prospective Milwaukee, Madison, future-vintage, validation-only, or otherwise unconsumed target was opened.
- No protected-characteristic scoring feature was used.
- No protected row, target, identity, coordinate, prediction, residual, registry, path, or prohibited digest entered Git or GitHub.
- MODEL-13 remains accepted and unchanged.
- APP-01 remains accepted and unchanged. PBI-02 remains separate and unmodified.
- Overture remains experimental; no DATA authority or production scoring package was created or promoted.
- The PR remains draft and unmerged; no H or capability-acceptance request exists.

Exact next destination: **MASTER CONTROL ROOM: Sprouts Customer Geography**
