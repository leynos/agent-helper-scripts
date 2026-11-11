"""Drive the implementation handoff through the readiness boundary end to end.

`pr_readiness_workflow` is the in-memory sequence. These cases run it from the
two shipped artefacts the receiver actually reads: the handoff packet in
`sdlc-implementation`, and a rehearsal scenario served through the shipped
`gh` stand-in. The candidate, the approved revision, the request marker, the
reply and the CI and CodeScene state the delivery gates consult all come from
those bytes, so a handoff or a premise that changes shape moves these cases
with it.

That is the direction the review asked for and the in-memory case did not
cover. `test_the_shipped_handoff_packet_reaches_the_readiness_sequence` reads
the packet and then drives the workflow with values composed inside that test.
Here the receiver is handed a scenario, reads the discussion and the plan
through the stand-in, derives its assignment from the packet, and decides on
the reply the recording holds. The recordings prove that the shipped skill
posts, polls and transitions at the agent boundary; these prove that the same
artefacts, read through the receiver's own rules, decide what the recordings
assert.
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from types import ModuleType

import pytest

import pr_readiness_workflow as workflow
from pr_readiness_model import COMPLETENESS, DECLARED_SUBSET, PROOF, WHOLE_PLAN

REPO_ROOT = Path(__file__).resolve().parents[1]
IMPLEMENTATION = REPO_ROOT / "skills" / "sdlc-implementation"
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "readiness-agent-boundary"
SHIM = FIXTURES / "gh-shim.py"

#: Each recorded candidate, the decision the receiver must reach for it, and
#: whether that decision permits the transition. Two rows clear and nine hold,
#: each holding on a rule of its own, so neither a sequence that never opened
#: nor one that never closed can pass.
DECISIONS = (
    ("current-whole-plan", "ready", True),
    # The reply says `clear`, but for a declared subset. Only the subject
    # rule can hold this one, so it is what separates "the verdict is clear"
    # from "the verdict clears the gate".
    ("subset-clear", "completeness-declared-subset-does-not-clear", False),
    # The reply says `not clear` for a declared subset, so the verdict rule
    # decides before the subject rule is reached.
    ("subset-only", "completeness-not-clear", False),
    # The reply is clear for the whole plan, but names the revision it was
    # recorded against as rev-6 while the plan served at this head states
    # rev-7. The decision is made from two reads of the stand-in, so a
    # receiver that took the revision in force from a reply, or the reply's
    # revision from the plan, would agree with itself and pass.
    ("superseded-revision", "completeness-superseded-revision", False),
    # Every check exits zero here, including CodeScene's, which is titled
    # "Issues found" and lists two. Reading the conclusions alone would clear
    # this candidate, so the row is what holds the gate to the finding text.
    ("codescene-advisory", "codescene-not-clear", False),
    # A candidate that changes a proof carries a proof question, so the
    # packet's conditional rule is load-bearing. Both replies here clear and
    # the gate opens, which is what makes the proof rows below a hold rather
    # than a receiver that never reads a proof at all.
    ("combined-plan-and-proof", "ready", True),
    # The proof reply is `pending`, so this holds after the completeness reply
    # has cleared: reading only the first reply would clear it.
    ("combined-proof-pending", "proof-pending", False),
    # The completeness reply is current — it echoes rev-8, which the plan at
    # this head states — while the proof reply echoes rev-7. The hold is the
    # proof's own, so a receiver that reconciled the plan against the first
    # reply it found would clear this one.
    ("combined-proof-stale-plan-revision", "proof-superseded-revision", False),
    # The proof reply is clear and current in revision, but was recorded
    # against another head, so the completeness reply alone is not the gate.
    # This is the row the model's per-assessment candidate binding exists for.
    ("combined-proof-candidate-mismatch", "proof-candidate-mismatch", False),
    # The proof reply names no revision while its request named one, so it
    # echoes only the base/head. That is the unbound form, not a
    # revision-less assignment, and the two are decided by different rules.
    ("combined-proof-unbound-revision", "proof-revision-unbound", False),
    # The premise the runner pins for this one is that only the head is wrong:
    # the proof verdict is clear and names the revision in force. So the hold
    # is its candidate binding, not a stale revision or an unclear verdict.
    ("combined-proof-stale-verdict", "proof-candidate-mismatch", False),
)


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


def handoff_section() -> str:
    """Return the raw handoff section carrying the implementation packet.

    The section is the last in the skill, so it runs to the end of the file
    when no further level-two heading follows it. A section appended below
    would end it instead, and the packet assertions would then be made
    against the handoff alone rather than against whatever came after.
    """
    text = (IMPLEMENTATION / "SKILL.md").read_text(encoding="utf-8")
    opening = "## 4. Hand PR delivery to pr-babysitting\n"
    start = text.index(opening) + len(opening)
    end = text.find("\n## ", start)
    return text[start:] if end == -1 else text[start:end]


#: The packet fields this receiver reads, by the rule each one states. The
#: handoff is the sender's instruction to `pr-babysitting`, so applicability
#: is taken from these lines rather than chosen by this test.
PACKET_FIELDS = {
    "candidate": "Repository, PR, worktree, target, and verified base/head:",
    "plan": "Approved ExecPlan path and revision; accepted scope and tolerances:",
    "assessment": "ExecPlan completeness/correctness assessment:",
    "proof": "Proof-specific assessment:",
}


def handoff_packet() -> dict[str, str]:
    """Return the shipped packet's lines, keyed by the field they state.

    Each value is the whole line, because the line carries both the field and
    the rule it states: `ExecPlan completeness/correctness assessment:` alone
    would say nothing about whether the assessment is required. A field the
    handoff stopped stating raises here, since a packet that lost one leaves
    the receiver inferring a rule from nothing.

    Returns
    -------
    dict
        The packet line for each field this receiver reads.
    """
    lines = handoff_section().splitlines()
    found = {}
    for key, label in PACKET_FIELDS.items():
        line = next(
            (text for text in lines if text.lstrip().startswith(label)), None
        )
        assert line is not None, f"the handoff packet lost its {key} field"
        found[key] = line.strip()
    return found


@pytest.fixture(scope="module")
def packet() -> dict[str, str]:
    """Return the shipped handoff packet, read once per module."""
    return handoff_packet()


def stage(directory: Path, scenario: str) -> Path:
    """Place one scenario's facts beside a runnable stand-in, returning it."""
    shutil.copy2(
        FIXTURES / "scenarios" / scenario / "facts.json",
        directory / "facts.json",
    )
    shim = directory / "gh"
    shutil.copy2(SHIM, shim)
    shim.chmod(0o755)
    return shim


