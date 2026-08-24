# DATA-04 Michigan public-data parity foundation

DATA-04 adds a statewide, public-only Michigan source contract for the exact 2024 inputs needed by later separately authorized GEO and frozen MODEL-11 work. It reuses the accepted national ACS source bytes and exact DATA-03 definitions, adds exact 2024 Michigan TIGER tract authority, and performs no scoring or protected-evidence access.

The machine-readable authority is `DATA04_MICHIGAN_PUBLIC_DATA_PARITY_SOURCE_CONTRACT_V1` in `config/data/data04_michigan_public_data_parity_source_contract.json`. The controlling work order is [DATA-04: Michigan Public-Data Parity Foundation](work_orders/DATA_04_MICHIGAN_PUBLIC_DATA_PARITY_FOUNDATION.md).

## Exact source boundary

- Michigan state FIPS: `26`
- Michigan table-file tract prefix: `1400000US26`
- ACS product: U.S. Census Bureau 2020–2024 ACS 5-Year Detailed Tables, 2024 vintage
- Household table: accepted national B11001 file and byte identity, `B11001_001E` / `B11001_001M`
- Multivariate menu: exact accepted DATA-03 11 tables, 22 estimate/MOE pairs, and 13 measures
- TIGER product: exact official `tl_2024_26_tract.zip`, 2024 vintage
- Observed statewide tract inventory: 3,017 unique canonical tract GEOIDs

The accepted Wisconsin contracts and manifests remain unchanged. The Wisconsin-labeled ACS manifests continue to govern the already accepted national file byte identities and their Wisconsin extraction identity; DATA-04's additive contract separately governs deterministic Michigan row selection from those exact national bytes.

## Acquisition

The exact national DATA-03 table files may be reused from their checksum-verified ignored local storage. B11001 and Michigan TIGER are likewise recovered or downloaded only from their fixed official URLs. No Census API key is used.

```powershell
python -m sprouts_customer_geography.data04 verify-contract

python -m sprouts_customer_geography.data04 acquire `
  --acs-raw-dir data/raw/data03 `
  --household-source data/local/acsdt5y2024-b11001.dat `
  --tiger-raw-dir data/raw/data04 `
  --observation-output-dir outputs/data04-acquisition
```

Acquisition reuses a complete file only after observing and requiring the accepted byte length and SHA-256. An incomplete `.partial` file is never promoted. An existing checksum mismatch fails closed and is not silently repinned.

## Statewide materialization

```powershell
python -m sprouts_customer_geography.data04 materialize `
  --acs-raw-dir data/raw/data03 `
  --household-source data/local/acsdt5y2024-b11001.dat `
  --tiger-source data/raw/data04/tl_2024_26_tract.zip `
  --output-dir outputs/data04-run-1

python -m sprouts_customer_geography.data04 materialize `
  --acs-raw-dir data/raw/data03 `
  --household-source data/local/acsdt5y2024-b11001.dat `
  --tiger-source data/raw/data04/tl_2024_26_tract.zip `
  --output-dir outputs/data04-run-2

python -m sprouts_customer_geography.data04 compare `
  outputs/data04-run-1 `
  outputs/data04-run-2 `
  --comparison-output outputs/data04-deterministic-comparison.json
```

Each run is immutable and writes top-level `READY.json` last. The generated package remains outside Git and contains:

- `michigan_b11001_tract_evidence.csv` with raw and parsed estimate/MOE evidence and explicit status;
- `michigan_tiger_tract_evidence.csv` with canonical components, raw/parsed internal points, geometry-record status, source CRS, and lineage;
- `multivariate/michigan_tract_source_values.csv` for all 22 accepted DATA-03 component pairs;
- `multivariate/michigan_tract_candidate_measures.csv` for all 13 accepted measures;
- the multivariate verification subreport and READY marker;
- the top-level reconciliation/readiness `verification_report.json`; and
- the top-level READY marker.

B11001 must have exactly the complete TIGER key set. Every multivariate table is reconciled independently to the complete TIGER inventory, and its observed present/missing/extra source-row counts must match the contract's pinned reconciliation. A missing table row remains in output as explicit `source_row_missing` evidence; a present row with a missing, special, inapplicable, suppressed, invalid, or invalid-denominator value retains its raw token and distinct explicit status. Unexpected coverage fails closed. No value is imputed or converted to zero, and no tract is dropped.

## Readiness and exclusions

The report verifies complete source-side prerequisites for a later Michigan GEO task: exact TIGER manifest, complete statewide keys, geometry records, parseable internal points, EPSG:4269 source CRS, 2024 vintage, B11001, and all DATA-03 components/measures. It does not create a Michigan market inventory or alter EPSG:5070, 3/5/7-mile radii, boundary, membership, or containing-tract semantics.

It also reports whether all public source families required by the accepted frozen MODEL-11 feature definitions are present. It does not access seeds, sales, targets, fitted parameters, coefficients, predictions, residuals, or protected bindings and does not fit, tune, calibrate, evaluate, or score a model.

The DATA-03 protected-characteristic exclusion remains exact. No scoring-source variable based directly on race, ethnicity, sex, age composition, disability, religion, national origin, or another protected-class basis is added.

## Verified execution evidence

The real public-only execution verified 3,017 unique Michigan TIGER tract keys, geometry records, and parseable internal points. B11001 contained 3,017 valid estimate/MOE rows. The multivariate output retained all 3,017 keys and produced 66,374 normalized component rows plus 3,017 13-measure rows.

B19301 was the only table without a complete source-row set: six of the 3,017 TIGER tracts were absent from that national table's Michigan rows. Those six output keys are retained with explicit missing status and `source_row_missing` status detail; they are not collapsed into a sentinel, converted to zero, or deleted. The other ten tables had complete source-row key equality. Candidate-measure computability ranged from 2,629 valid tracts for median gross rent to 2,914 for the most complete derived shares. The median-gross-rent result preserves 382 missing and six inapplicable values; other direct and zero-universe missingness remains explicit in the verification report.

Two independent Michigan materializations were byte-identical across all eight files. Principal output SHA-256 values were:

- B11001 evidence: `0a9368f237989b5622b9f483486af5509e737961a567c0bf23be27860d7b3041`
- TIGER evidence: `d1a0b6187674c6c7d945a37b38b8b5556ff77ce87c97a61a8fa239597dd5b2f3`
- normalized multivariate evidence: `b16af0a30110123312c0ff6c7484dda64a4d8c28abed8c6f38744e1ba0ee564d`
- 13-measure output: `adcc5ce6b08bb9973ccb5d76ac59162013d7db524e266d18585719581cca9198`
- top-level verification report: `ed746f3e7f23409f7d4f1dec85ccf4ec2d54ed05391cc2c0b61ed37004bd9c4e`
- top-level READY marker: `1b80d3e64ca58b8b70cdd05a6a3c46242a9fc0ac6e8bee896ba1430d509109e0`

The real Wisconsin regression reproduced the accepted DATA-03 normalized and candidate CSV hashes exactly: `e1125a21706b90b8adebd57e87b9d2f259292301d52b382b12a460b64cb5d4c8` and `90f80871d62c33401a31f0fe895a082a50a26a5a12ceaaa2e89a942b4acb70f3`. All ten repository conformance checks and all 258 unit tests passed, with the one expected raw-source skip. Raw tract-level evidence remains outside Git.
