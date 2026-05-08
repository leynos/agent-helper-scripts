---
name: verus
description: Write and maintain Verus deductive proofs for Rust code. Use for formal verification of pure functions, ordering invariants, extraction logic, and properties that require unbounded reasoning beyond what bounded model checking can provide.
---

# Verus deductive verification for Rust

This skill describes how to write, structure, and maintain Verus proofs that
provide deductive (unbounded) formal verification of Rust code. Verus uses the
Z3 SMT solver to statically verify that executable Rust code satisfies
user-provided specifications with zero runtime overhead.

## When to apply this skill

Apply this skill when:

- properties over unbounded domains (arbitrary-length sequences, any number of
  layers, all possible orderings) must be verified,
- a pure function must be shown to satisfy algebraic properties (reflexivity,
  antisymmetry, transitivity, totality),
- extraction, transformation, or mapping logic that must preserve structure
  requires verification,
- bounded model checking (Kani) has become unwieldy due to state-space
  explosion,
- compositional proofs where one lemma builds on another are needed.

Do not apply this skill when:

- bounded symbolic execution (Kani) would suffice and is simpler,
- the code under verification is tightly coupled to I/O, concurrency, or
  runtime behaviour,
- a property test would provide sufficient confidence and a proof would be
  disproportionate effort,
- the code involves features Verus does not support (async, most unsafe, raw
  concurrency).

## Where Verus fits in the verification spectrum

Verus sits at the top of the verification pyramid:

```text
                Verus (deductive proofs for pure logic)
                      ↑
                   Kani (bounded symbolic execution)
                      ↑
            Property tests (probabilistic sampling)
                      ↑
          Unit tests (specific known inputs)
                      ↑
              Lint / type checks (syntactic)
```

When a Kani harness keeps growing because control-flow complexity or state
space makes bounded exploration impractical, extract the corresponding pure
helper and move the proof obligation to Verus.

## Installation and toolchain

Verus requires a pinned release and a specific Rust nightly toolchain. The
recommended approach is a helper script that downloads, checksums, and installs
the correct version. See `references/install-verus.sh` for a reference
implementation.

### Version pinning

Pin the Verus version in a file (e.g., `tools/verus/VERSION`) and store
expected checksums in `tools/verus/SHA256SUMS`. The installation script reads these
files and verifies the download. This keeps CI deterministic.

### Running proofs

Use a `make verus` target backed by a runner script that:

1. Resolves the Verus binary (from `VERUS_BIN`, the installation directory, or
   PATH).
2. Parses the required Rust toolchain from `verus --version`.
3. Installs the toolchain via `rustup` if missing.
4. Executes the proofs.

See `references/run-verus.sh` for a reference implementation.

## Core concepts

### Three modes

Verus code operates in three modes:

| Mode   | Purpose                  | Compiled? |
|--------|--------------------------|-----------|
| `spec` | Describe properties      | No (ghost)|
| `proof`| Prove properties         | No (ghost)|
| `exec` | Ordinary Rust code       | Yes       |

Ghost code (`spec` and `proof`) is erased at compile time. It has zero runtime
cost.

### The `verus!` macro

All Verus-verified code lives inside a `verus! { ... }` block:

```rust
use vstd::prelude::*;

verus! {

pub type NodeId = nat;

pub open spec fn is_valid(id: NodeId) -> bool {
    id < 1000
}

proof fn lemma_valid_is_bounded(id: NodeId)
    requires is_valid(id),
    ensures id < 1000,
{
    // Trivial by definition; Z3 discharges automatically.
}

} // verus!
```

### Requires and ensures

Preconditions (`requires`) and postconditions (`ensures`) form the contract
between functions:

```rust
fn octuple(x1: i8) -> (x8: i8)
    requires
        -16 <= x1 < 16,
    ensures
        x8 == 8 * x1,
{
    let x2 = x1 + x1;
    let x4 = x2 + x2;
    x4 + x4
}
```

- `requires` clauses are comma-separated boolean expressions.
- `ensures` clauses use `-> (name: type)` to name the return value.
- Callers must satisfy `requires`; callees may assume `ensures`.

### Spec functions

