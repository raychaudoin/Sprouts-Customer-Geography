# GOV-16 — Governance Replacement and Two-Project Readiness Mailbox

## Purpose

Replace the current task-heavy operating wrapper with the owner-approved two-Project workflow and add a repository-safe Development Readiness Mailbox so Brainstorming can prepare future work against current local readiness without accessing the desktop repository or protected data.

This is a wholesale replacement, not another narrow governance patch.

Initiative Brief: GitHub Issue #44.

Canonical baseline at authorization: `e464d5ea2453d7387102d64154bb52f410b12670`.

## Core operating model

### Brainstorming Project

`Sprouts Customer Geography` is the cloud decision and prompt-authoring workspace.

Brainstorming owns:

- deciding the next substantive product/model objective with Ray;
- inspecting GitHub before authorizing new work;
- preparing the pathway needed for Development to complete that work;
- identifying prerequisites, permitted evidence, scope, exclusions, success criteria, and decisions reserved for Ray;
- writing the GitHub Initiative Brief and detailed Work Order;
- producing a very short Development launch message;
- reviewing the resulting PR/CI and safe local summary before deciding what comes next.

Brainstorming does not access the desktop repository or protected-local data.

### Development Project

`Sprouts-Customer-Geography-Development` is the repository-connected execution workspace.

Development owns:

- reading the Initiative Brief and Work Order;
- checking GitHub and the local repository before acting;
- validating that the prepared pathway actually exists locally;
- loading registered protected-local state when the Work Order permits it;
- implementing the exact approved objective;
- tests, bounded corrections, commits, pushes, and PR maintenance within that objective;
- writing repository-safe results and readiness back to GitHub.

Development has broad implementation discretion inside the prepared pathway, but it does **not** invent missing governance authority. If completion requires evidence, access, methodology, scope, or permissions not supplied by the Initiative Brief/Work Order, stop and report the precise gap rather than expanding authority.

## New two-way GitHub handoff

GitHub becomes the repository-safe intermediary in both directions.

### Brainstorming → Development

For meaningful work:

1. Brainstorming checks current GitHub state and Development Readiness Mailbox.
2. Ray and Brainstorming decide the objective.
3. Brainstorming writes one concise Initiative Brief Issue.
4. Brainstorming writes one detailed repository-safe Work Order.
5. Ray receives only a short launcher referencing those artifacts.

### Development → Brainstorming

After meaningful work, Development publishes:

1. PR/commit/CI evidence for repository-safe implementation;
2. a refreshed Development Readiness Mailbox containing only schema-approved, non-protected readiness facts;
3. a short safe completion summary for any decision-relevant local facts that cannot be published.

Brainstorming reads those GitHub artifacts before preparing the next initiative.

## Development Readiness Mailbox

Implement one standing repository-safe readiness snapshot that Development refreshes after meaningful local work and before returning control to Brainstorming.

The mailbox is not a task status cockpit. It is a safe capability/readiness snapshot.

### Brainstorming must be able to learn, without local access

At minimum publish safe statuses for:

- local repository readiness: clean / known-preserved-work / attention-needed;
- known local active initiative branches/worktrees by safe task/initiative identifier;
- whether uncommitted or unpushed repository-safe work exists, identified only by safe initiative/task identifier and high-level state;
- durable protected project profile: ready / stale / missing / invalid;
- protected asset catalog/registry: ready / stale / unresolved;
- original-source inventory: ready / incomplete / unresolved;
- evidence ledger: ready / incomplete / unresolved;
- MODEL-13 authority package: registered/recoverable status only;
- APP-01 protected input package: registered/recoverable status only;
- MODEL-14 local preservation state;
- MODEL-15 local preservation state;
- whether a fresh Development session has successfully recovered current project state without Ray;
- timestamp and repository commit against which the readiness snapshot was verified;
- safe prerequisites Brainstorming should account for before launching future work.

Do not publish protected filenames when revealing, paths, addresses, coordinates, SeedPointIDs, target values, row-level lineage, registry contents, credentials, protected artifact hashes if revealing, or anything from which protected locations/evidence could reasonably be reconstructed.

### Technical publication requirement

Do not rely on an AI free-form summary for safety.

Implement:

- a strict versioned readiness schema with an allowlist of publishable fields;
- a local readiness publisher that reads local repository state and the protected-local project profile/ledger;
- validation that rejects unknown fields and values matching prohibited disclosure classes;
- synthetic tests proving protected paths, coordinates, target-like values, row identities, and arbitrary extra fields cannot be published;
- one stable GitHub mailbox surface readable by Brainstorming.

Choose the simplest durable GitHub surface. A generated tracked file on an appropriate mailbox branch or another similarly stable repository-safe surface is acceptable. Do not pollute canonical source history with meaningless readiness commits if a dedicated mailbox branch provides a cleaner design. Document the choice and why.

The mailbox must make staleness obvious. Brainstorming must be able to tell when the snapshot was last refreshed and which GitHub/local baseline it represents.

## Protected-local project state

Implement one durable local project profile/ledger outside Git worktrees so Development sessions do not repeatedly lose asset pointers and evidence lineage.

Prefer the simplest local design that works with the existing project. Python standard-library SQLite plus a small local profile is acceptable and preferred over introducing a cloud service.

The protected-local state should support:

- authorized protected roots;
- stable logical asset IDs and recoverable asset locations;
- original workbook/source-generation inventory;
- physical-location reconciliation;
- state-qualified physical location × forecast vintage × target definition evidence units;
- source-row aliases and target revision lineage;
- evidence events distinguishing located, identity-read, machine-target-read, visible, analytically-used, validation-used, development-used, and disclosed;
- model/candidate genealogy;
- exact model-to-evidence membership;
- protected artifact registration;
- incident and backup/recovery state.

