//! Kani harness structure reference from a production HNSW graph library.
//!
//! This file demonstrates the harness structure, helper patterns, and
//! integration approach used in a production Rust codebase. It is included
//! for reference and is not compiled directly by `rustc`; harnesses require
//! `#[cfg(kani)]` and are executed via `cargo kani`.
//!
//! Pairs with `skills/kani/SKILL.md`.

// ---------------------------------------------------------------------------
// Cargo.toml: declare kani as a valid cfg
// ---------------------------------------------------------------------------
//
// [lints.rust]
// unexpected_cfgs = { level = "warn", check-cfg = ["cfg(kani)"] }

// ---------------------------------------------------------------------------
// Module declaration: conditionally compile the harness module
// ---------------------------------------------------------------------------
//
// In src/hnsw/mod.rs:
//
// #[cfg(kani)]
// mod kani_proofs;

// ---------------------------------------------------------------------------
// Makefile targets
// ---------------------------------------------------------------------------
//
// kani: ## Run practical Kani harnesses (fast feedback)
//     cargo kani -p my-crate --default-unwind 4 \
//         --harness verify_smoke_2_nodes
//     cargo kani -p my-crate --default-unwind 4 \
//         --harness verify_reconciliation_2_nodes
//
// kani-full: ## Run all Kani harnesses (slow, nightly CI)
//     cargo kani -p my-crate --default-unwind 10

// ---------------------------------------------------------------------------
// Harness: deterministic smoke test
// ---------------------------------------------------------------------------

#[cfg(kani)]
#[kani::proof]
#[kani::unwind(4)]
fn verify_bidirectional_links_smoke_2_nodes_1_layer() {
    // Phase 1: Deterministic setup
    let params = HnswParams::new(1, 1).expect("params must be valid");
    let mut graph = Graph::with_capacity(params, 2);

    graph
        .insert_first(NodeContext { node: 0, level: 0, sequence: 0 })
        .expect("insert node 0");
    graph
        .attach_node(NodeContext { node: 1, level: 0, sequence: 1 })
        .expect("attach node 1");

    // Phase 2: Deterministic edge population
    add_bidirectional_edge(&mut graph, 0, 1, 0);

    // Phase 3: No assumptions needed (deterministic setup)

    // Phase 4: Assert the invariant
    kani::assert(
        is_bidirectional(&graph),
        "bidirectional invariant violated in smoke harness",
    );
}

// ---------------------------------------------------------------------------
// Harness: nondeterministic reconciliation
// ---------------------------------------------------------------------------

#[cfg(kani)]
#[kani::proof]
#[kani::unwind(4)]
fn verify_bidirectional_links_reconciliation_2_nodes_1_layer() {
    // Phase 1: Deterministic setup
    let params = HnswParams::new(1, 1).expect("params must be valid");
    let max_connections = params.max_connections();
    let mut graph = Graph::with_capacity(params, 2);

    graph
        .insert_first(NodeContext { node: 0, level: 0, sequence: 0 })
        .expect("insert node 0");
    graph
        .attach_node(NodeContext { node: 1, level: 0, sequence: 1 })
        .expect("attach node 1");

    // Phase 2: Nondeterministic population
    let should_link = kani::any::<bool>();
    if should_link {
        add_edge_if_missing(&mut graph, 0, 1, 0);

        // Phase 3: Exercise production reconciliation code
        let ctx = KaniUpdateContext::new(0, 0, max_connections);
        let added = ensure_reverse_edge_for_kani(&mut graph, ctx, 1);
        kani::assert(added, "expected reverse edge to be inserted");
    }

    // Phase 4: Assert the invariant
    kani::assert(
        is_bidirectional(&graph),
        "bidirectional invariant violated after reconciliation",
    );
}

// ---------------------------------------------------------------------------
// Harness: eviction and deferred scrub
// ---------------------------------------------------------------------------

