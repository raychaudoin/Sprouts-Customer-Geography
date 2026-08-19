# PIPE-01B production freeze adapters and orchestration

## Scope

PIPE-01B implements the smallest production-form execution layer around accepted PIPE-01 calculation, schema, staging, conformance, commitment, and finalization controls. It does not run the real protected freeze, open a sealed forecast target, or change accepted DATA/GEO/MODEL analytical authority.

## Implemented boundary

- The GEO-03 runtime verifies operation fingerprint `3c7421053e63df6e120d8aefd142399c9c53e6a1594ed23c37c644609a21bf14`, normalized longitude/latitude input, NAD83/EPSG:4269 source semantics, direct Conus Albers EPSG:5070 projection, no ballpark/grid datum operation, and runtime provenance.
- The TIGER adapter verifies the DATA-02 manifest, filename, byte length, source checksum, ZIP members, DBF/SHP alignment, GEOID structure, exact canonical inventories, raw `INTPTLAT`/`INTPTLON`, parse states, and full polygon geometry.
- The GEO-02 adapter constructs projected primary footprints, canonical market support unions, positive-area tract intersections, truncation/completeness, in-market continuous geometric Jaccard, and threshold-graph connected components. It creates no membership Jaccard.
- The ACS adapter verifies the exact table-based B11001 artifact and preserves raw estimate/MOE tokens, parsed values, explicit special-value state, absent-annotation provenance, source/vintage identity, and inventory binding. Special or missing values never become zero.
- Protected orchestration verifies the MODEL-04 package commitment and MODEL-05 preregistration, strictly binds the accepted dependency preflight, derives anchor tract only by unique official polygon containment, reuses PIPE membership/aggregation/readiness/baseline logic, stages outputs outside Git, finalizes immutably, and emits only a disclosure-safe report at the CLI boundary.

`pyproj>=3.7,<4` and `shapely>=2.1,<3` are the only added runtime dependencies. They supply the accepted projection runtime and polygon operations; DBF and shapefile ingestion remain narrow repository code to avoid a broader GIS stack.

## Confidentiality and execution status

All committed tests and descriptions use fictional protected identities. Exact Census source bytes remain ignored local data. The full production-path conformance fixture uses an official public TIGER internal point labeled as fictional; it is not derived from a real Sprouts seed. Temporary membership, household, prediction, nonce, manifest, and commitment artifacts are written outside the repository and removed after the test.

No real protected freeze was produced. No real MODEL-04 row, real seed identifier or coordinate, seed-level total, prediction, nonce, or sealed target was accessed or committed.

## Authorization gate

The implementation must return to `PIPE: Analytical Pipeline Decisions & Acceptance`. Only PIPE acceptance and a later separate Master Control Room authorization may permit execution with the accepted real protected inputs. This record is implementation evidence, not self-acceptance or execution authorization.

## Conformance evidence

- Full repository suite: 84 tests passed with the exact pinned public sources supplied; no skips or failures.
- Structural repository guard: 12 PIPE schemas found and tracked-path confidentiality safeguard passed.
- Exact TIGER result: source SHA-256 matched DATA-02; 452 Milwaukee plus 152 Madison accepted tracts reproduced in canonical order, with all 604 source geometries and internal-point records bound.
- Exact ACS result: source SHA-256 matched DATA-02; 1,542 Wisconsin tract rows parsed, and all 604 accepted market tracts bound with estimate/MOE/status provenance.
- Fictional end-to-end result: one genuinely fictional protected context completed authoritative dependency binding, GEO-02/GEO-03, ACS aggregation, readiness, MODEL-05 baseline generation, staging, conformance, immutable finalization, final-marker-last, and disclosure-safe commitment creation through the production path.

Interruption remains incomplete without `FROZEN.json`; a run ID is never reusable; corrections require a new run with explicit `supersedes` lineage. Source, dependency, CRS/operation, inventory, anchor-containment, missingness, target-field, protected-root, and finalization mismatches fail closed.

## Limitations and residual risk

- The accepted GEO-02 specification defines metric footprints but not a cross-runtime curve tessellation parameter. PIPE-01B pins 64 quadrant segments and records the Shapely/GEOS execution provenance so PIPE can disposition reproducibility at acceptance.
- The pinned table-based ACS source contains no annotation columns. The adapter preserves `annotation=null`, raw jam tokens, and explicit status detail exactly as DATA-02 requires; any later API-annotation use requires a separately accepted source.
- The production path is locally functional, but real execution remains gated by PIPE acceptance and separate Master Control Room authorization. No target-opening permission is implied.

## Control Room Decision Record

- **Decision requested:** Accept or reject PIPE-01B production adapters and orchestration as conforming to the accepted PIPE/DATA/GEO/MODEL contracts.
- **Recommended disposition:** Accept for capability completion; do not authorize the real protected freeze in the same decision.
- **Promotion state:** Local implementation only; no merge, push, promotion, deployment, or real protected execution.
- **Next destination:** `PIPE: Analytical Pipeline Decisions & Acceptance`.

### Business Takeaway

- **Scenario:** Every accepted DATA, GEO, and MODEL dependency is available, while PIPE previously lacked production connectors.
- **Issue/Goal:** Complete the end-to-end execution path without mixing new implementation changes with the first real protected validation freeze.
- **Solution/Decision:** Add only checksum-pinned source adapters, accepted spatial execution, and protected orchestration, then prove them with exact public sources and a genuinely fictional protected fixture.
- **Business impact / Next step:** PIPE can now review the implementation for acceptance; only a later separate authorization may start the real target-blind freeze, and all Sprouts validation forecasts remain sealed.
