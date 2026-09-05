# Data Governance

## Classification

**Public data** is not automatically approved. Each source requires validation of permitted use, access, coverage, freshness, stability, reproducibility, rate limits, licensing, attribution, omissions, failure behavior, and refresh suitability.

**Confidential data** includes real seed points, live pursuits, internal direction, contacts, credentials, proprietary datasets, live Site Scanner databases, internal correspondence or documents, confidential exports, and revealing screenshots. It remains outside Git unless explicit approval states otherwise.

## Provenance and source-vintage pinning

Each accepted source must have a manifest or equivalent that records, as applicable: name; official location; access method; dataset and schema versions; release/vintage and retrieval date; geography vintage; license/terms and attribution; query/extraction parameters; checksums; omissions; lineage; refresh expectations; and fallback behavior. Transformations must retain source-vintage references and reconstructable lineage.

## Retention and Git boundary

Raw downloads, large caches, generated production exports, and confidential overlays remain in ignored local storage. Git should contain definitions needed to reproduce work—manifests, scripts, configuration, documentation, authorized small synthetic fixtures, and tests—not whole downloaded environments. Raw-data retention and deletion schedules must be defined per source in later work.

Deletion of discovered confidential or business records requires authorization. Do not delete, move, sanitize, or recommit protected material merely because it violates policy; isolate access, stop the affected operation, preserve evidence without exposing content, and report the incident.

## Repository-safe evidence surfaces

Treat GitHub Issues, pull requests, comments, checks, and both mailbox functions as public disclosure.

The Development Readiness Mailbox may publish only its versioned, allowlisted, closed-schema readiness values. The active Initiative/PR mailbox may carry only concise repository-safe Launch, Result, and Review chronology. Before a PR exists, the Initiative Issue may be active; once a PR exists, new candidate chronology belongs only in the PR conversation and is not mirrored to the Issue.

Neither mailbox may contain protected paths or revealing filenames, addresses, coordinates, row identities, targets, registry contents, credentials, revealing hashes, or reconstructable protected lineage. Mailbox records are evidence/coordination only; they cannot authorize access, analytical use, disclosure, merge, or acceptance.

## Synthetic fixtures

Committed fixtures must be small, clearly labeled synthetic or fictional, legally permissible, free of secrets and protected fields, and scoped to a meaningful test. Synthetic fixtures must not be reverse-engineered approximations of live pursuits.

## Secrets

Use documented environment variables or approved secret-management mechanisms. Provide safe example names without values when helpful. Never place secrets in Git, notebooks, logs, screenshots, reports, fixtures, command transcripts, or exception messages.

## Reproducibility and known gaps

Later pipelines must pin or record source vintages, inputs, schemas, configuration, and transformations; test reruns and interruptions; and make fallback behavior explicit. Known omissions, unavailable geography/year combinations, uncertainty, margins of error, stale inputs, and quality flags must survive into downstream contracts rather than being silently filled or discarded.

## Incident handling and approvals

If confidential material or a secret is found, fail closed: stop processing it, do not reveal or delete it, prevent further propagation, record only safe metadata, and notify Ray with the affected location and required decision. Approval is required before committing any real business data, even if it appears non-sensitive.
