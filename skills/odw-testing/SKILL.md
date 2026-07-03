---
name: odw-testing
description: >
  Test Open Dynamic Workflows (ODW) workflow scripts effectively. Use when the
  user wants to write, extend, review, or debug tests for an ODW workflow;
  when they mention testing `odw` workflows, workflow test suites, mock
  adapters, schema-satisfying mock agents, parse gates, helper-surface
  extraction, control-loop simulation, `events.jsonl` assertions, or
  verifying a workflow before a live run. Complements `odw-authoring` (which
  covers writing workflows) and `odw-supervision` (which covers operating
  runs).
---

# ODW Testing

Use this skill to test ODW workflow scripts: plain JavaScript files in Claude
Code's workflow dialect, executed by the `odw` CLI. A workflow under test has
three kinds of surface, each needing a different technique:

1. **Deterministic JavaScript** — parsers, guards, classifiers, schema
   constants, selection logic. Unit-test directly; this is where most defects
   live and where tests are cheapest.
2. **Orchestration wiring** — which agents run, in what order, behind which
   locks, and how failures route. Test by simulation with scripted primitives
   or by source-invariant assertions.
3. **Agent behaviour** — what real CLIs do with the prompts. Not unit-testable;
   bound it with mock adapters end-to-end, and with bounded live smoke runs
   only when the user asks.

Never "test" a workflow by running it against real adapters as a first resort.
Real runs are expensive, non-deterministic, and can mutate repositories.

## The Contract Under Test

ODW's loader (see `src/loader.ts` in the ODW source) defines what a valid
script is, and tests must respect the same transform:

- The file must `export const meta = { ... }` with a **pure literal** object
  (`name` and `description` required). The loader evaluates the literal with
  `new Function('return (…)')`.
- No other top-level `import`/`export` is allowed anywhere outside strings and
  comments.
- The body is wrapped in an `AsyncFunction` whose parameters are the injected
  globals, in this exact order: `agent`, `parallel`, `pipeline`, `phase`,
  `log`, `args`, `budget`, `workflow`, plus ODW's `validate` when the body
  does not bind that name itself. Top-level `await` and `return` are legal
  because of this wrap.
- `Date.now()`, `Math.random()`, and arg-less `new Date()` run under ODW but
  are banned in Claude Code's Workflow tool; ODW's `scanDualCompat` reports
  them as warnings. Treat them as test failures in dual-target workflows.

Primitive semantics that stubs must reproduce faithfully:

- `agent(prompt, opts)` returns a schema-validated **object** when
  `opts.schema` is set, otherwise the reply **string**. On adapter failure it
  **throws**; it does not return `null` by itself.
- `parallel(thunks)` is a barrier; a thunk that throws resolves to `null` in
  the result array rather than rejecting the batch.
- `pipeline(items, ...stages)` has **no barrier**; each stage receives
  `(previous, item, index)`, and a throwing chain yields a `null` slot.
- `budget` exposes `total` (or `null`), `spent()`, and `remaining()`
  (`Infinity` when no total). Reductions must be order-independent because
  completion order is not deterministic.

## Test Layers

Pick the smallest layer that answers the question; compose layers in one
suite.

| Layer | Verifies | Cost |
| --- | --- | --- |
| 0. Parse gate | source compiles as a workflow | milliseconds |
| 1. Helper surface | pure helpers and schema constants | milliseconds |
| 2. Fixture repos | git/filesystem evidence collectors | fast |
| 3. Source invariants | wiring that only exists in prompts/flow | milliseconds |
| 4. Simulation | control loop with scripted primitives | fast |
| 5. Mock-adapter e2e | whole run through the real `odw` runtime | seconds |
| 6. Live smoke | real adapters, bounded scope | expensive; only on request |

## Layer 0: Parse Gate

Wire a deterministic compile check into the repository gates (`make
typecheck`/`lint`) so a workflow that no longer parses fails CI before any
agent spends a token. Mirror the loader's transform (run this from a
`workflow-parse` make target over every workflow file):

```bash
node -e "const fs=require('fs');
for (const path of process.argv.slice(1)) {
  let source=fs.readFileSync(path,'utf8')
    .replace(/^export const meta\s*=/,'const meta =');
  new Function('return (async function __wrapped__() {\n' + source + '\n})');
  console.log(path + ': wrapped JavaScript parses');
}" workflows/*.js
```

For workflow source generated *inside* a workflow, use the injected
`validate(source)` primitive instead — it returns
`{ ok, meta, errors, warnings }` including the dual-compat warnings. Add a
grep-level check (or a test) that the source contains no `Date.now()`,
`Math.random()`, or arg-less `new Date()` outside strings and comments.

## Layer 1: Helper-Surface Unit Tests

