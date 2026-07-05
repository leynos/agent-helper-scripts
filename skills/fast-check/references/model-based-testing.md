# Model-based testing and race-condition detection

All examples assume fast-check 4.x and `import fc from "fast-check"`.

## Commands

A command couples a precondition with an action. It implements
`fc.Command<Model, Real>` (sync) or `fc.AsyncCommand<Model, Real>`:

- `check(m: Readonly<Model>): boolean` — may this operation run in the
  current model state?
- `run(m: Model, r: Real): void` — apply the operation to the real
  system *and* the model; throw (or fail an assertion) on any inconsistency
  between the two.
- `toString(): string` — how the command appears in the failure
  report. Capture runtime-resolved parameters into fields inside `run` so the
  report shows what actually happened (e.g. the resolved track name, not the
  raw modulo index).

The model must be a *simplified* abstraction — for a list, just its length; for
a key-value store, a plain `Map`. If the model re-derives the system's own
logic, the test compares the code with itself.

## Worked example

```typescript
class List {
  data: number[] = [];
  push = (v: number) => this.data.push(v);
  pop = () => this.data.pop()!;
  size = () => this.data.length;
}

type Model = { num: number };

class PushCommand implements fc.Command<Model, List> {
  constructor(readonly value: number) {}
  check = () => true;
  run(m: Model, r: List): void {
    r.push(this.value);
    ++m.num;
  }
  toString = () => `push(${this.value})`;
}

class PopCommand implements fc.Command<Model, List> {
  check = (m: Readonly<Model>) => m.num > 0;
  run(m: Model, r: List): void {
    expect(typeof r.pop()).toBe("number");
    --m.num;
  }
  toString = () => "pop";
}

class SizeCommand implements fc.Command<Model, List> {
  check = () => true;
  run(m: Model, r: List): void {
    expect(r.size()).toBe(m.num);
  }
  toString = () => "size";
}

const allCommands = [
  fc.integer().map((v) => new PushCommand(v)),
  fc.constant(new PopCommand()),
  fc.constant(new SizeCommand()),
];

test("List behaves like a counter", () => {
  fc.assert(
    fc.property(fc.commands(allCommands, { size: "+1" }), (cmds) => {
      const setup = () => ({ model: { num: 0 }, real: new List() });
      fc.modelRun(setup, cmds);
    }),
  );
});
```

`fc.commands` is not merely `fc.array(fc.oneof(...))`: it shrinks by keeping
only the commands that actually *executed* (those whose `check` passed), which
makes failing scenarios collapse quickly.

Runners:

- `fc.modelRun(setup, cmds)` — synchronous commands only.
- `fc.asyncModelRun(setup, cmds)` — `AsyncCommand`s inside
  `fc.asyncProperty`.
- `fc.scheduledModelRun(scheduler, setup, cmds)` — async commands with
  adversarial interleaving; combine with `fc.scheduler()` below.

## Replaying command failures

Command-based properties need one extra handle beyond `{ seed, path }`: the
failure report prints a `replayPath` encoding which commands really executed.
Replay by pinning all three:

```typescript
fc.assert(
  fc.property(
    fc.commands(allCommands, { replayPath: "AAAAABAAE:VF" }),
    checkEverythingIsOk,
  ),
  { seed: 670108017, path: "96:5", endOnFailure: true },
);
```

Remove the pins after the fix and promote the shrunk command sequence to a
named regression test that constructs it explicitly.

## Race-condition detection with the scheduler

`fc.scheduler()` generates a scheduler `s` whose job is to reorder the async
work you hand it, exploring interleavings that the happy-path event loop never
produces.

```typescript
test("queue is FIFO under concurrent producers", async () => {
  await fc.assert(
    fc.asyncProperty(fc.scheduler(), async (s) => {
      const q = new AsyncQueue<number>();

      // Wrap each concurrent operation so the scheduler controls order
      s.schedule(Promise.resolve("a")).then(() => q.put(1));
      s.schedule(Promise.resolve("b")).then(() => q.put(2));

      // Drive everything the scheduler currently knows about
      await s.waitIdle();

      expect(q.drain()).toHaveLength(2);
    }),
  );
});
```

Waiting primitives (4.2+):

- `s.waitNext(n)` — release exactly `n` scheduled tasks.
- `s.waitIdle()` — run until no scheduled task remains.
- `s.waitFor(promise)` — run scheduled tasks until the given promise
  settles, even if some of its dependencies are scheduled late.

`waitOne` and `waitAll` are deprecated. Note the 4.x semantics: a task
scheduled *after* `waitIdle`/`waitAll` began its final drain stays pending —
tasks created behind intermediate `await`s are not magically picked up as they
sometimes were in 3.x. When the code under test schedules follow-up work
asynchronously, prefer `s.waitFor(finalPromise)`.

Other scheduler helpers:

- `s.scheduleFunction(f)` — wrap an async function so each *call*
  resolves under scheduler control (ideal for mocked I/O clients).
- `s.scheduleSequence([...])` — impose a partial order on a sequence
  of steps while the scheduler interleaves everything else around it.

## Model design guidance

- Keep the model piecewise-trivial: counters, plain arrays, `Map`s.
  Complexity in the model is untested code deciding test verdicts.
- Put invariant checks in dedicated read-only commands (like
  `SizeCommand` above) so every interleaving of mutating commands gets audited.
- Constrain command generation with `check`, not by filtering the
  command arbitrary — `fc.commands` already knows how to skip and shrink
  unexecuted commands.
- When a command's effect depends on system state (e.g. "select item
  at position p mod length"), resolve and record the concrete effect inside
  `run` so `toString` reports it.
- Model-based tests sample sequences; they do not prove invariant
  preservation. For load-bearing state machines, mirror the invariant as a
  LemmaScript `//@ ensures` and keep the command suite as the fast regression
  net.
