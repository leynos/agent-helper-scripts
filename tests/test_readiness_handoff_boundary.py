"""Read the implementation handoff through the readiness boundary end to end.

These cases start from the two shipped artefacts the receiver actually reads:
the handoff packet in `sdlc-implementation`, and a rehearsal scenario served
through the shipped `gh` stand-in. The candidate, the approved revision, the
request, the reply and the CI and CodeScene state all come from those bytes,
so a handoff or a premise that changes shape moves these cases with it.

No policy is decided here. `observe` reads a scenario through the stand-in
and abstracts it into the facts of one frozen snapshot of the FizzBee
readiness model: which assessments the packet and the diff make applicable,
what each thread holds, and whether the delivery gates hold. Whether those
facts permit the transition is looked up in the model-checked snapshot tables
of `specs/pr-readiness/suite.toml`, which `make model-check` verifies. Each
recording also has a row of its own there, so the test fails when a recording
and its row drift apart, and it compares the answer with what the recorded
agent actually did.

The abstraction is the concrete-to-abstract mapping for snapshots: a commit
identifier becomes "the current candidate" or "another one", a revision
becomes "in force" or "superseded", and a reply becomes one of the model's
reply shapes. It is an adapter, and its direction is one way.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

import pytest

from pr_readiness_spec_support import (
    SNAPSHOT_DEFAULTS,
    checked_expectation,
    snapshot_rows,
)
from readiness_applicability import (
    PROOF_INVENTORY,
    affects_a_proof,
    applicability as applicability_of,
    changes_a_proof,
    proof_inventory,
    proof_reference,
)
from readiness_policy import stated_proofs
from readiness_snapshot_support import (
    COMPLETENESS,
    FIXTURES,
    PROOF,
    REPO_ROOT,
    SHIM,
    SHIM_MODULE,
    Bounds,
    thread_state,
)

#: The routine snapshot tables an observation may be looked up in.
CHECKED_TABLES = ("fixture-snapshots", "snapshot-regression-table")

IMPLEMENTATION = REPO_ROOT / "skills" / "sdlc-implementation"


@dataclass(frozen=True)
class Recording:
    """One agent-boundary recording, the fact that decides it, and its outcome."""

    name: str
    deciding: dict[str, str]
    expect: str

#: Each recorded candidate, the fact that decides it, and what the model
#: expects of it. Two rows clear and nine hold, each holding on a fact of its
#: own, so neither a model that never opened nor one that never closed can
#: pass, and an adapter that confused two shortfalls abstracts the wrong row.
DECISIONS = (
    Recording("current-whole-plan", {"completeness": "current:sound-clear"}, "ready"),
    # The reply says `clear`, but for a declared subset. Only the subject
    # separates "the verdict is clear" from "the verdict clears the gate".
    Recording("subset-clear", {"completeness": "current:subset-clear"}, "draft"),
    # The reply says `not clear` for a declared subset; the verdict decides.
    Recording("subset-only", {"completeness": "current:not-clear"}, "draft"),
    # The reply is clear for the whole plan, but names rev-6 while the plan
    # served at this head states rev-7. The abstraction is made from two reads
    # of the stand-in, so a receiver that took the revision in force from a
    # reply, or the reply's revision from the plan, would agree with itself.
    Recording("superseded-revision", {"completeness": "current:superseded-revision-echo"}, "draft"),
    # Every check exits zero here, including CodeScene's, which is titled
    # "Issues found" and lists two. Reading the conclusions alone would clear
    # this candidate, so the row is what holds the gate to the finding text.
    Recording("codescene-advisory", {"hosted": "findings"}, "draft"),
    # A candidate that changes a proof carries a proof question. Both replies
    # clear here, which is what makes the proof rows below a hold rather than
    # a receiver that never reads a proof at all.
    Recording("combined-plan-and-proof", {"proof": "current:sound-clear"}, "ready"),
    # The proof reply is `pending`: an acknowledgement, not an answer.
    Recording("combined-proof-pending", {"proof": "current:acknowledgement"}, "draft"),
    # The completeness reply is current while the proof request and its reply
    # name the superseded revision. The hold is the proof's own.
    Recording("combined-proof-stale-plan-revision", {"proof": "superseded-revision:sound-clear"}, "draft"),
    # The proof reply is clear and current in revision, but was recorded
    # against another head.
    Recording("combined-proof-candidate-mismatch", {"proof": "current:other-candidate"}, "draft"),
    # The proof reply names no revision while its request named one.
    Recording("combined-proof-unbound-revision", {"proof": "current:no-revision-echo"}, "draft"),
    # Only the head is wrong: the proof verdict is clear and names the
    # revision in force.
    Recording("combined-proof-stale-verdict", {"proof": "current:other-candidate"}, "draft"),
)


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


def recorded_reference(directory: Path) -> str:
    """Return the named proof reference the recording says its candidate carries.

    `proof_path` names the file; the inventory a reply is compared against
    names the reference inside it. The recording carries both, so the diff and
    the inventory are reconciled by the identity the recording was made under
    rather than by a second guess from the path's spelling.

    Parameters
    ----------
    directory : Path
        The run copy holding the facts `observe` serves.

    Returns
    -------
    str
        The reference the recording's proof is assessed under.
    """
    facts = json.loads((directory / "facts.json").read_text(encoding="utf-8"))
    return proof_reference(str(facts["proof_reference"]))


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
        The run copy holding the facts `observe` serves.

    Returns
    -------
    str
        The repository-relative proof path the recording names.
    """
    facts = json.loads((directory / "facts.json").read_text(encoding="utf-8"))
    return str(facts["proof_path"])


