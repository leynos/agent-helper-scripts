"""Mutation controls for the ExecPlan assessment contract.

The table is data rather than test logic: each row names the document it
mutates, the clause to find, its replacement, whether to relocate rather than
delete the clause, and the assertion the mutation must provoke. Keeping it
beside the shared helpers leaves the test module to the tests themselves.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest


LIMITATIONS_GUARD = "completeness request must restrict limitations to evidential limits"
MILESTONE_OWNERSHIP = "completeness section must bind milestones to the ownership rule"
LEDGER_VERDICT = "ledger section must state: A verdict of `clear`"
LEDGER_CANDIDATE = "ledger section must state: on the same entry"
LEDGER_SUBJECT = "ledger section must state: The completeness assessment's subject"
LEDGER_CLEARING = "ledger section must state: When the completeness assessment applies"
LEDGER_STACK_PATH = "ledger section must state: A managed-stack layer that implements only its own milestones"
LEDGER_STALE_REVISION = "ledger section must state: A verdict recorded against a superseded plan revision"
LEDGER_PROOF_READINESS = "ledger section must state: When the proof assessment applies"
READINESS_STALE_REVISION = "readiness section must compare the currently approved plan revision"
REQUEST_REVISION = "completeness request must identify the assessed plan revision"
ECHOED_REVISION = "completeness request must require the reply to echo the plan revision"
BASE_HEAD_LIMIT = "completeness section must state why base/head alone cannot bind a verdict"
READINESS_REVISION_RECONCILIATION = "readiness section must reconcile the echoed plan revision"
LEDGER_ECHO_REVISION = "ledger section must state: reconcile the revision the substantive reply echoes"
LEDGER_PROOF_REVISION = "ledger section must state: a proof request under an ExecPlan must also name and echo the revision"
LEDGER_NO_PLAN = "ledger section must state: without an ExecPlan, the base/head is the whole candidate"
PROOF_REVISION = "proof request must name the plan revision when an ExecPlan applies"
PROOF_ECHO_REVISION = "proof request must require the reply to echo the plan revision"
PROOF_CONDITIONAL_ECHO = "proof echo must stay conditional on an ExecPlan"
PROOF_NO_PLAN_CASE = "proof section must preserve the no-plan case"
STACK_NO_WAIVER = "stack path must state that no subset waiver exists"
STACK_EVIDENCE = "subset evidence must record the layer, parent and remainder"
STACK_LAYER_SCOPE = "subset evidence must not clear the gate"
STACK_FINAL_WHOLE_PLAN = "final layer must still obtain a whole-plan verdict"
STACK_SINGLE_PR = "single-PR partial delivery must stay blocked"
STACK_DEADLOCK_NAMED = "stack deadlock must be named"
STACK_DELIVERY_PATH = "stack delivery path must give each layer its own complete plan"
STACK_SINGLE_PR_ALTERNATIVE = "stack delivery path must retain the single-PR alternative"
STACK_APPROVAL_TIME = "stack delivery path must be resolved at approval, not by waiver"
REQUEST_SUBJECT = "completeness request must bound the assessed subject"
REQUEST_SUBJECT_WHOLE_PLAN = "completeness section must state that only the whole plan clears"
REQUEST_SUBSET_EVIDENCE = "completeness section must keep subset verdicts as evidence only"
HANDOFF_PACKET_EXCEPTION = (
    "completeness packet must not grant a declared-subset waiver"
)
HANDOFF_SUBSET_EVIDENCE = "handoff must keep a subset verdict as evidence only"
HANDOFF_DEFERS = (
    "handoff must defer the stack's clearing conditions to pr-babysitting"
    " instead of restating them"
)

COMPLETENESS_HEADING = "ExecPlan completeness and correctness"
PROOF_HEADING = "Proof inventory and specific scrutiny"

LIMITATIONS_FIELD = (
    "Known limitations: <evidential limits only: checks not run, inspection not"
    " possible, proof bounds; not unimplemented plan milestones>."
)
REQUEST_REVISION_FIELD = (
    "Plan revision: <approved revision identifier and the plan file's blob SHA"
    " at this head>."
)
REQUEST_SUBJECT_FIELD = "Assessed subject: <the whole approved plan>."
COMPLETENESS_ECHO_FIELD = (
    "Please echo the Assessment-ID, assessed base/head, and plan revision in"
    " your substantive reply."
)
PROOF_REVISION_FIELD = (
    "Plan revision: <approved revision identifier and the plan file's blob SHA"
    " at this head; omit when no ExecPlan applies>."
)
PROOF_ECHO_PREFIX_FIELD = (
    "Please echo the Assessment-ID, assessed base/head, and plan revision in"
    " your substantive reply"
)
PROOF_ECHO_FIELD = (
    PROOF_ECHO_PREFIX_FIELD
    + "; echo the plan revision only when this request names one."
)
PROOF_CONDITIONAL_ECHO_FIELD = (
    "echo the plan revision only when this request names one."
)

COMPLETENESS_REQUEST_FIELDS = (
    (LIMITATIONS_FIELD, LIMITATIONS_GUARD),
    (REQUEST_REVISION_FIELD, REQUEST_REVISION),
    (REQUEST_SUBJECT_FIELD, REQUEST_SUBJECT),
    (COMPLETENESS_ECHO_FIELD, ECHOED_REVISION),
)
PROOF_REQUEST_FIELDS = (
    (PROOF_REVISION_FIELD, PROOF_REVISION),
    (PROOF_ECHO_PREFIX_FIELD, PROOF_ECHO_REVISION),
)

REQUEST_FENCE_MUTATIONS = (
    pytest.param(
        COMPLETENESS_HEADING,
        LIMITATIONS_FIELD,
        LIMITATIONS_GUARD,
        id="moved-limitations-field-to-section-prose",
    ),
    pytest.param(
        COMPLETENESS_HEADING,
        REQUEST_SUBJECT_FIELD,
        REQUEST_SUBJECT,
        id="moved-request-subject-to-section-prose",
    ),
    pytest.param(
        COMPLETENESS_HEADING,
        REQUEST_REVISION_FIELD,
        REQUEST_REVISION,
        id="moved-request-plan-revision-to-section-prose",
    ),
    pytest.param(
        COMPLETENESS_HEADING,
        COMPLETENESS_ECHO_FIELD,
        ECHOED_REVISION,
        id="moved-request-echo-to-section-prose",
    ),
    pytest.param(
        PROOF_HEADING,
        PROOF_REVISION_FIELD,
        PROOF_REVISION,
        id="moved-proof-plan-revision-to-section-prose",
    ),
    pytest.param(
        PROOF_HEADING,
        PROOF_ECHO_FIELD,
        PROOF_ECHO_REVISION,
        id="moved-proof-echo-to-section-prose",
    ),
)

@dataclass(frozen=True)
class Mutation:
    """One row of the assessment mutation table.

    The row is a single parameterized value rather than five, so the contract
    test that unpacks it stays within the repository's argument limit and each
    field is still named at the point of use.
    """

    document: str
    old: str
    new: str
    expected: str
    move: bool = False
    ident: str = ""


ASSESSMENT_MUTATIONS = (
    Mutation("assessment", "Both applicable assessments must clear",
             "Both applicable assessments need not clear",
             "applicable assessments must precede readiness",
             ident="inverted-readiness"),
    Mutation("assessment",
             "An already-ready PR stays ready; obtain missing assessments before merge.",
             "", "missing assessment must block merge",
             ident="removed-ready-preservation"),
    Mutation("assessment", "for the published candidate.",
             "for any old candidate.", "gates must bind to published candidate",
             ident="stale-publication"),
    Mutation("assessment",
             "Assessment conversations never go through `comenq`.",
             "Assessment conversations always go through `comenq`.",
             "assessment follow-ups must not enter the review queue",
             ident="queued-assessment"),
    Mutation("assessment",
             "Both applicable assessments must clear for the accepted candidate before its draft-to-ready transition.",
             "", "applicable assessments must precede readiness", move=True,
             ident="moved-readiness"),
    Mutation("skill", "all applicable pre-readiness assessments hold",
             "no assessments hold",
             "parent readiness condition must include assessments",
             ident="parent-waiver"),
    Mutation("skill",
             "An already-ready PR remains ready while missing or invalidated assessments block merge.",
             "", "parent must preserve ready state and merge blocker",
             move=True, ident="moved-parent-preservation"),
    Mutation("skill",
             "7. Applicable ExecPlan completeness/correctness and proof-specific assessments cover the accepted candidate, with no unresolved substantive concern.",
             "", "merge checklist must require candidate-bound assessments",
             move=True, ident="moved-merge-guard"),
    Mutation("assessment",
             "Known limitations: <evidential limits only: checks not run, inspection not possible, proof bounds; not unimplemented plan milestones>.",
             "", LIMITATIONS_GUARD, ident="removed-limitations-guard"),
    Mutation("assessment", "not unimplemented plan milestones",
             "including unimplemented plan milestones", LIMITATIONS_GUARD,
             ident="inverted-limitations-guard"),
    Mutation("assessment",
             "An unimplemented plan milestone is in-scope work, not a limitation, per [applicability and ownership](#applicability-and-ownership).",
             "", MILESTONE_OWNERSHIP, move=True,
             ident="moved-milestone-ownership"),
    Mutation("skill",
             "A verdict of `clear`, `not clear`, or `pending`, with a justified `not applicable` for an assessment that does not apply",
             "a verdict of `posted` or `answered`", LEDGER_VERDICT,
             ident="ledger-drops-verdict"),
    Mutation("skill",
             "When the completeness assessment applies, a clear whole-plan completeness verdict covering the accepted base/head and recorded against the currently approved plan revision satisfies [the readiness gate](references/execplan-assessment.md#readiness-and-later-changes).",
             "", LEDGER_CLEARING, move=True,
             ident="moved-ledger-readiness-pointer"),
    Mutation("skill",
             "on the same entry as the base/head and the plan revision it was given for;",
             "", LEDGER_CANDIDATE, ident="unbound-ledger-verdict"),
    Mutation("skill",
             "The completeness assessment's subject is recorded as either the whole plan or the declared subset; only the whole approved plan clears the gate, and a declared-subset verdict is evidence for its actual scope only.",
             "Every assessment's subject is the whole plan.", LEDGER_SUBJECT,
             ident="proof-subject-collapsed-to-whole-plan"),
    Mutation("skill",
             "only the whole approved plan clears the gate, and a declared-subset verdict is evidence for its actual scope only",
             "a declared-subset verdict clears the gate", LEDGER_SUBJECT,
             ident="declared-subset-may-clear-ledger"),
    Mutation("skill",
             "A verdict recorded against a superseded plan revision does not carry over, even when the base/head is unchanged.",
             "", LEDGER_STALE_REVISION,
             ident="ledger-accepts-superseded-plan-revision"),
    Mutation("assessment",
             "a verdict recorded against a revision that has since been superseded by a newly approved revision does not clear the gate, even when the base/head is unchanged.",
             "", READINESS_STALE_REVISION,
             ident="readiness-accepts-superseded-plan-revision"),
    Mutation("skill",
             "When the proof assessment applies, readiness also requires its clear verdict for the same base/head; a clear completeness verdict alone does not satisfy the gate.",
             "A clear completeness verdict alone satisfies the readiness gate, whatever the proof verdict.",
             LEDGER_PROOF_READINESS, ident="completeness-alone-may-clear"),
    Mutation("skill",
             "When the completeness assessment applies, a clear whole-plan completeness verdict covering the accepted base/head",
             "When the completeness assessment applies, a clear declared-subset completeness verdict covering the accepted base/head",
             LEDGER_CLEARING, ident="declared-subset-may-clear"),
    Mutation("skill",
             "and recorded against the currently approved plan revision satisfies",
             "and satisfies", LEDGER_CLEARING, ident="unbound-plan-revision"),
    Mutation("skill",
             "A managed-stack layer that implements only its own milestones therefore stays in draft until a whole-plan verdict covers its candidate",
             "A managed-stack layer that implements only its own milestones may leave draft without a whole-plan verdict",
             LEDGER_STACK_PATH,
             ident="stack-layer-exempted-from-whole-plan"),
    Mutation("skill",
             "the record of its subset is evidence, not a readiness waiver.",
             "", LEDGER_STACK_PATH, ident="ledger-stack-path-unbound"),
    Mutation("assessment",
             "Plan revision: <approved revision identifier and the plan file's blob SHA at this head>.",
             "", REQUEST_REVISION, ident="request-omits-plan-revision"),
    Mutation("assessment",
             "Please echo the Assessment-ID, assessed base/head, and plan revision in your substantive reply.",
             "Please echo the Assessment-ID and assessed base/head in your substantive reply.",
             ECHOED_REVISION, ident="reply-echo-drops-plan-revision"),
    Mutation("assessment",
             "a reply that echoes only the base/head cannot bind its verdict to an approved revision.",
             "", BASE_HEAD_LIMIT, move=True, ident="moved-base-head-limit"),
    Mutation("assessment",
             "Reconcile the revision a reply echoes with the revision in force;",
             "", READINESS_REVISION_RECONCILIATION,
             ident="readiness-skips-echo-reconciliation"),
    Mutation("skill",
             "reconcile the revision the substantive reply echoes against the revision in force",
             "accept any reply that echoes the base/head", LEDGER_ECHO_REVISION,
             ident="ledger-binds-verdict-to-base-head-only"),
    Mutation("assessment",
             "Plan revision: <approved revision identifier and the plan file's blob SHA at this head; omit when no ExecPlan applies>.",
             "", PROOF_REVISION, ident="proof-request-omits-plan-revision"),
    Mutation("assessment",
             "Please echo the Assessment-ID, assessed base/head, and plan revision in your substantive reply; echo the plan revision only when this request names one.",
             "Please echo the Assessment-ID and assessed base/head in your substantive reply.",
             PROOF_ECHO_REVISION, ident="proof-reply-echo-drops-plan-revision"),
    Mutation("assessment",
             "echo the plan revision only when this request names one.",
             "echo the plan revision in every reply.", PROOF_CONDITIONAL_ECHO,
             ident="proof-echo-unconditional"),
    Mutation("assessment",
             "a proof-only assignment with no ExecPlan keeps the base/head as its whole candidate and asks for no revision echo.",
             "", PROOF_NO_PLAN_CASE, move=True,
             ident="moved-proof-no-plan-case"),
    Mutation("skill",
             "so a proof request under an ExecPlan must also name and echo the revision;",
             "", LEDGER_PROOF_REVISION,
             ident="ledger-proof-request-omits-revision"),
    Mutation("skill",
             "without an ExecPlan, the base/head is the whole candidate and there is no revision to reconcile.",
             "", LEDGER_NO_PLAN, ident="ledger-loses-no-plan-case"),
    Mutation("assessment", "There is no subset or plateau waiver:",
             "A declared subset is sufficient for a lower layer:",
             STACK_NO_WAIVER, ident="stack-path-admits-subset-waiver"),
    Mutation("assessment",
             "naming the layer's milestones, the `github-stacks` parent it builds on and the milestones remaining above it",
             "", STACK_EVIDENCE, ident="subset-evidence-unbound"),
    Mutation("assessment", "the record never clears the gate.",
             "the record clears the gate.", STACK_LAYER_SCOPE,
             ident="subset-evidence-clears-gate"),
    Mutation("assessment",
             "the stack does not count as delivered until the layer that carries the plan's remaining milestones obtains the whole-plan verdict",
             "the stack counts as delivered on each layer's subset verdict",
             STACK_FINAL_WHOLE_PLAN, ident="stack-drops-final-whole-plan"),
    Mutation("assessment",
             "A single PR that claims the whole plan but delivers part of it never qualifies either",
             "", STACK_SINGLE_PR, ident="stack-path-admits-single-partial-pr"),
    Mutation("assessment",
             "That leaves a stack cut from one undivided plan with no delivery path:",
             "", STACK_DEADLOCK_NAMED, ident="stack-deadlock-hidden"),
    Mutation("assessment",
             "Split the approved plan into independently complete units, one per layer",
             "Let the readiness gate waive the whole-plan verdict for a lower layer",
             STACK_DELIVERY_PATH, ident="stack-delivery-path-waives-rule"),
    Mutation("assessment", "or deliver the undivided plan in a single PR.",
             "", STACK_SINGLE_PR_ALTERNATIVE, ident="stack-drops-single-pr-option"),
    Mutation("assessment",
             "restructure the plan before approval rather than discovering the",
             "restructure the plan when readiness blocks and waive the rule if it",
             STACK_APPROVAL_TIME, ident="stack-deadlock-left-to-readiness"),
    Mutation("assessment", REQUEST_SUBJECT_FIELD, "", REQUEST_SUBJECT,
             ident="request-omits-assessed-subject"),
    Mutation("assessment",
             "The `Assessed subject:` line is always the whole approved plan, and no other subject clears the gate.",
             "The `Assessed subject:` line may name a subset instead of the whole approved plan.",
             REQUEST_SUBJECT_WHOLE_PLAN, ident="request-subject-admits-subset"),
    Mutation("assessment",
             "A managed-stack layer may record a declared-subset verdict as evidence for that layer's actual scope only",
             "", REQUEST_SUBSET_EVIDENCE, move=True,
             ident="moved-subset-evidence-rule"),
)
