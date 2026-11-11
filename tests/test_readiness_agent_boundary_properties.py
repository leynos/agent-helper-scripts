"""Property tests for the runner's ordered-evidence probes.

`test_readiness_agent_boundary_shim.py` states each probe's cases one at a
time: a candidate-bound delta before the boundary, a plan read at the head, a
read-back that returns a ready value. This module generates them instead,
because each rule is a relation over order and identity — which call, on which
side of the transition, for which revision — rather than a fixed list of
examples.

Every property runs the bytes `sandboxed_run.sh` executes. The probe body is
extracted from the runner and fed to `python3 -` rather than reimplemented
here, so a rewrite of a probe is exercised rather than a copy of it that would
drift.

The oracle for each case is the documented rule, not the probe's control flow:
a run clears when the evidence the rule requires exists on the required side of
the transition, and refuses otherwise. Both directions are asserted, because a
probe that refused everything would pass a one-sided test while being a broken
gate reported as a strict one.

The cases are built to named shapes rather than sampled uniformly. A trace with
a candidate-bound delta in it is vanishingly unlikely to be drawn at random
from arbitrary argument lists, so a uniform generator would exercise only the
branches that reject.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

from hypothesis import given, settings
from hypothesis import strategies as st

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "readiness-agent-boundary"
RUNNER = FIXTURES / "sandboxed_run.sh"
SCENARIO = FIXTURES / "scenarios" / "current-whole-plan" / "facts.json"

#: The candidate the probes are handed. Read from the recorded facts rather than
#: written here, so a fixture change moves the generated cases with it instead
#: of leaving them asserting about a head no scenario serves.
FACTS = json.loads(SCENARIO.read_text(encoding="utf-8"))
BASE = FACTS["pr"]["baseRefOid"]
HEAD = FACTS["pr"]["headRefOid"]
BRANCH = FACTS["pr"]["headRefName"]

#: A revision that is neither the candidate nor its base, standing for another
#: run's head. Evidence about it is not evidence about this candidate.
OTHER = "dddd4444"

#: The refs that name this candidate. The head names it by commit and by branch;
#: its base does not, because the plan file there is `main`'s copy.
CANDIDATE_REFS = {HEAD, BRANCH}

#: The probe's protocol with the shell. `sandboxed_run.sh` matches these tokens
#: in a `case`, so they are a contract between the two programs rather than
#: debugging text, and each case pins the token its shape must produce.
CLEARS = "yes"
NO_ORDERED_DELTA = "no"


def probe_body(marker: str) -> str:
    """Return the Python the runner runs from the heredoc named `marker`."""
    text = RUNNER.read_text()
    opening = f"<<'{marker}'\n"
    start = text.index(opening) + len(opening)
    end = text.index(f"\n{marker}\n", start)
    return text[start:end]


def run_probe(marker: str, *argv: str) -> subprocess.CompletedProcess[str]:
    """Run one of the runner's Python probes over the given arguments."""
    return subprocess.run(
        ["python3", "-", *argv],
        input=probe_body(marker),
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )


@contextmanager
def workspace() -> Iterator[Path]:
    """Yield a private directory for one generated case, then remove it.

    A directory per example is a directory per generated trace, which is what
    keeps one case's recordings from being read as another's. Hypothesis does
    not hand a function-scoped pytest fixture to a `@given` test, so the
    lifetime is managed here.
    """
    with tempfile.TemporaryDirectory(prefix="readiness-probe-") as directory:
        yield Path(directory)


def write_lines(path: Path, entries: list[object]) -> Path:
    """Write one JSON document per line, as the trace and answer files are."""
    path.write_text("".join(json.dumps(entry) + "\n" for entry in entries))
    return path


# --------------------------------------------------------------------------
# The local CodeScene probe: a candidate-bound delta before the transition.
# --------------------------------------------------------------------------

TRANSITION = {"event": "pr-ready", "head": HEAD}

