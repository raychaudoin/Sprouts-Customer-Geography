# PBI-02: Michigan Map-First Scouting & Public Context Redesign

## Authority and stopping boundary

Master Control Room authorized this Lane B successor task from canonical `main` commit `499cd611605380a3f2abca1e3e1d2f27cc56301c`. `PBI: Power BI Decisions & Acceptance` reviewed Product Design Option 1 and returned **ACCEPT WITH REQUIRED MODIFICATIONS**; the incorporated requirements below are controlling product authority.

PBI-02 uses exactly one branch, one task manifest, this one controlling work order, one disclosure-safe GitHub Issue, and one pull request. It stops at exact substantive H for `PBI: Power BI Decisions & Acceptance`. It cannot self-accept, create acceptance-record-only A, merge, publish to Power BI Service or Fabric, deploy, or begin follow-on work.

PBI-01 remains accepted historical authority. Its manifest, accepted implementation commit, and acceptance metadata must remain byte-for-byte unchanged. PBI-02 modifies the existing `powerbi/pbi01/project/MICustomerGeography.pbip` PBIR/TMDL project as successor product work; it must not create a second Power BI application.

## Current MCR preservation disposition

Master Control Room completed cross-capability disposition after the protected-local and first real-data Desktop execution stage. The prior `PBI02_MODEL13_METADATA_UNRESOLVED` condition is superseded and must not be presented as the current blocker. Both authorized MODEL-13 presentation-package candidates were resolved within the governed local boundary and independently passed the accepted validator. Repository authority did not distinguish between the two valid packages, so one was selected deterministically without moving, copying, renaming, regenerating, recomputing, or changing either protected package.

The selected exact package passed READY, hash, lineage, seed-readiness, and geometry-reconciliation bindings. MODEL-13 accounting reconciled exactly to 3,017 tracts: 2,973 computable, 44 noncomputable, and 438 support-truncated. The full PBI-02 preflight returned `READY`; ignored runtime preparation succeeded; the first real-data Power BI Desktop refresh completed; and the Michigan tract layer rendered on the Road basemap.

Validation then stopped because local Power BI Desktop and Windows exhausted paging-file/system resources. Power BI exited before the required save, close, reopen, and second refresh, so those gates and the remaining real-data Desktop validation are incomplete. No substantive H was created, and no protected artifact was moved, copied, committed, or uploaded.

MCR therefore directs PBI-02 to remain Lane B, non-H, unaccepted, unmerged, and preserved as implementation/fallback evidence while ARCH-01 evaluates the successor presentation architecture. Do not continue substantive Power BI implementation or validation solely to force H. PR #35 remains draft, and no capability acceptance is requested. The task manifest remains `BLOCKED_FAIL_CLOSED` with execution `BLOCKED`, capability acceptance `NOT_REVIEWED`, no `implementation_commit`, and no invented `PAUSED` lifecycle state. This preservation disposition returns current coordination to `MASTER CONTROL ROOM: Sprouts Customer Geography`; if MCR later resumes PBI-02 through genuine exact H, the acceptance destination remains `PBI: Power BI Decisions & Acceptance`.

## Accepted predecessor boundary

The implementation must recover and preserve:

- accepted PBI-01 and its `Michigan Tracts`, `Seed Context`, `Metric Selector`, and `Report Measures` semantic-model baseline;
- `MODEL13_MICHIGAN_POWER_BI_OUTPUT_CONTRACT_V1` and exact accepted protected-local MODEL-13 tract, seed-context, and metadata outputs;
- `DATA04_MICHIGAN_PUBLIC_DATA_PARITY_SOURCE_CONTRACT_V1` and exact accepted 2024 Michigan candidate materialization;
- `PBI01_MICHIGAN_2024_TIGER_TRACT_PRESENTATION_GEOMETRY_V1`, exactly 3,017 2024 Michigan TIGER tract GEOIDs; and
- repository disclosure, protected-data, provenance, Power BI, and Git governance.

