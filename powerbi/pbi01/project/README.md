# MICustomerGeography source-controlled project

Power BI Desktop created the initial `MICustomerGeography` PBIP skeleton through its normal Save As Power BI Project flow. PBI-01 then populated its supported PBIR report and TMDL semantic-model definitions deterministically.

This tracked folder contains definitions only. The two TMDL import sources use `__PBI01_TRACT_CSV__` and `__PBI01_SEED_CSV__` placeholders. Run `scripts/pbi01/prepare_runtime.py --replace` to create an ignored local copy with protected paths substituted after fail-closed preflight. Never add protected data, `.pbi` state, a PBIX/PBIT, or runtime screenshots here.
