# GEO-05: Michigan Statewide Geography Enablement

## Authority and outcome boundary

Master Control Room authorized this Lane B task to make the accepted Michigan public-data foundation spatially usable by the frozen MODEL-11 public feature system. Exact substantive H is accepted or rejected by `GEO Decisions Acceptance`. GEO-05 cannot self-accept, create acceptance-record-only A, merge, access protected evidence, score Michigan, or begin a follow-on task.

The authorized implementation branch is `task/geo-05-michigan-statewide-geography-enablement`, based on canonical `main` commit `431e2f2a1aefcf877b7312bd4e7d16dccecb3da5`. This work order and `governance/tasks/GEO-05.michigan-statewide-geography-enablement.task.json` are the only controlling GEO-05 durable task records.

DATA-04 is accepted, merged, and closed. Its six absent B19301 source rows remain exact `source_row_missing` evidence and must not be reinterpreted, imputed, repaired, deleted, or changed. Later accepted repository authority controls over older historical prose; accepted MODEL-11 development authority remains unchanged.

## Business and geography objective

GEO-05 establishes complete Michigan statewide spatial support over all 3,017 accepted DATA-04 Census tracts. It performs the substantial public-only spatial preparation required so that a later separately authorized protected task can supply arbitrary Michigan anchor coordinates and construct the exact public spatial inputs expected by MODEL-11 without another geography research or implementation project.

Michigan state FIPS is `26`. The support inventory is statewide and is not a Detroit, Ann Arbor, Grand Rapids, Lansing, or other named-market inventory. County allow-lists and changes to accepted GEO-04 market-inventory semantics are prohibited. Existing GEO-02 Milwaukee/Madison context authority remains unchanged.

## Exact accepted source binding

The additive Michigan spatial authority must bind all of the following without repinning or substitution:

- source contract `DATA04_MICHIGAN_PUBLIC_DATA_PARITY_SOURCE_CONTRACT_V1`, version `1.0.0`, content SHA-256 `4818c91e70d64119391aecf57f7306cd5dd2b3c0e174abb9fdfec6730676155d`;
- source manifest `DATA04_TIGER2024_MI_TRACT_SOURCE_MANIFEST_V1`, version `1.0.0`, manifest content SHA-256 `de0c9dc0e654990ee03a57b697289f4c480d29b3b3c64ef3162d390adc29d731`;
- exact archive `tl_2024_26_tract.zip`, 5,575,554 bytes, SHA-256 `220c0a351d94c9de456d87c5db78f3e3864b3287370350f1e503a84565224e82`;
- exact source geometry member SHA-256 `c1cc3adf41b9e9fa565a2bc5c58fd78dcd9a7488dddbf16e044ac036586af3c1`;
- complete 3,017-record Michigan tract geometry and internal-point evidence; and
- source CRS `EPSG:4269`, 2024 TIGER tract vintage, and the accepted DATA-04 GEOID/component requirements.

A source-integrity mismatch fails closed after verification. Another release, derivative, source, state, or repinned checksum may not substitute.

## Frozen GEO-03 mathematical parity

GEO-05 must reuse `GEO03_INTERNAL_POINT_MEMBERSHIP_SPATIAL_SPEC_V1` exactly. Preserve:

- logical input axis order longitude then latitude;
- direct NAD83 geographic `EPSG:4269` to NAD83 / Conus Albers `EPSG:5070` projection;
- operation ID `GEO03_EPSG4269_TO_EPSG5070_DIRECT_NAD83_CONUS_ALBERS_V1`;
- operation fingerprint SHA-256 `3c7421053e63df6e120d8aefd142399c9c53e6a1594ed23c37c644609a21bf14`;
- EPSG:9822 Albers Equal Area conversion with standard parallels 29.5 and 45.5 degrees, latitude of false origin 23 degrees, longitude of false origin -96 degrees, and zero false easting/northing;
- no alternate datum transformation and no grid dependency;
- full unrounded Euclidean planar distance in metres;
- membership comparison `distance_m <= radius_m` with no epsilon, snapping, or membership rounding;
- tract official internal-point membership;
- containing anchor tract forced into membership when otherwise absent, with at most one tract contribution; and
- explicit noncomputability instead of silent nonmembership for invalid anchor, tract, source, projection, containment, or other required spatial evidence.

The implementation records runtime/PROJ provenance and verifies the accepted operation fingerprint. A runtime difference may not change the mathematical operation.

## Frozen MODEL downstream compatibility

MODEL owns the spatial radii and feature semantics. GEO-05 supports but does not redefine:

- 3 miles = `4828.032` metres;
- 5 miles = `8046.72` metres;
- 7 miles = `11265.408` metres;
- five-mile household opportunity;
- 3-of-7-mile inner household share;
- inner-versus-outer household-density gradient;
- five-mile multivariate feature aggregation;
- containing anchor tract; and
- deterministic tract memberships.

