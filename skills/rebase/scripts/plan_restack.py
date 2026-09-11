# /// script
# requires-python = ">=3.13"
# dependencies = ["cyclopts>=4,<5"]
# ///
"""Prepare, but never execute, a squash-restack plan for human/agent review.

Only GitHub metadata and real Git ancestry inform the plan. The caller identifies
an already confirmed squash-merged parent PR. Fetching creates a private evidence
ref; discovery never moves a branch, changes the worktree, rebases, or pushes.

The module is layered, and the layers do not mix:

Domain
    Typed identities, evidence, graph facts, boundary provenance and the pure
    replay policy that reads them. Nothing here touches a :class:`~pathlib.Path`,
    a subprocess, GitHub CLI JSON, or Cyclopts, so the policy is testable
    without a repository.
Adapters
    :class:`Subprocess` runs processes; :class:`GitGraph` turns Git queries into
    typed graph facts; :class:`GitHubCli` parses and validates ``gh`` output.
Command layer
    :func:`discover` is the only operation that runs ``gh``, fetches, or writes
    a ref. It returns an immutable :class:`Evidence` snapshot.
Read path
    :func:`build_plan` consumes an already collected snapshot. It never invokes
    discovery, so it makes no network access and writes no ref.

Diagnostics form one operation span with child phase records, all on standard
error, keyed by an operation identifier the plan also carries. Standard output
carries a successful plan and nothing else.
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

#: Wall-clock ceiling for any single process this planner runs.
PROCESS_TIMEOUT_SECONDS = 60

#: Bounded failure categories. Diagnostics report one of these rather than free
#: text, so failures aggregate without parsing messages written for humans.
CATEGORY_IDENTITY = "identity"
CATEGORY_REPOSITORY_STATE = "repository-state"
CATEGORY_METADATA = "metadata"
CATEGORY_RECOVERY = "recovery"
CATEGORY_BOUNDARY = "boundary"
CATEGORY_RANGE = "range"
CATEGORY_RACE = "race"
CATEGORY_PROCESS = "process"
CATEGORY_UNCLASSIFIED = "unclassified"

#: Bounded phase names. Every diagnostic record carries exactly one of these.
PHASE_OPERATION = "operation"
PHASE_PREFLIGHT = "preflight"
PHASE_PARENT_METADATA = "parent-metadata"
PHASE_LANDING_VALIDATION = "landing-validation"
PHASE_PARENT_HEAD_FETCH = "parent-head-fetch"
PHASE_BOUNDARY_SELECTION = "boundary-selection"
PHASE_GRAPH_PLANNING = "graph-planning"

OUTCOME_OK = "ok"
OUTCOME_BLOCKED = "blocked"

STATUS_REVIEW_REQUIRED = "review-required"
STATUS_NO_OP = "no-op-decision-required"
STATUS_BLOCKED = "blocked"


# --------------------------------------------------------------------------
# Domain: identities and errors
# --------------------------------------------------------------------------

#: A resolved, full-length Git commit object ID.
CommitId = typ.NewType("CommitId", str)

#: Monotonic time source, injectable so diagnostics stay testable. Only
#: differences between two readings are ever used.
type Clock = typ.Callable[[], float]


@dataclasses.dataclass(frozen=True)
class ErrorContext:
    """Where a refusal happened, as structured data rather than prose.

    Parameters
    ----------
    operation : str
        Identifier correlating every diagnostic from one run.
    phase : str
        One of the bounded ``PHASE_*`` constants.
    """

    operation: str
    phase: str


class PlanError(RuntimeError):
    """Discovery cannot establish a safe, reviewable replay range.

    Parameters
    ----------
    reason : str
        Bounded, human-readable reason. This is what the blocked record
        reports, so it must never embed subprocess output, credentials, or
        repository contents.
    category : str
        One of the bounded ``CATEGORY_*`` constants.
    detail : str | None
        Unbounded diagnostic text, such as a failing process's standard error.
        It is appended to ``str(exc)`` for an operator reading a traceback, and
        is deliberately excluded from :func:`blocked_record`.

    Attributes
    ----------
    context : ErrorContext | None
        Set by the innermost enclosing :func:`phase`, so a caller learns where
        the refusal happened without parsing the message.
    """

    def __init__(
        self,
        reason: str,
        category: str = CATEGORY_UNCLASSIFIED,
        *,
        detail: str | None = None,
    ) -> None:
        super().__init__(reason if detail is None else f"{reason}: {detail}")
        self.reason = reason
        self.category = category
        self.detail = detail
        self.context: ErrorContext | None = None


@dataclasses.dataclass(frozen=True)
class ParentPullRequest:
    """The confirmed squash-merged parent PR, as an identity rather than text.

    Parameters
    ----------
    repository : str
        GitHub ``owner/name`` hosting the parent PR.
    number : int
        Parent PR number.
    """

    repository: str
    number: int

    def __str__(self) -> str:
        """Return the ``owner/name#number`` form used in plans and receipts."""
        return f"{self.repository}#{self.number}"

    def matches_receipt_identity(self, recorded: str) -> bool:
        """Report whether a recorded ``stackParent`` value names this PR.

        Parameters
        ----------
        recorded : str
            Value read from ``branch.<name>.stackParent``, possibly empty.

        Returns
        -------
        bool
            True when the recorded identity is this PR, ignoring case.
        """
        return recorded.casefold() == str(self).casefold()


