"""Hold the agent-boundary recordings and the model's scenario traces together.

``specs/pr-readiness/fixtures.toml`` states which recorded command stands for
which action of ``readiness.fizz``, and which hand-authored scenario trace of
the suite reproduces which recording. The model checker replays each trace
against the specification in ``make model-check``. These tests supply the
other half: they abstract each recording through the stated mapping and
require it to agree with its trace on what matters about order.

- The effects are the same, in the same order: a question posted, a PR
  marked ready.
- Every kind of read the model performs before an effect happened before
  that effect in the recording, so no effect rests on a read the recorded
  agent had not made.
- A PR read follows the last discussion read before the ready command,
  which is the position of the model's re-fetch, and a PR read follows the
  ready command, which is its read-back. These compare kinds of read, not
  their content: they do not establish which discussion read returned the
  reply, or that it returned anything new.

A recording is evidence about one sampled agent run. Where a run did not
make a read the model makes, ``fixtures.toml`` lists that step as unobserved
and says why; the last test here fails if a listed step turns out to be
present, so the list cannot go stale in the flattering direction.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import sys
import tomllib

import pytest

from pr_readiness_spec_support import REPO_ROOT, SPEC_DIRECTORY, actions, runs

FIXTURES = REPO_ROOT / "tests" / "fixtures" / "readiness-agent-boundary"
MAPPING = tomllib.loads((SPEC_DIRECTORY / "fixtures.toml").read_text(encoding="utf-8"))
EVENTS = MAPPING["event"]
NAMES = [fixture["name"] for fixture in MAPPING["fixture"]]
#: Agent steps with no command of their own: the decision is internal, and
#: an interruption is not something a recording of one session contains.
INTERNAL = {"AgentDecides", "AgentInterrupted"}


def kind_of(source: str, command: str) -> str | None:
    """Return the mapped kind of one recorded command, or None if unmapped."""
    for event in EVENTS:
        if event["source"] == source and re.search(event["pattern"], command + " "):
            return str(event["kind"])
    return None


def gh_kinds(name: str) -> list[str]:
    """Return a recording's ``gh`` commands as mapped kinds, in order."""
    lines = (FIXTURES / "traces" / f"{name}.jsonl").read_text().splitlines()
    kinds = (kind_of("gh", " ".join(map(str, json.loads(line)))) for line in lines)
    return [kind for kind in kinds if kind]


def cs_kinds(name: str) -> tuple[list[str], list[str], bool]:
    """Return a recording's ``cs`` kinds before and after the ready marker.

    The third value says whether the stand-in wrote a ``pr-ready`` marker at
    all. Without one, every local delta is in the second list.
    """
    lines = (FIXTURES / "traces" / f"{name}-cs.jsonl").read_text().splitlines()
    entries = [json.loads(line) for line in lines]
    markers = [index for index, entry in enumerate(entries) if entry.get("event") == "pr-ready"]

    def kinds(part: list[dict]) -> list[str]:
        """Return the mapped kinds of some ``cs`` entries."""
        found = (kind_of("cs", " ".join(entry.get("argv", []))) for entry in part)
        return [kind for kind in found if kind]

    if not markers:
        return [], kinds(entries), False
    last = markers[-1]
    return kinds(entries[:last]), kinds(entries[last + 1 :]), True


def recorded(name: str) -> list[str]:
    """Return a recording as mapped kinds, in the order the run made them.

    The two trace files are written by two processes. The only cross-file
    order a recording states is the stand-in's ``pr-ready`` marker in the
    ``cs`` trace. When it exists, a local delta before the marker is placed
    immediately before the ready command and one after it immediately after,
    so a check run after the transition is never read as evidence for it.
    Without a marker, every delta is placed at the start: its order against
    the ``gh`` reads is not recorded, and no check below depends on it
    except the one before a ready command.
    """
    before_ready, after_ready, marked = cs_kinds(name)
    if not marked:
        return [*after_ready, *gh_kinds(name)]
    sequence: list[str] = []
    for kind in gh_kinds(name):
        if kind == "ready-command":
            sequence.extend(before_ready)
        sequence.append(kind)
        if kind == "ready-command":
            sequence.extend(after_ready)
    return sequence