Original protected sources remain immutable. Avoid copying raw target values into the ledger unless technically necessary.

### Discovery/recovery

Recovery must use trusted registration, deterministic project layout, and safe metadata. Do not recursively open arbitrary JSON/Excel/protected outputs merely to discover what they are.

The normal system should recover the known project/protected root automatically from durable local configuration or deterministic project layout. An explicit override can exist for future relocation, but Ray must not be routinely asked to restore a path.

## Evidence semantics

The project must distinguish:

- asset located;
- identity fields read;
- target decoded by a machine;
- target visible to a human/model;
- target used analytically;
- target used for validation;
- target used for development/model decisions;
- protected information disclosed.

Machine reading alone does not automatically mean development consumption.

Migrate the existing MODEL-15 parser incident as:

- machine target read: possible/uncertain;
- visible: no evidence;
- analytically used: false;
- development used: false;
- disclosed: false.

Do not reopen real target files merely to make that migration entry.

## Governance constructs to retire for future work

The replacement should retire as mandatory operating machinery:

- Lane A / Lane B;
- universal task manifests for routine work;
- Issue-as-status-cockpit synchronization;
- permanent capability-acceptance/routing chats;
- exact-next-destination choreography;
- acceptance-only A commits;
- duplicate CI after metadata-only acceptance;
- task-lifecycle checkers that exist only to move status fields;
- per-worktree/session registry pointer restoration as normal operation.

Historical artifacts remain historical evidence and should not be rewritten merely for neatness.

## Safeguards to preserve

Do not weaken:

- protected/public disclosure boundary;
- source/vintage/schema/transformation provenance;
- explicit missingness/no silent zero-fill;
- target-blind feature/evaluation freezes;
- physical-location-grouped validation;
- reproducible deterministic runs;
- protected-field allowlists and egress controls;
- protected-characteristic restrictions;
- branches/PRs/CI/protected-main controls;
- exact final-version acceptance for consequential model/product decisions.

## Final-version approval model

For consequential decisions after cutover:

1. Development produces the final substantive commit.
2. CI runs on that exact commit.
3. Ray/reviewer accepts or rejects that exact commit.
4. Any subsequent substantive change invalidates the decision.
5. The unchanged accepted commit is merged.

No acceptance-record-only A commit is required.

Ordinary reversible implementation may proceed and, when expressly pre-authorized by Brainstorming, merge after CI without a separate Ray transition.

## Current work preservation

### MODEL-14

Keep frozen at `2759647ee814ac4d65dc3958e54277247288bacf` / PR #41. Do not modify, promote, or resume experimentation during GOV-16.

### MODEL-15

Before substantive GOV-16 implementation, inspect its local branch/worktree and preserve repository-safe uncommitted/unpushed work without opening protected evidence or resuming reconciliation/model execution.

Do not discard, reset, rewrite, merge, or analytically advance MODEL-15.

### MODEL-13 / APP-01 / PBI-02

- MODEL-13 remains the current accepted model pending MODEL-15 integrity reconciliation.
- APP-01 remains the usable dashboard baseline.
- PBI-02 remains untouched.

## Replacement instruction surfaces

Prepare final proposed text for coordinated cutover of:

- Brainstorming Project custom instructions;
- Development Project custom instructions;
- `AGENTS.md`;
- concise current operating-model documentation;
- protected-evidence/readiness documentation.

The new `AGENTS.md` must explicitly require Development to refresh the Development Readiness Mailbox after meaningful local work and before returning control to Brainstorming, and to validate the mailbox through the allowlisted publisher rather than free-form disclosure.

Brainstorming instructions must explicitly require reading the mailbox before preparing meaningful new work and treating an incomplete prerequisite as a Brainstorming runway-preparation problem rather than silently delegating it to Development.

## Validation

Use synthetic fixtures first.

At minimum prove:

- readiness schema accepts only approved fields;
- prohibited paths/coordinates/target-like values/row identity/unexpected fields are rejected;
- mailbox staleness is visible;
- fresh Development session can recover the project profile without Ray supplying paths;
- registered assets resolve without arbitrary protected-file scanning;
- path traversal/outside-root inputs fail safely;
- evidence events are auditable;
- model evidence membership can be queried;
- machine-target-read does not automatically become development-used;
- missing protected state blocks only the protected-dependent stage;
- existing MODEL-13/14 behavior is not changed by GOV-16.

Run relevant focused tests, repository confidentiality checks, analytical regression tests necessary to prove no behavior change, and normal CI.

## PR and stop point

Create one GOV-16 PR linked to Issue #44.

The PR should explain in plain English:

- what operating friction is being removed;
- how Brainstorming prepares the runway;
- how Development executes without inventing missing authority;
- what the Development Readiness Mailbox publishes;
- how protected-local recovery works;
- what safeguards remain;
- what analytical work was intentionally not resumed.

Stop at one final substantive PR head with passing CI.

Do not merge.

Do not resume MODEL-14 or MODEL-15 analytics.

Return a short completion report containing:

- final commit SHA and PR;
- CI result;
- readiness-mailbox design/location;
- proof the mailbox rejects protected/disallowed fields;
- fresh-session recovery result;
- confirmation MODEL-14 and MODEL-15 were preserved;
- confirmation no fresh targets were opened;
- final proposed Brainstorming and Development custom instructions;
- any material deviation from this Work Order.

The next step after Development completion is independent clean-room fidelity review and Ray's cutover decision.