@dataclass(frozen=True)
class Staged:
    """One scenario served through a copy of the stand-in, and its first reads.

    ``directory`` holds the copy and the facts it serves; ``listing`` is the
    discussion, ``pr`` the PR state, and the two requests are the tagged
    completeness and proof questions found in that discussion.
    """

    shim: Path
    directory: Path
    listing: list[dict]
    pr: dict
    completeness: dict
    proof: dict | None

    @property
    def body(self) -> str:
        """Return the completeness request's body."""
        return str(self.completeness["body"])

    def proof_changed(self) -> bool:
        """Return whether the candidate's own diff changes the recorded proof."""
        return changes_a_proof(changed_paths(self.shim), recorded_proof(self.directory))


def staged(scenario: str, directory: Path, served: dict | None) -> Staged:
    """Serve a scenario, or substituted facts, and make the first reads."""
    shim = stage(directory, scenario)
    if served is not None:
        (directory / "facts.json").write_text(json.dumps(served), encoding="utf-8")
    listing = discussion(shim)
    return Staged(
        shim=shim,
        directory=directory,
        listing=listing,
        pr=pr_state(shim),
        completeness=completeness_request(listing),
        proof=proof_request(listing),
    )


def bounds_of(scenario: str, served: Staged) -> Bounds:
    """Return the candidate the PR reports, its revision in force, and its proofs.

    The revision is read from the plan the completeness request names, at the
    head the PR gives. Applicability and coverage are reconciled, so an
    inventory that names some other proof cannot discharge the assessment the
    diff requires: the reply must cover the changed proof whether or not the
    sender listed it.
    """
    quoted = re.search(r"^> `([^`]+)`$", served.body, re.MULTILINE)
    assert quoted, f"{scenario} names no approved plan path"
    head = str(served.pr["headRefOid"])
    content = str(plan_file(served.shim, quoted.group(1), head).get("content", ""))
    revision = SHIM_MODULE.PLAN_REVISION.search(content)
    assert revision, f"{scenario} serves no plan revision at {head}"
    required = stated_proofs(
        proof_inventory(served.proof, served.body),
        served.proof_changed(),
        recorded_reference(served.directory),
    )
    return Bounds(str(served.pr["baseRefOid"]), head, revision.group(1), required)