MODEL-13, DATA-04, DATA-03, GEO-05, and the 2024 Michigan TIGER authority remain closed. PBI-02 adds presentation behavior only. It must not refit, rescore, reinterpret, impute, zero-fill, alter source values, change a source vintage, or move model fitting, feature construction, target transforms, support computation, spatial membership, or analytical GIS into Power BI.

## Product outcome and page layout

Replace the poor primary scouting UX with a map-first Michigan geographic exploration experience. The primary workflow is:

1. choose **COLOR TRACTS BY**;
2. explore Michigan on a recognizable Road basemap;
3. optionally choose Satellite road labels using Azure Maps' native Style picker;
4. select one tract;
5. read the tract's exact selected metric, opportunity context, selected demographics, and material warning; and
6. clear selection and continue scouting.

This is decision support, not routing, navigation, final site selection, a site-level sales forecast, a final site recommendation, or Sprouts' proprietary customer model.

The primary page remains 1,920 × 1,080:

- header: `x=0`, `y=0`, `w=1920`, `h=72`;
- primary map: `x=0`, `y=72`, `w=1440`, `h=1008`;
- inspector rail: `x=1440`, `y=72`, `w=480`, `h=1008`; and
- approximate inspector padding: 24 px.

Remove the permanent statewide KPI band, technical QA/filter stack, and competing small visuals from the primary page. Retain technical inspection on **QA & Coverage** and protected-local evidence on the separate **Sprouts Evidence Context** page.

## Azure Maps access and disclosure gates

The primary surface must use the built-in Power BI Azure Maps visual. Do not use marketplace visuals, HTML/JavaScript/React, ArcGIS organizational access, or Shape Map as an equivalent fallback.

The target Power BI Desktop environment must prove:

- Azure Maps can be created, rendered, saved, closed, reopened, and reconstructed in the exact PBIP;
- default style is Road;
- Satellite road labels renders;
- the native Style picker is available to the report reader;
- road/place labels remain visible;
- the data-bound reference layer contains exactly 3,017 Michigan tract polygons joined by public GEOID;
- polygons are semi-transparent at approximately 40% fill opacity with subdued approximately 1 px boundaries;
- unavailable tracts have a neutral treatment;
- ordinary tract click selection works; and
- Azure Maps multi-selection/selection tools capable of invoking subprocessors, drive-time, lasso, routing, traffic, and navigation behavior are disabled.

Only public geography and mapping context may be intentionally transmitted to Azure Maps: public Michigan tract geometry, public GEOID, viewport/basemap requests, and clearly public map context. Protected MODEL-13 values, `Seed Context`, coordinates or identities, Isolated Sales, predictions, errors, protected paths, protected metadata, and protected physical-location identifiers must never be placed in Location/geocoding roles or intentionally transmitted externally.

Before any real protected MODEL-13 value is connected to Azure Maps color, tooltip, selection, or inspector interaction, run a synthetic canary in the exact target Desktop/Azure Maps configuration. Use distinctive synthetic values on public synthetic/test tract bindings and inspect the actual outbound Azure Maps request/data path using already-installed local Power BI, OS, network, diagnostic, logging, WebView, or inspection facilities. The proof must demonstrate that values used only for polygon color, tooltip, selection, and inspector interaction are absent from outbound Azure Maps requests. Documentation alone is insufficient. Do not install a new proxy/security tool or alter trust/certificate infrastructure. Commit only disclosure-safe method and result evidence; raw traffic captures remain untracked.

If tenant policy blocks Azure Maps or the synthetic outbound-data proof cannot be established, stop fail-closed before connecting real protected MODEL-13 values. Set the task to `BLOCKED_FAIL_CLOSED` and return the bounded access/decision blocker to `PBI: Power BI Decisions & Acceptance`; do not produce a misleading completed H.

## Exact local data and fail-closed preflight

MODEL-13 preflight retains the PBI-01 invariants: 3,017 tracts; 2,973 computable; 44 noncomputable; 438 support-truncated; accepted ranks, percentiles, scores, QA/missingness, protected-local `Seed Context`, lineage, byte hashes, and READY chronology. No protected row enters Git or GitHub.

