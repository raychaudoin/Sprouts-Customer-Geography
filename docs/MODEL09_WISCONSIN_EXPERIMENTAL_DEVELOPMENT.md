# MODEL-09 Wisconsin experimental development

MODEL-09 consumes the accepted protected PIPE-04 READY binding only through an explicit protected registry. It joins fixed target-blind MODEL-10 canonical anchors to checksum-pinned ACS 2024 B11001 and TIGER 2024 tract evidence, constructs complete-cohort public household-geography features, and runs the bounded comparison in `MODEL09_WISCONSIN_EXPERIMENTAL_MODEL_CONTRACT_V1`.

No protected path is configured in the repository. Supply the exact registry explicitly or through `MODEL09_AUTHORITY_REGISTRY`:

```powershell
python -m sprouts_customer_geography.model09 --repository-root . --registry <explicit-protected-registry>
```

The registry resolves only opaque handles beneath authorized roots. Successful execution creates an immutable incomplete-first protected run and writes `READY.json` last. A correction requires a new patch version, run identity, and explicit supersedes lineage.

Console output is disclosure-safe aggregate development evidence only. Targets, coordinates, identities, features, fitted coefficients, observation predictions/residuals, fold assignments, commitments, and protected artifact identities remain outside Git and GitHub.

Conformance:

```powershell
$env:PYTHONPATH = 'src'
python -m unittest tests.test_model09_development -v
python scripts/check_model09_repository.py
Remove-Item Env:\PYTHONPATH
```