#: Calls that are not a candidate-bound delta. A `cs delta` for another
#: revision is noise here even though the real command would run it: the rule is
#: which revision the local check ran against, so a run of the check for some
#: other head says nothing about this one. A lone `delta` operand is the bare
#: form that reads the working tree, which this sandbox does not have.
DELTA_NOISE = (
    ["pr", "view", "272", "--repo", "leynos/agent-helper-scripts"],
    ["pr", "checks", "272", "--repo", "leynos/agent-helper-scripts"],
    ["api", "user", "--jq", ".login"],
    ["api", "repos/leynos/agent-helper-scripts/issues/272/comments"],
    ["api", "repos/leynos/agent-helper-scripts/pulls/272/reviews"],
    ["delta", BASE, OTHER],
    ["delta", OTHER, HEAD],
    ["delta", "HEAD"],
    ["delta", BASE],
)

#: The spellings that do name both endpoints. `cs delta` takes two revisions and
#: does not care which is first, and trailing operands do not stop it naming
#: them, so all three are the evidence the rule asks for.
BOUND_DELTAS = (
    ["delta", BASE, HEAD],
    ["delta", HEAD, BASE],
    ["delta", BASE, HEAD, "--verbose"],
)


def noise_entries(calls: list[list[str]]) -> list[dict]:
    """Wrap argument lists as the `cs` stand-in records them.

    Each line carries the mode the stand-in answered in, as a real run's does.
    The ordering probe reads only `argv` and `event`, so the mode is what a
    completed local analysis leaves behind; whether a finding or an unavailable
    result should stop the run is decided by the runner's own mode check.
    """
    return [{"argv": call, "mode": "clean"} for call in calls]


@st.composite
def delta_traces(draw: st.DrawFn) -> tuple[list[object], str]:
    """Return a generated CodeScene trace and the verdict the rule gives it.

    Parameters
    ----------
    draw : hypothesis.strategies.DrawFn
        Hypothesis draw function supplied to the composite strategy.

    Returns
    -------
    tuple
        ``(entries, expected)``. ``expected`` is ``"yes"`` when a candidate-bound
        delta precedes exactly one transition, ``"no"`` when no such delta
        precedes it, and ``"boundaries=0"`` or ``"boundaries=2"`` when the trace
        does not record a single decision at all.
    """
    head_noise = noise_entries(draw(st.lists(st.sampled_from(DELTA_NOISE), max_size=3)))
    tail_noise = noise_entries(draw(st.lists(st.sampled_from(DELTA_NOISE), max_size=3)))
    delta = {"argv": draw(st.sampled_from(BOUND_DELTAS)), "mode": "clean"}
    shape = draw(
        st.sampled_from(
            (
                "ordered",
                "after-transition",
                "absent",
                "no-transition",
                "two-transitions",
            )
        )
    )
    if shape == "ordered":
        return [*head_noise, delta, *tail_noise, TRANSITION], CLEARS
    if shape == "after-transition":
        # The run consulted the local check after deciding, which is not the
        # evidence it decided on however clear the result.
        return [*head_noise, TRANSITION, *tail_noise, delta], NO_ORDERED_DELTA
    if shape == "absent":
        return [*head_noise, *tail_noise, TRANSITION], NO_ORDERED_DELTA
    if shape == "no-transition":
        return [*head_noise, delta, *tail_noise], "boundaries=0"
    # Two boundaries: the trace records two transitions, so it says nothing
    # about which of them any delta preceded.
    return [*head_noise, delta, TRANSITION, *tail_noise, TRANSITION], "boundaries=2"


@settings(max_examples=40, deadline=None)
@given(delta_traces())
def test_the_code_scene_probe_accepts_exactly_a_delta_before_the_transition(
    case: tuple[list[object], str],
) -> None:
    """The probe clears iff a candidate-bound delta precedes a single boundary.

    The verdict and the exit status are both asserted. The token is what the
    shell acts on, and the status is what makes its `||` branch run, so a probe
    that printed the right word and exited zero would still gate nothing.
    """
    entries, expected = case
    with workspace() as directory:
        trace = write_lines(directory / "cs-trace.jsonl", entries)
        done = run_probe("PROBE_DELTA", str(trace), str(SCENARIO))
    assert done.stdout.strip() == expected, (
        f"a trace built to say {expected!r} produced {done.stdout.strip()!r}:"
        f" {entries} / stderr: {done.stderr}"
    )
    assert (done.returncode == 0) is (expected == CLEARS), (
        f"a trace built to say {expected!r} exited {done.returncode}"
    )


