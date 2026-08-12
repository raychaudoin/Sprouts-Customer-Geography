# Sprouts Customer Geography

Sprouts Customer Geography is intended to help GBT understand the distribution, mass, continuity, and market context of likely Sprouts-oriented customer households. Milwaukee is the intended first pilot, with later markets handled through configuration rather than copied applications.

## Current status

This repository contains governance and architecture foundations only. GOV-01 authorizes documentation and safe repository scaffolding; it does not authorize data ingestion, source downloads, demographic-variable selection, scoring, spatial analysis, Site Scanner integration, or creation of a functioning Power BI report. No scoring model or functioning MVP has been accepted.

The intended design keeps reproducible public-data and spatial processing upstream and uses Power BI as a replaceable MVP presentation layer driven by stable outputs.

> **Confidentiality:** Do not commit live seed points, candidate sites, proprietary or internal data, credentials, contacts, confidential exports, or revealing screenshots. Use synthetic fixtures and ignored local overlays only as authorized.

## Repository guidance

- [Agent contract](AGENTS.md)
- [Project charter](docs/PROJECT_CHARTER.md)
- [Starting architecture](docs/ARCHITECTURE.md)
- [Data governance](docs/DATA_GOVERNANCE.md)
- [Active GOV-01 work order](docs/work_orders/ACTIVE_GOV_01_REPOSITORY_FOUNDATION.md)
- [Data directory policy](data/README.md)
- [Market configuration boundary](config/markets/README.md)
- [Power BI boundary](powerbi/README.md)
