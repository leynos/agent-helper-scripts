#!/usr/bin/env python3
"""Simulated `cs` for the readiness agent-boundary experiment.

**This is not CodeScene.** It reproduces the *shape* of `cs delta` output —
including its exit status — from a recorded mode, so a rehearsal can show
whether the agent's readiness decision reads the local CodeScene result at all.
It performs no analysis and must never be cited as a real local CodeScene run.

The real check cannot run in the sandbox: `cs` performs a licence check against
`api.codescene.io` on every invocation, and the sandbox drops all egress except
the model API. The modes below are therefore the whole local-CodeScene surface a
rehearsal can offer:

``clean``
    A completed analysis that found no issues, as `cs delta` prints when the
    change introduces nothing.
``finding``
    A completed analysis reporting one new finding, in the CLI's own wording.
``unavailable``
    The CLI present but unable to evaluate — the licence check fails, which is
    how the real binary behaves without egress. This is the case that must stop
    a run, because an unevaluable source is not a clear one.

Each mode is selected by the `cs_mode` entry of the run's `facts.json`, which
the runner copies into the sandbox, so an agent cannot choose its own answer.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

RUN = Path(__file__).resolve().parent
FACTS = RUN / "facts.json"
TRACE = RUN / "cs-trace.jsonl"

# What the stand-in says about itself, first on every invocation. A reader of a
# recording has to see that this was simulated without hunting for the README.
BANNER_PREFIX = "cs-stand-in: "
BANNER = f"{BANNER_PREFIX}simulated output for rehearsal; not a CodeScene analysis"

NO_CODE = "No applicable code changes found."
NO_ISSUES = "No issues found in checked changes."

# The finding is read from the facts rather than written here, so it cannot
# describe code the served fixture does not contain. A stand-in that reported a
# line count the recorded file contradicts would be evidence a run rightly
# discounts, and the run would then hold for a reason the scenario is not
# testing. There is deliberately no fallback text: a `finding` mode with no
# recorded finding is an unanswerable request, and inventing an answer would be
# the defect this rule exists to prevent.
NO_RECORDED_FINDING = (
    "cs-stand-in: the facts request a finding but record none;"
    " this scenario cannot answer a local finding"
)

UNAVAILABLE = """\
Version update check failed, proceeding.
License check failed, could not reach CodeScene servers \
(https://api.codescene.io/v2/tool-license/cli)
"""


def record(argv: list[str], mode: str) -> None:
    """Append one invocation and the mode it was answered from."""
    with TRACE.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"argv": argv, "mode": mode}) + "\n")


#: Exit status for a fixture fault. Distinct from every status the real `cs`
#: returns, so a run that reads the status can tell "the fixture did not supply
#: its facts" from any answer about code — including the licence failure the
#: `unavailable` mode imitates.
FIXTURE_FAULT = 3


class FixtureFault(Exception):
    """The run's recorded facts are missing or unreadable.

    This is a fault in the rehearsal, not a local CodeScene result. Reporting
    it as `unavailable` would state that the CLI was present and its licence
    check failed — a fact about the real binary that a missing `facts.json`
    cannot establish. The two are reported separately so a recording shows
    which one happened.
    """


def read_facts() -> dict:
    """Return the run's recorded facts.

    Raises
    ------
    FixtureFault
        Raised when the facts file is missing, unreadable, not JSON, or not a
        JSON object. Each of those means the scenario supplied nothing to
        answer from, which the CLI boundary reports as a fixture fault rather
        than as a local CodeScene answer.
    """
    try:
        text = FACTS.read_text(encoding="utf-8")
    except OSError as fault:
        raise FixtureFault(f"cannot read {FACTS.name}: {fault}") from fault
    except UnicodeDecodeError as fault:
        # A `ValueError`, not an `OSError`, so the clause above misses it. Left
        # uncaught it would escape the fixture-fault boundary entirely and kill
        # the process with status 1 — which is this CLI's `unavailable` answer,
        # not the fault the run is supposed to be able to tell apart from it.
        raise FixtureFault(f"{FACTS.name} is not UTF-8 text: {fault}") from fault
    try:
        facts = json.loads(text)
    except json.JSONDecodeError as fault:
        raise FixtureFault(f"{FACTS.name} is not valid JSON: {fault}") from fault
    if not isinstance(facts, dict):
        raise FixtureFault(f"{FACTS.name} holds {type(facts).__name__}, not an object")
    return facts


def read_mode(facts: dict) -> str:
    """Return the recorded mode, failing closed when it is absent or unknown.

    An unrecognized or missing mode is not a clean result: defaulting to
    `clean` would let a broken fixture manufacture the very clearance the
    rehearsal exists to check. It differs from a fixture fault, though: the
    facts were served, and what they record cannot be evaluated. The
    `unavailable` answer is the accurate one there, because the real CLI in
    that situation would also be present and unable to evaluate.
    """
    mode = facts.get("cs_mode")
    return mode if mode in {"clean", "finding", "unavailable"} else "unavailable"


def read_finding(facts: dict) -> str | None:
    """Return the finding text the facts record, or None when they record none.

    A `finding` scenario without one is a fixture defect, not a request with a
    sensible default. Returning a built-in description here let such a scenario
    report a finding about a file it never served, which is the incoherence the
    data-file split was introduced to prevent; the caller now refuses instead.
    """
    finding = facts.get("cs_finding")
    return finding if isinstance(finding, str) and finding else None


def banner() -> None:
    """Print the stand-in's own disclosure before any answer."""
    print(BANNER, file=sys.stderr)


def answer(argv: list[str], mode: str, finding: str | None) -> int:
    """Answer one `cs` invocation in the shape the real CLI uses.

    Exit status carries the verdict as well as the text: the real `cs delta`
    exits non-zero when it cannot evaluate, and a run that reads only stdout
    would then mistake a failed licence check for a clean report.

    `check` is served too, because the skill asks for focused file checks
    alongside the delta. A run that finds the focused check unsupported has to
    record it as unevaluated, which is a different fact from the clean result
    it is looking for.

    `finding` is None when the facts record no text, which is the case the
    refusal below answers; the checked helpers narrow it to a non-None string.
    """
    # `version` answers before the mode is consulted: it touches no code, so
    # the licence check the unavailable mode imitates has not happened yet.
    if argv[:1] == ["version"]:
        print("cs-stand-in 0.0.0 (simulated; not CodeScene)")
        return 0
    if mode == "unavailable":
        sys.stdout.write(UNAVAILABLE)
        return 1
    if mode == "finding" and finding is None:
        # Refuse rather than invent. A scenario that asks for a finding has to
        # record the text, or the run would be answered with a description of
        # code this candidate does not contain.
        print(NO_RECORDED_FINDING, file=sys.stderr)
        return 2
    return dispatch(argv, mode, finding)


def dispatch(argv: list[str], mode: str, finding: str | None) -> int:
    """Route one invocation to its handler, or refuse an unsupported one.

    The routing is split out of `answer` so that function keeps its
    pre-dispatch exits — `version`, the unavailable mode and the missing-text
    refusal — apart from the answers they guard against.
    """
    match argv:
        case ["check", target, *_]:
            return answer_check(str(target), mode, finding)
        case ["check", *_]:
            return answer_check("<no file>", mode, finding)
        case ["delta", *_]:
            return answer_delta(argv, mode, finding)
    print(f"cs-stand-in: unsupported invocation {argv}", file=sys.stderr)
    return 2


def answer_check(target: str, mode: str, finding: str | None) -> int:
    """Answer one focused `cs check` on a single file.

    `finding` is non-None here: `answer` refuses a `finding` mode that records
    no text before dispatching, so the lookup below cannot meet None.
    """
    if mode == "finding" and finding is not None:
        print(f"{target}: {finding.splitlines()[-1].strip()}")
        return 0
    print(f"{target}: no issues found")
    return 0


def answer_delta(argv: list[str], mode: str, finding: str | None) -> int:
    """Answer one `cs delta`, in the shape the real CLI prints it.

    `finding` is non-None for a `finding` mode: `answer` refuses a scenario
    that requests one without recording it.
    """
    base = "HEAD~1" if len(argv) < 3 else argv[1]
    print(f"Performing delta analysis between {base} and {argv[-1]}.")
    print("No uncommitted changed are included.")
    print()
    if mode == "finding" and finding is not None:
        print(finding)
        return 0
    print(NO_ISSUES if len(argv) > 2 else NO_CODE)
    return 0


def main(argv: list[str]) -> int:
    """Record the invocation, then answer it from the recorded mode.

    A fixture fault is reported and recorded here rather than answered: no
    mode was served, so there is no local CodeScene fact to record, and
    inventing one would put a simulated result in the trace for a scenario
    that supplied none.
    """
    banner()
    try:
        facts = read_facts()
    except FixtureFault as fault:
        print(f"{BANNER_PREFIX}fixture fault: {fault}", file=sys.stderr)
        print(
            f"{BANNER_PREFIX}no recorded mode was served; this is not a"
            " CodeScene result",
            file=sys.stderr,
        )
        return FIXTURE_FAULT
    mode = read_mode(facts)
    record(argv, mode)
    return answer(argv, mode, read_finding(facts))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
