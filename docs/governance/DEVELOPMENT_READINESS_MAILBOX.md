# Development Readiness Mailbox and Protected-State Runbook

## Purpose and public surface

The Development Readiness Mailbox gives Brainstorming a bounded view of current local capability without granting desktop-repository or protected-data access. It is a standing readiness snapshot, not an initiative status cockpit and not a substitute for the Initiative Brief, Work Order, PR, CI, or a short safe completion summary.

The stable public surface is the root file `development-readiness.json` on the dedicated `readiness-mailbox` branch:

`https://raw.githubusercontent.com/raychaudoin/Sprouts-Customer-Geography/readiness-mailbox/development-readiness.json`

Keeping refresh commits on that dedicated branch avoids meaningless snapshot churn in canonical source history. The source schema is [`schemas/readiness/development_readiness.schema.json`](../../schemas/readiness/development_readiness.schema.json), currently version `1.0.0` with standing identity `development-readiness-v1`.

## Safety contract

Only the allowlisted publisher may write the snapshot. Do not hand-edit it, generate it from an AI free-form summary, paste command output into it, or add narrative fields.

The publisher constructs a closed document, binds it to the versioned schema, rejects unknown fields, and scans every value for prohibited disclosure classes before atomic replacement. It rejects paths and path traversal, addresses/coordinates, target-like values, row identities, arbitrary free text/numbers/booleans, revealing digests outside the exact repository-commit field, and unexpected fields.

The mailbox may contain only:

- `schema_version`, `snapshot_id`, and `generated_at_utc`;
- repository `verified_commit`, aggregate `worktree_state`, safe initiative IDs, and bounded worktree/push/work states;
- bounded protected-state readiness for the project profile, asset catalog, original-source inventory, evidence ledger, MODEL-13 authority package, and APP-01 protected inputs;
- bounded MODEL-14 and MODEL-15 preservation states;
- fresh-session recovery status; and
- allowlisted prerequisite codes with `READY`, `NEEDS_RUNWAY`, `BLOCKED`, or `NOT_APPLICABLE` status.

The snapshot must never contain raw worktree output, local or protected paths, revealing filenames, branch slugs beyond safe initiative IDs, Git status lines, addresses, coordinates, SeedPointIDs or other row identities, target values, source/registry contents, credentials, protected hashes, exception contents, or reconstructable protected lineage.

The bounded status vocabulary is:

| Area | Published values |
| --- | --- |
| Repository and active worktree state | `CLEAN`, `KNOWN_PRESERVED_WORK`, `ATTENTION_NEEDED` |
| Active push state | `SYNCHRONIZED`, `UNPUSHED_SAFE_WORK`, `UNKNOWN` |
| Safe local work | `UNCOMMITTED`, `UNPUSHED`, `UNCOMMITTED_AND_UNPUSHED`, `PRESERVED` |
| Project profile | `READY`, `STALE`, `MISSING`, `INVALID` |
| Asset catalog | `READY`, `STALE`, `UNRESOLVED` |
| Original-source inventory and evidence ledger | `READY`, `INCOMPLETE`, `UNRESOLVED` |
| MODEL-13 authority and APP-01 input registration | `REGISTERED_RECOVERABLE`, `REGISTERED_UNRECOVERABLE`, `UNREGISTERED`, `NOT_VERIFIED` |
| MODEL-14 / MODEL-15 preservation | `PRESERVED`, `ATTENTION_NEEDED`, `NOT_VERIFIED` |
| Fresh-session recovery | `SUCCEEDED`, `FAILED`, `NOT_VERIFIED` |
| Prerequisite status | `READY`, `NEEDS_RUNWAY`, `BLOCKED`, `NOT_APPLICABLE` |

The only prerequisite codes are `REPOSITORY_READINESS`, `PROTECTED_PROJECT_PROFILE`, `PROTECTED_ASSET_CATALOG`, `ORIGINAL_SOURCE_INVENTORY`, `EVIDENCE_LEDGER`, `MODEL13_AUTHORITY`, `APP01_INPUT_PACKAGE`, `MODEL14_PRESERVATION`, `MODEL15_PRESERVATION`, and `FRESH_SESSION_RECOVERY`.

## Staleness and interpretation

Brainstorming must inspect both `generated_at_utc` and `repository.verified_commit`. A snapshot whose timestamp or commit predates relevant repository activity is stale. `repository.worktree_state` distinguishes `CLEAN`, `KNOWN_PRESERVED_WORK`, and `ATTENTION_NEEDED`; active/safe work identifies only safe initiative IDs and bounded states.

