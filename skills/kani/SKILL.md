---
name: kani
description: Write and maintain Kani bounded model checking harnesses for Rust code. Use when formally verifying structural invariants, unsafe code, bounded state machines, or dispatch logic via exhaustive symbolic execution.
---

# Kani bounded model checking for Rust

This skill describes how to write, structure, and maintain Kani proof harnesses
that provide exhaustive bounded verification of Rust code. Kani uses CBMC (C
Bounded Model Checker) as its backend to explore every possible execution path
within specified bounds, providing formal guarantees rather than probabilistic
coverage.

## When to apply this skill

Apply this skill when:

- structural invariants in data structures (bidirectional links, uniqueness,
  ordering, reachability) must be verified,
- `unsafe` code is being written or reviewed and exhaustive coverage of
  undefined behaviour is needed,
- bounded state machines, dispatch selectors, or parser-like logic require
  verification,
- property-based testing should be complemented with exhaustive bounded
  exploration,
- Kani harnesses are being added or modified in a codebase.

Do not apply this skill when:

- the property requires unbounded induction over arbitrary-size inputs (use
  Verus instead),
- the code is concurrency-heavy (Kani does not model concurrency),
- the code depends heavily on I/O, file systems, or network operations,
- a simple unit test or property test would suffice.

## Where Kani fits in the verification spectrum

Kani occupies a specific position in the verification hierarchy:

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

- **Property tests** (proptest, quickcheck) sample random inputs and shrink
  counterexamples. They scale to realistic sizes but cannot prove absence of
  bugs.
- **Kani** exhaustively explores all inputs within a bound. It proves
  correctness for bounded configurations but cannot scale beyond small state
  spaces.
- **Verus** provides deductive proofs over unbounded domains using an SMT
  solver. It requires pure specification functions and explicit proof
  engineering.

Use Kani when bounded exhaustion is tractable. Move to Verus when the state
space grows beyond what Kani can handle, or when unbounded guarantees are needed.

## Installation

Install Kani via Cargo:

```bash
cargo install --locked kani-verifier
cargo kani setup
```

Kani requires a specific Rust nightly toolchain, which `cargo kani setup`
installs automatically.

## Core concepts

### Proof harnesses

A Kani proof harness is a function annotated with `#[kani::proof]`. It is
analogous to a test function but uses nondeterministic inputs to represent all
possible values:

```rust
#[cfg(kani)]
#[kani::proof]
fn verify_my_invariant() {
    let x: u32 = kani::any();
    kani::assume(x < 100);
    let result = my_function(x);
    kani::assert(result > 0, "result must be positive");
}
```

### Nondeterministic inputs

`kani::any::<T>()` produces a symbolic value representing every possible bit
pattern for type `T`. Kani explores all of them. For custom types, derive or
implement `kani::Arbitrary`:

```rust
#[cfg_attr(kani, derive(kani::Arbitrary))]
struct MyConfig {
    threshold: u8,
    enabled: bool,
}
```

### Assumptions

`kani::assume(condition)` constrains the symbolic search space. It is the
formal equivalent of a precondition. Only use it to mirror production
preconditions — never to paper over bugs.

### Assertions

`kani::assert(condition, message)` states the property that must hold. If Kani
finds any input satisfying the assumptions where the assertion fails, it
produces a counterexample.

### Loop unwinding

Kani cannot verify code with truly unbounded loops. Use `#[kani::unwind(n)]`
to set an upper bound on loop iterations. The bound must be **one greater than
the maximum number of iterations**. If a loop runs at most 10 times, set
`#[kani::unwind(11)]`.

## Writing a good harness

A good harness is small, focused, and exercises production code paths.

### Structure

Every harness follows the same four-phase pattern:

1. **Setup**: Construct the data structure deterministically or with minimal
   nondeterminism.
2. **Nondeterministic population**: Use `kani::any()` and `kani::any::<bool>()`
   to explore configurations.
3. **Precondition enforcement**: Use `kani::assume()` to mirror production
   invariants.
4. **Invariant assertion**: Use `kani::assert()` to state the property under
   verification.

### Positive example: exercising production code paths

This harness drives the actual production reconciliation logic and verifies
that it maintains the bidirectional invariant:

```rust
/// Verifies that reconciliation preserves bidirectional links.
#[kani::proof]
#[kani::unwind(4)]
fn verify_bidirectional_links_reconciliation_2_nodes_1_layer() {
    let params = HnswParams::new(1, 1).expect("params must be valid");
    let max_connections = params.max_connections();
    let mut graph = Graph::with_capacity(params, 2);

    graph
        .insert_first(NodeContext { node: 0, level: 0, sequence: 0 })
        .expect("insert node 0");
    graph
        .attach_node(NodeContext { node: 1, level: 0, sequence: 1 })
        .expect("attach node 1");

    let should_link = kani::any::<bool>();
    if should_link {
        add_edge_if_missing(&mut graph, 0, 1, 0);
        let ctx = KaniUpdateContext::new(0, 0, max_connections);
        let added = ensure_reverse_edge_for_kani(&mut graph, ctx, 1);
        kani::assert(added, "expected reverse edge to be inserted");
    }

    kani::assert(
        is_bidirectional(&graph),
        "bidirectional invariant violated after reconciliation",
    );
}
```

**Why this is good:**

- Exercises the actual production function (`ensure_reverse_edge_for_kani`),
  not a reimplementation.
- Uses `kani::any::<bool>()` to explore both the linked and unlinked states.
- Assertions verify a meaningful structural invariant.
- The harness is small enough to complete in under two minutes.
- The unwind bound (4) is tight and documented.

### Positive example: eviction and deferred scrub

This harness verifies a multi-step scenario (eviction triggers a deferred
scrub that cleans up orphaned edges):

```rust
/// Verifies that eviction triggers correct deferred scrub behaviour.
#[kani::proof]
#[kani::unwind(10)]
fn verify_eviction_deferred_scrub_reciprocity() {
    let params = HnswParams::new(1, 2).expect("params must be valid");
    let max_connections = params.max_connections();
    let mut graph = setup_eviction_test_graph(params);

    // Seed node 1 at capacity with node 2 (bidirectional at level 1).
    add_edge_if_missing(&mut graph, 1, 2, 1);
    add_edge_if_missing(&mut graph, 2, 1, 1);

    // Update: node 0 adds node 1 as neighbour at level 1.
    // ensure_reverse_edge evicts node 2 and creates a deferred scrub.
    let update_ctx = EdgeContext { level: 1, max_connections };
    let staged = StagedUpdate { node: 0, ctx: update_ctx, candidates: vec![1] };
    let updates: Vec<FinalisedUpdate> = vec![(staged, vec![1])];
    let new_node = NewNodeContext { id: 3, level: 1 };

    apply_commit_updates_for_kani(&mut graph, max_connections, new_node, updates)
        .expect("commit-path updates must succeed");

    kani::assert(
        is_bidirectional(&graph),
        "bidirectional invariant violated after eviction and deferred scrub",
    );

    assert_node_link(
        &graph,
        EdgeAssertion::new(1, 0, 1),
        "node 1 should link to node 0 after eviction",
    );
    assert_no_node_link(
        &graph,
        EdgeAssertion::new(2, 1, 1),
        "deferred scrub should remove node 2's forward edge to node 1",
    );
}
```

**Why this is good:**

- Tests a specific, non-trivial scenario (eviction cascade).
- Verifies both the positive outcome (new edge exists) and negative outcome
  (orphaned edge removed).
- Drives production code (`apply_commit_updates_for_kani`).
- The scenario is documented with a clear narrative.

### Negative example: reimplementing the invariant in the harness

```rust
// BAD: This harness inserts reverse edges itself, so it cannot detect
// missing reciprocity in production code.
#[kani::proof]
fn verify_bidirectional_bad() {
    let mut graph = make_graph(3);
    let a: usize = kani::any();
    let b: usize = kani::any();
    kani::assume(a < 3 && b < 3 && a != b);

    // The harness itself enforces the invariant it claims to verify!
    graph.add_edge(a, b, 0);
    graph.add_edge(b, a, 0);  // ← manually inserting the reverse edge

    assert!(is_bidirectional(&graph));  // Always passes, proves nothing.
}
```

**Why this is bad:**

