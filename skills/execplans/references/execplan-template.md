# <Roadmap item, if any> <short, action-oriented description>

This ExecPlan (execution plan) is a living document. The sections `Constraints`,
`Tolerances`, `Risks`, `Progress`, `Surprises & discoveries`, `Decision log`,
`Outcomes & retrospective`, `Conformance basis`, and `Verification plan` must
be kept up to date as work proceeds.

Status: DRAFT | APPROVED | IN PROGRESS | BLOCKED | COMPLETE

Branch: `<branch-name>`

Roadmap item: `<identifier>` in `<repository-relative roadmap path>`, or none.

Use one current status, with a short qualification if needed (for example,
`DRAFT (design review applied; awaiting user approval)`). Replace the prompts
below with repository-specific facts, commands, and expected results. Keep the
mandatory sections; state explicitly when an item does not apply. The completed
plan must stand alone without the example plan or a previous conversation.

## Purpose / big picture

Introduce the project and the affected behaviour in plain language. Show a
small, realistic input or caller example, explain what happens today, and show
what the same user can observe after the change. Define terms as they appear.
State which existing behaviour is preserved and any deliberately changed error
or diagnostic behaviour. Name the outstanding roadmap or design decision this
work closes, if there is one.

## Constraints

Hard invariants that must hold throughout implementation. These are not
suggestions; violation requires escalation, not workarounds.

- Paths/modules this plan must not modify.
- Public interfaces that must remain stable.
- Compatibility requirements (language versions, platforms, targets).
- Security or compliance considerations that constrain approach selection.
- Repository-specific limits on file size, complexity, module layout, and
  error handling, with the governing path or section.
- Authorized dependency and API changes, including whether callers change
  together and whether any deployed consumer requires compatibility.
- Historical documents that must remain untouched.
- Implementation begins only after the user approves the plan, unless existing
  standing instructions already authorize execution.

If satisfying the objective requires violating a constraint, do not proceed.
Document the conflict in `Decision log` and escalate.

## Tolerances (exception triggers)

Thresholds that trigger escalation when breached. These define the boundaries
of autonomous action, not quality criteria. State the comparison base and exact
counting commands, including path exclusions. Define separate limits for code,
configuration, and documentation changes. State whether each measures net lines
(additions minus deletions) or churn (additions plus deletions). Exclude
ExecPlan files from every size count, including this file when added or updated.

Set budgets only after surveying existing code, comments, and documentation.
Use the affected callers, tests, integration points, configuration, and live
guidance to estimate the complete change. Review relevant past ExecPlans and
their revision or decision history for budgets increased multiple times. Record
the original limits, increases, and causes where available, or state that no
comparable history exists. Explain how this evidence informs each initial
category budget and its contingency. Revisit scope or milestone decomposition
where earlier plans repeatedly underestimated the work; historical increases do
not authorize exceeding the approved budget during execution.

Classify changes by purpose: production source, tests, and executable build or
automation logic are code; declarative settings, manifests, lockfiles,
deployment descriptors, and CI workflow configuration are configuration; prose,
guides, and reference material are documentation. Assign each counted change to
one category only. For mixed files, classify changed hunks by purpose or state
a consistent whole-file rule. Under hunk-based accounting, embedded executable
logic counts as code. List category paths and any generated-file exclusions.

- Files: if implementation changes more than `<N>` non-ExecPlan files, stop and
  escalate. Exclude this ExecPlan file from the count.
- Code: if changes exceed `<C>` net lines of code, stop and escalate.
- Configuration: if changes exceed `<G>` net lines of configuration, stop and
  escalate.
- Documentation: if changes exceed `<D>` net lines of documentation excluding
  ExecPlan files, stop and escalate.
- Interface: if a public API change beyond those authorized in `Constraints`
  is needed, stop and escalate.
- Dependencies: if a dependency beyond those authorized in `Constraints` is
  needed, stop and escalate.
- Architecture: if the work requires changing
  `<protected boundary or design decision>`, stop and escalate.
- Iterations: if tests still fail after `<K>` attempts, stop and escalate.
- Time: if a milestone takes more than `<T>` hours, stop and escalate.
- Ambiguity: if multiple valid interpretations exist and the choice materially
  affects the outcome, stop and present options with trade-offs.

