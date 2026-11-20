"""Abstract a recorded assessment thread into a readiness-model snapshot.

The agent-boundary recordings under ``tests/fixtures/readiness-agent-boundary``
hold the discussion an agent read: requests carrying an ``Assessment-ID`` and
replies carrying bolded fields. The FizzBee readiness model states a thread as
``request:reply``, where the request is the current question or one asked
about another candidate or a superseded revision, and the reply is one of the
model's reply shapes. This module reads the recorded text and makes that
abstraction. It decides nothing: whether a snapshot permits the transition is
looked up in the model-checked tables of ``specs/pr-readiness/suite.toml``.

The direction is one way. Every value comes from the recorded text and the
candidate the stand-in serves, never from the expectation a test asserts.
"""

from __future__ import annotations

from dataclasses import dataclass
import importlib.machinery
import importlib.util
from pathlib import Path
import re
from types import ModuleType

COMPLETENESS = "completeness"
PROOF = "proof"
WHOLE_PLAN = "whole-plan"
DECLARED_SUBSET = "declared-subset"
#: The assessment service's GitHub login, as the shipped skill names it.
ASSESSOR = "coderabbitai[bot]"

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "readiness-agent-boundary"
SHIM = FIXTURES / "gh-shim.py"

#: A reply's verdict, and the shape it settles on its own. ``clear`` settles
#: nothing yet: the candidate, revision and subject still decide the shape.
_VERDICT_SHAPES = {
    "not applicable": "not-applicable-claim",
    "not clear": "not-clear",
    "clear": "",
}

#: A completeness reply's subject, and the shape a clear verdict for it has.
_SUBJECT_SHAPES = {WHOLE_PLAN: "sound-clear", DECLARED_SUBSET: "subset-clear"}


def _load_stand_in() -> ModuleType:
    """Return the shipped `gh` stand-in as a module, for its own expressions.

    The stand-in is where a request's `Assessment-ID` and a plan file's
    revision are defined for this repository, so reading them with its own
    expressions keeps one definition rather than a second one here. It does no
    import-time work beyond deriving its run directory from its location, so
    loading it reads nothing and writes nothing.
    """
    loader = importlib.machinery.SourceFileLoader("gh_stand_in", str(SHIM))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None, "the shipped gh stand-in could not be loaded"
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


SHIM_MODULE = _load_stand_in()


@dataclass(frozen=True)
class Bounds:
    """The candidate a thread is judged against.

    ``base`` and ``head`` are what the PR itself reports, ``in_force`` is the
    revision the plan states at that head, and ``required`` the proofs a
    proof reply must cover.
    """

    base: str
    head: str
    in_force: str
    required: tuple[str, ...]


def field_in(body: str, label: str) -> str:
    """Return the value a reply records for one bolded field.

    The reply format is the recorded one: each field is a bolded label
    followed by its value to the end of the line, as `make_scenarios.reply`
    writes it and the shipped runner reads it. A missing field raises rather
    than yielding an empty value that would silently weaken a case.
    """
    stated = optional_field(body, label)
    assert stated is not None, f"the reply states no {label}: {body!r}"
    return stated


def optional_field(body: str, label: str) -> str | None:
    """Return a field's value, or None when the reply omits the field.

    The proof template omits its plan revision when the request named none, so
    a proof reply may legitimately carry no revision at all. Keeping the
    absence distinguishable from an empty string is what lets the recorded
    unbound-revision case fail the binding rule rather than a parse error.
    """
    stated = re.search(rf"\*\*{re.escape(label)}:\*\*\s*(.+)", body)
    return stated.group(1).strip() if stated else None


def _is_reply(entry: dict, marker: str) -> bool:
    """Return whether one discussion entry is the assessor's reply to ``marker``."""
    body = str(entry.get("body", ""))
    if entry.get("user", {}).get("login") != ASSESSOR or "**Verdict:" not in body:
        return False
    return field_in(body, "Assessment-ID").strip("`") == marker


def answered(listing: list[dict], marker: str) -> dict:
    """Return the bot reply echoing ``marker``, from the served discussion."""
    for entry in listing:
        if _is_reply(entry, marker):
            return entry
    raise AssertionError(f"the discussion holds no reply to {marker!r}")


def reply_for(listing: list[dict], request: dict) -> str:
    """Return the recorded reply to one request, by the marker it echoes."""
    marker = SHIM_MODULE.ASSESSMENT_ID.search(str(request["body"]))
    assert marker, "the request carries no assessment marker"
    return str(answered(listing, marker.group(1))["body"])


def verdict_in(body: str) -> str:
    """Return the verdict a reply states, case-folded."""
    stated = re.search(r"\*\*Verdict:\s*([^*]+)\*\*", body)
    assert stated, f"the reply states no verdict: {body!r}"
    return stated.group(1).strip().casefold()


def subject_in(body: str) -> str:
    """Return the subject a reply says it assessed.

    The reference says the `Assessed subject:` line is the whole approved plan
    and that a managed-stack layer records a declared subset instead. The
    reply writes the subject as prose, so this maps the two documented forms
    and refuses anything else rather than choosing one.
    """
    stated = field_in(body, "Assessed subject").casefold()
    if "declared subset" in stated:
        return DECLARED_SUBSET
    assert "whole approved plan" in stated, f"unrecognized assessed subject: {stated!r}"
    return WHOLE_PLAN


