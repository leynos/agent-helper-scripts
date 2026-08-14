---
name: execplans
description: Write and maintain self-contained ExecPlans (execution plans) that a novice can follow end-to-end; use when planning or implementing non-trivial repo changes.
---

# Codex execution plans (ExecPlans)

This skill describes how to author, discuss, and implement an execution plan
("ExecPlan"). An ExecPlan is a living design-and-delivery document that a
coding agent (or human) can follow to ship a demonstrably working change.

Treat the reader as a complete beginner to this repository. Assume they have:

- only the current working tree,
- only the single ExecPlan file you provide,
- no memory of prior plans,
- no external context.

The bar is high: the ExecPlan must be self-contained and sufficient for
end-to-end delivery, including validation and observable behaviour.

## When to use this skill

Use this skill when:

- you are asked to write an "execution plan", "design doc", "spec", or
  "implementation plan" for a meaningful change, or
- you are asked to implement work that is (or should be) guided by an ExecPlan,
  or
- the task has significant unknowns and would benefit from prototyping
  milestones to de-risk feasibility.

## Non-negotiable requirements (read first)

Every ExecPlan must satisfy all of the following:

- Fully self-contained: it contains all knowledge and instructions needed for a
  novice to succeed.
- Living document: it must be revised as progress is made, discoveries occur,
  and decisions are finalized; each revision must remain self-contained.
- End-to-end and observable: it must produce demonstrably working behaviour,
  not merely "code changes that compile".
- Test-first delivery: all code changes must follow Red-Green-Refactor when
  the project has any practical test framework for the affected behaviour.
- Plain language: define every term of art immediately, or do not use it.
- Outcome-focused: begin with why the work matters and how to observe success.
- Controlled delegation: the agent implementing the plan proceeds
  milestone-by-milestone within defined tolerances, escalating when those
  tolerances would be exceeded rather than improvizing.

Autonomy without tolerances is unattended automation. The goal is predictable
outcomes, not maximum throughput.

## When to push back or escalate

Before accepting a task, evaluate whether an ExecPlan is the right approach.
Escalate or request clarification when:

- The task is underspecified and multiple interpretations lead to materially
  different implementations. Present the interpretations and ask which is
  intended.
- The task's scope is unbounded or unclear. Propose a bounded first milestone
  and ask if that captures the intent.
- The task conflicts with observable project conventions, existing tests, or
  documented constraints. Note the conflict and ask how to resolve it.
- The task requires changes to areas with high blast radius (auth, payments,
  data migrations, public APIs) without explicit acknowledgement of the risk.
  Name the risk and ask for confirmation.
- The task requests a pattern that experience suggests produces poor outcomes
  (e.g., "just make the tests pass" when the tests are wrong). State the
  concern and propose an alternative.

Pushing back is not failure; it is part of the agent's quality function.

## Approval gate (required before implementation)

An ExecPlan proceeds through two distinct phases:

1. Draft phase: the agent produces the ExecPlan but does not execute it.
2. Execution phase: the agent implements within tolerances, escalating on
   exceptions.

After completing the initial ExecPlan draft, present it to the user and await
explicit approval before beginning implementation. This gate exists because:

- The user may have constraints not yet captured.
- Tolerance thresholds may need adjustment.
- The proposed approach may conflict with work the agent cannot see.

Do not interpret silence as approval. Do not begin implementation until the
user explicitly confirms the plan or requests revisions.