Enforce each category independently. Spare capacity or deletions in one
category must not offset another category exceeding its limit. Any overall
line-count limit is additional to these budgets. Replace net lines with churn
above if that is the chosen metric, and state any category-specific file-count
limits.

Adjust these values based on the task. Small, well-understood changes warrant
tighter tolerances; exploratory work may need looser ones.

## Risks

Known uncertainties that might affect the plan. Identify these upfront and
update as work proceeds. Each risk should note severity, likelihood, and
mitigation or contingency.

- Risk: `<description>`
  Severity: low | medium | high Likelihood: low | medium | high Mitigation:
  `<how to prevent or reduce impact>`.

Risks differ from Surprises: risks are anticipated; surprises are not.

## Progress

Use a list with checkboxes to summarize granular steps. Every stopping point
must be documented here, even if it requires splitting a partially completed
task into two ("done" vs. "remaining"). This section must always reflect the
actual current state of the work.

- [x] (<YYYY-MM-DD HH:MMZ>) Reconnaissance and initial draft completed.
- [ ] Plan approved by the user.
- [ ] `EP-M1` <first coherent implementation outcome>.
- [ ] `EP-M2` <next coherent implementation outcome>.
- [ ] `EP-M3` <documentation and delivery closure>.
- [ ] <Partially completed step: completed X; remaining Y>.

Use timestamps to measure rates of progress and detect tolerance breaches.

## Surprises & discoveries

Unexpected findings during implementation that were not anticipated as risks.
Document with evidence so future work benefits.

- Observation: `<what was unexpected>`.
  Evidence: `<how this is known>`. Impact:
  `<how it affects this plan or future work>`.

## Decision log

Record every significant decision made while working on the plan. Include
decisions to escalate, decisions on ambiguous requirements, and design choices.
For an architecture deviation, name the affected upstream identifiers, impacts,
options, required upstream-document changes, and approving authority. Set the
plan status to `BLOCKED` until the deviation is accepted.

- D1. Decision: `<what was decided>`.
  Rationale:
  `<why this choice over the strongest alternative, including the
  rejected option and any future migration path>`.
  Date/Author: `<timestamp and who decided>`.

Reuse these decision identifiers where a constraint, milestone, or verification
choice depends on them. Record review-driven revisions and their rationale.

## Outcomes & retrospective

Summarize outcomes, gaps, and lessons learned at major milestones or at
completion. Compare the result against the original purpose. Note what would be
done differently next time. Before marking the plan `COMPLETE`, reconcile every
implementation discovery with the upstream artefacts listed in
`Conformance basis`: update a falsified Terms of Reference assumption and
impact-check the design; update the technical design or ADR for an
architectural change; or record a purely mechanical difference in
`Decision log`. An upstream change or deviation must not remain unrecorded or
unaccepted at completion.

Once the original implementation has merged, a completed plan is a historical
document reflecting the repository state at the time of implementation. Later
changes that affect the plan do not require retroactive updates to it.

## Context and orientation

Describe the current pipeline or control flow before proposing changes. Name
the owning modules, entrypoints, helpers, callers, and tests with full
repository-relative paths and exact symbol names. Explain existing error
channels, data ownership, and boundaries relevant to the change. Define any
non-obvious term you will use. Do not rely on prior plans.

Record the inspected base revision. If line numbers are useful, qualify them
with that revision and give a search command to relocate the symbols. List
existing test frameworks and relevant versions, fixtures, regression artefacts,
and gate commands. Distinguish tools installed on the host from tooling the
repository actually configures. Signpost relevant documentation and skills,
while including the facts needed to execute this plan here.

Include the budget-setting survey of existing code, comments, and
documentation. Name comparable historical ExecPlans, their relevant budget
revisions, and what caused repeated increases. Distinguish missed scope from
approved scope growth and repository constraints. Read completed plans as
evidence without changing them. Link these observations to the initial
estimates in `Tolerances`.

## Conformance basis

