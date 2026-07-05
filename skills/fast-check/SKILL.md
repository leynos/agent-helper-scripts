---
name: fast-check
description: >
  Write and maintain fast-check property-based tests for TypeScript and
  JavaScript, including arbitrary design, the filtering trap, model-based
  (stateful) testing with commands, race-condition detection with the
  scheduler, replay of failures, and CI tiering. Trigger whenever the user
  mentions fast-check, property-based testing in TypeScript or JavaScript,
  fc.assert, fc.property, arbitraries, model-based testing, fuzzing a
  TypeScript function, or wants generated inputs instead of hand-written
  test cases. Covers fast-check 4.x and flags 3.x idioms that no longer
  hold.
---

# fast-check property-based testing for TypeScript and JavaScript

fast-check generates many random inputs against a property and shrinks any
failing case to a minimal counter-example. It is the cheapest verification
adversary for functions whose input space is too large to enumerate, and its
command runner extends the same idea to stateful systems and race conditions.
Where a property must hold for *all* inputs rather than all *sampled* inputs,
escalate to formal proof with the `lemmascript` skill instead.

## When to apply

Apply when a function has an algebraic property (round-trip, idempotence,
ordering, conservation, commutativity), when a parser or codec must round-trip
across all valid inputs, when an oracle is available (reference implementation,
invariant predicate, prior version), when a stateful API must stay consistent
with a simplified model across arbitrary operation sequences, or when async
code may harbour race conditions that only surface under adversarial
interleaving.

Do not apply when the input space is small enough to enumerate exhaustively
(write a table-driven test), when the property must hold unconditionally and
the cost of a missed case is severe (use LemmaScript to prove it), or when each
generated input performs heavy real I/O — slow runs starve the generator and
the test finds nothing.

## Installation

```sh
npm install --save-dev fast-check
```

The current major is 4.x (latest: 4.8.0). It requires Node ≥ 12.17 and, for
TypeScript users, TS ≥ 5.0. fast-check is runner-agnostic: it works under
Vitest, Jest, and the Node test runner unchanged. Optional ergonomic bindings
exist as `@fast-check/vitest`, `@fast-check/jest`, and `@fast-check/ava`.

## Core concepts

A property test pairs an **arbitrary** (how to generate values) with a
predicate:

```typescript
import fc from "fast-check";

test("decode round-trips encode", () => {
  fc.assert(
    fc.property(fc.string(), (s) => {
      expect(decode(encode(s))).toBe(s);
    }),
  );
});
```

Key pieces:

- An **arbitrary** is an `Arbitrary<T>`. `fc.integer`, `fc.string`,
  `fc.array`, `fc.record`, `fc.oneof`, and `fc.constantFrom` are the everyday
  starters; `fc.letrec` builds recursive structures.
- The predicate either returns a boolean or throws (any assertion
  library works). `fc.assert` catches the failure and shrinks.
- `fc.pre(cond)` rejects the current case as uninteresting; use it
  sparingly (see the filtering trap below).
- `fc.asyncProperty` is the async twin; `fc.assert` returns a promise
  for it — remember to `await`.
- `fc.assert(..., { numRuns, seed, path, verbose })` tunes per-test.

A catalogue of arbitraries, composition patterns (`map`, `chain`, `record`,
`letrec`), and the filtering-trap fix live in
[`references/arbitraries.md`](references/arbitraries.md).

## The filtering trap

`fc.pre(cond)` and `.filter(pred)` use rejection sampling. Heavy rejection
wastes the run budget and degrades shrinking: a shrunk candidate that gets
rejected cannot guide the shrinker, so the minimized counter-example is larger
than it needs to be.

The fix is to construct only valid values from the seed. Replace "draw an int,
require it even" with "draw an int and double it"; replace "draw two values,
require `a < b`" with "draw `b`, then map `a` into `[0, b)`". Before-and-after
examples live in `references/arbitraries.md`.

## Model-based (stateful) testing

For stateful systems, define one command class per operation, each with
`check(model)` (is the operation valid now?), `run(model, real)` (execute
against both, assert consistency), and `toString()`. Feed them to
`fc.commands(...)` and execute with `fc.modelRun` (sync), `fc.asyncModelRun`
(async), or `fc.scheduledModelRun` (async with adversarial interleaving). The
model must be a *simplified* representation — a carbon copy of the system tests
the code against itself.

The full worked example, replay mechanics (`replayPath`), and guidance on model
design live in
[`references/model-based-testing.md`](references/model-based-testing.md).

## Race-condition detection

