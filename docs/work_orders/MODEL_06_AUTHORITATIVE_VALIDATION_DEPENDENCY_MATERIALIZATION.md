# MODEL-06 authoritative validation dependency materialization

This work order records bounded implementation evidence for MODEL capability acceptance. It does not self-accept MODEL-06, authorize target access, execute the PIPE protected freeze, create predictions, fit a model, or authorize any later validation stage.

## Outcome

MODEL-06 materialized the two accepted MODEL-owned dependencies identified by PIPE-01A:

- protected `MODEL04_VALIDATION_IDENTITY_ROLE_ANCHOR_PACKAGE_V1` version `1.0.0`, held only outside Git under the authorized MODEL-06 protected root; and
- repository-safe `MODEL05_PROSPECTIVE_VALIDATION_PREREGISTRATION_V1` version `1.0.0`, canonically hash-bound to the accepted DATA/GEO authorities.

Repository evidence for MODEL-04 is limited to `MODEL04_VALIDATION_IDENTITY_ROLE_ANCHOR_COMMITMENT_V1` version `1.0.0`. It reuses the PIPE salted commitment domain and discloses neither the protected package digest nor nonce.

## Canonical mechanism reuse

- Canonical UTF-8 JSON and SHA-256 use `sprouts_customer_geography.pipe01.canonical`.
- Protected-package commitment uses `sprouts_customer_geography.pipe01.commitment` without a new domain, encoding, or salt design.
- Immutable correction behavior uses the existing `supersedes` convention; accepted artifacts are not overwritten.
- DATA-01 and GEO-02/03/04 artifacts are referenced by exact ID, version, hash, and operation fingerprint rather than copied.
- Existing PIPE protected-path safeguards now cover the MODEL-04 protected package and nonce filenames.

## Target-blind boundary

The dedicated workbook projection reader opens the expected `Sheet1` worksheet member, inspects headers, and materializes body columns A:I only. It does not use an Excel object model, evaluate formulas, load styles/comments/charts, or materialize body values from J onward. Any formula in A:I or inability to confirm targets outside A:I fails with `TARGET_BLIND_MATERIALIZATION_NOT_ENFORCEABLE`.

The protected package retains target-blind identity, role, observed-coordinate lineage, and canonical observed anchors. Ambiguity is quarantined and receives no anchor. No forecast target, prediction, distribution, rank, target-derived parameter, or performance result is created.

## Authority and next decision

The exact destination is `MODEL: Customer-Fit Proxy Decisions & Acceptance` for MODEL-06 capability acceptance review. A later PIPE freeze remains separately authorized and must bind the accepted artifacts; this work order does not authorize it.
