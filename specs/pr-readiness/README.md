# PR-readiness behavioural specification

This directory holds the executable specification of the draft-to-ready
protocol that the `pr-babysitting` skill states in prose, and the suite that
checks it with [FizzBee](https://fizzbee.io/), a model checker.

The skill is the normative contract and keeps readiness ownership. These files
state selected behavioural obligations of that contract in a form a machine can
explore; they do not own policy. Where the two disagree, treat the disagreement
as a finding to investigate against the skill.

## Files

- `readiness.fizz` models one pull request (PR): the remote candidate, the
  approved plan revision, the proof inventory, the checks, the assessment
  thread, the agent's observations, and its durable ledger.
- `stack.fizz` reduces the managed-stack conflict to the two rules that
  produce it.
- `suite.toml` pins the checker and lists every run with its required
  outcome.
- `obligations.toml` maps each obligation to the skill section that states
  it, the assertions that express it, and the evidence kept outside the model.
- `fixtures.toml` maps the agent-boundary recordings under
  `tests/fixtures/readiness-agent-boundary/` to model events and scenarios.

## Running the checks

```bash
make fizzbee              # once: fetch and verify the pinned release
make model-check          # the mandatory suite, part of `make ci`
make model-check-extended # the mandatory suite and the larger explorations
```

`make fizzbee` is the only step that uses the network. It downloads the FizzBee
v0.5.4 `linux_x86` release archive (352 MB), checks it against the SHA-256
digest in `suite.toml`, unpacks it under `~/.cache/fizzbee`, and checks the
unpacked files. `make model-check` never downloads anything: it fails, naming
`make fizzbee`, when the release is absent or differs from the pinned bytes.
Only Linux on x86-64 is supported. Set `MODEL_CHECK_HOME` to keep the release
elsewhere and `MODEL_CHECK_JOBS` to change how many checker processes run at
once.

To iterate on one run, and its unmutated twin when it is a control:

```bash
uv run --script scripts/model_check_cli.py check \
  --suite specs/pr-readiness/suite.toml --only mutant-subset-verdict-clears
```

A named subset is reported as `PARTIAL` and is not a gate result. Each run's
specification, options, scenario, output and counterexample trace are kept under
`build/model-check/<run>/`, and `build/model-check/report.json` records the
checker version, each run's command, options, node and state counts, duration
and outcome.

## Reading a result

Every run belongs to one class, and the summary lists the classes apart.

| Class                     | The specification is | It must                                 | It is evidence that                                   |
| ------------------------- | -------------------- | --------------------------------------- | ----------------------------------------------------- |
| `assurance`               | unmodified           | pass, exhaustively                      | the obligations hold in that configuration            |
| `negative-control`        | mutated in one place | fail one named assertion                | that assertion detects that defect                    |
| `property-control`        | unmodified           | fail one named assertion                | that assertion is evaluated and can fail              |
| `expected-counterexample` | unmodified           | fail one named strong property          | the documented protocol has that limitation           |
| `scenario-trace`          | unmodified           | replay one event sequence, or refuse it | that sequence is, or is not, a behaviour of the model |

An expected counterexample is a recorded limitation. It is never assurance, and
a suite in which all of them "pass" has reproduced the limitations, not removed
them.

When a run fails the gate:

- `failed`: an assurance run broke a property. Read the trace in the summary
  and decide, against the skill, whether the model, the property or the
  contract is wrong.
- `undetected` or `wrong-failure`: a control did not fail, or failed another
  assertion. Either the guard it mutates is no longer what protects the
  obligation, or the assertion no longer discriminates.
- `wrong-reason`: a control's counterexample did not pass through the event
  the control names.
- `error`: the checker rejected the specification or crashed. This is never
  counted as a control detecting its defect.
- `inconclusive` or `interrupted`: the checker ran out of time, was stopped,
  left nodes queued, or explored as many nodes as `max_actions` allows.
- `unchecked` or `misconfigured`: the checker did not report checking a
  temporal assertion, or did not echo the options it was given.
- `unrecognized`: the output is not one the launcher knows. Do not teach the
  launcher a new line without running the pinned release to see what it means.

## What the model covers

The agent runs one pass at a time: read the PR, read the plan and inventory,
read the checks, run the local CodeScene delta, inspect the discussion, post
any missing question, read the replies, re-fetch the candidate, decide, and
then issue the ready or merge command and read it back. Each step is one atomic
action. The environment may act between any two of them: the head, base,
approved plan revision or proof inventory may change; checks complete; the local
`cs` becomes unavailable and recovers; the assessment service replies late,
out of order, in any of ten shapes, and may edit a reply in place; another
author may echo a request marker; and the agent's session may be interrupted,
losing everything it held in memory.

The layers are kept apart. `cfg` is authority: the accepted assignment. `base`,
`head`, `rev`, `requests`, `replies` and the rest are reality. `obs`, `cur` and
`intent` are the agent's observations and are lost on interruption. `l_checks`,
`l_local`, `l_eval` and `l_claim` are the durable ledger. No action reads
reality except the step that stands for the corresponding API call or command.

## Assumptions and bounds

These are assumptions of the model, not facts it establishes.

- **One lifecycle owner.** Only this agent posts assessment questions for the
  PR. Request uniqueness is a property of one owner inspecting the discussion
  before it posts; it is not a global deduplication service, and two concurrent
  owners could both post.
- **Truthful scope of a whole-plan verdict.** The service gives a whole-plan
  verdict only to a candidate that implements the whole plan. Whether any
  verdict is justified is the assessor's judgement and outside the model.
- **Atomic reads.** One API response is one step: a `gh pr view`, a check
  rollup, a paginated comment listing. A listing that changed between pages is
  not modelled.
- **The agent's checkout is private.** Checking out the observed head and
  running the local delta on it is one step.
- **Identities are never reused.** Head, base and revision only increase, so
  a superseded value cannot become current again. A snapshot's stand-in for "an
  earlier value" is -1.
- **Bounded change.** One shared budget of one change per run covers head,
  base, revision and inventory, so a second invalidation during a recovery is
  not explored. The budget is also what makes the candidate eventually stable
  in the progress property. Interruptions are bounded at one or two, outages at
  one, and a reply is edited at most once.
- **Small domains.** At most two required proofs, two assessment kinds, and
  one PR; `stack.fizz` has two layers.
- **Fairness.** Agent steps, check completion, service replies and outage
  recovery are weakly fair. No strong fairness is used: an outage is made
  transient by a budget, not by assuming the agent eventually retries at a
  lucky moment. Every run that declares progress also offers only favourable
  outcomes (green checks, a clean delta, a sound verdict), so progress never
  depends on a fair choice among outcomes.
- **Checks do not regress.** A check leaves `pending` once per candidate. A
  check that turns red, or a hosted finding that appears, on an unchanged
  candidate is not modelled.
- **Commands succeed.** `gh pr ready` and the read-back never fail, and nobody
  but the agent changes the draft or merged state.
- **Replies are attributed correctly.** A reply is stored under the marker of
  the request it answers, so a reply the service attributes to the wrong
  request, and the contract's "ambiguous attribution remains pending", cannot
  be represented. A verdict for another candidate differs in its head only.
- **Every change renews every assessment.** The contract renews the
  assessments a change affects; the model treats each change as affecting both.
- **Two scope errors are the model's decision.** The contract states that an
  applicable completeness assessment with no approved revision is a scope
  error. That an applicable proof assessment with an empty inventory, and an
  inapplicable assessment with no justification, also end in a recorded impasse
  follows the retired Python model and is not quoted from the skill.
- **A wait never becomes an impasse.** With the local `cs` permanently
  unavailable the model's agent observes for ever. The contract names a service
  failure that persists through repeated bounded recovery as an impasse; when a
  wait becomes one is not modelled.

- **No follow-up question on an unchanged candidate.** The agent asks each
  question once and then waits. The contract forbids repeating an unanswered
  request; a follow-up to an answer that does not clear, with nothing else
  changed, is neither modelled nor forbidden by `RequestIsNotRepeated`. The
  `superseded-revision` recording shows an agent posting one.

Deliberately excluded: the formal CodeRabbit review, review threads, approval,
rebase mechanics, prerequisite PRs, candidate trust, comment identities and
token routing, the content of a plan or a proof, and how a repair is made. A
push is an environment event whatever its author.

Every assurance run is an exhaustive breadth-first search of a small finite
model. It is not an unbounded proof, says nothing of larger populations, and
does not exercise an agent, GitHub, CodeScene or the review service.

## Atomicity and freshness

`gh pr ready` takes no expected head, and `gh pr merge --match-head-commit` is
conditional on the head alone. The model's commands behave the same way. Two
families of property therefore exist, and they must not be confused.

The realizable properties (`ReadyNeedsCurrentEvidence`,
`ReadyFollowsFreshReads`, `MergeFollowsFreshReads`,
`MergeNeedsAuthorityAndRenewedEvidence`) say that, when a command is issued,
the ledger clears the candidate the agent last observed, that the ledger holds
what this pass's reply read returned, and that this pass's re-fetch returned
that same candidate. The reply read and the re-fetch each leave what they
returned, and the properties compare those records; they do not trust a flag.
They hold in every assurance run.

The strong properties (`StrongReadyFreshness`, `StrongMergeFreshness`) say that
the evidence is current in reality when the command takes effect. They hold
under a frozen environment, and under head-only change for the merge, where the
head guard closes the race. Eight `expected-counterexample-*` runs keep a
failure reproducible for each of: the head, the base, the plan revision, the
inventory or a reply changing before the ready command, and the plan revision,
the base or a reply changing before the merge. A read-back after the command
detects that the candidate moved; it does not undo or prevent the transition.

## Changing the specification

- Keep each property independent of the agent's guard. A property must not
  call a function the agent uses to decide.
- When a guard changes, update the mutation that removes it; an anchor that
  no longer matches exactly once fails the gate.
- When a skill sentence quoted in `obligations.toml` changes, re-read the
  obligation against the new text before updating the quotation.
- Re-probe the release before relying on a FizzBee feature or changing the
  pin: the published documentation describes features v0.5.4 does not have.
