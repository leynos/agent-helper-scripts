---
name: sdlc-implementation
description: >-
  Implement an approved ExecPlan through validated milestones, then hand PR
  delivery to pr-babysitting.
---

# ExecPlan implementation

Use when asked to implement an approved ExecPlan, normally
`docs/execplans/<slug>.md`. An explicit instruction to proceed with that plan
supplies execution approval; do not request it again. Resolve an exact plan
path or an unambiguous slug, accepted scope, worktree, PR, and publication and
merge authority from live state. Do not choose a different plan or PR.

## Ownership boundary

This skill owns implementation, milestone validation and local CodeRabbit CLI
reviews, plan maintenance, and the implementation handoff. `pr-babysitting`
owns the PR lifecycle from red CI and draft through authorized merge and
post-merge integration, including hosted assessments, review conversations,
readiness, rebasing, and protected publication. Do not run a second lifecycle
loop here or wait for hosted CI to become green before invoking that skill.

Read `execplans`, applicable `AGENTS.md` and contribution instructions, every
resource and skill named by the plan, and its upstream requirements, designs,
ADRs, and verification decisions before changing code. Honour constraints and
tolerances; record and escalate a proposed deviation rather than silently
rewriting approved scope. Use the candidate execution boundary in
`pr-babysitting` before running repository-defined commands.

Read the effective `wyvern`, `artisan`, `journeyman`, and `scrutineer` entries
in `agents/subagents.yml` before dispatch. Use the
[helper manifest lookup](references/delegation.md#locate-the-effective-agent-manifest)
to verify its repository, revision, and actual tool access. Load
`firecrawl-mcp` for external evidence and read
[reconnaissance and delegation](references/delegation.md) before dispatch. The
supervisor or owning journeyman retains integration, architecture, tolerance
decisions, and acceptance. Give artisans only complete, bounded packets; use
wyverns for narrowly scoped, read-only reconnaissance.

Give a scrutineer exclusive sequential ownership of shared validation resources
and explicitly requested milestone CLI reviews. For CI run monitoring, invoke
`pr-babysitting`'s scrutineer workflow with a monitoring-only assignment. Do
not duplicate its watcher, retry, or failure-log procedure. No worker may edit
the candidate during validation or review, run competing gates, or assume
observation authorizes repairs or external mutations.

## 1. Establish the task and metadata

Read [setup and identity](references/setup.md). Where necessary, normalize the
local branch to the plan slug, tracking `origin/<slug>` only when it is the
actual PR head. Preserve work and remote topology; a local rename is not
permission to rename or delete an existing PR's remote branch.

Remove only a leading `Plan:` prefix followed by a space from the PR title.
Then rename the active Lody session with
`lody session rename --title "$title"`. Run `echo "${LODY_SESSION_ID}"`, verify
the identifier, and add its session link once to the description's final
`## References` section. Preserve existing references and record genuinely
inapplicable Lody work without inventing one.

Use one delivery ledger shared with `pr-babysitting`, outside the tracked
product diff. Record the actual base/head, work ownership, milestone evidence,
review coverage, pending actions, and blockers. Do not create competing CI or
review ledgers. Missing tools or authority remain explicit blockers.

## 2. Deliver one coherent milestone at a time

Establish each milestone's approved scope, requirements, verification
obligations, acceptance evidence, and rollback boundary. Resolve narrow
external questions with Firecrawl and repository questions with a wyvern. Turn
established findings into one independently testable artisan assignment only
after requirements and material design decisions are settled.

Follow Red-Green-Refactor where practical: observe the expected failing test,
make the smallest correct change, then refactor and rerun focused checks.
Record a justified observable substitute when a test framework cannot express
the requirement. Plan implementation and verification together; do not add
proofs after the design or assume a passing verifier discharges every claim.

Keep the ExecPlan's Progress, Decision log, Surprises & discoveries, Risks,
Verification plan, Conformance basis, and Outcomes & retrospective current,
preserving its section names and trace links. Record failed approaches,
findings, observations, decisions, and remaining work. Commit small coherent
changes frequently, subject to repository commit gates, for reviewable Git
history and rollback. Never commit another worker's changes accidentally.

At each major milestone, have the scrutineer execute all applicable correctness
and quality gates sequentially against the exact candidate. Prefer documented
repository targets; include required manifest, spelling, security, and proof
checks. A generic docs-only shortcut does not waive a repository requirement.
Missing, skipped, failed, or inconclusive required checks are not passes.
Repair deterministic failures before any review.

Only then request `coderabbit review --agent` through the scrutineer, using
[milestone review and CLI backoff](references/milestone-review.md). Ensure the
review covers committed milestone work and its real comparison base. Verify
concerns against current source, using a wyvern for bounded investigation and
an artisan for a fully specified repair. Repeat the applicable gates and CLI
assessment until no valid concern remains unresolved before advancing.

For each authorized publication, verify remote parity and invoke or refresh
`pr-babysitting`'s monitoring-only scrutineer assignment. One published
candidate has one lifecycle owner. Keep local milestone acceptance distinct
from hosted CI and hosted assessment results.

## 3. Complete the implementation record

Map every acceptance criterion to implementation and observable evidence.
Update applicable user and developer documentation and the ExecPlan's current
status, decisions, findings, observations, and progress. Distinguish completed
implementation activity from pending assessment or delivery.

If, and only if, an explicitly associated roadmap task or step exists in
`docs/` and its implementation activity is complete, check that exact item. Do
not invent an association, complete a parent with unfinished children, or mark
future rollout work done. Reopen premature completion when later feedback
exposes an in-scope gap.

Update the PR description to reflect implementation and actual validation, with
the plan and Lody links in its final `## References`. Include the inventory of
introduced or materially changed CrossHair, Kani, Verus, LemmaScript, or
comparable proofs: actual paths and named proof references, claims,
assumptions, bounds, production connection, verifier commands, and outcomes.
Follow `pr-babysitting`'s
[assessment contract](../pr-babysitting/references/execplan-assessment.md) for
the required inventory and evidence, rather than copying its templates. Record
an evidence-backed `not applicable` when no proof is affected.

Run applicable gates after the final tracked edits, commit, and publish only
within the assignment's authority. Record the actual remote head and any
unfinished publication. Local validation does not establish hosted success.

## 4. Hand PR delivery to pr-babysitting

Invoke `pr-babysitting` now, even if the published PR is still draft or its CI
is red, pending, or missing. Supply the existing ledger and this packet:

```text
Repository, PR, worktree, target, and verified base/head:
Approved ExecPlan path and revision; accepted scope and tolerances:
Implementation status and acceptance evidence; remaining in-scope work:
Local gate and milestone CLI results with candidate identities and logs:
Proof inventory and verifier evidence, or justified not applicable:
ExecPlan completeness/correctness assessment: required; evidence or pending.
Proof-specific assessment: required when applicable; evidence or pending.
Roadmap association/status; PR description and Lody references:
Observed CI/review state, existing requests, and current lifecycle owner:
Authorized publication/merge actions, stopping point, and concrete blockers:
```

The receiving skill owns the two applicable hosted CodeRabbit assessments
before readiness, their feedback and recovery, CI, rebasing, and merge. A
handoff is not approval, a green check, or a completed merge. Supply a bounded
implementation repair when it requests one; retain plan maintenance and
acceptance traceability without duplicating its conversations or watchers.
Continue through that skill to the authorized endpoint, or report its precise
blocked/pending outcome. Never claim unscheduled background supervision.