The `prerequisites` array is the handoff contract for future runway. `NEEDS_RUNWAY` means Brainstorming must prepare or expressly defer that prerequisite before authorizing a dependent stage. It does not authorize Development to fill the gap. Missing or invalid protected state blocks only protected-dependent stages; repository-only work may remain ready.

`REGISTERED_RECOVERABLE` means that Development verified a trusted logical registration. It does not reveal the asset, prove analytical suitability beyond existing authority, or authorize access.

## Durable protected-local project state

The profile and SQLite evidence ledger live outside all Git worktrees. Normal recovery uses the deterministic machine-local root:

- Windows: `%LOCALAPPDATA%\SproutsCustomerGeography\ProjectState`
- Linux with `XDG_STATE_HOME`: `$XDG_STATE_HOME/sprouts-customer-geography`
- other supported environments: the platform's user-local state location

`SCG_PROJECT_STATE_HOME` is the explicit relocation override. It should be set only when the project state has intentionally moved; Ray should not be routinely asked to supply protected paths.

On POSIX systems the state directory is owner-only (`0700`) and the profile/ledger are owner-read/write (`0600`). On Windows the deterministic location inherits the signed-in user's local-profile ACL; the files are never placed in a repository worktree. The repository safeguard rejects the profile, ledger, copies, journals, WAL/SHM sidecars, and deterministic state-directory names without echoing the detected path.

The profile has a fixed project identity and points to the colocated versioned SQLite ledger. The ledger records authorized roots, logical asset registrations, original-source inventory, physical locations and evidence units, source-row aliases/revisions, independent evidence events, model genealogy and exact evidence membership, protected artifact registrations, incidents, backups/recovery, and initiative preservation. It should not store raw target values unless a later Work Order establishes a technical need and authority.

Original protected sources remain immutable. Registered assets resolve only by stable logical ID and an exact relative location beneath an authorized root. Absolute asset paths, traversal, outside-root resolution, and unresolved `ready` registrations fail closed. Discovery must never recursively scan arbitrary JSON, spreadsheets, directories, or outputs.

`READY` for original-source inventory or evidence-ledger completeness requires an explicit durable completeness posture as well as valid registered rows. Mere non-emptiness never promotes a partial inventory to ready. Existing ledger versions and table shapes are verified as-is; initialization never relabels or repairs an unknown schema without an authorized migration.

## One-time trusted bootstrap and normal recovery

Bootstrap is needed only when the durable state does not yet exist or an authorized relocation requires rebuilding its registration. From the repository root:

```powershell
python -m sprouts_customer_geography.readiness bootstrap --repository-root .
```

By default this reads the one trusted ignored APP-01 local settings registration. An explicitly authorized alternate uses `--settings <trusted-settings-file>`; relocation uses `--state-root <durable-state-root>` or `SCG_PROJECT_STATE_HOME`. Bootstrap requires exactly one registered MODEL-13 package candidate and reads no candidate package contents. It performs no filesystem search.

Bootstrap also records the authorized MODEL-15 parser incident without reopening target files:

- `machine_target_read = uncertain`;
- `visible = false`;
- `analytically_used = false`;
- `development_used = false`; and
- `disclosed = false`.

Normal sessions recover the profile without a path from Ray:

```powershell
python -m sprouts_customer_geography.readiness verify
```

The command verifies the profile identity, ledger schema version/shape, SQLite integrity, and exact repository baseline and returns only safe status JSON. A successful no-`--state-root` invocation records fresh-session proof for that exact commit; merely loading state during publication does not. An explicit `--state-root` can diagnose an authorized relocation but does not claim path-free fresh-session recovery. The command never prints the state root or asset paths. Registered assets are later resolved by logical ID through the store interface; arbitrary discovery is not available.

## Evidence-event semantics

The ledger recognizes independent event types:

- `asset_located`;
- `identity_read`;
- `machine_target_read`;
- `visible`;
- `analytically_used`;
- `validation_used`;
- `development_used`; and
- `disclosed`.

Each event records `true`, `false`, or `uncertain` plus a bounded detail code. Recording one event never auto-creates another. In particular, machine decoding alone does not imply human/model visibility, analytical use, validation use, development use, or disclosure. Model-to-evidence membership is explicit and queryable by logical model and evidence-unit IDs.

## Refresh and publish procedure

Refresh after any meaningful local work and again immediately before returning control to Brainstorming if the repository/local baseline changed. Publish from the final Development branch commit, after focused validation, so `repository.verified_commit` identifies the exact implementation baseline.

