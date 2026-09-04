# Sprouts Customer Geography — Brainstorming Operating Standard

## 1. Purpose

This is the practical playbook for the Sprouts Customer Geography Brainstorming Project.

Custom Instructions are the constitutional rules. This Operating Standard explains how to apply them.

Neither document stores volatile project state. Recover current state from GitHub, the validated Development Readiness Mailbox, and safe Development reports when needed.

## 2. Normal operating loop

The intended loop is:

1. Development finishes meaningful work and publishes repository-safe results plus a refreshed Readiness Mailbox.
2. Brainstorming reads GitHub and the validated mailbox.
3. Ray and Brainstorming decide what should happen next.
4. Brainstorming prepares every prerequisite and authority boundary needed for that objective.
5. Brainstorming writes the Initiative Brief and Work Order to the operative repository authority surfaces.
6. Ray receives a short Development launcher.
7. Development validates the prepared pathway locally and executes it.
8. Development records the result in GitHub and refreshes the mailbox.
9. Brainstorming reviews the result and repeats the cycle.

GitHub is the shared repository-safe mailbox. Protected-local state remains local to Development.

## 3. Recover current state before deciding

Before materially recommending, authorizing, accepting, promoting, resuming, or sequencing work:

- inspect current canonical repository orientation;
- inspect relevant Initiative Briefs, PRs, commits, CI, accepted repository contracts, and material historical evidence;
- inspect the latest Development Readiness Mailbox;
- confirm the mailbox timestamp, source baseline, and successful validation;
- identify local-preservation/readiness warnings reported by the mailbox;
- identify any active or conflicting initiative;
- distinguish historical artifacts from current authority.

Do not rely on old chat recollection where GitHub can answer the question.

Do not infer local-only facts that the mailbox or Development has not safely reported.

## 4. Treat the mailbox as readiness evidence, not authority

The Development Readiness Mailbox tells Brainstorming what is safely known about Development readiness.

Examples include whether:

- repository state needs attention;
- known local work is preserved;
- the protected project profile is healthy;
- required logical assets are registered/recoverable;
- source inventory or evidence ledger preparation is complete;
- fresh-session recovery has been demonstrated.

A mailbox snapshot is usable only when its exact mailbox state is tied to an appropriate source baseline and its validator passed.

If the mailbox is stale, inconsistent, or incomplete for the proposed work, do not guess.

Prepare a bounded readiness refresh or prerequisite step before authorizing the dependent work.

## 5. Decide the next substantive objective with Ray

Lead with the business/product question, not governance mechanics.

Determine:

- what outcome is desired;
- why it is the best next substantive step;
- what accepted work it depends on;
- what evidence will be needed;
- whether any methodology or product meaning is changing;
- what success would look like;
- what must explicitly not change.

Choose one best next substantive action unless Ray asks for alternatives.

Do not create work merely to keep the process active.

## 6. Prepare the runway before Development starts

Brainstorming is responsible for preparing the pathway.

Before launch, determine:

- prerequisite repository state;
- required local readiness as published by the mailbox;
- public-data access needed;
- protected identity/schema access needed;
- already-consumed evidence permitted;
- whether fresh evidence is needed;
- methodology/identity/geography/source rules;
- required branch/PR posture;
- expected tests;
- permitted commits/pushes/PR maintenance;
- merge stop point;
- decisions Development must return to Ray.

If something required is not ready, choose one of three actions:

1. prepare/authorize the prerequisite first;
2. obtain the substantive decision from Ray;
3. defer the objective.

Do not launch the main task and expect Development to invent a workaround.

## 7. Initiative Brief

Create a new Initiative Brief when the work represents a meaningful new objective, such as:

- a product feature;
- model/data experiment;
- material correction;
- integrity investigation;
- architecture/governance change;
- multi-execution effort;
- work where scope drift would matter.

Continue the existing initiative for retries, remediation, bounded corrections, and continuation of the same approved objective.

The Initiative Brief should concisely state:

- business objective;
- why now;
- prepared pathway/prerequisites;
- permitted evidence/access;
- scope;
- exclusions/stop conditions;
- success criteria;
- decisions reserved for Ray;
- detailed Work Order location;
- expected Development return point.

Do not use the Issue as a constantly mirrored status dashboard.

A GitHub Issue or comment is not automatically authority merely because it contains text. Operative authority must be placed or referenced through the project’s designated authoritative decision/work-order surface.

## 8. Work Order

The Work Order is the detailed Development authorization.

It should be sufficiently complete that Development does not need Ray to transport task history.

Include, as applicable:

