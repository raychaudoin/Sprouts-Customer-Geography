# MODEL-14 Public Feature Expansion Successor Experiment — Pre-H Report

## Posture and chronology

MODEL-14 remains an experimental Lane B task stopped before H for Master Control Room review. The PR remains draft. Nothing in this result accepts a new source, replaces MODEL-13, promotes a scoring package, changes APP-01, touches PBI-02, requests capability acceptance, authorizes merge, or changes production.

The public definitions and complete tract matrix were frozen at `d516f2ffce151d83df8c80ea293ea84550378fbf` before development-target evaluation. Two independent 4,559-tract materializations were byte-identical. After exact accepted MODEL-13 authority was uniquely recovered, accepted development anchors were recomputed from the same frozen tract components and definitions using predecessor five-mile membership authority. That protected local anchor feature package was made READY before model evaluation. No feature definition, transformation, radius, missingness rule, or eligibility rule changed after target access.

## Public feature families

The frozen experimental universe contains 27 candidates over the exact accepted 2024 tract inventory: 3,017 Michigan tracts and 1,542 Wisconsin tracts. No tract was dropped and no missing value was converted to zero.

| Family | Status | Candidates | Exact experimental source/vintage | Statewide coverage and missingness |
| --- | --- | ---: | --- | --- |
| LODES | evaluation-ready | 14 | U.S. Census Bureau LEHD Origin-Destination Employment Statistics, release format 8.4, 2021 data, release identity `20251202_1657`, current crosswalk using 2024 TIGER | Exact 3,017 MI / 1,542 WI keys. Four features are complete; bounded ratios have at most 43 MI and 14 WI undefined tract-anchor contexts. |
| Business context | partially evaluation-ready | 0 | Overture Maps Places July 2026, OpenStreetMap, and Census 2023 CBP/ZBP investigated | No feature admitted. CBP/ZBP lack tract geography, while an overnight allocation or unfrozen Overture taxonomy/spatial join would add new source semantics. Candidate C was therefore not evaluated. |
| Traffic/accessibility | evaluation-ready | 2 | U.S. Census Bureau 2024 TIGER/Line state Primary and Secondary Roads, release date 2024-09-25 | Exact 3,017 MI / 1,542 WI keys; zero missing. These are proximity proxies, not AADT. |
| Richer non-protected ACS | evaluation-ready | 11 | 2020-2024 ACS 5-Year Detailed Tables B01003, B08303, B11001, B17001, B19001, B25024, B25070, with accepted B08201 and B08301 reused | Exact 3,017 MI / 1,542 WI keys; at most 42 MI and 14 WI undefined tract-anchor contexts. Census special values remain missing. |

All 27 new features were computable for every one of the 123 fitting physical locations: 82 in Michigan and 41 in Wisconsin. The broader statewide missingness therefore did not change the evaluation sample or require imputation in this cohort.

## MODEL-13 baseline reproduction

Baseline reproduction: **MATCH**. The exact accepted formulation `successor_combined_multivariate_elastic_net`, 11-term feature universe, 196 observations, 123 state-qualified physical locations, state-balanced five-fold outer / four-fold inner grouping, inverse location-observation weighting, and fold-local preprocessing reproduced the accepted repository metrics at recorded precision.

| Domain | Spearman | Kendall tau-b | Log RMSE | Level MAE |
| --- | ---: | ---: | ---: | ---: |
| Pooled | 0.6293 | 0.4544 | 0.1048 | 23,378.51 |
| Michigan | 0.4903 | 0.3487 | 0.1084 | 24,712.41 |
| Wisconsin | 0.7606 | 0.5601 | 0.0972 | 20,710.72 |

Five Michigan observations across three physical locations remained excluded from fitting only for `GEO05_ANCHOR_TRACT_MISSING_OR_AMBIGUOUS` and remained in protected accounting and QA. No incompatible sample was used.

## Frozen experiment matrix

All candidates used the same eligible evidence and grouped folds. Only convergent points in the frozen 12-point elastic-net grid were eligible; a point had to converge in every inner fold and on the complete current training fold. No broad search or target-conditioned feature revision occurred.

