# DATA-04: Michigan Public-Data Parity Foundation

## Authority and outcome boundary

Master Control Room authorized this Lane B task to establish the complete statewide Michigan public-source foundation required by later, separately authorized geography and frozen-model work. Exact substantive H is accepted or rejected by `DATA Public Data Sources`. DATA-04 cannot self-accept, create acceptance-record-only A, merge, score Michigan, access protected evidence, or begin a follow-on task.

The authorized implementation branch is `task/data-04-michigan-public-data-parity-foundation`, based on canonical `main` commit `0b0027691905e908990212ee7f5133454ab47b24`. This work order and `governance/tasks/DATA-04.michigan-public-data-parity-foundation.task.json` are the only controlling DATA-04 durable task records.

## Business and geography objective

DATA-04 creates configuration-driven Michigan parity with the accepted Wisconsin public inputs needed by MODEL-11. The state is Michigan, state FIPS is `26`, and the geography is the complete statewide 2024 Census tract set. An Ann Arbor-only, Detroit-only, market-selected, block-group, seed-selected, or other partial inventory is prohibited.

The fixed products are:

- U.S. Census Bureau `2020-2024 ACS 5-Year Detailed Tables`, 2024 vintage;
- official non-authenticated 2024 table-based ACS Summary File distribution; and
- official `2024 TIGER/Line Census Tracts` for Michigan.

No moving source, alternate vintage, Census API-key dependency, derivative geography, LODES, Overture, licensed source, commercial demographics, or another state may substitute for these products.

## Exact accepted ACS reuse

The accepted table-based ACS files are national fixed-release files. DATA-04 must recover each accepted Wisconsin manifest and reuse its exact source filename, URL, byte length, SHA-256, metadata identity, table/variable mapping, and vintage. If an accepted raw file is absent, reacquire that exact official fixed file and require the accepted checksum. A byte mismatch for an already accepted fixed national file is a source-integrity blocker; it must not be repinned silently.

Only deterministic geography extraction changes:

- Michigan `GEO_ID` prefix: `1400000US26`;
- canonical tract GEOID: the 11 text characters following `1400000US`; and
- every retained GEOID must match `^26[0-9]{9}$`.

Raw estimate and MOE tokens remain separate from parsed values and statuses. Missing source rows, present rows with missing values, official special/sentinel values, invalid values, and zero-universe denominators remain distinct. Missing values never become zero, no value is imputed, and no tract key is dropped because a measure is noncomputable.

## Required household evidence

Michigan receives exact parity with accepted DATA-02 B11001 household evidence using national file `acsdt5y2024-b11001.dat` and its accepted source-byte identity.

- Contract estimate variable: `B11001_001E`;
- contract MOE variable: `B11001_001M`;
- source estimate field: `B11001_E001`; and
- source MOE field: `B11001_M001`.

The normalized output preserves raw tokens, parsed estimate/MOE values, status, status detail, source variables, source manifest identity, and canonical Michigan tract identity. B11001 is mandatory because later public feature construction uses it for five-mile household opportunity, 3/5/7-mile spatial concentration, and household-weighted direct-profile features.

## Required multivariate evidence

Michigan reuses the exact accepted `DATA03_WISCONSIN_MULTIVARIATE_ACS_FEATURE_SOURCE_CONTRACT_V1` authority without reconstructing it from memory. The implementation must require exact equality for its 11 ordered Detailed Tables, 22 ordered estimate/MOE component pairs, component IDs, labels, predicate types, domains, metadata identity, special-value contract, derivation semantics, protected-characteristic exclusion, and 13 ordered candidate measures.

The ordered measure menu remains:

1. `median_household_income`
2. `per_capita_income`
3. `civilian_labor_force_share`
4. `employment_rate`
5. `bachelors_or_higher_share`
6. `owner_occupancy_share`
7. `vacancy_share`
8. `median_home_value`
9. `median_gross_rent`
10. `average_household_size`
11. `no_vehicle_household_share`
12. `drive_alone_commuter_share`
13. `work_from_home_commuter_share`

Direct-measure, component-sum MOE, subset-percentage MOE, negative-radicand fallback, invalid-denominator, invalid-subset, special-value, missingness, no-imputation, units, and MOE semantics are exactly those accepted by DATA-03. DATA-04 grants no authority to select a MODEL feature or change a formula.

## Michigan TIGER authority

Acquire and pin `https://www2.census.gov/geo/tiger/TIGER2024/TRACT/tl_2024_26_tract.zip`. The additive repository-safe source manifest records the exact publisher/product/vintage, source URL and filename, retrieval date, byte length, SHA-256, required archive members, attribution/terms, reproduction, failure, and supersession behavior.

