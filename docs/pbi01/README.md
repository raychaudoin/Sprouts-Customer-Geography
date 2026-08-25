# PBI-01 Michigan Power BI MVP operator guide

PBI-01 provides the local **Sprouts Customer Geography — Michigan** MVP as a source-controlled Power BI Project. The tracked source of truth is `powerbi/pbi01/project/MICustomerGeography.pbip` plus its PBIR report and TMDL semantic-model definitions. A PBIX, imported data cache, local settings, and protected MODEL-13 inputs are never sources of truth and must remain ignored.

The MVP is decision support, not final site selection, Sprouts' proprietary customer model, or operational Demand Heat authority. MODEL-13 is the sole analytical source. PBI-01 does not recompute scores, spatial memberships, feature construction, support completeness, targets, physical-location identity, or regression logic.

## Protected-local input convention

Place only the already accepted MODEL-13 outputs at these ignored repository-relative paths:

- `powerbi/pbi01/local/model13/tract/model13_michigan_tract_scores.csv`
- `powerbi/pbi01/local/model13/seed-context/model13_michigan_seed_context.csv`
- `powerbi/pbi01/local/model13/metadata/model13_michigan_power_bi_metadata.json`
- `powerbi/pbi01/local/model13/metadata/READY.json`

Do not put protected rows, source handles, absolute paths, screenshots, or runtime files in tracked folders. The preflight reports only disclosure-safe accounting and readiness state.

## Reconstruct and open locally

From the repository root, run:

```powershell
python scripts/pbi01/preflight.py
python scripts/pbi01/build_semantic_model.py
python scripts/pbi01/build_report.py
python scripts/pbi01/prepare_runtime.py --replace
```

Preflight must report `READY`, 3,017 tracts, 2,973 computable, 44 noncomputable, 438 support-truncated, 3,017 geometry keys, and seed-context readiness. The runtime command copies the tracked project into ignored `powerbi/pbi01/runtime/run/` and substitutes the two protected local CSV paths only in that ignored copy.

Open `powerbi/pbi01/runtime/run/MICustomerGeography.pbip` in Power BI Desktop and select **Refresh**. On a fresh open or reopen, refresh is expected because the tracked PBIP intentionally contains no protected import cache. Save only the ignored runtime project; never copy its `.pbi` state or a PBIX into the tracked project.

The implementation was validated with Power BI Desktop `2.157.879.0 (26.08)`, PBIR, and TMDL. It uses the built-in Shape Map with embedded public GeoJSON for tract views and a built-in scatter chart for protected-local seed coordinates. It does not require Power BI Service, Fabric, organizational ArcGIS access, marketplace custom visuals, or map-service sign-in.

## Report inventory

The PBIR report contains exactly three 1,920 by 1,080 pages and 33 built-in visuals:

1. **Michigan Opportunity Explorer** — 15 visuals, including the statewide tract Shape Map, three-metric selector, tract filters, accounting cards, and selected-tract detail.
2. **Sprouts Evidence Context** — 8 visuals, including the local-coordinate evidence scatter, protected-local metric cards/table, and QA/support filters.
3. **QA & Coverage** — 10 visuals, including the completeness Shape Map, QA-category chart, tract QA table, filters, and accounting cards.

The geometry joins on `GEOID`. The evidence page intentionally exposes protected values only at local runtime; its definitions and documentation contain no protected row values.

## Public presentation geometry reconstruction

The tracked geometry is a deterministic, simplified presentation derivative of the official 2024 Michigan TIGER/Line tract archive. To reconstruct it from an already downloaded official archive in ignored staging, run:

```powershell
python scripts/pbi01/build_geometry.py --source-zip powerbi/pbi01/local/staging/tl_2024_26_tract.zip --replace
```

The generator pins the official source archive hash, Michigan state FIPS, CRS conversion, simplification tolerance, coordinate precision, 3,017 unique GEOIDs, and output hash. This geometry has no analytical authority; accepted upstream GIS logic remains upstream.

## Repository validation

Run the PBI-01-specific checks with:

```powershell
python scripts/check_pbi01_repository.py
python -m unittest tests.pbi01.test_pbi01_conformance -v
```

The conformance tests use synthetic fixtures only. Full Repository Validation runs this checker and the complete test suite in CI.
