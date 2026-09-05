# Sprouts Customer Geography — Development Operating Standard

## 1. Purpose

This is the detailed repository-execution playbook for Development. `AGENTS.md` is the constitutional executor contract. This Operating Standard may elaborate that contract but may not contradict or override it.

Neither document stores volatile project state. Recover current commits, branches, Issues, pull requests, work status, mailbox state, blockers, model availability, and reasoning menus from current repository, GitHub, and validated mailbox evidence.

## 2. Authority and evidence hierarchy

Give each artifact one job:

- operative Work Order: canonical current execution authority;
- Initiative Brief: concise approved objective, boundaries, prerequisites, and Ray-reserved decisions;
- repository source, configuration, tests, and Git history: implemented technical truth;
- PR branch and head SHA: exact candidate identity;
- CI and tests: validation evidence;
- Development Readiness Mailbox: safe repository/local readiness evidence;
- active Issue/PR mailbox: chronological Launch/Result/Review evidence; and
- labels and status metadata: informational unless operative authority explicitly says otherwise.

No comment, PR description, check, label, or mailbox record can create or enlarge authority, accept work, authorize merge or protected action, or override the Work Order or repository truth.

## 3. Role boundary

Brainstorming prepares the pathway: objective, scope, prerequisites, evidence/access rules, methodology and product semantics, exclusions, success criteria, routine implementation authority, stop point, Ray-reserved decisions, and task-specific execution profile.

Brainstorming also owns the fresh full-suite comparison used to recommend that task-specific tool/model/reasoning profile. Development uses the supplied profile; it does not infer a substitute or embed a current model inventory in durable instructions.

Development implements that pathway. It may choose technical structure, wording, tests, bounded corrections, and routine repository mechanics that preserve approved meaning. It must not fill a runway gap by inventing evidence, access, methodology, scope, permissions, dependencies, analytical authority, deployment, publication, or product semantics.

When a real authority gap appears, stop only the dependent stage. Continue safe independent work when useful, then write a concise Result Record identifying the precise gap and safe completed state.

## 4. Preflight and recovery

Before meaningful changes:

1. read the exact Initiative Brief, operative Work Order, and latest applicable record from the active mailbox;
2. verify there is one coherent current authority set and distinguish historical evidence from operative authority;
3. read `README.md`, `AGENTS.md`, this Operating Standard, and referenced accepted contracts;
4. fetch and inspect current GitHub branch, PR, base, head, CI, and protected-main evidence;
5. inspect all linked worktrees and preserve unrelated uncommitted or unpushed work;
6. read the latest Development Readiness Mailbox, including timestamp and verified commit;
7. recover the protected-local profile/ledger only when the Work Order permits it; and
8. confirm that prerequisites for the first dependent stage are available or expressly deferred.

Use registered logical IDs and deterministic project layout for authorized protected recovery. Never discover protected state by recursively scanning arbitrary files, directories, spreadsheets, JSON, or outputs. An explicit relocation override is exceptional and does not become routine user-carried state.

## 5. Work preservation and Git posture

Use the authorized task-specific branch or an isolated worktree. Keep unrelated work intact. Do not force-push, destructively reset, delete user work, rebase, squash, merge, cherry-pick, or rewrite another initiative without explicit authority.

Routine in-scope recovery, tests, bounded mechanical correction, commits, pushes, and PR maintenance are implementation mechanics when the Work Order authorizes them. A transient test, CI, network, or tool failure is not a reason to invent new governance or create a Ray transition.

Before committing, review staged content. Before final return, review repository status, the complete diff, commit lineage, and push state. Check for unrelated files, large generated data, secrets, protected content, revealing metadata, and accidental caches or reports.

## 6. Public disclosure and protected-local handling

Treat all tracked and GitHub material as public. Do not place protected paths or revealing filenames, addresses, coordinates, row identities, targets, parameters, registry contents, credentials, revealing hashes, reconstructable lineage, or protected screenshots in repository or GitHub surfaces.

Use synthetic fixtures before authorized protected inputs. Keep original protected sources immutable. Resolve only registered logical assets beneath authorized roots; path traversal, outside-root resolution, and unresolved registrations fail closed. Keep protected values out of logs and exception text.

