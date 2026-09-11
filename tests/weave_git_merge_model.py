"""Pure-Python model of the stateful behaviour the Weave skill documents.

The functions here encode three documented concerns as deterministic rules so
that property tests can search their input spaces without invoking Git:

- **Attribute-scope fallback.** Which bypass makes the effective `merge`
  attribute `unspecified` for a rule supplied by each attribute source, and
  the `core.attributesFile` absent-versus-unset pitfall.
- **Stage validity.** Which index stages exist for a conflicted path, which of
  them may be parsed, and which may be trusted as a baseline.
- **Multi-commit replay transitions.** How the result of one replayed commit
  becomes the `ours` input of the next, and why a clean-exit but structurally
  invalid early result can never be accepted as a safe later `ours` stage.

Nothing here calls Git. The rules are transcriptions of
`skills/weave-git-merge/SKILL.md` and its `references/behaviour.md`; the
real-Git grounding lives in `test_weave_git_merge_procedures.py`.
"""

from __future__ import annotations

import dataclasses as dc
import enum
import typing as typ

if typ.TYPE_CHECKING:
    from collections.abc import Iterable, Sequence


class Operation(enum.StrEnum):
    """Git operations the skill's stateful guidance distinguishes.

    Attributes
    ----------
    REBASE : Operation
        Replaying commits one at a time.
    MERGE : Operation
        A single merge commit.
    """

    REBASE = "rebase"
    MERGE = "merge"


class Scope(enum.StrEnum):
    """Attribute sources that can supply a `merge=weave` rule.

    Attributes
    ----------
    TRACKED : Scope
        Tracked `.gitattributes` committed to the repository.
    CLONE_LOCAL : Scope
        `.git/info/attributes` local to the clone.
    GLOBAL : Scope
        The global attributes file named by `core.attributesFile`.
    """

    TRACKED = "tracked"
    CLONE_LOCAL = "clone-local"
    GLOBAL = "global"


class Bypass(enum.StrEnum):
    """Bypasses the skill's scope matrix documents.

    Attributes
    ----------
    NONE : Bypass
        No bypass in effect.
    DEV_NULL_ATTRIBUTES_FILE : Bypass
        `git -c core.attributesFile=/dev/null ...`.
    PATH_UNSET_MERGE : Bypass
        A later, path-specific `path !merge` line in
        `.git/info/attributes`.
    """

    NONE = "none"
    # `git -c core.attributesFile=/dev/null ...`
    DEV_NULL_ATTRIBUTES_FILE = "core.attributesFile=/dev/null"
    # A later, path-specific `path !merge` line in `.git/info/attributes`.
    PATH_UNSET_MERGE = "path-specific !merge"


WEAVE: typ.Final = "weave"
UNSPECIFIED: typ.Final = "unspecified"

DOCUMENTED_BYPASS: typ.Final[dict[Scope, Bypass]] = {
    Scope.GLOBAL: Bypass.DEV_NULL_ATTRIBUTES_FILE,
    Scope.TRACKED: Bypass.PATH_UNSET_MERGE,
    Scope.CLONE_LOCAL: Bypass.PATH_UNSET_MERGE,
}

DEFAULT_GLOBAL_ATTRIBUTES_SUFFIX: typ.Final = "git/attributes"


# --- Attribute-scope fallback ----------------------------------------------


def active_sources(sources: Iterable[Scope], bypass: Bypass) -> frozenset[Scope]:
    """Return the attribute sources still able to select Weave under `bypass`.

    `core.attributesFile=/dev/null` disables only the global attributes file;
    tracked `.gitattributes` and `.git/info/attributes` still apply. A later
    path-specific `!merge` line in `.git/info/attributes` outranks every other
    source for that path, so no source can select Weave for it.

    Parameters
    ----------
    sources : Iterable[Scope]
        Attribute sources currently supplying `merge=weave` for the path.
    bypass : Bypass
        Bypass in effect, if any.

    Returns
    -------
    frozenset[Scope]
        Sources still able to select Weave under `bypass`.
    """
    selected = frozenset(sources)
    if bypass is Bypass.DEV_NULL_ATTRIBUTES_FILE:
        return selected - {Scope.GLOBAL}
    if bypass is Bypass.PATH_UNSET_MERGE:
        return frozenset()
    return selected


def effective_merge_attribute(sources: Iterable[Scope], bypass: Bypass) -> str:
    """Return what `git check-attr merge -- path` reports under `bypass`.

    `sources` names every scope currently supplying `merge=weave` for the
    path; an empty collection means no source selects Weave.

    Parameters
    ----------
    sources : Iterable[Scope]
        Every scope currently supplying `merge=weave` for the path; an
        empty collection means no source selects Weave.
    bypass : Bypass
        Bypass in effect, if any.

    Returns
    -------
    str
        `weave` if a source still selects Weave under `bypass`,
        otherwise `unspecified`.
    """
    return WEAVE if active_sources(sources, bypass) else UNSPECIFIED


