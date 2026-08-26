# ARCH-01 disclosure-safe spike evidence

Evidence date: 2026-08-26

Task posture: architecture evidence awaiting exact-H acceptance

Data classification: accepted public geometry plus deterministic synthetic presentation values only

## What was measured

The spike exercised the selected local-first topology on the user's Windows host with Python 3.13.12 and the Codex in-app Chromium browser at a 1,280 × 720 CSS-pixel viewport with device-pixel ratio 1.5. A WebGL map canvas rendered successfully. Browser JavaScript heap metrics were not exposed by this browser surface, and the shared Chromium process pool did not provide an unambiguous per-tab process, so browser memory and CPU are reported as unavailable rather than estimated.

The workload was the accepted public Michigan 2024 tract presentation geometry and the deterministic synthetic bundle:

| Artifact | Observed size | Integrity |
|---|---:|---|
| Canonical accepted GeoJSON bytes served | 1,264,358 bytes | SHA-256 `e0f32095d2e2307f5ad78c9545fc0d3c74fca2250bc866bea8db2368848786ad` |
| Synthetic 3,017 × 16 bundle | 1,474,751 bytes | SHA-256 `1e1d55cc930e9c31561e3c1594d277286d116ba5b6c775d25cd1b3d01973cb84` |
| MapLibre ESM main/shared/worker | 1,076,302 bytes total | Exact file hashes in the runtime policy |
| MapLibre CSS | 83,195 bytes | Exact file hash in the runtime policy |
| ARCH-01 HTML/CSS/JavaScript | 29,784 bytes at measurement | Tracked source; no build output |

The Windows working-tree GeoJSON has one terminal CRLF because Git text checkout normalization makes it one byte larger. The server normalizes CRLF to LF, verifies the accepted Git-blob hash above, and serves only those canonical bytes. The accepted predecessor file is unchanged.

## Functional result

| Gate | Result |
|---|---|
| Geometry and prepared rows | Exactly 3,017 features, 3,017 rows, and 3,017 unique reconciled GEOIDs |
| Metric inventory | Exactly 16 entries in the authorized order |
| Fixed domains | The two modeled percentile layers use 0–100 |
| Robust domains | The other 14 layers use valid-only statewide Type-7 P02–P98 |
| Saturation and missingness | Endpoint saturation uses `≤` / `≥`; unavailable values are null and render neutral, never zero |
| Dynamic context | Name, unit, definition, source, domain, legend, inspector, status, MOE, support warning, and synthetic warning update with the active metric/tract |
| Map interaction | WebGL render, pan, zoom, metric switching, single selection, additive multiple selection, and clear-to-empty state succeeded |
| Context layers | USGS Topo default, USGS ImageryTopo optional, and Local neutral fallback succeeded |
| Local-only server | `127.0.0.1` binding, host validation, route allowlist, read-only methods, no query strings, CSP, no request log |
| Telemetry | No application telemetry, analytics, crash reporting, or remote logging |

The zoom test moved from `5.790` to `6.790`. The pan test changed the map center from `-85.75000,44.35000` to `-85.17818,44.14519` while the local-neutral basemap remained ready.

## Timing and resource observations

These are disclosure-safe observations from one development host, not contractual cross-machine benchmarks.

| Observation | Result |
|---|---:|
| First successful full map readiness, including public basemap | 978 ms |
| Later instrumented full readiness | 401.7 ms |
| Three retained-browser reloads | 397.8 ms, 391.0 ms, 396.5 ms |
| Sixteen metric switches | 1.2–7.8 ms; median 2.6 ms; observed p95/max 7.8 ms |
| Tested selection updates | 1.7–3.9 ms |
| Python server working set | 31.38 MiB |
| Python server private memory | 21.53 MiB |
| Python server CPU during one local-neutral zoom/pan interval | 0.000000 CPU-second increase at the process-counter resolution |
| Browser memory and CPU | Not unambiguously observable; JavaScript heap API unavailable and browser process pool shared |

Metric-switch samples in catalog order were `1.2, 3.0, 6.1, 2.4, 7.1, 1.8, 2.3, 2.0, 1.8, 2.6, 5.0, 3.0, 7.8, 2.1, 4.9, 1.3` milliseconds. Every sample retained 3,017 tracts, 16 metrics, and zero canary hits.

## Network and protected-shaped canary evidence

The browser request transform observed 25 viewport tile requests for USGS Topo and 25 additional requests after selecting USGS ImageryTopo. Every permitted external request used HTTPS `GET`, had no body or application-added headers, and targeted only `basemap.nationalmap.gov`. Switching from an online layer to Local neutral caused zero additional external requests.

The bundle carried the distinctive synthetic canary in local memory. Canary-hit diagnostics remained `0` through initial load, all 16 metric switches, single/multiple/empty selection states, pan, zoom, online basemap switching, local-neutral switching, and three browser reload cycles. The canary literal is not hardcoded into client source, UI, URLs, or evidence output.

This demonstrates the selected transport boundary for the synthetic test shape. It does not claim that a future protected adapter is safe without its own exact input, process, browser, and network tests.

## Stability, recovery, and failure behavior

- Fourteen focused ARCH-01 conformance tests passed, including schema-boundary checks and three clean server start/health/stop cycles.
- Governance validation and the standalone ARCH-01 repository checker passed with predecessor immutability and protected tracked-path guards enabled.
- The escalated Windows repository suite discovered 343 tests: 339 passed, three source-artifact tests skipped as designed, and one accepted PBI-01 byte-hash assertion failed solely because the Windows working-tree checkout adds one terminal CRLF. The unchanged Git blob and the canonical bytes served by ARCH-01 both match the accepted LF hash. Required exact-H Linux CI remains the authoritative full-suite gate.
- Three measured browser reloads each returned `ready`, 3,017 features, 16 metrics, no visible error, and zero canary hits.
- Each server start deterministically rebuilt the same 1,474,751-byte bundle with the same SHA-256; no cache, database, imported model, or repair step existed.
- A live first-run check exposed a missing MapLibre ESM shared module in the initial vendor inventory. The page remained in its loading/fail-closed state. The exact 6.6.0 shared module was then vendored, hashed, allowlisted, and added to conformance. This is evidence that missing runtime dependencies do not silently degrade the data contract.
- Local neutral was exercised after raster removal and preserved all polygon interaction with no new external requests.
- The app's map-error path preserves tract layers and displays an explicit external-basemap-unavailable notice; an unreviewed host is blocked before request issuance.

## Power BI evidence boundary

The controlling work order records the separate PBI-02 Power BI Desktop paging-file/resource exhaustion before its save/reopen gate. Power BI Desktop was not rerun during ARCH-01, so there is no direct same-session speed, memory, or CPU comparison. The only supported conclusion is that this smaller local browser workload completed and restarted cleanly on the same user environment while using a narrowly scoped runtime; no numeric Power BI benchmark is asserted.

## Disclosure and predecessor check

No real MODEL-13 row, Seed Context, target/candidate coordinate, sales value, credential, protected identity, screenshot, browser log, or local absolute user path is in this evidence. The accepted MODEL-13, DATA-04, GEO-05, and PBI-01 manifests, work orders, configs, and PBI-01 tree have no diff from canonical base `499cd611605380a3f2abca1e3e1d2f27cc56301c`.

PBI-02 draft PR #35 remained open, unmerged, unaccepted, and non-H at final pre-H verification. Its branch had independently advanced to observed head `b7edf51093bfd210f2856771095dd8005557f577`. ARCH-01 contains no PBI-02 merge or cherry-pick.
