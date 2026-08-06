# LemmaScript annotations, spec language, and gotchas

Condensed from SPEC.md v0.5.x. All annotations are comments beginning `//@`
(followed by a space) in ordinary TypeScript.

## Annotation surface

### File-level directives (top of file, column 0)

| Annotation          | Meaning                                                                                                                                                                                              |
| ------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `//@ backend dafny` | Restrict the file to one backend. Files are silently skipped when `lsc` runs with a different `--backend`. Required for Dafny-only features (classes, `havoc`, `assume`, `perm`, bitwise encodings). |
| `//@ safe-slice`    | Give two-arg `slice(lo, hi)` JavaScript clamping semantics via a `SafeSlice` helper. Without it, slices require provable `0 <= lo <= hi <= length`.                                                  |
| `//@ autohavoc`     | Abstract every unmodellable expression in the file to a nondeterministic value (Dafny only; see below).                                                                                              |

### Function contracts (before the first statement of the body)

| Annotation          | Meaning                                                                                                                                                                                                                                                                          |
| ------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `//@ verify`        | Opt this function into verification. Once any function in a file carries it, only marked functions are extracted (types and module `const`s are always extracted).                                                                                                               |
| `//@ requires E`    | Precondition.                                                                                                                                                                                                                                                                    |
| `//@ ensures E`     | Postcondition; `\result` names the return value.                                                                                                                                                                                                                                 |
| `//@ contract text` | Natural-language intent. Never reaches the prover; checked against `ensures` by the external `lemmascript-claimcheck` tool.                                                                                                                                                      |
| `//@ decreases E`   | Termination metric (also valid on loops). Accepts well-founded measures: naturals, lexicographic tuples.                                                                                                                                                                         |
| `//@ type x nat`    | Type override for a variable — most often `nat` for indices and counters. Also usable as a leading comment on type aliases and a trailing comment on interface fields. `//@ type T (==)` adds a Dafny equality constraint to a generic parameter (needed for `===` on generics). |

### Loop annotations (before the first statement of the loop body)

| Annotation        | Meaning                                                                                                                                                                                  |
| ----------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `//@ invariant E` | Loop invariant.                                                                                                                                                                          |
| `//@ decreases E` | Loop termination metric.                                                                                                                                                                 |
| `//@ done_with E` | Post-loop condition for loops containing `break`. Required on the Lean backend (Velvet otherwise assumes the negated loop condition, which is wrong with `break`); unnecessary on Dafny. |

### Declaration-site annotations (before the function declaration)

| Annotation   | Meaning                                                                                                                                                                                                                                                                                                      |
| ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `//@ pure`   | Force pure classification so the function is callable from other functions' specs. If the body cannot be auto-converted, Dafny emits `function by method` with an **empty spec body that is a parse error until you hand-write it in the `.dfy`** (regen preserves it). Lean rejects non-convertible bodies. |
| `//@ extern` | Body-less axiom: signature plus any `requires`/`ensures`, body skipped. Emits `function {:axiom}`. Deterministic and extensional (`f(x) == f(x)` holds — unlike havoc). Dotted form `//@ extern fs.readFileSync` axiomatizes a library call; pair with a body-less `declare function` carrying the contract. |

### Statement-level annotations (before any statement)

| Annotation                                | Meaning                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| ----------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `//@ ghost let x = e` / `//@ ghost x = e` | Proof-only variable declaration / reassignment. Optional type: `//@ ghost let x: T = e`. Init supports `new Set()`, `new Map()`, and spec expressions.                                                                                                                                                                                                                                                                                         |
| `//@ assert E`                            | Assertion (proof nudge).                                                                                                                                                                                                                                                                                                                                                                                                                       |
| `//@ assume E`                            | Trusted assumption — Dafny only. **Do not use to silence failures**; its sanctioned use is constraining a value you just `havoc`ed.                                                                                                                                                                                                                                                                                                            |
| `//@ skip`                                | Omit the next statement from the model (side-effect-only code).                                                                                                                                                                                                                                                                                                                                                                                |
| `//@ havoc`                               | Before a `let`/`const` or plain assignment: discard the RHS, give the target an arbitrary value of its declared type (Dafny only). Variants: `//@ havoc <name>` havocs only calls to that function inside the expression; `//@ havoc : T` types the havoc (`//@ havoc : Edge \| undefined` produces an Option); destructuring havocs each binding. Only plain `x = e` is havoc-able. Functions containing havoc become impure Dafny `method`s. |
| `//@ declare-type N { f: T, ... }`        | Declare a record type when imports cannot resolve, or shadow a real type (e.g. replace a function-valued field with plain data so the real function stays the proof target). Alias form: `//@ declare-type Ruleset = Rule[]`. Dotted references resolve by last segment.                                                                                                                                                                       |

### Autohavoc

File-level or per-function (next to `//@ verify`), Dafny only. Abstracts every
unmodellable expression to nondeterminism so the proof rests on control flow
plus declared contracts. Guarantees: it only havocs, never assumes, so proofs
can fail spuriously but never pass spuriously; any call to a function with a
`requires` (a *sink*) is preserved so its precondition is still checked;
discarded calls are reported. The trust boundary is "every *contracted* sink is
reached only under its guard" — uncontracted dangerous calls are invisible.

## Spec expression language