# --------------------------------------------------------------------------
# The plan probe: a usable candidate-bound read on the required side.
# --------------------------------------------------------------------------

#: The approved plan's own route. Built from the recorded facts rather than a
#: literal, because the probe binds the read to the approved path: a generated
#: read of any other ExecPlan is refused however good its evidence is, and a
#: literal that drifted from the label would make every permitting example
#: refuse for a reason the property is not about.
PLAN_ROUTE = (
    "repos/leynos/agent-helper-scripts/contents/" + FACTS["plan_path"]
)

#: The bodies a plan read can return, by kind. The plan file is the surface that
#: states the revision in force, so a successful read of it is only usable
#: evidence when the text names one.
BODIES = {
    "revision": "# Readiness handoff\n\nPlan revision: rev-7\n",
    "empty": "",
    "revision-less": "# Readiness handoff\n",
}

#: Calls unrelated to the plan question. None names the plan route, so none can
#: be mistaken for the read the revision is reconciled against.
PLAN_NOISE = (
    ["pr", "view", "272", "--repo", "leynos/agent-helper-scripts"],
    ["pr", "checks", "272", "--repo", "leynos/agent-helper-scripts"],
    ["api", "user", "--jq", ".login"],
    ["api", "repos/leynos/agent-helper-scripts/issues/272/comments"],
    ["api", "repos/leynos/agent-helper-scripts/pulls/272/reviews"],
)

PR_READY = ["pr", "ready", "272", "--repo", "leynos/agent-helper-scripts"]

#: One read as a test can describe it: the ref it asked for, the status it was
#: answered with, and which body it received.
READ_SPECS = st.fixed_dictionaries(
    {
        "ref": st.sampled_from((HEAD, BRANCH, BASE, OTHER, "")),
        "status": st.sampled_from((0, 0, 0, 1)),
        "body": st.sampled_from(tuple(BODIES)),
    }
)


def plan_read(ref: str) -> list[str]:
    """Return the argv of a plan read at one ref."""
    return ["api", "-H", "Accept: application/vnd.github.raw", f"{PLAN_ROUTE}?ref={ref}"]


def establishes_revision(spec: dict) -> bool:
    """Return whether one plan read establishes the revision in force.

    The rule is a conjunction of three facts about the call rather than a test
    of the probe's branches: the read named the candidate, it succeeded, and the
    text it returned states a revision.
    """
    return (
        spec["ref"] in CANDIDATE_REFS
        and spec["status"] == 0
        and spec["body"] == "revision"
    )


def read_entry(spec: dict) -> tuple[list[str], dict]:
    """Return one plan read's trace line and answer-record line."""
    call = plan_read(spec["ref"])
    return call, {"argv": call, "status": spec["status"], "stdout": BODIES[spec["body"]]}


@st.composite
def plan_cases(draw: st.DrawFn) -> tuple[list[object], list[object], str, bool]:
    """Return a generated plan run and whether the rule says it clears.

    Parameters
    ----------
    draw : hypothesis.strategies.DrawFn
        Hypothesis draw function supplied to the composite strategy.

    Returns
    -------
    tuple
        ``(trace, answers, expect_ready, clears)``: the two recorded files, the
        expectation the runner was started with, and the verdict the documented
        rule gives the run.
    """
    reads = draw(st.lists(READ_SPECS, max_size=3))
    expect_ready = draw(st.sampled_from(("yes", "yes", "yes", "no")))
    # A holding run has no transition to order against, and its decision ends
    # the run, so every read it made precedes that decision by construction. A
    # permitting run that issued no transition is generated too: the probe's own
    # guard refuses it, which is a case worth carrying.
    transitioned = expect_ready == "yes" and draw(
        st.sampled_from((True, True, True, False))
    )
    split = (
        draw(st.integers(min_value=0, max_value=len(reads)))
        if transitioned
        else len(reads)
    )
    head_noise = draw(st.lists(st.sampled_from(PLAN_NOISE), max_size=2))
    mid_noise = draw(st.lists(st.sampled_from(PLAN_NOISE), max_size=2))
    tail_noise = draw(st.lists(st.sampled_from(PLAN_NOISE), max_size=2))

    trace: list[object] = [*head_noise]
    answers: list[object] = [
        {"argv": call, "status": 0, "stdout": ""} for call in head_noise
    ]
    for spec in reads[:split]:
        call, answered = read_entry(spec)
        trace.append(call)
        answers.append(answered)
    trace.extend(mid_noise)
    answers.extend({"argv": call, "status": 0, "stdout": ""} for call in mid_noise)
    if transitioned:
        trace.append(PR_READY)
        answers.append({"argv": PR_READY, "status": 0, "stdout": ""})
    for spec in reads[split:]:
        call, answered = read_entry(spec)
        trace.append(call)
        answers.append(answered)
    trace.extend(tail_noise)
    answers.extend({"argv": call, "status": 0, "stdout": ""} for call in tail_noise)

    clears = (expect_ready == "no" or transitioned) and any(
        establishes_revision(spec) for spec in reads[:split]
    )
    return trace, answers, expect_ready, clears


