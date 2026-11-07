"""Mutation controls for the ExecPlan assessment contract.

The table is data rather than test logic: each row names the document it
mutates, the clause to find, its replacement, whether to relocate rather than
delete the clause, and the assertion the mutation must provoke. Keeping it
beside the shared helpers leaves the test module to the tests themselves.
"""

from __future__ import annotations

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

ASSESSMENT_MUTATIONS = (
    pytest.param(
        "assessment",
        "Both applicable assessments must clear",
        "Both applicable assessments need not clear",
        False,
        "applicable assessments must precede readiness",
        id="inverted-readiness",
    ),
    pytest.param(
        "assessment",
        "An already-ready PR stays ready; obtain missing assessments before merge.",
        "",
        False,
        "missing assessment must block merge",
        id="removed-ready-preservation",
    ),
    pytest.param(
        "assessment",
        "for the published candidate.",
        "for any old candidate.",
        False,
        "gates must bind to published candidate",
        id="stale-publication",
    ),
    pytest.param(
        "assessment",
        "Assessment conversations never go through `comenq`.",
        "Assessment conversations always go through `comenq`.",
        False,
        "assessment follow-ups must not enter the review queue",
        id="queued-assessment",
    ),
    pytest.param(
        "assessment",
        "Both applicable assessments must clear for the accepted candidate before its draft-to-ready transition.",
        "",
        True,
        "applicable assessments must precede readiness",
        id="moved-readiness",
    ),
    pytest.param(
        "skill",
        "all applicable pre-readiness assessments hold",
        "no assessments hold",
        False,
        "parent readiness condition must include assessments",
        id="parent-waiver",
    ),
    pytest.param(
        "skill",
        "An already-ready PR remains ready while missing or invalidated assessments block merge.",
        "",
        True,
        "parent must preserve ready state and merge blocker",
        id="moved-parent-preservation",
    ),
    pytest.param(
        "skill",
        "7. Applicable ExecPlan completeness/correctness and proof-specific assessments cover the accepted candidate, with no unresolved substantive concern.",
        "",
        True,
        "merge checklist must require candidate-bound assessments",
        id="moved-merge-guard",
    ),
    pytest.param(
        "assessment",
        "Known limitations: <evidential limits only: checks not run, inspection not possible, proof bounds; not unimplemented plan milestones>.",
        "",
        False,
        LIMITATIONS_GUARD,
        id="removed-limitations-guard",
    ),
    pytest.param(
        "assessment",
        "not unimplemented plan milestones",
        "including unimplemented plan milestones",
        False,
        LIMITATIONS_GUARD,
        id="inverted-limitations-guard",
    ),
    pytest.param(
        "assessment",
        "An unimplemented plan milestone is in-scope work, not a limitation, per [applicability and ownership](#applicability-and-ownership).",
        "",
        True,
        MILESTONE_OWNERSHIP,
        id="moved-milestone-ownership",
    ),
    pytest.param(
        "skill",
        "A verdict of `clear`, `not clear`, or `pending`, with a justified `not applicable` for an assessment that does not apply",
        "a verdict of `posted` or `answered`",
        False,
        LEDGER_VERDICT,
        id="ledger-drops-verdict",
    ),
    pytest.param(
        "skill",
        "When the completeness assessment applies, a clear whole-plan completeness verdict covering the accepted base/head and recorded against the currently approved plan revision satisfies [the readiness gate](references/execplan-assessment.md#readiness-and-later-changes).",
        "",
        True,
        LEDGER_CLEARING,
        id="moved-ledger-readiness-pointer",
    ),
    pytest.param(
        "skill",
        "on the same entry as the base/head and the plan revision it was given for;",
        "",
        False,
        LEDGER_CANDIDATE,
        id="unbound-ledger-verdict",
    ),
    pytest.param(
        "skill",
        "The completeness assessment's subject is recorded as either the whole plan or the declared subset; only the whole approved plan clears the gate, and a declared-subset verdict is evidence for its actual scope only.",
        "Every assessment's subject is the whole plan.",
        False,
        LEDGER_SUBJECT,
        id="proof-subject-collapsed-to-whole-plan",
    ),
    pytest.param(
        "skill",
        "only the whole approved plan clears the gate, and a declared-subset verdict is evidence for its actual scope only",
        "a declared-subset verdict clears the gate",
        False,
        LEDGER_SUBJECT,
        id="declared-subset-may-clear-ledger",
    ),
    pytest.param(
        "skill",
        "A verdict recorded against a superseded plan revision does not carry over, even when the base/head is unchanged.",
        "",
        False,
        LEDGER_STALE_REVISION,
        id="ledger-accepts-superseded-plan-revision",
    ),
    pytest.param(
        "assessment",
        "a verdict recorded against a revision that has since been superseded by a newly approved revision does not clear the gate, even when the base/head is unchanged.",
        "",
        False,
        READINESS_STALE_REVISION,
        id="readiness-accepts-superseded-plan-revision",
    ),
    pytest.param(
        "skill",
        "When the proof assessment applies, readiness also requires its clear verdict for the same base/head; a clear completeness verdict alone does not satisfy the gate.",
        "A clear completeness verdict alone satisfies the readiness gate, whatever the proof verdict.",
        False,
        LEDGER_PROOF_READINESS,
        id="completeness-alone-may-clear",
    ),
    pytest.param(
        "skill",
        "When the completeness assessment applies, a clear whole-plan completeness verdict covering the accepted base/head",
        "When the completeness assessment applies, a clear declared-subset completeness verdict covering the accepted base/head",
        False,
        LEDGER_CLEARING,
        id="declared-subset-may-clear",
    ),
    pytest.param(
        "skill",
        "and recorded against the currently approved plan revision satisfies",
        "and satisfies",
        False,
        LEDGER_CLEARING,
        id="unbound-plan-revision",
    ),
    pytest.param(
        "skill",
        "A managed-stack layer that implements only its own milestones therefore stays in draft until a whole-plan verdict covers its candidate",
        "A managed-stack layer that implements only its own milestones may leave draft without a whole-plan verdict",
        False,
        LEDGER_STACK_PATH,
        id="stack-layer-exempted-from-whole-plan",
    ),
    pytest.param(
        "skill",
        "the record of its subset is evidence, not a readiness waiver.",
        "",
        False,
        LEDGER_STACK_PATH,
        id="ledger-stack-path-unbound",
    ),
    pytest.param(
        "assessment",
        "Plan revision: <approved revision identifier and the plan file's blob SHA at this head>.",
        "",
        False,
        REQUEST_REVISION,
        id="request-omits-plan-revision",
    ),
    pytest.param(
        "assessment",
        "Please echo the Assessment-ID, assessed base/head, and plan revision in your substantive reply.",
        "Please echo the Assessment-ID and assessed base/head in your substantive reply.",
        False,
        ECHOED_REVISION,
        id="reply-echo-drops-plan-revision",
    ),
    pytest.param(
        "assessment",
        "a reply that echoes only the base/head cannot bind its verdict to an approved revision.",
        "",
        True,
        BASE_HEAD_LIMIT,
        id="moved-base-head-limit",
    ),
    pytest.param(
        "assessment",
        "Reconcile the revision a reply echoes with the revision in force;",
        "",
        False,
        READINESS_REVISION_RECONCILIATION,
        id="readiness-skips-echo-reconciliation",
    ),
    pytest.param(
        "skill",
        "reconcile the revision the substantive reply echoes against the revision in force",
        "accept any reply that echoes the base/head",
        False,
        LEDGER_ECHO_REVISION,
        id="ledger-binds-verdict-to-base-head-only",
    ),
    pytest.param(
        "assessment",
        "Plan revision: <approved revision identifier and the plan file's blob SHA at this head; omit when no ExecPlan applies>.",
        "",
        False,
        PROOF_REVISION,
        id="proof-request-omits-plan-revision",
    ),
    pytest.param(
        "assessment",
        "Please echo the Assessment-ID, assessed base/head, and plan revision in your substantive reply; echo the plan revision only when this request names one.",
        "Please echo the Assessment-ID and assessed base/head in your substantive reply.",
        False,
        PROOF_ECHO_REVISION,
        id="proof-reply-echo-drops-plan-revision",
    ),
    pytest.param(
        "assessment",
        "echo the plan revision only when this request names one.",
        "echo the plan revision in every reply.",
        False,
        PROOF_CONDITIONAL_ECHO,
        id="proof-echo-unconditional",
    ),
    pytest.param(
        "assessment",
        "a proof-only assignment with no ExecPlan keeps the base/head as its whole candidate and asks for no revision echo.",
        "",
        True,
        PROOF_NO_PLAN_CASE,
        id="moved-proof-no-plan-case",
    ),
    pytest.param(
        "skill",
        "so a proof request under an ExecPlan must also name and echo the revision;",
        "",
        False,
        LEDGER_PROOF_REVISION,
        id="ledger-proof-request-omits-revision",
    ),
    pytest.param(
        "skill",
        "without an ExecPlan, the base/head is the whole candidate and there is no revision to reconcile.",
        "",
        False,
        LEDGER_NO_PLAN,
        id="ledger-loses-no-plan-case",
    ),
    pytest.param(
        "assessment",
        "There is no subset or plateau waiver:",
        "A declared subset is sufficient for a lower layer:",
        False,
        STACK_NO_WAIVER,
        id="stack-path-admits-subset-waiver",
    ),
    pytest.param(
        "assessment",
        "naming the layer's milestones, the `github-stacks` parent it builds on and the milestones remaining above it",
        "",
        False,
        STACK_EVIDENCE,
        id="subset-evidence-unbound",
    ),
    pytest.param(
        "assessment",
        "the record never clears the gate.",
        "the record clears the gate.",
        False,
        STACK_LAYER_SCOPE,
        id="subset-evidence-clears-gate",
    ),
    pytest.param(
        "assessment",
        "the stack does not count as delivered until the layer that carries the plan's remaining milestones obtains the whole-plan verdict",
        "the stack counts as delivered on each layer's subset verdict",
        False,
        STACK_FINAL_WHOLE_PLAN,
        id="stack-drops-final-whole-plan",
    ),
    pytest.param(
        "assessment",
        "A single PR that claims the whole plan but delivers part of it never qualifies either",
        "",
        False,
        STACK_SINGLE_PR,
        id="stack-path-admits-single-partial-pr",
    ),
    pytest.param(
        "assessment",
        "That leaves a stack cut from one undivided plan with no delivery path:",
        "",
        False,
        STACK_DEADLOCK_NAMED,
        id="stack-deadlock-hidden",
    ),
    pytest.param(
        "assessment",
        "Split the approved plan into independently complete units, one per layer",
        "Let the readiness gate waive the whole-plan verdict for a lower layer",
        False,
        STACK_DELIVERY_PATH,
        id="stack-delivery-path-waives-rule",
    ),
    pytest.param(
        "assessment",
        "or deliver the undivided plan in a single PR.",
        "",
        False,
        STACK_SINGLE_PR_ALTERNATIVE,
        id="stack-drops-single-pr-option",
    ),
    pytest.param(
        "assessment",
        "restructure the plan before approval rather than discovering the",
        "restructure the plan when readiness blocks and waive the rule if it",
        False,
        STACK_APPROVAL_TIME,
        id="stack-deadlock-left-to-readiness",
    ),
    pytest.param(
        "assessment",
        REQUEST_SUBJECT_FIELD,
        "",
        False,
        REQUEST_SUBJECT,
        id="request-omits-assessed-subject",
    ),
    pytest.param(
        "assessment",
        "The `Assessed subject:` line is always the whole approved plan, and no other subject clears the gate.",
        "The `Assessed subject:` line may name a subset instead of the whole approved plan.",
        False,
        REQUEST_SUBJECT_WHOLE_PLAN,
        id="request-subject-admits-subset",
    ),
    pytest.param(
        "assessment",
        "A managed-stack layer may record a declared-subset verdict as evidence for that layer's actual scope only",
        "",
        True,
        REQUEST_SUBSET_EVIDENCE,
        id="moved-subset-evidence-rule",
    ),
)
