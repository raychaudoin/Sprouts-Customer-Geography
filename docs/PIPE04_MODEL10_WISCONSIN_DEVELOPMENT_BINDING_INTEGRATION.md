# PIPE-04 MODEL-10 Wisconsin development binding integration

## Boundary

PIPE-04 materializes `PIPE04_MODEL10_WISCONSIN_DEVELOPMENT_BINDING_V1` outside Git. It verifies the exact accepted MODEL-10 commitment and protected package, freezes the complete MODEL-10-eligible Wisconsin cohort, and only then projects `Isolated Sales` through exact successor source-observation lineage. MODEL-10 physical-location identity, eligibility, quarantine, historical MODEL-04 linkage, source market, vintage, and prior evidence-role lineage are inputs that target content cannot change.

The implementation reuses the accepted PIPE canonical JSON, SHA-256, salted commitment, opaque-handle, protected-root containment, incomplete-first, immutable-run, final-marker-last, supersession, and disclosure-safe reporting controls. Protected paths, registries, workbooks, observations, values, nonces, digests, packages, and execution artifacts remain outside Git.

## Explicit protected execution

Supply the exact protected registry directly or through `PIPE04_AUTHORITY_REGISTRY`:

```powershell
python -m sprouts_customer_geography.pipe04 --repository-root . --registry <explicit-protected-registry>
```

With no registry, the command performs no filesystem discovery and returns a disclosure-safe blocker. A successful run writes an incomplete state first and `READY.json` last. Run IDs are immutable; corrections require a new patch version and explicit supersession.

## Projection and consumption

Only exact authorized successor rows decode successor join lineage, forecast vintage, and `Isolated Sales`. `Impacted Sales` is not an allowlisted column or decoder input. Non-Wisconsin, quarantined, ineligible, unrelated, unresolved, or conflicting rows fail closed or remain unread. Historical MODEL-04 source-row or Seed Point equality is never required.

Binding does not mark evidence consumed. MODEL-09 consumption occurs later only when a value influences authorized analytical development.

## Conformance

```powershell
$env:PYTHONPATH = 'src'
python -m unittest tests.test_pipe04_binding -v
python scripts/check_pipe04_repository.py
Remove-Item Env:\PYTHONPATH
```

Fictional tests cover exact MODEL-10 verification, complete eligible-cohort binding, successor-lineage changes, quarantine exclusion, optional historical linkage, Isolated Sales-only projection, Impacted Sales and non-Wisconsin denial, target invariance, exact handles, containment, interruption, immutability, supersession, final-marker order, disclosure safety, and tracked-path protection.