PBI-02 additionally consumes accepted DATA-04 logical source `multivariate/michigan_tract_candidate_measures.csv` with SHA-256 `adcc5ce6b08bb9973ccb5d76ac59162013d7db524e266d18585719581cca9198`. If absent, PBI-02 may mechanically reconstruct the exact accepted public DATA-04 package with existing accepted tooling and source contracts; it may not substitute another source, vintage, table, definition, or derivation.

The extended preflight must verify at least:

- exact DATA-04 contract identity and active version;
- READY-last state and accepted package/file identity;
- exact candidate CSV hash and exact accepted ordered schema;
- 3,017 unique ordered Michigan GEOIDs, no duplicates, and complete reconciliation with `Michigan Tracts` and presentation geometry;
- accepted estimate, MOE, status, and status-detail fields for all 13 measures;
- no missing-to-zero conversion, imputation, silent favorable/neutral treatment, or row deletion; and
- validated one-to-one relationship eligibility.

## Semantic model and exact metric catalog

Preserve the PBI-01 model and add one row per GEOID table named **Michigan Public Context** (or an equally clear equivalent) with a validated one-to-one relationship to `Michigan Tracts` on GEOID. Expose operator-facing estimates; retain status, MOE, and status detail for QA; hide technical status/MOE fields from ordinary scouting-field browsing where appropriate.

Retain and expand the disconnected `Metric Selector`; do not replace it with a Field Parameter. The exact 16 production map layers, in order, are:

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

Average Household Income and Area Median Income are forbidden. Do not derive, proxy, rename, or imply either concept.

For every selector row retain a stable canonical metric key, source-authority ID, family/group, operator display name, optional short name, sort order, unit, dynamic format policy, plain-English definition, interpretation guidance, source label, vintage label, scale policy, availability category, and contextual-warning policy. One selection coherently drives polygon color, five-step legend, unit/format, title/subtitle, help, tooltip, selected-tract value, source/vintage, scale, availability, and warning.

Operator language must follow accepted universes and semantics. **Employment Rate** is employed civilians divided by the civilian labor force, not employment-to-population. **Customer Fit Percentile** is relative among computable Michigan tracts, is a public-data proxy, and is not Sprouts' proprietary model. **5-Mile Household Opportunity** is households/opportunity mass, not fit. **Modeled Target Mass Percentile** is not a site-level forecast or recommendation. ACS measures use exact DATA-04/DATA-03 universes, derivations, units, source, and 2024 ACS five-year vintage. Raw ACS variables, repository field names, internal IDs, and status codes are not primary scouting language.

## Robust color-scale policy

Customer Fit Percentile and Modeled Target Mass Percentile use fixed 0–100 domains. Every other numeric layer—5-Mile Household Opportunity and all 13 DATA-04 measures—uses a statewide valid-value P02 to P98 domain computed at refresh.

The domain must remain fixed across panning, selection, and report filtering during that refresh/session. Invalid, missing, inapplicable, and otherwise nonvalid rows do not participate. Authoritative values are unchanged; values below P02 saturate low, values above P98 saturate high; outer legend labels use `≤` and `≥`; the legend has five formatted steps and a separate neutral **No Data / Unavailable** state. Descriptive demographics use sequential palettes without red-versus-green good/bad semantics. A refresh-generated presentation-scale metadata table is permitted as the smallest deterministic presentation mechanism.

## Inspector, selection, tooltip, and warnings

The inspector begins with **COLOR TRACTS BY**, single-select control, current unit, source/vintage, concise definition, interpretation guidance, and dynamic five-step legend.

With no tract selected, never show stale tract values. Show **Select a tract** plus the selected metric definition, unit, source/vintage, and interpretation.

With exactly one tract selected, show in order:

1. selected metric name and exact value/unit;
2. material warning immediately below when applicable;
3. Customer Fit Percentile;
4. 5-Mile Household Opportunity;
5. Median Household Income;
6. Owner-Occupied Housing Share;
7. No-Vehicle Household Share; and
8. GEOID as secondary technical reference.

If the selected metric duplicates a support row, suppress the duplicate and substitute the next most useful accepted public-context value. County, city, and community names are not authorized; basemap labels supply orientation.

