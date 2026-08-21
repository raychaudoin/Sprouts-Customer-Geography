# PIPE-02 protected validation access binding

## Current accepted status

The real protected binding later completed and was accepted. Protected binding, registry, and package details remain outside Git. It supported only the bounded MODEL-07 Milwaukee temporal-validation access contract and did not authorize broader target access.

## Boundary

PIPE-02 creates one deterministic protected-local authority package for later MODEL-07 access. It binds the accepted MODEL-04 identity/role authority, the accepted MODEL-05 preregistration, the exact frozen PIPE-01 run, two independently governed validation-target workbook handles, the frozen Milwaukee temporal cohort, and the minimum target-cell projection. The exact target roles are `PRIOR_VINTAGE_TEMPORAL_SOURCE` and `2026_TEMPORAL_SOURCE`. It does not open a forecast value, perform validation analysis, authorize MODEL-07 resumption, or change an upstream frozen artifact.

The authoritative output is `PIPE02_PROTECTED_VALIDATION_ACCESS_BINDING_V1` version `1.0.0`. Real package content, handle registries, absolute paths, location identities, source rows, cell addresses, nonces, targets, and prediction values remain outside Git.

Because the one-source request shape was incompatible with the accepted authority boundary, the protected registry contract advances from `1.0.0` to `1.1.0` and the binding `$schema` advances to `pipe02-protected-validation-access-binding-v1.1`. The capability identity and authoritative package ID/version remain unchanged. The superseded one-source request is rejected rather than accepted through a permissive fallback.

## Reused protected framework

The implementation reuses PIPE-01 canonical JSON, SHA-256 helpers, salted commitment domain, exclusive writes, protected-root containment, final-marker-last behavior, and immutable supersession convention. It does not create another confidentiality or commitment framework.

A binding run starts with `binding_state.json` in `incomplete` state. Only after every reconciliation and projection check passes does it write the protected package, binding manifest, nonce, commitment evidence, and finally `READY.json`. Absence of `READY.json` means the run is not usable. A binding run ID can never be reused. A correction requires a new package version and opaque run ID with explicit `supersedes` lineage.

## Exact handle registry

The CLI consumes one explicitly supplied protected-local `PIPE02_PROTECTED_HANDLE_REGISTRY_V1` document. The resolver has no filename-search, glob, sibling-enumeration, or broad discovery operation. Every resource is an opaque `phandle-*` reference contained beneath an authorized `proot-*` root. The registry must bind exactly:

- the MODEL-04 protected package;
- the existing MODEL-04 verification material;
- the accepted PIPE-01 run directory;
- the authoritative prior-vintage temporal target workbook;
- the authoritative 2026 temporal target workbook; and
- the PIPE-02 protected output root.

Each target-source authority supplies its distinct role, opaque workbook handle, accepted provenance class, exact sheet, header row, three permitted columns, expected headers, lineage field, and role-specific vintage rule. The two roles and workbook handles must be exact, complete, unique, and independently resolvable. The prior source permits only `most_recent_eligible_prior`; the current source permits only `corresponding_2026`. PIPE-02 does not infer any of these from a filename and one workbook cannot implicitly satisfy both roles.

## Minimum projection and sealed-value reader

The default-deny projection permits only the frozen MODEL-04 Milwaukee `TEMPORAL_VALIDATION` repeated-location cohort. The cohort is established before workbook projection. For every location, the accepted MODEL-04 physical-location group determines the unique 2026 member and most recent unique prior-vintage member. Target workbook content cannot create, remove, regroup, quarantine, or reprioritize a cohort member.

The XLSX reader independently streams each exact authorized worksheet. It decodes only the three permitted headers plus lineage and forecast-vintage body cells. In the `Isolated Sales` body column it captures the cell address from the `<c>` element and deliberately does not retain or invoke the payload decoder for `<v>`/`<t>` content. String-backed target body cells fail closed because they could introduce shared-string payload risk. No whole-workbook digest is computed for either source. The final package retains two separate source authorities, two projection identities, and two zero-target-decode audits before pairing prior and current addresses by frozen MODEL-04 physical-location identity.

The protected package records only the most recent eligible prior-vintage and corresponding 2026 `Isolated Sales` addresses. Impacted Sales, prospective Milwaukee holdouts, Madison, ambiguous/quarantined rows, unrelated rows, unrelated columns, unknown fields, target values, and exploratory projections are denied.

## Execution

The registry must be supplied explicitly either with `--registry` or the controlled `PIPE02_AUTHORITY_REGISTRY` environment variable:

```powershell
python -m sprouts_customer_geography.pipe02 --repository-root . --registry <explicit-protected-registry>
```

If no authoritative registry is supplied, the CLI returns only a disclosure-safe blocker code and performs no discovery. A successful invocation prints package identity/hash and aggregate states only; it never prints paths, location identities, row/cell addresses, nonces, targets, or predictions.

## Conformance

`tests/test_pipe02_binding.py` uses genuinely fictional MODEL-04, PIPE-01, and XLSX structures. Its instrumented successful XLSX tests put sentinel payloads in each source's target cells and raise if either target decoder is invoked; target addresses still resolve. Other cases exercise exact commitments, artifact hashes, default-deny policy, handle-only resolution, containment, interruption, immutability, supersession, and disclosure safety.

The accepted single-workbook tests were intentionally migrated where their premise changed: handle-only resolution now proves two exact role-specific workbook handles; XLSX projection and nondecode tests execute once per role; the value-invariance test mutates both fictional workbooks independently; finalization fixtures retain two source authorities and audits; and the target-authority test now verifies exact role completeness, uniqueness, distinct handles, and role-specific policy. Controls unrelated to the defect remain unchanged.

Run:

```powershell
$env:PYTHONPATH = 'src'
python -m unittest tests.test_pipe02_binding -v
python scripts/check_pipe02_repository.py
Remove-Item Env:\PYTHONPATH
```

Outside-repository temporary directories are required for protected-run tests.
