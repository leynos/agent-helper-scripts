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
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


PY_TS_EXTS = {".py", ".pyi", ".ts", ".tsx", ".mts", ".cts"}
RUST_EXTS = {".rs"}
MD_EXTS = {".md", ".mdx", ".markdown"}


def run(cmd: List[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=str(cwd), text=True, capture_output=True)


def truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    half = max_chars // 2
    return text[:half] + "\n... (output truncated) ...\n" + text[-half:]


def repo_root(start_cwd: Path) -> Tuple[Optional[Path], Optional[str]]:
    p = run(["git", "rev-parse", "--show-toplevel"], start_cwd)
    if p.returncode != 0:
        err = (p.stderr.strip() or p.stdout.strip() or "not a git repository")
        return None, err
    root = p.stdout.strip()
    if not root:
        return None, "git rev-parse --show-toplevel returned empty output"
    return Path(root), None


def ensure_base_ref(repo: Path, base_ref: str, always_fetch: bool) -> Tuple[bool, Optional[str], bool]:
    """
    Ensures refs/remotes/origin/main exists (for base_ref == origin/main).
    If base_ref isn't origin/main, we just verify it resolves as a ref-ish.
    Returns: ok, error, fetched
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


def merge_base(repo: Path, base_ref: str) -> Tuple[Optional[str], Optional[str]]:
    p = run(["git", "merge-base", base_ref, "HEAD"], repo)
    if p.returncode != 0:
        return None, f"git merge-base {base_ref} HEAD failed: {p.stderr.strip() or p.stdout.strip()}"
    base = p.stdout.strip()
    if not base:
        return None, "git merge-base returned empty output"
    return base, None


def changed_files(repo: Path, base_commit: str) -> Tuple[Optional[List[str]], Optional[str]]:
    changed: Set[str] = set()

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


def detect_categories(files: List[str]) -> Dict[str, bool]:
    cats = {"python_ts": False, "rust": False, "markdown": False}
    for f in files:
        ext = Path(f).suffix.lower()
        if ext in PY_TS_EXTS:
            cats["python_ts"] = True
        if ext in RUST_EXTS:
            cats["rust"] = True
        if ext in MD_EXTS:
            cats["markdown"] = True
    return cats


def parse_make_targets(make_stdout: str) -> Set[str]:
    targets: Set[str] = set()
    rule_re = re.compile(r"^([^\s:#=]+(?:\s+[^\s:#=]+)*)\s*::?\s*.*$")
    for line in make_stdout.splitlines():
        if not line:
            continue
        if line.startswith("#") or line.startswith("\t") or line.startswith(" "):
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


def get_make_targets(repo: Path) -> Tuple[Optional[Set[str]], Optional[str]]:
    try:
        p = run(["make", "-qp", "--no-print-directory"], repo)
    except FileNotFoundError:
        return None, "make not found on PATH"

    # make -q can return 0 or 1 without being an error; 2 means failure
    if p.returncode == 2:
        return None, p.stderr.strip() or p.stdout.strip() or "make -qp failed"

    return parse_make_targets(p.stdout), None


def dedup_preserve_order(items: List[str]) -> List[str]:
    out: List[str] = []
    seen: Set[str] = set()
    for x in items:
        if x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out


def run_make(repo: Path, kind: str, targets: List[str], max_out: int) -> Dict[str, Any]:
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


def format_reason(state: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("Post-turn checks failed.")

    if state.get("error"):
        lines.append("")
        lines.append(f"Error: {state['error']}")

    base_ref = state.get("base_ref") or "?"
    base_commit = state.get("base_commit") or "?"
    lines.append("")
    lines.append(f"Diff base: {base_ref} ({base_commit})")

    changed = state.get("changed_files") or []
    lines.append("")
    lines.append(f"Changed files vs {base_ref}: {len(changed)}")
    for f in changed[:60]:
        lines.append(f"- {f}")
    if len(changed) > 60:
        lines.append(f"- … (+{len(changed) - 60} more)")

    cats = state.get("categories") or {}
    detected: List[str] = []
    if cats.get("python_ts"):
        detected.append("Python/TypeScript")
    if cats.get("rust"):
        detected.append("Rust")
    if cats.get("markdown"):
        detected.append("Markdown")
    if detected:
        lines.append("")
        lines.append("Detected change types: " + ", ".join(detected))

    if state.get("make_targets_requested"):
        lines.append("")
        lines.append("Requested make targets: " + " ".join(state["make_targets_requested"]))
    if state.get("make_targets_run"):
        lines.append("Targets run: " + " ".join(state["make_targets_run"]))
    if state.get("make_targets_skipped"):
        lines.append("Targets skipped (missing): " + " ".join(state["make_targets_skipped"]))

    failures = [c for c in (state.get("commands") or []) if int(c.get("exit_code", 0)) != 0]
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


def main() -> int:
    # Claude Code hook input arrives as JSON on stdin (but don’t assume it’s present/valid).
    hook_input: Dict[str, Any] = {}
    try:
        hook_input = json.load(sys.stdin)
    except Exception:
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
    max_out = int(os.environ.get("POST_TURN_MAX_OUTPUT_CHARS", "12000"))

    state: Dict[str, Any] = {
        "ok": True,
        "base_ref": base_ref,
        "changed_files": [],
        "categories": {"python_ts": False, "rust": False, "markdown": False},
        "make_targets_requested": [],
        "make_targets_run": [],
        "make_targets_skipped": [],
        "commands": [],
        "fetched": False,
    }

    repo, err = repo_root(start_cwd)
    if repo is None:
        # Not a git repo: allow stop quietly.
        return 0

    ok, err, fetched = ensure_base_ref(repo, base_ref, always_fetch=always_fetch)
    state["fetched"] = fetched
    if not ok:
        # If we cannot establish the base ref, block (you asked for strictness).
        state["ok"] = False
        state["error"] = err
        print(json.dumps({"decision": "block", "reason": format_reason(state)}))
        return 0

    base_commit, err = merge_base(repo, base_ref)
    if base_commit is None:
        state["ok"] = False
        state["error"] = err
        print(json.dumps({"decision": "block", "reason": format_reason(state)}))
        return 0
    state["base_commit"] = base_commit

    files, err = changed_files(repo, base_commit)
    if files is None:
        state["ok"] = False
        state["error"] = err
        print(json.dumps({"decision": "block", "reason": format_reason(state)}))
        return 0

    state["changed_files"] = files
    if not files:
        # No modifications relative to merge-base => allow.
        return 0

    cats = detect_categories(files)
    state["categories"] = cats

    # Decide what we'd like to run.
    requested: List[str] = []
    if cats["python_ts"]:
        requested += ["check-fmt", "lint", "typecheck"]
    if cats["rust"]:
        requested += ["check-fmt", "lint"]
    if cats["markdown"]:
        requested += ["markdownlint"]

    requested = dedup_preserve_order(requested)
    state["make_targets_requested"] = requested

    if not requested:
        # Changes exist, but none match the watched extensions => allow.
        return 0

    make_targets, make_err = get_make_targets(repo)
    if make_targets is None:
        state["ok"] = False
        state["error"] = f"Could not enumerate make targets: {make_err}"
        print(json.dumps({"decision": "block", "reason": format_reason(state)}))
        return 0

    run_targets = [t for t in requested if t in make_targets]
    skip_targets = [t for t in requested if t not in make_targets]
    state["make_targets_run"] = run_targets
    state["make_targets_skipped"] = skip_targets

    # Group execution so markdown runs even if code checks fail.
    commands: List[Dict[str, Any]] = []

    code_targets: List[str] = []
    if cats["python_ts"]:
        code_targets += ["check-fmt", "lint", "typecheck"]
    if cats["rust"]:
        code_targets += ["check-fmt", "lint"]
    code_targets = [t for t in dedup_preserve_order(code_targets) if t in make_targets]

    md_targets: List[str] = []
    if cats["markdown"] and "markdownlint" in make_targets:
        md_targets = ["markdownlint"]

    if code_targets:
        commands.append(run_make(repo, "code", code_targets, max_out))
    if md_targets:
        commands.append(run_make(repo, "markdown", md_targets, max_out))

    state["commands"] = commands

    # If we ran nothing because targets are missing, treat as OK (per your “only if targets exist” rule).
    if not commands:
        return 0

    ok_all = all(int(c.get("exit_code", 0)) == 0 for c in commands)
    if ok_all:
        return 0

    state["ok"] = False
    print(json.dumps({"decision": "block", "reason": format_reason(state)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

