# PBI-02 operator and reconstruction guide

PBI-02 is the governed successor to the accepted PBI-01 Michigan Power BI MVP. It updates the existing source-controlled `MICustomerGeography.pbip`; it does not create a second report. The primary experience is a statewide Michigan Azure Maps explorer with a metric selector and tract inspector, while protected evidence and technical QA remain on separate pages.

This capability is public-data decision support. It is not a final site-selection engine, a site-level sales forecast, routing or navigation, Sprouts' proprietary customer model, or authority to publish or deploy the report.

## Current governed posture

The authenticated target Power BI Desktop environment passed the required synthetic-only Azure Maps capability and outbound nontransmission gate. Road, Satellite road labels, the native Style picker, ordinary single-tract selection, and the 3,017-polygon public reference layer rendered. The disclosure-safe method and result are recorded in [AZURE_MAPS_CANARY.md](AZURE_MAPS_CANARY.md).

That result permitted governed implementation to continue; it is not capability acceptance or exact substantive H. The map-first successor, repository validation, and synthetic Desktop validation are complete, but the standard protected-local MODEL-13 package is currently absent (`PBI02_MODEL13_METADATA_UNRESOLVED`). PBI-02 is therefore `BLOCKED_FAIL_CLOSED` before real protected refresh and exact H. Resumption requires restoring the exact accepted package to its governed local input surface; no protected value or path belongs in Git or GitHub.

## Source-controlled architecture

The tracked project is under `powerbi/pbi01/project/` and contains only reconstruction-safe definitions:

- `MICustomerGeography.pbip` binds the report to its semantic model by relative path.
- `MICustomerGeography.Report/` contains four PBIR pages: **Michigan Opportunity Explorer**, **Sprouts Evidence Context**, **QA & Coverage**, and the noninteractive **Tract Tooltip** report-page tooltip.
- `MICustomerGeography.SemanticModel/` contains six TMDL tables and the validated one-to-one relationship between `Michigan Public Context[GEOID]` and `Michigan Tracts[GEOID]`.
- `StaticResources/RegisteredResources/michigan_2024_tracts.geojson` is the accepted public 2024 Michigan TIGER presentation geometry with exactly 3,017 unique tract GEOIDs.
- `config/pbi/pbi02_metric_catalog.json` is the exact ordered 16-metric presentation catalog.

Complex public-data preparation, spatial analysis, scoring, and support computation stay upstream. Power BI owns only light presentation logic, selection behavior, refresh-stable scale metadata, and rendering.

## Required local inputs

The runtime project must use both exact accepted packages:

1. The protected MODEL-13 Power-BI-ready output package, with its tract CSV, seed-context CSV, metadata, and READY marker. Its standard ignored location is resolved by the PBI-01 preflight. These files contain protected information and must remain local-only.
2. The accepted DATA-04 package containing `multivariate/michigan_tract_candidate_measures.csv`, `verification_report.json`, and `READY.json`. The accepted candidate CSV SHA-256 is `adcc5ce6b08bb9973ccb5d76ac59162013d7db524e266d18585719581cca9198`. DATA-04 tract-row material remains ignored even though its source is public.

The fail-closed PBI-02 preflight verifies MODEL-13's accepted identity, lineage, hashes, READY chronology, exact 3,017 / 2,973 / 44 / 438 accounting, and seed-context boundary. It also verifies DATA-04 contract identity, READY-last chronology, exact candidate bytes and ordered 56-column schema, all 13 estimate/MOE/status/status-detail groups, explicit missingness, 3,017 sorted unique GEOIDs, and exact reconciliation with MODEL-13 and presentation geometry.

Preflight never converts a missing, invalid, inapplicable, or noncomputable value to zero. It returns only disclosure-safe counts and booleans.

## Exact metric behavior

The selector has exactly 16 single-select layers in governed order:

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

Average Household Income and Area Median Income are not metrics and must not be derived, proxied, renamed, or implied. Each catalog row controls the display name, definition, interpretation, unit, format, source/vintage, availability policy, warning policy, palette, binding, and scale policy.

Customer Fit Percentile and Modeled Target Mass Percentile use fixed 0–100 presentation domains. The other 14 metrics use statewide valid-value P02/P98 domains computed at refresh. Invalid and unavailable values do not participate; source values remain unchanged, outliers saturate at the outer colors, and the legend retains a separate **No Data / Unavailable** state.