If protected material appears in a tracked or publishable surface, stop publication, preserve evidence without copying or deleting it, and report the risk through a safe channel. Do not sanitize, move, or destroy it without authority.

## 7. Evidence semantics

Record protected evidence events independently: asset located, identity read, target machine-read, target visible, analytically used, validation-used, development-used, and disclosed. One event does not promote another. Machine target reading alone does not imply human/model visibility, analytical use, validation use, or development use.

Maintain explicit model genealogy and exact evidence membership sufficient to determine which protected evidence influenced which model lineage. Do not put protected membership detail in public reports.

## 8. Data, geography, and analytical safeguards

Preserve accepted source/vintage/schema/transformation provenance and license/attribution records. Retain omissions, uncertainty, margins of error, quality flags, and missingness. Never silently convert missing data to zero, neutral, or favorable values.

Preserve target-blind feature and evaluation freezes, physical-location-grouped validation, deterministic reproduction, protected-field allowlists and egress controls, and protected-characteristic restrictions. Distinguish demographic fit from household mass and descriptive measures from modeled conclusions. Do not claim production readiness, operational authority, or proprietary-model equivalence without explicit accepted authority.

Perform reproducible public-data preparation and complex spatial analysis upstream. Keep protected adapters and inputs outside tracked source. Use configuration for later markets. New dependencies, cloud services, databases, APIs, orchestration, deployment, hosting, or publication require supplied authority.

## 9. Testing and bounded correction

Choose tests that demonstrate the authorized invariant. As relevant, cover schema/version compatibility, provenance, geography and joins, duplicates, missing/invalid inputs, uncertainty, stable output contracts, stale sources, interruption and reruns, deterministic output, path traversal, registered-asset containment, disclosure rejection, network egress, and fail-closed behavior.

Run focused tests during implementation, relevant regression/confidentiality checks before committing, and required repository validation on the final substantive head. Correct ordinary in-scope failures on the same branch and PR. Do not create ceremonial tests whose only purpose is to advance a lifecycle field.

## 10. Two mailbox functions

The two mailboxes serve different purposes and must not be conflated.

### Development Readiness Mailbox

This is the standing machine-generated capability/readiness snapshot on its dedicated branch. It publishes only closed-schema, allowlisted, disclosure-safe facts with a generation time and verified source commit. It is not task authority or candidate chronology.

Use only the repository publisher and validator. Never hand-edit the snapshot, add narrative, paste command output, or replace it with an AI summary. Unknown fields and prohibited disclosure classes fail closed.

### Active initiative/candidate mailbox

This is the GitHub conversation carrying chronological records. Before a PR exists, the Initiative Issue may be active. Once a PR exists, the PR conversation is the active candidate mailbox; new candidate chronology belongs only there and must not be mirrored to the Issue.

Brainstorming writes `LAUNCH`, Development writes `RESULT`, and independent review writes `REVIEW`. Follow the [Active Mailbox Record Guide](ACTIVE_MAILBOX_RECORDS.md). These records are concise evidence and coordination only.

## 11. Launch handling

Before meaningful Development or review work, read the latest applicable Launch Record and compare it with the Work Order and exact repository/GitHub state. A Launch Record identifies the intended action, role/surface, candidate, exclusions, execution profile, and expected control point, but it cannot enlarge the Work Order.

If launch text conflicts with operative authority, follow the authority hierarchy and stop the affected stage if the conflict is material.

## 12. Result Record

After meaningful implementation or remediation and before returning control, write a concise Result Record to the active mailbox. Once a PR exists, post it to the PR conversation only.

Identify the initiative/action performed, exact resulting PR/head, concise changed scope, validation and CI state, preserved safeguards/exclusions, any unresolved gap or deviation, and next control point. Keep local facts non-protected. The record is not acceptance or merge permission.

If the final head changes after a Result Record, post a new Result Record bound to the new head when returning again; do not edit history into an Issue cockpit.

## 13. Independent Review Record

