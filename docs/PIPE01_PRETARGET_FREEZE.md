# PIPE-01 Pretarget Validation Freeze

## Scope and current state

PIPE-01 implements a repository-safe target-blind freeze package and conformance harness. PIPE-01B adds production-form public-source, spatial, protected-input, and orchestration adapters. It does not evaluate forecasts. Real seed/anchor evidence, memberships, distances, household totals, predictions, quarantine details, nonces, and complete freeze manifests remain outside Git.

The accepted repository-safe DATA-01/DATA-02, GEO-02/GEO-03/GEO-04, and MODEL-05 authorities are now committed. MODEL-04 remains protected-local by design, with only disclosure-safe commitment evidence in Git. The production path requires the exact accepted dependency preflight, checksum-pinned raw Census files, the protected MODEL-04 package and nonce, and an outside-repository protected output root. PIPE-01B implementation does not authorize or perform the real protected freeze.

## Stable contracts

The twelve JSON Schemas in `schemas/pipe01/` define:

- `source_manifest`
- `tract_inventory`
- `tract_internal_point_evidence`
- `context_membership`
- `context_spatial_evidence`
- `acs_b11001_evidence`
- `household_opportunity`
- `baseline_prediction`
- `eligibility_readiness`
- `run_manifest`
- `freeze_manifest`
- `conformance_report`

Schemas labeled protected-local describe contracts only. Real instances of those schemas are not repository-safe.

## Frozen calculation behavior

The implementation:

- preserves raw TIGER `INTPTLAT`/`INTPTLON` strings and parses coordinates without converting invalid states to zero;
- requires exact accepted EPSG:4269-to-EPSG:5070 operation evidence and passes coordinates to the operation as longitude, latitude;
- uses unrounded EPSG:5070 planar Euclidean distance and the exact comparison `distance <= radius` at 4,828.032, 8,046.72, and 11,265.408 metres;
- enforces nested memberships and one contribution per membership spec, GEO-02 context instance, radius, and GEOID;
- uses only GEO-02 anchor identity, records forced inclusion only when ordinary membership is not true, and confines the internal-point failure exception to a valid anchor tract;
- keeps non-anchor coordinate failures noncomputable;
- retains ACS B11001 estimate, MOE, annotation, status, and provenance separately;
- aggregates whole-tract final members once and refuses a complete total when potentially contributing membership or member ACS evidence is invalid;
- permits only an accepted MODEL-05 raw 5-mile whole-tract household-opportunity baseline with no invented coefficients or transforms; and
- preserves GEO-02 geometric completeness/Jaccard evidence instead of creating an internal-point membership Jaccard.

## Protected-local finalization

`ProtectedRun` rejects an output root located inside the repository. A run begins with an incomplete state and an opaque `prun-*` ID. Artifacts are written exclusively and target-like fields are rejected at the calculation/write interfaces. Finalization requires every accepted dependency identity, exact code/configuration identity, passing protected conformance, at least one artifact, and an explicit statement that sealed targets were not supplied.

Finalization writes the run manifest and protected freeze manifest, generates a random 32-byte nonce, and computes:

```text
SHA256(
  UTF8("sprouts-customer-geography/pipe01/freeze-commitment/v1")
  || 0x00
  || nonce_bytes
  || 0x00
  || bytes.fromhex(SHA256(canonical_protected_freeze_manifest_json))
)
```

The nonce and underlying protected manifest digest stay local. `FROZEN.json` is written last. Without that marker the run is incomplete. A run directory is never overwritten; corrections require a new opaque run ID and `supersedes` lineage.

## Required dependency package

The field contract is `config/pipe01/accepted_dependency_contract.json`. It requires exact accepted DATA-01 configuration identity/version/hash, GEO-02 context specification/hash, GEO-03 operation fingerprint/artifact hash, MODEL-04 package identity/version/hash, MODEL-05 model and preregistration identity/version/hash, pinned TIGER manifest/checksum and inventory-derivation identity, and exact ACS source/retrieval identities/hash.

Audit a protected-local dependency package without printing its values:

```powershell
$env:PYTHONPATH = "src"
python -m sprouts_customer_geography.pipe01 audit-dependencies --package C:\path\outside\repository\accepted-dependencies.json
Remove-Item Env:\PYTHONPATH
```

This audit establishes field presence only. PIPE must still verify that the supplied package is the accepted authoritative evidence.

## Repository-safe conformance

Run the synthetic suite and structural guard:

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -v
python scripts\check_pipe01_repository.py
Remove-Item Env:\PYTHONPATH
```

The normal suite uses fictional identifiers and synthetic geometry where source bytes are unnecessary. Supplying `PIPE01B_PINNED_TIGER_ZIP` and `PIPE01B_PINNED_ACS_B11001` also executes exact-source conformance and one completely fictional protected end-to-end run through the production orchestration path. The fictional anchor is a public TIGER tract internal point, not a real or perturbed Sprouts seed. The temporary run is removed after testing and no source bytes or protected artifacts are committed.

## Production-form execution boundary

`sprouts_customer_geography.pipe01.production` verifies and consumes the exact pinned Census source files. `sprouts_customer_geography.pipe01.orchestration` cross-validates every repository authority, verifies the protected MODEL-04 salted commitment, binds the accepted dependency preflight, instantiates contexts, executes GEO-03 and GEO-02, reuses existing PIPE calculations, stages protected artifacts, and finalizes immutably.

The CLI entry point is intentionally explicit and prints only disclosure-safe conformance evidence:

```powershell
$env:PYTHONPATH = "src"
python -m sprouts_customer_geography.pipe01 run-production `
  --repository C:\path\to\repository `
  --protected-root C:\authorized\outside-repository-root `
  --tiger-source-zip C:\local-public-source\tl_2024_55_tract.zip `
  --acs-source-file C:\local-public-source\acsdt5y2024-b11001.dat `
  --model04-package C:\protected\model04_identity_role_anchor_package.json `
  --model04-nonce C:\protected\commitment_nonce.bin `
  --model04-commitment-evidence C:\protected\model04_commitment.json `
  --accepted-dependency-preflight C:\protected\accepted_dependencies.json `
  --code-identity <exact-commit-or-immutable-code-identity>
Remove-Item Env:\PYTHONPATH
```

Do not run this command with real protected inputs without a separate explicit authorization. It has no target-input parameter and refuses target-derived fields at protected write/finalization boundaries.

## Confidentiality safeguards

`.gitignore` excludes common protected-run paths and artifacts. The independent tracked-path guard rejects designated protected artifact classes even if Git ignore rules are bypassed. Disclosure-safe reporting permits only aggregated states/counts and a salted commitment; it excludes coordinates, identities tied to locations, membership lists, distances, household totals, prediction values, targets, ranks, residuals, correlations, and target-based statistics.

## Real protected execution status

PIPE-01B conformance reproduced the accepted 452 Milwaukee and 152 Madison tract inventories from the exact pinned TIGER file and bound the exact ACS B11001 source. The real target-blind protected freeze later completed and was accepted. Its protected run, commitment, inputs, and execution evidence remain outside Git; target values did not become public or repository-visible. Later validation access remained separately governed, and this status does not imply target-opening authorization.
