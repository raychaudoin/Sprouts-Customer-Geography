# ARCH-01 local-first presentation architecture decision

Status: **selected architecture awaiting exact-H capability acceptance**

Task: `ARCH-01` · Lane B

Canonical base: `499cd611605380a3f2abca1e3e1d2f27cc56301c`

Decision owner: `ARCH: Presentation Architecture Decisions & Acceptance`

## Decision

Select a static browser application served by a minimal Python standard-library HTTP server bound to `127.0.0.1`, with:

- plain JavaScript ES modules and semantic HTML/CSS;
- MapLibre GL JS `6.6.0`, pinned and vendored in the repository, for WebGL2 map rendering and interaction;
- a prepared JSON presentation bundle keyed by tract GEOID plus the already accepted public PBI-01 GeoJSON as separate runtime inputs;
- no framework, compile step, package manager, database, browser query engine, account, hosted backend, telemetry, analytics, crash reporting, or remote logging;
- USGS Topo raster tiles as the default recognizable road/place-label context, USGS ImageryTopo as optional aerial-plus-label context, and a network-free local-neutral fallback; and
- a local browser join that places presentation values on public tract features only after exact 3,017-key reconciliation.

This is the smallest supportable architecture for the measured workload. It keeps analytical and spatial preparation upstream, makes the presentation surface source-controlled and reconstructable, and avoids reintroducing a heavyweight authoring/import runtime around a 3,017-row, 16-metric display problem.

ARCH-01's source-controlled spike is architecture evidence, not a production dashboard. Production protected-input preparation, operator support, and deployment are outside this decision.

## Runtime topology and authority boundary

```text
accepted prepared outputs (future local adapter)       accepted public geometry
MODEL-13 + DATA-04 presentation fields                 PBI-01 GeoJSON, 3,017 GEOIDs
                  |                                                |
                  +-------- exact-key validation / bundle ---------+
                                           |
                               loopback allowlist server
                               127.0.0.1:8766, read-only
                                           |
                                  local browser runtime
                         JSON join -> WebGL styling -> inspector
                                           |
                         optional public raster tile GET requests
                             basemap.nationalmap.gov only
```

Presentation never becomes the owner of source extraction, geography construction, feature engineering, model fitting, scoring, support calculations, or evidence lineage. The spike's synthetic builder exercises only the presentation contract. It does not reproduce accepted MODEL-13 or DATA-04 values.

The canonical public geometry is verified after normalizing the platform checkout's terminal CRLF to the Git-blob LF form. The resulting bytes match the accepted SHA-256 `e0f32095d2e2307f5ad78c9545fc0d3c74fca2250bc866bea8db2368848786ad`. The accepted file and predecessor record are not modified.

## Input form and loading decision

The runtime loads four explicit local resources: the metric catalog, runtime policy, prepared presentation bundle, and public GeoJSON. The bundle is a row-major 3,017-by-16 JSON structure with values, availability statuses, status details, margins of error, support-truncation flags, stable domains, source bindings, and a synthetic nontransmission canary.