Materialization verifies the archive before interpretation and requires each source record to contain `STATEFP`, `COUNTYFP`, `TRACTCE`, `GEOID`, `INTPTLAT`, and `INTPTLON`. Require `STATEFP == 26`, three-digit county, six-digit tract, `GEOID == STATEFP + COUNTYFP + TRACTCE`, a unique complete sorted statewide key set, source CRS `EPSG:4269`, and lossless internal-point raw/parsed/status evidence. Malformed and duplicate source records fail closed.

The observed statewide tract count comes from the exact official TIGER and ACS evidence, not from memory or a user-supplied expectation. After observation, the accepted DATA-04 contract pins that count and requires exact ACS/TIGER reconciliation.

## Configuration-driven implementation contract

Use one reusable public-source machinery path rather than a copied Michigan application. The smallest authorized refactor may extract state-agnostic acquisition, parsing, materialization, output naming, GEOID validation, and TIGER validation primitives from DATA-03, with explicit Wisconsin and Michigan configuration supplied by their contracts.

Accepted Wisconsin contract and manifest bytes, logical IDs, CLI defaults, filenames, report identities, state-specific error behavior, and output semantics remain unchanged. Existing DATA-03 tests must pass. Given the accepted pinned Wisconsin inputs, the real Wisconsin materialization must remain byte-identical to its accepted output hashes. Any Wisconsin behavior change must be corrected before H.

## Repository-safe additive authority

DATA-04 adds one Michigan public-data source contract, one Michigan TIGER source manifest, one B11001 Michigan extraction manifest/identity, and state-scoped ACS extraction identities that reference rather than duplicate or repin the accepted national DATA-02/DATA-03 byte authority. It adds only schemas, implementation, tests, docs, and concise aggregate verification evidence needed to reproduce and validate the task.

Accepted DATA-01, DATA-02, DATA-03, GEO-03, GEO-04, MODEL-11, and Wisconsin source-manifest files must not be modified or superseded. No second provenance framework or Michigan market inventory is authorized.

Raw downloads, metadata caches, shapefiles, tract-level outputs, and bulk reports remain under ignored `data/raw/`, `data/cache/`, or `outputs/` paths. Git guards must reject raw/generated output from tracked scope.

## Real materialization and deterministic verification

Before H, run public-data-only materialization twice independently. Each immutable output directory is created incomplete-first and writes `READY.json` last. At minimum each run contains:

1. normalized Michigan B11001 estimate/MOE evidence;
2. normalized Michigan DATA-03 component estimate/MOE evidence;
3. the Michigan 13-measure tract dataset with estimate, MOE, status, and status detail;
4. verified Michigan TIGER tract geometry-source and internal-point evidence;
5. one verification report binding exact contract/manifests, source hashes, schemas, coverage, tract reconciliation, ordered columns, and output hashes; and
6. one immutable READY marker.

The two runs must be byte-identical for all deterministic generated artifacts. Existing ready output is never overwritten. Partial downloads retain a `.partial` suffix and never become authoritative input. Complete checksum-verified raw bytes may be reused.

Every ACS table is reconciled independently to the TIGER set. A whole missing ACS row is reported separately from a present noncomputable measure or special token. Every TIGER key appears exactly once in household, component, and candidate outputs.

## Downstream readiness boundary

DATA-04 prepares, but does not execute or reinterpret, GEO. The verification report must expose the Michigan TIGER manifest identity, complete statewide canonical GEOIDs, source geometry availability, parseable `INTPTLAT`/`INTPTLON` evidence and status, source CRS/vintage, exact ACS identities, B11001 availability, and all DATA-03 component/measure availability. The accepted 3/5/7-mile radii, forced containing-tract semantics, and EPSG:5070 transformation remain unchanged and Wisconsin-bound downstream authority is an expected later-task condition.

DATA-04 also verifies that every public source family required by the accepted frozen MODEL-11 public feature definitions is available for Michigan. It must not inspect coefficients, fitted parameters, seeds, targets, predictions, residuals, or protected outputs, and must not fit, tune, calibrate, evaluate, or score the model.

## Protected and protected-characteristic boundaries

Execution is confined to official public Census data and repository-safe accepted authority. Do not inspect Michigan Sprouts evidence, Michigan or Wisconsin seed points, Isolated Sales, Impacted Sales, forecasts, target lineage, PIPE-04 binding, or protected MODEL outputs. No protected filesystem discovery is required.

Preserve DATA-03's exact exclusion of measures directly based on race, ethnicity, sex, age composition, disability, religion, national origin, or another protected-class basis. Standard ACS universe phrases are source metadata only and do not authorize age-composition features. DATA-04 is not a variable-research task.

## Required validation and H gate

Tests and real checks cover canonical-main ancestry; exact ACS product and accepted national bytes; B11001 mapping; DATA-03 table, pair, component, measure, formula, metadata, special-value, and protected-policy parity; Michigan FIPS/prefix/GEOID construction; source checksums and schema drift; TIGER archive/member/field/CRS/internal-point validation; statewide unique keys and ACS reconciliation; missing-row versus missing-value distinctions; invalid denominator and no-imputation behavior; no row deletion; deterministic outputs; immutable READY-last behavior; Michigan/Wisconsin separation; accepted Wisconsin artifacts unchanged; real Wisconsin byte-identical regression; ignored raw/generated paths; downstream GEO fields; and MODEL-11 public-source completeness.

