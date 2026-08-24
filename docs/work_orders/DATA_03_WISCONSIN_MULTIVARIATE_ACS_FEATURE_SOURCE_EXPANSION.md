# DATA-03: Wisconsin Multivariate ACS Feature Source Expansion

## Authority and outcome boundary

Master Control Room authorized this Lane B task to expand Wisconsin public-source and variable authority for a later, separately authorized multivariate development round. Exact substantive H is accepted or rejected by `DATA Public Data Sources`. DATA-03 cannot self-accept, create acceptance-record-only A, merge, deploy, or begin MODEL-11 or any other follow-on task.

DATA-03 is source and variable authority only. It does not access targets or protected analytical outputs, fit a model, screen variables against performance, estimate coefficients, select a final model feature set, score geography, or change MODEL-09. The accepted menu below is justified only by business meaning, public-data quality, reproducibility, tract coverage, and potential usefulness in later disciplined modeling.

## Accepted source and geography boundary

The only new analytical source family is the U.S. Census Bureau `2020-2024 ACS 5-Year Detailed Tables`, vintage `2024`. The geography is the complete set of Wisconsin Census tracts identified by state FIPS `55`. Exact 2024 TIGER/Line Wisconsin tract authority remains `DATA02_TIGER2024_WI_TRACT_SOURCE_MANIFEST_V1`; DATA-03 reuses it for tract-key reconciliation and does not create or reinterpret geography methodology.

DATA-03 is additive to `DATA01_VALIDATION_SOURCE_CONTRACT_V1` and the accepted DATA-02 manifests. It does not overwrite, supersede, or reinterpret B11001 household-opportunity authority. Its logical identity is `DATA03_WISCONSIN_MULTIVARIATE_ACS_FEATURE_SOURCE_CONTRACT_V1`.

The official Census data endpoint is pinned as `https://api.census.gov/data/2024/acs/acs5`. The equivalent query uses an ordered `get` list containing every accepted estimate/MOE variable below, `for=tract:*`, and `in=state:55`. A credential, when available, is supplied only as `CENSUS_API_KEY`; it is never part of request identity, logs, manifests, fixtures, or output. On 2026-08-23 the endpoint returned the Census `Missing Key` gate without a credential. Therefore the required real DATA-03 acquisition uses the exact official 2024 table-based Summary File URLs, one file per accepted table. This is an access-surface choice within the same product/release/vintage, not a source substitution. No latest/current alias is permitted.

## Accepted bounded candidate menu

Every source estimate has its same-line ACS MOE. Direct measures preserve the published estimate and MOE. The deterministic percentages are source-safe candidate measures, not final model features.

| Family | Candidate measure | Exact 2024 ACS Detailed Table variables | Source-safe construction |
| --- | --- | --- | --- |
| Economic capacity | `median_household_income` | `B19013_001E` / `B19013_001M` | Direct 2024 inflation-adjusted dollars |
| Economic capacity | `per_capita_income` | `B19301_001E` / `B19301_001M` | Direct 2024 inflation-adjusted dollars |
| Economic capacity | `civilian_labor_force_share` | `B23025_003E` / `B23025_003M`; denominator `B23025_001E` / `B23025_001M` | Civilian labor force divided by population 16 years and over |
| Economic capacity | `employment_rate` | `B23025_004E` / `B23025_004M`; denominator `B23025_003E` / `B23025_003M` | Employed divided by civilian labor force |
| Education / socioeconomic structure | `bachelors_or_higher_share` | Numerator `B15003_022E` through `B15003_025E` with paired MOEs; denominator `B15003_001E` / `B15003_001M` | Bachelor's, master's, professional-school, and doctorate estimates summed, then divided by population 25 years and over |
| Housing and neighborhood economics | `owner_occupancy_share` | `B25003_002E` / `B25003_002M`; denominator `B25003_001E` / `B25003_001M` | Owner-occupied divided by occupied housing units |
| Housing and neighborhood economics | `vacancy_share` | `B25002_003E` / `B25002_003M`; denominator `B25002_001E` / `B25002_001M` | Vacant divided by total housing units |
| Housing and neighborhood economics | `median_home_value` | `B25077_001E` / `B25077_001M` | Direct dollars for owner-occupied housing units |
| Housing and neighborhood economics | `median_gross_rent` | `B25064_001E` / `B25064_001M` | Direct dollars for renter-occupied units paying cash rent |
| Household scale | `average_household_size` | `B25010_001E` / `B25010_001M` | Direct average household size for occupied housing units |
| Transportation / accessibility | `no_vehicle_household_share` | `B08201_002E` / `B08201_002M`; denominator `B08201_001E` / `B08201_001M` | Households with no vehicle available divided by households |
| Transportation / accessibility | `drive_alone_commuter_share` | `B08301_003E` / `B08301_003M`; denominator `B08301_001E` / `B08301_001M` | Workers age 16 and over who drove alone divided by workers age 16 and over |
| Transportation / accessibility | `work_from_home_commuter_share` | `B08301_021E` / `B08301_021M`; denominator `B08301_001E` / `B08301_001M` | Workers age 16 and over who worked from home divided by workers age 16 and over |