@settings(max_examples=40, deadline=None)
@given(plan_cases())
def test_the_plan_probe_accepts_exactly_a_usable_read_on_the_required_side(
    case: tuple[list[object], list[object], str, bool],
) -> None:
    """The probe clears iff a usable candidate-bound read precedes the decision.

    A read that names the base, another head, or no ref at all is not
    candidate-bound. A failed read, an empty one, and one whose text states no
    revision all succeeded without establishing anything. Each is generated, so
    the property covers the shapes that must refuse as well as the one that must
    permit — a probe that never opened would fail the permitting examples, and
    one that never closed would fail the refusing ones.
    """
    trace, answers, expect_ready, clears = case
    with workspace() as directory:
        recorded = write_lines(directory / "gh-trace.jsonl", trace)
        answered = write_lines(directory / "gh-answers.jsonl", answers)
        done = run_probe(
            "PROBE_PLAN", str(recorded), str(answered), str(SCENARIO), expect_ready
        )
    if clears:
        assert done.returncode == 0, (
            f"a usable candidate-bound read was refused: {done.stderr}"
        )
    else:
        assert done.returncode != 0, (
            f"a run with no usable read on the required side was accepted:"
            f" {trace} / {answers}"
        )


# --------------------------------------------------------------------------
# The read-back probe: a successful ready observation after the transition.
# --------------------------------------------------------------------------

#: The values a read-back can return. The rule accepts a `--jq`-reduced `false`,
#: the JSON object with `isDraft: false`, a JSON string, and a template printing
#: `false <ref>`.
READY_VALUES = (
    "false",
    "false cccc3333",
    '{"isDraft": false}',
    '{"isDraft": false, "headRefOid": "cccc3333"}',
    '"false"',
    "  false  ",
)

#: The values that are not-ready. `null` is what `pr view --json isDraft --jq
#: 'null'` prints while exiting zero, which is why the exit status alone cannot
#: be the observation.
NOT_READY_VALUES = (
    "null",
    "true",
    '"true"',
    '{"isDraft": true}',
    "{}",
    '{"headRefOid": "cccc3333"}',
    '{"isDraft": null}',
    "",
)

VIEW = [
    "pr", "view", "272", "--repo", "leynos/agent-helper-scripts",
    "--json", "isDraft,headRefOid", "--jq", ".isDraft",
]
#: A view that never asked for `isDraft`, so it cannot be the observation the
#: transition is judged on however it was answered.
PLAIN_VIEW = [
    "pr", "view", "272", "--repo", "leynos/agent-helper-scripts",
    "--json", "state,mergeable",
]


def read_back_specs() -> st.SearchStrategy[dict]:
    """Return a strategy over one read, with what the rule infers from it.

    Each drawn spec carries whether the call asked for `isDraft` at all and
    whether, taken as a whole, it observed the PR is no longer a draft. Both are
    stated here from the documented rule, so the test's oracle does not depend
    on the probe agreeing with itself.
    """
    ready = st.builds(
        lambda value: {
            "asks": True,
            "status": 0,
            "stdout": value,
            "shows": value.strip() not in NOT_READY_VALUES,
        },
        st.sampled_from(READY_VALUES),
    )
    not_ready = st.builds(
        lambda value: {"asks": True, "status": 0, "stdout": value, "shows": False},
        st.sampled_from(NOT_READY_VALUES),
    )
    # A read that failed is not an observation whatever it printed, which is why
    # the status belongs to the same spec rather than to a separate case.
    failed = st.just({"asks": True, "status": 1, "stdout": "", "shows": False})
    unrelated = st.just(
        {"asks": False, "status": 0, "stdout": "OPEN", "shows": False}
    )
    return st.one_of(ready, not_ready, failed, unrelated)


