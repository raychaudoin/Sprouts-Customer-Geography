# PBI-01: Michigan Customer Geography Power BI MVP

## Authority and stopping boundary

Master Control Room authorized this Lane B task from canonical `main` commit `a7ee04bb6cd9710fa161858f0b5b2559565cfc9f`, then amended the existing bootstrap-only authority to full Michigan Power BI MVP implementation after Ray completed the Desktop-created PBIP gate. Exact substantive H is accepted or rejected by `PBI: Power BI Decisions & Acceptance`.

PBI-01 remains the same task, branch, Issue, manifest, work order, Lane B classification, and capability owner. It may implement and validate the local MVP, create exact substantive H, open and maintain the existing task's pull request, and run exact-H CI. It cannot self-accept, create A, merge, publish, deploy, use Power BI Service or Fabric, or begin follow-on work.

MODEL-13 and all accepted predecessors remain closed authority. The sole analytical presentation boundary is `MODEL13_MICHIGAN_POWER_BI_OUTPUT_CONTRACT_V1`. Its tract output, seed-context output, and metadata remain protected-local and untracked. MODEL-13 values and lineage are authoritative; PBI-01 does not recompute, reinterpret, refit, or rescore them.

## Repository-safe workspace convention

The task uses one branch, one manifest, and this one controlling work order.

Tracked source-controlled surfaces are:

- `powerbi/pbi01/project/` for the Power BI Desktop-created `.pbip`, PBIR report, and TMDL semantic-model definitions;
- `powerbi/pbi01/presentation/` for deterministic presentation-geometry definitions and their generator;
- `scripts/pbi01/` for deterministic preflight, reconstruction, and checker scripts;
- `tests/pbi01/` for PBI-01 conformance tests; and
- `docs/pbi01/` for operator and reconstruction documentation.

Ignored-local surfaces are:

- `powerbi/pbi01/local/model13/tract/` for the protected tract input;
- `powerbi/pbi01/local/model13/seed-context/` for the protected seed-context input;
- `powerbi/pbi01/local/model13/metadata/` for protected MODEL-13 metadata;
- `powerbi/pbi01/local/staging/` for any other protected-local staging;
- `powerbi/pbi01/runtime/` for local PBIX or other binary runtime artifacts; and
- Power BI-generated `.pbi/localSettings.json`, `.pbi/cache.abf`, autosave, and local-settings files covered by the repository ignore rules.

The ignored-local folders are storage conventions only. Bootstrap does not locate, inspect, copy, or move protected rows into them.

## Desktop-owned project representation

Power BI Desktop created the initial skeleton through its normal **File > Save As > Power BI Project (.pbip)** flow. The repository-relative project folder is `powerbi/pbi01/project/`, and the exact project/report name is `MICustomerGeography`.

The project uses PBIP with PBIR report definitions and TMDL semantic-model definitions. A local PBIX may exist only as an ignored runtime artifact and is never a tracked source of truth.

## Accepted inputs and fail-closed preflight

Before refresh, deterministic local preflight verifies the accepted contract identity; exact filenames; metadata READY state; required tract and seed schemas; metadata-bound byte hashes and lineage where available; 3,017 tract rows; 2,973 computable tracts; 44 explicitly noncomputable tracts; 438 support-truncated tracts; unique GEOIDs; and absence of unexpected schema drift. Any mismatch fails closed. Protected absolute paths remain ignored and local.

## Report and semantic-model scope

The report title is **Sprouts Customer Geography — Michigan** and contains exactly three working pages:

1. **Michigan Opportunity Explorer** presents the dominant statewide tract choropleth, a Customer Fit / Household Opportunity / Modeled Target Mass selector, tract filters and details, and compact accounting cards.
2. **Sprouts Evidence Context** presents the accepted local-only seed-context evidence spatially where the built-in Desktop map capability supports it, plus protected-local evidence fields and QA/support context without committing rows or screenshots.
3. **QA & Coverage** makes noncomputability, support truncation, missingness, completeness diagnostics, and tract-level QA inspectable, and states that boundary support truncation is descriptive and unsupported out-of-state or Canadian demographics were not manufactured.

Power BI owns only light presentation logic: selection, display, counts, filters, formatting, and selected-tract detail. Model fitting, scoring, feature construction, spatial membership, support computation, target transformation, identity, and regression remain upstream.

## Presentation geography

PBI-01 deterministically reconstructs public Michigan 2024 TIGER tract presentation geometry from the accepted upstream geography authority, joins it by GEOID, and requires exactly 3,017 unique keys with full tract-table reconciliation. Geometry is presentation-only. A reasonably sized disclosure-safe artifact may be tracked; otherwise its generator and reconstruction instructions are the source of truth.

## Implementation evidence at H

The source-controlled result is the Desktop-created `MICustomerGeography` PBIP skeleton populated through supported PBIR `3.3.0` report definitions and TMDL semantic-model definitions. The report contains exactly three pages and 33 built-in visuals. Michigan tract views use two Shape Map visuals backed by the embedded deterministic public GeoJSON; the protected-local seed evidence uses one coordinate scatter and requires no external map service or sign-in. No custom visual is present.

The fail-closed local preflight verified `MODEL13_MICHIGAN_POWER_BI_OUTPUT_CONTRACT_V1`, exact filenames and schemas, READY metadata, metadata-bound hashes, lineage, unique tract keys, 3,017 total tracts, 2,973 computable tracts, 44 noncomputable tracts, 438 support-truncated tracts, seed-context readiness, and a complete 3,017-key geometry join. It did not recompute or change MODEL-13.

Power BI Desktop `2.157.879.0 (26.08)` refreshed and rendered all three pages locally. The Customer Fit, Household Opportunity, and Modeled Target Mass selector states were exercised; accounting cards displayed the exact statewide totals; both tract Shape Maps, the seed evidence coordinate view, slicers, detail tables, and QA views rendered. The project saved, closed, reopened, refreshed again, rendered all three pages again, saved with no unsaved changes, and closed. Reopen requires refresh by design because protected imported-data caches remain untracked.

The Microsoft PBIR validator reported zero errors and zero warnings. PBI-01 conformance tests, all repository checkers, protected-path safeguards, and the complete 325-test repository suite passed, with four expected skips for deliberately untracked source-dependent fixtures. Exact-H Repository Validation remains required on the pull request.

## Exact-H gate

At exact H the manifest is `COMPLETED_AWAITING_ACCEPTANCE`; execution is `COMPLETED`; capability acceptance is `NOT_REVIEWED`; all three pages are complete; MODEL-13 inputs and metadata pass preflight; all 3,017 tract keys reconcile to presentation geometry; protected seed context is refresh-ready; the PBIP refreshes and reopens successfully when Desktop execution is available; no upstream analytical or GIS logic moved into Power BI; no protected content entered Git or GitHub; and repository validation plus exact-H CI succeed.

H stops for `PBI: Power BI Decisions & Acceptance`. No A, merge, publication, deployment, or follow-on substantive work is authorized.
