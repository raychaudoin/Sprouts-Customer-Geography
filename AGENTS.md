# Repository Agent Contract

This file is the canonical repository-level instruction contract for Sprouts Customer Geography. Follow higher-priority system, developer, administrator, platform, and explicit user instructions first. When authority is ambiguous or an action could destroy or expose protected state, fail closed and request direction.

## Product and business boundary

Sprouts Customer Geography is a public-data proxy and decision-support capability for understanding likely Sprouts-oriented household geography, including demographic fit, target-household mass, pocket continuity, seed surroundings, directional change, candidate displacement, and market context. Milwaukee is the first pilot; later markets must use configuration rather than copied applications or repositories.

The product is not a final site-selection engine, a substitute for human judgment, an extension of the existing Sprouts Site Scanner, or a reproduction of Sprouts' proprietary customer model.

## Authority and workflow

- Ray's explicit instructions and authorizations control within applicable higher-level instructions.
- The Brainstorming Project's Master Control Room controls roadmap, sequencing, and task authorization. Capability Decisions & Acceptance chats control detailed acceptance.
- Treat Work as read-only assessment or research unless explicitly granted other capabilities. Treat Codex as bounded implementation.
- Work and Codex may recommend but may not self-authorize, self-accept, promote, or begin follow-on work.
- Stay within the execution prompt. Embed any inaccessible context needed for execution in that prompt.
- Ask only questions that materially change safe execution; otherwise make and label reasonable assumptions.

## Successor recovery and durable state

Use this reading order to recover current controlling state: (1) README current orientation; (2) this AGENTS authority and boundary contract; (3) exactly matching task manifest(s); (4) detailed work order where needed; (5) accepted `config/` and `schemas/` authority; and (6) relevant GitHub PR, commit, CI, and ruleset evidence. Repository authority remains controlling over derivative GitHub coordination evidence. Material conflict, missing authority, stale detail, inaccessible evidence, or ambiguous retrieval must fail closed. Because this repository is PUBLIC, treat all tracked repository material as public disclosure.

Every future material repository/GitHub execution or other acceptance-bearing durable implementation must use exactly one governed task manifest. Pure read-only exploratory Work does not require a manifest merely because it occurred. If a read-only result becomes accepted controlling state, reconcile it into an existing durable authority artifact or a justified work-order/current-state record; do not create a second registry.

## Scope control

Favor the smallest useful increment. Distinguish prerequisites from housekeeping. Avoid broad cleanup, unnecessary rewrites, speculative frameworks, and market-specific forks. Record unrelated discoveries as bounded backlog recommendations. Never promise background or future completion, and never begin a recommended follow-on task without authorization.

## Architecture boundary

- Perform reproducible public-data preparation and complex spatial analysis upstream; expose stable presentation-output contracts.
- Power BI is the intended MVP presentation layer, not the owner of complex GIS calculations. Do not build a custom HTML or JavaScript map unless later authorized.
- Use market configuration, replaceable public-source adapters, and an extension boundary for future proprietary adapters.
- Do not prematurely introduce cloud services, databases, APIs, orchestration frameworks, or dependencies. Dependency selection requires an authorized implementation task.
- Treat this architecture as a starting guardrail, not an implemented or irrevocable production design. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Confidentiality and protected information

Treat the repository as if it may later be viewed beyond the immediate user. Unless explicitly authorized, never commit real Sprouts seed points; internal Sprouts direction; live-pursuit candidate addresses or coordinates; owner or broker contacts; GBT, API, or vendor credentials; proprietary demographic data; live Site Scanner databases; emails; internal documents; production exports with confidential fields; or screenshots exposing confidential information.

Use synthetic or clearly fictional fixtures and ignored local overlays for confidential data. Document environment-variable handling. Keep secrets out of logs, fixtures, notebooks, screenshots, and reports. If protected material is discovered, stop, isolate it without copying or deleting it, and report it. See [docs/DATA_GOVERNANCE.md](docs/DATA_GOVERNANCE.md).

## Public-data provenance

Each accepted source needs a manifest or equivalent record, as applicable, with source name, official location, access method, dataset and schema versions, release/vintage, retrieval date, geography vintage, license/terms, attribution, query/extraction parameters, practical checksums, known omissions, transformation lineage, refresh expectations, and fallback behavior.

Keep raw downloads and large caches outside Git unless a specific small, legal fixture is authorized. Preserve reconstructability through manifests, scripts, configuration, documentation, synthetic fixtures, and tests—not copied downloaded environments.