@dataclasses.dataclass(frozen=True)
class ParentEvidence:
    """What was recovered about the parent, and where it was retained.

    Parameters
    ----------
    head : CommitId
        The parent PR's original head, fetched from GitHub.
    landed : CommitId
        The squash landing commit, proven reachable from the target.
    evidence_ref : str
        Private ref retaining ``head`` for review and recovery.
    """

    head: CommitId
    landed: CommitId
    evidence_ref: str


@dataclasses.dataclass(frozen=True)
class Evidence:
    """Immutable snapshot of everything discovery observed outside the planner.

    Parameters
    ----------
    operation : str
        Identifier correlating every diagnostic emitted for one run.
    parent : ParentPullRequest
        The parent PR the evidence was gathered for.
    old_head : CommitId
        Child branch tip observed at the start of discovery.
    target : CommitId
        Target ref tip observed at the start of discovery.
    parent_evidence : ParentEvidence
        The recovered parent head, its landing commit, and the retained ref.
    """

    operation: str
    parent: ParentPullRequest
    old_head: CommitId
    target: CommitId
    parent_evidence: ParentEvidence


@dataclasses.dataclass(frozen=True)
class ReceiptFacts:
    """What the graph says about a maintained boundary receipt.

    Parameters
    ----------
    ref : str
        The receipt ref name, as supplied by the operator.
    commit : CommitId
        The commit the receipt names.
    stack_parent : str
        Recorded ``branch.<name>.stackParent`` value, empty when unset.
    is_ancestor_of_child : bool
        Whether ``commit`` is reachable from the child branch tip.
    """

    ref: str
    commit: CommitId
    stack_parent: str
    is_ancestor_of_child: bool


@dataclasses.dataclass(frozen=True)
class BoundaryFacts:
    """Typed graph facts sufficient to choose a boundary, with no Git handle.

    Parameters
    ----------
    parent_head : CommitId
        Original parent PR head recovered from GitHub.
    old_head : CommitId
        Child branch tip.
    parent_head_inherited : bool
        Whether ``parent_head`` is reachable from ``old_head``.
    merge_base_candidates : tuple[CommitId, ...]
        Every merge base of the parent head and the child, reported only so a
        refusal can name them. They are never used to choose a boundary.
    receipt : ReceiptFacts | None
        Facts about the supplied receipt, or None when none was supplied.
    """

    parent_head: CommitId
    old_head: CommitId
    parent_head_inherited: bool
    merge_base_candidates: tuple[CommitId, ...]
    receipt: ReceiptFacts | None


@dataclasses.dataclass(frozen=True)
class Boundary:
    """The accepted exclusive replay boundary and the evidence supporting it.

    Parameters
    ----------
    old_base : CommitId
        Exclusive boundary commit; the last commit that must not be replayed.
    evidence : str
        Provenance label for ``old_base``, never a heuristic.
    corroborated : bool
        Whether preserved parent history proves no inherited commit follows
        ``old_base``. A maintained receipt alone cannot prove this.
    """

    old_base: CommitId
    evidence: str
    corroborated: bool


@dataclasses.dataclass(frozen=True)
class RangeFacts:
    """Typed graph facts about the proposed replay range.

    Parameters
    ----------
    old_base : CommitId
        Exclusive boundary the range starts after.
    old_head : CommitId
        Inclusive tip the range ends at.
    commits : tuple[CommitId, ...]
        Commits in ``old_base..old_head``, oldest first.
    contains_merges : bool
        Whether any commit in that range is a merge.
    """

    old_base: CommitId
    old_head: CommitId
    commits: tuple[CommitId, ...]
    contains_merges: bool


@dataclasses.dataclass(frozen=True)
class Identities:
    """Branch and target tips, re-read to detect a concurrent move.

    Parameters
    ----------
    branch_head : CommitId
        Current child branch tip.
    target : CommitId
        Current target ref tip.
    """

    branch_head: CommitId
    target: CommitId


# --------------------------------------------------------------------------
# Domain: pure replay policy
# --------------------------------------------------------------------------


def check_identities(parent: ParentPullRequest, branch: str) -> None:
    """Refuse an identity that is malformed, non-positive, or option-shaped.

    Pure: this inspects only the supplied values.

    Parameters
    ----------
    parent : ParentPullRequest
        Parent PR identity to validate.
    branch : str
        Local child branch name, without the ``refs/heads/`` prefix.

    Returns
    -------
    None

    Raises
    ------
    PlanError
        If any identity is not explicit and well-formed.
    """
    if not REPOSITORY_PATTERN.fullmatch(parent.repository) or any(
        part in {".", ".."} for part in parent.repository.split("/")
    ):
        raise PlanError(
            "Parent repository must be an explicit GitHub owner/name",
            CATEGORY_IDENTITY,
        )
    if type(parent.number) is not int or parent.number <= 0:
        raise PlanError("Parent PR must be a positive integer", CATEGORY_IDENTITY)
    if not branch or branch.startswith("-"):
        raise PlanError(
            "Branch must be an explicit local branch name, not an option",
            CATEGORY_IDENTITY,
        )


