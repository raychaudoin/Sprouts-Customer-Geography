# MODEL-10 Wisconsin successor identity and lineage

## Boundary

MODEL-10 materializes `MODEL10_WISCONSIN_COHORT_IDENTITY_LINEAGE_PACKAGE_V1` outside Git. It distinguishes exact successor source observations, successor physical locations, and supported immutable MODEL-04 physical-location linkage. The repository contains only the contract, schemas, mechanism, fictional tests, and a nondisclosing commitment record after a successful authorized protected run.

## Explicit protected execution

Supply the exact protected registry directly or through `MODEL10_AUTHORITY_REGISTRY`:

```powershell
python -m sprouts_customer_geography.model10 --repository-root . --registry <explicit-protected-registry>
```

With no registry, the command performs no filesystem discovery and returns a disclosure-safe blocker. The registry must cover every and only authorized successor source workbook handle, with protected expected observation counts, Wisconsin markets, and the complete 2024/2025/2026 vintage set.

## Target-blind and immutable behavior

The reader reuses the accepted MODEL-04 Sheet1 A:I projection and confirms target headers exist only outside it. It never materializes body values after column I. Identity is complete before any downstream MODEL-09 target binding exists. Output begins incomplete, writes the package and protected commitment material, and writes `READY.json` last. Run IDs are immutable; corrections require a patch version and explicit supersession.

The protected package retains the exact source market lineage for each observation. Because this is a complete statewide source and market labels can change between generations, market labels do not partition physical-location matching; MODEL-10 applies the accepted target-blind location rules within Wisconsin state.

## Conformance

```powershell
$env:PYTHONPATH = 'src'
python -m unittest tests.test_model10_identity_lineage -v
python scripts/check_model10_repository.py
Remove-Item Env:\PYTHONPATH
```

Fictional tests cover historical linkage preservation, changed row/Seed Point continuity, genuinely new classification, ambiguity quarantine, target-value invariance, Wisconsin/vintage completeness, explicit-handle containment, interruption, immutability, supersession, and disclosure safety.