def applicability(served: Staged, packet: dict[str, str]) -> tuple[bool, bool, bool]:
    """Return the three applicability answers for a staged recording.

    The rule is the policy unit's; the packet states no derivation, so the
    original-issue assessment is not applicable to a recording.
    """
    return applicability_of(packet, served.body, served.proof_changed())


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


def delivery(served: Staged) -> dict[str, str]:
    """Return the CI, hosted CodeScene and local CodeScene facts served."""
    recorded = json.loads((served.directory / "facts.json").read_text(encoding="utf-8"))
    local = {"clean": "clear", "finding": "findings"}.get(
        str(recorded.get("cs_mode")), "unavailable"
    )
    green = all(state == "SUCCESS" for state in checks(served.pr).values())
    return {
        "ci": "green" if green else "red",
        "hosted": "clear" if codescene_clear(served.pr) else "findings",
        "local": local,
    }


def observe(
    scenario: str,
    tmp_path: Path,
    packet: dict[str, str],
    served: dict | None = None,
) -> dict:
    """Read one recorded scenario and return it as a model snapshot's facts.

    The receiver is handed the scenario through the stand-in: it lists the
    discussion, reads the plan the completeness request names at the head the
    PR gives, reads the candidate's changed paths, and derives its assignment
    from the handoff packet, that diff and the request's proof inventory. No
    candidate value and no reply is written here, and nothing is decided.

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
    dict
        The facts of one ``snapshot()`` row, with every default filled in.
    """
    reads = staged(scenario, tmp_path, served)
    bounds = bounds_of(scenario, reads)
    completeness_applies, proof_applies, issue_derived = applicability(reads, packet)
    threads = {
        COMPLETENESS: (completeness_applies, reads.completeness),
        PROOF: (proof_applies, reads.proof),
    }
    held = {
        kind: thread_state(kind, reads.listing, request, bounds) if applies else "none"
        for kind, (applies, request) in threads.items()
    }
    # The model's inventory is a small set of stand-in names. Which recorded
    # proof is `p1` does not matter to it; how many there are, and how many
    # of them a reply covers, does.
    stand_ins = tuple(f"p{index + 1}" for index in range(len(bounds.required)))
    return {
        **SNAPSHOT_DEFAULTS,
        **delivery(reads),
        "completeness_applies": completeness_applies,
        "proof_applies": proof_applies, "issue_derived": issue_derived,
        "proofs": stand_ins if proof_applies else (),
        "completeness": held[COMPLETENESS],
        "proof": held[PROOF],
    }


def transitioned(scenario: str) -> bool:
    """Return whether the recorded agent issued `gh pr ready` in this run."""
    trace = FIXTURES / "traces" / f"{scenario}.jsonl"
    return any(
        json.loads(line)[:2] == ["pr", "ready"]
        for line in trace.read_text(encoding="utf-8").splitlines()
    )


@pytest.mark.parametrize("recording", DECISIONS, ids=lambda recording: recording.name)
def test_each_recording_is_the_snapshot_the_model_was_checked_on(
    recording: Recording, tmp_path: Path, packet: dict[str, str]
) -> None:
    """The handoff, the recording and the model agree on every deciding input.

    Each row names both the outcome and the fact that has to produce it.
    Pinning the fact rather than only the outcome is what keeps the rows
    apart: several of them hold, and an adapter that confused a declared
    subset with an unclear verdict, or a stale revision with an omitted one,
    would still hold every one of them for the wrong reason.

    Three things must then agree. The facts read through the stand-in equal
    the row the suite keeps for this recording, so the model checker was
    asked about this candidate and not a tidier one. That row's expectation,
    which `make model-check` verifies, is the one stated here. And the
    recorded agent did the same: it issued `gh pr ready` exactly when the
    model permits the transition.
    """
    scenario, expect = recording.name, recording.expect
    facts = observe(scenario, tmp_path, packet)

    for fact, value in recording.deciding.items():
        assert facts[fact] == value, (
            f"{scenario} abstracts {fact} as {facts[fact]!r}, not {value!r}"
        )
    recorded_expect, recorded_facts = snapshot_rows("fixture-snapshots")[
        f"fixture:{scenario}"
    ]
    assert recorded_facts == facts, (
        f"the suite's row for {scenario} states {recorded_facts}, but the"
        f" recording abstracts to {facts}"
    )
    assert recorded_expect == expect, (
        f"the suite expects {recorded_expect!r} of {scenario}, not {expect!r}"
    )
    assert transitioned(scenario) is (expect == "ready"), (
        f"the recorded agent's transition disagrees with {expect!r}"
    )


