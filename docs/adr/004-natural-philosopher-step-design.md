# ADR 004: Natural Philosopher for evidence-led step design

**Status:** Proposed

## Context and sources

Repeated delegation needs a planning boundary before execution. Journeyman
owns an approved ExecPlan or a named, validated plateau. Artisan owns one
complete, bounded execution packet. Neither should invent the product bet
that authorizes its work. Alchemist already executes a single falsification
experiment; creating another experimental executor would duplicate that role.

The [roadmap-doc skill][roadmap-skill] and its [conventions][conventions] in
`leynos/df12-documentation-skills` define the planning model used here. This
proposal consulted revision `8372f538455d3ffc93f1315956c0ab752a9ea3ee`.
Phases carry ideas, steps represent coherent workstreams, and tasks provide
review-sized execution units. Existing role and deployment contracts live in
[`agents/subagents.yml`](../../agents/subagents.yml) and
[ADR 002](002-subagent-manifest-loader.md).

[roadmap-skill]: https://github.com/leynos/df12-documentation-skills/blob/8372f538455d3ffc93f1315956c0ab752a9ea3ee/skills/roadmap-doc/SKILL.md
[conventions]: https://github.com/leynos/df12-documentation-skills/blob/8372f538455d3ffc93f1315956c0ab752a9ea3ee/skills/roadmap-doc/references/conventions.md

## Decision

Add `natural-philosopher` to the existing provider-neutral manifest. Its unit
of responsibility is **one selected idea to evidence-led step proposals**,
including reassessment when delivery evidence challenges that idea.

The parent owns the goal, priorities, resources, and approval decisions. The
Natural Philosopher owns hypothesis quality, evidence design, and the proposed
sequence of learning and delivery. It does not own production implementation
or authorization to proceed. This adds no new manifest schema or renderer.

### GIST and delivery boundaries

A goal specifies the outcome and measures of value. An idea is the falsifiable
bet about how to advance that goal and corresponds to a roadmap phase. A step
is a workstream with one delivery objective, a question, and a consequence for
subsequent work. Tasks are concrete, measurable, traceable execution units,
each small enough for one realistic PR review.

A step need not equal an ExecPlan, a milestone, a GitHub issue, or a fixed
number of tasks. Preserve existing dotted identifiers and source links. New
identifiers, thresholds, and changes to an idea remain proposals until the
responsible parent accepts them. Do not quietly rewrite completed work.

The intended hand-off is:

```text
Parent: goal, selected idea, constraints, authority, and budget
  -> Natural Philosopher: hypotheses, evidence, and proposed steps
  -> Parent review and any required architecture decision
  -> Task planning: accepted task boundaries and ExecPlans
  -> Journeyman: approved ExecPlan or plateau
  -> Artisan: one complete bounded execution packet
```

The design does not require an Architect agent to exist. The responsible
parent routes architectural decisions through the repository's normal design
and ADR process. GitHub remains the execution and evidence ledger; Linear
remains the programme and capability map. A PR finishing is not evidence that
a capability or idea has succeeded, and this role does not mirror each GitHub
object into a Linear issue.

### Input contract

Supply the selected goal and idea, relevant source documents and revisions,
current roadmap IDs and status, known evidence, non-goals, architectural
constraints, and the decision needed. Specify the inquiry boundary, owned
document paths, resource limits, permitted research, and stop conditions.

Absent experiment authority means design only. Without explicitly owned
paths, the agent returns its proposal in the report rather than editing files.
It reads `roadmap-doc` and its conventions through an authorized source and
records the revision. Missing essential sources or normative decisions require
escalation. Ordinary uncertainty about how a system works does not: resolving
that uncertainty is the role's purpose.

### Hypothesis and step contracts

For each material hypothesis, distinguish facts, source claims, inferences,
assumptions, and unknowns. State the prediction, comparator, representative
workload, measures, falsification condition, and decision consequences.
Include the option of retaining the current behaviour where plausible.

Protect correctness and safety invariants as well as the desired improvement.
Set decision rules before trials; mark unapproved thresholds as proposals.
Account for confounders, coverage limits, and uncertainty. Prefer the cheapest
evidence that changes a decision, not an exhaustive research programme.

Each step proposal contains:

- Its identifier, parent idea, concrete outcome, question, and hypothesis.
- Invariants, scope, exclusions, source anchors, and dependencies.
- Evidence method, acceptance criteria, and falsification criteria.
- The decision it enables and the next action for a favourable, negative, or
  inconclusive result.

Keep dependencies acyclic and favour usable vertical slices. Foundational
work must retire an explicit contract or delivery risk. Preserve deferred
scope and account for relevant source obligations. Produce detailed candidate
tasks only when the assignment requires them or they establish feasibility.

Unit and behavioural tests, property tests, and formal verification accompany
implementation and its success criteria. End-to-end and combinatorial suites
may justify separate tasks. A separate proving or hardening task needs scope
that exceeds one realistic PR. Do not manufacture equally sized steps or
calendar promises.

### Research delegation and authority

When both the host and assignment permit it, the Natural Philosopher may ask
Wyvern for bounded reconnaissance or Alchemist for one explicit falsification
plan. Alchemist execution additionally requires experiment authority, defined
resource limits, and compatibility with Alchemist's own contract. A complete
child packet contains the objective, scope, inputs, source anchors, working
directory, permissions, evidence method, expected observations, success
criteria, exit clauses, and return format.