## Azure Maps and protected-data boundary

The built-in Azure Maps visual receives only public Michigan tract geography and public mapping context. Its Location role binds only `Michigan Tracts[GEOID]`, and its reference layer uses the tracked public tract geometry. Protected values may drive local polygon color, presentation measures, tooltip, selection, and inspector interactions only because the synthetic canary proved those distinctive values absent from the observed outbound Azure Maps request path.

Never bind `Seed Context`, coordinates, identities, Isolated Sales, predictions, errors, protected paths, protected metadata, physical-location identifiers, or any other protected field to Azure Maps Location/geocoding roles. Keep the selection-control/multi-selection surface disabled, and do not enable lasso, routing, traffic, drive-time, or navigation behavior.

Raw request captures, canary inputs, runtime copies, Power BI caches, PBIX/PBIT binaries, protected screenshots, real MODEL-13 outputs, and real DATA-04 tract rows stay ignored and untracked.

## Deterministic reconstruction

From the repository root, reconstruct the tracked PBIR/TMDL definitions:

```powershell
python scripts\pbi02\build_project.py
python scripts\check_pbi02_repository.py
```

The tracked TMDL retains three source tokens and no machine-specific path:

- `__PBI01_TRACT_CSV__`
- `__PBI01_SEED_CSV__`
- `__PBI02_PUBLIC_CONTEXT_CSV__`

Run the exact-input preflight against standard ignored inputs:

```powershell
python scripts\pbi02\preflight.py
```

If the accepted DATA-04 package is at another ignored location, provide its package root:

```powershell
python scripts\pbi02\preflight.py --data04-root <accepted-data04-package-root>
```

Create the ignored Desktop runtime copy only after preflight passes:

```powershell
python scripts\pbi02\prepare_runtime.py --replace --data04-root <accepted-data04-package-root>
```

For an explicitly selected MODEL-13 package root, use:

```powershell
python scripts\pbi02\prepare_runtime.py --replace --model13-root <accepted-model13-package-root> --data04-root <accepted-data04-package-root>
```

Open `powerbi/pbi01/runtime/pbi02-run/MICustomerGeography.pbip` in the authenticated target Power BI Desktop environment. Never open the tracked project for a protected refresh because its source tokens are intentionally unresolved.

## Desktop validation checklist

Use exact accepted local inputs, then verify all of the following before exact H:

- Preflight returns `READY`, with 3,017 MODEL-13, DATA-04, and geometry keys and one-to-one eligibility.
- The project opens and refreshes without an unresolved-source or relationship warning.
- The primary map renders the Road basemap, public tract polygons, road/place labels, and the neutral unavailable state.
- Satellite road labels renders through the native Style picker, and returning to Road works.
- All 16 selector choices update title/help, five-step legend, polygon color, unit/format, source/vintage, tooltip, inspector, availability, and contextual warning coherently.
- Fixed 0–100 domains apply only to the two governed percentile layers; all other layers use refresh-stable valid-only statewide P02/P98 domains.
- With no selection, the inspector says **Select a tract** and shows no stale tract value.
- One ordinary tract click shows the exact selected metric, applicable warning, support metrics, selected public context, and secondary GEOID.
- Multiple-selection behavior cannot masquerade as a single tract; prohibited Azure Maps selection tools remain disabled.
- The report-page tooltip is noninteractive and contains no protected identifier, protected seed context, coordinate, or internal field name.
- **QA & Coverage** accounts for MODEL-13 and every DATA-04 estimate/MOE/status/status-detail field and confirms 3,017 reconciled public-context keys.
- **Sprouts Evidence Context** remains separate and contains no Azure Maps visual or Azure Maps binding.
- Save, close, reopen, refresh a second time, and confirm Azure Maps/reference-layer formatting and behavior persist.
- Run available Microsoft PBIR validation, the PBI-02 checker, focused tests, the full unit suite, all repository conformance checks, disclosure safeguards, and required CI.

If the exact protected MODEL-13 package is absent, invalid, or inaccessible, or if any required Desktop or disclosure gate fails, stop fail-closed. Preserve the PBI-02 task and branch, record only disclosure-safe evidence, do not claim exact H, and route the minimum blocker to `PBI: Power BI Decisions & Acceptance`.