If the user has previously established standing instructions (e.g., "implement
plans immediately for changes under 100 LOC"), those instructions override this
gate for qualifying work.

When implementing an ExecPlan:

- Do not pause to ask what to do next; proceed to the next milestone.
- Stop and escalate when a tolerance threshold is reached.
- Keep all sections current, especially the mandatory living sections.
- Commit frequently and keep changes small and testable.

## Formatting rules (strict)

ExecPlans have a strict envelope to keep them easy to copy, review, and resume:

- Use two newlines after every heading.
- Use correct Markdown syntax for ordered and unordered lists.
- Use code attribution in each fenced code block, and label text blocks as
  `plaintext`.
- Use `1.`, `2.`, etc. for ordered lists.
- If embedding the plan in a larger document, use triple tilde fences to
  enclose the plan.

## How to write a good ExecPlan

Write in plain prose. Prefer sentences over lists. Avoid checklists, tables,
and long enumerations unless brevity would obscure meaning.

Anchor everything to observable outcomes:

- State what a user can do after the change.
- Provide the exact commands to run and the outputs to expect.
- Phrase acceptance as behaviour a human can verify.
  - Good: "Running `make test` passes and the new test
    `tests::feature_x::works` fails before and passes after."
  - Good: "Starting the server and requesting `/health` returns HTTP 200 with
    body `OK`."
  - Bad: "Added a `HealthCheck` struct."

Be explicit about repository context:

- Name files with full repository-relative paths.
- Name functions/modules precisely, as they appear in code.
- Include a short orientation paragraph if touching multiple areas so a novice
  can navigate confidently.

Be safe and idempotent:

- Steps should be re-runnable without damage or drift.
- If a step can fail halfway, say how to retry.
- If anything destructive is unavoidable, spell out backups/rollback.

Validation is not optional:

- Include instructions to run tests, lint, and any relevant runtime checks.
- Establish a failing test suite prior to implementation using
  Red-Green-Refactor:
  - Red: add or update the smallest test that specifies the missing behaviour
    and run it before production-code changes. The command must fail for the
    expected reason.
  - Green: make the smallest production-code change that makes the red test
    pass, then run the focused test again.
  - Refactor: clean up the implementation without changing behaviour, rerunning
    the focused test and the relevant wider gates afterwards.
- Where the test framework supports expected-failure markers, use strict
  expected failures to enforce the red stage. For example, in pytest use
  `@pytest.mark.xfail(strict=True, reason="...")` until the red failure is
  observed, then remove the marker as part of the green step. Do not leave
  expected-failure markers in the final passing implementation unless the plan
  explicitly scopes a known unresolved defect.
- If Red-Green-Refactor is genuinely unavailable, document why in `Constraints`
  or `Decision Log`, then use the nearest observable substitute such as a
  reproducer script, golden fixture, compile-fail test, approval test, or
  manual runtime check.
- Where behaviour-driven development (BDD) is used, include the feature
  specification in the ExecPlan. Name the feature file path, quote or embed the
  relevant `Feature`, `Scenario`, `Given`, `When`, and `Then` statements, and
  keep the specification synchronized with the implementation milestones.
- Include expected outputs (even short ones) so a novice can tell success from
  failure.

Capture evidence:

- When steps produce output, include concise transcripts as codefenced examples.
- Keep evidence focused on what proves success.

## Mandatory living sections (always present)

ExecPlans must contain, and must keep up to date as work proceeds:

- `Constraints` (hard invariants that must not be violated)
- `Tolerances` (thresholds that trigger escalation when breached)
- `Risks` (known uncertainties with mitigations, identified upfront)
- `Progress` (with checkbox list and timestamps)
- `Surprises & Discoveries` (unexpected findings during implementation)
- `Decision Log` (every key decision with rationale)
- `Outcomes & Retrospective` (what was achieved and lessons learned)

If you change course mid-implementation:

- Document why in `Decision Log`.
- Reflect the implications in `Progress` (what changed, what remains).
- Update `Risks` if new uncertainties have emerged.

## Exception handling (manage by exception)

When a tolerance threshold is reached or a constraint would be violated:

1. Stop implementation immediately.
2. Document the situation in `Decision Log` with:
   - What threshold was reached or constraint threatened.
   - What options exist to proceed.
   - Trade-offs of each option.
3. Await explicit direction before proceeding.

Do not attempt to work around tolerances. They exist to catch situations where
human judgement is required.

## Prototyping milestones (encouraged when de-risking)

When requirements are challenging or unknowns are significant, include explicit
prototyping milestones:

- Label the milestone as prototyping.
- Keep prototypes additive, testable, and easy to delete or promote.
- Provide concrete run instructions and acceptance criteria that decide whether
  the prototype is kept or discarded.
- If exploring alternatives, keep them parallel only long enough to reduce
  risk, then retire one path with tests.

## ExecPlan template

Copy and complete the [ExecPlan template](references/execplan-template.md)
when starting a new ExecPlan. Keep its mandatory living sections current as
you research and implement.

## Revision note (required when editing an ExecPlan)

When you revise an ExecPlan, ensure changes are reflected across all relevant
sections. Append a short note at the bottom of the ExecPlan describing:

- what changed,
- why it changed,
- and how it affects the remaining work.

Update the Status field in the header when the plan's state changes.
