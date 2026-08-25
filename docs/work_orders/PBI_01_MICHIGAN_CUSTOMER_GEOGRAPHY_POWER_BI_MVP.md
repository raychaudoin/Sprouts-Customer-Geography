# PBI-01: Michigan Customer Geography Power BI MVP

## Authority and current stopping boundary

Master Control Room authorized this Lane B task from canonical `main` commit `a7ee04bb6cd9710fa161858f0b5b2559565cfc9f`. Exact substantive H, when later authorized and completed, is accepted or rejected by `PBI: Power BI Decisions & Acceptance`.

This initial step is bootstrap only. It creates the governed workspace and a manual Power BI Desktop handoff, then stops. It does not authorize hand-authoring a PBIP skeleton, saving a blank report for Ray, accessing protected MODEL-13 row content, implementing the dashboard, creating substantive H or A, opening a pull request, merging, publishing, deploying, or using Power BI Service or Fabric.

MODEL-13 and all accepted predecessors remain closed authority. The presentation boundary is `MODEL13_MICHIGAN_POWER_BI_OUTPUT_CONTRACT_V1`: the tract output, seed-context output, and metadata remain protected-local and untracked.

## Repository-safe workspace convention

The task uses one branch, one manifest, and this one controlling work order.

Tracked source-controlled surfaces are:

- `powerbi/pbi01/project/` for the Power BI Desktop-created `.pbip`, report, and semantic-model definitions;
- `powerbi/pbi01/presentation/` for later deterministic presentation-geometry definitions and their generator;
- `scripts/pbi01/` for later task-scoped deterministic scripts;
- `tests/pbi01/` for later task-scoped tests; and
- `docs/pbi01/` for task-scoped operator and reconstruction documentation.

Ignored-local surfaces are:

- `powerbi/pbi01/local/model13/tract/` for the protected tract input;
- `powerbi/pbi01/local/model13/seed-context/` for the protected seed-context input;
- `powerbi/pbi01/local/model13/metadata/` for protected MODEL-13 metadata;
- `powerbi/pbi01/local/staging/` for any other protected-local staging;
- `powerbi/pbi01/runtime/` for local PBIX or other binary runtime artifacts; and
- Power BI-generated `.pbi/localSettings.json`, `.pbi/cache.abf`, autosave, and local-settings files covered by the repository ignore rules.

The ignored-local folders are storage conventions only. Bootstrap does not locate, inspect, copy, or move protected rows into them.

## Desktop-owned initial project skeleton

Power BI Desktop must create the initial skeleton through its normal **File > Save As > Power BI Project (.pbip)** flow. The repository-relative save folder is `powerbi/pbi01/project/`, and the exact project/report name is `MICustomerGeography`.

The required preview settings are **Power BI Project (.pbip) save option**, **Store reports using enhanced metadata format (PBIR)**, and **Store semantic model using TMDL format**. After the settings are enabled and Desktop has been restarted, Ray creates a new blank report and saves it once to the specified folder and name. Codex must not fabricate the Desktop-owned project structure.

## Bootstrap stop

After the directory, ignore, Desktop-capability, and handoff checks are complete, PBI-01 remains `IN_PROGRESS`. The next step is Ray's one-time Desktop save. No dashboard work begins until the resulting Desktop-created PBIP skeleton is present in this same worktree.
