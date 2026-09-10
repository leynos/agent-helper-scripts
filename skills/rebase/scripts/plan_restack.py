# /// script
# requires-python = ">=3.13"
# dependencies = ["cyclopts>=4,<5"]
# ///
"""Prepare, but never execute, a squash-restack plan for human/agent review.

Only GitHub metadata and real Git ancestry inform the plan. The caller identifies
an already confirmed squash-merged parent PR. Fetching creates a private evidence
ref; discovery never moves a branch, changes the worktree, rebases, or pushes.
"""

from __future__ import annotations

import dataclasses
import json
import re
import subprocess
import sys
import uuid
from pathlib import Path

PARENT_QUERY = (
    "{number, merged, merged_at, head_sha: .head.sha, head_ref: .head.ref, "
    "base_ref: .base.ref, base_repository: .base.repo.full_name, "
    "landed: .merge_commit_sha}"
)
REBASE_PREFIX = (
    "git",
    "-c",
    "merge.conflictStyle=zdiff3",
    "rebase",
    "--merge",
    "--no-fork-point",
    "--no-update-refs",
    "--no-autostash",
    "--reapply-cherry-picks",
    "--keep-empty",
    "--empty=stop",
    "--onto",
)
OID_PATTERN = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
REPOSITORY_PATTERN = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")


class PlanError(RuntimeError):
    """Discovery cannot establish a safe, reviewable replay range."""


@dataclasses.dataclass(frozen=True)
class Request:
    """Explicit identities supplied by the operator, not inferred from titles."""

    repository: Path
    branch: str
    target_ref: str
    parent_repository: str
    parent_pr: int
    boundary_ref: str | None = None