Run all existing repository conformance checks and the full unit-test suite. Preserve the accepted MODEL-11 full-history CI checkout behavior. Review the complete diff and tracked-file inventory for unrelated, large, secret, protected, or Sprouts material.

## Completed real public-source verification

The exact official Michigan TIGER archive was observed at 5,575,554 bytes with SHA-256 `220c0a351d94c9de456d87c5db78f3e3864b3287370350f1e503a84565224e82`. Its DBF and shapefile each contained 3,017 records; all 3,017 GEOIDs were unique, component-consistent, and state FIPS 26; every geometry was structurally valid; every internal point parsed; and the projection metadata matched NAD83 / EPSG:4269 source authority.

The exact accepted national B11001 file and all 11 DATA-03 table files were reused from local ignored storage only after their lengths and SHA-256 values matched accepted manifests. B11001 provided valid estimate/MOE evidence for all 3,017 Michigan tracts. All source keys were reconciled to the TIGER inventory and every output retained the complete sorted 3,017-key set.

B19301 was the only source table with absent Michigan rows: six TIGER tract keys had no B19301 source row. The materializer retains those keys with null raw/parsed evidence, missing status, and distinct `source_row_missing` status detail. It does not collapse them into present-row missing/sentinel states, impute them, convert them to zero, or delete the tracts. The other ten tables had zero missing or extra source rows. At the candidate-measure layer:

- per-capita income had 2,907 valid and 110 missing tracts, including the six absent B19301 rows;
- average household size had 2,894 valid and 123 missing tracts;
- median household income had 2,869 valid, 146 missing, and two inapplicable tracts;
- median home value had 2,836 valid and 181 missing tracts;
- median gross rent had 2,629 valid, 382 missing, and six inapplicable tracts; and
- source-safe shares had 2,897–2,914 valid tracts, with zero-universe denominators retained as explicit invalid/noncomputable states.

Each independent Michigan run produced 3,017 B11001 rows, 3,017 TIGER rows, 66,374 normalized multivariate rows, and 3,017 candidate-measure rows. The two READY packages were byte-identical across all eight files. Key SHA-256 results were:

- B11001: `0a9368f237989b5622b9f483486af5509e737961a567c0bf23be27860d7b3041`;
- TIGER evidence: `d1a0b6187674c6c7d945a37b38b8b5556ff77ce87c97a61a8fa239597dd5b2f3`;
- normalized multivariate evidence: `b16af0a30110123312c0ff6c7484dda64a4d8c28abed8c6f38744e1ba0ee564d`;
- candidate measures: `adcc5ce6b08bb9973ccb5d76ac59162013d7db524e266d18585719581cca9198`;
- verification report: `ed746f3e7f23409f7d4f1dec85ccf4ec2d54ed05391cc2c0b61ed37004bd9c4e`; and
- READY: `1b80d3e64ca58b8b70cdd05a6a3c46242a9fc0ac6e8bee896ba1430d509109e0`.

The shared state-configurable refactor reproduced accepted Wisconsin DATA-03 outputs byte-for-byte: normalized SHA-256 `e1125a21706b90b8adebd57e87b9d2f259292301d52b382b12a460b64cb5d4c8` and candidate SHA-256 `90f80871d62c33401a31f0fe895a082a50a26a5a12ceaaa2e89a942b4acb70f3`. All ten repository conformance checks passed. All 258 repository unit tests passed with one expected skip for an unprovided raw source. The execution used only official public Census data and accessed zero protected or Sprouts evidence.

The verification report confirms complete source-side GEO readiness (manifest, geometry, keys, internal points, CRS, vintage, B11001, and all multivariate outputs) without creating a Michigan market inventory or changing GEO authority. It also confirms every public source family required by frozen MODEL-11 is available, without executing or inspecting the model.

At exact substantive H:

- the sole DATA-04 manifest is `COMPLETED_AWAITING_ACCEPTANCE`;
- execution is `COMPLETED` and capability acceptance is `NOT_REVIEWED`;
- real statewide Michigan materialization and independent comparison are READY;
- the exact observed tract count and material coverage are documented repository-safely;
- Wisconsin behavior and accepted authority are unchanged;
- all local tests/checks and required exact-H CI pass;
- the disclosure-safe Issue and PR identify exact H and the next manual transition; and
- zero protected or Sprouts evidence has been accessed.

Stop at H and route it to `DATA Public Data Sources`. Any substantive post-H change creates a revised H requiring new DATA acceptance. Do not create A, merge, or begin Michigan GEO/MODEL execution.
