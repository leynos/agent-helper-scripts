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
