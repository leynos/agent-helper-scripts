"""Exercise the documented draft-to-ready gate at the workflow boundary.

The skills state the readiness gate in prose, so these tests drive its
executable specification with whole candidates: accepted base/head, approved
plan revision, stack topology, and the two assessment verdicts. Each case
checks whether the candidate may leave draft, which is the externally
observable transition this work changes.

The specification is not product code. ``pr_readiness_model`` restates the
gate, and the cases below keep the restatement honest: every reason the model
returns must cite a sentence the shipped documents still contain, so a rule
cannot be dropped from the model or from the prose alone.
"""

from __future__ import annotations

import re
from pathlib import Path

import pr_readiness_model as readiness_module
import pytest
from pr_readiness_model import (
    CLEAR,
    COMPLETENESS,
    DECLARED_SUBSET,
    NOT_APPLICABLE,
    NOT_CLEAR,
    PENDING,
    PROOF,
    REASON_CITATIONS,
    WHOLE_PLAN,
    Candidate,
    StackLayer,
    Verdict,
    readiness,
)
from skill_contract_support import normalize, raw_section

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/pr-babysitting/SKILL.md"
ASSESSMENT = ROOT / "skills/pr-babysitting/references/execplan-assessment.md"

BASE = "base0000"
HEAD = "head0000"
REVISION = "rev-2026-11-01"


def candidate(
    *,
    revision: str | None = REVISION,
    layer: StackLayer | None = None,
    head: str = HEAD,
    ci_green: bool = True,
    codescene_clear: bool = True,
) -> Candidate:
    """Return the accepted candidate, optionally with a plan revision or stack."""
    return Candidate(
        base=BASE,
        head=head,
        approved_plan_revision=revision,
        stack_layer=layer,
        ci_green=ci_green,
        codescene_clear=codescene_clear,
    )


def completeness(
    *,
    verdict: str = CLEAR,
    subject: str = WHOLE_PLAN,
    revision: str | None = REVISION,
    echoed: str | None = REVISION,
    head: str = HEAD,
    base: str = BASE,
    justification: str = "",
) -> Verdict:
    """Return a completeness verdict, whole-plan and exact by default."""
    return Verdict(verdict=verdict, base=base, head=head,
                   plan_revision=revision, echoed_revision=echoed,
                   subject=subject, justification=justification)


def proof(
    *,
    verdict: str = NOT_APPLICABLE,
    revision: str | None = REVISION,
    echoed: str | None = REVISION,
    head: str = HEAD,
    base: str = BASE,
    justification: str = "No proof is affected by this change.",
) -> Verdict:
    """Return a proof verdict; the default is a justified not-applicable."""
    return Verdict(verdict=verdict, base=base, head=head,
                   plan_revision=revision, echoed_revision=echoed,
                   subject="named proofs", justification=justification)


def test_a_valid_current_assessment_allows_readiness() -> None:
    """Clear, candidate-bound, revision-bound assessments mark the PR ready."""
    decision = readiness(candidate(), completeness(), proof())
    assert decision.ready, decision.reason
    assert decision.reason == "ready"


def test_a_clear_proof_under_the_execplan_echoes_the_same_revision() -> None:
    """Ordinary single-PR delivery needs no stack, but keeps the revision."""
    decision = readiness(
        candidate(),
        completeness(subject=WHOLE_PLAN),
        proof(verdict=CLEAR),
    )
    assert decision.ready, decision.reason


@pytest.mark.parametrize(
    ("verdict", "reason"),
    [
        (PENDING, "completeness-pending"),
        (NOT_CLEAR, "completeness-not-clear"),
    ],
    ids=["pending", "not-clear"],
)
def test_an_unsettled_completeness_verdict_keeps_the_pr_in_draft(
    verdict: str, reason: str
) -> None:
    """Pending or not-clear completeness blocks the draft-to-ready transition."""
    decision = readiness(candidate(), completeness(verdict=verdict), proof())
    assert not decision.ready
    assert decision.reason == reason


