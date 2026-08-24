# DATA-03 Wisconsin multivariate ACS feature source

DATA-03 adds a target-blind, repository-safe source contract for 13 candidate measures drawn from 22 estimate/MOE pairs in 11 exact 2024 ACS 5-Year Detailed Tables. It is additive to DATA-01/DATA-02, reuses accepted 2024 TIGER Wisconsin tract authority, and grants no model-fitting, feature-selection, scoring, or target-access authority.

The controlling variable menu and source-safe derivations are documented in the [DATA-03 work order](work_orders/DATA_03_WISCONSIN_MULTIVARIATE_ACS_FEATURE_SOURCE_EXPANSION.md). Machine-readable authority is `DATA03_WISCONSIN_MULTIVARIATE_ACS_FEATURE_SOURCE_CONTRACT_V1` in `config/data/data03_wisconsin_multivariate_acs_feature_source_contract.json`. Each Detailed Table has a checksum-pinned source manifest under `data/manifests/`.

## Access and acquisition

The equivalent API query is pinned to `https://api.census.gov/data/2024/acs/acs5`, all 44 ordered estimate/MOE variables, `for=tract:*`, and `in=state:55`. It can be inspected without a credential:

```powershell
python -m sprouts_customer_geography.data03 api-query
```

The Census data endpoint was key-gated at retrieval, so real acquisition uses the exact official 2024 table-based Summary File for each accepted Detailed Table. This is the same fixed release and product, not a vintage or source substitution. Raw bytes and metadata responses stay under ignored local storage:

```powershell
python -m sprouts_customer_geography.data03 acquire `
  --raw-dir data/raw/data03 `
  --observation-output-dir outputs/data03-acquisition
```

Acquisition observations are explicitly non-authoritative. Repository source manifests establish the accepted byte identities only through the governed H/A lifecycle. Existing complete raw files are checksum-observed and reused; incomplete `.partial` files never become complete inputs.

## Materialization and deterministic verification

Materialization requires all 11 source manifests, their exact raw bytes, cached official metadata, and the accepted DATA-02 TIGER ZIP:

```powershell
python -m sprouts_customer_geography.data03 materialize `
  --raw-dir data/raw/data03 `
  --output-dir outputs/data03-run-1

python -m sprouts_customer_geography.data03 materialize `
  --raw-dir data/raw/data03 `
  --output-dir outputs/data03-run-2

python -m sprouts_customer_geography.data03 compare `
  outputs/data03-run-1 outputs/data03-run-2
```

Each output directory is immutable: overwrite is denied and `READY.json` is written last. Generated artifacts remain outside Git:

- `wisconsin_tract_source_values.csv` is normalized and lossless with respect to raw estimate/MOE tokens, parsed values, statuses, variable IDs, and table lineage.
- `wisconsin_tract_candidate_measures.csv` has the stable ordered schema for 13 direct or source-safe derived measures, with estimate, MOE, status, and status detail for every tract key.
- `verification_report.json` records contract/manifests, source hashes, metadata identity, complete tract reconciliation, coverage, schema, and output hashes.
- `READY.json` binds the verified report and output hashes after successful completion.

## Real Wisconsin verification

The 2026-08-23 materialization verified all 11 exact source checksums and reconciled every table to all 1,542 unique 2024 TIGER Wisconsin tract keys. It produced 33,924 normalized source rows and 1,542 candidate-measure rows. An independent rerun was byte-identical for both CSVs, the verification report, and the ready marker.

All retained measures had at least 1,494 computable tract values (96.9 percent). Noncomputability remained explicit: 17–18 zero-universe tracts affected source-safe percentages; direct published measures had 17 missing per-capita-income tracts, 18 missing average-household-size tracts, 20 missing median-household-income tracts, 42 missing median-home-value tracts, and 47 missing plus one inapplicable median-gross-rent tract. These are preserved quality states, not imputed values, dropped tract keys, or reasons to substitute a different variable.

The materialization accessed only public Census data. It did not access targets, protected analytical outputs, seed evidence, coefficients, residuals, rankings, or predictions. The candidate menu contains no protected-characteristic scoring variable and does not authorize obvious proxy reconstruction.