Treat this plan as a lightweight architecture contract. Name the exact Terms of
Reference revision, technical-design revision, ADRs, governing standards, and
relevant requirement or design-element identifiers. If an upstream artefact
does not exist, say so; do not invent one.

Record the revision inspected for each upstream artefact. Derive a short set of
named requirements (`REQ-<name>`) and observed gaps (`GAP-<name>`), each with a
precise statement. Keep these separate from the documents that justify them.

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

### Abstract model

Define the smallest model needed to reason about this change: inputs, states,
ranges, transitions, or ordering rules. State preconditions and the expected
result. Explain how malformed inputs or violated preconditions are handled. Use
precise notation only where it makes the contract clearer, and define it.

### Invariants and lemmas

Give each important invariant a stable `INV-<name>` identifier and each lemma an
`L-<name>` identifier. Link them to the requirements they establish. Phrase
them as claims about observable values or transitions, including absence,
failure, boundary, and independence cases where relevant. These are obligations
to establish, not assumptions that the implementation is already correct.

### Axioms (trusted, not verified here)

List the non-trivial axioms on which the reasoning depends. Include assumptions
about runtimes, platforms, external services, and third-party interfaces. Do
not attempt to verify third-party internals. Where repository-owned
configuration or integration logic depends on an external interface, plan
verification against the real interface or a faithful contract-level boundary.

Give each assumption an `AXIOM-<name>` identifier, its source or documented
contract, and the repository boundary that depends on it.

### Methods per obligation

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
reachable within meaningful bounds, and proof antecedents are inhabited. Plan a
negative control, seeded fault, or representative mutation that must be
rejected for the intended reason. If a negative control is impractical, justify
that exception and provide independent counterexample or witness evidence.
Treat excessive filtering, missing classifications, unreachable model states,
zero-work bounds, contradiction, or assuming the conclusion as verification
failures rather than successful evidence.

Where generated tests are used, define an oracle independent of the code being
tested. Name the important generated classes and how coverage is demonstrated;
do not compare two outputs derived from the same implementation and call that
agreement. Record seeds and regression-file handling. For temporary seeded
faults, specify the expected rejection, how the fault is reverted, and which
generated artefacts must be removed afterwards.

### Formal verification decision

State whether model checking or formal proof is needed and why the selected
methods are proportionate to the risk. Explain what stronger methods would add
and which boundaries they would leave unverified. Record the decision in
`Decision log`; tool availability alone is not a justification.

### Suggested BDD features

Suggest BDD features that clarify observable acceptance behaviour. BDD means
behaviour-driven development. Name a proposed feature file path and link each
scenario to requirements, milestones, and acceptance evidence. Include the main
user outcome and material failure or boundary cases. Replace this illustrative
feature with concrete inputs and outcomes:

```gherkin
Feature: <observable capability>
  Scenario: <main user outcome>
    Given <a concrete initial state>
    When <the user performs an action with specific input>
    Then <a specific observable result occurs>
```

Label suggestions as proposed until adopted. If the repository has no BDD
runner, state how existing tests or manual checks exercise these scenarios;
adding a framework or dependency requires separate authorization. Where BDD is
adopted, give the runner command and keep the feature synchronized with the
implementation and Red-Green-Refactor evidence.

## Plan of work

Describe, in prose, the sequence of edits and additions. For each edit, name
the file and location (function, module) and what to insert or change. Keep it
concrete and minimal.

Organize work by numbered, outcome-named milestones. Add or repeat the
following subsections as needed; keep the same identifiers in `Progress`,
`Conformance basis`, commands, and acceptance evidence.

### `EP-M0` feasibility probe (optional prototype)

Use a probe only to resolve a named uncertainty. State the question, exact
command or scratch artefact, expected observations, and the go/no-go decision
they support. Say whether the prototype is deleted, retained, or promoted.
Record its transcript in `Artefacts and notes`. Planning-time reconnaissance
does not authorize implementation before approval.

### `EP-M1` <first coherent implementation outcome>

Name the assigned requirements, gaps, and decisions. Describe the owning files,
symbols, and every affected caller. Give the red test or BDD specification and
smallest verification artefact that fails for the intended reason, then the
minimal implementation and refactor steps. State exact focused commands and
expected results. Keep tests and implementation in the same coherent plateau.

