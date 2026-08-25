# PBI-01 scripts

These deterministic, repository-safe entry points reconstruct and validate the PBI-01 MVP:

- `preflight.py` fails closed unless the protected-local MODEL-13 contract, READY metadata, schemas, hashes, lineage, accounting, and tract/geometry join all match.
- `build_geometry.py` reconstructs the pinned public Michigan 2024 TIGER tract presentation geometry.
- `build_semantic_model.py` regenerates the TMDL model with protected-path tokens and light presentation measures only.
- `build_report.py` regenerates the three-page PBIR report and embeds the tracked public geometry.
- `prepare_runtime.py` creates an ignored Desktop runtime copy after preflight and substitutes protected absolute paths only there.

See `docs/pbi01/README.md` for the required order and operator workflow.
