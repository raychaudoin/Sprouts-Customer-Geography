# PBI-02 scripts

These scripts reconstruct and validate the governed PBI-02 successor project without placing protected or local-only inputs in tracked definitions.

- `build_semantic_model.py` writes the six-table TMDL model, one-to-one public-context relationship, presentation-scale metadata, and light DAX.
- `build_report.py` writes the four-page PBIR report, built-in Azure Maps configuration, inspector, tooltip, QA, and preserved evidence page.
- `build_project.py` runs both deterministic builders.
- `preflight.py` runs fail-closed validation against the exact accepted MODEL-13 and DATA-04 packages.
- `prepare_runtime.py` copies the tracked project to the ignored `powerbi/pbi01/runtime/pbi02-run/` surface and substitutes the three local source tokens only after preflight passes.
- `prepare_synthetic_model13_fixture.py` creates the explicitly fictional, noncomputable MODEL-13-only fixture used for synthetic validation. It is not valid evidence for exact-H real-data validation.

Run from the repository root. See `docs/pbi02/README.md` for input requirements, commands, disclosure boundaries, and the Desktop checklist.