1. Confirm the source worktree and the dedicated `readiness-mailbox` worktree are preserved, current, and free of unrelated changes. The mailbox worktree must belong to the same Git repository, be on the exact `readiness-mailbox` branch, and match its remote baseline when that remote exists. Do not overwrite a dirty or diverged mailbox worktree.
2. From the source repository, run the allowlisted publisher, writing only the dedicated branch's root snapshot:

   ```powershell
   python -m sprouts_customer_geography.readiness publish --repository-root . --output <mailbox-worktree>\development-readiness.json
   ```

   The publisher probes linked worktrees plus unpushed local task refs internally but emits only closed-family initiative IDs and sanitized states. It requires the source worktree to be clean at the reported commit, refuses arbitrary output locations, and writes only the dedicated worktree's root snapshot. Before writing, it verifies that the mailbox schema, actual-file checker, workflow, and validation runtime are byte-identical Git blobs to the reported source commit.

3. Validate the generated file, then run the repository checker and focused synthetic tests:

   ```powershell
   python -m sprouts_customer_geography.readiness validate --repository-root . --input <mailbox-worktree>\development-readiness.json
   python scripts/check_readiness_repository.py
   python -m unittest tests.test_readiness_disclosure tests.test_readiness_repository tests.test_readiness_store tests.test_readiness_publisher -v
   ```

4. Inspect the mailbox-worktree diff. It must change only `development-readiness.json`, contain exactly the schema allowlist, and name the intended source commit and refresh time.
5. Commit that one generated regular file on `readiness-mailbox` with a concise mailbox-refresh message. From that worktree, run `python scripts/check_readiness_mailbox.py`; it validates the actual raw file, exact `100644` Git mode, exact root location, source-commit existence, enforcement-runtime binding, and single-file refresh commit.
6. Push the branch. The `Readiness Mailbox Validation` workflow repeats the actual-file and commit-scope checks on every mailbox push. If the push is not fast-forward, preserve both states, inspect the remote refresh, and retry without reset or force-push.
7. Read the stable raw URL and confirm that GitHub serves the new `generated_at_utc` and `verified_commit`. Link that surface and the passing mailbox check from the completion report.

The publisher can safely produce repository readiness when protected-local state is missing or invalid; affected protected fields and prerequisites become bounded missing/unresolved/needs-runway states. Do not fabricate `READY` values to make a launch proceed.

### Mailbox enforcement maintenance

Ordinary refreshes may change only `development-readiness.json`. If a later reviewed source commit changes any fixed mailbox enforcement file, the publisher fails with `READINESS_MAILBOX_ENFORCEMENT_STALE`; do not bypass that check.

A separately authorized maintenance sync may copy only the exact paths listed in `readiness.mailbox_contract.MAILBOX_ENFORCEMENT_PATHS` from the reviewed source commit. Commit those exact blobs on `readiness-mailbox` with the trailer `Readiness-Source-Commit: <40-hex-source-commit>`. The actual-mailbox checker recognizes this bounded maintenance mode, requires every enforcement blob to equal that source commit, and still validates the existing snapshot. Push only after the local maintenance check passes; then require the `Readiness Mailbox Validation` workflow to pass before generating the next snapshot. Schema-incompatible maintenance needs its own Work Order and coordinated snapshot-version migration.

## Failure handling

- **Disclosure/schema rejection:** do not weaken the validator or manually edit the JSON. Correct the local source fact or publisher mapping within current authority, rerun tests, and republish.
- **Missing/stale protected registration:** continue repository-only work if authorized, but block the dependent protected stage and publish `NEEDS_RUNWAY`.
- **Recovery failure:** preserve the state root; do not recreate, scan, or overwrite it reflexively. Report the safe failure code and let Brainstorming prepare any repair authority.
- **Mailbox branch conflict:** do not force-push or discard another refresh. Reconcile the repository-safe snapshots and publish a new validated snapshot.
- **Suspected disclosure:** stop publication, preserve evidence without copying it, and report the risk. Never paste the rejected value into GitHub or a completion report.

## Validation evidence

The synthetic readiness suites prove that the schema is closed; prohibited paths, traversal, coordinates, targets, row identities, hashes, arbitrary values, and extra fields are rejected; timestamp/commit staleness metadata is enforced; fresh sessions recover without Ray supplying paths; exact registered assets resolve without scanning; outside-root/traversal inputs fail; evidence events and model membership are auditable; machine-target-read does not imply development use; and absent protected state does not block the repository-only probe.