def command(repository: Path, *argv: str, allowed: tuple[int, ...] = (0,)) -> str:
    """Run an argv without a shell; distinguish negative answers from failures."""
    try:
        result = subprocess.run(
            argv,
            cwd=repository,
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PlanError(f"Cannot run {argv[0]}: {exc}") from exc
    if result.returncode not in allowed:
        detail = result.stderr.strip() or result.stdout.strip()
        raise PlanError(f"{argv[0]} exited {result.returncode}: {detail}")
    return result.stdout.strip()


def git(repository: Path, *args: str) -> str:
    """Run a Git query or the narrowly scoped evidence fetch."""
    return command(repository, "git", *args)


def commit(repository: Path, ref: str) -> str:
    """Resolve exactly one commit without treating a user ref as an option."""
    return git(
        repository, "rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}"
    )


def ancestor(repository: Path, older: str, newer: str) -> bool:
    """Ask a real graph query, propagating errors rather than treating them as no."""
    # rev-list errors remain errors; empty output means every older commit is
    # reachable from newer. Inputs are already resolved full commit IDs.
    return not git(repository, "rev-list", "--max-count=1", older, f"^{newer}")


def preflight(request: Request) -> tuple[str, str]:
    """Freeze identities and refuse incomplete history or an occupied checkout."""
    if not REPOSITORY_PATTERN.fullmatch(request.parent_repository) or any(
        part in {".", ".."} for part in request.parent_repository.split("/")
    ):
        raise PlanError("Parent repository must be an explicit GitHub owner/name")
    if type(request.parent_pr) is not int or request.parent_pr <= 0:
        raise PlanError("Parent PR must be a positive integer")
    if not request.branch or request.branch.startswith("-"):
        raise PlanError("Branch must be an explicit local branch name, not an option")
    git(request.repository, "check-ref-format", f"refs/heads/{request.branch}")
    if git(request.repository, "rev-parse", "--is-shallow-repository") != "false":
        raise PlanError("Shallow history cannot establish the complete replay range")
    for name in (
        "rebase-merge",
        "rebase-apply",
        "MERGE_HEAD",
        "CHERRY_PICK_HEAD",
        "REVERT_HEAD",
        "sequencer",
    ):
        path = Path(git(request.repository, "rev-parse", "--git-path", name))
        if not path.is_absolute():
            path = request.repository / path
        if path.exists():
            raise PlanError(f"An active Git operation exists: {name}")
    if git(request.repository, "status", "--porcelain=v1", "--untracked-files=all"):
        raise PlanError("Preserve staged, unstaged and untracked work before planning")
    return (
        commit(request.repository, f"refs/heads/{request.branch}"),
        commit(request.repository, request.target_ref),
    )


def parent_metadata(request: Request) -> dict[str, object]:
    """Validate the CLI response before using any source or landing identity."""
    output = command(
        request.repository,
        "gh",
        "api",
        f"repos/{request.parent_repository}/pulls/{request.parent_pr}",
        "--jq",
        PARENT_QUERY,
    )
    try:
        metadata = json.loads(output)
    except json.JSONDecodeError as exc:
        raise PlanError("gh returned malformed parent metadata") from exc
    if not isinstance(metadata, dict):
        raise PlanError("gh parent metadata must be an object")
    if (
        type(metadata.get("number")) is not int
        or metadata["number"] != request.parent_pr
    ):
        raise PlanError("Parent PR identity disagrees with the request")
    repository = metadata.get("base_repository")
    if (
        not isinstance(repository, str)
        or repository.casefold() != request.parent_repository.casefold()
    ):
        raise PlanError("Parent repository disagrees with the request")
    merged_at = metadata.get("merged_at")
    if (
        metadata.get("merged") is not True
        or not isinstance(merged_at, str)
        or not merged_at
    ):
        raise PlanError("The parent PR has not merged")
    for field in ("head_sha", "landed"):
        value = metadata.get(field)
        if not isinstance(value, str) or not OID_PATTERN.fullmatch(value):
            raise PlanError(f"Parent metadata has no valid {field} commit ID")
    return metadata


def recover_parent(request: Request, metadata: dict[str, object]) -> tuple[str, str]:
    """Fetch head, never the synthetic PR merge ref, into a fresh namespace."""
    evidence_ref = f"refs/agent-rebase/{uuid.uuid4().hex}/parent-head"
    git(
        request.repository,
        "-c",
        "gc.auto=0",
        "-c",
        "maintenance.auto=false",
        "fetch",
        "--no-prune",
        "--no-tags",
        "--no-write-fetch-head",
        f"https://github.com/{request.parent_repository}.git",
        f"refs/pull/{request.parent_pr}/head:{evidence_ref}",
    )
    parent_head = commit(request.repository, evidence_ref)
    if parent_head != metadata["head_sha"]:
        raise PlanError(
            f"Fetched PR head disagrees with metadata; retain {evidence_ref}"
        )
    return parent_head, evidence_ref


def choose_boundary(
    request: Request, old_head: str, parent_head: str
) -> tuple[str, str]:
    """Use inherited parent history or a maintained receipt, never a heuristic."""
    repo = request.repository
    inherited = ancestor(repo, parent_head, old_head)
    if request.boundary_ref is None:
        if inherited:
            return parent_head, "parent-pr-head"
        candidates = git(repo, "merge-base", "--all", parent_head, old_head)
        raise PlanError(
            "Parent head is not inherited. Merge-base candidates are not proof: "
            f"{candidates}. Review a maintained boundary receipt or historical reflog."
        )
    if not request.boundary_ref.startswith("refs/stack-bases/"):
        raise PlanError("Use a maintained refs/stack-bases/ boundary receipt")
    git(repo, "check-ref-format", request.boundary_ref)
    identity = command(
        repo,
        "git",
        "config",
        "--local",
        "--get",
        f"branch.{request.branch}.stackParent",
        allowed=(0, 1),
    )
    if (
        identity.casefold()
        != f"{request.parent_repository}#{request.parent_pr}".casefold()
    ):
        raise PlanError(
            "Boundary receipt needs the matching branch stackParent identity"
        )
    old_base = commit(repo, request.boundary_ref)
    if not ancestor(repo, old_base, old_head):
        raise PlanError("Recorded boundary is not an ancestor of the child")
    if inherited and old_base != parent_head:
        raise PlanError("Recorded boundary disagrees with the inherited parent head")
    return old_base, f"maintained-receipt:{request.boundary_ref}"


def plan(request: Request) -> dict[str, object]:
    """Return frozen evidence and an explicit replay range, never run a rebase.

    A successful plan still requires ownership/semantic review. It does not
    prove the merge method, receipt freshness, worktree ownership or that later
    target history did not revert parent functionality.
    """
    old_head, target = preflight(request)
    metadata = parent_metadata(request)
    landed = commit(request.repository, str(metadata["landed"]))
    if not ancestor(request.repository, landed, target):
        raise PlanError("Parent landing commit is not reachable from the target")
    parent_head, evidence_ref = recover_parent(request, metadata)
    old_base, evidence = choose_boundary(request, old_head, parent_head)
    series = f"{old_base}..{old_head}"
    if git(request.repository, "rev-list", "--merges", series):
        raise PlanError(
            "The selected range contains merges; use a topology-aware procedure"
        )
    commits = git(request.repository, "rev-list", "--reverse", series).splitlines()
    if commit(request.repository, f"refs/heads/{request.branch}") != old_head:
        raise PlanError("Child branch moved during discovery; discard this plan")
    if commit(request.repository, request.target_ref) != target:
        raise PlanError("Target ref moved during discovery; discard this plan")
    return {
        "status": "review-required" if commits else "no-op-decision-required",
        "branch": request.branch,
        "old_head": old_head,
        "target": target,
        "old_base": old_base,
        "parent_head": parent_head,
        "landed": landed,
        "parent_pr": f"{request.parent_repository}#{request.parent_pr}",
        "boundary_evidence": evidence,
        "evidence_ref": evidence_ref,
        "commits": commits,
        "rebase_argv": [*REBASE_PREFIX, target, old_base, request.branch]
        if commits
        else None,
        "review": [
            "Confirm the parent relationship and squash merge method independently.",
            "Account for every included child commit and excluded inherited commit.",
            "Check receipt freshness, target reverts, worktree ownership and driver policy.",
            "Preserve recovery refs and recheck branch/target identities before replay.",
        ],
    }


def main(
    repository: Path,
    *,
    branch: str,
    target_ref: str,
    parent_repository: str,
    parent_pr: int,
    boundary_ref: str | None = None,
) -> None:
    """Print a review-required JSON plan for a confirmed squash-merged parent."""
    try:
        result = plan(
            Request(
                repository.resolve(),
                branch,
                target_ref,
                parent_repository,
                parent_pr,
                boundary_ref,
            )
        )
    except PlanError as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}), file=sys.stderr)
        raise SystemExit(2) from exc
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    import cyclopts

    cyclopts.run(main)