def invoke(shim: Path, *argv: str) -> subprocess.CompletedProcess[str]:
    """Run the stand-in with one read-only invocation.

    The token variables are cleared rather than inherited: a token from the
    ambient shell would make the stand-in serve the posting identity, and a
    rehearsal that reads as the manual-comment account is not the read these
    recordings were made under. Nothing here posts, so no token is needed.
    """
    env = {
        **os.environ,
        "GH_TOKEN": "",
        "GH_CONFIG_DIR": str(shim.parent / "gh-config"),
    }
    return subprocess.run(
        [str(shim), *argv], capture_output=True, text=True, check=False, env=env
    )


def discussion(shim: Path) -> list[dict]:
    """Return the discussion the stand-in serves, through the route a run lists.

    This is the receiver's own read of the thread, not a look at `facts.json`:
    a premise the stand-in would not serve is not one a run could have seen.
    """
    done = invoke(
        shim, "api", "repos/leynos/agent-helper-scripts/issues/272/comments"
    )
    assert done.returncode == 0, done.stderr
    listing = json.loads(done.stdout)
    assert isinstance(listing, list), listing
    return listing


def pr_state(shim: Path) -> dict:
    """Return the PR state the stand-in serves for the scenario it holds."""
    done = invoke(
        shim,
        "pr",
        "view",
        "272",
        "--repo",
        "leynos/agent-helper-scripts",
        "--json",
        "isDraft,headRefOid,baseRefOid,statusCheckRollup",
    )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def plan_file(shim: Path, path: str, ref: str) -> dict:
    """Return the plan file the stand-in serves at the scenario's head."""
    done = invoke(
        shim, "api", f"repos/leynos/agent-helper-scripts/contents/{path}?ref={ref}"
    )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def tagged_requests(listing: list[dict], opening: str) -> list[dict]:
    """Return the tagged requests in a discussion that carry one opening.

    A request is identified by the opening the shipped template preserves and
    by the marker every request must carry, so a comment that merely mentions
    the bot is not mistaken for one.
    """
    return [
        entry
        for entry in listing
        if "@coderabbitai" in str(entry.get("body", ""))
        and SHIM_MODULE.ASSESSMENT_ID.search(str(entry.get("body", "")))
        and opening in str(entry.get("body", ""))
    ]