def test_the_receiver_reads_its_applicability_from_the_handoff(
    packet: dict[str, str],
    tmp_path: Path,
) -> None:
    """The assignment is the packet's, so the packet cannot quietly stop saying it.

    `observe` derives both flags from these lines. If the completeness line
    stopped saying `required`, the receiver would record an inapplicable
    assessment and the whole-plan case would clear without reading a reply at
    all, so the lines are asserted on their own as well as through it.

    Asserting the shipped wording alone would leave one direction open: an
    `observe` that hard-coded either flag would agree with the wording it read
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
    # requirement is withdrawn, which is the flag `observe` reads.
    withdrawn = {
        **packet,
        "assessment": packet["assessment"].replace(
            "required against the whole approved plan",
            "optional against the declared PR scope",
        ),
    }
    assert withdrawn["assessment"] != packet["assessment"]
    facts = observe("subset-clear", tmp_path, withdrawn)
    assert facts["completeness_applies"] is False
    assert checked_expectation(facts, CHECKED_TABLES) == "ready", (
        "a withdrawn completeness assessment still held the gate"
    )

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
    facts = observe("combined-proof-pending", tmp_path, unconditional)
    assert facts["proof_applies"] is False
    assert checked_expectation(facts, CHECKED_TABLES) == "ready", (
        "a withdrawn proof assessment still held the gate"
    )


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
    observed = observe("combined-plan-and-proof", asked, packet, facts)
    assert observed["proof_applies"] is True and observed["proof"] == "none", (
        f"a missing required proof question abstracts to {observed}"
    )
    assert checked_expectation(observed, CHECKED_TABLES) == "draft"

    # The control: the same removal where the inventory says none affected.
    empty = tmp_path / "empty"
    empty.mkdir()
    stage(empty, "current-whole-plan")
    empty_facts = json.loads((empty / "facts.json").read_text(encoding="utf-8"))
    assert not affects_a_proof(
        str(completeness_request(empty_facts["api"][r"/issues/\d+/comments"])["body"])
    ), "the control scenario no longer records an empty inventory"
    assert checked_expectation(
        observe("current-whole-plan", empty, packet), CHECKED_TABLES
    ) == "ready", "an empty inventory did not clear without a proof question"


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

    def observed_with(name: str, line: str) -> tuple[dict, dict]:
        """Serve this scenario with one `Proof inventory:` line, and observe."""
        directory = tmp_path / name
        directory.mkdir()
        stage(directory, "current-whole-plan")
        facts = json.loads((directory / "facts.json").read_text(encoding="utf-8"))
        facts["api"][r"/issues/\d+/comments"] = [
            {**entry, "body": PROOF_INVENTORY.sub(line, str(entry["body"]))}
            for entry in facts["api"][r"/issues/\d+/comments"]
        ]
        return observe("current-whole-plan", directory, packet, facts), facts

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
    assert checked_expectation(
        observe("current-whole-plan", empty, packet), CHECKED_TABLES
    ) == "ready", "the empty-inventory control did not clear"

    without, absent = observed_with("absent", "")
    assert not affects_a_proof(
        str(completeness_request(absent["api"][r"/issues/\d+/comments"])["body"])
    ), "the removed inventory still records an affected proof"
    assert checked_expectation(without, CHECKED_TABLES) == "ready", (
        "the absent-line control did not clear"
    )

    claimed, named = observed_with(
        "named", f"Proof inventory: `{proof}` (`{reference}`)."
    )
    assert affects_a_proof(
        str(completeness_request(named["api"][r"/issues/\d+/comments"])["body"])
    ), "the altered inventory names no proof"
    assert claimed["proof_applies"] is True and claimed["proof"] == "none", (
        f"an inventory naming an affected proof abstracts to {claimed}"
    )
    assert checked_expectation(claimed, CHECKED_TABLES) == "draft", (
        "an inventory naming an affected proof cleared without its assessment"
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
    observed = observe("combined-plan-and-proof", denied, packet, facts)
    # The diff is what applies, and it is what the reply must cover: with the
    # inventory denying it, the changed proof is added back to the inventory,
    # so the hold is the unasked assessment of that proof rather than a
    # request that named no subject at all.
    assert observed["proof_applies"] is True and observed["proofs"] == ("p1",), (
        f"a denied but changed proof abstracts to {observed}"
    )
    assert observed["proof"] == "none", f"no proof question remains: {observed}"
    assert checked_expectation(observed, CHECKED_TABLES) == "draft", (
        "a proof-changing candidate cleared with its inventory denying the proof"
    )

    # The control: no changed proof, the same empty inventory, and it clears.
    control = tmp_path / "control"
    control.mkdir()
    control_shim = stage(control, "current-whole-plan")
    assert not changes_a_proof(
        changed_paths(control_shim), recorded_proof(control)
    ), "the control scenario now changes the proof it names"
    assert checked_expectation(
        observe("current-whole-plan", control, packet), CHECKED_TABLES
    ) == "ready", "the control did not clear without a proof question"


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
    observed = observe("combined-plan-and-proof", renamed, packet, facts)
    assert observed["proofs"] == ("p1", "p2"), (
        f"the changed proof was not added to the inventory: {observed}"
    )
    assert observed["proof"] == "current:partial-proofs", (
        f"a verdict naming only the other proof abstracts to {observed}"
    )
    assert checked_expectation(observed, CHECKED_TABLES) == "draft", (
        "a clean verdict on another proof cleared the changed proof's assessment"
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
    assert checked_expectation(
        observe("current-whole-plan", control, packet, control_facts), CHECKED_TABLES
    ) == "ready", "the control did not clear without a proof assessment"


def listing_comments(directory: Path) -> list[dict]:
    """Return the discussion the scenario's own facts record, unfiltered."""
    facts = json.loads((directory / "facts.json").read_text(encoding="utf-8"))
    return list(facts["api"][r"/issues/\d+/comments"])


