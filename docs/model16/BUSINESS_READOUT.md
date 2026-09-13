# MODEL-16 business readout

Retain MODEL-13 for now. MODEL-16 found a credible development challenger, but its one-time tests did not establish a consistent improvement across Michigan and Wisconsin. Generation 1 is complete and closed to retuning. Further development would require a newly authorized descendant generation; this result grants no acceptance, replacement or merge authority.

The comparison used 50 target-blind features and 41 bounded candidates. The sole frozen challenger was ridge regression with the food-access family removed. Its development rank correlation rose from 0.465 to 0.500 and log RMSE fell about 5.9%, with the required state, stability, fold, family and location checks satisfied before holdout access.

| Evidence | Locations | Baseline Spearman | Challenger Spearman | Baseline log RMSE | Challenger log RMSE |
| --- | ---: | ---: | ---: | ---: | ---: |
| Grouped development validation | 70 | 0.4652 | 0.4996 | 0.1158 | 0.1090 |
| One-time 2026 Seed Points | 62 | 0.7091 | 0.7144 | 0.1085 | 0.1060 |
| One-time independent pursued sites | 36 | 0.5354 | 0.4499 | 0.1985 | 0.1938 |

The 2026 improvement was smaller than the frozen threshold, and Wisconsin ranking declined beyond the allowed margin. On pursued sites, pooled ranking declined despite a modest error improvement. Michigan pursued-site ranking was weak for both methods and almost zero for the challenger; its Michigan log error also increased beyond the allowed margin. Wisconsin pursued-site error improved, but ranking declined beyond the permitted margin. These mixed results do not support a two-state replacement.

The baseline in this experiment is the clean MODEL-13 method refitted on the authorized development evidence and historical public sources. It is not a rerun or modification of the accepted MODEL-13 artifact. The targets are isolated forecasts: these tests assess agreement with those forecasts, not realized store sales or measured customer behavior.

## What the public-data comparison contributed

Employment mass and job/resident balance provided the clearest family-addition improvement: pooled ranking increased about 0.078 and log error improved in both states relative to the same ridge method with baseline terms. Housing/urban form and road/intersection context also improved error in both states. Permits improved pooled ranking but worsened error, particularly in Wisconsin. Travel accessibility had mixed state error effects. The remaining families showed small, mixed or absent incremental gains in these bounded comparisons.

These are conditional development findings. Family additions and removals answer different questions because predictors overlap; they are not causal effects or proof that a source is universally useful or useless. Sparse transit coverage and stale structural snapshots limit interpretation. Removing food-access terms qualified as a challenger formulation; it does not establish that food access is irrelevant to customers.

## Evidence and limits

All 240 original observations remain accounted for across 171 physical locations. Development began with 142 observations at 73 locations. Five Michigan observations at three locations lacked unambiguous baseline geography, leaving 137 fitting observations at 70 locations. Different forecast years were preserved, all years at a location stayed together in validation, and each location received equal total fitting weight.

No duplicate or unresolved identity finding remained. Target-blind reconciliation found no pursued-site/Seed Point physical overlap. All 36 pursued sites were independent of every Seed Point location; there was no matched-location sample to score. All 62 temporal locations were also outside development locations. No 2,000-foot rule merged or removed Seed Points, and pursued-site names never became Seed Point IDs.

The primary source track uses verified historical releases. It excludes retrieved ACS and geometry revisions that could not establish the preceding-year cutoff. Direct protected characteristics, Impacted Sales, adjusted pursued forecasts, paid data and current store-network information were not model inputs. Raw sources, exact identities, targets, fitted parameters and private commitments remain protected-local.

The source investigation recorded 179 requests, with 174 verified retrievals and five failed discovery endpoints. It materially broadened the feature comparison but did not exhaust free public data. Historically reconstructed store-level competition/co-tenancy, detailed traffic and hourly direction, and release-pinned remote sensing remain untested. The sample is modest, the broad candidate selection still creates selection uncertainty, and older structural sources cannot describe every later market change.

See the [complete results](RESULTS.md), [machine-readable diagnostics](RESULTS.json), [source research](PUBLIC_SOURCE_RESEARCH.md), [feature catalog](../../config/model16/feature_catalog.json), and [reconstruction record](EXECUTION_AND_RECONSTRUCTION.md). Ray's next decision is whether to retain the current accepted model without further work or authorize a distinct future development effort. No such follow-on effort has begun.