@pytest.mark.parametrize(
    ("base", "head", "reason"),
    [
        (BASE, "superseded-head", "completeness-candidate-mismatch"),
        ("other-base", HEAD, "completeness-candidate-mismatch"),
    ],
    ids=["stale-head", "other-base"],
)
def test_a_verdict_on_another_candidate_keeps_the_pr_in_draft(
    base: str, head: str, reason: str
) -> None:
    """A verdict must cover the accepted base/head, not one it replaced."""
    decision = readiness(
        candidate(), completeness(base=base, head=head), proof()
    )
    assert not decision.ready
    assert decision.reason == reason


def test_a_subset_verdict_without_a_stack_keeps_the_pr_in_draft() -> None:
    """A single PR that claims the whole plan cannot clear on its subset."""
    decision = readiness(
        candidate(), completeness(subject=DECLARED_SUBSET), proof()
    )
    assert not decision.ready
    assert decision.reason == "completeness-whole-plan-required"


def test_a_lower_stack_layer_clears_on_its_named_subset() -> None:
    """A layer with its parent and milestones above clears only its own work."""
    layer = StackLayer(
        milestones=("EP-M1", "EP-M2"),
        parent="stack#12",
        remaining_above=("EP-M3", "EP-M4"),
    )
    decision = readiness(
        candidate(layer=layer), completeness(subject=DECLARED_SUBSET), proof()
    )
    assert decision.ready, decision.reason


@pytest.mark.parametrize(
    "layer",
    [
        StackLayer(milestones=(), parent="stack#12", remaining_above=("EP-M3",)),
        StackLayer(milestones=("EP-M1",), parent="", remaining_above=("EP-M3",)),
    ],
    ids=["unnamed-layer-milestones", "unnamed-parent"],
)
def test_a_subset_verdict_without_stack_evidence_keeps_the_pr_in_draft(
    layer: StackLayer,
) -> None:
    """A claimed subset must name its layer milestones and stack parent."""
    decision = readiness(
        candidate(layer=layer), completeness(subject=DECLARED_SUBSET), proof()
    )
    assert not decision.ready
    assert decision.reason == "completeness-stack-evidence-missing"


def test_the_final_stack_layer_cannot_clear_on_its_subset() -> None:
    """The layer carrying the remainder needs the whole-plan verdict."""
    layer = StackLayer(
        milestones=("EP-M3", "EP-M4"), parent="stack#12", remaining_above=()
    )
    decision = readiness(
        candidate(layer=layer), completeness(subject=DECLARED_SUBSET), proof()
    )
    assert not decision.ready
    assert decision.reason == "completeness-whole-plan-required"


def test_a_single_pr_claiming_the_whole_plan_cannot_clear_on_a_subset() -> None:
    """A PR with no layer above it has no one to carry the remainder."""
    layer = StackLayer(
        milestones=("EP-M1",),
        parent="stack#12",
        remaining_above=("EP-M3",),
        claims_whole_plan=True,
    )
    decision = readiness(
        candidate(layer=layer), completeness(subject=DECLARED_SUBSET), proof()
    )
    assert not decision.ready
    assert decision.reason == "completeness-whole-plan-required"


@pytest.mark.parametrize(
    ("revision", "echoed", "reason"),
    [
        ("rev-previous", "rev-previous", "completeness-superseded-revision"),
        (REVISION, None, "completeness-revision-unbound"),
    ],
    ids=["superseded-revision", "echo-omits-revision"],
)
def test_an_unbound_plan_revision_keeps_the_pr_in_draft(
    revision: str, echoed: str | None, reason: str
) -> None:
    """A verdict recorded against another revision does not clear the gate."""
    decision = readiness(
        candidate(), completeness(revision=revision, echoed=echoed), proof()
    )
    assert not decision.ready
    assert decision.reason == reason