- The harness manually inserts reverse edges, so it cannot detect if the
  production code fails to do so.
- The assertion is tautologically true by construction.
- A targeted mutation test (skip the reverse edge insertion in production code)
  would not cause this harness to fail.

### Negative example: over-constrained assumptions

```rust
// BAD: kani::assume constrains inputs so tightly that most states are
// excluded, hiding bugs in the unexplored space.
#[kani::proof]
fn verify_over_constrained() {
    let x: u32 = kani::any();
    kani::assume(x == 42);  // Only one value explored!
    let result = process(x);
    kani::assert(result.is_ok(), "process must succeed");
}
```

**Why this is bad:**

- Only a single input is explored. This is a unit test pretending to be formal
  verification.
- Bugs triggered by other inputs are invisible.
- Use `--coverage -Z source-coverage` to detect this: target 100% code
  coverage within the assumptions.

### Negative example: excessive unwind bound

```rust
// BAD: Unwind bound is much larger than needed, causing Kani to spend
// minutes exploring impossible iterations.
#[kani::proof]
#[kani::unwind(1000)]
fn verify_wasteful() {
    let mut v = Vec::new();
    for i in 0..3u32 {
        v.push(i);
    }
    kani::assert(v.len() == 3, "length must be 3");
}
```

**Why this is bad:**

- The loop runs exactly 3 times, so `#[kani::unwind(4)]` is sufficient.
- An unwind of 1000 wastes solver time exploring 996 impossible iterations.
- Start with a tight bound and increase only if unwinding assertion failures
  occur.

## What Kani can and cannot detect

### Kani detects

- Panics (`unwrap()` on `None`, index out of bounds, explicit `panic!()`)
- Arithmetic overflow (in debug mode)
- Null pointer dereference (in unsafe code)
- Assertion failures (`kani::assert`, `assert!`, `debug_assert!`)
- Undefined behaviour in unsafe blocks
- Bit-shift overflow

### Kani does not support

- **Concurrency**: Atomics and thread-locals are treated as sequential. Do not
  use Kani for data-race detection.
- **I/O**: File operations, network calls, and system interactions are not
  modelled.
- **Unbounded data structures**: `Vec`, `String`, and heap-allocated
  collections require manual bounds.
- **Floating-point precision**: Trigonometric and sqrt functions are
  over-approximated, producing spurious failures. Use stubs.
- **async/await**: Not supported.

## Project integration

### Conditional compilation

Always gate Kani code behind `#[cfg(kani)]`:

```rust
#[cfg(kani)]
mod kani_proofs;
```

This prevents Kani harnesses from interfering with normal builds, tests, or
clippy.

### Cargo.toml configuration

Declare `kani` as a valid cfg to suppress unknown-cfg warnings:

```toml
[lints.rust]
unexpected_cfgs = { level = "warn", check-cfg = ["cfg(kani)"] }
```

### Makefile targets

Split harnesses into practical (fast) and full (slow) tiers:

```makefile
kani: ## Run practical Kani harnesses (fast feedback)
    cargo kani -p my-crate --default-unwind 4 \
        --harness verify_smoke_test
    cargo kani -p my-crate --default-unwind 4 \
        --harness verify_reconciliation_2_nodes

kani-full: ## Run all Kani harnesses (slow, nightly CI)
    cargo kani -p my-crate --default-unwind 10
```

- `make kani` runs in the local development loop (target: under 3 minutes).
- `make kani-full` runs in nightly CI or on-demand.

### Nightly CI gating

Expensive `kani-full` runs can be gated on whether main has received commits
within the last 24 hours, avoiding wasted compute on quiet days.

## Stubbing

When production code uses features Kani cannot handle (inline assembly,
complex serialization, FFI), replace them with simplified versions:

```rust
#[cfg(kani)]
fn mock_random<T: kani::Arbitrary>() -> T {
    kani::any()
}

#[kani::proof]
#[kani::stub(rand::random, mock_random)]
fn verify_with_random() {
    let key: u32 = rand::random();
    // Kani replaces rand::random with mock_random, which returns kani::any()
}
```

Run with: `cargo kani -Z stubbing --harness verify_with_random`

**Stub lifetime gotcha**: Kani accepts stubs with different lifetime
annotations, but mismatches can cause subtle verification failures. Match
lifetimes exactly.

