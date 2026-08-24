# GEO-05 Michigan statewide geography enablement

GEO-05 adds a repository-safe, public-only Michigan statewide spatial-support proposal over every tract in the accepted DATA-04 foundation. It binds exact Michigan source identity to the accepted GEO-03 projection, internal-point distance, membership, and forced-containing-tract method without modifying Wisconsin GEO authority or executing MODEL-11.

The machine-readable authority is `GEO05_MICHIGAN_STATEWIDE_SPATIAL_SUPPORT_SPEC_V1` in `config/geo/geo05_michigan_statewide_spatial_support_spec.json`. The controlling work order is [GEO-05: Michigan Statewide Geography Enablement](work_orders/GEO_05_MICHIGAN_STATEWIDE_GEOGRAPHY_ENABLEMENT.md).

## Exact public spatial boundary

- State: Michigan, FIPS `26`
- Geography: complete statewide 2024 Census tract support
- Tracts: exactly 3,017 unique component-consistent 11-character GEOIDs
- Ordered inventory SHA-256: `8b6698b55423911163f1a2330ad600218a3b8b452576cc9b3d3997ada19e6c9b`
- DATA-04 contract SHA-256: `4818c91e70d64119391aecf57f7306cd5dd2b3c0e174abb9fdfec6730676155d`
- Michigan TIGER archive SHA-256: `220c0a351d94c9de456d87c5db78f3e3864b3287370350f1e503a84565224e82`
- Source geometry member SHA-256: `c1cc3adf41b9e9fa565a2bc5c58fd78dcd9a7488dddbf16e044ac036586af3c1`
- Source CRS: `EPSG:4269`
- Target CRS: `EPSG:5070`
- Operation: `GEO03_EPSG4269_TO_EPSG5070_DIRECT_NAD83_CONUS_ALBERS_V1`
- Operation fingerprint: `3c7421053e63df6e120d8aefd142399c9c53e6a1594ed23c37c644609a21bf14`

This is a statewide spatial-support inventory, not a Detroit, Ann Arbor, Grand Rapids, Lansing, or other market inventory. It has no county allow-list and does not reinterpret accepted GEO-04 market semantics.

## Materialization

Use one current accepted DATA-04 READY directory and the exact accepted Michigan TIGER archive:

```powershell
python -m sprouts_customer_geography.geo05 verify-contract

python -m sprouts_customer_geography.geo05 verify-data04-ready `
  --data04-ready-dir outputs/data04-run-5

python -m sprouts_customer_geography.geo05 materialize `
  --tiger-source data/raw/data04/tl_2024_26_tract.zip `
  --data04-ready-dir outputs/data04-run-5 `
  --output-dir outputs/geo05-run-1
```

The immutable package is created incomplete-first, denies an existing output directory, and writes `READY.json` last. It contains:

- `michigan_statewide_spatial_support_inventory.json`, the complete ordered statewide inventory;
- `michigan_projected_internal_points.csv`, with lossless hexadecimal float encodings for source and projected coordinates;
- `michigan_tract_source_geometries.jsonl`, the keyed official source geometries needed for later containment;
- `michigan_state_support_epsg5070.wkb`, the projected union used for support-completeness QA;
- `operation_runtime_provenance.json`;
- `verification_report.json`; and
- `READY.json`.

All files remain under ignored `outputs/` or another untracked output root. Raw TIGER bytes, shapefile members, tract-level geometry, operational anchor evidence, and generated packages are not committed.

## Later-anchor interface

The repository-safe interface accepts a verified public package plus only these anchor-instance inputs:

- latitude;
- longitude;
- opaque anchor identity; and
- opaque anchor lineage.

It returns exact target-blind public evidence under `GEO05_ANCHOR_SPATIAL_EVIDENCE_V1`: the containing tract, projected anchor, deterministic member GEOIDs and counts, forced-containing-tract state, support-completeness QA, and exact spatial lineage. The default radii are the MODEL-owned `4828.032`, `8046.72`, and `11265.408` metres. A later authorized caller may supply another positive radius while retaining the same unrounded `distance_m <= radius_m` method.

```powershell
python -m sprouts_customer_geography.geo05 evaluate-anchor `
  --materialization-dir outputs/geo05-run-1 `
  --latitude <later-authorized-latitude> `
  --longitude <later-authorized-longitude> `
  --anchor-identity <opaque-id> `
  --anchor-lineage <opaque-lineage> `
  --output outputs/later-authorized-anchor-spatial-evidence.json
```

