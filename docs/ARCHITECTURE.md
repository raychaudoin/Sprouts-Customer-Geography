# Starting Architecture

This document records a starting architecture guardrail. It is neither an implemented system nor an accepted production design, and it does not select dependencies.

## Intended separation

1. **Public-source adapters** acquire only later-approved datasets through documented, replaceable interfaces.
2. **Raw local cache** holds immutable or pinned source material outside Git, accompanied by source manifests and checksums where practical.
3. **Normalized data** reconciles schemas, geography identifiers, vintages, types, missingness, and quality indicators.
4. **Feature engineering** derives documented, reviewable components without hiding scoring assumptions.
5. **Spatial analysis** performs joins, concentrations, continuity, seed-direction, displacement, and related complex GIS work upstream.
6. **Stable presentation outputs** expose versioned, tested tables and geographies with explicit contracts.
7. **Power BI** presents prepared results and light report logic; it does not become the system of record for complex spatial calculations.
8. **Confidential local overlays** join only in an ignored, controlled local path and remain separate from committed definitions and public outputs.
9. **Future proprietary adapters** may later augment or substitute approved public adapters without forcing presentation redesign.

## Cross-cutting boundaries

- Markets are configuration-driven. Milwaukee is the first intended pilot; it is not a reason to hard-code a Milwaukee-only application.
- Source adapters, transformations, output contracts, and presentation definitions should remain independently replaceable and reconstructable.
- Missing inputs, schema drift, incompatible vintages, or misleading joins should fail closed and produce actionable diagnostics.
- No cloud platform, database, API, orchestration framework, Fabric workspace, enterprise Power BI capacity, ArcGIS organization, or proprietary vendor is assumed.
- No custom HTML/JavaScript map is part of the MVP boundary unless later authorized.
- Dependency and platform evaluation belongs to later authorized implementation work.
