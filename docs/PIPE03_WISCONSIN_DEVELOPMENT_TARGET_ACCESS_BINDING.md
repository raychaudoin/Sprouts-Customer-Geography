# PIPE-03 Wisconsin development target access binding

## Boundary

PIPE-03 is a distinct protected-local successor contract for the authorized MODEL-09 Wisconsin development evidence boundary. It reuses the accepted PIPE canonical JSON, SHA-256, salted commitment, exclusive-write, opaque-handle, containment, incomplete-first, immutable-run, final-marker-last, supersession, and disclosure-safe reporting controls.

The authoritative protected output identity is `PIPE03_WISCONSIN_DEVELOPMENT_TARGET_ACCESS_BINDING_V1` version `1.0.0`. Real registry entries, paths, workbooks, identities, values, nonces, protected hashes, packages, and execution artifacts remain outside Git.

## Target-blind cohort before values

The complete eligible currently available Wisconsin cohort is derived only from the exact accepted MODEL-04 protected package. Eligible observations are nonquarantined Milwaukee or Madison records with complete physical-location, lineage, and vintage identity. Historical identity state, evidence role, market, and target-view state are preserved. Repeated vintages retain the same physical-location group. Ambiguous identity is excluded and remains quarantined.

Only after that cohort is immutable for the run does the XLSX projection resolve exact lineage/vintage rows and decode their numeric `Isolated Sales` payloads. Workbook values cannot affect cohort membership or physical-location identity. Unmatched rows and all unrelated columns are ignored without retaining their payloads; `Impacted Sales` is never an allowed field or decoder input.

## Explicit registry and execution

Supply the exact protected-local registry directly with `--registry` or the controlled `PIPE03_AUTHORITY_REGISTRY` environment variable:

```powershell
python -m sprouts_customer_geography.pipe03 --repository-root . --registry <explicit-protected-registry>
```

With no registry, the CLI returns a disclosure-safe blocker and performs no filesystem discovery. Successful stdout contains only package identity and aggregate conformance counts; it excludes protected paths, identities, values, workbook details, registries, nonces, and protected digests.

## Finalization and corrections

A run begins with `binding_state.json` in incomplete state. Finalization writes the protected package, manifest, nonce, and commitment evidence, then writes `READY.json` last. Without `READY.json`, the run is unusable. Run IDs cannot be reused. A correction requires a new package patch version, new opaque run ID, and explicit `supersedes` lineage.

## Conformance

Run the fictional suite and structural guard:

```powershell
$env:PYTHONPATH = 'src'
python -m unittest tests.test_pipe03_binding -v
python scripts/check_pipe03_repository.py
Remove-Item Env:\PYTHONPATH
```

The tests use only fictional protected identities and synthetic XLSX containers. They exercise Wisconsin acceptance, `Isolated Sales` access, `Impacted Sales` and non-Wisconsin denial, ambiguity quarantine, target-invariant identity/cohort selection, exact-handle resolution, containment, interruption, final-marker order, immutability, supersession, and disclosure safety.