## Analytical and scoring guardrails

No customer-fit weights or scoring authority currently exists. Any later authorized implementation must:

- distinguish demographic fit from household mass and descriptive measures from modeled conclusions;
- retain components, source vintages, uncertainty, and quality flags;
- never silently convert missing values to neutral or favorable values, and fail closed when missing inputs would mislead;
- document normalization, transformations, weights, and calibration;
- exclude protected characteristics from scoring inputs absent explicit review and authorization;
- describe outputs as public-data proxies, never Sprouts' proprietary model; and
- use seed points as evidence, not automatic ground truth.

## Power BI guardrails

Future authorized Power BI work must prefer a source-control-compatible project representation when available, supportable, and approved. Document the report, semantic-model, data-contract, refresh, and any binary fallback sources of truth. Avoid unapproved custom visuals and hidden spatial logic in DAX or Power Query when upstream computation is more testable. Separate confidential local data from committed definitions; document licensing, organizational, and publishing assumptions; preserve a functional local MVP without assuming Fabric, Power BI Service, premium capacity, ArcGIS access, or enterprise publishing rights; retain reconstruction metadata; and avoid coupling the report to one proprietary source.

## Handoff and prompt formatting

Every handoff artifact has two distinct parts:

1. **Ray's routing wrapper**, outside the copyable prompt, may state the step, destination Project, create/continue choice, exact title, tool/surface, model, reasoning, selection reason, fallback, and where Ray should manually carry the result.
2. **Recipient-only prompt**, for the already-open chat or thread, begins with the exact title, directs work in the current chat/thread, states whether new-thread creation or delegation is prohibited, and includes complete authorization and self-contained context.

The recipient-only prompt must not contain `SEND TO`, `PASTE/DO THIS`, `WHEN COMPLETE, RETURN TO`, `THEN`, instructions for Ray to open another thread, or instructions for the recipient to delegate to another thread. No automatic handoff occurs unless Ray explicitly requests one.

Where durable detailed authority already exists, a continuation/resumption may use a short launcher containing only task ID, exact thread title, tool/surface, model, reasoning, and exact current step identity. The repository-connected receiver must resolve this contract, exactly one matching manifest, exactly one required detailed work order, referenced accepted config/schema authority, and relevant GitHub PR evidence. Fail closed for no or multiple controlling task records, non-executable manifest state, missing/stale/superseded required work order, conflicting authority, inaccessible evidence, or ambiguous retrieval. Do not use a short launcher for first execution of a new task without durable detailed execution authority; a full self-contained Master Control Room prompt remains the default and fallback.

## Systematic problem-solving

Identify the business problem, failure family, shared invariant, root cause, adjacent variants, boundaries, invalid and missing inputs, retry and interruption behavior, generalization limit, and residual risk. Prefer one bounded general rule or validation contract over record-specific exceptions.

## Testing and validation

Use meaningful tests appropriate to the authorized task. As relevant, cover source schemas, geography, join keys, reproducibility, synthetic spatial fixtures, boundary direction, missing data, uncertainty, quality flags, stable output schemas, duplicates, stale sources, interruption, reruns, fail-closed behavior, and full corrected-stage validation. Do not create meaningless tests merely to report a passing suite.

## Git safety

- Work on a task-specific branch or isolated worktree; do not edit the default branch unless explicitly authorized.
- For governed execution, maintain the repository-safe task manifest and apply the task, branch, commit, state, protected-boundary, and separate-acceptance rules in [docs/GITHUB_WORKFLOW_GOVERNANCE.md](docs/GITHUB_WORKFLOW_GOVERNANCE.md). Do not infer `ACCEPTED_CLOSED` from implementation evidence.
- Do not force-push, destructively reset, delete user work, rebase, squash, merge, cherry-pick, or promote without explicit authorization.
- Use concise task-specific commits. Before completion, review repository status and the complete diff; check for accidental large data, secrets, confidential inputs, and unrelated changes.
- Report the actual branch/worktree, commit, push result, and promotion readiness.

## Completion reports

Report only evidence material to the task and its acceptance or next decision. As applicable, include:

- outcome;
- validation;
- confidentiality and protected-state preservation;
- blockers;
- branch, commit, pull-request, and CI state;
- exact destination.

Do not repeat evidence already directly recoverable from the repository or GitHub unless needed to explain a discrepancy, limitation, or decision.

Current Project and chat instructions control prose style, tone, section structure, and whether a summary section is used. Do not require a formulaic Business Takeaway or other generic closing boilerplate.