`spec` functions define mathematical specifications. They can use `nat`,
`int`, `Seq`, `Set`, `Map`, and other mathematical types from `vstd`:

```rust
pub open spec fn count_non_self(
    neighbours: Seq<NeighbourSpec>,
    source_node: NodeId,
) -> nat
    decreases neighbours.len(),
{
    if neighbours.len() == 0 {
        0
    } else {
        let head = neighbours.first();
        let rest = neighbours.drop_first();
        if head.id == source_node {
            count_non_self(rest, source_node)
        } else {
            1 + count_non_self(rest, source_node)
        }
    }
}
```

Recursive spec functions require a `decreases` clause to prove termination.

### Proof functions (lemmas)

`proof fn` functions establish facts by invoking other lemmas and using
`assert`:

```rust
proof fn lemma_extract_from_layer_invariants(
    neighbours: Seq<NeighbourSpec>,
    source_node: NodeId,
    source_sequence: Sequence,
)
    ensures
        extract_layer_invariants(neighbours, source_node, source_sequence),
    decreases neighbours.len(),
{
    if neighbours.len() == 0 {
        // Base case: Z3 discharges automatically.
    } else {
        let rest = neighbours.drop_first();
        // Inductive step: invoke the lemma on the tail.
        lemma_extract_from_layer_invariants(rest, source_node, source_sequence);
        // Then assert the property for the full list.
        // (Details of the glue proof omitted for brevity.)
    }
}
```

## Writing a good proof

A good Verus proof is modular, trigger-aware, and context-disciplined.

### Positive example: total ordering proof

This proof establishes that a comparison function is a total ordering by
composing four lemmas (reflexive, antisymmetric, transitive, strongly
connected):

```rust
proof fn lemma_edge_leq_total_ordering()
    ensures
        total_ordering(|a: CandidateEdgeSpec, b: CandidateEdgeSpec| edge_leq(a, b)),
{
    reveal(total_ordering);
    lemma_edge_ord_leq_total_ordering();
    lemma_edge_leq_reflexive();
    lemma_edge_leq_antisymmetric();
    lemma_edge_leq_transitive();
    lemma_edge_leq_strongly_connected();
}
```

**Why this is good:**

- Each property (reflexivity, antisymmetry, transitivity, strong connectedness)
  is proved in a separate lemma, making each proof small and self-contained.
- The top-level lemma composes them cleanly.
- `reveal(total_ordering)` explicitly unfolds the definition, keeping the
  solver focused.
- Each sub-lemma can be debugged independently.

### Positive example: inductive extraction proof

This proof verifies that concatenating extracted edges preserves common
invariants across layers:

```rust
proof fn lemma_extract_from_layers_invariants(
    layers: Seq<LayerPlanSpec>,
    source_node: NodeId,
    source_sequence: Sequence,
)
    ensures
        extract_layers_invariants(layers, source_node, source_sequence),
    decreases layers.len(),
{
    if layers.len() == 0 {
        let edges = extract_from_layers(source_node, source_sequence, layers);
        assert(edges.len() == 0);
    } else {
        let head = layers.first();
        let rest = layers.drop_first();

        // Prove invariants hold for individual parts.
        lemma_extract_from_layer_invariants(head.neighbours, source_node, source_sequence);
        lemma_extract_from_layers_invariants(rest, source_node, source_sequence);

        // Prove concatenation preserves invariants.
        lemma_concat_preserves_common_invariants(
            head_edges, rest_edges,
            head_expected, rest_expected,
            source_node, source_sequence,
        );
    }
}
```

**Why this is good:**

- Follows the standard inductive proof pattern: base case, then inductive step.
- Breaks the inductive step into sub-obligations (individual parts valid,
  concatenation preserves validity).
- Each sub-obligation has its own lemma.
- The `decreases` clause makes termination explicit.

### Positive example: canonicalisation correctness

```rust
proof fn lemma_canonicalise_preserves_fields(edge: CandidateEdgeSpec)
    ensures
        edge.canonicalise().distance == edge.distance,
        edge.canonicalise().sequence == edge.sequence,
        edge.canonicalise().source <= edge.canonicalise().target,
{
    let canonical = edge.canonicalise();
    if edge.source <= edge.target {
        assert(canonical == edge);
    } else {
        assert(canonical.source == edge.target);
        assert(canonical.target == edge.source);
    }
}
```