GEO-05 must not fit, tune, score, validate, or execute MODEL-11 and must not inspect protected coefficients, intercept, selected target-conditioned parameters, predictions, or residuals.

## Canonical statewide spatial-support inventory

Materialize and pin a deterministic Michigan statewide support inventory derived from the exact accepted DATA-04 TIGER authority. It must contain exactly 3,017 unique canonical 11-character GEOIDs, require `STATEFP == 26`, require `GEOID == STATEFP + COUNTYFP + TRACTCE`, contain no missing, extra, duplicate, or substituted tract, and be ordered lexicographically by full GEOID. The additive contract records its deterministic identity/hash and exact DATA-04 lineage.

This artifact is a statewide spatial-support inventory for downstream public feature computation. It must not be labeled or used as a named-market inventory and must not overwrite or supersede accepted Wisconsin GEO-02, GEO-03, or GEO-04 artifacts.

## State-support completeness QA

Michigan has state and international boundaries. Presence of all Michigan tracts does not imply a complete circular footprint. For a later supplied valid anchor and radius, public-only QA must expose:

- full metric circle area in `EPSG:5070`;
- area inside the union of accepted Michigan tract geometry;
- support-completeness ratio;
- whether any positive area of the footprint extends outside Michigan analytical support; and
- metric distance or signed margin to the Michigan support boundary where practical.

This is descriptive QA only. GEO-05 creates no threshold, eligibility rule, score adjustment, or automatic rejection. It does not import MODEL-05 eligibility thresholds and does not acquire other-state or Canadian demographics or manufacture absent support.

## Spatial implementation and later-anchor interface

Use the smallest configuration-driven implementation. Reuse accepted GEO-03 projection code, accepted TIGER parsing, and accepted MODEL-09/MODEL-11 anchor-tract containment where practical. Narrowly generalize Wisconsin-only constants or messages only when necessary, preserving accepted Wisconsin output and error identity where tests require it. Do not copy an entire Michigan GIS implementation or perform an unrelated architecture rewrite.

At H, a machine-consumable interface must accept only target-blind later inputs:

- latitude;
- longitude; and
- opaque anchor identity/lineage.

It must return or materialize:

- containing tract GEOID;
- projected anchor coordinate;
- deterministic 3/5/7-mile member GEOIDs and counts;
- support-completeness QA; and
- exact spatial contract, inventory, source, operation, and runtime identities.

GEO-05 creates no real or protected anchor instance and makes no decision about seed grouping, scoring, consumption, or validation.

## Real public materialization

Before H, recover accepted DATA-04 ignored-local public evidence. If absent, recreate it from accepted public authority without changing DATA-04. If the Michigan TIGER ZIP is absent, reacquire the exact accepted archive and require its accepted checksum.

Materialize real bulk spatial outputs outside tracked Git, incomplete-first with `READY.json` written last and overwrite denied. The immutable package must include, as appropriate, ordered statewide tract inventory, projected internal-point evidence, projected/state-support geometry verification evidence, operation/runtime provenance, deterministic verification report, and READY marker. Do not commit raw ZIPs, shapefile members, bulk geometries, generated operational outputs, or anchor instances.

Real execution must verify all 3,017 geometry/internal-point keys, construct and verify projected Michigan support geometry, exercise deterministic public or clearly synthetic nonprotected anchors at 3/5/7 miles including support-edge cases, rerun materialization independently, compare deterministic outputs, and run Wisconsin regression evidence.

## Protected boundary

Execution is confined to official public Census evidence, repository-safe accepted authority, and clearly synthetic/public test anchors. Do not inspect, discover, open, copy, or derive Michigan Sprouts seeds or coordinates, Michigan Isolated Sales or Impacted Sales, forecasts, candidate-site coordinates, Wisconsin protected targets, protected PIPE bindings, or MODEL-11 protected parameters or outputs. No protected filesystem discovery is authorized or required.

## Failure, retry, and determinism behavior

Fail closed on authority identity, state, source vintage/checksum/member identity, CRS, operation fingerprint, coordinate order, malformed/duplicate/inconsistent GEOID, tract count or key mismatch, invalid required internal point or geometry, invalid anchor, ambiguous/non-unique containment, projection failure, missing required membership evidence, nondeterminism, output overwrite, premature READY, tracked raw/generated data, or Wisconsin regression.

Containment may resolve deterministic boundary contact only under an explicit contract rule; otherwise ambiguous positive-area or multiple containing polygons are noncomputable. A failed non-anchor internal point must not silently become nonmembership. Reruns use a new immutable output directory and deterministic artifacts.

## Required validation and H gate

