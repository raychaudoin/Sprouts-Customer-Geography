# PIPE-01 Pretarget Validation Freeze

## Scope and current state

PIPE-01 implements a repository-safe target-blind freeze package and synthetic conformance harness. It does not evaluate forecasts. Real seed/anchor evidence, memberships, distances, household totals, predictions, quarantine details, nonces, and complete freeze manifests remain outside Git.

The repository did not contain the accepted DATA-01, GEO-02/GEO-03, MODEL-04/MODEL-05 artifacts or the pinned TIGER/ACS source manifests when implementation began. DATA-02 subsequently materialized the public DATA configuration and pinned source manifests at `config/data/data01_validation_source_contract.json` and `data/manifests/`; GEO and MODEL dependencies remain absent. Therefore the real protected freeze is **blocked** and must not be described as frozen or ready. The implementation deliberately requires those exact identities and hashes instead of inferring them.

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

Tests use fictional identifiers and a synthetic coordinate transform. They prove calculation/control behavior, not the absent accepted GEO-03 operation or real market results.

## Confidentiality safeguards

`.gitignore` excludes common protected-run paths and artifacts. The independent tracked-path guard rejects designated protected artifact classes even if Git ignore rules are bypassed. Disclosure-safe reporting permits only aggregated states/counts and a salted commitment; it excludes coordinates, identities tied to locations, membership lists, distances, household totals, prediction values, targets, ranks, residuals, correlations, and target-based statistics.

## Blocked real-run facts

At PIPE-01 implementation time, no source bytes were downloaded and no accepted TIGER or ACS checksum was available. DATA-02 now pins public-source byte checksums without tracking raw downloads; the QA expectations of 452 Milwaukee tracts, 152 Madison tracts, and 604 total were not independently reproduced and remain unverified. No protected MODEL-04 input package or MODEL-05 preregistration artifact was available. No real protected run was started, no commitment exists, and no target-opening authorization is supported.