**Why this is good:**

- The ensures clause is a complete specification of what canonicalisation must
  preserve and establish.
- The proof is a simple case split matching the function's structure.
- No unnecessary lemma calls or context pollution.

### Negative example: unscoped helper lemmas

```rust
// BAD: Calling helper lemmas without scoping pollutes the proof context.
proof fn prove_something(s: Seq<int>)
    ensures s.len() > 0 ==> s[0] >= 0,
{
    lemma_about_sequences(s);        // Adds universal quantifiers to context.
    lemma_about_non_negativity(s);   // Adds more quantifiers.
    // Z3 now has to reason about all these quantifiers for every
    // subsequent assertion, potentially causing timeouts.
}
```

**Why this is bad:**

- Universal quantifications from helper lemmas remain in the proof context
  for all subsequent goals.
- This burdens the SMT solver and can cause timeouts in unrelated assertions.
- Use `assert(...) by { ... }` to scope auxiliary proofs (see below).

### Negative example: missing triggers

```rust
// BAD: Relying on auto-selected triggers without review.
proof fn prove_all_positive(s: Seq<int>)
    requires forall|i: int| 0 <= i < s.len() ==> s[i] > 0,
    ensures s.len() > 0 ==> s[0] > 0,
{
    // If the auto-selected trigger does not match s[0], this fails
    // even though it is logically trivial.
}
```

**Why this is bad:**

- The `forall` has no explicit trigger, so Verus auto-selects one.
- If the auto-selected trigger is `s[i]`, it works. If it is something else,
  Z3 never instantiates the quantifier for `i = 0`.
- Always review auto-trigger notes or use explicit `#[trigger]` or `#![auto]`.

### Negative example: assume left in production

```rust
// BAD: assume introduces unsoundness.
proof fn prove_with_assume(x: int)
    ensures x * x >= 0,
{
    assume(x >= 0);  // Silently excludes negative x!
    // The proof is unsound: it does not hold for x = -5.
}
```

**Why this is bad:**

- `assume` instructs the solver to accept a fact without proof.
- `assume(false)` proves anything. A stray `assume` can make an entire proof
  vacuously true.
- Complete proofs must contain `assert`s but **no** `assume`s.
- Use `assume` only as a temporary placeholder during development, and replace
  with `assert` before the proof is considered done.

## Triggers: the single most important Verus concept

Triggers control how the SMT solver instantiates universal quantifiers. A
trigger is a pattern containing all bound variables that the solver matches
against concrete expressions in the proof context.

### Syntax

```rust
// Explicit trigger:
forall|i: int| 0 <= i < s.len() ==> #[trigger] is_even(s[i])

// Auto trigger (Verus selects and prints a note):
forall|i: int| #![auto] 0 <= i < s.len() ==> is_even(s[i])

// Multiple triggers per quantifier:
forall|i: int, j: int|
    #![trigger a[i], b[j]]
    #![trigger a[i], c[j]]
    0 <= i < j < a.len() ==> a[i] != b[j] && a[i] != c[j]
```

### Trigger rules

1. A trigger must mention **all** bound variables.
2. A trigger **cannot** contain: equality (`==`, `!=`), arithmetic (`+`, `-`,
   `*`, `<=`, `<`), or boolean operators (`&&`, `||`, `!`).
3. Function calls, indexing (`s[i]`), and field access (`.field`) are valid
   triggers.

### The trigger trap

Consider:

```rust
requires forall|i: int| 0 <= i < s.len() ==> #[trigger] is_even(s[i]),
```

Then `assert(s[3] % 2 == 0)` **fails** because `is_even` never appears in the
assertion, so the quantifier is never instantiated. First assert the
trigger-matching expression:

```rust
assert(is_even(s[3]));    // Instantiates the quantifier for i = 3.
assert(s[3] % 2 == 0);   // Now succeeds using the fact from above.
```

### Matching loops

A matching loop occurs when instantiating a trigger produces new expressions
that match the same trigger, causing potentially infinite instantiation.

**Bad** (matching loop):

