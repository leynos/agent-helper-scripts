"""Check the assessment guards where they control the shipped workflow.

`skills/pr-babysitting/references/execplan-assessment.md` and the parent skill
state the readiness, request and publication obligations. The examples module
applies this contract to the shipped text and to every mutated copy; this
module holds the assertions so that the issue-specific checks can be added
without growing the examples module past its code-health budget.
"""

from __future__ import annotations

from assessment_mutation_cases import (
    COMPLETENESS_HEADING,
    COMPLETENESS_REQUEST_FIELDS,
    PROOF_CONDITIONAL_ECHO_FIELD,
    PROOF_HEADING,
    PROOF_REQUEST_FIELDS,
)
from pr_babysitting_issue_contract import issue_assessment_contract
from skill_contract_support import fenced_request, section

LEDGER_REQUIREMENTS = (
    "A verdict of `clear`, `not clear`, or `pending`, with a justified `not applicable` for an assessment that does not apply",
    "on the same entry as the base/head and the plan revision it was given for",
    "The completeness assessment's subject is recorded as either the whole plan or the declared subset; only the whole approved plan clears the gate, and a declared-subset verdict is evidence for its actual scope only.",
    "The proof assessment's subject is the named proofs it covers.",
    "When the completeness assessment applies, a clear whole-plan completeness verdict covering the accepted base/head and recorded against the currently approved plan revision satisfies [the readiness gate](references/execplan-assessment.md#readiness-and-later-changes).",
    "A managed-stack layer that implements only its own milestones therefore stays in draft until a whole-plan verdict covers its candidate; the record of its subset is evidence, not a readiness waiver.",
    "An ExecPlan-bound verdict recorded against a superseded plan revision does not carry over, even when the base/head is unchanged.",
    "The original-issue assessment is bound to the base/head only and names no plan revision, so a plan-revision change does not renew it while a changed base/head does.",
    "When the proof assessment applies, readiness also requires its clear verdict for the same base/head; a clear completeness verdict alone does not satisfy the gate.",
    "reconcile the revision the substantive reply echoes against the revision in force",
    "a proof assessment under an ExecPlan",
    "without an ExecPlan, the base/head is the whole candidate and there is no revision to reconcile",
)