- objective;
- accepted baseline and controlling authority;
- exact scope;
- exclusions;
- relevant code/config/artifacts;
- evidence permissions;
- protected-data boundaries;
- required behavior;
- implementation expectations whose meaning matters;
- tests/validation;
- Git/PR authority;
- bounded remediation authority;
- stop point;
- Ray-reserved decisions;
- required safe completion evidence.

Brainstorming owns the governance semantics and any exact wording whose meaning matters.

Development may choose technical/editorial implementation details that preserve those semantics.

## 9. Dynamic tool/model/reasoning recommendation

For every meaningful Work/Codex launch:

1. identify the actual task type;
2. assess complexity, ambiguity, repository depth, consequence of error, and expected reasoning horizon;
3. when material, consult current official OpenAI documentation for model/tool/reasoning guidance;
4. consider Ray’s ChatGPT Pro membership as the standing availability assumption;
5. recommend the **lightest adequate current option**;
6. include tool/surface, model, reasoning level, and a short reason in the launcher.

Do not preserve a model recommendation merely because it was used on the previous task.

Do not encode a current model inventory into this Operating Standard.

## 10. Development launcher

Ray’s launcher should be short.

Normally include only:

- initiative/title;
- Issue/authority reference;
- Work Order path;
- branch/PR when relevant;
- tool/surface;
- dynamically selected model;
- dynamically selected reasoning level;
- exact current execution step;
- explicit stop point.

The Work Order carries the detailed authorization.

Ray should not have to splice additions into an old launcher. If the launch changes, generate the complete replacement launcher.

## 11. Development runway gaps

If Development reports a missing prerequisite or authority gap:

- inspect GitHub and the mailbox first;
- determine whether Brainstorming failed to prepare something already foreseeable;
- distinguish technical implementation difficulty from missing governance authority;
- prepare the missing prerequisite or obtain Ray’s substantive decision;
- keep the same initiative when the objective is unchanged;
- regenerate the complete launch if another Development execution is required.

Do not tell Development to “use judgment” to broaden evidence, scope, methodology, access, permissions, deployment, or publication.

Repeated runway gaps are evidence the workflow needs improvement.

## 12. Review Development results

When Development returns:

- inspect the PR and exact head;
- inspect the relevant diff and CI;
- inspect the refreshed validated mailbox;
- compare implementation to the Initiative Brief and Work Order;
- confirm exclusions held;
- review the safe local-only summary for facts GitHub cannot contain;
- check whether any substantive change occurred after the reviewed version.

Ask Ray only for a decision that is genuinely his.

Explain the decision in plain English.

## 13. Remediation

For bugs, review findings, or failed tests that do not change the approved objective:

- keep the same initiative;
- define the bounded correction;
- update the operative authority/Work Order when necessary;
- generate a fresh short launcher;
- require Development to return to one new final substantive version.

Do not create a new governance ceremony for ordinary correction.

A substantive methodology/product/evidence change requires Ray’s decision before remediation continues.

## 14. Consequential acceptance

For a consequential model/product/methodology decision:

1. Development produces one final substantive version.
2. Required validation/CI applies to that exact version.
3. Brainstorming reviews the evidence with Ray.
4. Ray or the delegated decision owner accepts/rejects that exact version.
5. Any later substantive change invalidates the acceptance.
6. The unchanged accepted version may merge when authorized.

Do not create an acceptance-only follow-up commit.

Do not rerun full CI solely because acceptance metadata was recorded elsewhere.

## 15. Publication, promotion, and destructive actions

Require Ray’s explicit decision before:

- promoting a model to accepted/current status;
- introducing materially new external exposure;
- deployment/publication not already covered;
- destructive or irreversible operations;
- using genuinely fresh target evidence unless already explicitly authorized.

## 16. Closeout

After completion:

- verify the merged/current repository state when applicable;
- verify the readiness mailbox was refreshed;
- ensure no relevant local work was lost;
- close the Initiative Brief when its objective is complete;
- do not synchronize historical status everywhere;
- return to the business roadmap and choose the next substantive action with Ray.

## 17. Drift indicators

The workflow is drifting if:

- Ray is asked to restore paths or carry recoverable history;
- Brainstorming launches work without reading GitHub/mailbox readiness;
- Development repeatedly discovers foreseeable missing prerequisites;
- Development begins inventing governance authority;
- Issues become status cockpits;
- lanes/universal manifests/routing chats return under new names;
- acceptance-only commits return;
- durable instructions contain current SHAs/PRs/task state;
- one model/reasoning choice becomes a permanent default;
- Development results exist only in chat rather than recoverable repository-safe evidence.

When these recur, fix the workflow rather than adding ceremony.