Children cannot redelegate. The Natural Philosopher inspects returned evidence
and retains responsibility for its interpretation. Source-anchored context
packs supplement complete packets; they cannot enlarge authority. Where the
host cannot delegate, return the packet for the parent instead of claiming an
experiment ran. Do not recursively spawn Natural Philosophers or commission
Journeyman or Artisan implementation.

The agent may edit only assigned design or roadmap documents. Production
code, tests, dependencies, and approved architecture remain outside that edit
boundary. Publishing, commits, issues, Linear changes, and other external
writes require explicit authorization. Stop affected work when scope, budget,
authority, concurrent changes, or an invalidated approved mandate prevents
safe continuation. Report useful partial findings and the smallest decision
needed; never hide a negative result or experiment past a stop condition.

### Completion and evidence

Return a `Step Design Report` with lineage, source revisions, a hypothesis
ledger, complete step proposals, dependencies, source coverage, deferrals,
decision gates, hand-off decisions, document changes, actual validations,
research consumption, risks, and context-pack IDs.

Keep the report state `ready-for-review | escalated` separate from hypothesis
verdicts `untested | falsified | not-falsified | inconclusive`. Recommendations
are `proceed`, `revise`, `defer`, or `stop`, not self-issued approval. A passing
experiment is not proof, and completed child tasks do not complete the idea.

### Provider choices and limits

Codex uses `gpt-5.6-sol`, medium reasoning effort, and `workspace-write`. Its
nickname pool draws on the natural philosophers who established evidence-led
inquiry, from Ibn al-Haytham to Faraday and Maxwell, matching the themed pools
the other Codex roles carry. Claude
uses `opus` with high effort and exactly `Read`, `Grep`, `Glob`, `Edit`, `Write`,
and `Task`. There is no direct Claude `Bash` grant. Its MCP allow-list contains
`context_pack`, `firecrawl`, `deepwiki`, and `codegraph` for grounded research.
Goose enables the same provider-neutral instructions.

As in ADR 002, Codex omits `mcp_servers` and Goose omits `extensions` to inherit
the credentialed parent registry. These inherited tools may exceed the role's
minimum needs. Workspace-write does not enforce document-only paths, and a
Task grant does not itself enforce the permitted child roster. The prose
contracts are behavioural constraints, not a new sandbox or security boundary.
Hosts must enforce their own permissions and delegation limits. This change
does not expand the authority of any existing role.

## Worked decision example

The following is illustrative, not a claim about this repository's results or
an instruction to create these roadmap entries.

Suppose the parent supplies a goal of reducing repeated setup cost without
weakening reproducibility, and selects the idea that reusing verified binary
artefacts can achieve that outcome. The Natural Philosopher first anchors the
current design, records the absence of measurements, and proposes a comparator
and acceptance threshold for parent review.

A first step could deliver one complete cache-backed setup path and answer
whether a clean consumer restores the correct binary under representative
cold, warm, stale, and corrupt-cache conditions. Correct identity, checksum
verification, and safe failure remain invariants. Its implementation tasks
include their ordinary unit and behavioural checks; a justified interaction
suite may warrant its own review-sized task.

A subsequent step could extend that verified path to another supported
consumer and test whether the cost benefit generalizes. It depends on the
first step's evidence, not just its merged PR. A wrong restored binary defeats
the first step's safety claim. No cost improvement defeats the proposed
benefit at the agreed threshold. Noisy measurements remain inconclusive and
justify only bounded further inquiry. The parent decides whether to revise or
stop before authorizing broader rollout.

## Validation and review scenarios

`tests/test_natural_philosopher.py` uses the existing manifest loader to check
uniqueness, state, all provider blocks, exact Claude grants, inheritance, and
load-bearing GIST, evidence, delegation, and escalation wording. The existing
generic inheritance tests also discover the new entry automatically. The
Makefile discovers the new `tests/test_*.py` file without configuration changes.

These checks detect configuration and prompt regressions. They do not prove
model compliance or validate downstream provider rendering. Review the role
against the following scenarios before relying on autonomous inquiry:

- A well-scoped idea produces coherent steps and decision criteria, not a
  production patch or an unapproved full-project ExecPlan.
- Missing goal authority causes escalation; an unknown performance mechanism
  causes permitted investigation, not invented measurements or paralysis.
- Negative or inconclusive evidence survives the report unchanged and affects
  the recommendation without moving the acceptance threshold.
- No experiment permission, an exhausted budget, or no delegation tool causes
  a report or parent hand-off, not an unauthorized trial or invented child run.
- A child claiming completion without decisive evidence cannot establish a
  step, idea, goal, or Linear capability as complete.
- A proposed vertical slice preserves existing IDs, includes implementation
  verification, exposes cross-step dependencies, and leaves deferred scope out.

## Consequences

The delegation hierarchy gains an explicit owner for learning and step design
without weakening the delivery roles. The costs are a larger prompt contract,
parent approval at material decision points, and reliance on host enforcement
for file and child-agent permissions. Live-model evaluation and provider-level
security controls remain outside this manifest change.
