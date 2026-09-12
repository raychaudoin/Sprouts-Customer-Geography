# Active Mailbox Record Guide

## Purpose

The active GitHub mailbox carries concise chronological evidence for one initiative/candidate. It is distinct from the machine-generated [Development Readiness Mailbox](DEVELOPMENT_READINESS_MAILBOX.md), which publishes safe capability/readiness facts and is neither task authority nor chronology.

Before a PR exists, the Initiative Issue may serve as the active mailbox. Once a PR exists, the PR conversation is the active candidate mailbox. Write new candidate chronology only to the PR; do not mirror it to the Issue.

Launch, Result, and Review Records are coordination/evidence only. They cannot create or enlarge authority, accept work, authorize merge or protected action, or override the operative Work Order or repository truth. Keep records concise; link durable authority and evidence instead of copying long reports.

## LAUNCH

Brainstorming writes a Launch Record before meaningful Development or independent-review work.

```markdown
### LAUNCH — <initiative/current action>

- Record type: `LAUNCH`
- Controlling Work Order: `<repository path>`
- Destination/role: `<Development or review surface>`
- Candidate: `<PR and exact head, when applicable>`
- Requested action: <bounded action>
- Material exclusions: <concise exclusions>
- Execution profile: <task-specific surface/model/reasoning, when relevant>
- Next control point: <expected durable result>

This Launch Record is coordination/evidence only and does not enlarge authority.
```

## RESULT

Development writes a Result Record after meaningful implementation or remediation and before returning control. Once a PR exists, post it to that PR conversation.

```markdown
### RESULT — <initiative/action performed>

- Record type: `RESULT`
- Candidate: `<PR and exact resulting head>`
- Changed scope: <concise summary>
- Validation/CI: <performed, passing, or pending>
- Safeguards/exclusions: <preserved boundaries>
- Gap/deviation: `None` or <concise safe gap>
- Next control point: <review, decision, or prepared remediation>

This Result Record is coordination/evidence only and does not grant acceptance or merge authority.
```

If the candidate head changes after the record, post a new Result Record bound to the revised head before returning again.

## REVIEW

Independent review writes a Review Record against the exact candidate reviewed and posts it to the active PR mailbox.

```markdown
### REVIEW — <review role/surface>

- Record type: `REVIEW`
- Candidate: `<PR, exact base, exact head>`
- Disposition: `PASS` or `REWORK REQUIRED`
- Material findings/deviations: `None` or <concise findings>
- Safety/evidence concerns: `None` or <concise concerns>
- Next control point: <decision or bounded remediation>

This Review Record is technical/fidelity evidence only and does not create business acceptance or merge authority.
```

Any substantive change after review requires review of the revised candidate when review remains required.