def fixture(name: str) -> dict:
    """Return one fixture's mapping entry."""
    return next(entry for entry in MAPPING["fixture"] if entry["name"] == name)


def modelled(name: str) -> list[str]:
    """Return the agent actions of a fixture's trace that the model executes.

    A refused trace states how many steps run; the step after them is the
    one the model refuses, so it is not part of the behaviour.
    """
    run = runs()[fixture(name)["run"]]
    assert run["class"] == "scenario-trace", f"{run['id']} is not a scenario trace"
    steps = list(run["trace"])
    if run["expect"] != "pass":
        steps = steps[: run["expect"]["executed"]]
    return [step for step in steps if step.startswith("Agent")]


def kinds_for(action: str) -> set[str]:
    """Return the recorded kinds that can stand for one model action."""
    return {str(event["kind"]) for event in EVENTS if action in event["models"]}


EFFECT_KINDS = {str(event["kind"]) for event in EVENTS if event.get("effect")}
EFFECT_ACTIONS = {
    action for event in EVENTS if event.get("effect") for action in event["models"]
}


def test_every_external_agent_step_is_mapped_to_a_recorded_command() -> None:
    """The mapping covers the model's side completely and names nothing else."""
    declared = actions("readiness.fizz")
    mapped = {action for event in EVENTS for action in event["models"]}
    assert mapped <= declared, f"mapped to unknown actions: {sorted(mapped - declared)}"
    external = {
        action for action in declared if action.startswith("Agent")
    } - INTERNAL - {"AgentRunsMergeCommand"}
    assert external <= mapped, f"unmapped agent steps: {sorted(external - mapped)}"
    for entry in MAPPING["fixture"]:
        assert set(entry["unobserved"]) <= mapped, entry["name"]


@pytest.mark.parametrize("name", NAMES)
def test_a_recording_and_its_trace_make_the_same_effects(name: str) -> None:
    """The recorded agent posted and transitioned exactly as the trace does.

    This is also what keeps a blocking recording blocking: its trace is
    refused before the ready command, so the recording must hold none.
    """
    concrete = [kind for kind in recorded(name) if kind in EFFECT_KINDS]
    abstract = [
        next(iter(kinds_for(action)))
        for action in modelled(name)
        if action in EFFECT_ACTIONS
    ]
    assert concrete == abstract, (
        f"{name} recorded effects {concrete}; its trace makes {abstract}"
    )


def reads_before_effects(name: str) -> tuple[list[tuple[str, set[str]]], set[str]]:
    """Return each effect of a fixture's trace with the reads made before it.

    The second value is every read the trace makes. Internal steps make no
    read, and a step the fixture lists as unobserved is excluded here and
    checked separately.
    """
    unobserved = set(fixture(name)["unobserved"])
    needed: set[str] = set()
    effects: list[tuple[str, set[str]]] = []
    for action in modelled(name):
        if action in EFFECT_ACTIONS:
            effects.append((next(iter(kinds_for(action))), set(needed)))
        elif action not in INTERNAL | unobserved:
            needed |= kinds_for(action) - EFFECT_KINDS
    return effects, needed


@pytest.mark.parametrize("name", NAMES)
def test_every_modelled_read_precedes_the_effect_it_supports(name: str) -> None:
    """No recorded effect, and no recorded hold, rests on a read never made.

    For each effect of the trace, every kind of read the model performs
    before it must appear before the corresponding recorded effect. For a
    trace that ends without an effect, the reads must appear at all. The
    cross-file order of a local delta is recorded only against the ready
    command, so it is owed only there.
    """
    concrete = recorded(name)
    effects, needed = reads_before_effects(name)
    cursor = 0
    for effect, reads in effects:
        position = concrete.index(effect, cursor)
        unordered = set() if effect == "ready-command" else {"local-delta"}
        owed = reads - set(concrete[:position]) - unordered
        assert not owed, f"{name}: {effect} was made before any {sorted(owed)}"
        cursor = position + 1
    assert needed <= set(concrete), (
        f"{name} never made the reads {sorted(needed - set(concrete))}"
    )