| Candidate | Features | Pooled Spearman | MI Spearman | WI Spearman | Pooled log RMSE | Pooled level MAE | Stability |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A — reproduced MODEL-13 | 11 | **0.6293** | 0.4903 | **0.7606** | **0.1048** | **23,378.51** | 0.8826 |
| B — A + LODES | 25 | 0.6046 | **0.4961** | 0.7193 | 0.1117 | 24,600.40 | 0.8076 |
| C — A + business context | — | not run | not run | not run | not run | not run | not run |
| D — A + traffic/accessibility | 13 | 0.6003 | 0.4634 | 0.7235 | 0.1053 | 23,983.43 | 0.8083 |
| E — A + richer ACS | 22 | 0.5867 | 0.4625 | 0.7161 | 0.1077 | 24,353.44 | 0.7367 |
| F — A + all 27 evaluation-ready features | 38 | 0.5976 | 0.4766 | 0.7435 | 0.1157 | 24,783.17 | 0.7219 |

Every expanded candidate underperformed the reproduced baseline on pooled ranking and pooled error. Traffic came closest on log RMSE but still reduced pooled, Michigan, and Wisconsin ranking and increased MAE. The combined candidate added 27 features without recovering baseline performance and showed the weakest coefficient stability.

## Strongest expanded candidate and interpretation

Candidate B, MODEL-13 plus LODES, was the strongest expanded candidate by the frozen primary ordering of pooled then Michigan/Wisconsin ranking. Relative to baseline:

| Domain | Spearman delta | Kendall delta | Log RMSE delta | Level MAE delta |
| --- | ---: | ---: | ---: | ---: |
| Pooled | -0.0246 | -0.0208 | +0.0068 | +1,221.88 |
| Michigan | +0.0058 | +0.0048 | +0.0042 | +876.70 |
| Wisconsin | -0.0413 | -0.0439 | +0.0126 | +1,912.24 |

The small Michigan ranking gain did not offset the pooled and Wisconsin decline or worse errors. Removing LODES from candidate B reproduced candidate A, improving pooled and Wisconsin ranking and every pooled error measure. This is the decisive family ablation.

LODES fold stability was mixed: 13 of 14 LODES terms were nonzero in at least one outer fold, only one was nonzero in every fold, and mean selection frequency was 0.5286. Pooled fold Spearman ranged from 0.2583 to 0.7226; Wisconsin fold Spearman ranged from 0.1167 to 0.9048. Its maximum held-out physical-location absolute log error was 0.2822 versus 0.2637 for baseline. Removing the worst-error location changed pooled Spearman by only -0.0001, so the overall degradation was not attributable to one material outlier.

The strongest standardized LODES signals were workplace job mass (positive, 0.0538; selected in 60% of outer folds), retail-trade job share (negative, -0.0161; 80%), accommodation/food job share (positive, 0.0135; 60%), and workplace-block concentration (positive, 0.0093; 80%, with 75% dominant-sign agreement). Workplace mass and food-service intensity are plausible mechanisms; the negative retail-share signal and limited cross-fold selection reinforce the decision not to treat this formulation as a successor.

## Pre-H conclusion and safeguards

Evidence disposition: **no credible improvement**.

This is a completed experimental result, not an access-limited result and not evidence that every future public feature source is unhelpful. The admitted features were fully computable on the development cohort, but none of the bounded expanded formulations credibly improved accepted MODEL-13. MODEL-13 remains accepted and unchanged.

- No sealed, prospective Milwaukee, Madison, future-vintage, validation-only, or otherwise unconsumed target was opened.
- No race, ethnicity, sex, religion, age-composition, or other protected-characteristic feature was used.
- No protected row, identity, coordinate, target, prediction, residual, registry, path, or prohibited digest entered Git or GitHub.
- Experimental sources remain unaccepted candidate inputs; DATA-03, DATA-04, and GEO-05 authority is unchanged.
- APP-01 remains accepted and unchanged. PBI-02 remains separate and unmodified.
- No production scoring package was created or promoted.

Exact next destination: **MASTER CONTROL ROOM: Sprouts Customer Geography**
