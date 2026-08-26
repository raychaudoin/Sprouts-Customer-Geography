# APP-01: Michigan Local-First Customer Geography Dashboard

## Authority, lane, and stopping boundary

Master Control Room authorized this Lane B task from canonical `main` commit `b29be0c1c4faf173fc95f402446ddfd92f73f92c`. Exact substantive H is ultimately accepted or rejected by `ARCH: Presentation Architecture Decisions & Acceptance` after the mandatory final integrated review. GitHub Issue `#38` is the single disclosure-safe derivative cockpit. The task branch is `task/app-01-michigan-local-first-customer-geography-dashboard`.

APP-01 is the real local operator application. It is not an architecture-selection spike, another Power BI implementation, or a synthetic-only prototype. It implements the already accepted local-first architecture over the exact accepted MODEL-13, DATA-04, and public Michigan tract presentation inputs.

Stage 1 runs in this task, branch, Issue, pull request, and Codex thread under GPT-5.6 Sol / Max. Stage 1 must complete production implementation, the synthetic egress gate, authorized real-data validation, operator validation, and the required Product Design audit/correction cycle. Stage 1 must not create substantive H.

When every Stage-1 gate is complete, execution stops at the pre-Ultra review gate with the current branch and working state preserved. The exact next destination is `MASTER CONTROL ROOM: Sprouts Customer Geography`. Stage 2 later continues this same task under GPT-5.6 Sol / Ultra for final integrated review and bounded corrections before H. No second task, branch, Issue, pull request, or architecture effort is permitted.

## Controlling accepted authority

ARCH-01 is accepted and closed. Its accepted substantive H is `6347b05d1d126f6c63053eeea317dc7abfaa9b50`, acceptance-record-only A is `a2f127871fbc79995d5870da971baa07955a1d67`, and canonical merge is `b29be0c1c4faf173fc95f402446ddfd92f73f92c`.

APP-01 preserves without modification or reinterpretation:

- `MODEL13_MICHIGAN_POWER_BI_OUTPUT_CONTRACT_V1` and accepted MODEL-13 readiness, hashes, lineage, exact tract accounting, and Seed Context boundary;
- `DATA04_MICHIGAN_PUBLIC_DATA_PARITY_SOURCE_CONTRACT_V1`, exact accepted Michigan materialization, definitions, universes, estimates, MOEs, statuses, status details, and missingness;
- `GEO05_MICHIGAN_STATEWIDE_SPATIAL_SUPPORT_SPEC_V1` and accepted 2024 Michigan TIGER authority;
- `PBI01_MICHIGAN_2024_TIGER_TRACT_PRESENTATION_GEOMETRY_V1`, with exactly 3,017 GEOIDs and normalized byte identity;
- PBI-01 report and preflight semantics; and
- `ARCH01_LOCAL_FIRST_PRESENTATION_RUNTIME_POLICY_V1` plus `ARCH01_MICHIGAN_PRESENTATION_METRIC_CATALOG_V1`.

PBI-02 remains separate, draft, unaccepted, non-H, and unmerged. APP-01 may inspect it only as non-authoritative UX evidence. It must not merge, cherry-pick, transition, accept, or base on PBI-02. The preserved PBI-02 head at authorization was `b7edf51093bfd210f2856771095dd8005557f577`.

## Accepted runtime architecture

The production application uses:

- a static local browser application;
- a Python standard-library HTTP server bound only to `127.0.0.1`;
- semantic HTML and CSS plus plain JavaScript ES modules;
- exact vendored MapLibre GL JS 6.6.0 from the accepted ARCH-01 dependency inventory;
- a deterministic prepared JSON bundle keyed by tract GEOID;
- the accepted public Michigan tract GeoJSON;
- USGS Topo by default, USGS ImageryTopo as optional aerial-plus-label context, and a network-free Local neutral fallback; and
- no framework, Node, package manager, build toolchain, database, browser query engine, hosted backend, account, telemetry, analytics, crash reporting, or remote logging.

The application is a presentation surface. Analytical computation, source preparation, spatial analysis, target logic, and protected evidence preparation remain upstream.

## Primary operator workflow