def assessed_candidate(body: str) -> tuple[str, str]:
    """Return the base and head a reply says it assessed.

    The reply states the pair as `base...head`, so each half is read from its
    own side of the separator. Passing what the reply actually names, rather
    than the pull's own head, is what lets a reply about another candidate
    hold the gate instead of being silently rebound to this one.
    """
    stated = field_in(body, "Assessed base/head")
    base, _, head = stated.partition("...")
    assert base and head, f"the reply names no base/head pair: {stated!r}"
    return base, head


def named_proofs(reply: str) -> tuple[str, ...]:
    """Return the proofs a proof reply's subject names, as its backticked names.

    A proof verdict's subject is the named proofs it assessed, so the names
    inside backticks on that line are its inventory. This is how the recorded
    replies state it, and the inventory the request asked about is read the
    same way.
    """
    return tuple(re.findall(r"`([^`]+)`", field_in(reply, "Assessed subject")))


def checks(pr: dict) -> dict[str, str]:
    """Return each check's conclusion from a served status rollup."""
    return {
        str(check.get("name") or check.get("context")): str(
            check.get("conclusion") or check.get("state")
        )
        for check in pr.get("statusCheckRollup") or []
    }


def codescene_clear(pr: dict) -> bool:
    """Return whether the served CodeScene check reports no finding.

    The check's conclusion alone is not the signal: CodeScene reports its
    findings in the output title, and a green run that lists advisory findings
    is exactly what the readiness rule must not clear.
    """
    found = [
        check
        for check in pr.get("statusCheckRollup") or []
        if "codescene" in str(check.get("name", "")).casefold()
    ]
    if not found:
        return False
    output = found[0].get("output") or {}
    text = f"{output.get('title', '')} {output.get('summary', '')}"
    return "no issues" in text.casefold() and str(found[0].get("conclusion")) == "SUCCESS"


def _verdict_shape(body: str) -> str:
    """Return the shape a reply's verdict settles alone, or nothing for `clear`.

    Anything other than the three documented verdicts is an acknowledgement:
    it answers nothing.
    """
    return _VERDICT_SHAPES.get(verdict_in(body), "acknowledgement")


def _binding_shape(body: str, bounds: Bounds, asked_revision: str | None) -> str:
    """Return the shape a clear reply's candidate or revision settles, if any.

    A reply for another base/head says nothing about this one. When the
    request named a revision, the reply must echo that revision: naming none
    is unbound, and naming another is superseded.
    """
    if assessed_candidate(body) != (bounds.base, bounds.head):
        return "other-candidate"
    if asked_revision is None:
        return ""
    stated = optional_field(body, "Plan revision")
    if stated is None:
        return "no-revision-echo"
    return "" if stated == asked_revision else "superseded-revision-echo"


def _subject_shape(kind: str, body: str, required: tuple[str, ...]) -> str:
    """Return the shape a clear, bound reply's subject settles.

    A completeness reply clears for the whole plan or a declared subset. A
    proof reply clears only when it names every required proof; naming some
    is partial and naming none is no coverage at all.
    """
    if kind == COMPLETENESS:
        return _SUBJECT_SHAPES[subject_in(body)]
    named = set(named_proofs(body))
    covered = [proof for proof in required if proof in named]
    if len(covered) == len(required):
        return "sound-clear"
    return "partial-proofs" if covered else "no-proofs"


def reply_shape(kind: str, body: str, bounds: Bounds, asked_revision: str | None) -> str:
    """Return the model's reply shape for one recorded reply body.

    Every field comes from the reply's own text. The stages run in the order
    in which a shortfall hides the ones after it: a reply that is not a clear
    verdict has no candidate or revision worth reading, and a clear one for
    another candidate says nothing about this one's subject.

    Parameters
    ----------
    kind : str
        ``completeness`` or ``proof``, selecting how the subject is read.
    body : str
        The reply's recorded body.
    bounds : Bounds
        The candidate the PR reports and the proofs it requires.
    asked_revision : str or None
        The revision the request that prompted this reply named, if any.
    """
    return (
        _verdict_shape(body)
        or _binding_shape(body, bounds, asked_revision)
        or _subject_shape(kind, body, bounds.required)
    )


def _request_state(body: str, bounds: Bounds) -> tuple[str, str | None]:
    """Return whether a request asks about this candidate, and its revision.

    A request is ``current`` unless its own text names another head or a
    revision other than the one in force. A request that names no head is
    read as asked about this candidate, because the recorded proof question
    states its revision and leaves the head to the completeness request.
    """
    asked_head = re.search(r"Published head: (\S+?);", body)
    asked = SHIM_MODULE.PLAN_REVISION.search(body)
    asked_revision = asked.group(1) if asked else None
    if asked_head and asked_head.group(1) != bounds.head:
        return "another-candidate", asked_revision
    if asked_revision not in (None, bounds.in_force):
        return "superseded-revision", asked_revision
    return "current", asked_revision


def thread_state(kind: str, listing: list[dict], request: dict | None, bounds: Bounds) -> str:
    """Return what one assessment's thread holds, as ``request:reply``.

    A request with no recorded reply is ``<request>:none``, an unanswered
    question; no request at all is ``none``, a question never asked.
    """
    if request is None:
        return "none"
    state, asked_revision = _request_state(str(request["body"]), bounds)
    try:
        reply = reply_for(listing, request)
    except AssertionError:
        return f"{state}:none"
    return f"{state}:{reply_shape(kind, reply, bounds, asked_revision)}"
