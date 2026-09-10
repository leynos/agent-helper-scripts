# /// script
# requires-python = ">=3.13"
# dependencies = ["cyclopts>=4,<5"]
# ///
"""Prepare, but never execute, a squash-restack plan for human/agent review.

Only GitHub metadata and real Git ancestry inform the plan. The caller identifies
an already confirmed squash-merged parent PR. Fetching creates a private evidence
ref; discovery never moves a branch, changes the worktree, rebases, or pushes.

Discovery and plan construction are separate, and the separation is visible in
the names. :func:`discover` is the command-layer operation: it runs ``gh``,
fetches the parent PR head into a private evidence ref, and returns an
immutable :class:`Evidence` snapshot. :func:`build_plan` is the read path; it
consumes an already collected snapshot and only queries the local graph.
:func:`discover_and_plan` is the explicit composition of the two, named so that
no caller mistakes a plan for a side-effect-free query.

Every process interaction goes through an injected :class:`Runner`, so a caller
may substitute one without patching module globals.
"""

from __future__ import annotations

import contextlib
import dataclasses
import json
import re
import subprocess
import sys
import time
import typing as typ
import uuid
from pathlib import Path

if typ.TYPE_CHECKING:
    from collections.abc import Callable, Iterator

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

#: Bounded, fixed set of failure categories. Diagnostics report one of these
#: rather than free-form text, so a reader can aggregate failures without
#: parsing messages that are written for humans.
CATEGORY_IDENTITY = "identity"
CATEGORY_REPOSITORY_STATE = "repository-state"
CATEGORY_METADATA = "metadata"
CATEGORY_RECOVERY = "recovery"
CATEGORY_BOUNDARY = "boundary"
CATEGORY_RANGE = "range"
CATEGORY_RACE = "race"
CATEGORY_PROCESS = "process"
CATEGORY_UNCLASSIFIED = "unclassified"


class PlanError(RuntimeError):
    """Discovery cannot establish a safe, reviewable replay range.

    Parameters
    ----------
    message : str
        Human-readable reason, reported verbatim as the blocked ``reason``.
    category : str
        One of the bounded ``CATEGORY_*`` constants, reported in diagnostics.
    """

    def __init__(self, message: str, category: str = CATEGORY_UNCLASSIFIED) -> None:
        super().__init__(message)
        self.category = category


@typ.runtime_checkable
class Runner(typ.Protocol):
    """Runs one program in one repository and returns its standard output."""

    def __call__(
        self, program: str, /, *argv: str, allowed: tuple[int, ...] = (0,)
    ) -> str:
        """Run ``program`` with ``argv``; see :class:`Subprocess` for the contract."""
        ...


@dataclasses.dataclass(frozen=True)
class Subprocess:
    """The real process adapter: runs an argv without a shell.

    Parameters
    ----------
    repository : Path
        Working directory for every process this adapter runs.
    """

    repository: Path

    def __call__(
        self, program: str, /, *argv: str, allowed: tuple[int, ...] = (0,)
    ) -> str:
        """Run an argv without a shell; distinguish negative answers from failures.

        Parameters
        ----------
        program : str
            Executable to run.
        *argv : str
            Arguments, passed as a list so no shell parsing occurs.
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
                (program, *argv),
                cwd=self.repository,
                capture_output=True,
                text=True,
                check=False,
                timeout=60,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise PlanError(f"Cannot run {program}: {exc}", CATEGORY_PROCESS) from exc
        if result.returncode not in allowed:
            detail = result.stderr.strip() or result.stdout.strip()
            raise PlanError(
                f"{program} exited {result.returncode}: {detail}", CATEGORY_PROCESS
            )
        return result.stdout.strip()


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


@contextlib.contextmanager
def phase(operation: str, name: str, **fields: object) -> Iterator[None]:
    """Time one phase and emit a terminal success or failure diagnostic.

    Every phase reports the same bounded fields, so a reader can aggregate
    outcomes and durations without parsing human-readable reasons.

    Parameters
    ----------
    operation : str
        Identifier correlating diagnostics from one run.
    name : str
        Phase name, drawn from a fixed set of call sites.
    **fields : object
        Additional identities recorded on the start event.

    Yields
    ------
    None

    Raises
    ------
    PlanError
        Re-raised unchanged after the failure diagnostic is emitted.
    """
    started = time.monotonic()
    trace(operation, "phase-started", phase=name, **fields)

    def elapsed_ms() -> int:
        return round((time.monotonic() - started) * 1000)

    try:
        yield
    except PlanError as exc:
        trace(
            operation,
            "phase-finished",
            phase=name,
            outcome="blocked",
            error_category=exc.category,
            elapsed_ms=elapsed_ms(),
        )
        raise
    else:
        trace(
            operation,
            "phase-finished",
            phase=name,
            outcome="ok",
            elapsed_ms=elapsed_ms(),
        )


def _new_operation_id() -> str:
    """Return a fresh identifier correlating one run's diagnostics.

    Returns
    -------
    str
        A random hexadecimal identifier.
    """
    return uuid.uuid4().hex


def _new_evidence_ref() -> str:
    """Return a fresh, unused private ref name for the fetched parent head.

    Returns
    -------
    str
        A ref under ``refs/agent-rebase/`` that no earlier run can collide with.
    """
    return f"refs/agent-rebase/{uuid.uuid4().hex}/parent-head"


def git(run: Runner, *args: str) -> str:
    """Run a Git query or the narrowly scoped evidence fetch.

    Parameters
    ----------
    run : Runner
        Process adapter bound to the repository.
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
    return run("git", *args)