def global_attributes_path(
    configured: str | None, xdg_config_home: str | None, home: str
) -> str:
    """Return the global attributes file Git consults.

    `git config --path --get core.attributesFile` prints nothing and exits
    non-zero when the setting is absent. That means the default path applies,
    not that no global rule exists.

    Parameters
    ----------
    configured : str | None
        Value of `core.attributesFile`, or `None` when unset.
    xdg_config_home : str | None
        Value of `$XDG_CONFIG_HOME`, or `None` when unset.
    home : str
        Value of `$HOME`.

    Returns
    -------
    str
        Path Git consults for global attributes.
    """
    if configured:
        return configured
    base = xdg_config_home or f"{home}/.config"
    return f"{base}/{DEFAULT_GLOBAL_ATTRIBUTES_SUFFIX}"


# --- Stage validity --------------------------------------------------------


@dc.dataclass(frozen=True)
class ConflictCase:
    """One conflicted path with the per-stage facts an agent can observe.

    Attributes
    ----------
    operation : Operation
        Git operation producing the conflict.
    base_present : bool
        Whether a stage 1 (base) blob exists for the path.
    base_parses : bool
        Whether the stage 1 blob parses.
    ours_parses : bool
        Whether the stage 2 (ours) blob parses.
    theirs_parses : bool
        Whether the stage 3 (theirs) blob parses.
    ours_present : bool
        Whether a stage 2 (ours) blob exists for the path. It is absent when
        the path was deleted on the current side of a modify/delete conflict.
    theirs_present : bool
        Whether a stage 3 (theirs) blob exists for the path. It is absent when
        the path was deleted on the other side of a modify/delete conflict.
    prior_unverified_replays : int
        Count of earlier replayed commits in the same rebase whose
        results have not passed a structural gate. Always zero for a
        merge, which replays nothing.

    Raises
    ------
    ValueError
        If `prior_unverified_replays` is negative, or if `operation` is
        `Operation.MERGE` and `prior_unverified_replays` is non-zero.
    """

    operation: Operation
    base_present: bool
    base_parses: bool
    ours_parses: bool
    theirs_parses: bool
    prior_unverified_replays: int = 0
    ours_present: bool = True
    theirs_present: bool = True

    def __post_init__(self) -> None:
        if self.prior_unverified_replays < 0:
            msg = "prior_unverified_replays must not be negative"
            raise ValueError(msg)
        if self.operation is Operation.MERGE and self.prior_unverified_replays:
            msg = "a merge replays nothing, so it has no prior replays"
            raise ValueError(msg)


BASE_STAGE: typ.Final = 1
OURS_STAGE: typ.Final = 2
THEIRS_STAGE: typ.Final = 3


def existing_stages(case: ConflictCase) -> frozenset[int]:
    """Return the index stages Git holds for the conflicted path.

    Stage 1 is absent when the sides share no ancestor blob. Stage 2 or
    stage 3 is absent when that side deleted the path (a modify/delete
    conflict). The skill says to run the stage commands only for stages that
    exist.

    Parameters
    ----------
    case : ConflictCase
        Conflicted path facts to inspect.

    Returns
    -------
    frozenset[int]
        Stages Git holds for the path.
    """
    present = {
        BASE_STAGE: case.base_present,
        OURS_STAGE: case.ours_present,
        THEIRS_STAGE: case.theirs_present,
    }
    return frozenset(stage for stage, held in present.items() if held)


def parseable_stages(case: ConflictCase) -> frozenset[int]:
    """Return the existing stages whose blobs parse.

    Only stages that exist may be parsed; the skill says to run the stage
    commands only for stages that exist.

    Parameters
    ----------
    case : ConflictCase
        Conflicted path facts to inspect.

    Returns
    -------
    frozenset[int]
        Existing stages whose blobs parse.
    """
    parses = {
        BASE_STAGE: case.base_parses,
        OURS_STAGE: case.ours_parses,
        THEIRS_STAGE: case.theirs_parses,
    }
    return frozenset(stage for stage in existing_stages(case) if parses[stage])


def trusted_stages(case: ConflictCase) -> frozenset[int]:
    """Return the stages an agent may treat as a trusted baseline.

    A stage must exist and parse to be trusted. During a multi-commit rebase,
    stage 2 is additionally untrusted while any earlier replay is unverified,
    because it can already hold a silently corrupted earlier result. A
    parsing stage 3 never makes a non-parsing stage 2 safe.

    Parameters
    ----------
    case : ConflictCase
        Conflicted path facts to inspect.

    Returns
    -------
    frozenset[int]
        Stages an agent may treat as a trusted baseline.
    """
    trusted = set(parseable_stages(case))
    if case.operation is Operation.REBASE and case.prior_unverified_replays:
        trusted.discard(OURS_STAGE)
    return frozenset(trusted)


