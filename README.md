# Sprouts Customer Geography

Sprouts Customer Geography is intended to help GBT understand the distribution, mass, continuity, and market context of likely Sprouts-oriented customer households. Milwaukee is the intended first pilot, with later markets handled through configuration rather than copied applications.

## Current status

This repository contains the governance foundation, the bounded PIPE-01/PIPE-01B target-blind freeze implementation, and the repository-safe PIPE-02 protected validation-access binding mechanism. Accepted repository-safe DATA, GEO, and MODEL authorities are materialized. PIPE-02 adds handle-only protected authority resolution, accepted freeze reconciliation, default-deny temporal target addressing, and sealed-value XLSX projection without validation analysis.

Local task execution is governed through repository-safe task manifests, validated naming/state rules, and future GitHub templates. The repository currently has no GitHub remote; GOV-02 documents the local workflow only.

Raw Census source bytes, MODEL-04 protected inputs, the accepted real PIPE-01 freeze, validation-target workbooks, and any PIPE-02 binding remain local-only and outside Git. No real seed-level output, sealed forecast target value, scoring model, validation result, deployment, or functioning Power BI report is contained here.

The intended design keeps reproducible public-data and spatial processing upstream and uses Power BI as a replaceable MVP presentation layer driven by stable outputs.

> **Confidentiality:** Do not commit live seed points, candidate sites, proprietary or internal data, credentials, contacts, confidential exports, or revealing screenshots. Use synthetic fixtures and ignored local overlays only as authorized.

## Repository guidance

- [Agent contract](AGENTS.md)
- [Project charter](docs/PROJECT_CHARTER.md)
- [Starting architecture](docs/ARCHITECTURE.md)
- [Data governance](docs/DATA_GOVERNANCE.md)
- [Active GOV-01 work order](docs/work_orders/ACTIVE_GOV_01_REPOSITORY_FOUNDATION.md)
- [Local GitHub workflow governance](docs/GITHUB_WORKFLOW_GOVERNANCE.md)
- [Data directory policy](data/README.md)
- [Market configuration boundary](config/markets/README.md)
- [Power BI boundary](powerbi/README.md)
- [PIPE-01 target-blind freeze runbook](docs/PIPE01_PRETARGET_FREEZE.md)
- [PIPE-01B implementation record](docs/work_orders/PIPE_01B_PRODUCTION_FREEZE_ADAPTERS_AND_ORCHESTRATION.md)
- [PIPE-02 protected binding runbook](docs/PIPE02_PROTECTED_VALIDATION_ACCESS_BINDING.md)
- [PIPE-02 implementation record](docs/work_orders/PIPE_02_PROTECTED_VALIDATION_ACCESS_BINDING.md)