def test_a_proof_verdict_on_a_superseded_revision_keeps_the_pr_in_draft() -> None:
    """The revision binding applies to whichever assessment is in scope."""
    decision = readiness(
        candidate(),
        completeness(),
        proof(verdict=CLEAR, revision="rev-previous", echoed="rev-previous"),
    )
    assert not decision.ready
    assert decision.reason == "proof-superseded-revision"


@pytest.mark.parametrize(
    ("verdict", "reason"),
    [
        (PENDING, "proof-pending"),
        (NOT_CLEAR, "proof-not-clear"),
    ],
    ids=["pending", "not-clear"],
)
def test_an_unsettled_proof_verdict_keeps_the_pr_in_draft(
    verdict: str, reason: str
) -> None:
    """A clear completeness verdict alone does not satisfy the gate."""
    decision = readiness(
        candidate(), completeness(), proof(verdict=verdict, justification="")
    )
    assert not decision.ready
    assert decision.reason == reason


def test_a_proof_verdict_must_echo_its_revision_under_an_execplan() -> None:
    """A proof request under an ExecPlan names and echoes the revision."""
    decision = readiness(
        candidate(),
        completeness(),
        proof(verdict=CLEAR, revision=REVISION, echoed=None),
    )
    assert not decision.ready
    assert decision.reason == "proof-revision-unbound"


def test_an_undefended_not_applicable_keeps_the_pr_in_draft() -> None:
    """Not applicable needs evidence; silence is not a disposition."""
    decision = readiness(
        candidate(), completeness(), proof(verdict=NOT_APPLICABLE, justification="  ")
    )
    assert not decision.ready
    assert decision.reason == "not-applicable-undefended"


def test_a_proof_only_assignment_needs_no_plan_revision() -> None:
    """Without an ExecPlan the base/head is the whole candidate."""
    decision = readiness(
        candidate(revision=None),
        completeness(verdict=NOT_APPLICABLE, revision=None, echoed=None,
                     justification="No ExecPlan governs this change."),
        proof(verdict=CLEAR, revision=None, echoed=None),
    )
    assert decision.ready, decision.reason


def test_an_unaffected_proof_under_an_execplan_needs_no_reply() -> None:
    """A not-applicable proof has no reply to bind, so no revision is echoed."""
    decision = readiness(
        candidate(),
        completeness(),
        proof(verdict=NOT_APPLICABLE, revision=None, echoed=None),
    )
    assert decision.ready, decision.reason


def test_an_unaffected_completeness_needs_no_subject_or_revision() -> None:
    """A not-applicable completeness is skipped, not checked against a stack."""
    decision = readiness(
        candidate(revision=None),
        completeness(verdict=NOT_APPLICABLE, revision=None, echoed=None,
                     subject=DECLARED_SUBSET,
                     justification="This PR only authors the plan."),
        proof(verdict=NOT_APPLICABLE, revision=None, echoed=None,
              justification="No proof is affected by this change."),
    )
    assert decision.ready, decision.reason


@pytest.mark.parametrize(
    "verdict",
    ["acknowledged", "posted", "answered", "substantially complete"],
)
def test_an_unrecognized_verdict_is_not_settled(verdict: str) -> None:
    """Only the four documented verdicts settle an assessment."""
    decision = readiness(
        candidate(),
        Verdict(verdict=verdict, base=BASE, head=HEAD,
                plan_revision=REVISION, echoed_revision=REVISION),
        proof(),
    )
    assert not decision.ready
    assert decision.reason == "assessment-unrecognized-verdict"


