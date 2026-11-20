# Lessons from modelling the PR babysitting skill

Status: a case study, written as input to a later document on requisite
modelling of multi-system skills at agent-skill maturity tier 2. It is not that
policy, it defines no maturity tier, and it certifies nothing about the
`pr-babysitting` skill. It reports what one modelling exercise found, what it
cost, and what a policy author might take from it.

Revisions described: the skills as merged at `006e8d5` (which contains pull
request (PR) #272, merged as `9dec88c`); the specification under
`specs/pr-readiness/` as introduced by the branch `pr-readiness-fizzbee-spec`;
and FizzBee v0.5.4, the `linux_x86` release archive with SHA-256 digest
`8a1d0900f9ad920002151922337912e11f9e588a2f1196249fe40bf75370f782`. Figures
were measured on the development host, a 24-processor Linux machine that was
heavily loaded by other work at the time, so wall-clock times are upper bounds
and not benchmarks.

## Problem and original assurance

The motivating failure was a PR that left draft while it delivered part of an
approved plan. Its completeness assessment had been asked about the declared PR
scope, cleared for that scope, and read as clearance for the plan. PR #272
closed the gap in the skill text: only a whole-plan verdict clears the
draft-to-ready gate, and every verdict is bound to the candidate and to the
approved plan revision it was given for.

The workflow that rule lives in crosses five things that change independently
and answer to different authorities:

- the PR on GitHub, whose head and base anyone with push access can move;
- the approved plan revision, which the plan's approver changes;
- hosted continuous integration (CI) and CodeScene, which report on what was
  pushed, and the local CodeScene delta, which reports on a checkout;
- the assessment conversation, in which a review service answers late, may
  edit an answer in place, and shares a thread with other authors; and
- the agent's own session, which can end between any two steps and resumes
  with only what it wrote down.

The skills are Markdown, so nothing executes the rule. PR #272 therefore added
four kinds of assurance, and each established something different.

- **A Python specification.** `tests/pr_readiness_model.py` restated the gate
  as a function from one snapshot of facts to a decision and a reason;
  `tests/pr_readiness_workflow.py` wrapped it in a sequence against in-memory
  doubles. This established that the rule, as its authors understood it, was
  consistent and decidable for one snapshot, and it found real defects in its
  own drafts: an assignment requiring completeness with no approved revision
  once cleared on its base/head alone, and a reply declaring itself not
  applicable once skipped every other check.
- **Property tests.** Hypothesis generated states by starting from one that
  satisfied every condition and breaking named conditions, after a uniform
  generator had let a mutant that accepted a stale plan revision pass every
  example. This established soundness and completeness of the Python function
  against an oracle written from the prose, and it is the origin of the "break
  one named thing" discipline the new suite keeps.
- **Document checks.** Tests read the shipped Markdown, section by section,
  and failed when a clause was removed or moved under an unrelated heading.
  Every decision reason in the Python model cited a sentence that had to
  remain. This established that the contract is still stated, and where.
- **Sandboxed rehearsals.** A headless agent ran against the shipped skill
  text and a stand-in GitHub surface, in a network and mount sandbox built
  after an unmasked run posted to a live PR. This established what a sampled
  agent run does with a given set of facts.

None of that work is made worthless by a change of language. The snapshot
answers of the Python model are the expectations of the snapshot tables the new
suite checks, the document checks and rehearsals are retained unchanged, and
the Python work's own lesson about generators shaped the controls.

What the Python specification could not express is time. Its unit was a
snapshot: it could say whether a set of facts permits the transition, and not
what happens when a fact changes between the agent reading it and the agent
acting on it, what survives an interrupted session, or whether a blocked
workflow can still make progress.

## Modelling boundary and abstraction

The specification is `specs/pr-readiness/readiness.fizz`, with a second, small
file, `stack.fizz`, for the managed-stack conflict. Its
[README](../specs/pr-readiness/README.md) is the reference; this section
records which choices mattered.

**Actors.** The agent; the environment that moves the head, base, plan revision
and proof inventory; the checks; the local CodeScene tool; the assessment
service; any other comment author; and whatever interrupts a session.

**State, in four layers that never stand in for each other.** Authority is the
accepted assignment: which assessments apply, the authorized stopping point,
and whether the layer implements the whole plan. Reality is the remote
candidate, the checks and the thread. Observation is what the agent has read
and holds in memory. Evidence is the durable ledger. An action reads reality
only where it stands for the corresponding API call or command.

**Events.** Each agent step is one atomic action: read the PR, read the plan
and inventory, read the checks, run the local delta, inspect the discussion,
post a question, read the replies, re-fetch the candidate, decide, issue the
ready or merge command, and read it back. The environment may act between any
two of them.

**Properties.** Safety at a transition is a transition assertion over the state
before the step. Safety of a state is an invariant. Reachability is an `exists`
assertion per permitted assignment. Conditional progress is one
`eventually always` assertion, checked under strict liveness.

**Atomicity.** One API response is one step. Read, decide, command and verify
are never one step, because the commands that exist are not conditional on what
was read: `gh pr ready` takes no expected head, and
`gh pr merge --match-head-commit` is conditional on the head alone. Both facts
were checked against `gh` 2.97.0 before the model attributed anything to them.

**Fairness.** Agent steps, check completion, service replies and outage
recovery are weakly fair. Strong fairness was verified to work in the pinned
release and deliberately not used: making an outage transient through a budget
states the assumption more plainly than assuming the agent eventually retries
at a lucky moment.

**Faults.** Interruption is an explicit action that discards the agent's memory
and keeps the ledger and the remote. It also stands for a command whose
response was lost. FizzBee's built-in crash injection was verified and not
used, because it discards a thread without resetting the variables that model
the agent's memory.

**Bounds.** One shared budget of one change covers head, base, revision and
inventory in the routine suite; identities only increase, so a superseded value
cannot become current again. Interruptions are bounded at one or two, outages
at one, and a reply is edited at most once. Inventories hold at most two proofs.

**Excluded.** The formal review, review threads and approval; rebase and stack
mechanics; candidate trust; comment identities; the content of a plan or a
proof; how a repair is made; and whether any verdict is justified.

Distinctions that changed a result:

- **Observation against reality.** Two of the first properties were wrong
  because they compared a record with reality at the instant of writing. Once
  observation was a layer of its own, the same separation produced the expected
  counterexamples below.
- **Hosted against local CodeScene.** The Python model had one CodeScene fact.
  Keeping the hosted findings, the local result and the tree the local result
  was run on apart is what made "hosted green cannot stand in for an
  unavailable local run" and "a clean delta clears only its own tree" checkable
  at all.
- **A request's identity against its marker.** The agent correlates a reply by
  marker; the properties compare the recorded request with the candidate. That
  difference is what lets a mutation of one be caught by the other.
- **Ephemeral against durable.** Request correlation survives interruption
  because the thread is durable and is re-read, not because the agent remembers
  a marker.
- **A subscripted proof inventory with two members.** One proof cannot be
  partly covered.

Details that added only cost: separate steps for the plan read and the PR read
multiplied states without producing a finding beyond the one a single combined
read would have shown; modelling both base and head as independent counters
found nothing that head alone did not, apart from the base-specific merge
counterexample; and reply shapes for every way a reply can fall short were
worth having in the snapshot tables and expensive in the temporal
configurations, where three shapes found everything ten did.

## Findings and counterexamples

Each finding gives the claim, a witness, the obligation affected (identifiers
are those of `specs/pr-readiness/obligations.toml`), the consequence, the
resolution or residue, and where to reproduce it. Run identifiers are those of
`specs/pr-readiness/suite.toml`; `make model-check` reproduces all of them and
writes each trace under `build/model-check/<run>/trace.txt`.

### Known regressions reproduced

**R1. The snapshot decisions agree.** For 215 bounded snapshots, the Python
decision model and the FizzBee model give the same answer: four permit the
transition and 211 hold the draft. The set is four assignments, every thread
state of each applicable assessment crossed with each other, every single
delivery failure, and the scope errors. Obligations: `PRR-ELIG-01`,
`PRR-APPL-01` to `PRR-APPL-05`, `PRR-BIND-01`, `PRR-BIND-02`, `PRR-DELIV-01` to
`PRR-DELIV-03`. Evidence: the comparison script is in commit `7e1b74f` as
`tests/pr_readiness_migration_compare.py`, with the Python model it calls; the
71 single-deviation rows are the routine run `snapshot-regression-table` and
the whole set is the extended run `snapshot-comparison-table`. There was no
disagreement to investigate. Two Python cases have no counterpart because they
were properties of that model's own strings: whitespace around a revision
identifier, and inventories that join to the same comma-separated text.

**R2. Every guard is needed.** Each rule the Python model paired with a
monkeypatched mutant has a textual mutation of the specification that must fail
one named assertion through a counterexample that uses the behaviour the
control names. For example, with the whole-plan subject rule deleted, the
checker reports `ReadyNeedsCurrentEvidence` on a trace containing
`Any:shape="subset-clear"`. Evidence: the 31 `mutant-*` runs.

**R3. The recordings are the snapshots the model was checked on.** Each of the
eleven agent-boundary recordings, read through the shipped stand-in, abstracts
to a model snapshot whose checked expectation matches what the recorded agent
did. Evidence: `tests/test_readiness_handoff_boundary.py` and the routine run
`fixture-snapshots`.

### Newly found protocol limitations

**L1. The ready transition can take effect on a candidate nothing was assessed
for.** Witness, from `expected-counterexample-head-moves-before-ready`:

```plaintext
AgentReadsReplies -> AgentRechecksCandidate -> HeadChanges -> AgentDecides
-> AgentRunsReadyCommand
```

The agent re-fetched the candidate, the head moved, and the command marked the
new head ready. Obligation: `PRR-TOCTOU-01`. Consequence: the PR is ready, and
stays ready by rule, at a head with no assessment; the read-back detects the
move and the ledger records an observed, not a verified, transition, and the
merge still needs renewed evidence. Classification: a missing enforcement
capability, not an incorrect skill. `gh pr ready` and the GraphQL mutation
behind it take no expected head, so no ordering of reads closes the window.
Residue: unresolved by design, and recorded. The same class holds for the base
(`expected-counterexample-base-moves-before-ready`), for a proof joining the
inventory (`expected-counterexample-inventory-grows-before-ready`), and for a
reply edited from clear to not clear after it was read
(`expected-counterexample-reply-edited-before-ready`).

**L2. The plan revision's window is the whole pass, not the gap after the
re-fetch.** Witness, from
`expected-counterexample-plan-revision-moves-before-ready`:

```plaintext
AgentObservesPlanAndInventory -> PlanRevisionChanges -> ... ->
AgentRechecksCandidate -> AgentDecides -> AgentRunsReadyCommand
```

A new revision was approved immediately after the plan was read, eleven steps
before the command, and the documented re-fetch did not see it. Obligation:
`PRR-TOCTOU-01`, with `PRR-BIND-02`. Classification: an incomplete skill
contract. The waiting procedure says to "Re-fetch live base/head before
accepting the result"; the revision is part of the candidate by the same
contract and is not named there. Proposed narrow repair, not applied: name the
plan revision in force, and the proof inventory, alongside base/head in that
step. That would shrink this window to the size of L1's. It was not checked in
the model, and it would not close the window.

**L3. The merge guard protects the head and nothing else.** Witnesses:
`expected-counterexample-plan-revision-moves-before-merge`,
`expected-counterexample-base-moves-before-merge` and
`expected-counterexample-reply-edited-before-merge`, each ending
`AgentRechecksCandidate -> (change) -> AgentDecides -> AgentRunsMergeCommand`.
Obligation: `PRR-TOCTOU-02`. The skill's operations reference already says that
the head guard "protects against a changed PR head, not every possible base,
check, or review race", so this is a known limitation reproduced in a checkable
form, with one addition: the plan revision is among the things the guard does
not cover. The positive half is `merge-head-guard-closes-the-head-race`: when
only the head can change, the strong property holds for the merge, and removing
the guard (`mutant-merge-without-head-guard`) breaks it.

**L4. The re-fetch is stated only for a run that waited.** Witness, from the
recordings and not from the checker: in `current-whole-plan` the verdict was
already on the thread; the recorded agent read the PR, read the discussion and
ran `gh pr ready` with no second `gh pr view` between. The model re-fetches in
every pass and its property `ReadyFollowsFreshReads` requires it. Obligation:
`PRR-ORDER-01`. Classification: an ambiguity in the contract, found by mapping
a recording onto a model trace. The recorded run broke no stated rule; the
model implements the stricter reading. Residue:
`specs/pr-readiness/fixtures.toml` lists the step as unobserved for that
recording, with the reason, and `tests/test_pr_readiness_fixture_mapping.py`
fails if that stops being true. The policy owner should decide whether the
re-fetch binds every transition.

**L5. Whether an answered question may be asked again is not stated.** The
contract forbids repeating an unanswered request. In the `superseded-revision`
recording the agent, given a reply that named a superseded revision, posted a
follow-up question about the same candidate. The first statement of
`RequestIsNotRepeated` would have called that a violation; it now forbids
exactly what the contract forbids, and the model's agent never follows up.
Obligation: `PRR-REQ-02`. Residue: follow-up questions on an unchanged
candidate are neither modelled nor forbidden, which the README states.

### Structure the model made visible

**S1. The bindings are enforced twice.** The plan revision, the head and the
proof inventory each enter the protocol at two points: they are part of what
makes a question the same question, and they are checked against what the reply
echoes. Removing one check alone never produced an unsafe transition. With only
the question's identity weakened (`mutant-question-identity-ignores-revision`),
the superseded request is adopted, its reply fails the echo check, and the
assignment never recovers: a progress failure, not a safety failure. Only with
both removed (`mutant-revision-binding-removed`,
`mutant-candidate-binding-removed`, `mutant-inventory-binding-removed`) does
stale evidence carry a PR to ready or to merge. Consequence: the redundancy is
real and worth keeping, and a test suite that checked only safety would have
called the single weakening harmless.

**S2. The undivided stack is busy, not deadlocked.**
`stack-from-one-undivided-plan` shows the lower layer never leaving draft and
the stack never merging while both layers are still being observed; only when
the observation loop is removed (`mutant-stack-observation-removed`) does the
checker report a deadlock. The absence of a delivery path therefore has to be
stated as a property and cannot be read off deadlock detection. The documented
alternatives deliver (`stack-from-independent-plans`,
`undivided-plan-in-one-pr`), and a subset waiver is caught
(`mutant-subset-waiver-for-a-stack-layer`).

### No new defect in the stated policy

Within the bounds explored, the realizable properties hold in every assurance
run: no configuration marks a PR ready, posts a question or merges on evidence
that does not clear the candidate the agent last observed. The exercise found
limits of the commands and gaps in what the prose pins down. It did not find a
case where following the documented policy produces a transition the policy
forbids.

### Modelling mistakes

- `ObservationsRecordReality` first required the plan read to agree with the
  real head, giving the agent knowledge it had not read. The first run with a
  head change failed it.
- `VerifiedClaimNeedsMatchingReadBack` first required a record made from an
  observation to equal the remote at the instant of writing. A trace with an
  interruption after the ready command and a head change before the next
  decision failed it.
- The first `stack.fizz` explored one state. The pinned release ignores an
  assignment of the form `xs[i] = oneof choices`, so no layer was ever
  answered. Every safety property held, vacuously, and the two reachability
  assertions were what failed.
- `RequestIsNotRepeated` was first stronger than the contract, as L5 records.

All four were caught by a run that failed, three of them by a property that was
meant to pass.

An independent review of the specification, by a reviewer who was given the
files and the assertion names and not the author's conclusions, then found
defects that no run had failed on:

- `ReadyFollowsFreshReads` checked two flags that the agent's own steps set.
  Replacing the re-fetch's comparison with a constant, or keeping an old ledger
  entry instead of re-reading an answered request, left every assurance run
  passing. The reply read and the re-fetch now leave what they returned, the
  properties compare those records, a sibling property covers the merge, and
  the reviewer's three edits are kept as controls
  (`mutant-recheck-compares-nothing`, `mutant-answered-reply-not-reread`,
  `mutant-merge-decided-without-rechecking`).
- The local CodeScene result was bound to the head and not to the base, so a
  clean delta survived a retarget. It is now bound to the comparison.
- Two reachability witnesses were satisfiable without the event they were
  named for: recovery by a change before the agent's first read, and re-entry
  by an interruption before anything was posted. Both now require it.
- One assertion called a predicate the agent uses, against the suite's own
  rule, and one stated reason for leaving an assertion without a control was
  false; that assertion now has one.
- A run with several scenarios would have satisfied a reachability assertion
  through any one of them. No run did, and a test now forbids it.

The checker passing was not evidence that these properties discriminated. Every
one of them was found by reading the specification against the question "what
edit would this fail to notice?".

### Tool and harness limitations

All of these were observed in FizzBee v0.5.4 and each has a test in
`tests/test_model_check.py`.

- A failed invariant, transition assertion, reachability assertion, liveness
  check or deadlock prints `FAILED` and exits zero.
- An unrecognized `liveness` value disables liveness checking and prints
  `PASSED`; `liveness: "eventual"` passed a property that strict mode fails;
  the documented `liveness: true` is rejected.
- `max_actions` stops exploration silently.
- A replayed trace whose last step the model refuses prints `PASSED` with no
  warning. Three blocking traces were first reported as passing.
- The published reference documents temporal formulas (`leadsto`, `possibly`)
  that the release rejects as a syntax error; the site postdates the release.
- An assignment of the form `xs[i] = oneof choices` is silently ignored.

## Migration and residual assurance gaps

**Removed.** `tests/pr_readiness_model.py`, `tests/pr_readiness_workflow.py`
and the three modules that tested only them: 3,572 lines. The comparison script
that ran both models was removed with them.

**Retained unchanged.** The document-contract tests and their mutation table;
the stand-in tests, the probe property tests and the snapshot of the routes the
stand-ins serve; every recording.

**Refactored.** `tests/test_readiness_handoff_boundary.py` kept every read it
made through the shipped stand-in and lost its Python decision: it now
abstracts a recording into the facts of one model snapshot and looks the
expectation up in a model-checked table. The two handoff tests in
`tests/test_sdlc_implementation_skill.py` do the same from the shipped packet.
Neither decides readiness.

**Correspondence to the skill.** `specs/pr-readiness/obligations.toml` maps 36
obligations to the section that states each, with sentences that section must
still contain, the assertions that express it and evidence kept outside the
model. A contract test fails when a quoted sentence leaves its section, when an
assertion or run has no obligation, and when an assertion has no control that
must fail it and no stated reason. Three assertions are in that last, excused
group.

What this does not give is semantic agreement. A quoted sentence shows that a
rule is still stated. L4 and L5 are both cases where the model and a reasonable
reading of the prose differed, and both were found by a person comparing a
recording with a trace, not by the mapping.

Four different questions were in play, and the evidence for each is separate:

| Question                                                | What answers it here                                          | What it does not show                                 |
| ------------------------------------------------------- | ------------------------------------------------------------- | ----------------------------------------------------- |
| Policy validity: is the rule the right rule?            | Review of the skill; the stack and snapshot results inform it | The checker does not judge whether a rule is wise     |
| Whether the protocol can be realized by any procedure   | The model; the expected counterexamples                       | Nothing beyond the bounds, and nothing unmodelled     |
| Implementation conformance: does the code do it?        | Tests of the launcher, the stand-ins and the adapters         | There is no production implementation of the protocol |
| Agent adherence: does an agent follow the instructions? | The sandboxed rehearsals, mapped to model traces              | One sampled run per scenario, one model, one prompt   |

**What the rehearsals do not establish.** A recording is evidence about one
execution. It does not establish conformance across models, prompts or future
runs, it exercises a stand-in and not GitHub or CodeScene, and it does not
judge a verdict or a proof. The mapping in `fixtures.toml` is hand-authored:
four scenario traces were written from four recordings, and are model-derived
reproductions, not replays.

**Live rehearsals in this work.** None was performed. The sandboxed runner was
started for a permitting scenario (`current-whole-plan`), a blocking one
(`subset-clear`) and a temporal one (`posted-then-answered`). Its isolation
checks passed and the agent then failed to start, because the runner needs a
model API endpoint and token in `ANTHROPIC_BASE_URL` and `ANTHROPIC_AUTH_TOKEN`
and the session had neither. No agent executed and no recording was produced.
The skill text is unchanged by this work, so the committed recordings still
describe the shipped instructions; they are the recordings PR #272 made and are
not new evidence. What this work validated is deterministic: the stand-ins, the
adapters and the mapping of those recordings to the model.

**Residual gaps.** The strong freshness properties fail and will keep failing.
Follow-up questions, formal review and approval, repair, rebase and stack
mechanics are outside the model. The two Python string properties have no
replacement. Everything is bounded: one change, two interruptions, two proofs,
one PR.

## Cost and maintainability

**Routine suite.** 80 runs: 25 assurance, 31 negative controls, 12 property
controls, 4 scenario traces and 8 expected counterexamples. On the loaded
development host, four at a time, it took 124 seconds of wall-clock time and
the largest checker process reached 1.96 GiB of resident memory. Before the
review's fixes added recorded reads to the state, the same assurance runs
explored 10,122 distinct states in 19,268 nodes and peaked at 1.33 GiB; the
largest, `interacting-changes-and-interruption`, was 3,231 states.

**Extended suite.** The extended tier runs the routine suite and one more
configuration, the full 215-row comparison table. Measured before the review's
fixes, that table was 5,930 states in 64 seconds and the largest checker
process reached 2.57 GiB. Hosted CI cost was not measured before this document
was written; the pull request records it.

**Per-state cost.** The release costs roughly 9 ms of processor time and 200
KiB of resident memory per explored node on this host. Removing every assertion
from a 6,741-node configuration changed 58 seconds and 1.3 GiB to 19 seconds
and 1.2 GiB, so the memory is the checker's own. Moving the scenario record out
of the state, moving the agent's logic into pure functions, and the
`--experimental_processed_queue` flag each changed neither figure materially.
Each run also pays about 2.4 seconds to parse the specification.

**State-space growth.** With one change allowed among head, base and revision
and one interruption, the ordinary assignment is 3,227 states; allowing two
changes without the interruption is 5,889; adding a second assessment and an
inventory change to the first is 7,769 and several gigabytes. A configuration
with nine reply shapes for two assessments reached 7,764 states and more than
3.7 GiB before it was split in two, at 292 and 256 states. Growth comes from
lagging copies: every durable record that can differ from the reality it was
copied from multiplies the states.

**Toolchain.** The release archive is 352 MB and unpacks to 680 MB. It is
fetched once, verified by digest, and needs no network afterwards. Only Linux
on x86-64 is supported by this gate.

**Size.** The change removes 3,572 lines of Python specification and tests. It
adds 1,148 lines of specification, about 1,900 lines of suite and mapping data,
1,485 lines of launcher, 694 lines of launcher tests and about 580 lines of
contract tests and support. The total is larger than what it replaced. Fewer
lines was never the aim and is not evidence of anything here; the launcher
exists only because the checker cannot be trusted to report its own result, and
it is the part most likely to need attention when the pin moves.

**Review burden.** The specification is one long file in an unfamiliar
language. What made it reviewable in practice was not its length but three
habits: one atomic action per external step, properties that never call a
function the agent uses, and a named counterexample for every control. A
reviewer can check a control by reading one trace.

**Maintenance.** A change to the skill's readiness text now has four places to
touch: the specification, the mutation that removes the changed guard, the
quoted sentence in the obligation mapping, and possibly a snapshot row. The
gate fails on the last three when they are forgotten. It does not fail when the
prose changes meaning without changing the quoted sentences.

## Candidate requirements for maturity tier 2

These are proposals derived from one case. Each is marked as supported by this
case or as a hypothesis that needs further pilots.

### When modelling is requisite

The case supports treating a skill's protocol as needing a behavioural model
when at least one of these holds and the transition it guards is consequential:

- **State that changes independently of the agent** between a read and the
  action that depends on it. Every limitation found here is of this kind, and
  none was expressible in the snapshot model. (Supported.)
- **Durable hand-offs** across sessions or agents, where what was written down
  is all that survives. Re-entry and request correlation were untestable as
  snapshots. (Supported.)
- **Asynchronous evidence** that arrives late, out of order, or is edited
  after it was read. (Supported.)
- **Retries and partial failures**, where an effect may have happened without
  the agent learning of it. (Supported, through interruption between a command
  and its read-back.)
- **Authority boundaries**, where what applies is decided by one party and
  reported by another. The rule that a reply cannot exempt itself was already
  caught by the snapshot model; modelling added only the separation of
  authority from observation. (Partly supported.)
- **Consequential, hard-to-reverse transitions.** Here readiness is one-way
  by rule. That a lower consequence would not justify the cost is a hypothesis;
  this case has no cheaper comparison.

### When ordinary tests or a state table remain sufficient

- A decision that is a function of one snapshot. The Python model was adequate
  for that, and the snapshot tables are the same thing in another notation.
  (Supported.)
- A skill whose steps do not depend on external state staying still. The same
  repository's error-disposition model (`tests/pr_babysitting_error_model.py`)
  is a decision table and was left alone. (Supported by the decision not to
  migrate it.)
- Contracts in shipped text: required fields, ownership links, section-local
  clauses. Document checks are the right tool and were kept. (Supported.)
- Whether an agent follows instructions. No model answers that. (Supported.)

The recommendation is risk-based and independent of tool. A `.fizz` file
confers nothing by existing: the first `stack.fizz` passed every safety
property while modelling nothing.

### A minimal evidence package

| Element                                  | What this case suggests it must contain                                                                                        | Standing   |
| ---------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ | ---------- |
| An owned behavioural contract            | One normative owner; the model states obligations and owns no policy                                                           | Supported  |
| Environment and abstraction assumptions  | Named actors, what is atomic and why, bounds, exclusions, and each capability attributed to a real command, checked against it | Supported  |
| Safety obligations                       | Stated at the transition they guard, independent of the guard they check                                                       | Supported  |
| Progress obligations                     | Conditional, with the conditions written down, and a control showing progress fails without them                               | Supported  |
| Positive evidence                        | Reachability for every permitted outcome                                                                                       | Supported  |
| Negative evidence                        | One defect per control, a named assertion, and a counterexample that uses the named behaviour                                  | Supported  |
| Model-to-contract traceability           | Obligation, normative section, quoted sentence, assertion, retained evidence; checked in both directions                       | Supported  |
| Reproducible checks                      | A pinned tool, a gate that fails closed on anything it does not recognize, and recorded bounds and counts                      | Supported  |
| Boundary conformance evidence            | A stated concrete-to-abstract mapping and a few recorded executions held to it, with differences listed, not hidden            | Supported  |
| Recorded limitations                     | Properties the protocol cannot have, kept as reproducing counterexamples and never reported as assurance                       | Supported  |
| A migration comparison, where one exists | A bounded comparison with the artefact being replaced, then removal of that artefact                                           | Hypothesis |
| A cost budget for the routine gate       | A stated time and memory ceiling, with wider exploration in a separate tier that includes the routine one                      | Hypothesis |

Hypotheses that need further pilots before they become requirements: that the
launcher's fail-closed checks transfer to another checker; that a second
multi-system skill yields limitations of the same kind; that the four-layer
separation of authority, reality, observation and evidence is general and not
an artefact of this protocol; and that the cost is acceptable for a skill whose
transitions are reversible.

## Open questions and transferability

**Plausibly general.** Separating what the agent has read from what is true;
checking each claimed atomicity against the real command; requiring a
reachability assertion for every permitted outcome; reading every control's
counterexample; treating a model checker's own output as untrusted input; and
keeping limitations as failing runs. None of these depends on PRs.

**Specific to PR babysitting.** The reply shapes, the whole-plan subject rule,
the proof inventory, the hosted and local CodeScene split, and the stack
conflict.

**Where runtime enforcement might be necessary.** L1 to L3 cannot be closed by
instructions. Closing them needs a conditional transition: a ready command that
names the head it expects, branch protection or a required check that encodes
the evidence, or a merge queue. Whether the residual risk justifies that is a
decision this document does not make; the consequence today is a PR that is
ready, and not merged, at an unassessed head.

**What the later policy author still has to decide.**

- Whether a recorded, unclosable limitation is acceptable at tier 2, and who
  accepts it.
- Whether boundary conformance needs fresh recordings when the model changes
  and the skill text does not.
- How much of an evidence package may be bounded, and how the bounds are
  justified.
- Whether prose-model correspondence needs a named reviewer, given that the
  mapping cannot establish it.
- Who owns the model when the skill's owner changes the prose.

**Triggers for updating the model.**

- A change to any sentence quoted in `obligations.toml`, or to the readiness,
  assessment, waiting or merge sections it quotes from.
- A change to what a command guarantees: a conditional form of `gh pr ready`,
  a wider merge guard, or a merge queue.
- A change to the assessment service's reply format, to how replies are
  correlated, or to who may answer.
- A new FizzBee pin. Re-probe every behaviour the launcher depends on first.
- A recording that the fixture mapping can no longer hold to its trace.
- A new consequential transition in the skill, such as an automatic retarget.

## Checklist for the later author

This list is subordinate to the evidence and qualifications above.

1. Name the normative owner of the contract, and state that the model owns no
   policy.
2. List the systems that change independently of the agent, and who changes
   each.
3. Separate authority, reality, observation and durable evidence in the
   model's state.
4. For every step the model treats as atomic, name the real command and check
   what it guarantees.
5. State each safety obligation at its transition, in terms the guard does not
   share.
6. Give every permitted outcome a reachability check, and show that it can
   fail.
7. State progress conditionally, and show that it fails without its
   conditions.
8. Give every guard one mutation, one named assertion and a counterexample
   that uses the named behaviour; read the counterexample.
9. Keep properties the protocol cannot have as failing runs, reported apart
   from assurance.
10. Map each obligation to a quoted sentence, an assertion and retained
    evidence, and check the mapping in both directions.
11. Hold a few recorded executions to the model through a stated mapping, and
    list every difference.
12. Pin the tool, and make the gate fail on anything it does not recognize.
13. Record bounds, counts, time and memory, and say what the bounds leave out.
14. Remove what the model replaces.
