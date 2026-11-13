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


def changed_paths(shim: Path) -> list[str]:
    """Return the candidate's changed paths, through the route a run reads.

    The diff is read from the stand-in rather than from `facts.json` for the
    same reason the discussion is: a premise the stand-in would not serve is
    not one a run could have seen. `gh pr diff --name-only` prints one path per
    line, so the read is the same text a receiver would parse.
    """
    done = invoke(
        shim, "pr", "diff", "272", "--repo", "leynos/agent-helper-scripts",
        "--name-only",
    )
    assert done.returncode == 0, done.stderr
    return [line for line in done.stdout.splitlines() if line.strip()]


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


#: The opening the shipped proof template preserves.
PROOF_OPENING = "are you satisfied that the introduced proof"


def proof_request(listing: list[dict]) -> dict | None:
    """Return the tagged proof request, or None when the candidate has none."""
    asked = tagged_requests(listing, PROOF_OPENING)
    assert len(asked) <= 1, f"the discussion holds {len(asked)} proof requests"
    return asked[0] if asked else None


#: The line the completeness request records its affected-proof inventory on.
#: The shipped template asks the sender for it, and `none affected` is the
#: recorded form of an empty inventory.
PROOF_INVENTORY = re.compile(r"^Proof inventory:[^\n]*", re.MULTILINE)


def recorded_reference(directory: Path) -> str:
    """Return the named proof reference the recording says its candidate carries.

    `proof_path` names the file; the inventory a reply is compared against
    names the reference inside it. The recording carries both, so the diff and
    the inventory are reconciled by the identity the recording was made under
    rather than by a second guess from the path's spelling.

    Parameters
    ----------
    directory : Path
        The run copy holding the facts `decide` serves.

    Returns
    -------
    str
        The reference the recording's proof is assessed under.
    """
    facts = json.loads((directory / "facts.json").read_text(encoding="utf-8"))
    return proof_reference(str(facts["proof_reference"]))


def stated_proofs(
    inventory: tuple[str, ...], changed: bool, reference: str
) -> tuple[str, ...]:
    """Return the inventory a proof assessment must actually cover.

    Applicability and coverage are two facts that have to agree. The diff says
    the assessment applies; the inventory says what the reply will be compared
    against. An inventory that owes nothing to a changed proof — it names some
    other proof, or names none — would let a clear reply for that other proof
    discharge an assessment of the proof the candidate changed, so the changed
    proof is added to what the reply must cover.

    The addition is one-way. A non-empty inventory that already names the
    changed proof is left exactly as recorded, and an empty inventory over an
    unchanged candidate stays empty: the join only ever adds the proof the
    diff actually carries.

    Parameters
    ----------
    inventory : tuple of str
        The proofs the request's inventory names.
    changed : bool
        Whether the candidate's diff changes the proof the recording names.
    reference : str
        The named reference the recording's proof is assessed under.

    Returns
    -------
    tuple of str
        The inventory the reply's subject is compared against.
    """
    if not changed:
        return inventory
    return tuple(dict.fromkeys((*inventory, reference)))


def affects_a_proof(body: str) -> bool:
    """Return whether a completeness request says the candidate affects a proof.

    The sender records the candidate's affected-proof inventory on the
    `Proof inventory:` line, which is the handoff's own statement of what the
    proof assessment would be about. An inventory that says `none affected` is
    empty; one that names proofs is not. A request carrying no such line
    establishes nothing, and is read as neither.

    This is the secondary read, and it can only *add* applicability. The
    candidate's diff is the primary evidence, so an inventory that names a
    proof the diff does not carry still makes the assessment apply, while an
    inventory that says `none affected` over a changed proof cannot unmake it.
    A sender that writes that sentence over its own changed proof has recorded
    a contradiction, and taking the sentence as authoritative is what let a
    proof-changing candidate clear on the completeness reply alone.

    The proof question is a different fact again. It says the assessment was
    asked for, not whether it applies: a candidate that changes a proof and
    never has its question posted is a candidate with a missing assessment.
    Reading applicability from the question alone made that state look
    inapplicable, which cleared the gate on the completeness reply.

    Parameters
    ----------
    body : str
        The completeness request's recorded body.

    Returns
    -------
    bool
        Whether the recorded inventory names at least one affected proof.
    """
    stated = PROOF_INVENTORY.search(body)
    if stated is None:
        return False
    return "none affected" not in stated.group(0).casefold()