#[cfg(kani)]
#[kani::proof]
#[kani::unwind(10)]
fn verify_eviction_deferred_scrub_reciprocity() {
    // Phase 1: Setup (4-node graph at level 1, max_connections = 1)
    let params = HnswParams::new(1, 2).expect("params must be valid");
    let max_connections = params.max_connections();
    let mut graph = setup_eviction_test_graph(params);

    // Phase 2: Seed node 1 at capacity
    add_edge_if_missing(&mut graph, 1, 2, 1);
    add_edge_if_missing(&mut graph, 2, 1, 1);

    // Phase 3: Drive production commit-path code
    let update_ctx = EdgeContext { level: 1, max_connections };
    let staged = StagedUpdate { node: 0, ctx: update_ctx, candidates: vec![1] };
    let updates: Vec<FinalisedUpdate> = vec![(staged, vec![1])];
    let new_node = NewNodeContext { id: 3, level: 1 };

    apply_commit_updates_for_kani(&mut graph, max_connections, new_node, updates)
        .expect("commit-path updates must succeed");

    // Phase 4: Assert invariants (both positive and negative)
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

// ---------------------------------------------------------------------------
// Harness: nondeterministic level assignment with entry-point promotion
// ---------------------------------------------------------------------------

#[cfg(kani)]
#[kani::proof]
#[kani::unwind(12)]
fn verify_entry_point_validity_4_nodes() {
    let params = HnswParams::new(2, 3).expect("params must be valid");
    let mut graph = Graph::with_capacity(params, 4);

    // First node: nondeterministic level with kani::assume precondition
    let level0: usize = kani::any();
    kani::assume(level0 <= 2);
    graph
        .insert_first(NodeContext { node: 0, level: level0, sequence: 0 })
        .expect("insert first");

    // Subsequent nodes: nondeterministic levels with promotion
    for (id, seq) in [(1usize, 1u64), (2, 2), (3, 3)] {
        let level: usize = kani::any();
        kani::assume(level <= 2);
        graph
            .attach_node(NodeContext { node: id, level, sequence: seq })
            .expect("attach node");
        graph.promote_entry(id, level);
    }

    kani::assert(
        is_entry_point_valid(&graph),
        "entry-point validity invariant violated",
    );
}

// ---------------------------------------------------------------------------
// Helper functions (gated behind #[cfg(kani)])
// ---------------------------------------------------------------------------

#[cfg(kani)]
fn setup_eviction_test_graph(params: HnswParams) -> Graph {
    let mut graph = Graph::with_capacity(params, 4);
    graph
        .insert_first(NodeContext { node: 0, level: 1, sequence: 0 })
        .expect("insert node 0");
    graph
        .attach_node(NodeContext { node: 1, level: 1, sequence: 1 })
        .expect("attach node 1");
    graph
        .attach_node(NodeContext { node: 2, level: 1, sequence: 2 })
        .expect("attach node 2");
    graph
        .attach_node(NodeContext { node: 3, level: 1, sequence: 3 })
        .expect("attach node 3");
    graph
}

#[cfg(kani)]
struct EdgeAssertion {
    source: usize,
    target: usize,
    level: usize,
}

#[cfg(kani)]
fn assert_node_link(graph: &Graph, edge: EdgeAssertion, message: &str) {
    let has_link = graph
        .node(edge.source)
        .map(|n| n.neighbours(edge.level).contains(&edge.target))
        .unwrap_or(false);
    kani::assert(has_link, message);
}

#[cfg(kani)]
fn assert_no_node_link(graph: &Graph, edge: EdgeAssertion, message: &str) {
    let has_link = graph
        .node(edge.source)
        .map(|n| n.neighbours(edge.level).contains(&edge.target))
        .unwrap_or(false);
    kani::assert(!has_link, message);
}

fn add_bidirectional_edge(graph: &mut Graph, origin: usize, target: usize, level: usize) {
    add_edge_if_missing(graph, origin, target, level);
    add_edge_if_missing(graph, target, origin, level);
}

fn push_if_absent(list: &mut Vec<usize>, value: usize) {
    if !list.contains(&value) {
        list.push(value);
    }
}
