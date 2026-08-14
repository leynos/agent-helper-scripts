# `<Short, action-oriented description>`

This ExecPlan (execution plan) is a living document. The sections
`Constraints`, `Tolerances`, `Risks`, `Progress`, `Surprises & Discoveries`,
`Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work
proceeds.

Status: DRAFT | APPROVED | IN PROGRESS | BLOCKED | COMPLETE

## Purpose / big picture

Explain in a few sentences what someone gains after this change and how they
can see it working. State the user-visible behaviour you will enable.

## Constraints

Hard invariants that must hold throughout implementation. These are not
suggestions; violation requires escalation, not workarounds.

- Paths/modules this plan must not modify.
- Public interfaces that must remain stable.
- Compatibility requirements (language versions, platforms, targets).
- Security or compliance considerations that constrain approach selection.

If satisfying the objective requires violating a constraint, do not proceed.
Document the conflict in `Decision Log` and escalate.

## Tolerances (exception triggers)

Thresholds that trigger escalation when breached. These define the boundaries
of autonomous action, not quality criteria.

- Scope: if implementation requires changes to more than `<N>` files or `<M>` lines
  of code (net), stop and escalate.
- Interface: if a public API signature must change, stop and escalate.
- Dependencies: if a new external dependency is required, stop and escalate.
- Iterations: if tests still fail after `<K>` attempts, stop and escalate.
- Time: if a milestone takes more than `<T>` hours, stop and escalate.
- Ambiguity: if multiple valid interpretations exist and the choice materially
  affects the outcome, stop and present options with trade-offs.

Adjust these values based on the task. Small, well-understood changes warrant
tighter tolerances; exploratory work may need looser ones.

## Risks

Known uncertainties that might affect the plan. Identify these upfront and
update as work proceeds. Each risk should note severity, likelihood, and
mitigation or contingency.

- Risk: `<description>`
  Severity: low | medium | high
  Likelihood: low | medium | high
  Mitigation: `<how to prevent or reduce impact>`.

Risks differ from Surprises: risks are anticipated; surprises are not.

## Progress

Use a list with checkboxes to summarize granular steps. Every stopping point
must be documented here, even if it requires splitting a partially completed
task into two ("done" vs. "remaining"). This section must always reflect the
actual current state of the work.

- [x] (2025-10-01 13:00Z) Example completed step.
- [ ] Example incomplete step.
- [ ] Example partially completed step (completed: X; remaining: Y).

Use timestamps to measure rates of progress and detect tolerance breaches.

## Surprises & discoveries

Unexpected findings during implementation that were not anticipated as risks.
Document with evidence so future work benefits.

- Observation: `<what was unexpected>`.
  Evidence: `<how you know>`.
  Impact: `<how it affects this plan or future work>`.

## Decision log

Record every significant decision made while working on the plan. Include
decisions to escalate, decisions on ambiguous requirements, and design choices.

- Decision: `<what was decided>`
  Rationale: `<why this choice over alternatives>`
  Date/Author: `<timestamp and who decided>`.

## Outcomes & retrospective

Summarize outcomes, gaps, and lessons learned at major milestones or at
completion. Compare the result against the original purpose. Note what would be
done differently next time.

## Context and orientation

Describe the current state relevant to this task as if the reader knows
nothing. Name the key files and modules by full path. Define any non-obvious
term you will use. Do not refer to prior plans.

## Plan of work

Describe, in prose, the sequence of edits and additions. For each edit, name
the file and location (function, module) and what to insert or change. Keep it
concrete and minimal.

Structure as stages with explicit go/no-go points where appropriate:

- Stage A: understand and propose (no code changes)
- Stage B: red tests or BDD feature specification (small, verifiable diffs that
  fail before implementation for the expected reason)
- Stage C: implementation (minimal change to satisfy tests)
- Stage D: refactor, documentation, and cleanup

Each stage ends with validation. Do not proceed to the next stage if the
current stage's validation fails.

## Concrete steps

State the exact commands to run and where to run them (working directory).
When a command generates output, show a short expected transcript so the
reader can compare. This section must be updated as work proceeds.

## Validation and acceptance

Describe how to start or exercise the system and what to observe. Phrase
acceptance as behaviour, with specific inputs and outputs. If tests are
involved, say "run `<project's test command>` and expect `<N>` passed; the new
test `<name>` fails before the change and passes after".

For code changes, record the Red-Green-Refactor evidence:

- Red command and expected failure, including any strict expected-failure marker
  used to prove the test fails for the intended reason.
- Green command and expected pass after the minimal implementation.
- Refactor command sequence and expected pass after cleanup.

For BDD changes, include the feature specification that drives the work and the
BDD runner command that proves the scenario fails before implementation and
passes afterwards.

Quality criteria (what "done" means):

- Tests: `<what must pass>`
- Lint/typecheck: `<commands and expected result>`
- Performance: `<any benchmarks or thresholds>`
- Security: `<any scans or review requirements>`

Quality method (how we check):

- `<CI command or manual verification steps>`

## Idempotence and recovery

If steps can be repeated safely, say so. If a step is risky, provide a safe
retry or rollback path. Keep the environment clean after completion.

## Artefacts and notes

Include the most important transcripts, diffs, or snippets as codefenced
examples. Keep them concise and focused on what proves success.

## Interfaces and dependencies

Be prescriptive. Name the libraries, modules, and services to use and why.
Specify the types, traits/interfaces, and function signatures that must exist
at the end of the milestone. Prefer stable names and paths such as
`crate::module::function` or `package.submodule.Interface`.

E.g., in crates/foo/planner.rs, define:

```rust
pub trait Planner {
    fn plan(&self, observed: &Observed) -> Vec<Action>;
}
```