Direct prepared-file loading is selected because the synthetic bundle is 1,474,751 bytes and contains only 48,272 value positions. There is no measured query-planning, aggregation, concurrency, or update workload that justifies a database. DuckDB-Wasm is capable but its official documentation notes browser/Wasm memory limits and a default single-threaded deployment; that complexity provides no current benefit for this fixed presentation slice ([DuckDB-Wasm overview](https://duckdb.org/docs/stable/clients/wasm/overview)). SQLite's official Wasm distribution is similarly unnecessary for the current read-once keyed bundle ([SQLite Wasm overview](https://www.sqlite.org/wasm/doc/trunk/about.md)).

If a later accepted presentation workload requires many markets, large longitudinal history, ad hoc local queries, or incremental updates, the prepared-bundle adapter is the replacement boundary. That later task may evaluate Parquet/DuckDB or SQLite with measured evidence; this decision does not pre-authorize it.

## Mapping and application technology evaluation

| Choice | Disposition | Material reason |
|---|---|---|
| File-opened static HTML | Rejected | `file:` origins make multi-file fetch, workers, CSP, and fail-closed input routing inconsistent across browsers. They also cannot provide a narrow served-file allowlist. |
| Minimal loopback server | Selected | Uses the existing Python runtime, binds only to loopback, rebuilds in memory at each start, and exposes an explicit read-only route allowlist with security headers. |
| MapLibre GL JS 6.6.0 | Selected | WebGL2 rendering, data-driven style expressions, raster composition, and map interaction fit 3,017 polygons and rapid metric switching. The exact current release and BSD-3-Clause license are recorded by the project's official [release](https://github.com/MapLibre/maplibre-gl-js/releases/tag/v6.6.0), [documentation](https://maplibre.org/maplibre-gl-js/docs/), and [license](https://github.com/maplibre/maplibre-gl-js/blob/main/LICENSE.txt). |
| Leaflet 1.9.4 | Rejected for this slice | Leaflet remains a sound lightweight alternative and supports GeoJSON plus Canvas, but its default SVG/Canvas layer model would require CPU-side style updates across tract paths. Its official site identifies 1.9.4 as the stable release ([Leaflet download](https://leafletjs.com/download.html), [Canvas/GeoJSON reference](https://leafletjs.com/reference.html#canvas)). MapLibre's expression-driven WebGL path is a closer fit to the measured layer-switch workload. |
| Plain JavaScript ES modules | Selected | The bounded UI has no build-time transformation, shared component library, or type-generation requirement. Avoiding a Node/framework toolchain reduces installation, lockfile, security-update, and reconstruction surface. |
| TypeScript plus UI framework | Rejected for this slice | A compiler and framework would add more runtime-independent machinery than the current application logic. The map adapter and data schemas preserve a later replacement boundary if scale changes. |
| Prepared JSON + GeoJSON | Selected | The measured bundle is small, fixed, read-once, and keyed for an exact client join. It is directly reviewable and reconstructable. |
| SQLite or DuckDB-Wasm | Rejected for this slice | No measured query workload needs them; they add binary/Wasm artifacts, memory, licenses/notices, and operational update surface. |

## Map semantics preserved

The metric catalog contains exactly the 16 authorized layers in the controlling work order and preserves their order, definition, unit, source, availability, warning, format, and input-binding metadata.

- Customer Fit Percentile and Modeled Target Mass Percentile use fixed 0–100 domains.
- The other 14 metrics use Type-7 statewide valid-value P02–P98 domains computed once for the loaded bundle.
- Exact out-of-domain values are retained and saturate the endpoint colors; legend endpoints use `≤` and `≥`.
- Missing, invalid, inapplicable, and noncomputable values stay null, are excluded from the domain, and render as neutral `No Data / Unavailable`; they never become zero.
- Descriptive metrics use a non-evaluative sequential palette.
- The inspector exposes value/status context, synthetic margins of error where applicable, support-truncation context, and an explicit synthetic-evidence warning.
- Empty, single, and multiple selection states are first-class. Multiple selection works through Shift/Ctrl/Command or the explicit Add-to-selection control.

Average Household Income is not a metric. Median Household Income explicitly distinguishes itself from Average Household Income and Area Median Income. Area Median Income remains outside current authority.

## Basemap, imagery, legal, privacy, cost, and failure posture

### Selected services

The default is the USGS Topo ArcGIS raster tile service. USGS describes it as a cached topographic basemap with boundaries, geographic names, transportation, hydrography, and land-cover context ([USGS Topo service metadata](https://basemap.nationalmap.gov/arcgis/rest/services/USGSTopo/MapServer?f=pjson)). The optional aerial layer is USGS ImageryTopo, which combines orthoimagery with US Topo reference information ([USGS ImageryTopo service metadata](https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryTopo/MapServer?f=pjson)).

USGS states that National Map services and data are free, public domain, and available without use restrictions, while requesting acknowledgment ([USGS licensing terms](https://www.usgs.gov/faqs/what-are-terms-uselicensing-map-services-and-data-national-map)). Neither selected endpoint requires an API key or recurring fee. No service-level agreement was found in the reviewed official material, so availability is treated as best-effort and never required for tract interaction.

Attribution is shown in the map. The tracked runtime policy holds the exact service templates, metadata, terms, privacy, attribution, maximum zoom, cost, key, and SLA posture.

### Exact egress and privacy

Automatic external egress is restricted to HTTPS `GET` tile requests to `basemap.nationalmap.gov`. The URL contains only the public service path and viewport-derived zoom/row/column tile identifiers. Ordinary connection/request metadata necessarily accompanies HTTPS traffic.

USGS states that its sites automatically log items including domain, IP address, browser/operating system, request time, referrer, approximate country/state, pages visited, and requested information for site management and security ([USGS privacy policies](https://www.usgs.gov/office-of-the-director/privacy-policies)). Therefore even a public basemap request reveals network metadata and a coarse public viewport. The application does not add local GEOIDs, values, selection state, canary, coordinates from protected overlays, lineage, file paths, user identity, headers, query parameters, body, analytics, or diagnostic payloads.

The browser's request transform rejects every unreviewed external host and checks the synthetic canary before permitting a tile URL. The server CSP independently limits image and connection origins to self and USGS. Selecting Local neutral removes the raster source and generates no new external requests.

### Alternatives and failure behavior

- OpenStreetMap's standard tile policy explicitly says the data are free but the community tile servers are capacity-limited, best-effort, and prohibit bulk/offline use; it is not selected as an application default ([OSM tile usage policy](https://operations.osmfoundation.org/policies/tiles/)).
- OpenFreeMap advertises no keys, fees, or request limits, but its own terms disclaim guaranteed availability and its privacy material describes operational logging. It is not selected while an official U.S. public-domain source satisfies the pilot ([OpenFreeMap terms](https://openfreemap.org/tos/), [privacy](https://openfreemap.org/privacy/)).
- A local vector/raster package would eliminate external egress but introduces a materially larger artifact, separate source/license/provenance/refresh process, and distribution burden. PMTiles provides an open single-file archive and remains a plausible later adapter if fully offline recognizable context becomes accepted scope ([PMTiles project](https://github.com/protomaps/PMTiles/blob/main/README.md)). It is not required to validate the current local-first presentation runtime.

If USGS tiles fail, tract polygons, metric switching, selection, inspector, QA, and legend remain local. The app shows a basemap-unavailable notice and the operator can select Local neutral. No retry sends presentation values or widens the host allowlist.

## Dependency, source-control, and maintenance posture

| Dependency | Purpose | Version/policy | License/cost | Telemetry/security posture | Replacement boundary |
|---|---|---|---|---|---|
| Python | Loopback allowlist server and deterministic bundle construction | 3.11+ standard library; tested with 3.13.12 | Existing runtime; no new package or recurring cost | No request logging; no outbound calls | `scripts/arch01/serve_spike.py` |
| MapLibre GL JS | WebGL2 map, raster composition, data-driven polygon styling, interaction | Exact vendored 6.6.0 with five recorded SHA-256 hashes | BSD-3-Clause and bundled notices; no recurring cost | Library telemetry disabled/absent; no CDN runtime; CSP and request transform constrain network | Map initialization, sources, layers, paint, and interactions in `presentation/arch01/site/app.mjs` |
| USGS Topo / ImageryTopo | Recognizable roads/place labels and optional aerial context | External public service; metadata reviewed 2026-08-26 | U.S. public domain; no key or recurring fee; attribution shown | Best-effort; reviewed network metadata only | Runtime basemap configuration and `addBasemap` adapter |

The app, policy, schemas, tests, deterministic builder, server, license, and exact MapLibre distribution files are tracked. There is no generated bundle, database, imported-data cache, service credential, or build output to recover. Dependency updates must be deliberate: select a version, review official release/license/security posture, vendor the complete ESM distribution, update hashes, and rerun conformance plus live interaction tests.

## Performance and recovery conclusion

The full measurements and limitations are in [ARCH-01 spike evidence](../arch01/ARCH_01_SPIKE_EVIDENCE.md). On the observed Windows host, all 3,017 polygons and 16 metrics became interactive in 391–978 ms across the successful first-load/reload observations. Sixteen metric switches measured 1.2–7.8 ms, and tested selection updates measured 1.7–3.9 ms. The Python server held 31.38 MiB working set / 21.53 MiB private memory and showed no measurable CPU increase during a local-neutral pan/zoom interaction. Browser-process memory and CPU were not unambiguously observable in the shared in-app Chromium pool and are deliberately reported as unavailable.

Three clean browser reloads and three clean server restart cycles each reconciled 3,017 tracts and 16 metrics with zero canary hits and no repair. There is no hidden imported-data state: stopping and rerunning `RunArch01Spike.bat` reconstructs the in-memory bundle from tracked inputs.

The separately supplied PBI-02 evidence established a Power BI Desktop paging-file/resource failure before its save/reopen gate. That observation motivated a smaller host but is not a direct benchmark: PBI-02 was not rerun, and this decision does not manufacture comparative memory or speed values.

## Protected-data boundary

The tracked spike contains only public geometry, public source descriptions, configuration, deterministic synthetic values generated in memory, and a conspicuous synthetic canary. It does not read or commit real MODEL-13 rows, Seed Context, target locations, candidate locations, sales, protected identity, credentials, or screenshots.

For a later authorized implementation, the local input adapter may read an accepted prepared presentation subset from protected local storage. It must validate READY/hash/schema/key accounting before row use, retain status/MOE/lineage semantics, and expose only the selected prepared fields to the loopback process. Values remain within the local server/browser. They must never enter tile URLs, geocoding, routing, traffic, analytics, crash reporting, remote logs, public Git, GitHub, or screenshots.

## PBI-02 semantic migration and branch boundary

PBI-02 was inspected only as non-authoritative implementation evidence. ARCH-01 carries forward the intended map-first product semantics—Michigan map dominance, exact 16-metric inventory, dynamic context, tract selection, QA, warnings, and robust-domain behavior—through newly written configuration and spike code grounded in the accepted predecessor contracts.

No PBI-02 commit is an ARCH-01 base, merge parent, or cherry-pick. At investigation time its draft PR #35 remained open/unmerged and its branch head `b60d0e4f27026967bd1d3a50e81f91fda141b677` remained non-H. ARCH-01 does not close, rewrite, accept, or otherwise transition PBI-02.

## Reconstruction and verification

From a clean checkout with Python 3.11+:

```powershell
python scripts\arch01\build_synthetic_bundle.py --summary
python scripts\arch01\serve_spike.py --check
python scripts\check_arch01_repository.py
python -m unittest tests.arch01.test_arch01_conformance -v
.\RunArch01Spike.bat
```

Open `http://127.0.0.1:8766/`. No package installation, database initialization, login, credential, build, cache restore, or cloud service is required.

## Residual risk and exact follow-on boundary

Residual risks are bounded but real: USGS service availability and terms can change; WebGL/graphics drivers vary; larger multi-market or historical workloads may outgrow direct GeoJSON/JSON; protected-input preparation is not implemented; and an operator support lifecycle has not been designed. Exact dependency hashes improve reproducibility but require deliberate maintenance.

If exact H is accepted, a separately authorized production-implementation task may build the protected local input adapter, operator packaging/support, broader accessibility and browser coverage, offline-basemap decision if required, and production UX. That task must recover this accepted decision and the predecessor authorities, establish its own manifest/work order/branch/acceptance gate, and preserve the same public/protected and egress invariants.

ARCH-01 does not authorize that follow-on, deployment, hosting, publication, acceptance-record commit A, merge, or any PBI-02 transition. Exact H stops for `ARCH: Presentation Architecture Decisions & Acceptance`.
