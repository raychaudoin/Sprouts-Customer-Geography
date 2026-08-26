# ARCH-01: Local-First Customer Geography Presentation Architecture

## Authority and stopping boundary

Master Control Room authorized this Lane B architecture-selection task from canonical `main` commit `499cd611605380a3f2abca1e3e1d2f27cc56301c`. Exact substantive H is accepted or rejected by `ARCH: Presentation Architecture Decisions & Acceptance`.

ARCH-01 may select a local presentation architecture, add only the minimum public/synthetic spike needed to validate that selection, create and maintain its single Issue, branch, manifest, work order, pull request, commits, and CI, and stop at exact H. It must not self-accept, create acceptance-record-only A, merge, deploy, publish a production application, or begin the follow-on production implementation.

PBI-02 remains a draft, unaccepted, non-H branch and PR. ARCH-01 may inspect it as non-authoritative implementation evidence but may not base on it, merge it, cherry-pick it, rewrite it, or treat its code as accepted authority.

## Business problem and failure family

The accepted analytics and prepared-output contracts need a durable operator surface. The PBI-02 attempt established the intended map-first product semantics and completed a real local refresh, but the Power BI Desktop workflow exhausted Windows paging-file and system resources before the required save/reopen gate. The failure family is an operator runtime whose heavyweight authoring host, imported-data refresh lifecycle, and recovery behavior are materially more fragile than the presentation workload requires.

The shared invariant is that presentation consumes prepared, authoritative outputs. It does not own complex GIS, feature construction, model fitting, scoring, support computation, source derivation, target logic, protected identity, or protected evidence lineage. ARCH-01 selects a smaller runtime around that invariant and does not use the Power BI failure as authority to change accepted analytical meaning.

## Accepted authority and input boundary

The task preserves without modification:

- `MODEL13_MICHIGAN_POWER_BI_OUTPUT_CONTRACT_V1`, including tract scores, Seed Context, metadata, READY, hashes, lineage, and the exact 3,017 / 2,973 / 44 / 438 accounting;
- `DATA04_MICHIGAN_PUBLIC_DATA_PARITY_SOURCE_CONTRACT_V1`, including the accepted Michigan 13-measure materialization, statuses, margins of error, status details, and complete 3,017-key reconciliation;
- `GEO05_MICHIGAN_STATEWIDE_SPATIAL_SUPPORT_SPEC_V1` and accepted 2024 Michigan TIGER geography; and
- `PBI01_MICHIGAN_2024_TIGER_TRACT_PRESENTATION_GEOMETRY_V1`, the public simplified GeoJSON with exactly 3,017 unique GEOIDs.

Runtime-form evaluation may consider CSV, JSON, GeoJSON, Parquet, SQLite, DuckDB, browser-local query engines, and prebuilt bundles. A database or query engine is selected only if measured workload and reconstruction evidence require it.

## Product semantics to preserve

The selected architecture must support a map-dominant Michigan scouting surface with recognizable roads and place labels, optional aerial context when a legally and operationally acceptable no-recurring-cost source exists, all 3,017 tract polygons, non-fuzzy choropleth coloring, tract pan/zoom and selection, empty/single/multiple-selection states, a selected-tract inspector, contextual warnings, technical QA, and dynamic legend/unit/definition/source metadata.

The metric catalog contains exactly these 16 layers in order:

1. Customer Fit Percentile
2. 5-Mile Household Opportunity
3. Modeled Target Mass Percentile
4. Median Household Income
5. Per Capita Income
6. Civilian Labor Force Share
7. Employment Rate
8. Bachelor's Degree or Higher Share
9. Owner-Occupied Housing Share
10. Vacant Housing Unit Share
11. Median Home Value
12. Median Gross Rent
13. Average Household Size
14. No-Vehicle Household Share
15. Drive-Alone Commuter Share
16. Work-from-Home Commuter Share

Customer Fit Percentile and Modeled Target Mass Percentile use fixed 0–100 domains. Every other numeric metric uses a statewide valid-value P02–P98 domain fixed for the loaded dataset. Exact values remain unchanged; out-of-domain values saturate endpoint colors; legends use explicit `≤` and `≥` endpoints; missing, invalid, inapplicable, and noncomputable values remain neutral `No Data / Unavailable` and never become zero. Descriptive metrics use non-evaluative sequential palettes. Average Household Income is prohibited; Area Median Income requires separate later authority.

## Local-first and protected-data requirements

