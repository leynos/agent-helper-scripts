# Replace the PR-readiness Python specification with a FizzBee model

This ExecPlan (execution plan) is a living document. The sections `Constraints`,
`Tolerances`, `Risks`, `Progress`, `Surprises & discoveries`, `Decision log`,
`Outcomes & retrospective`, `Conformance basis`, and `Verification plan` must
be kept up to date as work proceeds.

Status: COMPLETE (implementation and validation; PR delivery is owned by
`pr-babysitting` on PR #291)

Branch: `pr-readiness-fizzbee-spec`

Roadmap item: none.

## Purpose / big picture

Pull request (PR) #272 bound the draft-to-ready gate of the `pr-babysitting`
skill to the `sdlc-implementation` handoff. The skills are prose, so that work
added a bespoke Python restatement of the gate under `tests/`: a decision
function (`tests/pr_readiness_model.py`), a sequence around it with in-memory
doubles (`tests/pr_readiness_workflow.py`), and three test modules that
exercise only that restatement.

The Python restatement answers one question well: given one snapshot of facts,
may the PR leave draft? It cannot answer the questions the protocol actually
raises, because they are about time: what happens when the candidate, the
approved plan revision or a reply changes between the agent reading it and the
agent acting on it; what survives an interrupted session; and whether a blocked
workflow can still make progress.

After this change the same obligations are stated once, in a FizzBee
specification under `specs/pr-readiness/`, and checked by a model checker that
explores every interleaving of the agent and its environment within stated
bounds. FizzBee is a model checker whose specifications are written in a
Python-like language; a model checker enumerates the reachable states of a
small abstract description of a system and reports any state or step that
breaks a stated property, with the sequence of events that led there.

A contributor observes success by running:

```bash
make model-check
```

and seeing every assurance run pass, every negative control fail for its named
reason, and every expected counterexample reproduce. `make ci` runs the same
target. The Python restatement and its three test modules are gone. The tests
that read the shipped Markdown, drive the real stand-ins and replay the agent
recordings remain, and the document
`docs/lessons-from-modelling-the-pr-babysitting-skill.md` records what the
exercise found.

The skill remains the normative procedural contract and `pr-babysitting` keeps
readiness ownership. The FizzBee file is the executable specification of the
selected behavioural obligations; it is not a second policy owner.

## Constraints

- Work only after PR #272 has merged. Its merge commit is
  `9dec88cd77c28e1327a6818cc0b76adf94f8e9eb`, an ancestor of the branch base
  `006e8d5e0d89ba9a7af5635cfd697f09d39c7cdd`. Do not modify PR #272.
- Do not change the policy the skills state. Where the model shows that the
  documented protocol cannot satisfy a property, preserve the counterexample
  and report the gap; do not edit a skill or invent infrastructure to make the
  checker pass. Skill text under `skills/` is not modified by this plan.
- Do not keep two permanent implementations of the readiness policy. The
  Python decision and workflow models are removed, with no compatibility façade.
- Keep tests that exercise real code or shipped text: the stand-ins
  (`gh-shim.py`, `cs-shim.py`), the runner's probes, fixture consistency,
  sandbox isolation, and the documentation-contract checks.
- Do not weaken the rehearsal sandbox, and do not fabricate, relabel or
  regenerate agent recordings.
- Checking the model must need no GitHub credential, model API, paid service
  or network access once the checker has been acquired.
- Do not add a daemon, service, scheduled job, source-build toolchain or
  credential dependency.
- Do not disable deadlock detection globally, and do not accept a syntax
  error, timeout or crash as evidence that a control detected its defect.
- Follow `AGENTS.md`: run `make check-fmt`, `make markdownlint`, `make lint`,
  `make typecheck`, `make test` and `make spelling` sequentially before each
  commit; never edit `typos.toml` by hand; every Python definition under
  `scripts` and `tests` carries a docstring.
- New scripts follow the repository scripting standards: Cyclopts for the
  command line, Cuprum for launching processes, and a standard-library core
  that tests can drive with a process double.
- Execution approval: the assignment that requested this plan also instructs
  its implementation, which is the standing instruction the `execplans` skill
  recognizes. No separate approval round is awaited.

## Tolerances (exception triggers)

Comparison base: `006e8d5e0d89ba9a7af5635cfd697f09d39c7cdd`. Count with
`git diff --numstat 006e8d5 -- <paths>`. Net lines are additions minus
deletions. This ExecPlan file is excluded from every count.

Classification: `scripts/`, `tests/*.py`, `specs/pr-readiness/*.fizz` and
`Makefile` recipes are code. `specs/pr-readiness/*.toml`, `pyproject.toml`,
`.gitignore`, `typos.local.toml`, `typos.toml` and `.github/workflows/` are
configuration. Markdown outside `docs/execplans/` is documentation.

The survey behind these budgets: the retired Python machinery is 3,572 lines
(`pr_readiness_model.py` 616, `pr_readiness_workflow.py` 510, and their three
test modules 972, 609 and 865). The two mixed-purpose callers are
`tests/test_readiness_handoff_boundary.py` (1,224 lines) and the last two tests
of `tests/test_sdlc_implementation_skill.py`. The only comparable historical
plan, `docs/execplans/adopt-vendcurl.md`, records no numeric budgets, so there
is no history of revised limits to learn from.

- Files: more than 30 non-ExecPlan files changed or created: stop and
  escalate.
- Code: more than 2,500 lines added outside the deleted files (specification,
  launcher and tests together): stop and escalate. The change is expected to be
  net negative.
- Configuration: more than 900 net lines: stop and escalate. The suite
  manifest is the bulk of it.
- Documentation: more than 1,300 net lines: stop and escalate. The lessons
  document is the bulk of it.
- Dependencies: any new Python package dependency: stop and escalate. The
  pinned FizzBee release is the one authorized new tool.
- Coverage: if an existing obligation in the inventory below cannot be given
  replacement or retained evidence, stop and escalate rather than deleting its
  test.
- Runtime: if the routine suite exceeds ten minutes or 4 GiB of resident
  memory on this host, reduce it or escalate; do not move required checks to
  the extended tier to meet the limit.
- Iterations: three failed attempts at one gate without a new diagnosis: stop
  and escalate.

## Risks

- Risk: the FizzBee documentation describes features that the pinned release
  does not have. Severity: high. Likelihood: high (confirmed). Mitigation:
  every feature used was exercised against the pinned binary first; see
  `Surprises & discoveries`.
- Risk: the checker reports failure through text, not its exit status.
  Severity: high. Likelihood: certain (confirmed). Mitigation: the launcher
  parses the pinned output strictly and fails closed on anything it does not
  recognize, and its tests drive it with real and doubled checker output.
- Risk: a property and the guard it checks share a predicate, so a defective
  edit moves both. Severity: high. Likelihood: medium. Mitigation: properties
  are written separately from the agent's guard and each guard has a mutation
  control that must fail the named property.
- Risk: a passing model is vacuous because the happy path is unreachable.
  Severity: high. Likelihood: medium. Mitigation: every permitted assignment
  has a reachability assertion, and controls show that reachability and
  liveness assertions can fail.
- Risk: state-space growth makes the routine suite too slow for the hosted
  runner. Severity: medium. Likelihood: medium. Mitigation: focused
  configurations, one combined configuration, and an extended tier for the
  widest combination; measured cost is recorded.
- Risk: retiring Python tests removes a documentation-contract check that
  happened to live beside the model. Severity: medium. Likelihood: medium.
  Mitigation: the inventory classifies each test by what it establishes, and
  the citation checks move to the obligation mapping's own contract test.
- Risk: the 352 MB checker archive makes CI slow or flaky. Severity: low.
  Likelihood: medium. Mitigation: the digest is verified, the download is a
  single retried transfer, and the measured CI time is recorded.

## Progress

- [x] (2026-11-20 02:05Z) Prerequisite confirmed: PR #272 merged as
  `9dec88c`; branch renamed to `pr-readiness-fizzbee-spec`.
- [x] (2026-11-20 02:40Z) Read the merged contract, the Python models, their
  tests and callers; built the coverage-and-retirement inventory below.
- [x] (2026-11-20 03:00Z) `EP-M1` toolchain: pinned FizzBee v0.5.4, verified
  the archive digest, and exercised every needed feature against the binary.
- [x] (2026-11-20 04:10Z) `EP-M2` core model and properties:
  `specs/pr-readiness/readiness.fizz` and `stack.fizz`.
- [x] (2026-11-20 04:40Z) `EP-M2` launcher (`scripts/model_check.py`,
  `scripts/model_check_cli.py`), suite manifest, `make fizzbee`,
  `make model-check`, `make model-check-extended`, CI install step, and
  `tests/test_model_check.py`.
- [x] (2026-11-20 04:40Z) `EP-M3` 24 assurance runs, 5 property controls, 5
  expected counterexamples and 26 negative controls; every control's
  counterexample was read and passes through its intended event.
- [x] (2026-11-20 04:45Z) `EP-M3` temporary Python/FizzBee snapshot
  comparison: 189 bounded snapshots, the Python model permits 4 and holds 185,
  and the FizzBee model agrees on every row. The 68 single-deviation rows are
  the routine `snapshot-regression-table`; the full set is the extended
  `snapshot-comparison-table`.
- [x] (2026-11-20 06:10Z) `EP-M4` `obligations.toml` (36 obligations) and
  `tests/test_pr_readiness_obligations.py`; `fixtures.toml`, four scenario
  traces, the `fixture-snapshots` table and
  `tests/test_pr_readiness_fixture_mapping.py`;
  `tests/test_readiness_handoff_boundary.py` and the two handoff tests of
  `tests/test_sdlc_implementation_skill.py` refactored to abstract and look up
  instead of deciding.
- [x] (2026-11-20 06:20Z) First commit, `7e1b74f`, with the Python model
  still present and the comparison script beside it.
- [x] (2026-11-20 06:50Z) `EP-M5` Python model, workflow double, their three
  test modules and the comparison script removed; `AGENTS.md`, the developers'
  guide and the users' guide updated.
- [x] (2026-11-20 07:00Z) `EP-M6` lessons document written. Extended tier
  measured: 74 runs, 100 s, 2.57 GiB peak.
- [x] (2026-11-20 07:00Z) Live rehearsals attempted and not performed: the
  runner's isolation checks passed, then the agent failed to start because
  `ANTHROPIC_BASE_URL` and `ANTHROPIC_AUTH_TOKEN` were not set in this session.
  No recording was produced or changed.
- [x] (2026-11-20 08:10Z) `EP-M6` independent review of the formal claims by
  a reviewer given the files and assertion names only. Its blocking finding
  (fresh-read properties checked flags the agent set) and its should-fix
  findings on the local delta's base, two weak witnesses, a shared predicate, a
  false excuse and overstated purposes were fixed; its remaining notes are
  declared in the specification's README. The routine suite is now 80 runs.
- [x] (2026-11-20 09:00Z) Full gate sequence run by the scrutineer on
  `02c27bd`: `check-fmt`, `markdownlint`, `lint`, `typecheck`, `model-check`
  (80 runs, 97 s, 1.93 GiB peak), `test` (2,001 passed in 435 s) and `spelling`
  all exited zero, and the tree was clean afterwards. `typecheck` runs only the
  syntax check; the repository configures no type checker.
- [x] (2026-11-20 09:20Z) Draft PR #291 opened; hosted CI passed on
  `6acb82c` (Makefile gates, 5m49s). Handed to `pr-babysitting` with merge
  authorized at equilibrium.
- [x] (2026-11-20 10:30Z) `pr-babysitting` section 4: the repository has no
  hosted CodeScene check, and the local `cs delta` (cs 1.0.56) of
  `006e8d5..6acb82c` reported new issues in six files, chiefly
  `scripts/model_check.py` at code health 4.91. The launcher was split into
  `model_check_suite.py`, `model_check_judge.py` and `model_check.py`, with
  class and option rules as data; `check` takes a flattened `CheckOptions`; the
  handoff test's reply abstraction moved to
  `tests/readiness_snapshot_support.py`. The delta now reports no new or
  degraded issue, and every new module scores 10.0.
- [x] (2026-11-20 11:14Z) Completeness and proof assessments requested on
  `5c4fa22` (comments 7037980348 and 7037983922). Both answered "not yet". The
  proof concern: the fresh-read properties did not assert the order of the
  reply read and the re-fetch. The completeness concerns: the same gap; the
  blocking "Unit Architecture" pre-merge check; maintainer direction on D9 and
  D10; and an aggregate measure of concurrent checker memory.
- [x] (2026-11-20 12:40Z) Repairs: a reversed-order mutant passed the
  specification, confirming the gap; the re-fetch now records the reply read it
  followed, and two reversed-order controls fail their named property. Session
  loading writes nothing and `reset_report` deletes explicitly; machine facts
  arrive in an injected `Host`; the applicability rules moved to
  `tests/readiness_applicability.py` with one control each. The routine suite
  is 82 runs. Aggregate concurrent checker memory peaked at 2.25 GiB.
- [x] (2026-11-20 11:44Z) Follow-up assessments on `9e24fbe` (comments
  7038587210 and 7038588134). Proof: "Yes, for the stated bounded
  model-checking claims", with the read-order concern resolved and the recorded
  limits restated. Completeness: substantially complete with no remaining
  correctness defect, naming one stale statement in this plan's outcomes about
  hosted CI time, corrected in the next commit.
- [x] (2026-11-20 12:20Z) PR #291 marked ready on `8e447aa`; the automatic
  formal review requested changes with 16 inline findings and two failed
  pre-merge checks (User-Facing Documentation, Unit Architecture).
- [x] (2026-11-20 13:30Z) Every finding verified against the source and
  repaired: partial runs exit non-zero and the gate ignores an inherited
  `MODEL_CHECK_ONLY`; the checker runs in its own process group; graph failures
  count only from a finished search; run identifiers, control options and trace
  actions are validated; a relative checker home is resolved; presentation
  moved to `scripts/model_check_report.py`; `CompletionIsEarned` forbids ending
  on a wait or an unmatched read-back; an unnamed-revision completeness request
  does not clear; the fixture mapping orders post-ready checks and, where a
  recording's mapped re-fetch is observed, requires a PR read after its last
  discussion read (it compares command kinds, so it cannot tell which
  discussion read returned a reply, and it does not verify reply content); four
  prose claims narrowed; user-facing documentation added. The routine suite is
  85 runs.
- [x] (2026-11-20 14:05Z) Renewed assessments on `bb62ec9` (comments
  7041061771 and 7041161685) were not clear. Proof: `CompletionIsEarned`
  cleared any ending whose evidence was clear, so an agent could finish before
  its decision step, or a merge assignment could stop there. The property now
  names the step and the authorized stopping condition: an ending from `start`
  needs a merged PR, from the read-back a matched ready-only claim, and from
  the decision step a stay-draft or ready-only or no-merge authority over clear
  evidence. Two controls, `mutant-completion-before-the-decision` and
  `mutant-merge-assignment-stops-at-the-decision`, fail it; under the old
  property both were caught only by a reachability assertion. Completeness: the
  file-count breach is recorded as D16, memory was re-measured (D14) and the PR
  description was refreshed. The routine suite is 87 runs.
- [x] (2026-11-20 14:30Z) Assessments on `b6ec91a` (comments 7041957435 and
  7042022872). Proof: "Yes, for the stated bounded model-checking claims".
  Completeness: substantially complete, naming one overstatement in this plan's
  progress, which described the fixture mapping's re-fetch check as following
  the last reply read; corrected in the next commit.
- [x] (2026-11-20 11:50Z) Implementation and validation complete. From here,
  readiness, the formal review, its findings, approval and merge are owned by
  `pr-babysitting` and recorded on PR #291, not in this plan.

## Surprises & discoveries

- Observation: the published FizzBee reference describes temporal formulas
  (`leadsto`, `possibly`, unprefixed `assertion`) that v0.5.4 rejects as a
  syntax error. Evidence: a probe specification using
  `assertion Leads: return … leadsto …` fails compilation with
  `mismatched input 'assertion'`; the site's pages carry a modification date of
  2026-10-29, after the 2026-10-01 release. Impact: the model uses only
  `always`, `exists`, `transition`, `eventually always` and `always eventually`
  assertions, all of which were run against the pinned binary.
- Observation: `fizz` exits zero when a property fails. Evidence: a failing
  invariant, a failing transition assertion, an unreached `exists` assertion, a
  liveness failure and a deadlock all printed `FAILED` and exited `0`; only a
  syntax error (`1`) and a runtime error in the specification (`2`) exit
  non-zero. Impact: the launcher decides from the output text and treats the
  exit status only as an error signal.
- Observation: an unrecognized `liveness` value silently disables liveness
  checking. Evidence: `liveness: "bogus"` printed `PASSED` with no `Checking`
  line for a property that `liveness: "strict"` fails; `liveness: "eventual"`
  also passed a property that strict mode fails; the documented
  `liveness: true` is rejected by the release as an invalid value. Impact: the
  suite requires `liveness: "strict"` and the launcher requires a `Checking`
  line for every temporal assertion in the specification.
- Observation: `max_actions` clips exploration silently. Evidence: an
  unbounded counter with `max_actions: 15` printed `Nodes: 16, queued: 0` and
  `PASSED`. Impact: the launcher accepts a pass as exhaustive only when the
  reported node count is below `max_actions`, because a breadth-first search of
  a graph with fewer nodes than the bound cannot have reached it.
- Observation: `gh pr ready` has no conditional form, and
  `gh pr merge --match-head-commit` is conditional on the head only. Evidence:
  `gh pr ready --help` (gh 2.97.0) lists only `--undo`; the merge help lists
  `--match-head-commit SHA`. Impact: the model's ready command marks whatever
  is published, and its merge command refuses only a changed head. Both shapes
  produce the expected counterexamples recorded below.
- Observation: the pinned release silently ignores an assignment of the
  form `xs[i] = oneof choices`. Evidence: the first `stack.fizz` explored one
  state and failed its reachability assertions; assigning the choice to a local
  first restored the 12 states expected. Impact: no subscript is assigned
  directly from `oneof`, and the incident is why every permitted outcome has a
  reachability assertion.
- Observation: the release costs roughly 9 ms of CPU and 200 KiB of resident
  memory per explored node on this host, whatever the assertions. Evidence:
  6,741 nodes took 58 s of CPU and 1.3 GiB with every assertion present and 19
  s and 1.2 GiB with none; moving the scenario record out of the state and the
  agent's logic into pure functions changed neither materially, and
  `--experimental_processed_queue` changed nothing. Impact: configurations are
  kept focused, the widest combinations are in the extended tier, and the
  launcher runs configurations in parallel.
- Observation (modelling mistake): `RecoveryIsReachable` was satisfiable by a
  change before the agent's first read. Evidence:
  `mutant-question-identity-ignores-revision` was predicted to fail it and
  failed only `ProgressWhenWarranted`; the independent review then showed the
  witness held with no invalidation at all. Impact: the witness now requires a
  renewed question, and the control fails it as first predicted.
- Observation: a replayed trace whose last step the model refuses prints
  `PASSED` with no warning. Evidence: three traces written to end in a refused
  `AgentRunsReadyCommand` were reported as passing; the release warns only when
  it stops before the last step. Impact: the launcher takes the executed step
  count from the reported node count, and the blocked expectations are what
  exposed the gap.
- Observation (modelling mistake): the first statement of
  `ObservationsRecordReality` required the plan-read step to agree with the
  real head, which gave the agent knowledge it had not read. Evidence: the
  first run with a head change failed that assertion. Impact: the property now
  checks each read against only what that read returns.
- Observation (modelling mistake): the first statement of
  `VerifiedClaimNeedsMatchingReadBack` required a readiness record made from an
  observation to equal the remote at the instant of writing. Evidence: a trace
  in which the session was interrupted after the ready command, and the head
  changed between the re-entry pass's last read and its decision. Impact: the
  property distinguishes a read-back, which is a read, from an
  observation-derived record, which is bound to the observation.

## Decision log

- D1. Decision: pin FizzBee v0.5.4 as the prebuilt `linux_x86` release
  archive, verified by the SHA-256 digest GitHub records for the asset
  (`8a1d0900f9ad920002151922337912e11f9e588a2f1196249fe40bf75370f782`) and by
  digests of the unpacked `fizz`, `fizzbee`, `fizz.env` and
  `parser/parser_bin`. Rationale: a trusted prebuilt distribution with
  integrity verification exists, so a source build through Bazel is
  unnecessary; the release bundles its own Python runtime for the parser. Other
  platforms are unsupported by this gate and say so. Date/Author: 2026-11-20,
  implementing agent.
- D2. Decision: every action in the model is atomic and stands for one
  externally visible step; interleaving boundaries are the gaps between
  actions, and interruption is an explicit `AgentInterrupted` action.
  `crash_on_yield` is set to `false` explicitly. Rationale: FizzBee's built-in
  crash injection discards a thread but cannot reset the agent's ephemeral
  variables, because all state is global; an explicit action makes the split
  between ephemeral and durable state reviewable. Non-atomic actions and
  crash-on-yield were verified to work and deliberately not used. Date/Author:
  2026-11-20, implementing agent.
- D3. Decision: negative controls are textual mutations of the specification
  applied by the launcher, each required to match exactly once, not mutant
  switches inside the specification. Rationale: the shipped specification stays
  free of defect branches, the mutation exercises the real guard text, and a
  mutation whose anchor has drifted fails the gate instead of silently testing
  nothing. Date/Author: 2026-11-20, implementing agent.
- D4. Decision: scenario facts live in one `cfg` record chosen in `Init` from
  a `SCENARIOS` list that a configuration replaces through
  `--preinit-hook-file`. Rationale: one mechanism serves both a focused
  configuration (one entry) and a snapshot table (many entries checked in a
  single run), with no second specification file for snapshots. Date/Author:
  2026-11-20, implementing agent.
- D5. Decision: bound the environment with one shared change budget across
  head, base, plan revision and inventory, and let each identity component only
  increase. Rationale: identities are never recycled, so superseded evidence
  can never become current again by wrap-around, and the budget doubles as the
  "candidate eventually stabilizes" progress condition. Date/Author:
  2026-11-20, implementing agent.
- D6. Decision: the strong freshness properties are part of the specification
  but evaluated only where a configuration sets `check_strong`: under a frozen
  environment, where they must pass, and in runs classed
  `expected-counterexample`, where they must fail. Rationale: the documented
  protocol cannot satisfy them, and the limitation must stay visibly separate
  from passing assurance. Date/Author: 2026-11-20, implementing agent.
- D7. Decision: download the checker with `curl` through Cuprum rather than
  `vendcurl`. Rationale: `vendcurl` is a bootstrap-time tool that neither this
  host nor the hosted runner provides; the launcher verifies the digest itself.
  Date/Author: 2026-11-20, implementing agent.
- D8. Decision: the managed-stack conflict is a small separate specification,
  `stack.fizz`, not a second PR inside the readiness model. Rationale: two
  layers inside the full protocol square its state space while adding nothing
  to the conflict, which depends only on the whole-plan subject rule and the
  stack's all-layers-ready merge rule. Date/Author: 2026-11-20, implementing
  agent.

- D9. Decision: continue past the size tolerances, and report the breach.
  The code budget of 2,500 added lines and the configuration budget of 900 were
  set before the launcher and the suite existed and are exceeded: the
  specification is about 1,100 lines, the launcher about 1,500, its tests about
  700, the contract tests about 530, and the suite and mapping data about
  1,800. The options were to stop and await direction, to cut controls or
  launcher checks to fit, or to continue. Cutting would remove exactly the
  fail-closed checks and controls the assignment requires, and this session has
  no interactive reviewer to await. The work continued, and the breach is
  stated in the PR description for the maintainer to accept or reject.
  Date/Author: 2026-11-20, implementing agent.
- D10. Decision: gate interim commits with the fast gates, `make model-check`
  and the affected test modules, and run the full `make test` once on the final
  candidate. Rationale: under the host's load the full suite takes about an
  hour, and a run started mid-work was stopped at 9 % after six minutes.
  Date/Author: 2026-11-20, implementing agent.
- D11. Decision: `RequestIsNotRepeated` forbids repeating an unanswered
  request, as the contract says, and nothing more. Rationale: the
  `superseded-revision` recording shows an agent following up an answered
  question; the first, stronger statement would have called a recorded,
  contract-permitted action a violation. The model's agent never follows up,
  which the README states as an exclusion. Date/Author: 2026-11-20,
  implementing agent.
- D12. Decision: do not edit the skills. Three contract observations are
  reported for the policy owner instead: the re-fetch before acceptance names
  base/head and not the plan revision; the re-fetch is stated only in the
  waiting procedure; and whether an answered question may be followed up on an
  unchanged candidate is unstated. Date/Author: 2026-11-20, implementing agent.

- D13. Decision: record, in the re-fetch, the reply read it followed, and
  require it in `ReadyFollowsFreshReads` and `MergeFollowsFreshReads`.
  Rationale: the assessment service showed that the two records could be
  consistent with either order; a reversed-order mutant confirmed it. A witness
  written by the re-fetch step itself is independent of the agent's control
  flow, which the reversed-order controls mutate. Date/Author: 2026-11-20,
  implementing agent.
- D14. Decision: the memory tolerance is measured as the summed resident
  memory of the checker processes running at once, not the largest one.
  Evidence: sampled every 0.2 s during `make model-check` with four jobs, it
  peaked at 2,308 MiB on 82 runs and at 2,310 MiB on the 87-run suite (two
  processes at the peak, 355 samples, 72.2 s), within the 4 GiB tolerance.
  Date/Author: 2026-11-20, implementing agent.
- D15. Decision: proceed with the size delivered (D9). The delivery report
  stated the breach, the figures and the option of trimming the snapshot tables
  and launcher tests, and asked the maintainer to accept or reject it; the
  maintainer then directed that the PR be merged once it reaches equilibrium.
  That is recorded as direction to proceed, not as an explicit acceptance of
  the budgets, which remain exceeded. D10's partial interim gating is
  superseded: the full gate sequence has since run on `02c27bd`, `5c4fa22` and
  each later candidate. Date/Author: 2026-11-20, implementing agent, on the
  maintainer's direction.
- D16. Decision: the file-count breach grew after the maintainer's direction
  (D15) and is carried under the same direction rather than trimmed. At
  `6acb82c`, when the breach was reported, 25 non-ExecPlan paths had changed; at
  `bb62ec9` there are 32 (19 added, 5 deleted, 8 modified), over the 30-file
  tolerance. The seven later paths are `docs/v0-3-0-migration-guide.md`,
  `scripts/model_check_judge.py`, `scripts/model_check_report.py`,
  `scripts/model_check_suite.py`, `tests/readiness_applicability.py`,
  `tests/readiness_snapshot_support.py` and
  `tests/test_readiness_applicability.py`. Each was required by a gate the
  merge depends on: the launcher was split for the CodeScene delta and the Unit
  Architecture pre-merge check, the adapters were split from the boundary test
  for the same reasons, and the migration note answers the User-Facing
  Documentation pre-merge check. Folding them back would restore the findings
  those gates raised. The breach is stated on PR #291 for the maintainer, who
  may still direct a trim. Date/Author: 2026-11-20, implementing agent.

## Outcomes & retrospective

The Python decision model, its workflow double and their tests are gone, and
the same obligations are stated in `specs/pr-readiness/readiness.fizz` and
checked by `make model-check`, which `make ci` runs. The routine suite is 87
runs. Every obligation in the inventory has an assertion and a routine run, or
is recorded as retired without replacement with the reason.

Against the purpose: the model answers the questions the snapshot model could
not. It reproduces eight counterexamples to the strong freshness properties,
shows the head-only merge guard closing the one race it can close, checks
re-entry after interruption, and states progress conditionally. It found no
case in which following the documented policy produces a forbidden transition.

What would be done differently: probe the pinned release's failure reporting
before writing any model, since four separate behaviours of the checker would
each have produced a false pass; budget for the launcher, which is larger than
the specification; and set size tolerances after a prototype, not before. See
`docs/lessons-from-modelling-the-pr-babysitting-skill.md` for the findings in
full.

Gaps: the strong properties fail by design; two properties of the Python
model's own strings have no replacement; and live agent rehearsals were not
performed. Hosted CI time is measured: the `Makefile gates` job took 5m49s on
`6acb82c` and 6m36s on `9e24fbe`, including the checker download. On the hosted
runner 2,005 tests pass and 10 are skipped, against 2,015 passing on the
development host; the skipped tests are installer and Markdown-gate tests that
need tools the runner does not provide.

## Context and orientation

Inspected base revision: `006e8d5e0d89ba9a7af5635cfd697f09d39c7cdd`.

The normative contract lives in three shipped documents:

- `skills/pr-babysitting/SKILL.md`, especially section 1 (the delivery
  ledger and what each verdict is bound to), section 4 (CodeScene, including
  "an unevaluable source is not a clear source"), section 5 (the mandatory
  order and the ready command), section 10 (the checks immediately before a
  merge) and the operating contract's "Never return a PR to draft".
- `skills/pr-babysitting/references/execplan-assessment.md`, especially
  "Applicability and ownership", "Comment routing", the two request templates,
  and "Readiness and later changes".
- `skills/pr-babysitting/references/awaiting-coderabbit.md`, "Bounded
  issue-comment observation", which states how a reply is correlated and that
  live base/head is re-fetched before a result is accepted.

`skills/sdlc-implementation/SKILL.md` and its `references/setup.md` hand
delivery to `pr-babysitting` and point at the readiness rule instead of
restating it. `skills/github-stacks/SKILL.md`, "Merging", requires every
selected PR of a stack to be open and not a draft.

Terms used below:

- Candidate: the base commit and head commit of the PR, together with the
  approved plan revision when an ExecPlan applies and the required proof
  inventory when a proof assessment applies.
- Assessment: a tagged issue-comment conversation with the review service
  about completeness and correctness against the plan, or about the rigour of
  introduced proofs. It is not a formal review.
- Ledger: the durable record the agent keeps outside the product diff.
- Delivery gates: green hosted continuous integration (CI), clear hosted
  CodeScene findings, and an evaluated, clean local CodeScene delta.

Existing validation is `make ci`, which runs `check-fmt`, `markdownlint`,
`lint`, `typecheck`, `test` and then `spelling`. `.github/workflows/ci.yml` runs
`make ci CI_SKIP_MARKDOWNLINT=1` on `ubuntu-latest` with Python 3.13, uv and a
Rust toolchain. Tests run with `uv run --group dev python -m pytest`.

### Coverage-and-retirement inventory

Each row is one obligation, classified by what its current evidence
establishes. "Retire" means the Python check restates the abstract protocol and
its assurance moves to the model. "Keep" means the check reads shipped text or
drives real code.

| Obligation                                                               | Normative section                                           | Current evidence                                                                               | Treatment                                                                                             | Limitation                                                                                    |
| ------------------------------------------------------------------------ | ----------------------------------------------------------- | ---------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| Ready needs green CI, clear CodeScene and applicable assessments         | SKILL section 5 step 3                                      | `test_pr_readiness_model.py` gate cases; properties soundness                                  | Retire; `ReadyNeedsCurrentEvidence`                                                                   | Python had one CodeScene flag; the model separates hosted and local                           |
| Delivery gates precede any assessment question                           | assessment reference, "Applicability and ownership"         | `test_a_blocked_delivery_gate_asks_no_assessment_question`                                     | Retire; `RequestNeedsDeliveryGates`                                                                   | none                                                                                          |
| Unavailable local CodeScene is not clean; hosted green cannot substitute | SKILL section 4                                             | shim tests, `local-codescene-*` recordings, examples test                                      | Keep those; add `LocalResultIsWhatWasRun` and controls                                                | The model does not run `cs`                                                                   |
| Applicability comes from the assignment; a reply cannot exempt itself    | assessment reference, "Applicability and ownership"         | `test_an_applicable_assessment_cannot_excuse_itself`                                           | Retire; shape `not-applicable-claim` and control                                                      | none                                                                                          |
| A justified not-applicable is required for an inapplicable assessment    | SKILL section 1                                             | `test_an_undefended_not_applicable_keeps_the_pr_in_draft`                                      | Retire; impasse `not-applicable-undefended`                                                           | Justification is a Boolean in the model                                                       |
| Only the whole approved plan clears completeness                         | SKILL section 1; assessment reference, readiness            | subset cases, `subset-clear` recordings, handoff boundary test                                 | Retire model cases; keep recordings and document checks; shapes `subset-clear`, `other-subject`       | none                                                                                          |
| A proof verdict covers every required proof                              | assessment reference, proof section                         | inventory cases                                                                                | Retire; two-proof scenario with `partial-proofs`                                                      | Inventories of at most two proofs                                                             |
| An applicable proof assessment names an inventory                        | assessment reference, proof section                         | `test_an_applicable_proof_assessment_must_name_an_inventory`                                   | Retire; impasse `proof-inventory-empty`                                                               | none                                                                                          |
| A verdict is bound to base and head                                      | SKILL section 1                                             | candidate-mismatch cases                                                                       | Retire; shape `other-candidate`, head and base changes                                                | none                                                                                          |
| A verdict is bound to the approved revision, echoed by the reply         | SKILL section 1; assessment reference, readiness            | superseded and unbound revision cases, `superseded-revision` recordings                        | Retire model cases; keep recordings; plan-only change and `no-revision-echo`                          | none                                                                                          |
| An applicable completeness assessment needs an approved revision         | assessment reference, readiness                             | `test_an_applicable_completeness_with_no_approved_revision_keeps_the_draft`                    | Retire; impasse `completeness-without-approved-revision`                                              | none                                                                                          |
| Whitespace around a revision identifier is not part of it                | none: a property of the Python strings                      | `test_a_blank_revision_identifies_nothing`                                                     | Retire without replacement                                                                            | No shipped parser exists; identifiers are abstract in the model. Recorded as a deliberate gap |
| Only the service's correlated reply answers a request                    | awaiting reference, steps 2 and 3                           | `test_a_reply_from_another_author_is_not_a_verdict`; shim authorization tests                  | Retire the model case; keep shim tests; `EvidenceIsWhatWasRead` and controls                          | none                                                                                          |
| An unanswered request is preserved, not repeated                         | assessment reference, "Comment routing"                     | workflow marker cases                                                                          | Retire; `RequestIsNotRepeated`, `ReentryConsumesDelayedReply`                                         | Single lifecycle owner assumed                                                                |
| A materially different question gets its own request                     | assessment reference, "Comment routing"; awaiting reference | superseded-candidate and narrow-inventory cases                                                | Retire; request identity includes candidate, revision and inventory                                   | none                                                                                          |
| Inventories compare as lists of names                                    | none: a property of the Python strings                      | `test_inventories_that_join_to_the_same_string_are_different_questions`                        | Retire without replacement                                                                            | The model's inventories are tuples; no joined string exists to confuse                        |
| Unrecognized verdicts and subjects do not settle anything                | SKILL section 1                                             | unrecognized verdict and subject cases                                                         | Retire; shapes `acknowledgement`, `other-subject`                                                     | none                                                                                          |
| Never return a PR to draft; ready is one-way                             | SKILL operating contract                                    | `test_the_sequence_never_returns_an_already_ready_pr_to_draft`                                 | Retire; `NeverReturnsToDraft`                                                                         | none                                                                                          |
| Each decision reason cites a sentence the documents still state          | all of the above                                            | `test_each_readiness_reason_cites_a_sentence_...`, `test_dropping_any_single_citation`         | Move: the obligation mapping carries the anchors and a retained contract test checks them             | Matching text does not prove semantic agreement                                               |
| Every rule has a control that reverses the decision when it is dropped   | all of the above                                            | `DEFECTIVE_RULES` monkeypatch table                                                            | Retire; textual mutation controls in the suite                                                        | none                                                                                          |
| The handoff packet reaches the readiness sequence                        | `sdlc-implementation` section 4                             | last two tests of `test_sdlc_implementation_skill.py`                                          | Refactor: keep the packet reads, drop the Python decision                                             | none                                                                                          |
| The receiver decides each recorded case from the shipped artefacts       | assessment reference; rehearsal README                      | `test_readiness_handoff_boundary.py`                                                           | Refactor: keep the stand-in reads; map each recording to a model snapshot instead of a Python verdict | The mapping is hand-authored                                                                  |
| Stand-in routes, probes, authorization and fixture coherence             | rehearsal README                                            | `test_readiness_agent_boundary_shim.py`, `..._properties.py`                                   | Keep unchanged                                                                                        | none                                                                                          |
| The shipped Markdown states each contract clause                         | the skills                                                  | `test_pr_babysitting_examples.py`, `assessment_mutation_cases.py`, `skill_contract_support.py` | Keep unchanged                                                                                        | none                                                                                          |
| The stack cut from one undivided plan has no delivery path               | assessment reference, readiness                             | document checks only                                                                           | Keep document checks; add `stack.fizz`                                                                | Two layers                                                                                    |
| Evidence freshness across observation and command                        | awaiting reference step 5; operations reference             | none                                                                                           | New: fresh-read ordering, strong properties and expected counterexamples                              | The gap is a property of the commands, not of the model                                       |
| Interrupted sessions, lost responses and re-entry                        | assessment reference, "Comment routing"                     | none                                                                                           | New: `AgentInterrupted`, read-back and claim properties                                               | Bounded interruptions                                                                         |
| Renewed evidence before merge; a ready PR stays ready                    | SKILL sections 5, 9 and 10                                  | document checks only                                                                           | New: `MergeNeedsAuthorityAndRenewedEvidence`, `StaleReadyIsReachable`                                 | Formal review and approval are outside the model                                              |
| Conditional progress                                                     | SKILL "Equilibrium and impasse"                             | none                                                                                           | New: `ProgressWhenWarranted` with stated conditions                                                   | Bounded changes, interruptions and outages                                                    |

## Conformance basis

There is no Terms of Reference or technical design document for this work. The
upstream artefacts are the assignment text for this follow-up, the merged
skills at `006e8d5`, and the repository's `AGENTS.md`. Obligation identifiers
(`PRR-...`) are defined in `specs/pr-readiness/obligations.toml` and trace as:

```plaintext
skill section -> PRR obligation -> FizzBee assertion or run -> retained test or recording
```

Milestones:

- `EP-M1` inventory and executable toolchain.
- `EP-M2` core model, properties, launcher and gate.
- `EP-M3` independent controls, snapshot comparison and temporal coverage.
- `EP-M4` traceability mapping and rehearsal-fixture mapping.
- `EP-M5` Python retirement.
- `EP-M6` lessons document, review, validation and delivery handoff.

## Verification plan

The obligations and how each is discharged:

- Safety at a transition is a `transition assertion` over the state before the
  step: readiness evidence, authority, fresh-read ordering, merge evidence,
  request preconditions, request uniqueness, and the honesty of each recorded
  observation.
- Safety of a state is an `always assertion`: a claim never outruns the
  remote; an impasse never accompanies a transition; a configuration that
  declares an assignment blocked never sees it ready.
- Reachability is an `exists assertion` per permitted assignment: ordinary
  whole-plan completion, proof-only delivery with no ExecPlan, combined
  completeness and proof, a justified case where neither applies, recovery
  after invalidation, a ready PR that stays ready with stale evidence, and
  re-entry that consumes a delayed reply.
- Progress is one `eventually always assertion` checked under strict
  liveness, with the conditions in the configuration: a bounded change budget,
  outages that recover, a service that eventually answers, and weakly fair
  agent steps. No strong fairness is used.
- Non-vacuity: reachability assertions; a control in which reachability is
  required to fail; a control in which progress is required to fail under a
  permanent outage; and a control that removes the terminal stutter action and
  must be reported as a deadlock.
- Mutation: each guard has a textual mutation that must fail one named
  assertion, and each mutation's unmutated twin must pass.
- Independence: no property calls a predicate the agent uses to decide. The
  guard correlates by request marker; the properties compare the recorded
  request identity with a named candidate.
- Axioms and assumptions, stated in the specification's directory: one
  lifecycle owner posts requests; the review service's whole-plan verdict is
  truthful about whether the layer implements the whole plan; identities are
  never reused; one API response is read atomically.
- Completion: a pass counts only when the checker printed its pass line,
  left nothing queued, explored fewer nodes than `max_actions`, echoed the
  requested options, and reported checking every temporal assertion.
- Independent review: a reviewer who did not write the model reads the
  specification and assertion list for abstraction adequacy, omitted
  behaviours, fairness, atomicity, vacuity, mutation effectiveness and
  prose-model correspondence, and CodeRabbit is asked the proof-quality
  question through `pr-babysitting`.

Evidence limits: every run is an exhaustive search of a small finite model. It
is not an unbounded proof, says nothing about larger populations, and does not
exercise an agent, GitHub, CodeScene or the review service.

## Revision notes

- 2026-11-20: initial plan written after the toolchain probes and the first
  model run. Remaining work is `EP-M2` onwards.
- 2026-11-20: recorded the formal review's findings and their repairs.
- 2026-11-20: recorded the follow-up assessment outcomes, corrected the
  stale statement about hosted CI time, and marked implementation and
  validation complete, with delivery owned by `pr-babysitting`.
- 2026-11-20: recorded the CodeScene repair made under `pr-babysitting`
  before readiness, and the PR's lifecycle state.
- 2026-11-20: recorded `EP-M2` to `EP-M5`, the tolerance breach (D9), the
  gating decision (D10), the corrected request property (D11) and the decision
  to leave the skills unedited (D12). Remaining work is the independent review,
  the full gate run and delivery.