When independent review is requested, review the exact base and candidate head, relevant diff, tests/CI, readiness baseline, and Work Order fidelity. Post a concise Review Record to the active PR mailbox with the review role/surface, exact PR/base/head, `PASS` or `REWORK REQUIRED`, material findings/deviations, safety/evidence concerns, and next control point.

A favorable Review Record is technical/fidelity evidence, not business acceptance or merge authority. A substantive candidate change invalidates review of the prior version when review remains required.

## 14. Readiness refresh procedure

Refresh the Development Readiness Mailbox after meaningful local work and immediately before final return if the source baseline changed:

1. ensure the source worktree is clean at the exact candidate commit;
2. synchronize and verify the clean dedicated mailbox worktree without reset or force-push;
3. run fresh-session recovery when required by the Work Order;
4. publish the closed snapshot from the exact source commit;
5. validate the snapshot, repository readiness checks, and focused synthetic suites;
6. inspect that only the root snapshot changed;
7. commit and validate the single-file mailbox refresh;
8. push the mailbox branch and require its validation workflow to pass; and
9. confirm the stable public snapshot reports the intended generation time and source commit.

Missing or incomplete protected readiness blocks only dependent protected stages. Do not fabricate `READY`. If safe publication fails, report the safe failure and last verified mailbox state rather than improvising a disclosure.

## 15. PR and candidate maintenance

Keep one implementation PR for the initiative. The PR body states the authorized objective and exclusions, exact final substantive commit, validation/CI, readiness snapshot and source baseline, safe preservation posture, deviations, review path, and merge posture.

Once the PR exists, use its conversation as the active candidate mailbox. Do not duplicate Launch/Result/Review chronology into the Initiative Issue. Update stale PR body evidence when the candidate changes; the body remains derivative evidence and cannot override the Work Order.

## 16. Exact-final-version lifecycle

For consequential model, methodology, or product decisions:

1. Development produces one final substantive candidate;
2. required validation and CI succeed on that exact candidate;
3. required independent review evaluates that exact candidate;
4. Ray or an explicitly delegated decision owner accepts or rejects that exact version;
5. later substantive change invalidates prior review or acceptance as applicable; and
6. only the unchanged accepted version may merge when authorized.

Do not create acceptance-only commits or rerun full CI solely for acceptance metadata. Green CI, a mailbox refresh, a Result/Review Record, labels, or PR state cannot create acceptance or merge authority.

## 17. Failure and remediation

Recover ordinary implementation failures within supplied authority. Preserve both sides of a non-fast-forward mailbox or PR conflict and reconcile safely; never force-push to discard another state.

Stop the dependent stage for missing governance authority, unauthorized fresh evidence, material methodology/product-semantic change, unresolved substantive evidence conflict, destructive action, deployment, publication, or genuine risk of losing user work.

In-scope review findings remain on the same initiative and PR unless authority says otherwise. Brainstorming writes a new Launch Record for bounded remediation, Development writes a new Result Record bound to the revised head, and independent review writes a new Review Record against that head.

## 18. Completion and user burden

Before returning control:

- ensure the exact final candidate and required CI are established;
- refresh and validate the readiness mailbox against that candidate;
- post the required Result Record to the active PR mailbox;
- preserve unrelated local work and protected-state boundaries; and
- stop at the Work Order endpoint without merging or beginning follow-on work unless expressly authorized.

Ray should normally carry only a short launcher between Projects. Brainstorming retrieves Result/Review Records and readiness evidence directly from GitHub when available. Do not require Ray to transport long reports, reconstruct chronology, restore recoverable paths, splice instruction fragments, or choose an execution profile that Brainstorming can recommend.

## 19. Retired machinery and drift

Do not recreate mandatory lanes, universal routine manifests or lifecycle state machines, synchronized Issue cockpits, permanent routing chats, exact-next-destination choreography, acceptance-only commits, duplicate acceptance-metadata CI, or routine per-session path restoration.

Treat repeated user-carried recovery, duplicated Issue/PR chronology, hard-coded current model inventory, Result/Review records acting as authority, or Development inventing runway as governance drift. Correct the workflow within supplied authority or return the precise gap to Brainstorming.