def select_boundary(parent: ParentPullRequest, facts: BoundaryFacts) -> Boundary:
    """Use inherited parent history or a maintained receipt, never a heuristic.

    Pure: this reads typed graph facts and never queries a repository.

    Parameters
    ----------
    parent : ParentPullRequest
        The parent PR a receipt must name to be trusted.
    facts : BoundaryFacts
        Typed graph facts gathered by an adapter.

    Returns
    -------
    Boundary
        The accepted exclusive boundary, its provenance, and whether preserved
        parent history corroborates it.

    Raises
    ------
    PlanError
        If the parent head is not inherited and no maintained receipt is
        supplied, or the supplied receipt belongs to another parent, is not an
        ancestor of the child, or contradicts inherited parent history.
    """
    inherited = facts.parent_head_inherited
    if facts.receipt is None:
        if inherited:
            return Boundary(facts.parent_head, "parent-pr-head", corroborated=True)
        raise PlanError(
            "Parent head is not inherited. Merge-base candidates are not proof: "
            f"{' '.join(facts.merge_base_candidates)}. "
            "Review a maintained boundary receipt or historical reflog.",
            CATEGORY_BOUNDARY,
        )
    receipt = facts.receipt
    if not parent.matches_receipt_identity(receipt.stack_parent):
        raise PlanError(
            "Boundary receipt needs the matching branch stackParent identity",
            CATEGORY_BOUNDARY,
        )
    if not receipt.is_ancestor_of_child:
        raise PlanError(
            "Recorded boundary is not an ancestor of the child", CATEGORY_BOUNDARY
        )
    if inherited and receipt.commit != facts.parent_head:
        raise PlanError(
            "Recorded boundary disagrees with the inherited parent head",
            CATEGORY_BOUNDARY,
        )
    return Boundary(
        receipt.commit,
        f"maintained-receipt:{receipt.ref}",
        # Only inherited parent history can prove that no inherited commit
        # follows the receipt. Otherwise the receipt is an unverified claim.
        corroborated=inherited,
    )


def check_receipt_ref(boundary_ref: str) -> None:
    """Refuse a boundary ref outside the maintained receipt namespace.

    Parameters
    ----------
    boundary_ref : str
        Ref name supplied by the operator.

    Returns
    -------
    None

    Raises
    ------
    PlanError
        If the ref is not under ``refs/stack-bases/``.
    """
    if not boundary_ref.startswith(RECEIPT_PREFIX):
        raise PlanError(
            f"Use a maintained {RECEIPT_PREFIX} boundary receipt", CATEGORY_BOUNDARY
        )


def check_range(facts: RangeFacts) -> tuple[CommitId, ...]:
    """Accept a replay range only when its topology is replayable in order.

    Pure: this reads typed graph facts and never queries a repository.

    Parameters
    ----------
    facts : RangeFacts
        Typed graph facts about the proposed range.

    Returns
    -------
    tuple[CommitId, ...]
        The accepted commits, oldest first. May be empty.

    Raises
    ------
    PlanError
        If the range contains a merge.
    """
    if facts.contains_merges:
        raise PlanError(
            "The selected range contains merges; use a topology-aware procedure",
            CATEGORY_RANGE,
        )
    return facts.commits


