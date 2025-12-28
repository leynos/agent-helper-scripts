---
name: execplans
description: Write and maintain self-contained ExecPlans (execution plans) that a novice can follow end-to-end; use when planning or implementing non-trivial repo changes.
---

# Codex Execution Plans (ExecPlans)

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
  and decisions are finalised; each revision must remain self-contained.
- End-to-end and observable: it must produce demonstrably working behaviour,
  not merely "code changes that compile".
- Plain language: define every term of art immediately, or do not use it.
- Outcome-focused: begin with why the work matters and how to observe success.
- Autonomous: the agent implementing the plan proceeds milestone-by-milestone,
  without asking the user for "next steps".

## Relationship to `PLANS.md`

If `PLANS.md` exists in the repo, follow it to the letter.

When authoring an ExecPlan:

- Read the entire `PLANS.md` file, then re-read anything you rely on.
- Start from the skeleton (included below) and flesh it out as you research.

When implementing an ExecPlan:

- Do not pause to ask what to do next; proceed to the next milestone.
- Keep all sections current, especially the mandatory living sections.
- Commit frequently and keep changes small and testable.

## Formatting rules (strict)

ExecPlans have a strict envelope to keep them easy to copy, review, and resume:

- Each ExecPlan must be one single fenced code block labelled as `md` that
  begins and ends with triple backticks.
- Do not nest additional triple-backtick fences inside the ExecPlan. When you
  need commands, transcripts, diffs, or code, present them as indented blocks
  inside the single fence.
- Use two newlines after every heading.
- Use correct Markdown syntax for ordered and unordered lists.

Exception:

- If you are writing an ExecPlan to a Markdown file where the entire file is
  only the ExecPlan, omit the outer triple backticks.

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
- Include expected outputs (even short ones) so a novice can tell success from
  failure.

Capture evidence:

- When steps produce output, include concise transcripts as indented examples.
- Keep evidence focused on what proves success.

## Mandatory living sections (always present)

ExecPlans must contain, and must keep up to date as work proceeds:

- `Progress` (with checkbox list and timestamps)
- `Surprises & Discoveries` (unexpected behaviours and evidence)
- `Decision Log` (every key decision with rationale)
- `Outcomes & Retrospective` (what was achieved and lessons learned)

If you change course mid-implementation:

- Document why in `Decision Log`.
- Reflect the implications in `Progress` (what changed, what remains).

## Prototyping milestones (encouraged when de-risking)

When requirements are challenging or unknowns are significant, include explicit
prototyping milestones:

- Label the milestone as prototyping.
- Keep prototypes additive, testable, and easy to delete or promote.
- Provide concrete run instructions and acceptance criteria that decide whether
  the prototype is kept or discarded.
- If exploring alternatives, keep them parallel only long enough to reduce
  risk, then retire one path with tests.

## Skeleton of a good ExecPlan

Copy the following skeleton when starting a new ExecPlan, then fill it in as
you research and implement.

```markdown
# <Short, action-oriented description>

This ExecPlan is a living document. The sections `Progress`,
`Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must
be kept up to date as work proceeds.

If PLANS.md file is checked into the repo, reference the path to that file here
from the repository root and note that this document must be maintained in
accordance with PLANS.md.

## Purpose / Big Picture

Explain in a few sentences what someone gains after this change and how they
can see it working. State the user-visible behaviour you will enable.

## Progress

Use a list with checkboxes to summarise granular steps. Every stopping point
must be documented here, even if it requires splitting a partially completed
task into two (“done” vs. “remaining”). This section must always reflect the
actual current state of the work.

    - [x] (2025-10-01 13:00Z) Example completed step.
    - [ ] Example incomplete step.
    - [ ] Example partially completed step (completed: X; remaining: Y).

Use timestamps to measure rates of progress.

## Surprises & Discoveries

Document unexpected behaviours, bugs, optimisations, or insights discovered
during implementation. Provide concise evidence.

    - Observation: …
      Evidence: …

## Decision Log

Record every decision made while working on the plan in the format:

    - Decision: …
      Rationale: …
      Date/Author: …

## Outcomes & Retrospective

Summarise outcomes, gaps, and lessons learned at major milestones or at
completion. Compare the result against the original purpose.

## Context and Orientation

Describe the current state relevant to this task as if the reader knows
nothing. Name the key files and modules by full path. Define any non-obvious
term you will use. Do not refer to prior plans.

## Plan of Work

Describe, in prose, the sequence of edits and additions. For each edit, name
the file and location (function, module) and what to insert or change. Keep it
concrete and minimal.

## Concrete Steps

State the exact commands to run and where to run them (working directory).
When a command generates output, show a short expected transcript so the
reader can compare. This section must be updated as work proceeds.

## Validation and Acceptance

Describe how to start or exercise the system and what to observe. Phrase
acceptance as behaviour, with specific inputs and outputs. If tests are
involved, say "run <project’s test command> and expect <N> passed; the new test
<name> fails before the change and passes after>".

## Idempotence and Recovery

If steps can be repeated safely, say so. If a step is risky, provide a safe
retry or rollback path. Keep the environment clean after completion.

## Artifacts and Notes

Include the most important transcripts, diffs, or snippets as indented
examples. Keep them concise and focused on what proves success.

## Interfaces and Dependencies

Be prescriptive. Name the libraries, modules, and services to use and why.
Specify the types, traits/interfaces, and function signatures that must exist
at the end of the milestone. Prefer stable names and paths such as
`crate::module::function` or `package.submodule.Interface`.

E.g., in crates/foo/planner.rs, define:

    pub trait Planner {
        fn plan(&self, observed: &Observed) -> Vec<Action>;
    }
```

## Revision note (required when editing an ExecPlan)

When you revise an ExecPlan, ensure changes are reflected across all relevant
sections. Append a short note at the bottom of the ExecPlan describing:

- what changed,
- why it changed,
- and how it affects the remaining work.