Single tract click is primary. Multiple selections must show **Multiple tracts selected**, never an average masquerading as tract detail. Native deselection is acceptable. A clear-selection button is optional only if a reliable native/bookmark mechanism proves correct.

Provide a noninteractive report-page tooltip with selected metric, exact value/unit, Customer Fit Percentile, 5-Mile Household Opportunity, useful public context, GEOID, relevant warning, and source/vintage. It must contain no raw protected identifier, protected seed context, interactive control, or internal field name.

Warnings are metric-specific. Direct DATA-04 layers show their own missing/invalid/inapplicable warning and never inherit MODEL radius warnings. 5-Mile Household Opportunity shows accepted five-mile support truncation when applicable. MODEL layers show MODEL-13 noncomputability and only their relevant accepted support warning. Missingness never becomes zero, neutral, or favorable.

## QA and protected evidence pages

Retain **QA & Coverage** and existing MODEL-13 QA. Add selected public metric status, MOE, status detail, availability/missingness, and complete 3,017-key public-context reconciliation.

Preserve **Sprouts Evidence Context** as a separate protected-local page with unchanged purpose. Its protected coordinates, identities, sales, predictions, errors, and other values must not bind to or pass through Azure Maps.

## Tracked and local-only boundary

Tracked scope may include the PBI-02 manifest/work order; PBIR/TMDL; built-in Azure Maps definitions containing only public geometry/reference configuration; metric metadata; light DAX/presentation logic; public deterministic geometry; preflight/reconstruction tooling; tests; operator documentation; and disclosure-safe canary methodology/results.

Tracked scope must never include protected MODEL-13 rows, seed rows or coordinates, Isolated Sales, predictions/errors, protected paths/handles/metadata, real protected screenshots, raw network traces, imported caches, PBIX/PBIT binaries, or real DATA-04 tract rows. Runtime project copies, canary inputs/captures, DATA-04 packages, MODEL-13 inputs, and Power BI caches remain ignored.

## Validation and exact-H gate

Conformance coverage must include one PBI-02 manifest/work order; unchanged PBI-01 acceptance bytes; exact DATA-04 contract/hash/schema/status binding; 3,017 unique public keys and one-to-one eligibility; exact 16-metric inventory and forbidden AHI/AMI absence; accepted labels and metadata completeness; fixed and P02/P98 scale semantics; No Data behavior; no zero-fill/imputation; public-only Azure Maps bindings; disabled multi-selection tools; protected-field exclusion from Location/geocoding; reconstruction definitions; and protected/local Git safeguards.

Run the PBI-02 checker, focused tests, full unit suite, every repository conformance checker, disclosure safeguards, Microsoft PBIR validation when available, and required `repository-validation` CI.

After the canary gate passes, validate with real authorized local data in installed Power BI Desktop: project open; refresh; Road; Satellite road labels; native Style picker; 3,017 polygons; all 16 selector layers; fixed and P02/P98 scales; neutral missingness; selection/empty/multiple inspector states; warning placement; tooltip; QA; separate Evidence Context; save; close; reopen; second refresh; and persisted Azure Maps/reference-layer formatting.

At exact H:

- manifest state is `COMPLETED_AWAITING_ACCEPTANCE`;
- execution is `COMPLETED` and capability acceptance is `NOT_REVIEWED`;
- PR is open and non-draft with head exactly H;
- exact-H `repository-validation` succeeds;
- Azure Maps tenant/access, Road, Satellite road labels, Style picker, and multi-selection gates pass;
- synthetic-canary outbound-data proof passes before real protected bindings;
- exact accepted MODEL-13 and DATA-04 inputs validate and refresh;
- 3,017 geometry/public-context keys, exact 16 metrics, scale policy, inspector, tooltip, QA, and separate Evidence Context validate;
- Desktop save/close/reopen/second-refresh and available PBIR validation pass; and
- no protected or public-disclosure violation exists.

Stop at H for `PBI: Power BI Decisions & Acceptance`. Do not create A, merge, publish, deploy, or start another substantive task.