```rust
forall|i: int|
    0 <= i < s.len() - 1 ==> #[trigger] s[i] <= s[i + 1]
```

Matching `i = 2` produces `s[3]`, which matches `i = 3` producing `s[4]`,
continuing indefinitely.

**Good** (no matching loop):

```rust
forall|i: int, j: int|
    #![trigger s[i], s[j]]
    0 <= i <= j < s.len() ==> s[i] <= s[j]
```

Each instantiation requires two concrete `s[_]` expressions already in context.

### Practical trigger workflow

1. Start with `#![auto]` and review the trigger note Verus prints.
2. When a proof fails, check whether the concrete expressions in the
   assertions match the auto-selected trigger.
3. Otherwise, add explicit `#[trigger]` annotations.
4. For slow proofs, check for matching loops.

## `assert(...) by { ... }`: scoping proof context

When a fact `F` requires auxiliary proof `P`, use `assert(F) by { P }` to
prevent `P`'s facts from polluting subsequent proof goals:

```rust
proof fn example(s: Seq<int>) {
    // Prove F using lemma_B, but do not let lemma_B's facts leak.
    assert(some_fact(s)) by {
        lemma_about_sequences(s);
    };
    // Here, only some_fact(s) is known, not the internals of lemma_B.
    assert(another_fact(s));  // Not burdened by lemma_B's quantifiers.
}
```

This is one of the most important patterns for keeping proofs fast and
maintainable.

## Nonlinear arithmetic

Z3 handles linear arithmetic well but struggles with nonlinear expressions
(`x * y` where neither is constant). Verus disables nonlinear arithmetic axioms
by default.

### `by(nonlinear_arith)`

General-purpose but unpredictable:

```rust
assert(x * y <= 100) by(nonlinear_arith)
    requires x <= 10, y <= 10;
```

### `by(integer_ring)`

Decidable and deterministic, but limited to equational ring theory:

```rust
proof fn lemma(a: int, b: int, c: int) by(integer_ring)
    requires (a - b) % c == 0,
    ensures (a * a - b * b) % c == 0;
```

**`integer_ring` limitations:**

- Only supports `int` parameters.
- No inequality support.
- No division support.
- Cannot prove `a % b == x` (unless `x == 0`).

Combine both: use `integer_ring` for algebraic identities as helper lemmas,
then `nonlinear_arith` for the main theorem. Fall back to manual lemmas from
`vstd::arithmetic` if neither mode works.

## Project structure

### Proof file organisation

Keep Verus proofs in a dedicated directory (e.g., `verus/`) at the repository
root, separate from the Cargo workspace:

```text
project/
├── Cargo.toml
├── src/
│   └── ...
├── verus/
│   ├── my_proofs.rs          # Main proof file with types and specs
│   ├── my_proofs_extract.rs  # Extraction invariant proofs
│   └── my_proofs_ordering.rs # Ordering property proofs
├── scripts/
│   ├── install-verus.sh
│   └── run-verus.sh
└── tools/
    └── verus/
        ├── VERSION
        └── SHA256SUMS
```

Verus files use `mod` declarations and `use super::*` to share types and
specifications across proof files:

```rust
// my_proofs.rs (root)
mod my_proofs_extract;
mod my_proofs_ordering;

fn main() {}

verus! {
    // Types, specs, and top-level lemmas here.
}
```

```rust
// my_proofs_extract.rs
verus! {
    use super::*;
    // Sub-proofs that use types from the root module.
}
```

### Makefile integration

```makefile
verus: ## Run Verus proofs
    VERUS_BIN="$(VERUS_BIN)" scripts/run-verus.sh
```

## Mirroring production types as specs

Verus proofs operate on `spec` types (`nat`, `int`, `Seq`, `Set`) rather than
production Rust types (`usize`, `i64`, `Vec`). Define spec structs that mirror
production data:

```rust
verus! {

// Mirrors the production NeighbourEntry struct.
pub struct NeighbourSpec {
    pub id: NodeId,       // nat, not usize
    pub distance: Distance, // int, not f32
}

// Mirrors the production CandidateEdge struct.
pub struct CandidateEdgeSpec {
    pub source: NodeId,
    pub target: NodeId,
    pub distance: Distance,
    pub sequence: Sequence,
}

} // verus!
```