def commit(run: Runner, ref: str) -> str:
    """Resolve exactly one commit without treating a user ref as an option.

    Parameters
    ----------
    run : Runner
        Process adapter bound to the repository.
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
    return git(run, "rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}")


def ancestor(run: Runner, older: str, newer: str) -> bool:
    """Ask a real graph query, propagating errors rather than treating them as no.

    Parameters
    ----------
    run : Runner
        Process adapter bound to the repository holding both commits.
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
    return not git(run, "rev-list", "--max-count=1", older, f"^{newer}")


def _validate_identities(run: Runner, request: Request) -> None:
    """Refuse an identity that is malformed, non-positive, or option-shaped.

    Parameters
    ----------
    run : Runner
        Process adapter bound to the repository.
    request : Request
        Operator-supplied identities to validate.

    Returns
    -------
    None

    Raises
    ------
    PlanError
        If the parent repository, parent PR number, or branch name is not an
        explicit, well-formed identity.
    """
    if not REPOSITORY_PATTERN.fullmatch(request.parent_repository) or any(
        part in {".", ".."} for part in request.parent_repository.split("/")
    ):
        raise PlanError(
            "Parent repository must be an explicit GitHub owner/name",
            CATEGORY_IDENTITY,
        )
    if type(request.parent_pr) is not int or request.parent_pr <= 0:
        raise PlanError("Parent PR must be a positive integer", CATEGORY_IDENTITY)
    if not request.branch or request.branch.startswith("-"):
        raise PlanError(
            "Branch must be an explicit local branch name, not an option",
            CATEGORY_IDENTITY,
        )
    git(run, "check-ref-format", f"refs/heads/{request.branch}")


def _refuse_active_operation(run: Runner, request: Request) -> None:
    """Refuse incomplete history, another in-flight Git operation, or dirty work.

    Parameters
    ----------
    run : Runner
        Process adapter bound to the repository.
    request : Request
        Operator-supplied identities, used for the repository path.

    Returns
    -------
    None

    Raises
    ------
    PlanError
        If the history is shallow, another Git operation is in progress, or the
        checkout holds staged, unstaged, or untracked work.
    """
    if git(run, "rev-parse", "--is-shallow-repository") != "false":
        raise PlanError(
            "Shallow history cannot establish the complete replay range",
            CATEGORY_REPOSITORY_STATE,
        )
    for name in (
        "rebase-merge",
        "rebase-apply",
        "MERGE_HEAD",
        "CHERRY_PICK_HEAD",
        "REVERT_HEAD",
        "sequencer",
    ):
        path = Path(git(run, "rev-parse", "--git-path", name))
        if not path.is_absolute():
            path = request.repository / path
        if path.exists():
            raise PlanError(
                f"An active Git operation exists: {name}", CATEGORY_REPOSITORY_STATE
            )
    if git(run, "status", "--porcelain=v1", "--untracked-files=all"):
        raise PlanError(
            "Preserve staged, unstaged and untracked work before planning",
            CATEGORY_REPOSITORY_STATE,
        )


def preflight(run: Runner, request: Request) -> tuple[str, str]:
    """Freeze identities and refuse incomplete history or an occupied checkout.

    Parameters
    ----------
    run : Runner
        Process adapter bound to the repository.
    request : Request
        Operator-supplied identities to validate.

    Returns
    -------
    tuple[str, str]
        The child branch tip and the target ref tip.

    Raises
    ------
    PlanError
        Propagated from :func:`_validate_identities` or
        :func:`_refuse_active_operation`, or raised when either ref does not
        resolve to exactly one commit.
    """
    _validate_identities(run, request)
    _refuse_active_operation(run, request)
    return (
        commit(run, f"refs/heads/{request.branch}"),
        commit(run, request.target_ref),
    )


