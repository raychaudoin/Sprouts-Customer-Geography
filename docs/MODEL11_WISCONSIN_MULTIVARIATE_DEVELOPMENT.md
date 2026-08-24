# MODEL-11 Wisconsin multivariate development

MODEL-11 uses a mandatory two-phase protected workflow. `freeze` constructs and finalizes the complete target-blind public feature package without resolving or reading PIPE-04. Only an exact READY freeze identity may be supplied to `develop`, which then reuses the accepted PIPE-04 Isolated Sales projection for the bounded nested grouped comparison.

No protected path is configured in the repository. Create one registry from exact authorized paths with `model11-bootstrap-registry`, or supply an already-created registry directly or through `MODEL11_AUTHORITY_REGISTRY`. The registry and all resources must be outside Git.

```powershell
python -m sprouts_customer_geography.model11 freeze --repository-root . --registry <exact-protected-registry> --freeze-run-id <opaque-freeze-id>
python -m sprouts_customer_geography.model11 develop --repository-root . --registry <exact-protected-registry> --feature-freeze-run-id <same-opaque-freeze-id> --development-run-id <opaque-development-id>
```

Both phases are immutable and incomplete-first with READY written last. A corrected target-conditioned run uses a new patch version, new opaque run identity, and explicit supersedes identity. The console emits disclosure-safe aggregate evidence only; target values, identities, locations, observation features, fold assignments, selected parameters, fitted coefficients, predictions, residuals, handles, paths, hashes, and reconstructable artifacts remain protected-local.

Conformance:

```powershell
$env:PYTHONPATH = 'src'
python -m unittest tests.test_model11_development -v
python scripts/check_model11_repository.py
Remove-Item Env:\PYTHONPATH
```
