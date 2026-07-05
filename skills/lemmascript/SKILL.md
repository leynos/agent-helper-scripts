---
name: lemmascript
description: >
  Verify TypeScript formally with LemmaScript: write `//@` specification
  annotations in ordinary TypeScript, generate Dafny or Lean artefacts
  with `lsc`, and discharge proof obligations so properties hold for all
  inputs, not just sampled ones. Trigger whenever the user mentions
  LemmaScript, lsc, formal verification or model checking of TypeScript
  or JavaScript, proving a TypeScript function correct, `//@ requires`
  / `//@ ensures` annotations, .dfy.gen files, or wants machine-checked
  guarantees (invariant preservation, conservation, soundness,
  completeness) for TypeScript code. Covers LemmaScript 0.5.x (tech
  preview) with the Dafny and Lean backends.
---

# LemmaScript formal verification for TypeScript

LemmaScript is a verification toolchain for TypeScript. You write ordinary
TypeScript with `//@` specification comments; the `lsc` CLI generates formal
artefacts that a backend prover (Dafny, or Lean via Velvet/Loom) checks. The
annotations are comments — invisible to tsc, bundlers, and the runtime — and
the TypeScript source *is* the production code; there is no erasure and no
verified-model/production gap. Think "Verus is to Rust as LemmaScript is to
TypeScript".

Where fast-check samples inputs and can only find bugs, LemmaScript proves
properties for every input. It costs far more effort per property, so reserve
it for load-bearing logic; use the `fast-check` skill for the broad regression
net beneath the proofs.

## When to apply

Apply when a property must hold unconditionally and a violation is severe:
invariant preservation across a state machine's actions, conservation ("money
never leaks"), soundness and completeness of a decision procedure, security
predicates (path-traversal containment, open-redirect exclusion,
permission-gate correctness), parser conservation, or bounded-resource
guarantees (no overbooking, rate-limit bounds).

Do not apply to code outside the supported fragment (heavy `async`,
`this`-dispatch, closures over mutable state, regex, real I/O), to
float-sensitive numerics (the model treats `number` as a mathematical integer),
or when a sampled property-based test gives sufficient confidence — proofs are
expensive to write and to maintain.

## Installation and prerequisites

Node.js ≥ 18. Dafny ≥ 4.x for the primary backend; `elan` plus the Loom/Velvet
forks for the Lean backend.

```sh
npm install lemmascript
```

For brownfield work, clone LemmaScript as a **sibling** of the target project
and invoke it from source (`npx tsx ../LemmaScript/tools/src/lsc.ts ...`) — it
is a tech preview, and the cleanest fix for a gap is sometimes in the toolchain
itself. The `midspiral/hono-lemmascript` repository is a complete worked
example with annotations, generated Dafny, proofs, and CI.

## Core concepts

Annotate the function, then generate and verify:

```typescript
export function firstIndexOf(arr: number[], target: number): number {
  //@ verify
  //@ requires arr.length > 0
  //@ ensures \result >= -1 && \result < arr.length
  //@ ensures \result >= 0 ==> arr[\result] === target
  let i = 0;
  while (i < arr.length) {
    //@ invariant 0 <= i && i <= arr.length
    //@ decreases arr.length - i
    if (arr[i] === target) return i;
    i = i + 1;
  }
  return -1;
}
```

```sh
npx lsc gen   --backend=dafny src/find.ts   # generate artefacts
npx lsc check --backend=dafny src/find.ts   # generate + verify
npx lsc regen --backend=dafny src/find.ts   # regenerate, 3-way merge
```

Key pieces:

- `//@ verify` opts a function in; once any function in a file has it,
  only marked functions are extracted.
- `//@ requires` / `//@ ensures` are the contract; `\result` names the
  return value; `==>` is implication; `forall(k, P)` / `exists(k, P)` quantify.
- `//@ invariant` and `//@ decreases` go at the top of the loop body.
- Pure functions (no loops, no mutation) are callable from other
  functions' specs; `//@ pure` forces the classification.
- Unmodellable calls are handled by `//@ extern` (deterministic
  axiom), `//@ havoc` (nondeterministic value), or file-level `//@ autohavoc`
  (abstract everything unmodellable, soundly).

The complete annotation surface, the spec expression language, and the semantic
gotcha list live in [`references/annotations.md`](references/annotations.md).

## The edit loop (Dafny backend)