A TypeScript-expression subset with extensions. Precedence from loosest: `<==>`
(iff), `==>` (implication, right-associative), `||`, `&&`, comparisons (`===`,
`!==`, `<`, `<=`, `>`, `>=`, `in`), arithmetic (`+ - * / %`), unary (`!`, `-`).

- `\result` — the return value; only in `ensures`.
- `forall(k, P)` / `exists(k, P)` — quantifiers. Optional explicit
  type: `forall(k: nat, ...)`, `forall(x: MyType, ...)`. Untyped binders are
  inferred from collection usage (`m.has(k)`, `arr.includes(k)`) and default to
  `int`.
- `perm(a, b)` — arrays equal as multisets (permutation). Spec-only,
  Dafny only. The canonical tool for order-independence theorems.
- `old(...)` — **not yet supported** in TS annotations. For mutating
  class methods, `this.field` in `ensures` means the *post*-state; hand-write
  `old(this.field)` clauses in the `.dfy`.
- `x in coll` — membership for sets, sequences, and map keys.
- Top-level `&&` in `requires`/`ensures`/`invariant` is split into
  separate clauses; `(A && B) ==> C` emits curried `A ==> B ==> C`.

Most everyday string, array, map, set, and `Math` operations are modelled:
`s.startsWith/endsWith/includes/indexOf/slice/trim/split` (split requires a
non-empty separator),
`arr.map/filter/every/some/ includes/indexOf/findIndex/flat/join/sort/concat`,
spreads (`[...a, x]`), `m.get/set/has/delete/size`, `s.has/add/delete/size`,
`Math.abs/min/max/floor/ceil`, `Math.max(...arr)` (requires non-empty), and
template literals. `arr.sort(cmp)` is axiomatized as a sorted permutation and
requires `cmp` to be a total preorder.

## Supported TypeScript fragment

- **Types**: `number` → `int` (or `nat` via `//@ type`), `bigint` →
  `int`, `boolean`, `string`, `T[]` → `seq`, `Map`/`Record` → `map`, `Set` →
  `set`, `T | undefined` and `T | null` → `Option`, tuples → `seq`, interfaces
  and object types → datatypes, discriminated unions → `datatype`/`inductive`,
  string-literal unions → enum-like (members must be valid identifiers:
  `"Add"`, not `"+"`). `unknown` maps to `int` — avoid it.
- **Statements**: `let`/`const`, assignment (including `arr[i] = v`,
  compound assigns, `++`/`--`), `if`/`else`, `while`, C-style `for`, `for-of`
  (desugared to an indexed loop with an automatic bound invariant), `break`,
  `return`, `switch` on discriminants (no fall-through), `throw new Error(...)`
  → `assert false`.
- **Narrowing**: `v !== undefined`, truthiness, `&&`/`||`, `kind ===`
  discriminants, `'field' in x`, early-return guards, optional chaining, `??`.
  Narrowing patterns fire only on pure access paths (`x`, `a.b.c`) — bind
  method-call results to a variable first.
- **Classes**: Dafny only; `//@ backend dafny`. `modifies this` /
  `reads this` clauses are not generated — add them in the `.dfy`.
- **Excluded**: `await` (an `async` function with no `await` is fine;
  `Promise<T>` unwraps to `T`), `this`-dispatch and inheritance, closures over
  mutable state, `any`, `eval`, dynamic property access, regex, `JSON.parse`,
  I/O, crypto (handle the last group via `extern`/`havoc`/`autohavoc`).
  Statement-block lambdas that cannot flatten to an expression are rejected.

## Purity

A function is auto-classified pure when its body has no loops, no mutable
`let`, and calls only pure functions. Pure functions emit as Dafny `function`s
/ Lean `Pure` namespace `def`s and are the only functions callable from specs.
On the Lean backend, pure defs are **total** — `requires` clauses are dropped
from the `Pure` def, so they must accept any input (they get called from
runtime checks).

## Gotchas

1. **`number` is a mathematical integer**; non-integer literals become
   `real`. IEEE 754 behaviour and 2^53 overflow are out of scope.
2. **Map vs Record at runtime**: both model as `map`, but a value
   built with `new Map()` and returned as a `Record` verifies yet fails at
   runtime — wrap with `Object.fromEntries(result)` (an identity in the model,
   a real conversion at runtime).
3. **`return` inside a loop** works on Dafny but not on Lean —
   restructure to `break` + result variable + `//@ done_with`.
4. **Short-circuit is lost when method calls are lifted** out of
   `&&`/`||`: both sides execute in the model.
5. **Class array-field mutation**: after `this.arr[i] = v`, an
   `ensures this.arr[i] == v` needs a hand-added
   `ensures |this.arr| == old(|this.arr|)` in the `.dfy`.
6. **Uninitialized `let x: T;`** gets a type-appropriate default for
   collections/options/primitives; other types will not compile — initialize,
   or annotate `T | undefined`.
7. **Cross-file calls are automatically axiomatized**: callees in
   other files emit as `function {:axiom}` carrying their source `requires`/
   `ensures`. Their bodies are *not* verified from this file — verify them in
   their own file if they matter.
8. **Bitwise operators** are arithmetic encodings with literal RHS
   only (`x >> 32n` → division, `x & mask` only when `mask + 1` is a power of
   two). Dafny only.