def entry(spec: dict) -> dict:
    """Return one answer-record line for a read spec."""
    argv = VIEW if spec["asks"] else PLAIN_VIEW
    return {"argv": argv, "status": spec["status"], "stdout": spec["stdout"]}


@st.composite
def read_back_cases(draw: st.DrawFn) -> tuple[list[object], bool]:
    """Return a generated answer record and whether the rule says it clears.

    Parameters
    ----------
    draw : hypothesis.strategies.DrawFn
        Hypothesis draw function supplied to the composite strategy.

    Returns
    -------
    tuple
        ``(entries, clears)``: the answer record and the verdict the documented
        rule gives it.
    """
    transitioned = draw(st.sampled_from((True, True, True, False)))
    before = draw(st.lists(read_back_specs(), max_size=2))
    after = draw(st.lists(read_back_specs(), max_size=2))

    entries: list[object] = [entry(spec) for spec in before]
    if transitioned:
        entries.append({"argv": PR_READY, "status": 0, "stdout": ""})
    entries.extend(entry(spec) for spec in after)

    # The rule: the transition happened, at least one read after it asked for
    # `isDraft`, none of those failed, and at least one returned a ready value.
    # A read before the transition is not the observation of it, whatever it
    # printed.
    read_backs = [spec for spec in after if spec["asks"]]
    clears = (
        transitioned
        and bool(read_backs)
        and all(spec["status"] == 0 for spec in read_backs)
        and any(spec["shows"] for spec in read_backs)
    )
    return entries, clears


@settings(max_examples=40, deadline=None)
@given(read_back_cases())
def test_the_read_back_probe_accepts_exactly_a_ready_observation_after_the_transition(
    case: tuple[list[object], bool],
) -> None:
    """The probe clears iff a successful ready read follows the transition.

    The value matters as much as the order: `null`, `true`, a missing field and
    an empty answer all exit zero, so a probe that accepted the exit status
    would clear a run that observed nothing. The order matters as much as the
    value: an initial `pr view` also carries `isDraft`, so a probe that ignored
    order would accept a run that only looked before transitioning.
    """
    entries, clears = case
    with workspace() as directory:
        answers = write_lines(directory / "gh-answers.jsonl", entries)
        done = run_probe("PROBE_READBACK", str(answers))
    if clears:
        assert done.returncode == 0, (
            f"a ready observation after the transition was refused: {done.stderr}"
        )
    else:
        assert done.returncode != 0, (
            f"an answer record with no ready observation was accepted: {entries}"
        )


# --------------------------------------------------------------------------
# The proof-read probe: a usable read of the assessed proof before the
# transition.
# --------------------------------------------------------------------------

#: The combined scenario serves the proof the assessment is about, so a proof
#: read is generated against the route that actually answers for it. The facts
#: are read rather than restated for the same reason the plan route is: a
#: fixture that moved its proof would otherwise leave every permitting example
#: reading a route that serves nothing.
COMBINED = FIXTURES / "scenarios" / "combined-plan-and-proof" / "facts.json"
PROOF_FACTS = json.loads(COMBINED.read_text(encoding="utf-8"))
PROOF_PATH = PROOF_FACTS["proof_path"]
PROOF_ROUTE = (
    "repos/leynos/agent-helper-scripts/contents/" + PROOF_PATH
)
PROOF_HEAD = PROOF_FACTS["pr"]["headRefOid"]
PROOF_BRANCH = PROOF_FACTS["pr"]["headRefName"]
PROOF_BASE = PROOF_FACTS["pr"]["baseRefOid"]
PROOF_CANDIDATE_REFS = {PROOF_HEAD, PROOF_BRANCH}

#: The text the combined scenario's proof route serves, taken from the facts.
#: The probe compares a read against this, so the oracle here compares against
#: the same served text rather than against a copy that a fixture edit would
#: leave behind.
SERVED_PROOF = next(
    str(payload["content"])
    for pattern, payload in PROOF_FACTS["api"].items()
    if isinstance(payload, dict) and "content" in payload
    and re.search(pattern, f"/contents/{PROOF_PATH}")
)

