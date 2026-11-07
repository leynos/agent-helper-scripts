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
LEDGER_STALE_REVISION = "ledger section must state: A verdict recorded against a superseded plan revision"
LEDGER_PROOF_READINESS = "ledger section must state: When the proof assessment applies"
READINESS_STALE_REVISION = "readiness section must compare the currently approved plan revision"

ASSESSMENT_MUTATIONS = (
    pytest.param(
        'assessment',
        'Both applicable assessments must clear',
        'Both applicable assessments need not clear',
        False,
        'applicable assessments must precede readiness',
        id='inverted-readiness',
    ),
    pytest.param(
        'assessment',
        'An already-ready PR stays ready; obtain missing assessments before merge.',
        '',
        False,
        'missing assessment must block merge',
        id='removed-ready-preservation',
    ),
    pytest.param(
        'assessment',
        'for the published candidate.',
        'for any old candidate.',
        False,
        'gates must bind to published candidate',
        id='stale-publication',
    ),
    pytest.param(
        'assessment',
        'Assessment conversations never go through `comenq`.',
        'Assessment conversations always go through `comenq`.',
        False,
        'assessment follow-ups must not enter the review queue',
        id='queued-assessment',
    ),
    pytest.param(
        'assessment',
        'Both applicable assessments must clear for the accepted candidate before its draft-to-ready transition.',
        '',
        True,
        'applicable assessments must precede readiness',
        id='moved-readiness',
    ),
    pytest.param(
        'skill',
        'all applicable pre-readiness assessments hold',
        'no assessments hold',
        False,
        'parent readiness condition must include assessments',
        id='parent-waiver',
    ),
    pytest.param(
        'skill',
        'An already-ready PR remains ready while missing or invalidated assessments block merge.',
        '',
        True,
        'parent must preserve ready state and merge blocker',
        id='moved-parent-preservation',
    ),
    pytest.param(
        'skill',
        '7. Applicable ExecPlan completeness/correctness and proof-specific assessments cover the accepted candidate, with no unresolved substantive concern.',
        '',
        True,
        'merge checklist must require candidate-bound assessments',
        id='moved-merge-guard',
    ),
    pytest.param(
        'assessment',
        'Known limitations: <evidential limits only: checks not run, inspection not possible, proof bounds; not unimplemented plan milestones>.',
        '',
        False,
        'completeness request must restrict limitations to evidential limits',
        id='removed-limitations-guard',
    ),
    pytest.param(
        'assessment',
        'not unimplemented plan milestones',
        'including unimplemented plan milestones',
        False,
        'completeness request must restrict limitations to evidential limits',
        id='inverted-limitations-guard',
    ),
    pytest.param(
        'assessment',
        'An unimplemented plan milestone is in-scope work, not a limitation, per [applicability and ownership](#applicability-and-ownership).',
        '',
        True,
        'completeness section must bind milestones to the ownership rule',
        id='moved-milestone-ownership',
    ),
    pytest.param(
        'skill',
        'A verdict of `clear`, `not clear`, or `pending`, with a justified `not applicable` for an assessment that does not apply',
        'a verdict of `posted` or `answered`',
        False,
        LEDGER_VERDICT,
        id='ledger-drops-verdict',
    ),
    pytest.param(
        'skill',
        'When the completeness assessment applies, only a clear whole-plan completeness verdict that covers the accepted base/head and was recorded against the currently approved plan revision satisfies [the readiness gate](references/execplan-assessment.md#readiness-and-later-changes).',
        '',
        True,
        LEDGER_CLEARING,
        id='moved-ledger-readiness-pointer',
    ),
    pytest.param(
        'skill',
        'on the same entry as the base/head and the plan revision it was given for.',
        '',
        False,
        'ledger section must state: on the same entry',
        id='unbound-ledger-verdict',
    ),
    pytest.param(
        'skill',
        "The completeness assessment's subject is either the whole plan or the declared subset; the proof assessment's subject is the named proofs it covers.",
        "Every assessment's subject is the whole plan.",
        False,
        "ledger section must state: The completeness assessment's subject",
        id='proof-subject-collapsed-to-whole-plan',
    ),
    pytest.param(
        'skill',
        'A verdict recorded against a superseded plan revision does not carry over, even when the base/head is unchanged.',
        '',
        False,
        'ledger section must state: A verdict recorded against a superseded plan revision',
        id='ledger-accepts-superseded-plan-revision',
    ),
    pytest.param(
        'assessment',
        'a verdict recorded against a revision that has since been superseded by a newly approved revision does not clear the gate, even when the base/head is unchanged.',
        '',
        False,
        'readiness section must compare the currently approved plan revision',
        id='readiness-accepts-superseded-plan-revision',
    ),
    pytest.param(
        'skill',
        'When the proof assessment applies, readiness also requires its clear verdict for the same base/head; a clear completeness verdict alone does not satisfy the gate.',
        'A clear completeness verdict alone satisfies the readiness gate, whatever the proof verdict.',
        False,
        LEDGER_PROOF_READINESS,
        id='completeness-alone-may-clear',
    ),
    pytest.param(
        'skill',
        'When the completeness assessment applies, only a clear whole-plan completeness verdict that covers the accepted base/head and was recorded against the currently approved plan revision',
        'When the completeness assessment applies, only a clear declared-subset completeness verdict that covers the accepted base/head and was recorded against the currently approved plan revision',
        False,
        LEDGER_CLEARING,
        id='declared-subset-may-clear',
    ),
    pytest.param(
        'skill',
        'and was recorded against the currently approved plan revision satisfies',
        'and satisfies',
        False,
        LEDGER_CLEARING,
        id='unbound-plan-revision',
    ),
)