Keep the correspondence explicit with comments naming the production type.

## Common gotchas and hard-won lessons

### Triggers are not optional

If a proof fails and the logic seems correct, the problem is almost certainly
a trigger mismatch. Before debugging the logic, check whether the concrete
expressions in the assertions match the quantifier triggers. This accounts
for the majority of "why does this obvious proof fail?" situations.

### `assert` in Verus is not `assert!` in Rust

Verus `assert` is a static verification request to Z3. It has no runtime
effect. Rust `assert!` is a runtime panic. Do not confuse the two. Inside
`verus! { }`, use `assert`; outside, use `assert!`.

### `assume` is a loaded gun

Every `assume` in a proof is a soundness hole. Use it only during
development as a placeholder. Before considering a proof complete, search for
and eliminate all `assume` statements. A proof with `assume(false)` anywhere
in its call chain proves literally anything.

### `broadcast use` for sequence axioms

Many sequence operations require axioms that Z3 does not know by default. Use:

```rust
broadcast use vstd::seq::group_seq_axioms;
```

at the top of proof functions that manipulate sequences. Without this, proofs
about `Seq::add`, `Seq::push`, or indexing across concatenated sequences will
fail mysteriously.

### Proof context pollution causes timeouts

If a proof works in isolation but times out when composed with other proofs,
the likely cause is proof context pollution. Universal quantifications from
helper lemmas burden Z3 on every subsequent goal. Use `assert(...) by { ... }`
to scope auxiliary proofs aggressively.

### Recursive proofs need `decreases`

Every recursive `spec fn` and `proof fn` must have a `decreases` clause. Verus
will reject the function without one. The argument to `decreases` must be a
natural number that strictly decreases on each recursive call. For sequence
recursion, `decreases seq.len()` is the standard pattern.

### `open spec fn` vs `closed spec fn`

- `open spec fn`: Callers can see and reason about the function body.
- `closed spec fn`: Callers can only use the function's `ensures` clause.

Use `open` for specification functions that callers need to unfold. Use
`closed` to encapsulate implementation details. Most specification functions
should be `open`.

### `reveal` for opaque definitions

Some definitions from `vstd` (e.g., `total_ordering`) are opaque by default.
Call `reveal(name)` to make the definition available to the solver:

```rust
proof fn lemma_my_total_ordering()
    ensures total_ordering(my_leq),
{
    reveal(total_ordering);
    // Now Z3 knows what total_ordering means.
}
```

Without `reveal`, Z3 treats the definition as an uninterpreted symbol and
cannot prove anything about it.

### Index arithmetic in quantifiers

Expressions like `i - 1` or `i + 1` in quantifiers can confuse the solver
because they introduce arithmetic into what should be a pure trigger context.
Prefer auxiliary variables:

```rust
// Instead of reasoning about edges[i] == rest_edges[i - 1]:
let j = i - 1;
assert(0 <= j < rest_edges.len());
assert(edges[i] == rest_edges[j]);
```

### Verus is not a Cargo dependency

Verus runs as a standalone binary, not through `cargo build`. Verus proof
files are compiled by Verus directly, not by `rustc`. This means:

- Verus files cannot `use` production crate modules.
- Type definitions must be duplicated as spec structs.
- Keep the spec structs synchronised with production types manually (or via
  code review).

### The Z3 timeout cliff

Z3 performance is nonlinear. Adding one more `forall` to the proof context
can tip the solver from 0.5 seconds to timeout. When this happens:

1. Identify which lemma call introduced the problematic quantifier.
2. Wrap it in `assert(...) by { ... }`.
3. If that is insufficient, split the proof into smaller lemmas.

### Ghost code erasure

`verus --compile` produces executables with all ghost code erased. Spec and
proof functions have zero runtime cost. This is by design and is one of Verus's
key selling points.

## References

- [Verus Guide](https://verus-lang.github.io/verus/guide/)
- [Verus GitHub](https://github.com/verus-lang/verus)
- [Verus Releases](https://github.com/verus-lang/verus/releases)
- [vstd Documentation](https://verus-lang.github.io/verus/verusdoc/vstd/)
- [Verus Playground](https://play.verus-lang.org/)