def completeness_request(listing: list[dict]) -> dict:
    """Return the single tagged completeness request the discussion carries."""
    asked = tagged_requests(listing, "please assess the implementation")
    assert len(asked) == 1, f"the discussion holds {len(asked)} completeness requests"
    return asked[0]


def proof_request(listing: list[dict]) -> dict | None:
    """Return the tagged proof request, or None when the candidate has none."""
    asked = tagged_requests(listing, "are you satisfied that the introduced proof")
    assert len(asked) <= 1, f"the discussion holds {len(asked)} proof requests"
    return asked[0] if asked else None


def field_in(body: str, label: str) -> str:
    """Return the value a reply records for one bolded field.

    The reply format is the recorded one: each field is a bolded label
    followed by its value to the end of the line, as `make_scenarios.reply`
    writes it and the shipped runner reads it. A missing field raises rather
    than yielding an empty value that would silently weaken a case.
    """
    stated = re.search(rf"\*\*{re.escape(label)}:\*\*\s*(.+)", body)
    assert stated, f"the reply states no {label}: {body!r}"
    return stated.group(1).strip()


def answered(listing: list[dict], marker: str) -> dict:
    """Return the bot reply echoing ``marker``, from the served discussion."""
    for entry in listing:
        body = str(entry.get("body", ""))
        if entry.get("user", {}).get("login") != workflow.CODERABBIT:
            continue
        if "**Verdict:" not in body:
            continue
        if field_in(body, "Assessment-ID").strip("`") == marker:
            return entry
    raise AssertionError(f"the discussion holds no reply to {marker!r}")


def verdict_in(body: str) -> str:
    """Return the verdict a reply states, in the model's vocabulary."""
    stated = re.search(r"\*\*Verdict:\s*([^*]+)\*\*", body)
    assert stated, f"the reply states no verdict: {body!r}"
    return stated.group(1).strip().casefold()


def subject_in(body: str) -> str:
    """Return the subject a reply says it assessed, in the model's vocabulary.

    The reference says the `Assessed subject:` line is the whole approved plan
    and that a managed-stack layer records a declared subset instead. The
    reply writes the subject as prose, so this maps the two forms the model
    names and refuses anything else rather than choosing one.
    """
    stated = field_in(body, "Assessed subject").casefold()
    if "declared subset" in stated:
        return DECLARED_SUBSET
    if "whole approved plan" in stated:
        return WHOLE_PLAN
    raise AssertionError(f"unrecognized assessed subject: {stated!r}")


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


def optional_field(body: str, label: str) -> str | None:
    """Return a field's value, or None when the reply omits the field.

    The proof template omits its plan revision when the request named none, so
    a proof reply may legitimately carry no revision at all. Keeping the
    absence distinguishable from an empty string is what lets the recorded
    unbound-revision case fail the binding rule rather than a parse error.
    """
    stated = re.search(rf"\*\*{re.escape(label)}:\*\*\s*(.+)", body)
    return stated.group(1).strip() if stated else None


def named_proofs(reply: str) -> tuple[str, ...]:
    """Return the proofs a proof reply's subject names, as its backticked names.

    A proof verdict's subject is the named proofs it assessed, so the names
    inside backticks on that line are its inventory. This is how the recorded
    replies state it, and the inventory the request asked about is read the
    same way.
    """
    return tuple(re.findall(r"`([^`]+)`", field_in(reply, "Assessed subject")))


def proof_reference(entry: str) -> str:
    """Return the named proof reference from a `path#reference` inventory entry.

    The shipped proof template asks about "proof file paths with named proof
    references", so its inventory entry carries both. The recorded replies
    name the reference alone, which is the same proof and is how the template's
    own subject line asks for it. An entry with no separator is already a
    reference, so it is returned unchanged.
    """
    return entry.rsplit("#", 1)[-1].strip()


