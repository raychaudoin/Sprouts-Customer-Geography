# Two-Project Operating Model

## Outcome

Sprouts Customer Geography separates decision/runway preparation from repository-connected implementation while keeping Ray as the business decision-maker. GitHub carries repository-safe authority and evidence between Brainstorming and Development.

```text
Ray + Brainstorming
  decide objective, prepare runway, write Work Order + LAUNCH
                         |
                         v
     Initiative Issue until a PR exists
                         |
                         v
Development ----> PR conversation: RESULT ----> Independent review: REVIEW
     |                   ^
     |                   |  candidate chronology stays here
     v
Development Readiness Mailbox
  separate closed-schema capability snapshot
```

The two GitHub mailbox functions are deliberately separate. Neither is an alternate authority system.

## Four durable instruction surfaces

Brainstorming uses:

1. Brainstorming Project Custom Instructions as its constitutional layer; and
2. the Brainstorming Operating Standard as its detailed playbook.

Development uses:

1. `AGENTS.md` as its repository constitutional executor contract; and
2. the Development Operating Standard as its detailed repository-execution playbook.

The Development Project has no ChatGPT Project Custom Instructions. Each Operating Standard may elaborate but cannot override its constitutional layer. Durable instruction surfaces exclude volatile commits, PR/Issue numbers, task state, branch names, blockers, mailbox state, and current model/reasoning inventory.

## Brainstorming

The cloud Project owns product/model decisions with Ray, governance meaning, runway preparation, authority/evidence boundaries, Initiative Brief and Work Order authoring, Launch Records, short user launchers, dynamic execution-profile recommendations, and interpretation of durable Result/Review evidence.

Before meaningful work, Brainstorming reads current repository/GitHub evidence, the active mailbox chronology, and the latest validated readiness snapshot. It prepares prerequisites, permitted evidence/access, scope, exclusions, success criteria, routine implementation authority, stop point, Ray-reserved decisions, and a task-specific execution profile.

Brainstorming cannot access the desktop repository or protected-local data. A missing prerequisite is its runway-preparation problem. It must prepare or separately authorize the prerequisite, obtain Ray's decision, or defer the dependent objective rather than imply authority for Development to invent a workaround.

## Development

The repository-connected Project reads the Initiative Brief, operative Work Order, and latest applicable Launch Record first. It then inspects GitHub and local state, preserves active work, reconciles referenced accepted authority, verifies the prepared pathway, implements within scope, runs tests and CI, maintains the existing branch/PR, refreshes readiness, and writes a Result Record.

Development has broad technical discretion inside the supplied pathway. It does not invent missing evidence, access, methodology, scope, permissions, product semantics, analytical authority, dependencies, deployment, publication, or destructive-action authority. It stops only the dependent stage when such a gap is real and reports the precise gap through the active mailbox.

## Development Readiness Mailbox

The Development Readiness Mailbox answers: “What repository/local capabilities and prerequisites are safely known to be ready?”

It is a standing machine-generated, closed-schema snapshot on its dedicated branch. It exposes only allowlisted bounded facts, generation time, and verified source baseline. It is not task authority and not candidate chronology. Development refreshes it through the approved publisher and validator after meaningful local work and before final return.

See the [Development Readiness Mailbox runbook](DEVELOPMENT_READINESS_MAILBOX.md).

## Active initiative/candidate mailbox

The active mailbox answers: “What happened most recently, by which role, against which candidate, and what control point comes next?”

Before a PR exists, the Initiative Issue may carry concise chronology. Once a PR exists, the PR conversation becomes the active candidate mailbox; new candidate chronology is not mirrored to the Issue.

- Brainstorming writes `LAUNCH` before meaningful Development or review work.
- Development writes `RESULT` after meaningful implementation or remediation and before returning control.
- Independent review writes `REVIEW` against the exact candidate reviewed.

These concise records are evidence and coordination only. They cannot create or enlarge authority, accept work, authorize merge or protected action, or override the Work Order or repository truth. See the [Active Mailbox Record Guide](ACTIVE_MAILBOX_RECORDS.md).

## Dynamic execution profile

Brainstorming performs a fresh, full-suite comparison of the current Pro-eligible options for the intended surface before each meaningful Development or review launch. It recommends the lightest adequate current tool/model/reasoning profile only after considering task complexity, ambiguity, error consequence, coding depth, research/tool burden, reasoning horizon, duration, latency, cost, and reliability.

Durable governance contains no current model inventory or reasoning menu. Task-specific Work Orders, Launch Records, and launchers carry the current recommendation and rationale. Model choice never enlarges authority.

## Exact-final-version review

Consequential model, methodology, and product decisions follow this sequence:

1. Development produces the final substantive commit.
2. Required validation and CI pass on that exact commit.
3. Independent review evaluates that exact commit when required.
4. Ray or an explicitly delegated decision owner accepts or rejects that exact version.
5. A substantive change invalidates prior review or acceptance as applicable.
6. Only the unchanged accepted version may merge when authorized.

There is no acceptance-only commit and no duplicate full CI solely for acceptance metadata. Passing CI, a mailbox snapshot, or a favorable Result/Review Record is not acceptance or merge authority.

## Safeguards retained

The operating model preserves the public/protected boundary; source/vintage/schema/transformation provenance; explicit missingness; target-blind feature/evaluation freezes; physical-location-grouped validation; deterministic reproduction; protected-field allowlists and egress controls; protected-characteristic restrictions; independent evidence-event semantics; exact model-to-evidence membership; branch/PR/CI/protected-main controls; and Git safety against loss of user work.

It does not reintroduce lanes, universal routine manifests or state machines, synchronized Issue cockpits, permanent routing chats, exact-next-destination choreography, acceptance-only commits, duplicate acceptance-metadata CI, or routine per-session path restoration.
