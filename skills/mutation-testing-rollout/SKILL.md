---
description: Roll out scheduled, informational mutation testing across an estate of repositories, triage the results into issues and killing tests, and keep the callers documented and drift-free.
---

# Mutation-testing estate rollout and triage

This skill captures the process used to roll mutation testing out across
github.com/leynos/\* — approximately forty Rust and Python repositories —
and to operate it afterwards: harvesting survivors into issues, fixing
broken baselines, writing killing tests, and documenting the machinery.
Apply it when adopting mutation testing in a new repository, when triaging
the output of scheduled runs, or when running an estate-wide sweep.

## Architecture

One pair of reusable workflows lives in `leynos/shared-actions`:

- `mutation-cargo.yml` (Rust, [cargo-mutants](https://mutants.rs/)) and
- `mutation-mutmut.yml` (Python, [mutmut](https://mutmut.readthedocs.io/)).

Each consumer repository carries only a thin caller,
`.github/workflows/mutation-testing.yml`, pinned to a shared-actions commit
SHA that Dependabot owns. The runs are **informational only**: they never
gate pull requests. A daily cron fires a change-scoped run (mutating only
files changed within a detection window, so quiet days are cheap no-ops);
manual dispatch runs the full mutation set, fanned out across shards.
Survivors surface in the job summary and in downloadable
`mutation-report-*` artefacts.

The mutation run is a measurement of the test suite, not of the code. A
surviving mutant is a test gap; the goal is a falling survivor count, not
zero.

## Per-repository adoption recipe

1. **Verify eligibility.** The repository needs a healthy test suite that
   passes in CI. No tests means every mutant survives as noise — defer
   until tests exist. Python repositories must be uv-managed (a hard
   requirement of the mutmut workflow).
2. **Verify the baseline under the mutation runner's conditions, not
   CI's.** This is the single most common failure. Hazards found in
   practice:
   - Tests that pass under nextest's process isolation but fail under
     plain `cargo test` (shared global state, log capture, a claimed
     global tracing dispatcher). Either fix the test or pass
     `--test-tool=nextest`.
   - CI running `--all-targets` never runs doctests, but cargo-mutants
     does. Broken doctests (including in vendored code) break the
     baseline. Fix them, mark them `ignore`, or set `doctest = false`.
   - mutmut copies sources into a `mutants/` sandbox that omits
     `.github/`; any test reading workflow files needs a
     `pytest.mark.skipif(not WORKFLOW_PATH.exists(), ...)` guard (or put
     `.github/` in `also_copy`, or exclude the test from selection).
   - Hygiene tests that walk the file system see the workflow-source
     checkout; enumerate `git ls-files` instead.
   - Stateful test dependencies (embedded PostgreSQL) break on re-run;
     pin credentials/versions via the workflow's `setup-commands` input.
3. **Write the caller.** Copy a proven caller (wireframe for Rust,
   cmd-mox for Python) and adapt:
   - `paths`: change-detection globs matching the repository's source
     layout.
   - `exclude-globs`: example code, test scaffolding, fixture crates, and
     `cfg(test)`-only companion files — anything whose survivors are
     noise. Note that a module-root glob (`src/foo.rs`) does not match the
     directory's submodules; add `src/foo/**` too.
   - `extra-args`: match the CI baseline exactly (`--all-features`,
     `--test-workspace=true` for workspaces). A mismatch reports
     feature-gated code as untested. For workspaces where bare feature
     names fail to resolve against the shard-scoped baseline, ensure every
     mutated member defines the baseline feature set (forwarding features
     if necessary).
   - `setup-commands`: install anything `.cargo/config.toml` assumes
     (clang/lld/mold), pin environmental state.
   - `shard-count`: size from the first full run; a shard that brushes the
     360-minute job ceiling needs more shards.
   - For mutmut: configure `[tool.mutmut]` in `pyproject.toml`
     (`source_paths`, test selection, `do_not_mutate` for
     subprocess-executed or generated code, `also_copy` for fixtures the
     tests need). mutmut hard-codes importable layouts (`./`, `src/`,
     `source/`); a `pkg/` layout needs a committed `src -> pkg` symlink
     and `module-prefix-strip`.
4. **Pin and stagger.** Pin the `uses:` line to a full 40-character
   shared-actions commit SHA. Give each repository a distinct cron slot;
   mutation runs are heavy and synchronized schedules concentrate load.
5. **Add a contract test.** A PyYAML-based test
   (`tests/workflow_contracts/` or `tests/test_workflow_contract.py`)
   pins the caller's shape so drift fails the pull request: the `uses:`
   path and that its ref is a 40-hex commit SHA (match the *shape* with a
   regex — never hard-code the SHA value, or every Dependabot bump becomes
   a manual chore), least-privilege permissions (`contents: read`,
   `id-token: write`; empty workflow default), concurrency that queues per
   ref without cancelling, the schedule-plus-plain-dispatch triggers, and
   the `with:` block contents.
6. **Dispatch a full run** and calibrate: verify the summary populates,
   record survivor counts and runtime, and adjust shards/timeouts.
7. **Document.** Add a "Mutation-testing workflow contract tests" section
   to `docs/developers-guide.md`: why the workflow exists (informational
   only), the two run modes, the rationale for each `with:` input, the
   SHA-pin policy, the exact aspects the contract test validates, and the
   local run command (a `make test-workflow-contracts` target where the
   repository has a Makefile). Create the guide (and file an issue for a
   fuller one) where it is missing.

## Triage discipline

Harvest survivors from `mutants.out/outcomes.json` (cargo;
`scenario.Mutant.file`, `span.start.line`, `name`) or the mutmut summary.
File **one issue per coherent area** (module or concern), not per mutant,
with counts, representative survivors (`file:line` plus the mutation), and
a proposed next step. Then work the issues as draft PRs:

- **Real test gap** — write a killing test. Prefer exact assertions;
  "equivalent" verdicts frequently fall to a sharper test.
- **Equivalent mutant** — suppress with justification:
  `#[cfg_attr(test, mutants::skip)]` (Rust, via the `mutants` crate) or
  `# pragma: no mutate` (Python). Keep skips rare and justified; prefer a
  killing test wherever the mutation is observable. Beware two silent
  no-op traps: mutmut honours the pragma only on single logical lines
  (trailing pragmas on continuation lines of multi-line statements are
  ignored — restructure to a single line), and cargo-mutants' skip
  attribute does not cover plain `const` items or binary-expression
  initializers (only functions, impls, and certain expression kinds) — a
  skip placed there changes nothing and the mutant resurfaces next run.
  Verify a suppression actually suppressed by re-running scoped
  (`cargo mutants --file <f>` / `mutmut run <path>`).
- **Dead code** — delete it; this is one of mutation testing's best
  yields.
- **Untestable boundary** — document and move on.

Link every kill site to its tracking issue (issue refs in PR titles and
doc comments at the test), so the provenance survives the merge.

Red-green verification traps: stale `.pyc` bytecode can fake a red-green
cycle (`PYTHONDONTWRITEBYTECODE=1`); an ambient environment variable can
turn a gate into a no-op — check what the gate actually ran.

## Operating the estate: run sweeps

Periodically sweep all repositories' runs (`gh api
repos/<owner>/<repo>/actions/workflows`, then the runs endpoint). Do NOT
classify by wall-clock duration — runner-queue wait routinely inflates a
15-second no-op to an hour. The reliable signals are:
`mutation_detect_has_changes` in the detect step's log (the mutmut
workflow runs its gate *inside* the single mutants job, so a no-op still
reports a green job), and the `mutants` job's conclusion (the cargo
workflow skips it visibly). Remember success does not mean clean — a real
run's survivors live in the job summary — and conversely a "failure" can
mask a fully completed run (a teardown-step regression once failed
otherwise-green runs estate-wide). For failures, read
`gh run view <id> --log-failed`, identify the root cause, and file one
issue per distinct cause (not per run); recurring identical quick failures
are one issue listing occurrences. Deduplicate against existing issues
first — comment on a persisting area rather than re-filing it (and when
concurrent sweep agents race, reconcile their duplicate filings onto one
canonical issue). If the cause lies in the reusable workflow, file it on
the shared-actions repository.

Be aware the change-detection gate suppresses scheduled coverage on quiet
repositories: a repo can report weeks of green runs while executing zero
mutants, leaving a broken baseline undetected. After merging a
baseline fix, trigger a full `workflow_dispatch` to prove it end-to-end
and produce a survivor dataset — do not wait for the schedule.

## Estate lessons (hard-won)

- **Unpinned linters break baselines estate-wide.** `uv tool install ty`,
  unpinned ruff preview rules, and rolling-release dylint each turned CI
  red across multiple repositories at once. Pin linter versions.
- **Stale local checkouts lie.** Before concluding a file is absent,
  verify against the remote default branch (`gh api
  repos/<owner>/<repo>/contents/...`), and branch from a freshly fetched
  `origin/<default>`.
- **Companion and fixture crates produce false survivors.** Where a
  crate's coverage lives in a sibling, scope the run or record that its
  survivor table is advisory.
- **Keep a living rollout ledger** (per-repository status, hazards,
  issue/PR numbers). The tracker outlives any one session and is the only
  reliable memory across an estate this size.
- Spelling gates (typos, en-GB Oxford `-ize`) apply to generated prose
  too; expect `summarising`/`serialises` to be rejected in favour of
  `summarizing`/`serializes`.