`lsc gen` produces two files beside the source: `foo.dfy.gen` (always
regeneratable — never edit) and `foo.dfy` (source of truth — add helper lemmas,
ghost predicates, `assert` nudges here). The diff between them must be
**additions only**; `lsc check` enforces this. After editing the TypeScript, run
`regen` (never delete and `gen` fresh — that discards every proof). When Dafny
complains, the fix belongs either in the `.ts` (tighten `requires`, weaken
`ensures`, add `invariant`/`decreases`) or in the `.dfy` (helper lemma, ghost
predicate, assert).

The full workflow — backend choice, Lean's four-file scheme, proof debugging
flags, CI wiring, and brownfield strategy — lives in
[`references/workflow.md`](references/workflow.md).

## Anti-patterns

- **Reaching for `//@ assume` to silence a failure.** It tells the
  prover to trust the obligation unconditionally; the proof stops meaning
  anything. Restructure, or prove a helper lemma. Its one sanctioned use is
  constraining a value you deliberately `havoc`ed.
- **Refactoring production code "for clarity" during brownfield
  verification.** In-place verification is the point; an unchanged diff is the
  evidence the verified code is the shipped code.
- **Editing `.dfy.gen`.** It is regenerated; changes vanish. Edit the
  `.dfy`.
- **Deleting `.dfy` files to "start clean".** Proof work lives there;
  `regen`'s three-way merge exists precisely so you never do this.
- **Verifying a parallel model instead of the real function.** Prefer
  in-place annotation; where a type can't be imported, shadow it with
  `//@ declare-type` so the actual function stays the proof target.
- **Proving what the spec doesn't say.** Write the `//@ contract`
  intent line and check the `ensures` actually expresses it — a theorem about
  the wrong predicate verifies happily.

## Project integration

- **State the trust boundary in the README**: which functions are
  proved, and which surrounding layers (UI, I/O, auth, clock) are trusted. Case
  studies do this plainly; follow suit.
- **Track verified files in `LemmaScript-files.txt`** (one file per
  line, optional per-file timeout and flags) so `tools/check.sh` and CI verify
  them; copy hono-lemmascript's GitHub Actions workflow as the template.
- **Start small in brownfield code**: pure helpers, predicates,
  parsers without I/O. Grow towards the invariant-bearing core.
- **Keep fast-check properties alongside proofs.** They run in the
  inner loop in milliseconds, catch spec regressions before a prover run, and
  cover the unverified boundary code.
- **Land toolchain fixes separately.** When the tech preview needs a
  patch (unsupported method, missed narrowing), fix `LemmaScript/tools/src/` in
  its own PR.

## Hard-won lessons

- **The spec is the product.** Provers check what you wrote, not what
  you meant. Review `ensures` clauses as adversarially as code.
- **`number` is a mathematical integer** in the model (floats become
  `real`; overflow at 2^53 is out of scope). Do not verify float-sensitive
  numerics; do flag integer-encoding overflow risks — a case study's
  injectivity proof surfaced a real ≥1000-votes overflow in an existing
  encoding.
- **Missing invariants live in the TypeScript.** The LLM/prover loop
  can supply tactics and lemmas in the `.dfy`, but a missing `//@ invariant`
  must be added in the source and regenerated.
- **Refinement scales.** For loop-heavy code, prove the method equals
  a pure recursive spec (`result == range_spec(...)`), then prove properties of
  the spec — every property transfers automatically.
- **Verification conditions are cheap to split.**
  `dafny verify --filter-symbol=...` and `--isolate-assertions` turn one opaque
  timeout into named, tractable obligations.

## References

- [LemmaScript repository](https://github.com/midspiral/LemmaScript)
  — SPEC.md, DESIGN.md, GETTING_STARTED.md, AGENTS.md, examples.
- [Announcement post](https://midspiral.com/blog/lemmascript-a-verification-toolchain-for-typescript/)
  and [lemmascript.com](https://lemmascript.com/).
- Worked case studies:
  [hono-lemmascript](https://github.com/midspiral/hono-lemmascript)
  (brownfield, CVE-driven),
  [clear-split-lemmascript](https://github.com/midspiral/clear-split-lemmascript)
  (greenfield, dual-backend),
  [collab-todo-lemmascript](https://github.com/midspiral/collab-todo-lemmascript)
  (verified domain model behind a React app).
- [`references/annotations.md`](references/annotations.md) for the
  annotation surface, spec language, and gotchas.
- [`references/workflow.md`](references/workflow.md) for the edit
  loop, backends, CI, and brownfield strategy.
- Sampled-input testing as the complementary adversary lives in
  [`../fast-check/SKILL.md`](../fast-check/SKILL.md).