#: The bodies a proof read can return, by kind. `whole` is the served text, so
#: it is a read of the proof; `header` is the file's first line only, which is
#: what a filtered read that stopped at the declaration returns, and `metadata`
#: is the JSON envelope around the content rather than the content itself.
PROOF_BODIES = {
    "whole": SERVED_PROOF,
    "header": SERVED_PROOF.splitlines(keepends=True)[0],
    "metadata": json.dumps({"sha": "0" * 40, "path": PROOF_PATH}),
    "empty": "",
}


def proof_read_call(ref: str) -> list[str]:
    """Return the argv of a read of the assessed proof at one ref."""
    return ["api", "-H", "Accept: application/vnd.github.raw", f"{PROOF_ROUTE}?ref={ref}"]


def names_the_proof(argument: object) -> bool:
    """Return whether one argv entry asks for the assessed proof itself.

    Written from the documented rule rather than from the probe's helper: the
    read has to name the proof route, and may qualify it with a query or
    fragment. A path that merely continues past the proof's own — a `.bak`
    beside it — is a different file and is not the assessment's subject.
    """
    text = str(argument)
    found = text.find(f"contents/{PROOF_PATH}")
    if found < 0:
        return False
    tail = text[found + len(f"contents/{PROOF_PATH}"):]
    return tail == "" or tail[:1] in "?#"


#: One proof read as a test can describe it: the ref it asked for, the status
#: it was answered with, and which body it received. The ref set includes a
#: different proof path and an unrelated call, so a generated trace can hold
#: reads that are not of the assessed proof at all.
PROOF_READ_SPECS = st.fixed_dictionaries(
    {
        "ref": st.sampled_from((PROOF_HEAD, PROOF_BRANCH, PROOF_BASE, OTHER, "")),
        "status": st.sampled_from((0, 0, 0, 1)),
        "body": st.sampled_from(tuple(PROOF_BODIES)),
    }
)

#: Calls unrelated to the proof question. None names the proof route, so none
#: can be mistaken for the read the assessment rests on.
PROOF_NOISE = (
    ["pr", "view", "272", "--repo", "leynos/agent-helper-scripts"],
    ["pr", "checks", "272", "--repo", "leynos/agent-helper-scripts"],
    ["api", "user", "--jq", ".login"],
    ["api", "repos/leynos/agent-helper-scripts/issues/272/comments"],
    ["api", "repos/leynos/agent-helper-scripts/pulls/272/reviews"],
    # A read of a different file beside the proof, and a bare hash of it. Both
    # name a route the answer is not about, which is the shape a check anchored
    # on the proof directory alone would accept.
    [
        "api",
        "-H",
        "Accept: application/vnd.github.raw",
        f"{PROOF_ROUTE}.bak?ref={PROOF_HEAD}",
    ],
    ["api", f"{PROOF_ROUTE}?ref={PROOF_HEAD}", "--jq", ".sha"],
)


def establishes_the_proof(spec: dict) -> bool:
    """Return whether one proof read establishes the assessed proof itself.

    The rule is a conjunction of four facts about the call rather than a test of
    the probe's branches: the read named the candidate, it succeeded, it
    returned the whole served text rather than a header or an envelope, and it
    was therefore a read of the proof the assessment is about.
    """
    return (
        spec["ref"] in PROOF_CANDIDATE_REFS
        and spec["status"] == 0
        and spec["body"] == "whole"
    )


def proof_entry(spec: dict) -> tuple[list[str], dict]:
    """Return one proof read's trace line and answer-record line."""
    call = proof_read_call(spec["ref"])
    return call, {"argv": call, "status": spec["status"], "stdout": PROOF_BODIES[spec["body"]]}


#: The refs a proof read can name. `candidate` names this PR, so it is the
#: only kind that can establish the proof; the rest are another ref or none.
READ_REF_KINDS = ("candidate", "other", "base", "none")

#: The bodies a read can return, in the terms the rule uses rather than the
#: probe's. `whole` is the one that shows the proof; the others are the ways a
#: read can succeed without doing so.
READ_BODIES = ("whole", "header", "metadata", "empty")