## Function contracts (experimental)

Kani supports function contracts for compositional verification:

```rust
#[kani::requires(divisor != 0)]
#[kani::ensures(|result| *result <= dividend)]
fn safe_div(dividend: u32, divisor: u32) -> u32 {
    dividend / divisor
}

#[kani::proof_for_contract(safe_div)]
fn verify_safe_div() {
    let a: u32 = kani::any();
    let b: u32 = kani::any();
    safe_div(a, b);
}
```

Run with: `cargo kani -Z function-contracts`

Use `#[kani::stub_verified(function_name)]` to replace verified functions with
their contracts in other harnesses, reducing solver load.

## Mutation testing

Validate that the harness is sensitive to the bug it claims to catch. The
simplest mutation test:

1. Temporarily break the production code (e.g., skip inserting a reverse edge).
2. Run the harness.
3. Confirm it fails with a meaningful error message.

If the harness still passes after the mutation, it is not testing what it
appears to test.

## Common gotchas and hard-won lessons

### Unwind bound off-by-one

The unwind bound must be **one more than** the number of loop iterations. A
loop running 10 times needs `#[kani::unwind(11)]`. This catches every
newcomer.

### Vec and heap allocation do not scale

`kani::any::<Vec<T>>()` does not exist. Bounded collections must be constructed manually.
collections. Even small `Vec`s with 2--3 elements can take minutes. A proof
harness with nondeterministic inventory of size 2 will likely take a couple of
minutes to verify.

### Compilation is slow

Kani compiles the entire crate through its own pipeline before running the
solver. The first run takes significantly longer than subsequent runs. Do not
be surprised by a 30--60 second compilation phase before verification begins.

### Warnings about unsupported constructs

Kani emits warnings about `caller_location`, foreign functions, and
concurrency primitives (atomics, thread-locals) treated as sequential. These
are only problematic if the relevant code is reachable by the harness. If the
warnings mention code the harness does not exercise, they are safe to ignore.

### Coverage checking

Use `cargo kani --coverage -Z source-coverage` to verify that assumptions are
not over-constraining the search space. If coverage is less than 100% within
the bounded configuration, the assumptions are hiding code paths.

### Start small, grow deliberately

Start with 2-node harnesses and trivial configurations. Get them passing.
Then increase bounds one step at a time. A 3-node harness that explores 64
edge configurations can take 10+ minutes. A 4-node harness may not terminate.

### Separate harness helpers from production code

Create `#[cfg(kani)]` helper functions that bundle setup, precondition
validation, and production-code invocation. This keeps harnesses readable and
allows the helpers to enforce preconditions that mirror production invariants.

### Do not add Kani to the normal test path

Kani runs take minutes, not seconds. Keep `make kani` as an explicit opt-in
target, not part of `make test`. Reserve `make kani-full` for nightly CI.

### Solver choice matters

The default solver (CaDiCaL) works well for most harnesses. If a harness times
out, try `#[kani::solver(kissat)]` or `#[kani::solver(cadical)]`. Some
harnesses respond dramatically to solver changes.

### The 3-node cliff

There is a sharp combinatorial cliff between 2-node and 3-node harnesses. A
2-node smoke test might complete in 15 seconds; the same invariant on 3 nodes
might take 10 minutes or time out entirely. Plan for this when designing
harness tiers.

### Assertions are the specification

Every `kani::assert` in a passing harness is a proven theorem for the bounded
configuration. Treat harnesses as executable specifications and keep them
alongside the code they verify.

## References

- [Kani Rust Verifier](https://github.com/model-checking/kani)
- [Kani Documentation](https://model-checking.github.io/kani/)
- [Kani First Steps Tutorial](https://model-checking.github.io/kani/tutorial-first-steps.html)
- [Kani Attributes Reference](https://model-checking.github.io/kani/reference/attributes.html)
- [Kani Stubbing](https://model-checking.github.io/kani/reference/experimental/stubbing.html)
- [Kani Function Contracts](https://model-checking.github.io/kani/reference/experimental/contracts.html)
- [Kani Rust Feature Support](https://model-checking.github.io/kani/rust-feature-support.html)
