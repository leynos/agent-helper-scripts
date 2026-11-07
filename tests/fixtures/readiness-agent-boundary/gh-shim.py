#!/usr/bin/env python3
"""Recorded GitHub stand-in for the readiness agent-boundary experiment.

The scenario directory is derived from this file's own location, not from the
environment, so a run reveals no harness path through `env` and cannot be
redirected by it. Every invocation is appended to `gh-trace.jsonl` next to the
facts before an answer is produced; the answer itself comes from
`facts.json`, which holds this repository's real response shapes.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

RUN = Path(__file__).resolve().parent
SCENARIO = RUN / "facts.json"
TRACE = RUN / "gh-trace.jsonl"
STATE = RUN / "state.json"


def record(argv: list[str]) -> None:
    """Append one invocation to the trace before answering it."""
    with TRACE.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(argv) + "\n")


def fail(message: str, status: int = 1) -> int:
    """Report an unsupported or unrecorded invocation on standard error."""
    print(message, file=sys.stderr)
    return status


def emit(payload: object, *, slurp: bool = False) -> int:
    """Print a recorded payload, wrapped in a list when `--slurp` was given."""
    if isinstance(payload, str):
        print(payload)
        return 0
    print(json.dumps([payload] if slurp else payload))
    return 0


VALUE_FLAGS = {"--hostname", "--method", "-X", "-f", "-F", "-H", "--jq", "-q"}


def api_url(argv: list[str]) -> str:
    """Return the first operand that is neither a flag nor a flag's value."""
    skip = False
    for part in argv[1:]:
        if skip:
            skip = False
            continue
        if part in VALUE_FLAGS:
            skip = True
            continue
        if part.startswith("-") or part == "GET":
            continue
        return part
    return ""


def read_facts() -> dict:
    """Return this run's facts, with any post-transition state applied."""
    facts = json.loads(SCENARIO.read_text(encoding="utf-8"))
    if STATE.exists():
        facts["pr"] = {**facts["pr"], **json.loads(STATE.read_text(encoding="utf-8"))}
    return facts


def answer(argv: list[str]) -> int:
    """Answer one invocation from the recorded facts."""
    facts = read_facts()
    slurp = "--slurp" in argv
    if argv[:2] == ["pr", "view"]:
        return emit(facts["pr"])
    if argv[:2] == ["pr", "ready"]:
        STATE.write_text(json.dumps({"isDraft": False}), encoding="utf-8")
        return emit(facts["pr_ready_response"])
    if argv[:2] == ["pr", "checks"]:
        return emit(facts["pr_checks"])
    if argv[:1] == ["api"]:
        url = api_url(argv)
        if url == "user":
            return emit(facts["login"])
        for pattern, payload in facts["api"].items():
            if re.search(pattern, url):
                return emit(payload, slurp=slurp)
        return fail(f"gh: Not Found (HTTP 404)")
    if argv[:2] == ["auth", "status"]:
        return emit(f"Logged in to github.com as {facts['login']}")
    return fail(f"gh: unsupported invocation {argv}")


def main(argv: list[str]) -> int:
    """Record the invocation, then answer it."""
    record(argv)
    return answer(argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