def refetched(concrete: list[str]) -> bool:
    """Return whether a PR read follows the last discussion read before the end.

    The end is the ready command when there is one, and the end of the run
    otherwise. The last discussion read is the one that can have supplied
    the replies the decision rests on, so a PR read before it, even one after
    an earlier discussion read, is not the re-fetch the model requires.
    """
    end = concrete.index("ready-command") if "ready-command" in concrete else len(concrete)
    window = concrete[:end]
    if "discussion-read" not in window:
        return False
    last = len(window) - 1 - window[::-1].index("discussion-read")
    return "pr-view" in window[last + 1 :]


@pytest.mark.parametrize("name", NAMES)
def test_the_refetch_and_the_read_back_are_where_the_model_puts_them(name: str) -> None:
    """The two reads whose position is the obligation are checked in place.

    The model re-fetches the candidate after it reads the replies and before
    it decides, and reads the PR back after the ready command. Both are the
    same recorded command as the first observation, so only their position
    distinguishes them.
    """
    concrete, abstract = recorded(name), modelled(name)
    unobserved = set(fixture(name)["unobserved"])
    if "AgentRechecksCandidate" in abstract and "AgentRechecksCandidate" not in unobserved:
        assert refetched(concrete), (
            f"{name} did not re-fetch the candidate after reading the discussion"
        )
    if "AgentReadsBackReady" in abstract:
        after = concrete[concrete.index("ready-command") + 1 :]
        assert "pr-view" in after, f"{name} did not read the transition back"


@pytest.mark.parametrize("name", NAMES)
def test_an_unobserved_step_is_really_absent(name: str) -> None:
    """A recorded difference is stated only while it is true.

    Listing a step as unobserved excuses it from the checks above. If the
    recording does contain it, the entry is stale and must be removed, so
    that the recording is held to the model's order again.
    """
    concrete = recorded(name)
    for action in fixture(name)["unobserved"]:
        if action == "AgentRechecksCandidate":
            assert not refetched(concrete), (
                f"{name} does re-fetch the candidate; remove the unobserved entry"
            )
        else:
            assert not kinds_for(action) & set(concrete), (
                f"{name} does record {action}; remove the unobserved entry"
            )
    assert fixture(name)["note"].strip(), f"{name} states no reason"


@pytest.mark.parametrize(
    ("concrete", "expected"),
    [
        (["discussion-read", "pr-view", "ready-command"], True),
        (["discussion-read", "pr-view", "discussion-read", "ready-command"], False),
        (["pr-view", "discussion-read", "ready-command", "pr-view"], False),
        (["discussion-read", "pr-view"], True),
    ],
    ids=["re-fetched", "reply-read-after-re-fetch", "read-back-only", "no-transition"],
)
def test_the_refetch_must_follow_the_reply_read(concrete: list[str], expected: bool) -> None:
    """A PR read counts only after the discussion read that supplied the replies."""
    assert refetched(concrete) is expected


def test_a_delta_after_the_ready_marker_is_not_evidence_for_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A local check recorded after the transition is placed after it."""
    monkeypatch.setattr(sys.modules[__name__], "cs_kinds", lambda _name: ([], ["local-delta"], True))
    monkeypatch.setattr(
        sys.modules[__name__], "gh_kinds", lambda _name: ["pr-view", "ready-command", "pr-view"]
    )
    assert recorded("any") == ["pr-view", "ready-command", "local-delta", "pr-view"]


@pytest.mark.parametrize("name", NAMES)
def test_a_refused_step_is_absent_from_its_recording(name: str) -> None:
    """The step a trace expects the model to refuse is one the agent never took.

    A refused trace states how many steps run; the step after them is the
    one the model refuses. When that step is an effect, the recording must
    not contain it, so the refusal and the recorded agent agree.
    """
    run = runs()[fixture(name)["run"]]
    if run["expect"] == "pass":
        return
    refused = run["trace"][run["expect"]["executed"]]
    assert refused.startswith("Agent"), f"{name} refuses a step that is not an agent step"
    effects = kinds_for(refused) & EFFECT_KINDS
    assert not effects & set(recorded(name)), (
        f"{name} refuses {refused}, but the recording made {sorted(effects)}"
    )
