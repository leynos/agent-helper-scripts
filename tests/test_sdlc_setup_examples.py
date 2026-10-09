"""Execute the documented title update against an offline GitHub CLI double."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SETUP = ROOT / "skills/sdlc-implementation/references/setup.md"


def title_example(document: str | None = None) -> str:
    """Select the unique title fence, refusing missing or ambiguous examples."""
    source = SETUP.read_text() if document is None else document
    fences = re.findall(r"^```bash\n(.*?)^```$", source, re.M | re.S)
    matches = [fence for fence in fences if "--json title" in fence]
    assert len(matches) == 1, "setup must contain exactly one title update example"
    return matches[0]


def run_title_example(
    tmp_path: Path, titles: list[str], *, fail: str = ""
) -> tuple[subprocess.CompletedProcess[str], list[list[str]]]:
    """Supply controlled title reads and record every CLI argument without network."""
    stub = tmp_path / "gh"
    stub.write_text(
        f"#!{sys.executable}\n"
        "import json, os, pathlib, sys\n"
        "root = pathlib.Path(os.environ['STUB_ROOT'])\n"
        "args = sys.argv[1:]\n"
        "with (root / 'calls').open('a') as log:\n"
        "    log.write(json.dumps(args) + '\\n')\n"
        "calls = (root / 'calls').read_text().splitlines()\n"
        "views = sum(json.loads(line)[1] == 'view' for line in calls)\n"
        "operation = 'view' + str(views) if args[1] == 'view' else 'edit'\n"
        "if operation == os.environ['STUB_FAIL']:\n"
        "    sys.exit(17)\n"
        "if args[1] == 'view':\n"
        "    titles = json.loads(os.environ['STUB_TITLES'])\n"
        "    print(titles[min(views - 1, len(titles) - 1)])\n"
    )
    stub.chmod(0o755)
    env = {
        "PATH": str(tmp_path) + os.pathsep + "/usr/bin:/bin",
        "STUB_ROOT": str(tmp_path),
        "STUB_TITLES": json.dumps(titles),
        "STUB_FAIL": fail,
        "repo": "assigned/repository",
        "pr": "203",
    }
    result = subprocess.run(
        ["/bin/bash", "-c", title_example()],
        env=env, text=True, capture_output=True, check=False, timeout=30,
    )
    calls = [json.loads(line) for line in (tmp_path / "calls").read_text().splitlines()]
    return result, calls


@pytest.mark.parametrize(
    ("original", "expected"),
    [("Plan: Implement feature", "Implement feature"),
     ("Plan: Plan: Implement feature", "Plan: Implement feature")],
    ids=["leading-prefix", "remove-once"],
)
def test_title_example_edits_assigned_pr_and_verifies_readback(
    tmp_path: Path, original: str, expected: str
) -> None:
    """A stable live title loses exactly one prefix and is confirmed after editing."""
    result, calls = run_title_example(tmp_path, [original, original, expected])
    assert result.returncode == 0, result.stderr
    assert calls == [
        ["pr", "view", "203", "--repo", "assigned/repository", "--json", "title", "--jq", ".title"],
        ["pr", "view", "203", "--repo", "assigned/repository", "--json", "title", "--jq", ".title"],
        ["pr", "edit", "203", "--repo", "assigned/repository", "--title", expected],
        ["pr", "view", "203", "--repo", "assigned/repository", "--json", "title", "--jq", ".title"],
    ], "title update must use the assigned PR and verify the exact replacement"


@pytest.mark.parametrize("title", ["Implement feature", "Discuss Plan: feature", "Plan:feature"],
                         ids=["unrelated", "infix", "missing-space"])
def test_title_example_preserves_other_prefixes(tmp_path: Path, title: str) -> None:
    """Only the exact leading prefix followed by a space permits an edit."""
    result, calls = run_title_example(tmp_path, [title])
    assert result.returncode == 0, result.stderr
    assert not any(call[1] == "edit" for call in calls), "unrelated titles must be preserved"


@pytest.mark.parametrize("title", ["Plan: ", "Plan:   "], ids=["prefix-only", "blank-remainder"])
def test_title_example_rejects_empty_replacement(tmp_path: Path, title: str) -> None:
    """Removing a prefix may not create an empty or whitespace-only title."""
    result, calls = run_title_example(tmp_path, [title])
    assert result.returncode != 0, "empty replacement must fail"
    assert not any(call[1] == "edit" for call in calls), "empty replacement must not be published"


def test_title_example_stops_when_second_read_changed(tmp_path: Path) -> None:
    """An intervening human edit detected on the final read prevents overwriting it."""
    result, calls = run_title_example(tmp_path, ["Plan: feature", "Human title"])
    assert result.returncode != 0, "changed live title must stop the update"
    assert not any(call[1] == "edit" for call in calls), "stale title must not overwrite human work"


def test_title_example_rejects_mismatched_readback(tmp_path: Path) -> None:
    """A write is not reported successful when its observed result differs."""
    result, _ = run_title_example(tmp_path, ["Plan: feature", "Plan: feature", "Other title"])
    assert result.returncode != 0, "mismatched readback must require reconciliation"


@pytest.mark.parametrize("failure", ["view1", "view2", "edit", "view3"])
def test_title_example_propagates_cli_failures(tmp_path: Path, failure: str) -> None:
    """Each failed read or write stops rather than claiming an unverified update."""
    result, calls = run_title_example(tmp_path, ["Plan: feature", "Plan: feature", "feature"], fail=failure)
    assert result.returncode != 0, f"{failure} failure must propagate"
    if failure in {"view1", "view2"}:
        assert not any(call[1] == "edit" for call in calls), "failed read must prevent editing"


@pytest.mark.parametrize(
    "document",
    ["No fence", "```bash\ngh --json title\n",
     "```bash\ngh --json title\n```\n```bash\ngh --json title\n```"],
    ids=["missing", "unclosed", "ambiguous"],
)
def test_title_example_extraction_rejects_invalid_documents(document: str) -> None:
    """Missing, unterminated, or duplicate snippets must not select a substitute."""
    with pytest.raises(AssertionError, match="exactly one title update example"):
        title_example(document)


def description_contract(document: str) -> None:
    """Require body preservation and race safeguards in the actual update section."""
    matches = re.findall(
        r"^## Description and final References section\n(.*?)(?=^## |\Z)",
        document, re.M | re.S,
    )
    assert len(matches) == 1, "description update section must be unique"
    instructions = " ".join(matches[0].split())
    for obligation in (
        "Preserve task links, issue-closing keywords, stack information, attribution, and unrelated human-authored content",
        "one final second-level `## References` section",
        "existing references",
        "move its complete content to the end without dropping nested content",
        "Preserve required machine-managed blocks",
        "re-read the remote body immediately before writing to detect intervening edits",
        "Reconcile changes instead of overwriting another editor",
        "Use `gh pr edit --body-file`, then read back the complete body and title",
        "A failed or ambiguous write requires observation before retrying",
    ):
        assert obligation in instructions, f"description section must retain: {obligation}"


def test_description_updates_preserve_body_and_reconcile_writers() -> None:
    """Metadata updates retain existing references and observe writes before retrying."""
    description_contract(SETUP.read_text())


def test_description_contract_rejects_reread_moved_to_unrelated_section() -> None:
    """A reread guard elsewhere cannot protect the described body write procedure."""
    source = SETUP.read_text()
    guard = "re-read the\nremote body immediately before writing to detect intervening edits."
    assert source.count(guard) == 1, "mutation must anchor the actual body reread safeguard"
    mutated = source.replace(guard, "write the body immediately.", 1)
    mutated += "\n## Unrelated notes\n\n" + guard + "\n"
    with pytest.raises(AssertionError, match="description section must retain"):
        description_contract(mutated)