@pytest.mark.parametrize(
    ("ci_green", "codescene_clear", "reason"),
    [
        (False, True, "ci-not-green"),
        (True, False, "codescene-not-clear"),
        (False, False, "ci-not-green"),
    ],
    ids=["red-ci", "open-codescene", "both"],
)
def test_the_delivery_gates_precede_the_assessments(
    ci_green: bool, codescene_clear: bool, reason: str
) -> None:
    """Green CI and clear CodeScene findings come before any ready transition."""
    decision = readiness(
        candidate(ci_green=ci_green, codescene_clear=codescene_clear),
        completeness(verdict=PENDING),
        proof(),
    )
    assert not decision.ready
    assert decision.reason == reason, "delivery gates must be checked first"


@pytest.mark.parametrize(("reason", "citation"), sorted(REASON_CITATIONS.items()))
def test_each_readiness_reason_cites_a_sentence_in_the_shipped_documents(
    reason: str, citation: str
) -> None:
    """No reason may outlive the prose that states it."""
    documents = normalize(SKILL.read_text()) + " " + normalize(ASSESSMENT.read_text())
    assert normalize(citation) in documents, (
        f"reason {reason!r} cites a sentence no shipped document states: {citation}"
    )


def _lower_stack() -> StackLayer:
    """Return a layer with a parent and milestones above it."""
    return StackLayer(
        milestones=("EP-M1",), parent="stack#12", remaining_above=("EP-M3",)
    )


#: One candidate and verdict pair per reason the model can return. Every entry
#: is a state, so the coverage test can require the model to produce exactly
#: the cited reasons rather than a sample of them.
REASON_STATES = {
    "ci-not-green": (candidate(ci_green=False), completeness(), proof()),
    "codescene-not-clear": (
        candidate(codescene_clear=False), completeness(), proof()
    ),
    "assessment-unrecognized-verdict": (
        candidate(),
        Verdict(verdict="acknowledged", base=BASE, head=HEAD),
        proof(),
    ),
    "not-applicable-undefended": (
        candidate(),
        completeness(),
        proof(verdict=NOT_APPLICABLE, justification="  "),
    ),
    "completeness-pending": (
        candidate(), completeness(verdict=PENDING), proof()
    ),
    "completeness-not-clear": (
        candidate(), completeness(verdict=NOT_CLEAR), proof()
    ),
    "completeness-candidate-mismatch": (
        candidate(), completeness(head="superseded-head"), proof()
    ),
    "completeness-superseded-revision": (
        candidate(), completeness(revision="rev-previous", echoed="rev-previous"),
        proof(),
    ),
    "completeness-revision-unbound": (
        candidate(), completeness(echoed=None), proof()
    ),
    "completeness-whole-plan-required": (
        candidate(), completeness(subject=DECLARED_SUBSET), proof()
    ),
    "completeness-stack-evidence-missing": (
        candidate(layer=StackLayer(milestones=(), parent="stack#12",
                                  remaining_above=("EP-M3",))),
        completeness(subject=DECLARED_SUBSET),
        proof(),
    ),
    "proof-pending": (
        candidate(), completeness(), proof(verdict=PENDING, justification="")
    ),
    "proof-not-clear": (
        candidate(), completeness(), proof(verdict=NOT_CLEAR, justification="")
    ),
    "proof-candidate-mismatch": (
        candidate(), completeness(), proof(verdict=CLEAR, head="superseded-head")
    ),
    "proof-superseded-revision": (
        candidate(), completeness(),
        proof(verdict=CLEAR, revision="rev-previous", echoed="rev-previous"),
    ),
    "proof-revision-unbound": (
        candidate(), completeness(), proof(verdict=CLEAR, echoed=None)
    ),
    "ready": (candidate(), completeness(), proof()),
}


def test_the_model_produces_exactly_the_reasons_it_cites() -> None:
    """Every cited reason is reachable, and no other reason is returned."""
    produced = {reason: readiness(*state).reason for reason, state in REASON_STATES.items()}
    wrong = {reason: got for reason, got in produced.items() if got != reason}
    assert not wrong, f"states produced a different reason: {wrong}"
    assert set(produced) == set(REASON_CITATIONS), (
        "cited reasons and reachable reasons must match: "
        f"{sorted(set(produced) ^ set(REASON_CITATIONS))}"
    )
    assert set(readiness_module.REASONS) == set(REASON_CITATIONS)