The example contains placeholders only. GEO-05 created no anchor instance. A later protected caller must keep its input and output instance outside tracked Git.

Invalid coordinates, a missing or ambiguous containing tract, a noncomputable internal point, an operation/runtime mismatch, or any incomplete required tract distance fails closed with a machine-readable `NONCOMPUTABLE` error and no partial membership. Membership uses lossless projected coordinates, full unrounded Euclidean distance, no epsilon or snapping, one contribution per tract, and lexicographically ordered deduplicated results. The containing tract is forced when it is not an ordinary radius member.

## Support-completeness QA

For every radius, the interface constructs the accepted 64-segment-per-quadrant metric buffer in `EPSG:5070` and reports:

- full footprint area;
- area inside the union of all accepted Michigan tract geometry;
- completeness ratio;
- positive-area extension outside Michigan analytical support;
- outside-support area;
- anchor-to-support-boundary distance; and
- footprint-edge margin.

This is descriptive QA only. It has no threshold, does not reject an anchor, does not alter a score, and does not import MODEL-05 eligibility rules. GEO-05 did not obtain other-state or Canadian demographics or manufacture support outside Michigan.

## Verified real public execution

The accepted DATA-04 READY package was recovered with exact report SHA-256 `ed746f3e7f23409f7d4f1dec85ccf4ec2d54ed05391cc2c0b61ed37004bd9c4e` and READY SHA-256 `1b80d3e64ca58b8b70cdd05a6a3c46242a9fc0ac6e8bee896ba1430d509109e0`. The exact Michigan TIGER archive and all four pinned source members matched accepted checksums.

Both independent GEO-05 runs verified:

- 3,017 source rows, geometries, unique canonical GEOIDs, valid official internal points, and projected internal points;
- exact lexicographic inventory identity `8b6698b55423911163f1a2330ad600218a3b8b452576cc9b3d3997ada19e6c9b`;
- every official internal point covered by its correctly keyed source geometry;
- every projected internal point covered by its correctly keyed projected geometry and the statewide support union;
- direct `EPSG:4269` to `EPSG:5070` operation fingerprint parity;
- a valid projected statewide support polygon of `250485944037.48492` square metres; and
- zero missing, extra, duplicate, or substituted tracts.

Runtime provenance was pyproj `3.7.2`, PROJ `9.5.1`, and Shapely `2.1.2`. The mathematical authority remains the accepted GEO-03 operation fingerprint, not those incidental version numbers.

The deterministic public edge case selected official internal point tract `26163580100`, 357.18 metres from the projected support boundary. Its 3/5/7-mile completeness ratios were approximately `0.56954`, `0.56791`, and `0.57302`, and each footprint extended outside Michigan support. The deterministic interior case selected tract `26073940200`, 192,916.96 metres from the support boundary, and remained effectively complete at all three radii. These cases confirm boundary QA without creating an eligibility decision.

The two independent READY packages were byte-identical across all seven files. Principal SHA-256 results were:

- projected internal points: `f75484682f757b7d77ca6fd35b022f250cb31f39161209fd0515b84039da7987`;
- projected statewide support WKB: `4080e21a6c208467c7db6258a1b2e3ddd15a3994ee89848fcee40a3b1752ff3e`;
- materialized statewide inventory: `a3a771832020ec08c8cd8ce61ce28a4d6d8411d9efe3118209777dd222585996`;
- keyed source geometry JSONL: `8a00ba5dbf449ae343461e900c80849325d9c497e09e3b99d5c7e0c3670ed7a5`;
- runtime provenance: `e8c76bf0a5f77ce0a9a260c211f9a2e4438ae0420715c21a3592e273dfeb4a09`;
- verification report: `0ff58b37df00cd7f72fff099643b7d42bf0af911ef6502ef569140951130baea`; and
- READY: `5e5902e5efed9a040583aecb705621db9f2052e6d30d44b4e6b75868b34bbc9c`.

Execution used only official public Census evidence and public TIGER internal points. It performed no protected filesystem discovery, accessed zero protected or Sprouts evidence, created no protected anchor instance, and did not fit, tune, score, or execute MODEL-11.

Repository validation covers the complete unit-test suite, every repository conformance checker, immutable READY-last and overwrite behavior, independent byte-for-byte rerun comparison, real-package reload, later-anchor interface failure semantics, and accepted Wisconsin GEO/MODEL spatial regressions. The exact substantive commit and CI results are recorded on the GEO-05 pull request; this proposed capability remains awaiting GEO Decisions Acceptance.