def check_unmoved(evidence: Evidence, current: Identities) -> None:
    """Refuse a plan whose inputs moved while the evidence was being gathered.

    Pure: this compares two typed snapshots.

    Parameters
    ----------
    evidence : Evidence
        Identities frozen at the start of discovery.
    current : Identities
        Identities re-read after the range was computed.

    Returns
    -------
    None

    Raises
    ------
    PlanError
        If the child branch or the target ref moved.
    """
    if current.branch_head != evidence.old_head:
        raise PlanError(
            "Child branch moved during discovery; discard this plan", CATEGORY_RACE
        )
    if current.target != evidence.target:
        raise PlanError(
            "Target ref moved during discovery; discard this plan", CATEGORY_RACE
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


@dataclasses.dataclass(frozen=True)
class ReplayPlan:
    """The reviewable replay decision, in domain terms and no tool's terms.

    This records which commits belong to the replay and what remains unproven.
    It deliberately holds no Git command: rendering one is an adapter concern,
    so the policy stays independent of the tool that would carry it out.

    Parameters
    ----------
    status : str
        ``review-required`` or ``no-op-decision-required``. Never an
        authorization to replay.
    operation : str
        Identifier correlating this plan with the diagnostics that produced it.
    branch : str
        Local child branch the plan applies to.
    parent : ParentPullRequest
        The squash-merged parent the boundary was derived from.
    old_head : CommitId
        Child branch tip the plan was derived from.
    target : CommitId
        Commit the replay would land on.
    boundary : Boundary
        The accepted exclusive boundary and its provenance.
    parent_evidence : ParentEvidence
        The recovered parent head, its landing commit, and the retained ref.
    commits : tuple[CommitId, ...]
        Accepted replay commits, oldest first. May be empty.
    review : tuple[str, ...]
        Obligations this plan does not discharge.
    """

    status: str
    operation: str
    branch: str
    parent: ParentPullRequest
    old_head: CommitId
    target: CommitId
    boundary: Boundary
    parent_evidence: ParentEvidence
    commits: tuple[CommitId, ...]
    review: tuple[str, ...]


def plan_replay(
    branch: str,
    evidence: Evidence,
    boundary: Boundary,
    commits: tuple[CommitId, ...],
) -> ReplayPlan:
    """Decide the reviewable replay from accepted domain values.

    Pure: this reads typed values, never queries a repository, and never
    renders a command for any particular tool.

    Parameters
    ----------
    branch : str
        Local child branch the plan applies to.
    evidence : Evidence
        The snapshot the plan was derived from.
    boundary : Boundary
        The accepted exclusive boundary.
    commits : tuple[CommitId, ...]
        Accepted replay commits, oldest first.

    Returns
    -------
    ReplayPlan
        The decision, in domain terms.
    """
    return ReplayPlan(
        status=STATUS_REVIEW_REQUIRED if commits else STATUS_NO_OP,
        operation=evidence.operation,
        branch=branch,
        parent=evidence.parent,
        old_head=evidence.old_head,
        target=evidence.target,
        boundary=boundary,
        parent_evidence=evidence.parent_evidence,
        commits=commits,
        review=tuple(review_notes(boundary)),
    )


# --------------------------------------------------------------------------
# Diagnostics
# --------------------------------------------------------------------------


def trace(operation: str, event: str, **fields: object) -> None:
    """Emit one bounded, structured diagnostic line on standard error.

    Diagnostics carry only identities and fixed labels, never repository
    contents, credentials, or subprocess output. Standard output stays reserved
    for the plan.

    Parameters
    ----------
    operation : str
        Identifier correlating diagnostics from one run.
    event : str
        Short, stable event name.
    **fields : object
        Additional bounded, JSON-serializable fields for this event.

    Returns
    -------
    None
    """
    record = {"operation": operation, "event": event, **fields}
    print(json.dumps(record, default=str), file=sys.stderr)


@contextlib.contextmanager
def phase(
    operation: str, name: str, *, clock: Clock = time.monotonic, **fields: object
) -> Iterator[None]:
    """Time one phase, record its outcome, and stamp refusals with their phase.

    Every phase emits the same bounded fields, so outcomes and durations
    aggregate without parsing human-readable reasons. A :class:`PlanError`
    leaving this block is stamped with an :class:`ErrorContext` naming the
    innermost phase, so callers never infer the phase from message text.

    Parameters
    ----------
    operation : str
        Identifier correlating diagnostics from one run.
    name : str
        One of the bounded ``PHASE_*`` constants.
    clock : Clock
        Monotonic time source; defaults to :func:`time.monotonic`.
    **fields : object
        Additional bounded identities recorded on the start event.

    Yields
    ------
    None

    Raises
    ------
    PlanError
        Re-raised unchanged, apart from the stamped context.
    """
    started = clock()
    trace(operation, "phase-started", phase=name, **fields)

    def elapsed_ms() -> int:
        return round((clock() - started) * 1000)

    try:
        yield
    except PlanError as exc:
        if exc.context is None:
            exc.context = ErrorContext(operation, name)
        trace(
            operation,
            "phase-finished",
            phase=name,
            outcome=OUTCOME_BLOCKED,
            error_category=exc.category,
            elapsed_ms=elapsed_ms(),
        )
        raise
    else:
        trace(
            operation,
            "phase-finished",
            phase=name,
            outcome=OUTCOME_OK,
            elapsed_ms=elapsed_ms(),
        )


@contextlib.contextmanager
def operation_span(
    operation: str, branch: str, *, clock: Clock = time.monotonic
) -> Iterator[None]:
    """Wrap one restack-planning operation, recording its terminal outcome.

    Parameters
    ----------
    operation : str
        Identifier correlating every diagnostic from this run.
    branch : str
        Child branch being planned, recorded on the start event.
    clock : Clock
        Monotonic time source; defaults to :func:`time.monotonic`.

    Yields
    ------
    None

    Raises
    ------
    PlanError
        Re-raised unchanged, apart from a fallback context for a refusal that
        escaped without passing through any phase.
    """
    started = clock()
    trace(operation, "operation-started", phase=PHASE_OPERATION, branch=branch)

    def elapsed_ms() -> int:
        return round((clock() - started) * 1000)

    try:
        yield
    except PlanError as exc:
        if exc.context is None:
            exc.context = ErrorContext(operation, PHASE_OPERATION)
        trace(
            operation,
            "operation-finished",
            phase=exc.context.phase,
            outcome=OUTCOME_BLOCKED,
            error_category=exc.category,
            elapsed_ms=elapsed_ms(),
        )
        raise
    else:
        trace(
            operation,
            "operation-finished",
            phase=PHASE_OPERATION,
            outcome=OUTCOME_OK,
            elapsed_ms=elapsed_ms(),
        )


def blocked_record(exc: PlanError, operation: str) -> dict[str, str]:
    """Render the terminal blocked result as a bounded, structured record.

    The record carries only fixed labels and the bounded reason. A failing
    process contributes its executable name and exit status, never its output:
    that lives on ``PlanError.detail``, which this deliberately omits. So the
    record never carries command output, credentials, or repository contents.

    Parameters
    ----------
    exc : PlanError
        The refusal to report.
    operation : str
        Operation identifier, used when the refusal carries no context.

    Returns
    -------
    dict[str, str]
        The object written to standard error before exiting with status 2.
    """
    context = exc.context or ErrorContext(operation, PHASE_OPERATION)
    return {
        "status": STATUS_BLOCKED,
        "operation": context.operation,
        "phase": context.phase,
        "outcome": OUTCOME_BLOCKED,
        "category": exc.category,
        "reason": exc.reason,
    }


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


# --------------------------------------------------------------------------
# Adapters
# --------------------------------------------------------------------------


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
                timeout=PROCESS_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as exc:
            raise PlanError(
                f"{program} timed out after {PROCESS_TIMEOUT_SECONDS}s",
                CATEGORY_PROCESS,
                detail=str(exc),
            ) from exc
        except OSError as exc:
            raise PlanError(
                f"Cannot start {program}", CATEGORY_PROCESS, detail=str(exc)
            ) from exc
        if result.returncode not in allowed:
            # The reason stays bounded to the executable and its exit status.
            # The output goes in `detail`, which the blocked record excludes.
            raise PlanError(
                f"{program} exited {result.returncode}",
                CATEGORY_PROCESS,
                detail=result.stderr.strip() or result.stdout.strip(),
            )
        return result.stdout.strip()


def _path_exists(path: Path) -> bool:
    """Report whether a path exists, as the default filesystem probe.

    Parameters
    ----------
    path : Path
        Path to probe.

    Returns
    -------
    bool
        True when the path exists.
    """
    return path.exists()


@dataclasses.dataclass(frozen=True)
class GitGraph:
    """Turns Git queries into typed graph facts for the domain layer.

    Filesystem access lives here rather than in policy, so the domain layer
    never touches a :class:`~pathlib.Path`.

    Parameters
    ----------
    run : Runner
        Process adapter bound to the repository.
    exists : Callable[[Path], bool]
        Filesystem probe, injectable so a caller can substitute one. Defaults
        to :func:`_path_exists`.
    """

    run: Runner
    exists: Callable[[Path], bool] = _path_exists

    def git(self, *args: str) -> str:
        """Run a Git query or the narrowly scoped evidence fetch.

        Parameters
        ----------
        *args : str
            Git subcommand and arguments.

        Returns
        -------
        str
            Stripped standard output.
        """
        return self.run("git", *args)

    def commit(self, ref: str) -> CommitId:
        """Resolve exactly one commit without treating a user ref as an option.

        Parameters
        ----------
        ref : str
            Ref or object name supplied by the operator or by metadata.

        Returns
        -------
        CommitId
            Full commit object ID.
        """
        return CommitId(
            self.git("rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}")
        )

    def is_ancestor(self, older: CommitId, newer: CommitId) -> bool:
        """Ask a real graph query, propagating errors rather than answering no.

        Parameters
        ----------
        older : CommitId
            Candidate ancestor.
        newer : CommitId
            Candidate descendant.

        Returns
        -------
        bool
            True when ``older`` is reachable from ``newer``.
        """
        # rev-list errors remain errors; empty output means every older commit
        # is reachable from newer. Inputs are already resolved commit IDs.
        return not self.git("rev-list", "--max-count=1", older, f"^{newer}")

    def config(self, key: str) -> str:
        """Read one local config value, treating "unset" as an answer.

        Parameters
        ----------
        key : str
            Fully qualified configuration key.

        Returns
        -------
        str
            The recorded value, or the empty string when unset.
        """
        return self.run("git", "config", "--local", "--get", key, allowed=(0, 1))

    def check_ref_format(self, ref: str) -> None:
        """Refuse a ref name Git itself considers malformed.

        Parameters
        ----------
        ref : str
            Fully qualified ref name.

        Returns
        -------
        None
        """
        self.git("check-ref-format", ref)

    def git_path(self, name: str, repository: Path) -> Path:
        """Resolve a path inside the Git directory, honouring worktree layouts.

        Parameters
        ----------
        name : str
            Name relative to the Git directory.
        repository : Path
            Repository root, used to absolutize a relative answer.

        Returns
        -------
        Path
            The resolved path, which may not exist.
        """
        path = Path(self.git("rev-parse", "--git-path", name))
        return path if path.is_absolute() else repository / path

    def path_exists(self, name: str, repository: Path) -> bool:
        """Report whether a Git-directory entry exists, never guessing on failure.

        A filesystem error is a refusal, not an answer: treating it as "marker
        absent" would let discovery proceed over an in-flight Git operation.

        Parameters
        ----------
        name : str
            Name relative to the Git directory.
        repository : Path
            Repository root, used to absolutize a relative answer.

        Returns
        -------
        bool
            True when the entry exists.

        Raises
        ------
        PlanError
            Categorized as a process failure when the probe itself fails.
        """
        path = self.git_path(name, repository)
        try:
            return self.exists(path)
        except OSError as exc:
            raise PlanError(
                f"Cannot determine whether {name} exists: {exc}", CATEGORY_PROCESS
            ) from exc

    def is_shallow(self) -> bool:
        """Report whether the repository has incomplete history.

        Returns
        -------
        bool
            True when the clone is shallow.
        """
        return self.git("rev-parse", "--is-shallow-repository") != "false"

    def is_dirty(self) -> bool:
        """Report whether the checkout holds staged, unstaged or untracked work.

        Returns
        -------
        bool
            True when anything would be lost by proceeding.
        """
        return bool(self.git("status", "--porcelain=v1", "--untracked-files=all"))

    def identities(self, branch: str, target_ref: str) -> Identities:
        """Resolve the child branch and target tips together.

        Parameters
        ----------
        branch : str
            Local child branch name.
        target_ref : str
            Fetched target ref.

        Returns
        -------
        Identities
            Both tips, resolved at the same point in time.
        """
        return Identities(self.commit(f"refs/heads/{branch}"), self.commit(target_ref))

    def fetch_parent_head(
        self, parent: ParentPullRequest, evidence_ref: str
    ) -> CommitId:
        """Fetch the PR head, never the synthetic merge ref, into a private ref.

        Parameters
        ----------
        parent : ParentPullRequest
            Parent PR whose head is recovered.
        evidence_ref : str
            Private ref the head is written to.

        Returns
        -------
        CommitId
            The fetched parent head.
        """
        self.git(
            "-c",
            "gc.auto=0",
            "-c",
            "maintenance.auto=false",
            "fetch",
            "--no-prune",
            "--no-tags",
            "--no-write-fetch-head",
            f"https://github.com/{parent.repository}.git",
            f"refs/pull/{parent.number}/head:{evidence_ref}",
        )
        return self.commit(evidence_ref)

    def boundary_facts(
        self,
        parent_head: CommitId,
        old_head: CommitId,
        branch: str,
        boundary_ref: str | None,
    ) -> BoundaryFacts:
        """Gather every graph fact the boundary policy needs, and nothing more.

        Parameters
        ----------
        parent_head : CommitId
            Recovered parent PR head.
        old_head : CommitId
            Child branch tip.
        branch : str
            Local child branch name, used to read the receipt identity.
        boundary_ref : str | None
            Maintained receipt ref, or None.

        Returns
        -------
        BoundaryFacts
            Typed facts for :func:`select_boundary`.
        """
        inherited = self.is_ancestor(parent_head, old_head)
        candidates: tuple[CommitId, ...] = ()
        receipt: ReceiptFacts | None = None
        if boundary_ref is None:
            if not inherited:
                candidates = tuple(
                    CommitId(line)
                    for line in self.git(
                        "merge-base", "--all", parent_head, old_head
                    ).splitlines()
                )
        else:
            check_receipt_ref(boundary_ref)
            self.check_ref_format(boundary_ref)
            recorded = self.config(f"branch.{branch}.stackParent")
            commit = self.commit(boundary_ref)
            receipt = ReceiptFacts(
                boundary_ref,
                commit,
                recorded,
                self.is_ancestor(commit, old_head),
            )
        return BoundaryFacts(parent_head, old_head, inherited, candidates, receipt)

    def range_facts(self, old_base: CommitId, old_head: CommitId) -> RangeFacts:
        """Gather the topology facts the range policy needs.

        Parameters
        ----------
        old_base : CommitId
            Exclusive boundary.
        old_head : CommitId
            Inclusive tip.

        Returns
        -------
        RangeFacts
            Typed facts for :func:`check_range`.
        """
        series = f"{old_base}..{old_head}"
        merges = bool(self.git("rev-list", "--merges", series))
        commits = tuple(
            CommitId(line)
            for line in self.git("rev-list", "--reverse", series).splitlines()
        )
        return RangeFacts(old_base, old_head, commits, merges)


@dataclasses.dataclass(frozen=True)
class GitHubCli:
    """Parses and validates ``gh`` output into typed parent metadata.

    Parameters
    ----------
    run : Runner
        Process adapter bound to the repository.
    """

    run: Runner

    def parent_metadata(self, parent: ParentPullRequest) -> tuple[str, str]:
        """Validate the CLI response before using any source or landing identity.

        Parameters
        ----------
        parent : ParentPullRequest
            Identity naming the parent PR to query.

        Returns
        -------
        tuple[str, str]
            The reported head commit ID and landing commit ID, unresolved.

        Raises
        ------
        PlanError
            If ``gh`` fails, returns malformed output, reports a different PR or
            repository, reports an unmerged PR, or omits a valid commit ID.
        """
        output = self.run(
            "gh",
            "api",
            f"repos/{parent.repository}/pulls/{parent.number}",
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
            or metadata["number"] != parent.number
        ):
            raise PlanError(
                "Parent PR identity disagrees with the request", CATEGORY_METADATA
            )
        repository = metadata.get("base_repository")
        if (
            not isinstance(repository, str)
            or repository.casefold() != parent.repository.casefold()
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
                    f"Parent metadata has no valid {field} commit ID",
                    CATEGORY_METADATA,
                )
        return str(metadata["head_sha"]), str(metadata["landed"])


def rebase_argv(plan: ReplayPlan) -> list[str] | None:
    """Render the proposed Git replay command for a plan.

    This is an adapter: it turns a domain decision into one tool's argv. It
    sits outside the domain layer deliberately, so replay policy never depends
    on Git's command-line surface.

    Parameters
    ----------
    plan : ReplayPlan
        The decision to render a command for.

    Returns
    -------
    list[str] | None
        The proposed argv, or None when the plan proposes no replay.
    """
    if not plan.commits:
        return None
    return [*REBASE_PREFIX, plan.target, plan.boundary.old_base, plan.branch]


def render_document(plan: ReplayPlan) -> dict[str, object]:
    """Render the plan as the JSON document the CLI prints.

    This is the serialization boundary: it names the wire fields and attaches
    the tool-specific argv from :func:`rebase_argv`.

    Parameters
    ----------
    plan : ReplayPlan
        The decision to serialize.

    Returns
    -------
    dict[str, object]
        The document written to standard output on a successful run.
    """
    return {
        "status": plan.status,
        "operation": plan.operation,
        "branch": plan.branch,
        "old_head": plan.old_head,
        "target": plan.target,
        "old_base": plan.boundary.old_base,
        "parent_head": plan.parent_evidence.head,
        "landed": plan.parent_evidence.landed,
        "parent_pr": str(plan.parent),
        "boundary_evidence": plan.boundary.evidence,
        "boundary_corroborated": plan.boundary.corroborated,
        "evidence_ref": plan.parent_evidence.evidence_ref,
        "commits": list(plan.commits),
        "rebase_argv": rebase_argv(plan),
        "review": list(plan.review),
    }


# --------------------------------------------------------------------------
# Request and preflight
# --------------------------------------------------------------------------


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

    @property
    def parent(self) -> ParentPullRequest:
        """Return the parent PR as a typed identity.

        Returns
        -------
        ParentPullRequest
            The identity the domain layer consumes.
        """
        return ParentPullRequest(self.parent_repository, self.parent_pr)


def _refuse_active_operation(graph: GitGraph, repository: Path) -> None:
    """Refuse incomplete history, another in-flight Git operation, or dirty work.

    Parameters
    ----------
    graph : GitGraph
        Graph adapter bound to the repository.
    repository : Path
        Repository root, used to absolutize Git-directory paths.

    Returns
    -------
    None

    Raises
    ------
    PlanError
        If the history is shallow, another Git operation is in progress, or the
        checkout holds staged, unstaged, or untracked work.
    """
    if graph.is_shallow():
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
        if graph.path_exists(name, repository):
            raise PlanError(
                f"An active Git operation exists: {name}", CATEGORY_REPOSITORY_STATE
            )
    if graph.is_dirty():
        raise PlanError(
            "Preserve staged, unstaged and untracked work before planning",
            CATEGORY_REPOSITORY_STATE,
        )


def preflight(graph: GitGraph, request: Request) -> Identities:
    """Freeze identities and refuse incomplete history or an occupied checkout.

    Parameters
    ----------
    graph : GitGraph
        Graph adapter bound to the repository.
    request : Request
        Operator-supplied identities to validate.

    Returns
    -------
    Identities
        The child branch tip and the target ref tip.

    Raises
    ------
    PlanError
        Propagated from :func:`check_identities` or
        :func:`_refuse_active_operation`, or raised when either ref does not
        resolve to exactly one commit.
    """
    check_identities(request.parent, request.branch)
    graph.check_ref_format(f"refs/heads/{request.branch}")
    _refuse_active_operation(graph, request.repository)
    return graph.identities(request.branch, request.target_ref)


# --------------------------------------------------------------------------
# Command layer and read path
# --------------------------------------------------------------------------


def discover(
    request: Request,
    run: Runner | None = None,
    *,
    operation: str | None = None,
    new_operation_id: Callable[[], str] = _new_operation_id,
    new_evidence_ref: Callable[[], str] = _new_evidence_ref,
    clock: Clock = time.monotonic,
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
    operation : str | None
        Diagnostic correlation identifier; generated when not supplied, so the
        CLI can create it before discovery and reuse it in a terminal record.
    new_operation_id : Callable[[], str]
        Supplies ``operation`` when it is not given.
    new_evidence_ref : Callable[[], str]
        Supplies the private ref name the fetched parent head is written to.
    clock : Clock
        Monotonic time source for phase durations.

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
    graph = GitGraph(run)
    cli = GitHubCli(run)
    operation = new_operation_id() if operation is None else operation
    parent = request.parent

    with phase(operation, PHASE_PREFLIGHT, branch=request.branch, clock=clock):
        identities = preflight(graph, request)
    with phase(operation, PHASE_PARENT_METADATA, parent_pr=str(parent), clock=clock):
        reported_head, reported_landed = cli.parent_metadata(parent)
    with phase(operation, PHASE_LANDING_VALIDATION, clock=clock):
        landed = graph.commit(reported_landed)
        if not graph.is_ancestor(landed, identities.target):
            raise PlanError(
                "Parent landing commit is not reachable from the target",
                CATEGORY_METADATA,
            )
    with phase(operation, PHASE_PARENT_HEAD_FETCH, clock=clock):
        evidence_ref = new_evidence_ref()
        parent_head = graph.fetch_parent_head(parent, evidence_ref)
        if parent_head != reported_head:
            raise PlanError(
                f"Fetched PR head disagrees with metadata; retain {evidence_ref}",
                CATEGORY_RECOVERY,
            )

    trace(
        operation,
        "evidence-frozen",
        phase=PHASE_PARENT_HEAD_FETCH,
        old_head=identities.branch_head,
        target=identities.target,
        parent_head=parent_head,
        evidence_ref=evidence_ref,
    )
    return Evidence(
        operation,
        parent,
        identities.branch_head,
        identities.target,
        ParentEvidence(parent_head, landed, evidence_ref),
    )


def build_plan(
    request: Request,
    evidence: Evidence,
    run: Runner | None = None,
    *,
    clock: Clock = time.monotonic,
) -> dict[str, object]:
    """Derive an explicit replay range from frozen evidence, never run a rebase.

    This is the read path. It consumes an already collected snapshot and never
    invokes :func:`discover`, so it performs no network access, writes no ref,
    and generates no identifier. It reads the local graph through an adapter,
    then applies pure policy to typed facts.

    A successful plan still requires ownership and semantic review: it does not
    prove the merge method, receipt freshness, worktree ownership, or that later
    target history did not revert parent functionality.

    Parameters
    ----------
    request : Request
        Operator-supplied identities.
    evidence : Evidence
        Snapshot returned by :func:`discover`.
    run : Runner | None
        Process adapter; defaults to a :class:`Subprocess` bound to
        ``request.repository``.
    clock : Clock
        Monotonic time source for phase durations.

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
    graph = GitGraph(run)
    operation = evidence.operation

    with phase(operation, PHASE_BOUNDARY_SELECTION, clock=clock):
        facts = graph.boundary_facts(
            evidence.parent_evidence.head,
            evidence.old_head,
            request.branch,
            request.boundary_ref,
        )
        boundary = select_boundary(evidence.parent, facts)
    trace(
        operation,
        "boundary-selected",
        phase=PHASE_BOUNDARY_SELECTION,
        old_base=boundary.old_base,
        evidence=boundary.evidence,
        corroborated=boundary.corroborated,
    )
    with phase(operation, PHASE_GRAPH_PLANNING, clock=clock):
        commits = check_range(graph.range_facts(boundary.old_base, evidence.old_head))
        check_unmoved(evidence, graph.identities(request.branch, request.target_ref))

    plan = plan_replay(request.branch, evidence, boundary, commits)
    trace(
        operation,
        "plan-built",
        phase=PHASE_GRAPH_PLANNING,
        status=plan.status,
        commits=len(commits),
    )
    return render_document(plan)


def discover_and_plan(
    request: Request,
    run: Runner | None = None,
    *,
    operation: str | None = None,
    clock: Clock = time.monotonic,
) -> dict[str, object]:
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
    operation : str | None
        Diagnostic correlation identifier; generated when not supplied.
    clock : Clock
        Monotonic time source for phase durations.

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
    evidence = discover(request, run, operation=operation, clock=clock)
    return build_plan(request, evidence, run, clock=clock)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


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

    The CLI owns the operation identifier: it creates one, calls discovery
    first and plan construction second, and reports a terminal record either
    way. A successful plan is written to standard output; a refusal is written
    to standard error as a bounded ``blocked`` object and exits with status 2,
    leaving standard output empty.

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
        With status 2 when discovery or plan construction raises
        :class:`PlanError`. The bounded blocked record, including the operation
        identifier, failing phase, outcome and category, is written to standard
        error; standard output stays empty.
    """
    request = Request(
        repository.resolve(),
        branch,
        target_ref,
        parent_repository,
        parent_pr,
        boundary_ref,
    )
    # Composition root: the real adapters and time source are bound here, and
    # nowhere below, so every layer beneath stays substitutable.
    run = Subprocess(request.repository)
    clock: Clock = time.monotonic
    operation = _new_operation_id()
    try:
        with operation_span(operation, request.branch, clock=clock):
            evidence = discover(request, run, operation=operation, clock=clock)
            result = build_plan(request, evidence, run, clock=clock)
    except PlanError as exc:
        print(json.dumps(blocked_record(exc, operation)), file=sys.stderr)
        raise SystemExit(2) from exc
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    import cyclopts

    cyclopts.run(main)
