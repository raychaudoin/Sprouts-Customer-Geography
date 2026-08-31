# Two-Project Operating Model

## Outcome

Sprouts Customer Geography uses two Projects with GitHub as a repository-safe mailbox between them. The model separates decision/runway preparation from local implementation while keeping Ray as the business decision-maker.

```text
Ray + Brainstorming
  decide objective and prepare complete runway
            |
            v
GitHub Initiative Brief + detailed Work Order
            |
            v
Development
  verifies local pathway, preserves work, implements, validates
            |
            v
PR + CI + refreshed Development Readiness Mailbox
            |
            v
Ray + Brainstorming
  review exact result and prepare any future runway
```

## Brainstorming

The cloud Project `Sprouts Customer Geography` owns:

- deciding the next substantive product/model objective with Ray;
- inspecting GitHub and the latest mailbox before authoring meaningful work;
- preparing prerequisites, permitted evidence/access, scope, exclusions, success criteria, and Ray-reserved decisions;
- writing one concise Initiative Brief Issue and one detailed repository-safe Work Order;
- sending a short launcher that points Development to those artifacts; and
- reviewing the PR, CI, refreshed mailbox, and short safe local summary.

Brainstorming cannot access the desktop repository or protected-local data. A missing prerequisite is its runway-preparation problem: authorize a bounded prerequisite, supply missing repository-safe authority, request a safe mailbox refresh, or defer the objective. Do not send Development an incomplete pathway and imply authority to fill it in.

## Development

The repository-connected Project `Sprouts-Customer-Geography-Development` owns:

- reading the Initiative Brief and Work Order first;
- inspecting current GitHub and local repository state;
- preserving active and uncommitted local work;
- verifying that the prepared pathway exists locally;
- recovering registered protected state when expressly permitted;
- implementing the exact objective with broad in-pathway discretion;
- tests, bounded corrections, commits, pushes, and PR maintenance; and
- returning safe results plus a validated mailbox refresh.

Development does not invent missing evidence, access, methodology, scope, permissions, or product semantics. It stops the dependent stage and reports the exact runway gap.

## GitHub handoff

Brainstorming sends authority through an Initiative Brief Issue and detailed Work Order. Development returns implementation evidence through a PR/CI, the standing mailbox, and a short non-protected local summary.

The Issue is a concise authority brief, not a synchronized task-status cockpit. The mailbox is a readiness snapshot, not an initiative registry. Historical manifests and lifecycle records remain historical evidence, but future routine work does not require a universal manifest or status mutation.

## Readiness refresh

After meaningful local work and before Development returns control, it must generate and validate the mailbox with the allowlisted publisher. Free-form AI disclosure and manual snapshot editing are prohibited. The snapshot exposes only schema-approved bounded statuses and safe initiative IDs, with refresh time and verified baseline so staleness is visible.

See the [mailbox runbook](DEVELOPMENT_READINESS_MAILBOX.md) for the publication and recovery contract.

## Final-version review

For consequential model or product decisions:

1. Development produces the final substantive commit.
2. CI passes on that exact commit.
3. Ray or the named reviewer accepts or rejects that exact commit.
4. Any substantive change invalidates the decision.
5. The unchanged accepted commit may merge through protected `main`.

No acceptance-only commit or duplicate metadata CI is required. Ordinary reversible implementation may merge after CI only when Brainstorming expressly pre-authorized it.

## Safeguards retained

The simpler wrapper does not weaken the public/protected boundary; source/vintage/schema/transformation provenance; explicit missingness; target-blind feature/evaluation freezes; physical-location-grouped validation; deterministic runs; protected-field allowlists and egress controls; protected-characteristic restrictions; branch/PR/CI/protected-main controls; or exact-final-version acceptance for consequential decisions.