This 13-measure menu is intentionally small relative to the later development sample. It covers the authorized families without a variable dump. Housing-stock vintage, commute-time approximation, poverty-status measures, and other additional public variables remain deferred because they add dimensionality or interpretation without being necessary for this first multivariate round.

## MOE, missingness, and derivation contract

Published raw estimate and MOE tokens remain lossless in the normalized source output. Empty tokens, nonnumeric tokens, Census special-value sentinels, nonfinite values, invalid negative counts, and missing estimate/MOE pairs receive explicit noncomputable statuses and never become zero. Legitimate zero counts remain valid. Direct non-count measures use their documented domains.

For a sum of mutually exclusive source components, the approximate 90-percent MOE is the square root of the sum of squared component MOEs. For a subset percentage with proportion `p = numerator / denominator`, the approximate MOE is `100 * sqrt(MOE_numerator^2 - p^2 * MOE_denominator^2) / denominator`; when the quantity under the square root is negative, the documented conservative addition fallback replaces subtraction with addition. A missing input, nonpositive denominator, numerator outside `[0, denominator]`, or nonfinite result yields a null derived value and an explicit status. No imputation is authorized.

Every output contains all accepted Wisconsin tract keys exactly once even when a particular measure is noncomputable. Coverage is reported per source variable and candidate measure. A measure with materially unacceptable real coverage or unstable semantics must be removed from the accepted menu before substantive H rather than forced through.

## Provenance and materialization contract

One DATA-03 source manifest is maintained for each of the 11 accepted Detailed Tables: B08201, B08301, B15003, B19013, B19301, B23025, B25002, B25003, B25010, B25064, and B25077. Each reuses the existing DATA-02 source-manifest schema and records the exact table file URL, filename, retrieval date, content length, SHA-256, required headers, exact source-to-contract mapping, metadata endpoint and identity, special-value behavior, attribution, refresh posture, and fail-closed behavior.

Raw downloads and metadata responses remain under ignored local paths. Materialization verifies every source byte checksum before parsing, selects only `GEO_ID` values with exact prefix `1400000US55`, converts them to 11-character Wisconsin tract GEOIDs, rejects duplicate or malformed keys, and reconciles the result exactly to the accepted 2024 TIGER inventory. Table joins are one-to-one and lexicographically ordered by GEOID.

The repository-safe implementation writes two generated artifacts outside Git:

- a normalized source-value file preserving raw tokens, parsed values, statuses, variable IDs, table IDs, and estimate/MOE pairing; and
- a stable wide candidate-measure file containing tract GEOID key fields plus estimate, MOE, and status for each of the 13 measures.

A verification report records contract/manifest identities, request and metadata hashes, raw source checksums, tract coverage, missingness/quality counts, ordered output schema, output checksums, and deterministic rerun evidence. Interrupted or failed acquisition/materialization never produces a ready report, and existing ready output is not silently overwritten.

## Protected-characteristic and target-blind boundary

The accepted candidate scoring menu contains no variables based directly on race, ethnicity, sex, age, disability, religion, national origin, or another protected-class status. Population-age phrases used only to define the standard universe for labor, education, and commuting measures do not authorize age composition as a scoring variable. No variable is selected to reconstruct an excluded protected characteristic. A future request that raises a material protected-characteristic, proxy, legal, or compliance question requires separate review and authority.

DATA-03 must not access Isolated Sales, Impacted Sales, PIPE-04 protected binding content, protected MODEL-09 outputs, protected seed evidence, residuals, coefficients, rankings, predictions, or target-conditioned artifacts. No target performance may influence the menu, coverage thresholds, derivations, or exclusions.

## Required validation and H gate

Tests cover exact 2024 release pinning, Wisconsin tract scope, table/variable identity, estimate/MOE integrity, deterministic API/query construction, metadata/schema drift, duplicate tracts, special and missing values, invalid derived denominators, complete TIGER-key coverage, stable output schema, rerun determinism, stale/latest rejection, raw-data Git exclusion, and protected-characteristic exclusion. Full repository validation must pass.

The completed real verification used all 11 checksum-pinned official table files plus the accepted DATA-02 TIGER ZIP. Each table reconciled exactly to the 1,542-key statewide tract inventory. Two independent materializations produced 33,924 normalized rows and 1,542 candidate rows with byte-identical CSVs, verification report, and ready marker. The normalized and candidate CSV SHA-256 values are respectively `e1125a21706b90b8adebd57e87b9d2f259292301d52b382b12a460b64cb5d4c8` and `90f80871d62c33401a31f0fe895a082a50a26a5a12ceaaa2e89a942b4acb70f3`. All 223 repository unit tests passed with one expected skip, and every required repository conformance check passed before H was frozen.

At substantive H there is exactly one DATA-03 task manifest in `COMPLETED_AWAITING_ACCEPTANCE`, with execution `COMPLETED` and capability acceptance `NOT_REVIEWED`; exactly one controlling DATA-03 work order; exact additive source contract and source manifests; successful real Wisconsin materialization/verification; passing focused and full validation; successful required CI on exact H; and a reviewed disclosure-safe diff containing no target-conditioned or protected material. H is then routed to `DATA Public Data Sources` for Lane B acceptance or rejection. Any substantive post-H change creates a revised H that requires new DATA acceptance.