@st.composite
def a_proof_read(draw: st.DrawFn) -> dict:
    """Return one proof read together with whether the rule accepts it.

    The read's kind is drawn first and its parts are built from it, so the one
    shape that establishes the proof is drawn with the same frequency as any
    other. Sampling the fields independently would make "the candidate ref,
    exit zero, the whole served text" one combination in eighty, and the
    permittting arm would be reached by luck rather than by construction —
    which is how an earlier version of this property passed against a probe
    whose completeness check had been disabled.

    Parameters
    ----------
    draw : hypothesis.strategies.DrawFn
        Hypothesis draw function supplied to the composite strategy.

    Returns
    -------
    dict
        The read's ``ref``, ``status``, ``body``, the ``names`` and ``asks``
        flags that say what it named, and the ``establishes`` verdict the
        documented rule gives it.
    """
    kind = draw(st.sampled_from(READ_REF_KINDS))
    body = draw(st.sampled_from(READ_BODIES))
    # A failed read is a separate shape from a successful one: the rule refuses
    # it whatever body it carried, so the status is drawn independently and the
    # oracle does not let the body override it.
    status = draw(st.sampled_from((0, 0, 0, 1)))
    ref = {
        "candidate": draw(st.sampled_from((PROOF_HEAD, PROOF_BRANCH))),
        "other": OTHER,
        "base": PROOF_BASE,
        "none": "",
    }[kind]
    # The read's route. A `.bak` beside the proof names a route the answer is
    # not about, and an unrelated call names none at all; both are generated so
    # the oracle's `names` test is exercised in both directions rather than
    # being taken for granted.
    route = draw(
        st.sampled_from(
            (
                PROOF_ROUTE,
                PROOF_ROUTE,
                PROOF_ROUTE,
                f"{PROOF_ROUTE}.bak",
                "repos/leynos/agent-helper-scripts/issues/272/comments",
            )
        )
    )
    names = names_the_proof(f"{route}?ref={ref}" if ref else route)
    return {
        "ref": ref,
        "route": route,
        "status": status,
        "body": body,
        "names": names,
        "establishes": (
            kind == "candidate" and status == 0 and body == "whole" and names
        ),
    }


def proof_call(spec: dict) -> list[str]:
    """Return the argv one drawn proof read records."""
    route = spec["route"]
    ref = spec["ref"]
    return [
        "api",
        "-H",
        "Accept: application/vnd.github.raw",
        f"{route}?ref={ref}" if ref else route,
    ]


def proof_answer(spec: dict) -> dict:
    """Return the answer-record line for one drawn proof read."""
    return {
        "argv": proof_call(spec),
        "status": spec["status"],
        "stdout": PROOF_BODIES[spec["body"]],
    }


@st.composite
def usable_proof_read(draw: st.DrawFn) -> dict:
    """Return the one read shape the rule accepts: candidate, zero, whole.

    The ref is drawn from the two spellings that name this candidate, so the
    shape exercises both the commit and the branch rather than only whichever
    one the fixture happens to list first.

    Parameters
    ----------
    draw : hypothesis.strategies.DrawFn
        Hypothesis draw function supplied to the composite strategy.

    Returns
    -------
    dict
        A read spec carrying the whole served text at a candidate ref.
    """
    return {
        "ref": draw(st.sampled_from((PROOF_HEAD, PROOF_BRANCH))),
        "route": PROOF_ROUTE,
        "status": 0,
        "body": "whole",
        "names": True,
        "establishes": True,
    }


@st.composite
def decoy_proof_read(draw: st.DrawFn) -> dict:
    """Return a candidate-shaped read of a *different* file beside the proof.

    This is the near-miss the rule has to refuse: the ref names the candidate,
    the call exits zero, and the body is the whole served text — but the route
    is `…/Theorem.lean.bak`, a file that merely continues past the assessed
    proof's path. A probe that matched the proof directory, or that dropped
    the terminator its own naming helper applies, accepts it and clears a run
    that never read the proof.

    Parameters
    ----------
    draw : hypothesis.strategies.DrawFn
        Hypothesis draw function supplied to the composite strategy.

    Returns
    -------
    dict
        A read spec that looks usable but names another file.
    """
    return {
        "ref": draw(st.sampled_from((PROOF_HEAD, PROOF_BRANCH))),
        "route": f"{PROOF_ROUTE}.bak",
        "status": 0,
        "body": "whole",
        "names": False,
        "establishes": False,
    }


