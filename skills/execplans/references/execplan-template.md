# `<Short, action-oriented description>`

This ExecPlan (execution plan) is a living document. The sections
`Constraints`, `Tolerances`, `Risks`, `Progress`, `Surprises & Discoveries`,
`Decision log`, `Outcomes & retrospective`, `Conformance basis`, and
`Verification plan` must be kept up to date as work proceeds.

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
For an architecture deviation, name the affected upstream identifiers, impacts,
options, required upstream-document changes, and approving authority. Set the
plan status to `BLOCKED` until the deviation is accepted.

- Decision: `<what was decided>`
  Rationale: `<why this choice over alternatives>`
  Date/Author: `<timestamp and who decided>`.

## Outcomes & retrospective

Summarize outcomes, gaps, and lessons learned at major milestones or at
completion. Compare the result against the original purpose. Note what would be
done differently next time. Before marking the plan `COMPLETE`, reconcile every
implementation discovery with the upstream artefacts listed in `Conformance
basis`: update a falsified Terms of Reference assumption and impact-check the
design; update the technical design or ADR for an architectural change; or
record a purely mechanical difference in `Decision log`. An upstream change or
deviation must not remain unrecorded or unaccepted at completion.

Once the original implementation has merged, a completed plan is a historical
document reflecting the repository state at the time of implementation. Later
changes that affect the plan do not require retroactive updates to it.

## Context and orientation

Describe the current state relevant to this task as if the reader knows
nothing. Name the key files and modules by full path. Define any non-obvious
term you will use. Do not refer to prior plans.

## Conformance basis

Treat this plan as a lightweight architecture contract. Name the exact Terms of
Reference revision, technical-design revision, ADRs, governing standards, and
relevant requirement or design-element identifiers. If an upstream artefact
does not exist, say so; do not invent one.

Use stable identifiers only for important traced items. Map each applicable
upstream requirement and baseline-to-target gap through its milestone to
observable evidence, for example:

```plaintext
TOR-GOAL-004 -> TDD-REQ-012 -> TDD-COMP-queue-store -> EP-M3 -> tests::queue::persists_reordering
```

When a traced item changes, identify and record its upstream and downstream
impacts before accepting the change, then update every affected link.

## Verification plan

Co-design verification with the implementation rather than adding it after the
implementation structure is fixed. State every invariant over inputs, states,
orderings, or transitions that the planned implementation introduces or
preserves. State every lemma or intermediate contract required to connect those
invariants to the required behaviour.

List the non-trivial axioms on which the reasoning depends. Include assumptions
about runtimes, platforms, external services, and third-party interfaces. Do
not attempt to verify third-party internals. Where repository-owned
configuration or integration logic depends on an external interface, plan
verification against the real interface or a faithful contract-level boundary.

For each invariant and lemma, specify:

- Obligation: <stable name and precise statement>.
- Method: <parameterized test, property test, bounded model check, state-machine
  model check, formal proof, or justified combination>.
- Rationale: <why this method provides proportionate rigour>.
- Domain: <inputs, states, transitions, generated cases, or explicit bounds>.
- Artefact: <repository-relative test, harness, model, or proof path>.
- Evidence: <command, expected initial failure or counterexample, and discharge
  condition>.
- Non-vacuity: <satisfying witnesses, exercised classes or reachable states, and
  the negative control or mutation that must be rejected>.

Use parameterized tests for finite partitions and explicit combinations;
property tests for ranges of inputs, sequences, orderings, or transitions;
bounded model checking for exhaustive exploration within meaningful bounds;
state-machine model checking for protocols, concurrency, and temporal
properties; and formal proofs for introduced lemmas or contractual business
logic requiring guarantees over all admissible inputs. Combine methods when
necessary. State bounds, abstractions, and residual gaps explicitly.

Any proof must be substantive, rigorous, and well-founded, not a restatement of
an assumed property or a vacuous assertion. If this change introduces no
non-trivial invariant or lemma, record that conclusion and its rationale here;
do not omit this section.

For each obligation, explain why the verification can fail when the
implementation is wrong. Show that preconditions are satisfiable, generators
reach material classes and boundaries, model states and transitions are
reachable within meaningful bounds, and proof antecedents are inhabited. Plan
a negative control, seeded fault, or representative mutation that must be
rejected for the intended reason. If a negative control is impractical, justify
that exception and provide independent counterexample or witness evidence.
Treat excessive filtering, missing classifications, unreachable model states,
zero-work bounds, contradiction, or assuming the conclusion as verification
failures rather than successful evidence.

## Plan of work

Describe, in prose, the sequence of edits and additions. For each edit, name
the file and location (function, module) and what to insert or change. Keep it
concrete and minimal.

Structure as stages with explicit go/no-go points where appropriate:

- Stage A: understand and propose (no code changes)
- Stage B: red tests or BDD feature specification plus the smallest verification
  artefacts that fail, find a counterexample, or leave the proof obligation open
  for the expected reason
- Stage C: implementation and verification scaffold developed together to
  discharge the planned obligations
- Stage D: refactor, documentation, proof cleanup, and wider validation

Each stage ends with validation. Do not proceed to the next stage if the
current stage's validation fails.

## Milestones and plateaus

Define each implementation milestone as a coherent, validated repository state
that is safe to continue from if later work is postponed. A plateau requires
correctness and internal coherence, not simultaneous support for old and new
interfaces. For each milestone record:

- Identifier and outcome: `<EP-M1 and the coherent end state>`.
- Requirements and gaps: `<upstream identifiers discharged or advanced>`.
- Acceptance evidence: `<observable behaviour and stable evidence identifier>`.
- Conformance check: `<requirements satisfied; design still followed; upstream
  assumptions still valid; no unapproved public interface, dependency, trust
  boundary, or persisted-format change; trace links current>`.
- Recovery: `<how to retry, revert, or safely continue>`.
- Remaining gaps: `<work deliberately left for later milestones>`.
- Compatibility decision: `<none, or the named consumer, deployed state,
  commitment, or migration requirement that makes compatibility necessary>`.

Never introduce compatibility machinery merely to create an incremental
milestone. If compatibility would not be required for one atomic change, update
the interface and all affected callers together. Plans MUST NOT prescribe
source-API compatibility layers for private or application-internal APIs,
test-only surfaces, pre-1.0 APIs, or code ahead of the latest formal release
tag. For released 1.0-or-later APIs, inherit compatibility only from an actual
external consumer or explicit project commitment. Persisted and wire formats
are separate: deployed data or peers may require a migration even when source
compatibility does not.

Do not prescribe aliases, facade types, deprecated entrypoints, dual
implementations, adapters, migration wrappers, or temporary shims unless the
plan can answer "compatible with whom or what?" and trace the answer to a real
requirement.

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

For verification obligations, record the command and the initial failure,
counterexample, open goal, or model-checking result. After implementation,
record the passing result, explored bounds where applicable, axioms relied on,
and any obligation that remains undischarged. An implementation change that
requires an unplanned invariant, lemma, or axiom must return to `Verification
plan` before further elaboration.

At each milestone boundary, record the focused architecture-conformance check
from `Milestones and plateaus`. If implementation evidence requires an
unapproved design departure, record the proposed deviation and affected
identifiers in `Decision Log`, set the status to `BLOCKED`, and obtain explicit
acceptance before continuing.

Quality criteria (what "done" means):

- Tests: `<what must pass>`
- Verification: `<which invariants and lemmas must be discharged, and how>`
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