### `EP-M2` <next coherent implementation outcome>

Describe the next complete behaviour, its integration points, and its
Red-Green-Refactor sequence. If property or behavioural verification is
expanded here, identify the obligations it discharges and the coverage left by
earlier milestones. Do not postpone the tests needed to establish `EP-M1`
correctness.

### `EP-M3` documentation and delivery closure

Name the live guides, ADR sections, changelog entry, and roadmap checkbox to
update, where applicable. State which deferred decisions are superseded or
closed. Give any search used to find stale claims and explicitly exclude
historical completed plans. Run the wider gates and reconcile upstream
artefacts before marking the work complete.

Each milestone ends with validation. Do not proceed to the next milestone if
the current milestone's validation fails.

## Milestones and plateaus

Define each implementation milestone as a coherent, validated repository state
that is safe to continue from if later work is postponed. A plateau requires
correctness and internal coherence, not simultaneous support for old and new
interfaces. For each milestone record:

- Identifier and outcome: `<EP-M1 and the coherent end state>`.
- Requirements and gaps: `<upstream identifiers discharged or advanced>`.
- Acceptance evidence: `<observable behaviour and stable evidence identifier>`.
- Conformance check, one line per item:
  - `<requirements satisfied>`.
  - `<design still followed>`.
  - `<upstream assumptions still valid>`.
  - `<no unapproved public interface or dependency change>`.
  - `<no unapproved trust boundary or persisted-format change>`.
  - `<trace links current>`.
- Recovery: `<how to retry, revert, or safely continue>`.
- Remaining gaps: `<work deliberately left for later milestones>`.
- Compatibility decision, one of:
  - `<none>`.
  - `<the named consumer or deployed state that requires compatibility>`.
  - `<the commitment or migration requirement that requires compatibility>`.

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
Group focused commands by milestone and distinguish red from green results.
Replace this illustrative transcript with the repository's actual commands:

```plaintext
Working directory: <repository root>
Red: <focused command> -> <specific assertion failure or missing-symbol error>
Green: <same focused command> -> <passing result and expected case count>
Refactor: <focused command and relevant wider gates> -> <passing results>
```

List the repository gate sequence as runnable commands in its required order,
preferring Makefile targets. If output is piped through `tee`, enable
`pipefail` in the executing shell so a failed gate cannot appear to pass. Name
the log paths. Record known baseline or host-specific failures separately from
regressions, with evidence and a recovery path; do not quietly waive a gate.
This section must be updated as work proceeds.

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
requires an unplanned invariant, lemma, or axiom must return to
`Verification plan` before further elaboration.

At each milestone boundary, record the focused architecture-conformance check
from `Milestones and plateaus`. If implementation evidence requires an
unapproved design departure, record the proposed deviation and affected
identifiers in `Decision log`, set the status to `BLOCKED`, and obtain explicit
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

Label evidence by milestone, command, and revision. Distinguish observations
already obtained during reconnaissance from expected implementation results.
Include probe results, red/green evidence, and negative-control transcripts;
record cleanup of temporary faults and generated regression artefacts.

## Interfaces and dependencies

Be prescriptive. Name the libraries, modules, and services to use and why.
Specify the types, traits/interfaces, and function signatures that must exist
at the end of the milestone. Prefer stable names and paths such as
`crate::module::function` or `package.submodule.Interface`.

State ownership, exports, error contracts, and relevant source locations. Name
existing helpers to reuse and explain any deliberate non-reuse. Specify a reuse
policy: which layer owns the new abstraction, how callers access it, and where
parallel implementations or reparsing would violate the design. List authorized
dependencies with versions, requirement syntax, and runtime or development
scope, or explicitly state that none are needed.

E.g., in crates/foo/planner.rs, define:

```rust
pub trait Planner {
    fn plan(&self, observed: &Observed) -> Vec<Action>;
}
```

## Revision note

- <YYYY-MM-DD>: <what changed, why it changed, and how it affects remaining
  work>.

Append a dated entry for each revision. For review or rebase updates, name the
reconciled base or conventions and say whether the API, obligations, milestone
order, or remaining scope changed. Update the status and all affected sections.