This is the workhorse layer. It requires a structural convention in the
workflow itself — adopt it when authoring (see `odw-authoring`):

- Define every pure helper, schema constant, and prompt builder **above** the
  control loop.
- Mark the boundary with a stable marker comment, for example
  `// --- Worker-pool control loop`.

Tests then slice the helper region, compile it with injected stubs, and
return the helpers worth testing:

```js
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const WORKFLOW_PATH = new URL('../workflows/my-flow.js', import.meta.url)
const CONTROL_LOOP_MARKER = '// --- Worker-pool control loop'

async function loadSurface() {
  let source = await readFile(WORKFLOW_PATH, 'utf8')
  source = source.replace(/^export const meta\s*=/, 'const meta =')
  const markerIndex = source.indexOf(CONTROL_LOOP_MARKER)
  assert.notEqual(markerIndex, -1, 'control-loop marker should exist')
  const helperSource = source.slice(0, markerIndex)
  const factory = new Function(
    'args', 'phase', 'log', 'agent', 'parallel', 'budget',
    `${helperSource}
return { MY_SCHEMA, classifyFailure, selectNextTask, shouldAssess }
`,
  )
  return factory(
    {},                                   // args: default configuration path
    () => {},                             // phase: no-op
    () => {},                             // log: no-op
    async () => null,                     // agent: never called by helpers
    async (thunks) => Promise.all(thunks.map((t) => t())),
    { total: null, remaining: () => Infinity, spent: () => 0 },
  )
}
```

Notes on this pattern:

- Because the test compiles the slice with its **own** parameter list, the
  loader's parameter order does not apply here; it only matters when
  executing the whole body (Layer 4).
- Guard the marker with `assert.notEqual(markerIndex, -1, …)` so a refactor
  that drops it fails loudly instead of silently compiling the whole file.
- Passing `{}` as `args` exercises every configuration default. Add a second
  factory call with overrides when defaults are load-bearing (adapter
  routing, parallelism caps, feature flags).
- Helpers using `process.getBuiltinModule('node:fs')` etc. work unchanged
  under `node --test` (Node 22+); no mocking needed.
- The slice must not execute side effects at top level. If the helper region
  contains an eager `process.chdir` or filesystem probe, run the tests from a
  directory where those succeed, or gate the side effect on configuration.

Prime candidates for this layer:

- **Classifiers and guards** — failure-detail matchers (auth vs provider vs
  product fault), retry/defer predicates, "should this branch be assessed"
  gates. Table-drive them: one assertion per representative detail string,
  including the negative cases that must NOT match.
- **Deterministic selection** — roadmap/queue parsing, dependency resolution,
  dedupe keys. Feed crafted text fixtures; assert both the selection and the
  blocked/remainder reporting.
- **Result shapers** — functions that turn an error or agent reply into a
  typed result object; assert the exact object with `assert.deepEqual`.

## Layer 2: Schema Contract Tests

Schemas are cross-agent contracts, so test them as data:

```js
test('assessment schema exposes only the ADR classifications', async () => {
  const s = await loadSurface()
  assert.deepEqual(s.ASSESSMENT_SCHEMA.properties.classification.enum,
    s.ASSESSMENT_CLASSIFICATIONS)
  assert.equal(s.ASSESSMENT_SCHEMA.additionalProperties, false)
  assert.deepEqual(s.ASSESSMENT_SCHEMA.required, [/* every property */])
})
```

Assert three things: the enum matches the documented contract (an ADR or
design doc where one exists), `additionalProperties` is `false` wherever the
consumer iterates keys, and `required` lists exactly what downstream
JavaScript dereferences without optional chaining. When a downstream branch
reads `result.foo`, a test must fail if `foo` leaves `required`.

Also check mock-satisfiability: ODW's schema-satisfying mock agent (Layer 5)
generates `enum[0]`, `false` for booleans, `1`/`0.5` for numbers, and
`max(minItems, 2)` array entries. A schema whose only "healthy" value is not
the mock default (e.g. a workflow that loops until `ok === true` while the
mock always returns `false`) will hang or exhaust rounds in e2e tests —
either bound the loop or script a bespoke adapter for that call.

## Layer 3: Git and Filesystem Fixtures

Helpers that collect evidence from a repository get real throwaway repos, not
mocks:

```js
function git(cwd, ...args) {
  return execFileSync('git', args, {
    cwd, encoding: 'utf8',
    env: {
      ...process.env,
      GIT_AUTHOR_NAME: 'test', GIT_AUTHOR_EMAIL: 'test@example.invalid',
      GIT_COMMITTER_NAME: 'test', GIT_COMMITTER_EMAIL: 'test@example.invalid',
    },
  }).trim()
}

function makeRepo() {
  const dir = mkdtempSync(path.join(tmpdir(), 'wf-fixture-'))
  git(dir, 'init', '-b', 'main')
  writeFileSync(path.join(dir, 'README.md'), '# Fixture\n')
  git(dir, 'add', 'README.md')
  git(dir, 'commit', '-m', 'Initial fixture')
  return { dir, baseSha: git(dir, 'rev-parse', 'HEAD') }
}
```

Rules:

- Pin author/committer identity through `env` so CI hosts without a git
  identity still pass.
- Build the exact states the helper distinguishes: committed-only, staged,
  dirty/untracked, and the empty branch (no commits after base). The empty
  case is where `git log base..HEAD` and `diff base...HEAD` parsers usually
  break.
- Assert structured output (`assert.deepEqual` on parsed entries), plus the
  error-accumulator path: point the helper at a missing directory or a bogus
  base SHA and assert it reports collection errors instead of throwing.

## Layer 4: Source-Invariant Assertions

Some wiring exists only in prompt text or call ordering: an auth check gated
before integration, a preflight command per adapter, a lock wrapping a merge.
When simulation would cost more than it proves, pin the invariant with an
anchored regex over the raw source:

```js
test('implementations gate auth before integration', async () => {
  const source = await readFile(WORKFLOW_PATH, 'utf8')
  assert.match(
    source,
    new RegExp(
      String.raw`const impl = await buildLock\(\(\) => agent\(implementPrompt` +
        String.raw`[\s\S]*?implementationAuthFailureDetail\(impl\)` +
        String.raw`[\s\S]*?status: 'fatal-auth'`,
    ),
  )
})
```

Use these sparingly and only for load-bearing sequences. Anchor on structural
tokens (function names, status literals, option keys), never on prose
wording — prompt copy-editing must not break the suite. If a regex needs
`[\s\S]*?` more than twice, the invariant probably deserves a Layer 4/5 test
or a helper extraction instead.

## Layer 5: Control-Loop Simulation

To test routing decisions (which statuses halt the pool, what gets retried,
what a terminal summary contains), execute the **whole body** with scripted
primitives, mirroring the loader exactly:

```js
async function runWorkflow({ args, script }) {
  let source = await readFile(WORKFLOW_PATH, 'utf8')
  source = source.replace(/^export const meta\s*=/, 'const meta =')
  const AsyncFunction = Object.getPrototypeOf(async () => {}).constructor
  const body = new AsyncFunction(
    'agent', 'parallel', 'pipeline', 'phase', 'log',
    'args', 'budget', 'workflow', 'validate',
    source,
  )
  const calls = []
  const agent = async (prompt, opts = {}) => {
    calls.push({ label: opts.label, adapter: opts.adapter, phase: opts.phase })
    return script(prompt, opts)          // scripted reply per call
  }
  const parallel = (thunks) => Promise.all(
    thunks.map((t) => Promise.resolve().then(t).catch(() => null)),
  )
  const pipeline = async (items, ...stages) => Promise.all(
    items.map(async (item, index) => {
      try {
        let value = item
        for (const stage of stages) value = await stage(value, item, index)
        return value
      } catch { return null }
    }),
  )
  const phases = []
  const result = await body(
    agent, parallel, pipeline,
    (t) => phases.push(t), () => {},
    args, { total: null, spent: () => 0, remaining: () => Infinity },
    async () => { throw new Error('nested workflow not scripted') },
    () => ({ ok: true, errors: [], warnings: [] }),
  )
  return { result, calls, phases }
}
```

The `script` function is the test's steering wheel. Key it on `opts.label`
or `opts.adapter` (stable identifiers), not on prompt substrings, and make
it schema-aware: when `opts.schema` is present, return an object that
satisfies it. Scenarios worth scripting:

- the happy path (assert the terminal result shape and processed set);
- one stage returning a failing verdict (assert the fix/retry loop runs and
  is bounded by its cap);
- `agent` throwing an auth-shaped and a provider-shaped error (assert the
  run halts with the right status and no further work is opened);
- an agent returning `null`/nothing (assert the control loop converts it to
  a failure result rather than crashing).

Beware workflows whose helpers shell out (`git fetch origin`, auth-status
CLIs): simulation executes those for real. Point `args` at a fixture repo
(Layer 3) with a local `origin` remote, or make the command paths injectable
via `args`. If the top of the body does `process.chdir`, run the simulation
in a subprocess or pass a safe `projectRoot`.

## Layer 6: End-to-End with Mock Adapters

The highest-fidelity test short of spending tokens: run the real `odw`
runtime with adapters that are deterministic local scripts. ODW ships the
canonical fixture — `tests/fixtures/mock-agent.mjs` in the ODW source
(upstream: `github.com/xz1220/open-dynamic-workflows`) — which reads the
prompt from stdin, extracts the JSON Schema the bridge appends after the
`JSON Schema:` marker, and prints a minimal valid instance. Any
schema-driven workflow runs end to end against it with no model calls.

Hermetic test config (write into a `mkdtemp` root):

```json
{
  "defaultAdapter": "mock",
  "workspaceMode": "inplace",
  "schemaRetries": 1,
  "concurrency": 8,
  "runsRoot": "<tmp>/runs",
  "adapters": {
    "mock": { "command": ["node", "<path>/mock-agent.mjs"], "stdin": "{prompt}" }
  }
}
```

Then:

```bash
odw run workflow.js --config <tmp>/odw.config.json --source <tmp>/fixture \
  --wait --timeout 300 --args '{"maxTasks":1}'
```

For role-specific behaviour (an implementer that improves per round, a
reviewer that fails round 1 and passes round 2), define one adapter per role
as an inline `node -e` script and reference them from the workflow's
adapter-routing args — this is how ODW's own multi-adapter e2e test drives a
converging duel deterministically.

Assert on durable run artifacts under `runsRoot`, not on stdout alone:

- `result.json` — the final return value (wrapped as `{ "value": … }`);
  assert its shape and the terminal summary.
- `events.jsonl` — the ordered event stream; assert the `phase_started`
  sequence matches the declared flow, and count `agent_finished` events per
  adapter to prove each role really ran the expected number of times.
- `error.json` — must be absent on success; on failure tests, assert the
  message routes correctly.

Every adapter named by the workflow's routing configuration must exist in
the test config, or the run fails on dispatch — that failure is itself a
useful test that routing args and config stay in sync.

## Live Smoke Runs

Only when the user asks, and always bounded:

- use the workflow's own scope limits (`dryRun`, a single `taskId`,
  `maxTasks: 1`) so planning/review paths run without implementation or
  merges;
- point `--source` at a throwaway clone, never the canonical checkout,
  unless real-tree edits are the explicit goal;
- set `--timeout` with `--wait`, and supervise with `odw status`/`odw logs`
  (see `odw-supervision`);
- inspect `result.json` before treating the run as evidence.

## Suite Hygiene

- Use `node --test` with plain `node:assert/strict`; name files
  `tests/<workflow>-<facet>.test.mjs` and wire them into the repository's
  standard test gate so `make all`-style commit gates run them.
- One behavioural claim per test; table-drive classifier matrices.
- Keep tests independent of agent prose: key on labels, adapters, schema
  fields, status literals, and marker comments — the stable contract — so
  prompt tuning never breaks the suite.
- When a test needs a helper the factory does not yet export, add it to the
  factory's return list rather than duplicating logic in the test.
- Clean up `mkdtemp` roots in `finally`; a leaked fixture repo with a stale
  `origin` can poison later git tests.

## Anti-Patterns

- **Prompt-wording assertions.** Testing that a prompt contains a sentence
  couples the suite to copy-editing. Test the data the prompt is built from,
  or a structural regex on function/option names.
- **Whole-body eval in a unit test.** Executing the full script to reach one
  helper runs the control loop, shells out, and can chdir. Slice above the
  marker instead.
- **Stubs with the wrong failure semantics.** A `parallel` stub that rejects
  on the first error, or an `agent` stub that returns `null` on failure
  instead of throwing, validates code paths the real runtime never takes.
- **Order-dependent assertions on concurrent work.** Completion order is
  scheduler-dependent; sort or set-compare results.
- **Unbounded e2e loops against the mock agent.** The mock returns fixed
  defaults (`false`, `enum[0]`), so a loop-until-true workflow never
  converges; bound rounds via args or script a bespoke adapter.
- **Testing against real adapters in CI.** Non-deterministic, slow, billed,
  and capable of mutating repositories. Reserve real adapters for explicit,
  supervised smoke runs.

## Checklist

1. Parse gate wired into CI for every workflow file.
2. Helper region above a marker comment; factory-based unit tests for every
   classifier, guard, parser, and result shaper — negatives included.
3. Schema tests: enum ↔ contract, `required` ↔ downstream access,
   `additionalProperties: false`, mock-satisfiable.
4. Fixture-repo tests for every git/filesystem evidence helper, including
   empty and error paths.
5. A few anchored source invariants for load-bearing wiring.
6. Simulation scenarios for happy path, bounded retry, fatal-auth,
   provider-fault, and null-return routing.
7. Mock-adapter e2e proving the flow end to end, asserting `result.json`
   and `events.jsonl`.
8. Live smoke only on request, bounded, on a throwaway source.
