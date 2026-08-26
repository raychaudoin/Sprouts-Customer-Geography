# MICustomerGeography source-controlled project

Power BI Desktop created the initial `MICustomerGeography` PBIP skeleton through its normal Save As Power BI Project flow. PBI-01 populated the accepted PBIR/TMDL baseline. PBI-02 reconstructs the governed successor map-first report in this same project; it does not create a second application.

This tracked folder contains definitions and public presentation geometry only. Its TMDL sources use `__PBI01_TRACT_CSV__`, `__PBI01_SEED_CSV__`, and `__PBI02_PUBLIC_CONTEXT_CSV__` placeholders. Run `python scripts\pbi02\build_project.py` to reconstruct the tracked project, then `python scripts\pbi02\prepare_runtime.py --replace --data04-root <accepted-data04-package-root>` to create an ignored local copy after fail-closed MODEL-13 and DATA-04 preflight.

Never add protected data, real DATA-04 tract rows, local paths, `.pbi` state, PBIX/PBIT binaries, raw request captures, or runtime screenshots here. See `docs/pbi02/README.md` for the complete operator and reconstruction guide.