def test_a_completeness_request_naming_no_revision_cannot_clear(
    tmp_path: Path, packet: dict[str, str]
) -> None:
    """An applicable completeness verdict is bound to a named revision.

    `current-whole-plan` clears. Serve it with the completeness request's
    `Plan revision:` line removed while the reply still echoes one, and the
    request names nothing the verdict could be bound to: it abstracts to the
    model's `unnamed-revision` request, which no reply clears. The control is
    the unaltered recording, which still clears.
    """
    directory = tmp_path / "unnamed"
    directory.mkdir()
    stage(directory, "current-whole-plan")
    facts = json.loads((directory / "facts.json").read_text(encoding="utf-8"))
    comments = facts["api"][r"/issues/\d+/comments"]
    request = completeness_request(comments)
    stripped = re.sub(r"^Plan revision:[^\n]*\n", "", str(request["body"]), flags=re.MULTILINE)
    assert stripped != request["body"], "the recorded request names no revision to remove"
    request["body"] = stripped

    observed = observe("current-whole-plan", directory, packet, facts)

    assert observed["completeness"] == "unnamed-revision:sound-clear", observed
    assert checked_expectation(observed, CHECKED_TABLES) == "draft", (
        "a completeness request naming no revision cleared the gate"
    )
    control = tmp_path / "control"
    control.mkdir()
    assert checked_expectation(
        observe("current-whole-plan", control, packet), CHECKED_TABLES
    ) == "ready", "the unaltered recording no longer clears"