@pytest.mark.parametrize("reason", sorted(REASON_CITATIONS))
def test_dropping_any_single_citation_is_detected(reason: str) -> None:
    """No citation can be deleted without failing the model's own check."""
    reduced = {
        key: value for key, value in REASON_CITATIONS.items() if key != reason
    }
    assert set(REASON_STATES) != set(reduced), (
        f"dropping {reason!r} would leave the reachable reasons unchanged"
    )
    real_state = REASON_STATES[reason]
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(readiness_module, "REASON_CITATIONS", reduced)
        monkeypatch.setattr(readiness_module, "REASONS", frozenset(reduced))
        with pytest.raises(AssertionError):
            readiness(*real_state)


def test_the_readiness_section_states_the_transition_under_assessment() -> None:
    """The prose and the model agree on where the gate sits in the lifecycle."""
    readiness_text = normalize(raw_section(ASSESSMENT.read_text(), "Readiness and later changes"))
    assert "before its draft-to-ready transition" in readiness_text, (
        "readiness gate must still precede the draft-to-ready transition"
    )
    assert "An already-ready PR stays ready; obtain missing assessments before merge" in readiness_text, (
        "a blocked gate must not return the PR to draft"
    )
    assert re.search(r"Do not set the PR back to draft", readiness_text), (
        "readiness section must keep the redrafting prohibition"
    )


def test_readiness_model_names_the_completeness_and_proof_kinds() -> None:
    """The model's assessment kinds match the two documented assessments."""
    assert (COMPLETENESS, PROOF) == ("completeness", "proof")