def recorded_proof(directory: Path) -> str:
    """Return the proof the recording says its candidate carries.

    A GitHub diff names files, not what they are: whether a changed path is a
    proof under assessment is a fact about the candidate's own inventory of
    proofs, and the shipped contract says to inspect symbols and verifier
    configuration rather than decide by filenames. So the identity comes from
    the recording's `proof_path`, and the diff says only whether that file is
    among the changed ones. The runner compares a run's `none affected`
    against the same premise, so applicability here is decided against the
    identity the recording was made under rather than against a second guess
    from the path's spelling.

    Parameters
    ----------
    directory : Path
        The run copy holding the facts `decide` serves.

    Returns
    -------
    str
        The repository-relative proof path the recording names.
    """
    facts = json.loads((directory / "facts.json").read_text(encoding="utf-8"))
    return str(facts["proof_path"])


def changes_a_proof(changed: list[str], proof: str) -> bool:
    """Return whether the candidate's own diff carries the proof it names.

    Parameters
    ----------
    changed : list of str
        The paths the candidate changes, as its diff reports them.
    proof : str
        The repository-relative proof path the recording names.

    Returns
    -------
    bool
        Whether that proof is among the changed paths.
    """
    return bool(proof) and proof in changed


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


def proof_inventory(
    proof_ask: dict | None, completeness_body: str
) -> tuple[str, ...]:
    """Return the named proof references this candidate's inventory holds.

    The completeness request's `Proof inventory:` line is the sender's own
    statement of what the candidate affects, and it is available whether or
    not the proof question was ever posted. A missing question is a missing
    assessment, not a missing inventory, so the line is what a pending proof
    assessment is pending *about*. Reading the question alone made the two
    facts the same one: a proof-changing candidate with no question had no
    inventory either, and the gate then held on `proof-inventory-empty`
    rather than on the unanswered assessment.

    A proof-only assignment has no completeness request to carry that line, so
    its inventory comes from the question's opening, which is the shipped
    template's `(proof file paths with named proof references)`, filled with
    the proofs the request asks about.

    Parameters
    ----------
    proof_ask : dict or None
        The recorded proof question, when the discussion has one.
    completeness_body : str
        The completeness request's body, whose `Proof inventory:` line names
        the affected proofs.

    Returns
    -------
    tuple of str
        The named references the reply's subject is compared against.
    """
    stated = PROOF_INVENTORY.search(completeness_body)
    if stated is not None:
        listed = stated.group(0)
        if "none affected" in listed.casefold():
            return ()
        # Each entry is a backticked path and a backticked reference; the path
        # contains a separator and the reference does not, so the references
        # are the backticked names without one.
        named = tuple(
            name for name in re.findall(r"`([^`]+)`", listed) if "/" not in name
        )
        if named:
            return named
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
    scenario: str,
    tmp_path: Path,
    packet: dict[str, str],
    served: dict | None = None,
) -> tuple[workflow.PullRequest, workflow.Readiness]:
    """Run the receiver over one recorded scenario, end to end.

    The receiver is handed the scenario through the stand-in: it lists the
    discussion, reads the plan the completeness request names at the head the
    PR gives, reads the candidate's changed paths, derives its assignment from
    the handoff packet, that diff and the request's proof inventory, and
    decides on the replies the recording holds for the markers it found. No
    candidate value and no reply is written here.

    Parameters
    ----------
    scenario : str
        The scenario directory under `scenarios/`.
    tmp_path : Path
        Directory the run copy and its stand-in are placed in.
    packet : dict
        The shipped handoff packet, whose lines state the applicability rules.
    served : dict, optional
        Facts to serve instead of the scenario's own, for a case that removes
        one premise from a recording. They are written before the stand-in
        reads anything, so the receiver sees the altered premise rather than
        the file it was altered from.

    Returns
    -------
    tuple
        The PR double after the sequence, and its readiness decision.
    """
    shim = stage(tmp_path, scenario)
    if served is not None:
        (tmp_path / "facts.json").write_text(
            json.dumps(served), encoding="utf-8"
        )
    listing = discussion(shim)
    proof_ask = proof_request(listing)
    request = completeness_request(listing)
    body = str(request["body"])
    marker = SHIM_MODULE.ASSESSMENT_ID.search(body).group(1)
    quoted = re.search(r"^> `([^`]+)`$", body, re.MULTILINE)
    assert quoted, f"{scenario} names no approved plan path"

    pr = pr_state(shim)
    head = str(pr["headRefOid"])
    content = str(plan_file(shim, quoted.group(1), head).get("content", ""))
    revision = SHIM_MODULE.PLAN_REVISION.search(content)
    assert revision, f"{scenario} serves no plan revision at {head}"

    # The packet conditions the proof assessment, and two independent reads
    # decide whether the condition is met. The candidate's own diff is the
    # primary evidence: a change to the proof the recording names affects it
    # whatever any request says about it. The completeness request's
    # `Proof inventory:` line can only add applicability, by naming a proof the
    # diff does not carry; it can never take it away, because a sender that
    # writes `none affected` over a changed proof has contradicted its own
    # diff, and reading that sentence as authoritative is what let a
    # proof-changing candidate clear on the completeness reply alone.
    #
    # A tagged proof question is not applicability evidence in either
    # direction. It says the question was posted, so reading applicability from
    # it made a proof-changing candidate with no question look inapplicable.
    # The question is the assessment, not the condition.
    conditional = "required when applicable" in packet["proof"].casefold()
    changed = changes_a_proof(changed_paths(shim), recorded_proof(tmp_path))
    affected = changed or affects_a_proof(body)
    # Applicability and coverage are reconciled, so an inventory that names
    # some other proof cannot discharge the assessment the diff requires. The
    # reply must cover the changed proof whether or not the sender listed it.
    pull = workflow.PullRequest(
        base=str(pr["baseRefOid"]),
        head=head,
        is_draft=bool(pr["isDraft"]),
        ci_green=all(state == "SUCCESS" for state in checks(pr).values()),
        codescene_clear=codescene_clear(pr),
        approved_plan_revision=revision.group(1),
        required_proofs=stated_proofs(
            proof_inventory(proof_ask, body),
            changed,
            recorded_reference(tmp_path),
        ),
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
        proof_applies=conditional and affected,
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
    tmp_path: Path,
) -> None:
    """The assignment is the packet's, so the packet cannot quietly stop saying it.

    `decide` derives both flags from these lines. If the completeness line
    stopped saying `required`, the receiver would record an inapplicable
    assessment and the whole-plan case would clear without reading a reply at
    all, so the lines are asserted on their own as well as through it.

    Asserting the shipped wording alone would leave one direction open: a
    `decide` that hard-coded either flag would agree with the wording it read
    and pass. The rest of the test therefore hands the receiver a packet with
    one line withdrawn at a time. The declared subset, which holds under the
    shipped packet, clears once the completeness line says the assessment is
    optional; the pending proof reply clears once the proof line says the
    assessment is unconditional. Each run differs from the shipped one in that
    line alone, so neither can pass by reading a constant.
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

    # Still names the whole plan, so the subject claim is untouched; only the
    # requirement is withdrawn, which is the flag `decide` reads.
    withdrawn = {
        **packet,
        "assessment": packet["assessment"].replace(
            "required against the whole approved plan",
            "optional against the declared PR scope",
        ),
    }
    assert withdrawn["assessment"] != packet["assessment"]
    pull, decision = decide("subset-clear", tmp_path, withdrawn)
    assert decision.ready is True, (
        "a withdrawn completeness assessment still held the gate"
    )
    assert pull.ready_transitions == [pull.head]

    # The same direction for the proof line: with the condition withdrawn, the
    # pending proof reply no longer holds the gate. A receiver that had fixed
    # the condition true would still hold this one.
    unconditional = {
        **packet,
        "proof": packet["proof"].replace(
            "required when applicable", "optional"
        ),
    }
    assert unconditional["proof"] != packet["proof"]
    pull, decision = decide("combined-proof-pending", tmp_path, unconditional)
    assert decision.ready is True, (
        "a withdrawn proof assessment still held the gate"
    )
    assert pull.ready_transitions == [pull.head]


def test_the_receiver_reads_applicability_from_the_inventory_not_the_question(
    tmp_path: Path,
    packet: dict[str, str],
) -> None:
    """A required question that was never posted is pending, not inapplicable.

    `combined-plan-and-proof` clears with both questions answered. Remove the
    proof question from its discussion and the candidate is unchanged: the same
    proof file is in the diff and the completeness request still records it on
    its `Proof inventory:` line. Applicability cannot come from the question's
    presence, because that would make the missing assessment the reason the
    assessment does not apply — the gate would open on the completeness reply
    alone, which is exactly the state the proof gate exists to refuse.

    The control is the negative case: the same removal from a scenario whose
    inventory says `none affected` still clears, so the test is about the
    inventory and not about deleting a comment.
    """
    # A proof-changing candidate whose proof question was never posted.
    asked = tmp_path / "asked"
    asked.mkdir()
    shim = stage(asked, "combined-plan-and-proof")
    comments = listing_comments(asked)
    without_question = [
        entry for entry in comments if not proof_request([entry])
    ]
    assert len(without_question) < len(comments), "the scenario asks no proof question"
    facts = json.loads((asked / "facts.json").read_text(encoding="utf-8"))
    facts["api"][r"/issues/\d+/comments"] = without_question
    assert affects_a_proof(str(completeness_request(without_question)["body"])), (
        "the inventory no longer records an affected proof"
    )
    pull, decision = decide("combined-plan-and-proof", asked, packet, facts)
    assert decision.reason == "proof-pending", (
        f"a missing required proof question decided {decision.reason!r}"
    )
    assert pull.ready_transitions == []

    # The control: the same removal where the inventory says none affected.
    empty = tmp_path / "empty"
    empty.mkdir()
    stage(empty, "current-whole-plan")
    empty_facts = json.loads((empty / "facts.json").read_text(encoding="utf-8"))
    assert not affects_a_proof(
        str(completeness_request(empty_facts["api"][r"/issues/\d+/comments"])["body"])
    ), "the control scenario no longer records an empty inventory"
    pull, decision = decide("current-whole-plan", empty, packet)
    assert decision.ready is True, (
        "an empty inventory did not clear without a proof question"
    )
    assert pull.ready_transitions == [pull.head]


def test_an_inventory_naming_a_proof_the_diff_omits_still_applies(
    tmp_path: Path,
    packet: dict[str, str],
) -> None:
    """The inventory can add an assessment the diff alone would not require.

    The two reads are not symmetric. The diff decides a change to a proof it
    carries; the inventory decides a sender's claim about a proof the diff does
    not carry. `current-whole-plan` changes only the plan and records
    `none affected`, and it clears. Give it the combined scenario's inventory —
    naming `refinement_sound`, which its own diff does not touch — and it must
    stop clearing: the sender has said a proof is affected, so the assessment
    applies and its missing reply holds the gate. A receiver that read only the
    diff would clear this candidate, and the sentence would be ignored in the
    one direction it is allowed to speak.

    This is the case that separates the two reads. The test above holds a
    candidate whose diff decides; this one holds a candidate whose inventory
    decides while its diff does not.
    """
    claim = tmp_path / "claim"
    claim.mkdir()
    shim = stage(claim, "current-whole-plan")
    proof = recorded_proof(claim)
    reference = recorded_reference(claim)
    assert not changes_a_proof(changed_paths(shim), proof), (
        "the scenario now changes the proof it names"
    )

    def decided(
        name: str, line: str
    ) -> tuple[workflow.PullRequest, workflow.Readiness, dict]:
        """Serve this scenario with one `Proof inventory:` line, and decide."""
        directory = tmp_path / name
        directory.mkdir()
        stage(directory, "current-whole-plan")
        facts = json.loads((directory / "facts.json").read_text(encoding="utf-8"))
        facts["api"][r"/issues/\d+/comments"] = [
            {**entry, "body": PROOF_INVENTORY.sub(line, str(entry["body"]))}
            for entry in facts["api"][r"/issues/\d+/comments"]
        ]
        pull, decision = decide("current-whole-plan", directory, packet, facts)
        return pull, decision, facts

    # The ladder the README states: the scenario's own empty inventory clears,
    # an absent line clears, and only a line naming a proof its diff does not
    # carry holds. Each step changes the line and nothing else.
    empty = tmp_path / "empty"
    empty.mkdir()
    stage(empty, "current-whole-plan")
    facts = json.loads((empty / "facts.json").read_text(encoding="utf-8"))
    assert not affects_a_proof(
        str(completeness_request(facts["api"][r"/issues/\d+/comments"])["body"])
    ), "the scenario no longer records an empty inventory"
    pull, decision = decide("current-whole-plan", empty, packet)
    assert decision.ready is True, (
        f"the empty-inventory control decided {decision.reason!r}"
    )
    assert pull.ready_transitions == [pull.head], (
        f"the empty-inventory control recorded {pull.ready_transitions}"
    )

    pull, decision, absent = decided("absent", "")
    assert not affects_a_proof(
        str(completeness_request(absent["api"][r"/issues/\d+/comments"])["body"])
    ), "the removed inventory still records an affected proof"
    assert decision.ready is True, (
        f"the absent-line control decided {decision.reason!r}"
    )
    assert pull.ready_transitions == [pull.head], (
        f"the absent-line control recorded {pull.ready_transitions}"
    )

    pull, decision, named = decided(
        "named", f"Proof inventory: `{proof}` (`{reference}`)."
    )
    assert affects_a_proof(
        str(completeness_request(named["api"][r"/issues/\d+/comments"])["body"])
    ), "the altered inventory names no proof"
    assert decision.ready is False, (
        "an inventory naming an affected proof cleared without its assessment"
    )
    assert pull.ready_transitions == [], (
        f"the candidate transitioned to {pull.ready_transitions}"
    )
    assert decision.reason == "proof-pending", (
        f"the candidate decided {decision.reason!r}, not 'proof-pending'"
    )


def test_the_receiver_reads_applicability_from_the_diff_the_inventory_cannot_undo(
    tmp_path: Path,
    packet: dict[str, str],
) -> None:
    """A changed proof makes the assessment apply whatever the inventory says.

    The diff is the candidate's own evidence: `combined-plan-and-proof` changes
    `proofs/refinement/Theorem.lean`, so the proof assessment applies to it.
    Rewrite that candidate's `Proof inventory:` line to `none affected` and
    remove its proof question, and the candidate is still the same one — the
    same proof is in its diff. An inventory read as authoritative would take
    the assessment out of scope on the sender's word, so the candidate would
    clear on the completeness reply alone with no proof reply at all, which is
    exactly the transition the proof gate exists to refuse. The inventory is
    the sender's statement of what it affects; it can name a proof the diff
    does not carry, and it cannot deny one the diff does.

    The control is `current-whole-plan`, which changes no proof and records the
    same empty inventory: it must still clear without a proof question, so the
    hold above is the diff and not the sentence.
    """
    # A proof-changing candidate whose inventory denies the proof it changes.
    denied = tmp_path / "denied"
    denied.mkdir()
    shim = stage(denied, "combined-plan-and-proof")
    proof = recorded_proof(denied)
    assert changes_a_proof(changed_paths(shim), proof), (
        "the scenario no longer changes the proof it names"
    )
    facts = json.loads((denied / "facts.json").read_text(encoding="utf-8"))
    comments = [
        entry for entry in facts["api"][r"/issues/\d+/comments"]
        if not proof_request([entry])
    ]
    assert len(comments) < len(facts["api"][r"/issues/\d+/comments"]), (
        "the scenario asks no proof question"
    )
    for entry in comments:
        entry["body"] = PROOF_INVENTORY.sub(
            "Proof inventory: none affected.", str(entry["body"])
        )
    facts["api"][r"/issues/\d+/comments"] = comments
    assert not affects_a_proof(str(completeness_request(comments)["body"])), (
        "the altered inventory still records an affected proof"
    )
    pull, decision = decide("combined-plan-and-proof", denied, packet, facts)
    assert decision.ready is False, (
        "a proof-changing candidate cleared with its inventory denying the proof"
    )
    assert pull.ready_transitions == [], (
        f"the candidate transitioned to {pull.ready_transitions}"
    )
    # The diff is what applies, and it is what the reply must cover: with the
    # inventory denying it, the changed proof is added back to the inventory,
    # so the hold is the unanswered assessment of that proof rather than a
    # request that named no subject at all.
    assert decision.reason == "proof-pending", (
        f"the candidate decided {decision.reason!r}, not 'proof-pending'"
    )

    # The control: no changed proof, the same empty inventory, and it clears.
    control = tmp_path / "control"
    control.mkdir()
    control_shim = stage(control, "current-whole-plan")
    assert not changes_a_proof(
        changed_paths(control_shim), recorded_proof(control)
    ), "the control scenario now changes the proof it names"
    pull, decision = decide("current-whole-plan", control, packet)
    assert decision.ready is True, (
        f"the control decided {decision.reason!r} without a proof question"
    )
    assert pull.ready_transitions == [pull.head], (
        f"the control recorded {pull.ready_transitions}"
    )


def test_a_non_empty_inventory_naming_another_proof_cannot_cover_the_change(
    tmp_path: Path,
    packet: dict[str, str],
) -> None:
    """The reply must cover the proof the candidate changed, not a nearby one.

    Applicability and coverage are two facts a candidate can make disagree.
    `combined-plan-and-proof` changes `refinement_sound` and asks about it.
    Rename the proof throughout the served recording — inventory, question and
    answer alike — to `other_sound`, and every part of the sender's side is
    consistent about a proof the candidate does not carry. The diff is
    unchanged, so the assessment still applies; but an inventory that owes
    nothing to the changed proof would let that clean verdict on `other_sound`
    discharge the assessment of `refinement_sound`, and the candidate would
    leave draft with the changed proof unassessed.

    Reconciling the diff with the inventory adds the changed proof to what the
    reply must cover, so the clean verdict naming only `other_sound` is
    incomplete rather than clear. The `current-whole-plan` control changes no
    proof at all: the same rename there leaves the inventory the whole story,
    and the clean verdict on the renamed proof clears the gate. The hold above
    is therefore the changed proof, not the name.
    """
    # A proof-changing candidate whose whole recording names another proof.
    renamed = tmp_path / "renamed"
    renamed.mkdir()
    shim = stage(renamed, "combined-plan-and-proof")
    proof = recorded_proof(renamed)
    reference = recorded_reference(renamed)
    assert changes_a_proof(changed_paths(shim), proof), (
        "the scenario no longer changes the proof it names"
    )
    assert reference and reference != "other_sound", (
        f"the recording's reference is {reference!r}, so the rename is a no-op"
    )
    facts = json.loads((renamed / "facts.json").read_text(encoding="utf-8"))
    facts["api"][r"/issues/\d+/comments"] = [
        {
            **entry,
            "body": str(entry["body"]).replace(reference, "other_sound"),
        }
        for entry in facts["api"][r"/issues/\d+/comments"]
    ]
    stripped = [
        entry for entry in facts["api"][r"/issues/\d+/comments"]
        if "please assess the implementation" in str(entry["body"])
    ]
    assert stripped, "the renamed discussion holds no completeness request"
    assert reference not in str(stripped[0]["body"]), (
        "the renamed inventory still names the changed proof"
    )
    pull, decision = decide("combined-plan-and-proof", renamed, packet, facts)
    assert decision.ready is False, (
        "a clean verdict on another proof cleared the changed proof's assessment"
    )
    assert pull.ready_transitions == [], (
        f"the candidate transitioned to {pull.ready_transitions}"
    )
    assert decision.reason == "proof-inventory-incomplete", (
        f"the candidate decided {decision.reason!r}, not"
        " 'proof-inventory-incomplete'"
    )

    # The control: the same rename on a candidate that changes no proof.
    control = tmp_path / "renamed-control"
    control.mkdir()
    control_shim = stage(control, "current-whole-plan")
    assert not changes_a_proof(
        changed_paths(control_shim), recorded_proof(control)
    ), "the control scenario now changes the proof it names"
    control_facts = json.loads(
        (control / "facts.json").read_text(encoding="utf-8")
    )
    control_facts["api"][r"/issues/\d+/comments"] = [
        {
            **entry,
            "body": str(entry["body"]).replace(reference, "other_sound"),
        }
        for entry in control_facts["api"][r"/issues/\d+/comments"]
    ]
    control_body = str(
        completeness_request(
            control_facts["api"][r"/issues/\d+/comments"]
        )["body"]
    )
    assert not affects_a_proof(control_body), (
        "the control's inventory no longer records an empty inventory"
    )
    pull, decision = decide(
        "current-whole-plan", control, packet, control_facts
    )
    assert decision.ready is True, (
        f"the control decided {decision.reason!r} without a proof assessment"
    )
    assert pull.ready_transitions == [pull.head], (
        f"the control recorded {pull.ready_transitions}"
    )


def listing_comments(directory: Path) -> list[dict]:
    """Return the discussion the scenario's own facts record, unfiltered."""
    facts = json.loads((directory / "facts.json").read_text(encoding="utf-8"))
    return list(facts["api"][r"/issues/\d+/comments"])