def parent_metadata(run: Runner, request: Request) -> dict[str, object]:
    """Validate the CLI response before using any source or landing identity.

    Parameters
    ----------
    run : Runner
        Process adapter bound to the repository.
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
    output = run(
        "gh",
        "api",
        f"repos/{request.parent_repository}/pulls/{request.parent_pr}",
        "--jq",
        PARENT_QUERY,
    )
    try:
        metadata = json.loads(output)
    except json.JSONDecodeError as exc:
        raise PlanError(
            "gh returned malformed parent metadata", CATEGORY_METADATA
        ) from exc
    if not isinstance(metadata, dict):
        raise PlanError("gh parent metadata must be an object", CATEGORY_METADATA)
    if (
        type(metadata.get("number")) is not int
        or metadata["number"] != request.parent_pr
    ):
        raise PlanError(
            "Parent PR identity disagrees with the request", CATEGORY_METADATA
        )
    repository = metadata.get("base_repository")
    if (
        not isinstance(repository, str)
        or repository.casefold() != request.parent_repository.casefold()
    ):
        raise PlanError(
            "Parent repository disagrees with the request", CATEGORY_METADATA
        )
    merged_at = metadata.get("merged_at")
    if (
        metadata.get("merged") is not True
        or not isinstance(merged_at, str)
        or not merged_at
    ):
        raise PlanError("The parent PR has not merged", CATEGORY_METADATA)
    for field in ("head_sha", "landed"):
        value = metadata.get(field)
        if not isinstance(value, str) or not OID_PATTERN.fullmatch(value):
            raise PlanError(
                f"Parent metadata has no valid {field} commit ID", CATEGORY_METADATA
            )
    return metadata


def recover_parent(
    run: Runner,
    request: Request,
    metadata: dict[str, object],
    new_evidence_ref: Callable[[], str],
) -> tuple[str, str]:
    """Fetch head, never the synthetic PR merge ref, into a fresh namespace.

    Parameters
    ----------
    run : Runner
        Process adapter bound to the repository.
    request : Request
        Identities naming the parent PR and the local repository.
    metadata : dict[str, object]
        Validated parent metadata supplying the expected head commit ID.
    new_evidence_ref : Callable[[], str]
        Supplies a fresh, unused private ref name for the fetched head.

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
    evidence_ref = new_evidence_ref()
    git(
        run,
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
    parent_head = commit(run, evidence_ref)
    if parent_head != metadata["head_sha"]:
        raise PlanError(
            f"Fetched PR head disagrees with metadata; retain {evidence_ref}",
            CATEGORY_RECOVERY,
        )
    return parent_head, evidence_ref


def choose_boundary(
    run: Runner, request: Request, old_head: str, parent_head: str
) -> Boundary:
    """Use inherited parent history or a maintained receipt, never a heuristic.

    Parameters
    ----------
    run : Runner
        Process adapter bound to the repository.
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
    inherited = ancestor(run, parent_head, old_head)
    if request.boundary_ref is None:
        if inherited:
            return Boundary(parent_head, "parent-pr-head", corroborated=True)
        candidates = git(run, "merge-base", "--all", parent_head, old_head)
        raise PlanError(
            "Parent head is not inherited. Merge-base candidates are not proof: "
            f"{candidates}. Review a maintained boundary receipt or historical reflog.",
            CATEGORY_BOUNDARY,
        )
    if not request.boundary_ref.startswith(RECEIPT_PREFIX):
        raise PlanError(
            f"Use a maintained {RECEIPT_PREFIX} boundary receipt", CATEGORY_BOUNDARY
        )
    git(run, "check-ref-format", request.boundary_ref)
    identity = run(
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
            "Boundary receipt needs the matching branch stackParent identity",
            CATEGORY_BOUNDARY,
        )
    old_base = commit(run, request.boundary_ref)
    if not ancestor(run, old_base, old_head):
        raise PlanError(
            "Recorded boundary is not an ancestor of the child", CATEGORY_BOUNDARY
        )
    if inherited and old_base != parent_head:
        raise PlanError(
            "Recorded boundary disagrees with the inherited parent head",
            CATEGORY_BOUNDARY,
        )
    return Boundary(
        old_base,
        f"maintained-receipt:{request.boundary_ref}",
        # Only inherited parent history can prove that no inherited commit
        # follows the receipt. Otherwise the receipt is an unverified claim.
        corroborated=inherited,
    )


def discover(
    request: Request,
    run: Runner | None = None,
    *,
    new_operation_id: Callable[[], str] = _new_operation_id,
    new_evidence_ref: Callable[[], str] = _new_evidence_ref,
) -> Evidence:
    """Gather and freeze every external observation the plan depends on.

    This is the command-layer operation, named as one. It runs ``gh``, fetches
    the parent PR head into a private evidence ref, and returns an immutable
    snapshot. It never rebases, pushes, prunes, moves a branch or tracking ref,
    or touches the index or worktree. :func:`build_plan` consumes the snapshot
    and performs no discovery of its own.

    Parameters
    ----------
    request : Request
        Operator-supplied identities.
    run : Runner | None
        Process adapter; defaults to a :class:`Subprocess` bound to
        ``request.repository``.
    new_operation_id : Callable[[], str]
        Supplies the diagnostic correlation identifier.
    new_evidence_ref : Callable[[], str]
        Supplies the private ref name the fetched parent head is written to.

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
    run = Subprocess(request.repository) if run is None else run
    operation = new_operation_id()
    with phase(operation, "preflight", branch=request.branch):
        old_head, target = preflight(run, request)
    with phase(operation, "parent-metadata", parent_pr=request.parent_pr):
        metadata = parent_metadata(run, request)
    with phase(operation, "landing-validation"):
        landed = commit(run, str(metadata["landed"]))
        if not ancestor(run, landed, target):
            raise PlanError(
                "Parent landing commit is not reachable from the target",
                CATEGORY_METADATA,
            )
    with phase(operation, "parent-head-fetch"):
        parent_head, evidence_ref = recover_parent(
            run, request, metadata, new_evidence_ref
        )
    trace(
        operation,
        "evidence-frozen",
        old_head=old_head,
        target=target,
        landed=landed,
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


def build_plan(
    request: Request, evidence: Evidence, run: Runner | None = None
) -> dict[str, object]:
    """Derive an explicit replay range from frozen evidence, never run a rebase.

    This is the read path. It consumes an already collected snapshot and never
    invokes discovery, so it performs no network access and writes no ref.
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
    run : Runner | None
        Process adapter; defaults to a :class:`Subprocess` bound to
        ``request.repository``.

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
    run = Subprocess(request.repository) if run is None else run
    with phase(evidence.operation, "boundary-selection"):
        boundary = choose_boundary(
            run, request, evidence.old_head, evidence.parent_head
        )
    trace(
        evidence.operation,
        "boundary-selected",
        old_base=boundary.old_base,
        evidence=boundary.evidence,
        corroborated=boundary.corroborated,
    )
    with phase(evidence.operation, "range-validation"):
        series = f"{boundary.old_base}..{evidence.old_head}"
        if git(run, "rev-list", "--merges", series):
            raise PlanError(
                "The selected range contains merges; use a topology-aware procedure",
                CATEGORY_RANGE,
            )
        commits = git(run, "rev-list", "--reverse", series).splitlines()
    with phase(evidence.operation, "identity-recheck"):
        if commit(run, f"refs/heads/{request.branch}") != evidence.old_head:
            raise PlanError(
                "Child branch moved during discovery; discard this plan",
                CATEGORY_RACE,
            )
        if commit(run, request.target_ref) != evidence.target:
            raise PlanError(
                "Target ref moved during discovery; discard this plan", CATEGORY_RACE
            )
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


def discover_and_plan(request: Request, run: Runner | None = None) -> dict[str, object]:
    """Run discovery, then derive the reviewable plan from that snapshot.

    Named for what it does. This is a command, not a query: it runs ``gh`` and
    writes a private evidence ref before any plan exists. Callers that already
    hold an :class:`Evidence` snapshot should call :func:`build_plan` instead,
    which performs no discovery.

    Parameters
    ----------
    request : Request
        Operator-supplied identities.
    run : Runner | None
        Process adapter; defaults to a :class:`Subprocess` bound to
        ``request.repository``.

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
    run = Subprocess(request.repository) if run is None else run
    return build_plan(request, discover(request, run), run)


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
        With status 2 when :func:`discover_and_plan` raises :class:`PlanError`.
        The reason and its bounded category are written to standard error as a
        ``blocked`` JSON object.
    """
    try:
        result = discover_and_plan(
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
        print(
            json.dumps(
                {"status": "blocked", "reason": str(exc), "category": exc.category}
            ),
            file=sys.stderr,
        )
        raise SystemExit(2) from exc
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    import cyclopts

    cyclopts.run(main)
