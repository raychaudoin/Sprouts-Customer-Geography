# PIPE-02 protected validation access binding

## Boundary

PIPE-02 creates one deterministic protected-local authority package for later MODEL-07 access. It binds the accepted MODEL-04 identity/role authority, the accepted MODEL-05 preregistration, the exact frozen PIPE-01 run, one already-authoritative validation-target workbook handle, the frozen Milwaukee temporal cohort, and the minimum target-cell projection. It does not open a forecast value, perform validation analysis, authorize MODEL-07 resumption, or change an upstream frozen artifact.

The authoritative output is `PIPE02_PROTECTED_VALIDATION_ACCESS_BINDING_V1` version `1.0.0`. Real package content, handle registries, absolute paths, location identities, source rows, cell addresses, nonces, targets, and prediction values remain outside Git.

## Reused protected framework

The implementation reuses PIPE-01 canonical JSON, SHA-256 helpers, salted commitment domain, exclusive writes, protected-root containment, final-marker-last behavior, and immutable supersession convention. It does not create another confidentiality or commitment framework.

A binding run starts with `binding_state.json` in `incomplete` state. Only after every reconciliation and projection check passes does it write the protected package, binding manifest, nonce, commitment evidence, and finally `READY.json`. Absence of `READY.json` means the run is not usable. A binding run ID can never be reused. A correction requires a new package version and opaque run ID with explicit `supersedes` lineage.

## Exact handle registry

The CLI consumes one explicitly supplied protected-local `PIPE02_PROTECTED_HANDLE_REGISTRY_V1` document. The resolver has no filename-search, glob, sibling-enumeration, or broad discovery operation. Every resource is an opaque `phandle-*` reference contained beneath an authorized `proot-*` root. The registry must bind exactly:

- the MODEL-04 protected package;
- the existing MODEL-04 verification material;
- the accepted PIPE-01 run directory;
- the authoritative target workbook; and
- the PIPE-02 protected output root.

The target-source authority also supplies its accepted provenance class and the exact sheet, header row, three permitted columns, expected headers, lineage field, and target year. PIPE-02 does not infer any of these from a filename.

## Minimum projection and sealed-value reader

The default-deny projection permits only the frozen MODEL-04 Milwaukee `TEMPORAL_VALIDATION` repeated-location cohort. The cohort is established before workbook projection. For every location, the accepted MODEL-04 physical-location group determines the unique 2026 member and most recent unique prior-vintage member. Target workbook content cannot create, remove, regroup, quarantine, or reprioritize a cohort member.

The XLSX reader streams the exact authorized worksheet. It decodes only the three permitted headers plus lineage and forecast-vintage body cells. In the `Isolated Sales` body column it captures the cell address from the `<c>` element and deliberately does not retain or invoke the payload decoder for `<v>`/`<t>` content. String-backed target body cells fail closed because they could introduce shared-string payload risk. No whole-workbook digest is computed.

The protected package records only the most recent eligible prior-vintage and corresponding 2026 `Isolated Sales` addresses. Impacted Sales, prospective Milwaukee holdouts, Madison, ambiguous/quarantined rows, unrelated rows, unrelated columns, unknown fields, target values, and exploratory projections are denied.

## Execution

The registry must be supplied explicitly either with `--registry` or the controlled `PIPE02_AUTHORITY_REGISTRY` environment variable:

```powershell
python -m sprouts_customer_geography.pipe02 --repository-root . --registry <explicit-protected-registry>
```

If no authoritative registry is supplied, the CLI returns only a disclosure-safe blocker code and performs no discovery. A successful invocation prints package identity/hash and aggregate states only; it never prints paths, location identities, row/cell addresses, nonces, targets, or predictions.

## Conformance

`tests/test_pipe02_binding.py` uses genuinely fictional MODEL-04, PIPE-01, and XLSX structures. Its instrumented successful XLSX test puts sentinel payloads in target cells and raises if the target decoder is invoked; target addresses still resolve. Other cases exercise exact commitments, artifact hashes, default-deny policy, handle-only resolution, containment, interruption, immutability, supersession, and disclosure safety.

Run:

```powershell
$env:PYTHONPATH = 'src'
python -m unittest tests.test_pipe02_binding -v
python scripts/check_pipe02_repository.py
Remove-Item Env:\PYTHONPATH
```

Outside-repository temporary directories are required for protected-run tests.