The functional operator runtime must run on the user's Windows machine without Power BI Service, Fabric, premium capacity, a cloud database, hosted application backend, enterprise deployment, paid proprietary GIS, account, login, production server, telemetry, analytics, or crash reporting. A minimal HTTP server must bind only to loopback by default and serve only an explicit allowlist of presentation assets and selected local inputs.

Protected MODEL-13 values and protected evidence remain local. They must not enter public Git or GitHub, basemap or imagery requests, geocoding, telemetry, analytics, crash reporting, remote APIs, third-party query strings, external logs, or screenshots. Public viewport coordinates and tile identifiers may reach an explicitly reviewed basemap service. Protected overlay values are joined and styled only within the local browser/runtime.

The spike uses synthetic MODEL-13-like values. A distinctive synthetic canary must prove that protected-shaped values do not appear in external request URLs, methods, bodies, or available headers. Real protected MODEL-13 rows are unnecessary and prohibited for ARCH-01 unless a later authority change explicitly establishes necessity.

## Technology and basemap evaluation

The architecture decision must evaluate at least:

- a file-opened static page versus a browser application served by a minimal local server;
- MapLibre GL JS, Leaflet, or a materially equivalent open mapping library;
- plain JavaScript versus TypeScript and a UI framework;
- direct prepared-file loading versus SQLite, DuckDB, or another local query engine; and
- a public online basemap, a locally packaged basemap, and an explicit basemap-unavailable fallback.

For every selected dependency the decision records purpose, pinned version or version policy, license, cost, maintenance posture, security/telemetry posture, and replacement boundary. For every selected external basemap or imagery service it records terms, attribution, rate or availability posture, API-key and cost posture, privacy and data routing, exact egress, and replacement/fail-closed behavior. No recurring paid dependency is authorized.

## Minimum architecture spike

The source-controlled spike is architecture evidence, not a production dashboard. It uses the accepted public 3,017-tract presentation geometry and deterministic synthetic values shaped like the protected presentation inputs. It must demonstrate:

- all 16 metric-selector entries and dynamic metric metadata;
- fixed percentile and valid-only P02/P98 domains, saturation, and explicit missingness;
- responsive 3,017-polygon rendering, pan/zoom, tract selection, and metric switching;
- empty, single, and multiple selection states;
- inspector, contextual-warning, QA, and source/definition/unit concepts;
- loopback-only serving, no telemetry, and an allowlisted local-file surface; and
- deterministic bundle reconstruction plus synthetic-canary nontransmission.

The spike remains intentionally bounded. It does not need production styling, production protected-input preparation, operator authentication, deployment, geocoding, routing, traffic, drive time, or a production support model.

## Performance, restart, and recovery evidence

Measure disclosure-safe local startup time, server and browser memory where observable, CPU behavior during interaction where observable, 3,017-polygon render readiness, metric-switch latency, tract-selection latency, and stability across repeated open/close or restart cycles. Compare these observations only to the separately recorded Power BI failure evidence; do not manufacture a direct benchmark when the Power BI runtime is unavailable.

Failure behavior must preserve a usable local neutral-map or explicit basemap-unavailable state when an external basemap is unavailable, fail closed on malformed or unreconciled local inputs, and allow clean restart without hidden imported-data caches or manual repair.

## Required outputs

ARCH-01 produces:

- exactly one governed manifest and this one controlling work order;
- one disclosure-safe Issue, one task branch, and one PR;
- one architecture decision artifact covering selection, rejected alternatives, runtime topology, maps, input loading, data and egress boundaries, dependencies, resource evidence, recovery, tests, PBI-02 semantic migration, and exact follow-on boundary;
- a minimal public/synthetic spike, deterministic reconstruction tooling, dependency and license evidence, and conformance tests; and
- disclosure-safe exact-H validation evidence.

## Exact-H gate

At exact H the manifest is `COMPLETED_AWAITING_ACCEPTANCE`; execution is `COMPLETED`; capability acceptance is `NOT_REVIEWED`; the architecture selection and selected stack are explicit and justified; the spike validates all 3,017 tracts, exactly 16 metrics, required interaction and scale/missingness behavior; local-only default binding and no-telemetry posture pass; protected/public and network-egress boundaries are explicit and tested; basemap terms, privacy, cost, attribution, and failure behavior are documented; deterministic reconstruction and clean restart pass; accepted predecessor records remain unchanged; no protected content enters Git or GitHub; the PR is open and non-draft at exact H; and full repository validation plus exact-H CI succeed.

H stops for `ARCH: Presentation Architecture Decisions & Acceptance`. No A, merge, PBI-02 transition, production implementation, publication, deployment, or follow-on work is authorized.