Tests and real checks cover exact DATA-04 source identities; state FIPS 26; 3,017-key uniqueness/completeness; lexicographic ordering and inventory hash; component-consistent GEOIDs; EPSG:4269 source CRS; accepted GEO-03 operation ID/fingerprint and EPSG:5070 projection; longitude/latitude axis order; valid/invalid internal points and anchors; exact and ambiguous containment; unrounded `distance_m <= radius_m`; exact MODEL-11 3/5/7 radii; forced containing-tract inclusion; nested membership; deduplication and ordering; support-completeness QA and edge cases; explicit noncomputability; rerun determinism; READY-last and overwrite denial; Michigan/Wisconsin separation; accepted Wisconsin GEO and MODEL-09/MODEL-11 public spatial regression; no market-inventory creation; no protected access; and raw/generated Git exclusion.

Run every existing repository conformance check and the full test suite. Review the complete diff and tracked-file inventory for unrelated, large, secret, protected, or Sprouts material.

At exact substantive H:

- exactly one GEO-05 manifest is `COMPLETED_AWAITING_ACCEPTANCE`;
- execution is `COMPLETED` and capability acceptance is `NOT_REVIEWED`;
- exactly one controlling GEO-05 work order exists;
- one additive proposed Michigan spatial-support authority binds the exact accepted DATA-04 source;
- the complete 3,017-tract statewide support inventory and hash are pinned;
- accepted GEO-03 projection/membership behavior is preserved;
- deterministic projected internal-point/support materialization and support-completeness QA are complete;
- the later-anchor machine interface is available;
- Wisconsin regressions and all local/required exact-H CI checks pass;
- the reviewed diff contains no protected or unrelated material; and
- zero protected or Sprouts evidence has been accessed.

Stop at H and route it to `GEO Decisions Acceptance`. Any substantive post-H change creates revised H requiring new GEO acceptance. Do not create A, merge, or begin Michigan seed intake, MODEL-11 scoring, Power BI, Site Scanner, or another follow-on task.

## Completed real public-source spatial verification

The exact accepted DATA-04 READY package was recovered without reopening DATA-04. Its current accepted contract, Michigan TIGER manifest, 3,017-key inventory, source archive, geometry members, and READY/report hashes all matched accepted authority. No source was reacquired or repinned.

Two independent GEO-05 packages each materialized exactly 3,017 lexicographically ordered unique Michigan tract GEOIDs; 3,017 component-consistent source records; 3,017 valid keyed geometries; 3,017 valid official internal points; and 3,017 projected internal points. Every source internal point was covered by its keyed source geometry, every projected internal point was covered by its keyed projected geometry and the projected statewide union, and no tract was missing, extra, duplicate, or substituted. The controlling ordered inventory SHA-256 is `8b6698b55423911163f1a2330ad600218a3b8b452576cc9b3d3997ada19e6c9b`.

The accepted GEO-03 operation ID and fingerprint reproduced under pyproj `3.7.2` / PROJ `9.5.1`, with Shapely `2.1.2` recorded as geometry-engine provenance. Direct longitude/latitude NAD83 `EPSG:4269` to Conus Albers `EPSG:5070` behavior, no-grid/no-datum-shift semantics, unrounded Euclidean distance, `distance_m <= radius_m`, nested deterministic membership, and forced-containing-tract behavior were preserved.

The projected union of all accepted Michigan tract geometries is a valid polygon with area `250485944037.48492` square metres. A deterministic public TIGER edge internal point exercised truncation at every MODEL-owned radius, with completeness ratios approximately `0.56954`, `0.56791`, and `0.57302`; a deterministic public interior point remained effectively complete. The interface reports full footprint area, retained area, outside area, completeness, boundary distance, and margin, but creates no threshold, automatic rejection, score adjustment, or extra-state support.

The two independent runs were byte-identical across all seven files, including READY. Verification report SHA-256 is `0ff58b37df00cd7f72fff099643b7d42bf0af911ef6502ef569140951130baea`; READY SHA-256 is `5e5902e5efed9a040583aecb705621db9f2052e6d30d44b4e6b75868b34bbc9c`.

The machine interface accepts latitude, longitude, opaque anchor identity, and opaque anchor lineage and returns containing tract, projected coordinate, member GEOIDs/counts, support-completeness QA, and exact spatial lineage. GEO-05 created no protected anchor instance, performed no protected filesystem discovery, accessed zero protected or Sprouts evidence, and did not execute or inspect MODEL-11 fitted state.

All repository conformance checkers, the complete unit-test suite, the real Michigan package verification, deterministic rerun comparison, and accepted Wisconsin spatial regressions were run against the completed implementation. Exact test and CI evidence is attached to substantive H and its pull request; any substantive correction after H requires a revised H and fresh GEO acceptance.
