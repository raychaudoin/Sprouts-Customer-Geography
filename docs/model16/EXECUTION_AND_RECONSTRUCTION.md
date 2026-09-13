# MODEL-16 execution and reconstruction

MODEL-16 is a bounded Generation 1 comparison under the [controlling Work Order](../work_orders/MODEL_16_CLEAN_MI_WI_EVIDENCE_REBUILD.md) at authority commit `12ee5ad97f9a422edeb63664641cfbbae49fe465` and the latest [Issue 46 launch](https://github.com/raychaudoin/Sprouts-Customer-Geography/issues/46#issuecomment-5651462190). MODEL-13 remains accepted. MODEL-14 and preserved MODEL-15 work are unchanged. This branch creates no acceptance, deployment, merge, or successor-generation authority.

## Sources and feature preparation

Install this checkout with Python 3.13 and the pinned numerical and geodatabase dependencies in `pyproject.toml`. Public acquisition requires internet access. Protected computation uses local joins; no protected address, coordinate, identifier or target is sent to a public service.

```powershell
python -m pip install .
python -m sprouts_customer_geography.model16.public_data --cache data/cache/model16
```

The [research report](PUBLIC_SOURCE_RESEARCH.md), public source manifests in `config/model16`, and [feature catalog](../../config/model16/feature_catalog.json) document source selection, dates, terms, transformation and missingness. Public files are cached outside Git with integrity receipts. A failed discovery endpoint does not prove that the source is unavailable or unlawful. A source that was not materialized is not described as empirically rejected.

The primary track requires source versions demonstrably available before each forecast year. Retain the verified 2022 ACS estimates for 2024, 2023 ACS estimates for both 2025 and 2026, and fixed 2023 TIGER tract geometry. The available 2024 ACS files are dated January 2026; the available 2024 TIGER files are dated June 2025. Those retrieved bytes cannot establish the earlier cutoff and are excluded from the primary track. Fixed geography avoids introducing later boundary revisions. Successive ACS periods overlap four years; their difference is a noisy descriptive change measure.

The accepted baseline definitions remain separate from broader candidate features. Coverage-qualified economic profiles require at least 95% of known positive aggregation weight; unknown uncertainty remains flagged. Structural historical EPA/FARA/LODES products retain their documented older vintages. Business and permit series use release-aware lags. Missing transit coverage, food-access rows and incomplete commute-distance geography remain null.

## Protected stages and one-use controls

The originals are registered in place through exactly the three Work Order logical IDs. Registration takes the explicit user-authorized files; it does not discover, scan, relocate or copy substitutes. A separate registered protected output package stores identity projections, features, access audits, fits, exact memberships and results. No original path or private digest belongs in this repository.

Normal continuation recovers those registrations without user-supplied paths:

```powershell
python -m sprouts_customer_geography.model16.workflow identity
python -m sprouts_customer_geography.model16.workflow features
python -m sprouts_customer_geography.model16.workflow prepare
python -m sprouts_customer_geography.model16.workflow freeze_features
python -m sprouts_customer_geography.model16.workflow develop
python -m sprouts_customer_geography.model16.workflow seed_2026
python -m sprouts_customer_geography.model16.workflow pursued
python -m sprouts_customer_geography.model16.workflow finalize_evidence
```

These commands describe the stage sequence, not permission to restart a completed generation. On a completed package, recover the saved results. Do not recreate or remove its journal. Running identity intake again does not confer target access or replace an existing projection. The feature/source/library freeze binds exact public definitions, analytical code, original integrity, identity, eligibility and feature bytes before development targets are decoded. The model freeze binds the completed fit objects and selection before any holdout targets are decoded.

The one-use SQLite journal durably consumes a holdout opening before its cell projection starts. An interrupted opening remains consumed. Only a completed saved result is recoverable through the evaluation command; it cannot reopen original target cells. Prediction paths are checked against already-known features before claiming the opening. Failure never grants an extra look. Protected numerical objects are loaded only after verifying their saved commitment. Pickle files must remain local trusted outputs; this workflow does not accept arbitrary model files.

Only Isolated Sales target cells for the current role are decoded. All Impacted Sales bodies and other roles' target bodies are excluded by the selective parser. Raw workbook hashing establishes immutable original integrity and does not turn prohibited cells into analytical fields. All source rows remain in evidence accounting, including pre-target geographic exclusions. Cross-year observations are retained, exact duplicate candidates fail closed, and distance only flags identity review.

## Development comparison and interpretation

The [model library](../../config/model16/model_library.json) fixes the candidate methods, parameter grids, five outer/four inner physical-location-grouped folds, metrics and selection gates. Each location totals one fitting weight across its admitted years. Scaling, imputation, missing indicators, correlation screening, spline knots, PCA, tuning and ensemble weights are learned inside training folds. The baseline uses its accepted strict missingness and feature-priority rules; candidate imputations are separate. Unavailable candidates retain explicit failure reasons.

Primary metrics give each physical location one arithmetic-mean actual/prediction pair. Supplemental row-error metrics preserve within-location yearly errors with inverse observation-count weights. Reports include pooled and state results, paired outer-fold differences, stability, family additions/removals and omission sensitivity. Omission sensitivity removes a location or market from scored out-of-fold predictions; it is not a claim of leave-market-out retraining. All such diagnostics use development evidence only.

At most one challenger is frozen. The same frozen objects receive the one-time temporal and pursued evaluations. Temporal rows at development locations are explicitly separated from new-location rows. Pursued independence is checked against all Seed Point locations, including 2026 locations. Matched locations cannot be called independent external evidence. Development ranking among many bounded candidates is selection evidence, not independent confirmation. A later source family or another generation requires new authority after these holdouts are opened.

## Verification and return

Synthetic tests exercise prohibited-field exclusion, source schema, identity, weighted grouped validation, source bytes/vintages, missingness, freeze chronology, concurrency, interrupted openings, replay and public-report disclosure. The existing Repository Validation workflow runs the complete repository suite; accepted model checks remain unchanged.

The final protected sidecar records every observation's source, year, class, physical group, evidence role and candidate membership, including source-family robustness variants. It records bounded MODEL-16 completeness without changing project-wide completeness. Readiness refresh follows the existing governed publisher and actual-file checker. Added pinned dependencies require an exact-blob mailbox maintenance sync of `pyproject.toml`, followed by its passing mailbox check, before the ordinary single-file snapshot refresh. This is a bounded maintenance consequence of this task; no mailbox schema or CI policy is changed.

Stop at the final substantive task head with one open unmerged PR, passing exact-head Repository Validation, complete bounded records and a validated mailbox refresh. Post a concise RESULT record to that PR. Brainstorming receives the result for independent review and Ray's exact-version decision.