@st.composite
def proof_read_cases(draw: st.DrawFn) -> tuple[list[object], list[object], bool]:
    """Return a generated proof-read run and whether the rule says it clears.

    A run is generated from named shapes: the reads that precede the
    transition, where the decisive one sits among them, and the reads that
    follow it. The transition is placed at a drawn index, so a usable read can
    fall on either side of it, and noise calls are interleaved so a probe that
    scanned the whole trace for a proof route would be caught.

    Parameters
    ----------
    draw : hypothesis.strategies.DrawFn
        Hypothesis draw function supplied to the composite strategy.

    Returns
    -------
    tuple
        ``(trace, answers, clears)``: the two recorded files and the verdict
        the documented rule gives the run.
    """
    before = draw(st.lists(a_proof_read(), max_size=3))
    after = draw(st.lists(a_proof_read(), max_size=3))
    # A usable read that lands after the barrier cannot be evidence the
    # transition rested on it. Drawing `after` from the same shape as `before`
    # made "the candidate ref, exit zero, the whole served text" after the
    # barrier one combination in hundreds, so a probe that scanned the whole
    # trace instead of the part before the transition still passed. Drawing one
    # deliberately is what catches that.
    after.extend(draw(st.lists(usable_proof_read(), max_size=1)))
    # A decoy is drawn on the permitting side too. A run whose only
    # candidate-shaped read is of another file must still refuse, so the decoy
    # is placed deliberately rather than waiting for the shape to be sampled
    # alongside a real read.
    before.extend(draw(st.lists(decoy_proof_read(), max_size=1)))
    head_noise = draw(st.lists(st.sampled_from(PROOF_NOISE), max_size=2))
    mid_noise = draw(st.lists(st.sampled_from(PROOF_NOISE), max_size=2))
    tail_noise = draw(st.lists(st.sampled_from(PROOF_NOISE), max_size=2))

    trace: list[object] = [*head_noise]
    answers: list[object] = [
        {"argv": call, "status": 0, "stdout": ""} for call in head_noise
    ]
    trace.extend(proof_call(spec) for spec in before)
    answers.extend(proof_answer(spec) for spec in before)
    trace.extend(mid_noise)
    answers.extend({"argv": call, "status": 0, "stdout": ""} for call in mid_noise)
    trace.append(PR_READY)
    answers.append({"argv": PR_READY, "status": 0, "stdout": ""})
    trace.extend(proof_call(spec) for spec in after)
    answers.extend(proof_answer(spec) for spec in after)
    trace.extend(tail_noise)
    answers.extend({"argv": call, "status": 0, "stdout": ""} for call in tail_noise)

    return trace, answers, any(spec["establishes"] for spec in before)


@settings(max_examples=40, deadline=None)
@given(proof_read_cases())
def test_the_proof_read_probe_accepts_exactly_a_usable_read_before_the_transition(
    case: tuple[list[object], list[object], bool],
) -> None:
    """The probe clears iff a usable candidate-bound proof read precedes ready.

    A read of the base, another head, or no ref at all is not candidate-bound.
    A failed read, an empty one, one whose body is only the metadata envelope,
    and one reduced to the declaration header all succeeded without showing the
    proof the assessment is about. Reads placed after the transition are not
    evidence the transition rested on them. Each of those shapes is generated
    on both sides of the boundary, so the property covers what must refuse as
    well as what must permit — a probe that never opened would fail the
    permitting examples, and one that never closed would fail the refusing
    ones.
    """
    trace, answers, clears = case
    with workspace() as directory:
        recorded = write_lines(directory / "gh-trace.jsonl", trace)
        answered = write_lines(directory / "gh-answers.jsonl", answers)
        done = run_probe("PROBE_PROOF_READ", str(recorded), str(answered), str(COMBINED))
    if clears:
        assert done.returncode == 0, (
            f"a usable candidate-bound proof read was refused: {done.stderr}"
        )
    else:
        assert done.returncode != 0, (
            f"a run with no usable proof read before the transition was"
            f" accepted: {trace} / {answers}"
        )