def resolution_may_continue(case: ConflictCase, resolved_parses: bool) -> bool:
    """Return whether `git add` and `--continue` are permitted for the path.

    The resolved working file must parse, and an existing stage 2 must be a
    trusted baseline: an earlier corrupt replay cannot be laundered by a clean
    later resolution built on top of it. When stage 2 is absent (the current
    side deleted the path) there is no baseline to trust or distrust, so only
    the resolved file's parse decides.

    Parameters
    ----------
    case : ConflictCase
        Conflicted path facts to inspect.
    resolved_parses : bool
        Whether the resolved working file parses.

    Returns
    -------
    bool
        Whether `git add` and `--continue` are permitted for the path.
    """
    if not resolved_parses:
        return False
    if OURS_STAGE not in existing_stages(case):
        return True
    return OURS_STAGE in trusted_stages(case)


# --- Multi-commit replay transitions --------------------------------------


class DriverExit(enum.IntEnum):
    """Weave driver exit statuses the skill interprets.

    Attributes
    ----------
    CLEAN : DriverExit
        The driver replayed the commit without conflict.
    CONFLICT : DriverExit
        The driver left conflict markers to resolve.
    FAILURE : DriverExit
        The driver failed outright.
    """

    CLEAN = 0
    CONFLICT = 1
    FAILURE = 2


@dc.dataclass(frozen=True)
class ReplayOutcome:
    """What the driver did for one replayed commit.

    Attributes
    ----------
    exit_code : DriverExit
        Exit status the driver reported for this replay.
    structurally_valid : bool
        Whether the driver's produced result is structurally valid.
    """

    exit_code: DriverExit
    structurally_valid: bool


@dc.dataclass(frozen=True)
class ReplayState:
    """The modelled state after one replayed commit.

    `ours_input_safe` records whether the `ours` side Git handed the driver
    derived from a safe earlier result. `git_accepted` records whether Git
    recorded the result and moved on. `safe` is the andon verdict: whether
    the produced result may be accepted as the next commit's `ours` stage.

    Attributes
    ----------
    index : int
        Position of this replay within the fold, starting at 0.
    ours_input_safe : bool
        Whether the `ours` side Git handed the driver derived from a
        safe earlier result.
    outcome : ReplayOutcome
        Driver's exit status and structural-validity verdict for this
        replay.
    git_accepted : bool
        Whether Git recorded the result and moved on.
    safe : bool
        Andon verdict: whether the produced result may be accepted as
        the next commit's `ours` stage.
    """

    index: int
    ours_input_safe: bool
    outcome: ReplayOutcome
    git_accepted: bool
    safe: bool


def fold_replays(
    outcomes: Sequence[ReplayOutcome], *, per_replay_guard: bool
) -> tuple[ReplayState, ...]:
    """Fold replay outcomes into per-commit states.

    Commit 0 replays onto the target, which is safe by definition. Commit N's
    `ours` input derives from commit N-1's produced result. The fold stops at
    the first replay Git does not accept (a conflict or a driver failure), or,
    with a per-replay guard, at the first replay whose result is unsafe.

    A clean exit lets Git accept the result regardless of its validity. The
    andon rule marks a result safe only when the driver exited cleanly, the
    result is structurally valid, and the `ours` input it was built on was
    itself safe; a structurally invalid early result is therefore never
    accepted as a safe later `ours` stage.

    Parameters
    ----------
    outcomes : Sequence[ReplayOutcome]
        Per-commit driver results to fold, in replay order.
    per_replay_guard : bool
        Whether to stop folding at the first unsafe replay rather than
        continuing until Git itself rejects one.

    Returns
    -------
    tuple[ReplayState, ...]
        Modelled state for each replay processed before the fold
        stopped.
    """
    states: list[ReplayState] = []
    ours_input_safe = True
    for index, outcome in enumerate(outcomes):
        git_accepted = outcome.exit_code is DriverExit.CLEAN
        safe = git_accepted and outcome.structurally_valid and ours_input_safe
        states.append(
            ReplayState(
                index=index,
                ours_input_safe=ours_input_safe,
                outcome=outcome,
                git_accepted=git_accepted,
                safe=safe,
            )
        )
        if not git_accepted or (per_replay_guard and not safe):
            break
        ours_input_safe = safe
    return tuple(states)


def sequence_is_safe(states: Sequence[ReplayState]) -> bool:
    """Return whether every replay Git accepted is also safe.

    Parameters
    ----------
    states : Sequence[ReplayState]
        Modelled replay states to check.

    Returns
    -------
    bool
        Whether every replay Git accepted is also safe.
    """
    return all(state.safe for state in states if state.git_accepted)


def safe_prefix_length(states: Sequence[ReplayState]) -> int:
    """Return how many leading replays were accepted by Git and safe.

    Parameters
    ----------
    states : Sequence[ReplayState]
        Modelled replay states to check, in replay order.

    Returns
    -------
    int
        Count of leading replays accepted by Git and safe.
    """
    count = 0
    for state in states:
        if not (state.git_accepted and state.safe):
            break
        count += 1
    return count