DEFECTIVE_RULES = (
    pytest.param(
        "_subject",
        lambda monkeypatch: monkeypatch.setattr(
            readiness_module, "_subject", lambda subject, cand: None
        ),
        (candidate(), completeness(subject=DECLARED_SUBSET), proof()),
        "completeness-whole-plan-required",
        id="subject-rule-dropped",
    ),
    pytest.param(
        "_revision_bound",
        lambda monkeypatch: monkeypatch.setattr(
            readiness_module, "_revision_bound", lambda verdict, cand, reason: None
        ),
        (candidate(), completeness(revision="rev-previous", echoed="rev-previous"),
         proof()),
        "completeness-superseded-revision",
        id="revision-binding-dropped",
    ),
    pytest.param(
        "_disposition",
        lambda monkeypatch: monkeypatch.setattr(
            readiness_module,
            "_disposition",
            lambda verdict, kind, cand: (
                None if kind == PROOF else _real_disposition(verdict, kind, cand)
            ),
        ),
        (candidate(), completeness(), proof(verdict=PENDING, justification="")),
        "proof-pending",
        id="proof-disposition-dropped",
    ),
    pytest.param(
        "_disposition",
        lambda monkeypatch: monkeypatch.setattr(
            readiness_module,
            "_disposition",
            lambda verdict, kind, cand: (
                None
                if verdict.verdict == NOT_CLEAR
                else _real_disposition(verdict, kind, cand)
            ),
        ),
        (candidate(), completeness(verdict=NOT_CLEAR), proof()),
        "completeness-not-clear",
        id="not-clear-treated-as-settled",
    ),
    pytest.param(
        "names_its_evidence",
        lambda monkeypatch: monkeypatch.setattr(
            StackLayer, "names_its_evidence", property(lambda self: True)
        ),
        (candidate(layer=StackLayer(milestones=(), parent="stack#12",
                                    remaining_above=("EP-M3",))),
         completeness(subject=DECLARED_SUBSET), proof()),
        "completeness-stack-evidence-missing",
        id="stack-evidence-requirement-dropped",
    ),
    pytest.param(
        "is_final_layer",
        lambda monkeypatch: monkeypatch.setattr(
            StackLayer, "is_final_layer", property(lambda self: False)
        ),
        (candidate(layer=StackLayer(milestones=("EP-M3",), parent="stack#12",
                                    remaining_above=())),
         completeness(subject=DECLARED_SUBSET), proof()),
        "completeness-whole-plan-required",
        id="final-layer-exemption-widened",
    ),
    pytest.param(
        "_delivery_gates",
        lambda monkeypatch: monkeypatch.setattr(
            readiness_module,
            "_delivery_gates",
            lambda cand: (
                _real_delivery_gates(cand)
                if not cand.codescene_clear
                else None
            ),
        ),
        (candidate(ci_green=False), completeness(), proof()),
        "ci-not-green",
        id="ci-gate-dropped",
    ),
    pytest.param(
        "_delivery_gates",
        lambda monkeypatch: monkeypatch.setattr(
            readiness_module,
            "_delivery_gates",
            lambda cand: (
                _real_delivery_gates(cand) if not cand.ci_green else None
            ),
        ),
        (candidate(codescene_clear=False), completeness(), proof()),
        "codescene-not-clear",
        id="codescene-gate-dropped",
    ),
    pytest.param(
        "VERDICTS",
        lambda monkeypatch: monkeypatch.setattr(
            readiness_module, "VERDICTS", (*readiness_module.VERDICTS, "acknowledged")
        ),
        (candidate(),
         Verdict(verdict="acknowledged", base=BASE, head=HEAD,
                 plan_revision=REVISION, echoed_revision=REVISION),
         proof()),
        "assessment-unrecognized-verdict",
        id="unrecognized-verdict-accepted",
    ),
    pytest.param(
        "_revision_bound",
        lambda monkeypatch: monkeypatch.setattr(
            readiness_module, "_revision_bound", lambda verdict, cand, kind: None
        ),
        (candidate(), completeness(), proof(verdict=CLEAR, echoed=None)),
        "proof-revision-unbound",
        id="proof-revision-binding-dropped",
    ),
    pytest.param(
        "_revision_bound",
        lambda monkeypatch: monkeypatch.setattr(
            readiness_module, "_revision_bound", lambda verdict, cand, kind: None
        ),
        (candidate(), completeness(echoed=None), proof()),
        "completeness-revision-unbound",
        id="completeness-echo-binding-dropped",
    ),
    pytest.param(
        "_disposition",
        lambda monkeypatch: monkeypatch.setattr(
            readiness_module,
            "_disposition",
            lambda verdict, kind, cand: (
                None
                if verdict.verdict == NOT_APPLICABLE and not verdict.justification.strip()
                else _real_disposition(verdict, kind, cand)
            ),
        ),
        (candidate(), completeness(), proof(verdict=NOT_APPLICABLE, justification="  ")),
        "not-applicable-undefended",
        id="undefended-not-applicable-accepted",
    ),
)
_real_disposition = readiness_module._disposition
_real_delivery_gates = readiness_module._delivery_gates


@pytest.mark.parametrize(
    ("rule", "defect", "state", "reason"),
    DEFECTIVE_RULES,
)
def test_a_defective_readiness_rule_is_detected_by_its_case(
    rule: str,
    defect,
    state,
    reason: str,
) -> None:
    """Each mutation control proves its case discriminates, not just passes."""
    real = readiness(*state)
    assert not real.ready and real.reason == reason, (
        f"{rule} control's case must fail on the real model"
    )
    with pytest.MonkeyPatch.context() as monkeypatch:
        defect(monkeypatch)
        mutated = readiness(*state)
    assert mutated.ready, (
        f"case {reason!r} does not detect a dropped {rule} rule"
    )
    assert reason in REASON_CITATIONS, (
        f"mutation control cites an uncited reason: {reason}"
    )