def assessment_contract(assessment: str, skill: str) -> None:
    """Check obligations where they control readiness, requests, and publication."""
    applicability = section(assessment, "Applicability and ownership")
    assert "Apply the proof assessment whenever implementation introduces or materially changes a proof" in applicability, "proof applicability must remain in ownership section"
    assert "require passing applicable deterministic correctness and quality gates" in applicability, "request prerequisites must require passing gates"
    assert "for the published candidate" in applicability, "gates must bind to published candidate"
    assert "Verify remote parity" in applicability, "request prerequisites must verify publication"
    completeness = section(assessment, "ExecPlan completeness and correctness")
    assert "Known limitations: <evidential limits only: checks not run, inspection not possible, proof bounds; not unimplemented plan milestones>." in completeness, "completeness request must restrict limitations to evidential limits"
    assert "checks not run" in completeness, "evidential limitation kind must remain named: checks not run"
    assert "inspection not possible" in completeness, "evidential limitation kind must remain named: inspection not possible"
    assert "not unimplemented plan milestones" in completeness, "completeness request must exclude unimplemented milestones"
    assert "An unimplemented plan milestone is in-scope work, not a limitation, per [applicability and ownership](#applicability-and-ownership)." in completeness, "completeness section must bind milestones to the ownership rule"
    assert "a reply that echoes only the base/head cannot bind its verdict to an approved revision" in completeness, "completeness section must state why base/head alone cannot bind a verdict"
    assert "The `Assessed subject:` line is always the whole approved plan, and no other subject clears the gate." in completeness, "completeness section must state that only the whole plan clears"
    assert "A managed-stack layer may record a declared-subset verdict as evidence for that layer's actual scope only" in completeness, "completeness section must keep subset verdicts as evidence only"
    assert "The whole-plan verdict remains required before any layer's transition" in completeness, "completeness section must require a whole-plan verdict for every transition"
    request = fenced_request(assessment, COMPLETENESS_HEADING)
    for field, expected_message in COMPLETENESS_REQUEST_FIELDS:
        assert field in request, expected_message
    proofs = section(assessment, PROOF_HEADING)
    assert "a proof-only assignment with no ExecPlan keeps the base/head as its whole candidate and asks for no revision echo" in proofs, "proof section must preserve the no-plan case"
    proof_request = fenced_request(assessment, PROOF_HEADING)
    for field, expected_message in PROOF_REQUEST_FIELDS:
        assert field in proof_request, expected_message
    assert PROOF_CONDITIONAL_ECHO_FIELD in proof_request, (
        "proof echo must stay conditional on an ExecPlan"
    )
    routing = section(assessment, "Comment routing")
    assert "Assessments are conversations through tagged issue comments, not formal CodeRabbit reviews" in routing, "assessments must remain distinct from formal reviews"
    assert "assigned token procedure" in routing, "initial comments must use assigned token route"
    assert "`shuf`" in routing, "initial comments must shuffle the assigned token"
    assert "Assessment conversations never go through `comenq`" in routing, "assessment follow-ups must not enter the review queue"
    ledger = section(skill, "1. Establish the candidate and keep a delivery ledger")
    for requirement in LEDGER_REQUIREMENTS:
        assert requirement in ledger, f"ledger section must state: {requirement}"
    readiness = section(assessment, "Readiness and later changes")
    assert "Every applicable assessment must clear for the accepted candidate before its draft-to-ready transition" in readiness, "applicable assessments must precede readiness"
    assert "An already-ready PR stays ready; obtain missing assessments before merge" in readiness, "missing assessment must block merge without redrafting"
    assert "a verdict recorded against a revision that has since been superseded by a newly approved revision does not clear the gate, even when the base/head is unchanged" in readiness, "readiness section must compare the currently approved plan revision"
    assert "Reconcile the revision a reply echoes with the revision in force" in readiness, "readiness section must reconcile the echoed plan revision"
    assert "There is no subset or plateau waiver" in readiness, "stack path must state that no subset waiver exists"
    assert "stays in draft until a clear whole-plan verdict covers its candidate" in readiness, "a lower layer must wait for the whole-plan verdict"
    assert "naming the layer's milestones, the `github-stacks` parent it builds on and the milestones remaining above it" in readiness, "subset evidence must record the layer, parent and remainder"
    assert "the record never clears the gate" in readiness, "subset evidence must not clear the gate"
    assert "the stack does not count as delivered until the layer that carries the plan's remaining milestones obtains the whole-plan verdict" in readiness, "final layer must still obtain a whole-plan verdict"
    assert "A single PR that claims the whole plan but delivers part of it never qualifies either" in readiness, "single-PR partial delivery must stay blocked"
    assert "That leaves a stack cut from one undivided plan with no delivery path" in readiness, "stack deadlock must be named"
    assert "Split the approved plan into independently complete units, one per layer" in readiness, "stack delivery path must give each layer its own complete plan"
    assert "or deliver the undivided plan in a single PR" in readiness, "stack delivery path must retain the single-PR alternative"
    assert "restructure the plan before approval rather than discovering the" in readiness, "stack delivery path must be resolved at approval, not by waiver"
    assert "Do not set the PR back to draft" in readiness, "redrafting prohibition must remain in readiness section"
    parent_ready = section(skill, "5. Assess applicable delivery gates, then mark green drafts ready")
    assert "all applicable pre-readiness assessments hold" in parent_ready, "parent readiness condition must include assessments"
    assert "An already-ready PR remains ready while missing or invalidated assessments block merge" in parent_ready, "parent must preserve ready state and merge blocker"
    merge = section(skill, "10. End cosmetic review churn, then squash-merge safely")
    assert "assessments cover the accepted candidate, with no unresolved substantive concern" in merge, "merge checklist must require candidate-bound assessments"
    issue_assessment_contract(assessment, skill)