def proof_inventory(proof_ask: dict | None) -> tuple[str, ...]:
    """Return the named references the recorded proof question asked about.

    The question's opening is the shipped template's
    `(proof file paths with named proof references)`, filled with the proofs
    the request asks about. That opening is the inventory the request put to
    the assessor, and it is what the reply's subject is compared against. The
    completeness request's `Proof inventory:` line says what the candidate
    affects, which is the same list in another form; reading the question
    keeps one source.
    """
    if proof_ask is None:
        return ()
    opening = re.search(
        r"introduced proof\(s\)\s*\(([^)]*)\)", str(proof_ask["body"])
    )
    assert opening, "the proof request names no inventory"
    return tuple(
        proof_reference(name)
        for name in opening.group(1).split(",")
        if name.strip()
    )


def reply_for(listing: list[dict], request: dict) -> str:
    """Return the recorded reply to one request, by the marker it echoes."""
    body = str(request["body"])
    marker = SHIM_MODULE.ASSESSMENT_ID.search(body)
    assert marker, "the request carries no assessment marker"
    return str(answered(listing, marker.group(1))["body"])


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
    for check in pr.get("statusCheckRollup") or []:
        if "codescene" not in str(check.get("name", "")).casefold():
            continue
        output = check.get("output") or {}
        text = f"{output.get('title', '')} {output.get('summary', '')}"
        reported_clean = "no issues" in text.casefold()
        return reported_clean and str(check.get("conclusion")) == "SUCCESS"
    return False


def observed_reply(
    body: str, marker: str, kind: str, asked_revision: str | None
) -> workflow.Reply:
    """Return the reply a recorded body holds, as the receiver reads it.

    Every field but the assessment's own identity comes from the reply's text.

    The two revision fields are not the same fact. ``plan_revision`` is the
    revision the verdict was recorded against, which is what the reply names,
    or the revision its request asked about when the reply names none: a reply
    cannot have been recorded against a revision its request never put to it.
    ``echoed_revision`` is only what the reply itself states. Keeping them
    apart is what lets a reply that names rev-6 to a request asking rev-7 be
    held as superseded while one that names nothing is held as unbound —
    filling either from the served plan instead would make the receiver agree
    with itself and stale replies would pass.

    A completeness reply's subject is the plan or a declared subset; a proof
    reply's is the named proofs it says it assessed, which is what the
    inventory check compares.

    Parameters
    ----------
    body : str
        The reply's recorded body.
    marker : str
        The marker the reply must echo for the receiver to observe it.
    kind : str
        ``completeness`` or ``proof``, selecting how the subject is read.
    asked_revision : str or None
        The revision the request that prompted this reply named, if any.
    """
    base, head = assessed_candidate(body)
    stated = optional_field(body, "Plan revision")
    if kind == COMPLETENESS:
        subject = subject_in(body)
        proofs: tuple[str, ...] = ()
    else:
        proofs = named_proofs(body)
        subject = field_in(body, "Assessed subject")
    return workflow.Reply(
        assessment_id=marker,
        author=workflow.CODERABBIT,
        base=base,
        head=head,
        verdict=verdict_in(body),
        plan_revision=stated if stated is not None else asked_revision,
        echoed_revision=stated,
        subject=subject,
        proofs=proofs,
    )