`fc.scheduler()` produces a scheduler arbitrary that reorders scheduled
promises to explore interleavings. Wrap the async operations under test with
`s.schedule(...)` (or `s.scheduleFunction`), then drive the run with
`s.waitFor(promise)`, `s.waitNext(n)`, or `s.waitIdle()`. `waitOne`/`waitAll`
are deprecated since 4.2 — prefer the newer trio, which behave predictably when
tasks are scheduled after intermediate awaits. Worked examples live in
`references/model-based-testing.md`.

## fast-check 4.x versus 3.x

Watch for stale 3.x idioms in existing suites and in generated code:

- Character-set string arbitraries are gone. `fc.asciiString()`,
  `fc.unicodeString()`, `fc.hexaString()`, `fc.stringOf(arb)` all become
  `fc.string({ unit: ... })` — e.g. `fc.string({ unit: "binary" })` for full
  Unicode, `fc.string({ unit: fc.constantFrom("a", "b") })` for custom units.
- `.noBias()` / `.noShrink()` methods become `fc.noBias(arb)` /
  `fc.noShrink(arb)`.
- `fc.uuidV(4)` becomes `fc.uuid({ version: 4 })`; `fc.bigUintN` and
  friends collapse into `fc.bigInt({ min, max })`.
- `fc.date()` now generates Invalid Date by default — pass
  `{ noInvalidDate: true }` if the code under test cannot take one.
- `fc.record(model, { withDeletedKeys })` becomes
  `{ requiredKeys: [] }`; `record` and `dictionary` may now generate
  null-prototype objects unless `{ noNullPrototype: true }`.
- Failures now attach the original error as `Error.cause` instead of
  splicing messages; pass `{ includeErrorInReport: true }` to restore the old
  report text.

## Anti-patterns

- **Swallowing the failure.** An `expect` inside a `try/catch` that
  ignores the error hides the counter-example from the runner.
- **Asserting only "does not throw".** Pair every no-throw property
  with a real check (round-trip, oracle, invariant).
- **Re-implementing the function under test as the oracle.** Use a
  structurally different reference: brute force, prior version, property
  predicate.
- **Forgetting to `await fc.assert` on async properties.** The test
  passes vacuously; enable `require-await`-style lint rules or use
  `@fast-check/vitest` which handles it.
- **Lowering `numRuns` to make a flake go away.** If the property
  fails at 1000 runs but not 100, the test has found a bug.
- **A model that mirrors the system.** Model-based testing compares
  the system to a *simpler* model; a clone proves nothing.

## Project integration

- **Promote shrunk failures to named unit tests** with the input
  pinned and a comment explaining the bug. fast-check has no failure database;
  the report's `{ seed, path }` (plus `replayPath` for commands) is the only
  replay handle, so capture it immediately.
- **Tier runs.** Default `numRuns` (100) in the inner loop and CI;
  a nightly job with `numRuns: 10000` widens the search. Configure globally with
  `fc.configureGlobal({ numRuns })`.
- **Keep generation deterministic per failure.** Replay with
  `fc.assert(prop, { seed, path, endOnFailure: true })` before attempting a
  fix, and re-run without the pin afterwards.
- **Validate each property with a deliberate mutation.** Break the
  production code, confirm the property fails with a useful shrunk input, then
  restore. StrykerJS automates this across the suite.

## Hard-won lessons

- **Arbitraries decide what you test.** A weak generator makes a
  strong property look strong. Audit the arbitrary first — e.g. `fc.string()`
  alone never exercises surrogate pairs; add `{ unit: "binary" }` coverage for
  codec properties.
- **Shrinking is sacred.** Never swallow failures, never tune
  `numRuns` to hide a flake, never filter when you can compose.
- **The report is not a regression test.** Promote each failure to a
  named unit test; seeds rot as arbitraries evolve.
- **Sampled is not proved.** When the property is load-bearing enough
  to prove, escalate to the `lemmascript` skill and keep the fast-check
  property as a fast regression net beneath the proof.

## References

- [fast-check documentation](https://fast-check.dev/) and
  [GitHub repository](https://github.com/dubzzz/fast-check).
- [Arbitraries reference](https://fast-check.dev/docs/core-blocks/arbitraries/).
- [Model-based testing](https://fast-check.dev/docs/advanced/model-based-testing/)
  and [race conditions](https://fast-check.dev/docs/advanced/race-conditions/).
- [Migration guide 3.x → 4.x](https://fast-check.dev/docs/migration-guide/from-3.x-to-4.x/).
- [`references/arbitraries.md`](references/arbitraries.md) for worked
  generators and the filtering-trap fix.
- [`references/model-based-testing.md`](references/model-based-testing.md)
  for commands, replay, and the scheduler.
- Escalation from sampled properties to machine-checked proof lives in
  [`../lemmascript/SKILL.md`](../lemmascript/SKILL.md).