The Explore view is map-dominant at ordinary desktop sizes with a fixed control and inspector rail. The operator launches once, chooses **Color tracts by**, scouts statewide Michigan, switches among Topo, Imagery + Labels, and Local neutral, pans and zooms, selects a tract, reads the selected metric and supporting context, sees any material warning directly with the affected value, clears or changes selection, and continues scouting.

Do not recreate the cluttered PBI-01 layout. Do not add permanent statewide KPI cards to fill space. Do not expose raw repository field names or technical QA fields in ordinary scouting. Basemap labels provide geographic orientation; APP-01 does not invent county, city, community, market, or neighborhood analytical fields.

## Exact metric catalog and scales

The map exposes exactly these 16 layers in this order:

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

Average Household Income and Area Median Income are prohibited. Customer Fit Percentile is a relative public-data proxy, not Sprouts' proprietary model, site recommendation, or sales forecast. Five-Mile Household Opportunity is accepted raw B11001 household opportunity mass around the public internal-point anchor and is not customer fit. Modeled Target Mass Percentile is a relative accepted modeled output, not a site forecast or recommendation. Employment Rate is employed civilians divided by the civilian labor force, not employment-to-population.

Customer Fit Percentile and Modeled Target Mass Percentile use fixed 0–100 domains. The other 14 numeric metrics use statewide valid-only Type-7 P02–P98 domains computed once for the loaded production bundle. Domains do not change with viewport, selection, or interaction. Exact values remain unchanged, values outside the robust bounds saturate the endpoints, legends show five formatted steps with `≤` and `≥`, and every legend includes `No Data / Unavailable`. Missing, invalid, inapplicable, and noncomputable values remain unavailable, are excluded from robust domains, and never become zero or favorable. Descriptive demographic metrics use non-evaluative sequential palettes rather than desirable-versus-undesirable color semantics.

## Inspector, warnings, and selection

With no tract selected, the inspector says **Select a tract** and shows the current metric name, definition, unit, source/vintage, interpretation, and dynamic legend. It does not show stale tract values.

For exactly one selected tract, show in order:

1. selected metric name;
2. exact selected value and unit;
3. relevant warning immediately below the affected value;
4. Customer Fit Percentile;
5. 5-Mile Household Opportunity;
6. Median Household Income;
7. Owner-Occupied Housing Share;
8. No-Vehicle Household Share; and
9. GEOID as a secondary technical reference.

If the selected metric duplicates a support row, suppress the duplicate and substitute the next useful accepted public-context metric. Do not show the same value twice.

Multiple selection explicitly says **Multiple tracts selected** and never presents an average as one tract. Provide a straightforward clear-selection action. A lightweight hover treatment is permitted but remains subordinate to the selected-tract inspector and may expose only accepted presentation fields.

Warnings are contextual. Direct DATA-04 metrics show only their own missing, invalid, inapplicable, status, status-detail, and MOE context. Five-Mile Household Opportunity shows accepted five-mile support truncation where applicable. MODEL layers show accepted MODEL-13 noncomputability and relevant support limitation only where applicable. Missingness never becomes a numeric value.

## QA and protected-local evidence context

Provide a separate **QA & Coverage** view containing enough information to verify 3,017 total tracts, 2,973 MODEL-13 computable, 44 noncomputable, 438 support-truncated, selected public metric status, selected public metric MOE and status detail, availability, presentation-domain bounds, source/vintage, input readiness, and key reconciliation. Raw technical fields remain here rather than in Explore, and QA must not become a second scouting dashboard.

Provide a separate local-only **Sprouts Evidence Context** view using only exact accepted protected-local Seed Context presentation fields authorized by MODEL-13. Coordinates, identities, sales, predictions, errors, and evidence context must never enter USGS URLs, external query strings, geocoding, routing, traffic, analytics, telemetry, crash reporting, remote logs, public Git, GitHub, or committed screenshots. The browser bundle exposes only fields needed for this separate view; no additional protected presentation field is invented.

## Production input adapters and deterministic bundle

The MODEL-13 adapter recovers the accepted logical local-input convention and validates, before serving any protected row:

- accepted contract and metadata identities and versions;
- READY chronology and required metadata;
- exact CSV schemas;
- metadata-bound hashes and lineage;
- 3,017 tract rows, 2,973 computable, 44 noncomputable, and 438 support-truncated;
- Seed Context readiness; and
- exact key reconciliation with accepted public geometry.

If several protected-local candidates satisfy accepted authority and repository authority does not distinguish them, use an authority-preserving deterministic selection rule. Do not move, copy, rename, mutate, regenerate, or recompute a protected package to resolve selection. If valid candidates disagree in authoritative contents, fail closed. Diagnostics must not disclose protected absolute paths or values.

The DATA-04 adapter consumes exact `multivariate/michigan_tract_candidate_measures.csv` bytes with accepted SHA-256 `adcc5ce6b08bb9973ccb5d76ac59162013d7db524e266d18585719581cca9198`, exact accepted schema, exactly 3,017 unique GEOIDs, no duplicates, explicit status/status-detail/MOE/missingness semantics, and complete reconciliation with public geometry. Existing accepted deterministic public reconstruction tooling may be reused within authority. Real tract-row material remains outside Git.

The production runtime bundle is deterministic and ignored. It contains only required presentation values, availability/status, status detail, MOE, support truncation, domains, source/definition/unit/interpretation, necessary QA metadata, and the authorized evidence-context subset. It never contains unnecessary protected source fields and is reconstructed at ordinary startup when practical.

## Server, security, and egress

Bind only to `127.0.0.1`, never `0.0.0.0`. Maintain an explicit read-only route allowlist. Reject unexpected methods, paths, query strings, and non-loopback Host headers. Apply restrictive CSP and security headers. Do not add protected request logging, file upload, arbitrary file browsing, write APIs, remote-control APIs, or authentication features.

Automatic external egress is limited to reviewed HTTPS `GET` requests to `basemap.nationalmap.gov` for accepted USGS Topo and ImageryTopo tiles. GEOID, selected metric, values, protected coordinates, Seed Context, sales, predictions, errors, support flags, lineage, paths, canaries, and user identity must never leave the machine. MapLibre loads only from the exact vendored dependency. Local neutral must preserve polygons, metric switching, legend, selection, inspector, warnings, and QA without producing new external requests. USGS failure preserves core tract exploration and does not broaden network access.

## Mandatory synthetic production egress gate

Before connecting real protected MODEL-13 values to the production browser runtime, exercise the actual APP-01 application configuration with conspicuous synthetic canaries in every later protected-value path, including polygon color, hover if present, selected-tract inspector, selection state, support/warnings, and Sprouts Evidence Context plumbing. Inspect the actual outbound request path sufficiently to prove no canary or protected-shaped value leaves the machine. Raw captures remain local and untracked; only disclosure-safe methodology/result evidence may be committed. If any canary appears outbound, stop before real protected values and do not weaken CSP, host allowlists, request transforms, or server restrictions.

## Operator packaging, recovery, and validation

Provide one normal Windows launcher from the repository root. It validates prerequisites, resolves and validates accepted local inputs, builds the deterministic bundle, starts the loopback server, opens the default browser when practical, and reports plain-English actionable failures. No tracked file hard-codes a protected absolute path. Any real local settings file is ignored and has only a disclosure-safe template.

Fail closed for absent or invalid MODEL-13, disagreeing valid candidates, invalid hash/schema/READY metadata, absent or wrong-hash DATA-04, schema drift, duplicate/missing/unexpected keys, geometry mismatch, unsupported WebGL, occupied port, and invalid runtime routes. USGS outage permits Local neutral. Production mode never silently substitutes stale or synthetic data and clearly identifies accepted real, synthetic validation, or invalid/no-data mode.

After the synthetic egress gate passes, validate startup, prerequisites, preflight, all 3,017 polygons, all 16 metrics, fixed and robust scales, unavailable rendering, single/multiple/clear selection, inspector and warnings, QA & Coverage, Sprouts Evidence Context, all basemaps, no protected external egress, clean shutdown, clean restart, and deterministic reconstruction. Measure disclosure-safe startup readiness, server memory where practical, polygon readiness, metric switching, selection, reload, and restart stability. Do not manufacture Power BI comparisons.