def decide(
    scenario: str, tmp_path: Path, packet: dict[str, str]
) -> tuple[workflow.PullRequest, workflow.Readiness]:
    """Run the receiver over one recorded scenario, end to end.

    The receiver is handed the scenario through the stand-in: it lists the
    discussion, reads the plan the completeness request names at the head the
    PR gives, derives its assignment from the handoff packet and the request's
    proof inventory, and decides on the replies the recording holds for the
    markers it found. No candidate value and no reply is written here.

    Parameters
    ----------
    scenario : str
        The scenario directory under `scenarios/`.
    tmp_path : Path
        Directory the run copy and its stand-in are placed in.
    packet : dict
        The shipped handoff packet, whose lines state the applicability rules.

    Returns
    -------
    tuple
        The PR double after the sequence, and its readiness decision.
    """
    shim = stage(tmp_path, scenario)
    listing = discussion(shim)
    request = completeness_request(listing)
    body = str(request["body"])
    marker = SHIM_MODULE.ASSESSMENT_ID.search(body).group(1)
    quoted = re.search(r"^> `([^`]+)`$", body, re.MULTILINE)
    assert quoted, f"{scenario} names no approved plan path"
    proof_ask = proof_request(listing)

    pr = pr_state(shim)
    head = str(pr["headRefOid"])
    content = str(plan_file(shim, quoted.group(1), head).get("content", ""))
    revision = SHIM_MODULE.PLAN_REVISION.search(content)
    assert revision, f"{scenario} serves no plan revision at {head}"

    # The packet conditions the proof assessment; a tagged proof question is
    # the recorded evidence that the assessment was asked for this candidate.
    # Both are needed: the packet says when the assessment applies, and the
    # thread says whether that is now.
    conditional = "required when applicable" in packet["proof"].casefold()
    applied = proof_ask is not None
    pull = workflow.PullRequest(
        base=str(pr["baseRefOid"]),
        head=head,
        is_draft=bool(pr["isDraft"]),
        ci_green=all(state == "SUCCESS" for state in checks(pr).values()),
        codescene_clear=codescene_clear(pr),
        approved_plan_revision=revision.group(1),
        required_proofs=proof_inventory(proof_ask),
    )
    proof_marker = (
        SHIM_MODULE.ASSESSMENT_ID.search(str(proof_ask["body"])).group(1)
        if proof_ask
        else "unused-proof-marker"
    )
    assignment = workflow.Assignment(
        completeness_id=marker,
        proof_id=proof_marker,
        completeness_applies="required" in packet["assessment"].casefold(),
        proof_applies=conditional and applied,
    )

    in_force = pull.approved_plan_revision
    thread = workflow.Discussion(base=pull.base, head=pull.head)
    thread.responses.append(
        observed_reply(reply_for(listing, request), marker, COMPLETENESS, in_force)
    )
    if proof_ask is not None:
        # The template writes the revision beside the plan's blob SHA on one
        # line, so the identifier is read with the stand-in's own expression
        # rather than taken as the whole field.
        asked = SHIM_MODULE.PLAN_REVISION.search(str(proof_ask["body"]))
        thread.responses.append(
            observed_reply(
                reply_for(listing, proof_ask),
                proof_marker,
                PROOF,
                asked.group(1) if asked else None,
            )
        )
    return pull, workflow.assess_and_maybe_mark_ready(pull, thread, assignment)


@pytest.mark.parametrize(("scenario", "reason", "ready"), DECISIONS)
def test_the_receiver_decides_each_recorded_case(
    scenario: str,
    reason: str,
    ready: bool,
    tmp_path: Path,
    packet: dict[str, str],
) -> None:
    """The handoff and the boundary recording agree on every deciding input.

    Each row names both the decision it must reach and the rule that has to
    reach it. Pinning the reason rather than only the outcome is what keeps
    the rows apart: several of them hold, and a receiver that confused a
    declared subset with an unclear verdict, or a stale revision with an
    omitted one, would still hold every one of them while deciding them for
    the wrong reason. The two permitting rows assert the transition, so a
    sequence that read no reply at all cannot pass them.
    """
    pull, decision = decide(scenario, tmp_path, packet)

    assert decision.reason == reason, (
        f"{scenario} decided {decision.reason!r}, not {reason!r}"
    )
    assert decision.ready is ready, (
        f"{scenario} reported ready={decision.ready}"
    )
    if ready:
        assert pull.ready_transitions == [pull.head], (
            f"{scenario} recorded {pull.ready_transitions}"
        )
    else:
        assert pull.ready_transitions == [], (
            f"{scenario} transitioned to {pull.ready_transitions}"
        )


def test_the_receiver_reads_its_applicability_from_the_handoff(
    packet: dict[str, str],
) -> None:
    """The assignment is the packet's, so the packet cannot quietly stop saying it.

    `decide` derives both flags from these lines. If the completeness line
    stopped saying `required`, the receiver would record an inapplicable
    assessment and the whole-plan case would clear without reading a reply at
    all, so the lines are asserted on their own as well as through it.
    """
    assessment = packet["assessment"].casefold()
    assert "required" in assessment, (
        "the handoff no longer requires a completeness assessment"
    )
    assert "whole approved plan" in assessment, (
        "the handoff no longer names the whole approved plan as the subject"
    )
    assert "required when applicable" in packet["proof"].casefold(), (
        "the handoff no longer conditions the proof assessment"
    )
