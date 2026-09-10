# /// script
# requires-python = ">=3.13"
# dependencies = ["cyclopts>=4,<5"]
# ///
"""Prepare, but never execute, a squash-restack plan for human/agent review.

Only GitHub metadata and real Git ancestry inform the plan. The caller identifies
an already confirmed squash-merged parent PR. Fetching creates a private evidence
ref; discovery never moves a branch, changes the worktree, rebases, or pushes.

Discovery and plan construction are separate. :func:`discover` performs every
process and network interaction and returns an immutable :class:`Evidence`
snapshot. :func:`build_plan` consumes that snapshot and only queries the local
graph, so replay policy stays readable apart from the adapters that gather it.
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
RECEIPT_PREFIX = "refs/stack-bases/"


class PlanError(RuntimeError):
    """Discovery cannot establish a safe, reviewable replay range."""


@dataclasses.dataclass(frozen=True)
class Request:
    """Explicit identities supplied by the operator, not inferred from titles.

    Parameters
    ----------
    repository : Path
        Working tree in which every Git query runs.
    branch : str
        Local child branch to be replayed, without the ``refs/heads/`` prefix.
    target_ref : str
        Fetched ref the child will be replayed onto.
    parent_repository : str
        GitHub ``owner/name`` hosting the confirmed squash-merged parent PR.
    parent_pr : int
        Number of that parent PR.
    boundary_ref : str | None
        Maintained ``refs/stack-bases/`` receipt naming the last inherited
        commit, required when the parent head is no longer inherited.
    """

    repository: Path
    branch: str
    target_ref: str
    parent_repository: str
    parent_pr: int
    boundary_ref: str | None = None


@dataclasses.dataclass(frozen=True)
class Boundary:
    """The accepted exclusive replay boundary and the evidence supporting it.

    Parameters
    ----------
    old_base : str
        Exclusive boundary commit; the last commit that must not be replayed.
    evidence : str
        Provenance label for ``old_base``, never a heuristic.
    corroborated : bool
        Whether preserved parent history proves no inherited commit follows
        ``old_base``. A maintained receipt alone cannot prove this.
    """

    old_base: str
    evidence: str
    corroborated: bool


@dataclasses.dataclass(frozen=True)
class Evidence:
    """Immutable snapshot of everything discovery observed outside the planner.

    Parameters
    ----------
    operation : str
        Identifier correlating every diagnostic emitted for one discovery run.
    old_head : str
        Child branch tip observed at the start of discovery.
    target : str
        Target ref tip observed at the start of discovery.
    landed : str
        Squash landing commit, resolved locally and proven to be on the target.
    parent_head : str
        Original parent PR head, fetched into ``evidence_ref``.
    evidence_ref : str
        Private ref retaining ``parent_head`` for review and recovery.
    metadata : dict[str, object]
        Validated ``gh api`` response for the parent PR.
    """

    operation: str
    old_head: str
    target: str
    landed: str
    parent_head: str
    evidence_ref: str
    metadata: dict[str, object]


def trace(operation: str, event: str, **fields: object) -> None:
    """Emit one bounded, structured diagnostic line on standard error.

    Diagnostics carry only identities the plan already reports, so they never
    leak repository contents. Standard output stays reserved for the plan.

    Parameters
    ----------
    operation : str
        Identifier correlating diagnostics from one discovery run.
    event : str
        Short, stable event name.
    **fields : object
        Additional JSON-serializable identities for this event.

    Returns
    -------
    None
    """
    record = {"operation": operation, "event": event, **fields}
    print(json.dumps(record, default=str), file=sys.stderr)


def command(repository: Path, *argv: str, allowed: tuple[int, ...] = (0,)) -> str:
    """Run an argv without a shell; distinguish negative answers from failures.

    Parameters
    ----------
    repository : Path
        Working directory for the child process.
    *argv : str
        Program and arguments, passed as a list so no shell parsing occurs.
    allowed : tuple[int, ...]
        Exit statuses that carry an answer rather than a failure.

    Returns
    -------
    str
        Stripped standard output of the process.

    Raises
    ------
    PlanError
        If the process cannot start, times out, or exits outside ``allowed``.
    """
    try:
        # argv is a fixed list and no shell is used, so nothing here is
        # parsed as a shell string; callers pass validated identities.
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
    """Run a Git query or the narrowly scoped evidence fetch.

    Parameters
    ----------
    repository : Path
        Working directory for the Git process.
    *args : str
        Git subcommand and arguments.

    Returns
    -------
    str
        Stripped standard output of the Git process.

    Raises
    ------
    PlanError
        If Git cannot run or exits non-zero.
    """
    return command(repository, "git", *args)


def commit(repository: Path, ref: str) -> str:
    """Resolve exactly one commit without treating a user ref as an option.

    Parameters
    ----------
    repository : Path
        Repository to resolve the ref in.
    ref : str
        Ref or object name supplied by the operator or by metadata.

    Returns
    -------
    str
        Full commit object ID.

    Raises
    ------
    PlanError
        If the ref is missing, ambiguous, or does not name a commit.
    """
    return git(
        repository, "rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}"
    )


def ancestor(repository: Path, older: str, newer: str) -> bool:
    """Ask a real graph query, propagating errors rather than treating them as no.

    Parameters
    ----------
    repository : Path
        Repository holding both commits.
    older : str
        Candidate ancestor, already resolved to a full commit ID.
    newer : str
        Candidate descendant, already resolved to a full commit ID.

    Returns
    -------
    bool
        True when ``older`` is reachable from ``newer``.

    Raises
    ------
    PlanError
        If either object is missing, so a negative answer is never faked.
    """
    # rev-list errors remain errors; empty output means every older commit is
    # reachable from newer. Inputs are already resolved full commit IDs.
    return not git(repository, "rev-list", "--max-count=1", older, f"^{newer}")


def preflight(request: Request) -> tuple[str, str]:
    """Freeze identities and refuse incomplete history or an occupied checkout.

    Parameters
    ----------
    request : Request
        Operator-supplied identities to validate.

    Returns
    -------
    tuple[str, str]
        The child branch tip and the target ref tip.

    Raises
    ------
    PlanError
        If an identity is malformed, the history is shallow, another Git
        operation is in progress, or the checkout holds uncommitted work.
    """
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
    """Validate the CLI response before using any source or landing identity.

    Parameters
    ----------
    request : Request
        Identities naming the parent PR to query.

    Returns
    -------
    dict[str, object]
        The validated ``gh api`` response.

    Raises
    ------
    PlanError
        If ``gh`` fails, returns malformed output, reports a different PR or
        repository, reports an unmerged PR, or omits a valid commit ID.
    """
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
    """Fetch head, never the synthetic PR merge ref, into a fresh namespace.

    Parameters
    ----------
    request : Request
        Identities naming the parent PR and the local repository.
    metadata : dict[str, object]
        Validated parent metadata supplying the expected head commit ID.

    Returns
    -------
    tuple[str, str]
        The fetched parent head and the private ref retaining it.

    Raises
    ------
    PlanError
        If the fetch fails, the PR head is unavailable, or the fetched commit
        disagrees with the metadata.
    """
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


def choose_boundary(request: Request, old_head: str, parent_head: str) -> Boundary:
    """Use inherited parent history or a maintained receipt, never a heuristic.

    Parameters
    ----------
    request : Request
        Identities, including any maintained boundary receipt.
    old_head : str
        Child branch tip.
    parent_head : str
        Original parent PR head recovered from GitHub.

    Returns
    -------
    Boundary
        The accepted exclusive boundary, its provenance, and whether preserved
        parent history corroborates it.

    Raises
    ------
    PlanError
        If the parent head is not inherited and no maintained receipt is
        supplied, or the supplied receipt is malformed, belongs to another
        parent, is not an ancestor of the child, or contradicts inherited
        parent history.
    """
    repo = request.repository
    inherited = ancestor(repo, parent_head, old_head)
    if request.boundary_ref is None:
        if inherited:
            return Boundary(parent_head, "parent-pr-head", corroborated=True)
        candidates = git(repo, "merge-base", "--all", parent_head, old_head)
        raise PlanError(
            "Parent head is not inherited. Merge-base candidates are not proof: "
            f"{candidates}. Review a maintained boundary receipt or historical reflog."
        )
    if not request.boundary_ref.startswith(RECEIPT_PREFIX):
        raise PlanError(f"Use a maintained {RECEIPT_PREFIX} boundary receipt")
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
    return Boundary(
        old_base,
        f"maintained-receipt:{request.boundary_ref}",
        # Only inherited parent history can prove that no inherited commit
        # follows the receipt. Otherwise the receipt is an unverified claim.
        corroborated=inherited,
    )


def discover(request: Request) -> Evidence:
    """Gather and freeze every external observation the plan depends on.

    This is the only command-layer operation. It runs ``gh``, fetches the
    parent PR head into a private evidence ref, and returns an immutable
    snapshot. It never rebases, pushes, prunes, moves a branch or tracking
    ref, or touches the index or worktree.

    Parameters
    ----------
    request : Request
        Operator-supplied identities.

    Returns
    -------
    Evidence
        Frozen identities plus the retained evidence ref.

    Raises
    ------
    PlanError
        If preflight fails, the metadata is unusable, the landing commit is not
        reachable from the target, or the parent head cannot be recovered.
    """
    operation = uuid.uuid4().hex
    trace(operation, "discovery-started", branch=request.branch)
    old_head, target = preflight(request)
    trace(operation, "preflight-passed", old_head=old_head, target=target)
    metadata = parent_metadata(request)
    trace(operation, "parent-metadata-validated", parent_pr=request.parent_pr)
    landed = commit(request.repository, str(metadata["landed"]))
    if not ancestor(request.repository, landed, target):
        raise PlanError("Parent landing commit is not reachable from the target")
    parent_head, evidence_ref = recover_parent(request, metadata)
    trace(
        operation,
        "parent-head-recovered",
        parent_head=parent_head,
        evidence_ref=evidence_ref,
    )
    return Evidence(
        operation, old_head, target, landed, parent_head, evidence_ref, metadata
    )


def review_notes(boundary: Boundary) -> list[str]:
    """Return the review obligations this plan explicitly does not discharge.

    Parameters
    ----------
    boundary : Boundary
        The accepted boundary, whose corroboration decides the extra note.

    Returns
    -------
    list[str]
        Human-readable obligations, most specific first.
    """
    notes = [
        "Confirm the parent relationship and squash merge method independently.",
        "Account for every included child commit and excluded inherited commit.",
        "Check receipt freshness, target reverts, worktree ownership and driver policy.",
        "Preserve recovery refs and recheck branch/target identities before replay.",
    ]
    if not boundary.corroborated:
        notes.insert(
            0,
            "The receipt is uncorroborated: the recovered parent head is not in the "
            "child's history, so nothing here proves no inherited parent commit "
            "follows the receipt. Prove it from preserved parent history or reflog "
            "before replaying.",
        )
    return notes


def build_plan(request: Request, evidence: Evidence) -> dict[str, object]:
    """Derive an explicit replay range from frozen evidence, never run a rebase.

    Only local graph queries run here. A successful plan still requires
    ownership and semantic review: it does not prove the merge method, receipt
    freshness, worktree ownership, or that later target history did not revert
    parent functionality.

    Parameters
    ----------
    request : Request
        Operator-supplied identities.
    evidence : Evidence
        Snapshot returned by :func:`discover`.

    Returns
    -------
    dict[str, object]
        A ``review-required`` or ``no-op-decision-required`` plan. The status is
        never an authorization to replay.

    Raises
    ------
    PlanError
        If no boundary can be established, the range contains merges, or the
        child or target ref moved during discovery.
    """
    boundary = choose_boundary(request, evidence.old_head, evidence.parent_head)
    trace(
        evidence.operation,
        "boundary-selected",
        old_base=boundary.old_base,
        evidence=boundary.evidence,
        corroborated=boundary.corroborated,
    )
    series = f"{boundary.old_base}..{evidence.old_head}"
    if git(request.repository, "rev-list", "--merges", series):
        raise PlanError(
            "The selected range contains merges; use a topology-aware procedure"
        )
    commits = git(request.repository, "rev-list", "--reverse", series).splitlines()
    if commit(request.repository, f"refs/heads/{request.branch}") != evidence.old_head:
        raise PlanError("Child branch moved during discovery; discard this plan")
    if commit(request.repository, request.target_ref) != evidence.target:
        raise PlanError("Target ref moved during discovery; discard this plan")
    status = "review-required" if commits else "no-op-decision-required"
    trace(evidence.operation, "plan-built", status=status, commits=len(commits))
    return {
        "status": status,
        "operation": evidence.operation,
        "branch": request.branch,
        "old_head": evidence.old_head,
        "target": evidence.target,
        "old_base": boundary.old_base,
        "parent_head": evidence.parent_head,
        "landed": evidence.landed,
        "parent_pr": f"{request.parent_repository}#{request.parent_pr}",
        "boundary_evidence": boundary.evidence,
        "boundary_corroborated": boundary.corroborated,
        "evidence_ref": evidence.evidence_ref,
        "commits": commits,
        "rebase_argv": [
            *REBASE_PREFIX,
            evidence.target,
            boundary.old_base,
            request.branch,
        ]
        if commits
        else None,
        "review": review_notes(boundary),
    }


def plan(request: Request) -> dict[str, object]:
    """Discover evidence, then derive the reviewable plan from that snapshot.

    Parameters
    ----------
    request : Request
        Operator-supplied identities.

    Returns
    -------
    dict[str, object]
        The plan produced by :func:`build_plan`.

    Raises
    ------
    PlanError
        Propagated from :func:`discover` or :func:`build_plan` whenever the
        evidence cannot establish a safe, reviewable replay range.
    """
    return build_plan(request, discover(request))


def main(
    repository: Path,
    *,
    branch: str,
    target_ref: str,
    parent_repository: str,
    parent_pr: int,
    boundary_ref: str | None = None,
) -> None:
    """Print a review-required JSON plan for a confirmed squash-merged parent.

    Parameters
    ----------
    repository : Path
        Working tree holding the child branch and the fetched target ref.
    branch : str
        Local child branch to replay, without the ``refs/heads/`` prefix.
    target_ref : str
        Fetched ref the child will be replayed onto.
    parent_repository : str
        GitHub ``owner/name`` hosting the confirmed squash-merged parent PR.
    parent_pr : int
        Number of that parent PR.
    boundary_ref : str | None
        Maintained ``refs/stack-bases/`` receipt naming the last inherited
        commit, required when the parent head is no longer inherited.

    Returns
    -------
    None
        The plan is written to standard output as JSON.

    Raises
    ------
    SystemExit
        With status 2 when :func:`plan` raises :class:`PlanError`. The reason is
        written to standard error as a ``blocked`` JSON object.
    """
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
