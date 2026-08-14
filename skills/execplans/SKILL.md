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
- Joint implementation and verification planning: identify the invariants,
  lemmas, and non-trivial axioms before settling the implementation structure,
  then align each obligation with a proportionate verification strategy.
- Lightweight architecture contract: preserve selective traceability from
  approved upstream requirements and design decisions through milestones to
  acceptance evidence, and surface deviations rather than silently drifting.
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

## Traceability and architecture conformance

Treat an ExecPlan as a lightweight architecture contract, not as an isolated
task list. Where upstream artefacts exist, add a `Conformance basis` naming the
exact Terms of Reference revision, technical-design revision, ADRs, governing
standards, and relevant requirement or design-element identifiers. If no such
artefact exists, say so explicitly rather than inventing one.

Use stable identifiers selectively for propositions whose provenance and
discharge matter: upstream goals, hard constraints, success criteria,
important assumptions, architecture requirements and major design elements;
ExecPlan milestones; and their acceptance evidence. Do not number every
paragraph. Preserve a chain such as:

```plaintext
TOR-GOAL-004 -> TDD-REQ-012 -> TDD-COMP-queue-store -> EP-M3 -> tests::queue::persists_reordering
```

Map each applicable upstream requirement or baseline-to-target gap to at least
one milestone and observable acceptance item. When a traced item changes,
identify its upstream and downstream impacts before accepting the change, and
update every affected link.

At each milestone boundary, perform a focused conformance check:

- Are the requirements and gaps assigned to this milestone satisfied?
- Does the implementation still conform to the approved design?
- Did a discovery falsify an upstream assumption?
- Did the work introduce an unapproved public interface, dependency, trust
  boundary, or persistent-format change?
- Are trace links and acceptance evidence still current?

Tailor this check to the work's material risks; do not create a ceremonial
enterprise-compliance checklist.

If evidence shows that the approved design cannot or should not be followed,
do not silently amend the implementation or plan around it. Record a proposed
deviation in `Decision log`, including the affected identifiers, impacts,
options, and whether the technical design or an ADR must change. Set the plan
status to `BLOCKED` and wait for explicit acceptance of the deviation before
continuing.

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
- Keep the unit and behavioural test plan, then add verification evidence for
  invariants and lemmas that examples alone cannot establish.
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
  or `Decision log`, then use the nearest observable substitute such as a
  reproducer script, golden fixture, compile-fail test, approval test, or
  manual runtime check.
- Where behaviour-driven development (BDD) is used, include the feature
  specification in the ExecPlan. Name the feature file path, quote or embed the
  relevant `Feature`, `Scenario`, `Given`, `When`, and `Then` statements, and
  keep the specification synchronized with the implementation milestones.
- Include expected outputs (even short ones) so a novice can tell success from
  failure.

## Plan implementation and verification together

Do not choose an implementation and bolt verification onto it afterwards.
Select an implementation structure whose decomposition, state representation,
and control flow expose tractable verification obligations. If implementation
reveals an unplanned invariant, lemma, or axiom, return to the plan and revise
both the implementation and verification strategy before continuing.

Every ExecPlan must contain a `Verification plan` that:

- states each invariant over inputs, states, orderings, or transitions that the
  planned implementation introduces or preserves;
- states each lemma or intermediate contract needed to connect those invariants
  to the required behaviour;
- lists every non-trivial axiom on which the reasoning depends, including
  assumptions about runtimes, platforms, external services, and third-party
  interfaces;
- assigns each invariant and lemma a verification method, planned artefact,
  command, expected evidence, and discharge condition; and
- justifies why the selected method provides adequate rigour and records any
  bound, abstraction, or residual gap.

Choose methods according to the obligation rather than language or habit:

- Use parameterized tests for finite partitions, boundary cases, and explicit
  combinations where exhaustive enumeration is practical.
- Use property tests for invariants spanning generated inputs, operation
  sequences, orderings, or state transitions.
- Use bounded model checking when exhaustive exploration within explicit bounds
  materially strengthens confidence in memory, arithmetic, or transition
  safety.
- Use state-machine model checking for protocols, concurrent actors, retries,
  and temporal or ordering properties.
- Use a formal prover for introduced lemmas, contractual business logic, or
  obligations whose required guarantee applies to all admissible inputs.
- Combine methods when no single technique covers both repository behaviour and
  the strongest invariant.

Any proof must be substantive, rigorous, and well-founded. A restatement of the
assumed property, a vacuous assertion, or finite examples presented as an
exhaustive argument do not discharge an obligation. If the change introduces
no non-trivial invariant or lemma, say so explicitly in the `Verification plan`
and justify that conclusion; do not omit the section.

### Avoid vacuous verification

For every obligation, explain why the verification can fail when the
implementation is wrong. A passing result is vacuous when, for example, an
unsatisfiable precondition excludes every input, a generator or filter never
reaches relevant cases, an implication's antecedent is never true, a model's
target states are unreachable, a bound excludes every meaningful transition,
or a proof merely assumes the conclusion.

Require a non-vacuity argument and evidence appropriate to the method:

- Exhibit at least one witness satisfying every precondition and exercise each
  material equivalence class, boundary, and transition named by the invariant.
- Record generator acceptance and classification evidence; treat excessive
  filtering, missing classes, or unreachable states as verification failures.
- Include a negative control, seeded fault, or representative mutation that the
  verification rejects for the intended reason. If this is impractical, state
  why and provide an independent counterexample or witness argument.
- For bounded or state-machine models, show that initial states exist, relevant
  transitions are reachable, and the chosen bounds admit the shortest
  interesting execution.
- For formal proofs, inspect the trusted assumptions and proof dependencies,
  demonstrate that antecedents are satisfiable, and reject proofs that derive
  the goal only from contradiction, an equivalent assumption, or an axiom added
  solely for the theorem.

Record the non-vacuity checks beside the obligation they protect, not as a
generic assurance at the end of the plan.

Do not plan to verify the internal correctness of third-party libraries or
tools. Treat their documented interfaces as axioms. However, when
repository-owned configuration logic builds upon such an interface, or safe
behaviour depends on non-trivial interaction with it, verify the
repository-owned logic against the real interface or a faithful contract-level
boundary. Record the exact external assumptions and the evidence that exercises
that boundary.

Capture evidence:

- When steps produce output, include concise transcripts as codefenced examples.
- Keep evidence focused on what proves success.

## Milestones are coherent plateaus

Every implementation milestone must end in a coherent, validated repository
state that is safe to continue from if later work is postponed. This plateau
requires correctness and internal coherence, not simultaneous support for the
old and new architecture. For each milestone, state its stable identifier,
assigned requirements or gaps, end state, acceptance evidence, conformance
check, recovery path, and remaining gaps.

Never introduce compatibility machinery solely to make a milestone
independently viable. Ask: "Would compatibility be required if this work were
made as one atomic change?" If not, update the interface and every affected
caller together. Plans MUST NOT prescribe source-API compatibility machinery
for any of the following surfaces:

- private APIs, including application-internal interfaces declared `public`;
- test-only APIs and support surfaces;
- pre-1.0 public APIs; and
- APIs introduced after the latest formal release tag.

For a released 1.0-or-later API without known external consumers,
compatibility is normally unnecessary, subject to explicit project policy. For
a released API with external consumers, preserve compatibility or plan a
deliberate migration only when an existing commitment requires it. Any
proposed compatibility layer must name the external consumer, deployed state,
compatibility commitment, or other concrete requirement that necessitates it.

Persisted and wire formats are separate from source API compatibility. A
private application may still need to migrate data written by an earlier
deployed version or communicate with an existing peer. Model that deployed
state explicitly rather than treating it as justification for unrelated API
shims.

Reject **compatibility theatre**: aliases, facade types, deprecated
entrypoints, dual implementations, adapters, migration wrappers, or temporary
shims added merely to create incremental milestones. If the plan cannot answer
"compatible with whom or what?", it must not prescribe the layer.

## Mandatory living sections (always present)

ExecPlans must contain, and must keep up to date as work proceeds:

- `Constraints` (hard invariants that must not be violated)
- `Tolerances (exception triggers)` (thresholds that trigger escalation when
  breached)
- `Risks` (known uncertainties with mitigations, identified upfront)
- `Progress` (with checkbox list and timestamps)
- `Surprises & discoveries` (unexpected findings during implementation)
- `Decision log` (every key decision with rationale)
- `Outcomes & retrospective` (what was achieved and lessons learned)
- `Conformance basis` (upstream revisions, identifiers, and trace links)
- `Verification plan` (obligations, axioms, methods, artefacts, and evidence)

If you change course mid-implementation:

- Document why in `Decision log`.
- Reflect the implications in `Progress` (what changed, what remains).
- Update `Risks` if new uncertainties have emerged.
- Update `Verification plan` if implementation structure, proof obligations, or
  external assumptions changed.
- Update `Conformance basis` and affected trace links if an upstream item,
  milestone, design element, or acceptance item changed.

## Exception handling (manage by exception)

When a tolerance threshold is reached, a constraint would be violated, or an
architecture deviation needs approval:

1. Stop implementation immediately.
2. Document the situation in `Decision log` with:
   - What threshold was reached or constraint threatened.
   - What options exist to proceed.
   - Trade-offs of each option.
3. Await explicit direction before proceeding.

Do not attempt to work around tolerances. They exist to catch situations where
human judgement is required.

## Reconcile discoveries before completion

Before setting an ExecPlan to `COMPLETE`, reconcile implementation discoveries
with every upstream artefact in the conformance basis:

- If a discovery falsifies a Terms of Reference assumption, update that
  artefact, impact-check the technical design, and revise the ExecPlan.
- If implementation changes the architecture, update the technical design or
  ADR and re-check every affected requirement and trace link.
- If a difference is mechanical and changes neither requirement nor
  architecture, record the rationale in `Decision log`.

Do not mark the plan `COMPLETE` while an upstream change or deviation remains
unrecorded or unaccepted.

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
