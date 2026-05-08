// Reference: Verus proof structure from chutoro
//
// This file demonstrates the proof structure, spec type patterns, and lemma
// composition approach used in a production Rust codebase (HNSW edge harvest
// primitives). It is included for reference, not compilation by rustc.
//
// Run with: verus verus/edge_harvest_proofs.rs

// ---------------------------------------------------------------------------
// Project layout
// ---------------------------------------------------------------------------
//
// project/
// ├── verus/
// │   ├── edge_harvest_proofs.rs      # Root: types, specs, top-level lemmas
// │   ├── edge_harvest_extract.rs     # Extraction invariant proofs
// │   └── edge_harvest_ordering.rs    # Ordering property proofs
// ├── scripts/
// │   ├── install-verus.sh
// │   └── run-verus.sh
// └── tools/
//     └── verus/
//         ├── VERSION                 # e.g., 0.2026.01.30.44ebdee
//         └── SHA256SUMS

// ---------------------------------------------------------------------------
// Root proof file: types, specifications, and top-level lemmas
// ---------------------------------------------------------------------------

use vstd::prelude::*;
use vstd::relations::sorted_by;
use vstd::seq_lib::*;

mod edge_harvest_extract;
mod edge_harvest_ordering;

fn main() {}

verus! {

// -- Spec type aliases (mirror production types) ----------------------------

/// Identifier for a node in the HNSW graph.
pub type NodeId = nat;
/// Monotonic insertion sequence number for candidate edges.
pub type Sequence = nat;
/// Distance metric value used for ordering edges.
pub type Distance = int;

// -- Spec structs (mirror production structs) --------------------------------

pub struct NeighbourSpec {
    pub id: NodeId,
    pub distance: Distance,
}

pub struct LayerPlanSpec {
    pub neighbours: Seq<NeighbourSpec>,
}

pub struct InsertionPlanSpec {
    pub layers: Seq<LayerPlanSpec>,
}

pub struct CandidateEdgeSpec {
    pub source: NodeId,
    pub target: NodeId,
    pub distance: Distance,
    pub sequence: Sequence,
}

// -- Spec functions (pure specifications) ------------------------------------

impl CandidateEdgeSpec {
    /// Returns a canonical edge with ordered endpoints.
    pub open spec fn canonicalise(self) -> Self {
        if self.source <= self.target {
            self
        } else {
            CandidateEdgeSpec {
                source: self.target,
                target: self.source,
                distance: self.distance,
                sequence: self.sequence,
            }
        }
    }
}

/// Total ordering on edges: distance, then source, target, sequence.
pub open spec fn edge_ord_leq(a: CandidateEdgeSpec, b: CandidateEdgeSpec) -> bool {
    if a.distance < b.distance { true }
    else if a.distance > b.distance { false }
    else if a.source < b.source { true }
    else if a.source > b.source { false }
    else if a.target < b.target { true }
    else if a.target > b.target { false }
    else { a.sequence <= b.sequence }
}

/// Counts non-self neighbours (recursive, with decreases clause).
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

// -- Invariant specifications ------------------------------------------------

/// Shared invariants: correct length, all edges have expected source,
/// no self-edges, correct sequence number.
pub open spec fn edges_common_invariants(
    edges: Seq<CandidateEdgeSpec>,
    expected_len: nat,
    source_node: NodeId,
    source_sequence: Sequence,
) -> bool {
    // Note the use of #![auto] for trigger selection:
    &&& edges.len() == expected_len
    &&& forall|i: int| #![auto] 0 <= i < edges.len() ==> edges[i].source == source_node
    &&& forall|i: int| #![auto] 0 <= i < edges.len() ==> edges[i].target != source_node
    &&& forall|i: int| #![auto] 0 <= i < edges.len() ==> edges[i].sequence == source_sequence
}

// -- Top-level proof (composes sub-lemmas) -----------------------------------

/// Proves that sorting edges by edge_leq preserves the multiset and produces
/// a sorted sequence.
proof fn lemma_edge_harvest_from_unsorted_invariants(edges: Seq<CandidateEdgeSpec>)
    ensures
        edge_harvest_invariants(edges),
{
    // Compose: first prove total ordering, then invoke sort lemma.
    edge_harvest_ordering::lemma_edge_leq_total_ordering();
    edges.lemma_sort_by_ensures(|a: CandidateEdgeSpec, b: CandidateEdgeSpec| edge_leq(a, b));
}

} // verus!

// ---------------------------------------------------------------------------
// Sub-proof file: extraction invariants (edge_harvest_extract.rs)
// ---------------------------------------------------------------------------
//
// Key patterns demonstrated:
// - Inductive proof over Seq (base case + recursive step)
// - Helper lemma for prepend-preserves-invariants
// - Helper lemma for concat-preserves-invariants
// - broadcast use group_seq_axioms for sequence axioms
//
// verus! {
// use super::*;
//
// proof fn lemma_prepend_first_edge_preserves_common_invariants(
//     first_edge: CandidateEdgeSpec,
//     rest_edges: Seq<CandidateEdgeSpec>,
//     rest_expected: nat,
//     source_node: NodeId,
//     source_sequence: Sequence,
// )
//     requires
//         edges_common_invariants(rest_edges, rest_expected, source_node, source_sequence),
//         first_edge.source == source_node,
//         first_edge.target != source_node,
//         first_edge.sequence == source_sequence,
//     ensures
//         edges_common_invariants(
//             Seq::<CandidateEdgeSpec>::empty().push(first_edge).add(rest_edges),
//             1 + rest_expected,
//             source_node,
//             source_sequence,
//         ),
// {
//     broadcast use vstd::seq::group_seq_axioms;
//
//     let prefix = Seq::<CandidateEdgeSpec>::empty().push(first_edge);
//     let edges = prefix.add(rest_edges);
//
//     // Prove each conjunct separately with explicit index reasoning:
//     assert forall|i: int| #![auto] 0 <= i < edges.len()
//         implies edges[i].source == source_node
//     by {
//         if i == 0 {
//             assert(edges[i] == prefix[i]);
//         } else {
//             let j = i - 1;
//             assert(edges[i] == rest_edges[j]);
//         }
//     }
//     // (Similar blocks for .target and .sequence)
// }
// } // verus!

// ---------------------------------------------------------------------------
// Sub-proof file: ordering properties (edge_harvest_ordering.rs)
// ---------------------------------------------------------------------------
//
// Key patterns demonstrated:
// - Proving reflexivity, antisymmetry, transitivity, strong connectedness
// - Composing into total_ordering via reveal()
// - Case-split proof structure matching the function's if-else chain
//
// verus! {
// use super::*;
//
// proof fn lemma_edge_ord_leq_total_ordering()
//     ensures
//         total_ordering(|a: CandidateEdgeSpec, b: CandidateEdgeSpec| edge_ord_leq(a, b)),
// {
//     reveal(total_ordering);  // Must reveal opaque vstd definition
//     lemma_edge_ord_leq_reflexive();
//     lemma_edge_ord_leq_antisymmetric();
//     lemma_edge_ord_leq_transitive();
//     lemma_edge_ord_leq_strongly_connected();
// }
// } // verus!