Bounded accessibility/browser validation uses a current Chromium-family browser, preferably Edge where available, and checks keyboard access, visible focus, logical tab order, labels, readable values, contrast, non-color warning/missing cues, target size, ordinary desktop layouts, and horizontal scrolling. Screenshot evidence alone cannot establish accessibility compliance.

## Mandatory Product Design audit and correction cycle

Do not audit a half-built shell. First complete the production shell, real map, exact metric catalog, production adapter, inspector, warnings, QA, Evidence Context, all basemap modes, synthetic egress gate, authorized real-data operation, and one-step launcher.

Then use the installed Product Design audit workflow against the actual running application with current browser captures. At minimum exercise and capture the initial Michigan view; metric selector and several metrics; pan, zoom, and statewide orientation; one-tract selection; inspector and exact selected value; material MODEL warning; DATA-04 unavailable/status context where available; No Data rendering; multiple and cleared selection; Topo, Imagery + Labels, and Local neutral; QA; Evidence Context; keyboard navigation and visible focus; ordinary desktop viewport; and visible reload/restart recovery.

Evaluate map dominance, hierarchy, density, geographic legibility, scanning, metric discoverability, metric-family distinctions, inspector composition, source/vintage readability, contextual warnings, missing-data clarity, selection states, consistency, spacing, typography, control sizing, interaction affordance, keyboard use, focus, contrast, non-color communication, QA/Evidence separation, operator language, and perceived stability. Tie findings to current-run screenshots and do not claim accessibility compliance from screenshots alone.

Classify each material finding. Implement every high-impact in-scope correction and reasonable medium-impact correction that clearly improves the operator workflow without changing accepted semantics. Record out-of-scope recommendations without implementing them. Rerun affected flows and use new browser evidence to confirm corrections. Product Design may improve bounded presentation behavior but cannot reopen architecture, metrics, definitions, analytical semantics, sources, geography, scoring, privacy, or egress policy.

## Repository and test boundary

Tracked scope may include the manifest, work order, HTML, CSS, JavaScript, Python adapter/server/launcher, accepted vendored MapLibre files, schemas, metric metadata, accepted public geometry, synthetic fixtures, tests, operator documentation, and disclosure-safe audit and validation evidence.

Tracked scope must not include real MODEL-13 rows, real Seed Context, protected locations, sales, predictions, errors, parameters, protected absolute paths or handles, credentials, a real generated bundle, browser profiles/caches, raw network captures, or revealing screenshots.

Conformance covers exact APP-01 identity and Lane B posture; accepted predecessor immutability; PBI-02 separation; exact metric order; prohibited income fields; scale and missingness semantics; geometry identity; synthetic adapter behavior; fail-closed package selection; key reconciliation; loopback/route/method/query/Host/CSP policy; external host and method allowlists; absence of telemetry/analytics/remote logging; synthetic egress protection; Local neutral network behavior; deterministic generation; protected tracked-path safeguards; launcher/restart behavior; and completion of the Product Design audit gate before pre-Ultra transition.

Run focused APP-01 tests, the full unit suite, every repository conformance checker, disclosure/protected-path safeguards, appropriate static validation, and live browser/operator validation. Stage 1 remains pre-H.

## Pre-Ultra review gate

Stage 1 is complete only when the production application and adapters are complete; synthetic egress passes before real protected use; exact MODEL-13, DATA-04, and geometry inputs validate; the real 3,017-tract and 16-metric dashboard works; scales, missingness, inspector, warnings, QA, Evidence Context, basemaps, Local neutral, launcher, reload, and restart behavior work; Product Design has audited the actual app; material in-scope findings are corrected and rechecked; local validation passes; and no protected material has entered Git or GitHub.

At that point stop. Do not create H, mark `COMPLETED_AWAITING_ACCEPTANCE`, route to ARCH acceptance, merge, deploy, or begin another task. Preserve the exact branch and working state and return only the Stage-1 evidence requested by MCR, including confirmation that APP-01 is ready for the mandatory GPT-5.6 Sol / Ultra final integrated review.
