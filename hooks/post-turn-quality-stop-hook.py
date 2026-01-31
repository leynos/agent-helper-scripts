#!/usr/bin/env python3
"""
Claude Code Stop-hook quality gate.

At "turn end" (Claude Code Stop hook):
1) Ensure refs/remotes/origin/main exists (git fetch only if missing by default)
2) Compute changed files vs origin/main using merge-base(origin/main, HEAD)
3) If changes exist:
   - If any Python/TypeScript files changed: run `make check-fmt lint typecheck` (only targets that exist)
   - If any Rust files changed:             run `make check-fmt lint`          (only targets that exist)
   - If any Markdown files changed:         run `make markdownlint`            (only targets that exist)
4) If any invoked command fails, BLOCK the stop with a detailed reason.

Behaviour knobs (env vars):
- POST_TURN_ALWAYS_FETCH=1   -> always `git fetch origin main` (otherwise only if origin/main missing)
- POST_TURN_BASE_REF=...     -> override base ref (default: origin/main)
- POST_TURN_MAX_OUTPUT_CHARS -> truncate per-command output (default: 12000)

Claude Code contract:
- Reads JSON hook input from stdin (but works even if stdin isn't JSON)
- On failure: prints JSON {"decision":"block","reason":"..."} to stdout and exits 0
- On success: prints nothing and exits 0
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


PY_TS_EXTS = {".py", ".pyi", ".ts", ".tsx", ".mts", ".cts"}
RUST_EXTS = {".rs"}
MD_EXTS = {".md", ".mdx", ".markdown"}

CATS_TO_TARGETS: dict[str, list[str]] = {
    "python_ts": ["check-fmt", "lint", "typecheck"],
    "rust": ["check-fmt", "lint"],
    "markdown": ["markdownlint"],
}
CODE_CATS = {"python_ts", "rust"}
MD_CATS = {"markdown"}


def default_categories() -> dict[str, bool]:
    return {"python_ts": False, "rust": False, "markdown": False}


@dataclass
class HookState:
    ok: bool = True
    base_ref: str = "origin/main"
    base_commit: str | None = None
    changed_files: list[str] = field(default_factory=list)
    categories: dict[str, bool] = field(default_factory=default_categories)
    make_targets_requested: list[str] = field(default_factory=list)
    make_targets_run: list[str] = field(default_factory=list)
    make_targets_skipped: list[str] = field(default_factory=list)
    commands: list[dict[str, Any]] = field(default_factory=list)
    fetched: bool = False
    error: str | None = None


def run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - command and args are controlled (no shell, no user-supplied command strings).
        cmd, cwd=str(cwd), text=True, capture_output=True
    )


def truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    half = max_chars // 2
    return text[:half] + "\n... (output truncated) ...\n" + text[-half:]


def repo_root(start_cwd: Path) -> tuple[Path | None, str | None]:
    p = run(["git", "rev-parse", "--show-toplevel"], start_cwd)
    if p.returncode != 0:
        err = (p.stderr.strip() or p.stdout.strip() or "not a git repository")
        return None, err
    root = p.stdout.strip()
    if not root:
        return None, "git rev-parse --show-toplevel returned empty output"
    return Path(root), None


def ensure_base_ref(
    repo: Path,
    base_ref: str,
    *,
    always_fetch: bool,
) -> tuple[bool, str | None, bool]:
    """
    Ensures refs/remotes/origin/main exists (for base_ref == origin/main).
    If base_ref isn't origin/main, we just verify it resolves as a ref-ish.

    Parameters
    ----------
    repo
        Repository root path.
    base_ref
        Base git ref used to compute the merge-base.
    always_fetch
        If True, always fetch origin/main when base_ref is origin/main.

    Returns
    -------
    tuple[bool, str | None, bool]
        ok, error message (if any), fetched.
    """
    fetched = False

    # If base_ref is origin/main, ensure 'origin' exists and fetch as needed.
    if base_ref == "origin/main":
        remotes = run(["git", "remote"], repo)
        if remotes.returncode != 0:
            return False, f"git remote failed: {remotes.stderr.strip() or remotes.stdout.strip()}", fetched
        if "origin" not in remotes.stdout.split():
            return False, "git remote 'origin' not found", fetched

        if always_fetch:
            fetch = run(["git", "fetch", "--quiet", "origin", "main"], repo)
            fetched = True
            if fetch.returncode != 0:
                return False, f"git fetch origin main failed: {fetch.stderr.strip() or fetch.stdout.strip()}", fetched
        else:
            verify = run(["git", "show-ref", "--verify", "--quiet", "refs/remotes/origin/main"], repo)
            if verify.returncode != 0:
                fetch = run(["git", "fetch", "--quiet", "origin", "main"], repo)
                fetched = True
                if fetch.returncode != 0:
                    return False, f"git fetch origin main failed: {fetch.stderr.strip() or fetch.stdout.strip()}", fetched

                verify2 = run(["git", "show-ref", "--verify", "--quiet", "refs/remotes/origin/main"], repo)
                if verify2.returncode != 0:
                    return False, "origin/main still missing after fetch", fetched

        # Final sanity: can we rev-parse it?
        rp = run(["git", "rev-parse", "--verify", "--quiet", base_ref], repo)
        if rp.returncode != 0:
            return False, f"Cannot resolve {base_ref}", fetched
        return True, None, fetched

    # For other base refs, just ensure it resolves.
    rp = run(["git", "rev-parse", "--verify", "--quiet", base_ref], repo)
    if rp.returncode != 0:
        return False, f"Cannot resolve base ref '{base_ref}'", fetched
    return True, None, fetched


def merge_base(repo: Path, base_ref: str) -> tuple[str | None, str | None]:
    p = run(["git", "merge-base", base_ref, "HEAD"], repo)
    if p.returncode != 0:
        return None, f"git merge-base {base_ref} HEAD failed: {p.stderr.strip() or p.stdout.strip()}"
    base = p.stdout.strip()
    if not base:
        return None, "git merge-base returned empty output"
    return base, None


def changed_files(repo: Path, base_commit: str) -> tuple[list[str] | None, str | None]:
    changed: set[str] = set()

    # Tracked changes (unstaged and staged) relative to base_commit
    for args in (
        ["git", "diff", "--name-only", base_commit],
        ["git", "diff", "--cached", "--name-only", base_commit],
    ):
        p = run(args, repo)
        if p.returncode != 0:
            return None, f"{' '.join(args)} failed: {p.stderr.strip() or p.stdout.strip()}"
        for line in p.stdout.splitlines():
            line = line.strip()
            if line:
                changed.add(line)

    # Untracked (but not ignored)
    u = run(["git", "ls-files", "--others", "--exclude-standard"], repo)
    if u.returncode != 0:
        return None, f"git ls-files failed: {u.stderr.strip() or u.stdout.strip()}"
    for line in u.stdout.splitlines():
        line = line.strip()
        if line:
            changed.add(line)

    return sorted(changed), None


def detect_categories(files: list[str]) -> dict[str, bool]:
    cats = default_categories()
    for f in files:
        ext = Path(f).suffix.lower()
        if ext in PY_TS_EXTS:
            cats["python_ts"] = True
        if ext in RUST_EXTS:
            cats["rust"] = True
        if ext in MD_EXTS:
            cats["markdown"] = True
    return cats


def parse_make_targets(make_stdout: str) -> set[str]:
    targets: set[str] = set()
    rule_re = re.compile(r"^([^\s:#=]+(?:\s+[^\s:#=]+)*)\s*::?\s*.*$")
    for line in make_stdout.splitlines():
        if not line:
            continue
        if line.startswith(("#", "\t", " ")):
            continue
        m = rule_re.match(line)
        if not m:
            continue
        lhs = m.group(1)
        for t in lhs.split():
            if "%" in t:
                continue
            targets.add(t)
    return targets


def is_missing_makefile(output: str) -> bool:
    lowered = output.lower()
    return "no makefile found" in lowered


def get_make_targets(repo: Path) -> tuple[set[str] | None, str | None]:
    try:
        p = run(["make", "-qp", "--no-print-directory"], repo)
    except FileNotFoundError:
        return None, "make not found on PATH"

    # make -q can return 0 or 1 without being an error; 2 means failure
    if p.returncode == 2:
        combined = f"{p.stderr.strip()}\n{p.stdout.strip()}".strip()
        if is_missing_makefile(combined):
            return set(), None
        return None, combined or "make -qp failed"

    return parse_make_targets(p.stdout), None


def dedup_preserve_order(items: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for x in items:
        if x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out


def run_make(repo: Path, kind: str, targets: list[str], max_out: int) -> dict[str, Any]:
    if not targets:
        return {"kind": kind, "cmd": "", "exit_code": 0, "stdout": "", "stderr": ""}

    p = run(["make", "--no-print-directory", *targets], repo)
    return {
        "kind": kind,
        "cmd": "make " + " ".join(targets),
        "exit_code": int(p.returncode),
        "stdout": truncate(p.stdout, max_out),
        "stderr": truncate(p.stderr, max_out),
    }


def format_reason(state: HookState) -> str:
    lines: list[str] = []
    lines.append("Post-turn checks failed.")

    if state.error:
        lines.append("")
        lines.append(f"Error: {state.error}")

    base_ref = state.base_ref or "?"
    base_commit = state.base_commit or "?"
    lines.append("")
    lines.append(f"Diff base: {base_ref} ({base_commit})")

    changed = state.changed_files
    lines.append("")
    lines.append(f"Changed files vs {base_ref}: {len(changed)}")
    for f in changed[:60]:
        lines.append(f"- {f}")
    if len(changed) > 60:
        lines.append(f"- … (+{len(changed) - 60} more)")

    cats = state.categories
    detected: list[str] = []
    if cats.get("python_ts"):
        detected.append("Python/TypeScript")
    if cats.get("rust"):
        detected.append("Rust")
    if cats.get("markdown"):
        detected.append("Markdown")
    if detected:
        lines.append("")
        lines.append("Detected change types: " + ", ".join(detected))

    if state.make_targets_requested:
        lines.append("")
        lines.append("Requested make targets: " + " ".join(state.make_targets_requested))
    if state.make_targets_run:
        lines.append("Targets run: " + " ".join(state.make_targets_run))
    if state.make_targets_skipped:
        lines.append("Targets skipped (missing): " + " ".join(state.make_targets_skipped))

    failures = [c for c in state.commands if int(c.get("exit_code", 0)) != 0]
    for c in failures:
        cmd = c.get("cmd", "")
        code = c.get("exit_code", "?")
        combined = "\n".join([x for x in [c.get("stdout", ""), c.get("stderr", "")] if x]).strip()

        lines.append("")
        lines.append(f"Command failed (exit {code}): {cmd}")
        lines.append("```")
        lines.append(combined or "(no output captured)")
        lines.append("```")

    lines.append("")
    lines.append("Fix the failures above. The checks will re-run at the end of the next turn.")
    return "\n".join(lines)


def block_and_print(state: HookState) -> int:
    payload = {"decision": "block", "reason": format_reason(state)}
    print(json.dumps(payload))
    return 0


def targets_for_categories(
    categories: dict[str, bool],
    *,
    include: set[str] | None = None,
) -> list[str]:
    requested: list[str] = []
    for category, enabled in categories.items():
        if not enabled:
            continue
        if include is not None and category not in include:
            continue
        requested.extend(CATS_TO_TARGETS.get(category, []))
    return dedup_preserve_order(requested)


def main() -> int:
    # Claude Code hook input arrives as JSON on stdin (but don't assume it's present/valid).
    hook_input: dict[str, Any] = {}
    try:
        hook_input = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        hook_input = {}

    # Choose a sensible cwd.
    cwd_str = (
        hook_input.get("cwd")
        or os.environ.get("CLAUDE_PROJECT_DIR")
        or os.getcwd()
    )
    start_cwd = Path(cwd_str)

    base_ref = os.environ.get("POST_TURN_BASE_REF", "origin/main")
    always_fetch = os.environ.get("POST_TURN_ALWAYS_FETCH", "").strip() in {"1", "true", "TRUE", "yes", "YES"}
    max_out_raw = os.environ.get("POST_TURN_MAX_OUTPUT_CHARS", "12000")
    try:
        max_out = int(max_out_raw)
    except ValueError:
        max_out = 12000

    state = HookState(base_ref=base_ref)

    repo, err = repo_root(start_cwd)
    if repo is None:
        # Not a git repo: allow stop quietly.
        return 0

    ok, err, fetched = ensure_base_ref(repo, base_ref, always_fetch=always_fetch)
    state.fetched = fetched
    if not ok:
        # If we cannot establish the base ref, block (you asked for strictness).
        state.ok = False
        state.error = err
        return block_and_print(state)

    base_commit, err = merge_base(repo, base_ref)
    if base_commit is None:
        state.ok = False
        state.error = err
        return block_and_print(state)
    state.base_commit = base_commit

    files, err = changed_files(repo, base_commit)
    if files is None:
        state.ok = False
        state.error = err
        return block_and_print(state)

    state.changed_files = files
    if not files:
        # No modifications relative to merge-base => allow.
        return 0

    cats = detect_categories(files)
    state.categories = cats

    # Decide what we'd like to run.
    requested = targets_for_categories(cats)
    state.make_targets_requested = requested

    if not requested:
        # Changes exist, but none match the watched extensions => allow.
        return 0

    make_targets, make_err = get_make_targets(repo)
    if make_targets is None:
        state.ok = False
        state.error = f"Could not enumerate make targets: {make_err}"
        return block_and_print(state)

    run_targets = [t for t in requested if t in make_targets]
    skip_targets = [t for t in requested if t not in make_targets]
    state.make_targets_run = run_targets
    state.make_targets_skipped = skip_targets

    # Group execution so markdown runs even if code checks fail.
    commands: list[dict[str, Any]] = []

    code_targets = [
        t for t in targets_for_categories(cats, include=CODE_CATS) if t in make_targets
    ]
    md_targets = [
        t for t in targets_for_categories(cats, include=MD_CATS) if t in make_targets
    ]

    if code_targets:
        commands.append(run_make(repo, "code", code_targets, max_out))
    if md_targets:
        commands.append(run_make(repo, "markdown", md_targets, max_out))

    state.commands = commands

    # If we ran nothing because targets are missing, treat as OK (per your “only if targets exist” rule).
    if not commands:
        return 0

    ok_all = all(int(c.get("exit_code", 0)) == 0 for c in commands)
    if ok_all:
        return 0

    state.ok = False
    return block_and_print(state)


if __name__ == "__main__":
    raise SystemExit(main())
