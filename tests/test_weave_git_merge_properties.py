"""Property tests for the pure-Python Weave git-merge model.

These tests drive `weave_git_merge_model` (see its module docstring) to check
the documented invariants around attribute-scope fallback, index-stage
validity, and multi-commit replay transitions, without invoking Git.
"""

from __future__ import annotations

import dataclasses as dc

from hypothesis import given
from hypothesis import strategies as st
import pytest

import weave_git_merge_model as model

# --- Module-level strategies -------------------------------------------------

OPERATIONS = st.sampled_from(list(model.Operation))
SCOPES = st.sampled_from(list(model.Scope))
SCOPE_SETS = st.frozensets(SCOPES)
BYPASSES = st.sampled_from(list(model.Bypass))

REPLAY_OUTCOMES = st.builds(
    model.ReplayOutcome,
    exit_code=st.sampled_from(list(model.DriverExit)),
    structurally_valid=st.booleans(),
)
REPLAY_SEQUENCES = st.lists(REPLAY_OUTCOMES, min_size=2, max_size=8)
CLEAN_REPLAY_OUTCOMES = st.builds(
    model.ReplayOutcome,
    exit_code=st.just(model.DriverExit.CLEAN),
    structurally_valid=st.booleans(),
)
CLEAN_REPLAY_SEQUENCES = st.lists(CLEAN_REPLAY_OUTCOMES, min_size=2, max_size=8)

_MERGE_CONFLICT_CASES = st.builds(
    model.ConflictCase,
    operation=st.just(model.Operation.MERGE),
    base_present=st.booleans(),
    base_parses=st.booleans(),
    ours_parses=st.booleans(),
    theirs_parses=st.booleans(),
    prior_unverified_replays=st.just(0),
)
_REBASE_CONFLICT_CASES = st.builds(
    model.ConflictCase,
    operation=st.just(model.Operation.REBASE),
    base_present=st.booleans(),
    base_parses=st.booleans(),
    ours_parses=st.booleans(),
    theirs_parses=st.booleans(),
    prior_unverified_replays=st.integers(min_value=0, max_value=5),
)
CONFLICT_CASES = st.one_of(_MERGE_CONFLICT_CASES, _REBASE_CONFLICT_CASES)


# --- Attribute-scope fallback properties -------------------------------------


@given(scope=SCOPES)
def test_documented_bypass_disables_its_own_scope(scope: model.Scope) -> None:
    """The bypass the skill documents for a scope always yields unspecified."""
    bypass = model.DOCUMENTED_BYPASS[scope]

    result = model.effective_merge_attribute({scope}, bypass)

    assert result == model.UNSPECIFIED, (
        "documented bypass failed to disable its own scope"
    )


@given(
    scope=st.sampled_from([model.Scope.TRACKED, model.Scope.CLONE_LOCAL]),
    others=SCOPE_SETS,
)
def test_dev_null_attributes_file_does_not_disable_tracked_or_clone_local(
    scope: model.Scope, others: frozenset[model.Scope]
) -> None:
    """`core.attributesFile=/dev/null` leaves tracked and clone-local rules live."""
    sources = others | {scope}

    result = model.effective_merge_attribute(
        sources, model.Bypass.DEV_NULL_ATTRIBUTES_FILE
    )

    assert result == model.WEAVE, (
        "the wrong bypass unexpectedly disabled a non-global scope"
    )


@given(sources=SCOPE_SETS)
def test_dev_null_attributes_file_disables_only_global_source(
    sources: frozenset[model.Scope],
) -> None:
    """`/dev/null` removes only the global source from the active set."""
    active = model.active_sources(sources, model.Bypass.DEV_NULL_ATTRIBUTES_FILE)

    assert active == sources - {model.Scope.GLOBAL}, (
        "/dev/null bypass changed a source other than global"
    )
    expect_weave = bool(sources - {model.Scope.GLOBAL})
    result = model.effective_merge_attribute(
        sources, model.Bypass.DEV_NULL_ATTRIBUTES_FILE
    )

    assert (result == model.WEAVE) == expect_weave, (
        "effective attribute disagreed with the non-global source count"
    )


@given(sources=SCOPE_SETS)
def test_path_unset_merge_always_yields_unspecified(
    sources: frozenset[model.Scope],
) -> None:
    """A later path-specific `!merge` line outranks every other source."""
    result = model.effective_merge_attribute(sources, model.Bypass.PATH_UNSET_MERGE)

    assert result == model.UNSPECIFIED, (
        "path-specific unset failed to outrank every attribute source"
    )


@given(sources=SCOPE_SETS)
def test_no_bypass_yields_weave_iff_sources_non_empty(
    sources: frozenset[model.Scope],
) -> None:
    """With no bypass, Weave applies exactly when some source selects it."""
    result = model.effective_merge_attribute(sources, model.Bypass.NONE)

    assert (result == model.WEAVE) == bool(sources), (
        "no-bypass result disagreed with whether any source was active"
    )


@given(
    xdg_config_home=st.one_of(st.none(), st.text(max_size=20)),
    home=st.text(min_size=1, max_size=20),
)
def test_absent_configured_attributes_file_still_yields_a_global_path(
    xdg_config_home: str | None, home: str
) -> None:
    """An absent `core.attributesFile` still points at a default global rule."""
    path = model.global_attributes_path(None, xdg_config_home, home)

    assert path != "", "an absent setting must not read as no global rule location"
    assert path.endswith("git/attributes"), (
        "the default global attributes path lost its documented suffix"
    )
    if xdg_config_home:
        assert path == f"{xdg_config_home}/git/attributes", (
            "an XDG config home was not used as the base of the default path"
        )
    else:
        assert path == f"{home}/.config/git/attributes", (
            "a missing XDG config home did not fall back to ~/.config"
        )


@given(
    configured=st.text(min_size=1, max_size=30),
    xdg_config_home=st.one_of(st.none(), st.text(max_size=20)),
    home=st.text(min_size=1, max_size=20),
)
def test_configured_attributes_file_is_returned_verbatim(
    configured: str, xdg_config_home: str | None, home: str
) -> None:
    """A configured `core.attributesFile` value overrides the default path."""
    path = model.global_attributes_path(configured, xdg_config_home, home)

    assert path == configured, "a configured value was not returned verbatim"


@given(
    xdg_config_home=st.one_of(st.none(), st.text(max_size=20)),
    home=st.text(min_size=1, max_size=20),
)
def test_empty_configured_attributes_file_falls_back_to_default(
    xdg_config_home: str | None, home: str
) -> None:
    """An empty configured value is treated the same as an absent one."""
    absent_path = model.global_attributes_path(None, xdg_config_home, home)
    empty_path = model.global_attributes_path("", xdg_config_home, home)

    assert empty_path == absent_path, (
        "an empty configured value diverged from the absent-value default"
    )


# --- Stage-validity properties -----------------------------------------------


@given(case=CONFLICT_CASES)
def test_parseable_and_trusted_stages_are_nested(case: model.ConflictCase) -> None:
    """Parseable stages exist, and trusted stages are always parseable."""
    parseable = model.parseable_stages(case)
    trusted = model.trusted_stages(case)

    assert parseable <= model.existing_stages(case), (
        "a parseable stage was reported that does not exist"
    )
    assert trusted <= parseable, "a trusted stage was reported that does not parse"


@given(case=CONFLICT_CASES)
def test_base_absence_hides_stage_one_everywhere(case: model.ConflictCase) -> None:
    """Stage 1 never appears for a conflict without a common ancestor blob."""
    if case.base_present:
        assert model.BASE_STAGE in model.existing_stages(case), (
            "a present base was not reported as existing at stage 1"
        )
        return

    assert model.BASE_STAGE not in model.existing_stages(case), (
        "an absent base was reported as an existing stage"
    )
    assert model.BASE_STAGE not in model.parseable_stages(case), (
        "an absent base was reported as a parseable stage"
    )
    assert model.BASE_STAGE not in model.trusted_stages(case), (
        "an absent base was reported as a trusted stage"
    )


@given(case=CONFLICT_CASES)
def test_stages_two_and_three_always_exist(case: model.ConflictCase) -> None:
    """Every conflicted path always has stage 2 and stage 3 index entries."""
    existing = model.existing_stages(case)

    assert model.OURS_STAGE in existing, "stage 2 was missing from a conflict case"
    assert model.THEIRS_STAGE in existing, "stage 3 was missing from a conflict case"


@given(case=CONFLICT_CASES, theirs_parses=st.booleans())
def test_a_parsing_stage_three_never_rescues_a_non_parsing_stage_two(
    case: model.ConflictCase, theirs_parses: bool
) -> None:
    """Stage 2 is untrustworthy on its own merits, regardless of stage 3."""
    broken_case = dc.replace(case, ours_parses=False, theirs_parses=theirs_parses)

    assert model.OURS_STAGE not in model.trusted_stages(broken_case), (
        "a non-parsing stage 2 was trusted because stage 3 parsed"
    )
    assert model.resolution_may_continue(broken_case, True) is False, (
        "continuation was allowed despite a non-parsing stage 2"
    )


@given(case=CONFLICT_CASES)
def test_stage_two_trust_depends_on_prior_unverified_replays(
    case: model.ConflictCase,
) -> None:
    """Rebase stage 2 is untrusted while earlier replays are unverified."""
    trusted = model.trusted_stages(case)

    if case.operation is model.Operation.REBASE and case.prior_unverified_replays:
        assert model.OURS_STAGE not in trusted, (
            "stage 2 was trusted despite unverified prior rebase replays"
        )
    else:
        assert (model.OURS_STAGE in trusted) == case.ours_parses, (
            "stage 2 trust disagreed with whether it parses"
        )


@given(case=CONFLICT_CASES)
def test_resolution_never_continues_on_a_non_parsing_resolved_file(
    case: model.ConflictCase,
) -> None:
    """A resolved file that fails to parse can never be continued."""
    assert model.resolution_may_continue(case, False) is False, (
        "continuation was allowed for a non-parsing resolved file"
    )


def test_merge_with_prior_unverified_replays_is_rejected() -> None:
    """A merge cannot carry a nonzero prior-unverified-replay count."""
    with pytest.raises(ValueError, match="prior replays"):
        model.ConflictCase(
            operation=model.Operation.MERGE,
            base_present=True,
            base_parses=True,
            ours_parses=True,
            theirs_parses=True,
            prior_unverified_replays=1,
        )


# --- Multi-commit replay properties -------------------------------------------


@given(sequence=REPLAY_SEQUENCES, per_replay_guard=st.booleans())
def test_ours_input_safe_tracks_the_previous_states_safety(
    sequence: list[model.ReplayOutcome], per_replay_guard: bool
) -> None:
    """Each state's `ours` input safety mirrors the prior state's verdict."""
    states = model.fold_replays(sequence, per_replay_guard=per_replay_guard)

    assert states[0].ours_input_safe is True, (
        "the first replay's ours input was not treated as safe by definition"
    )
    for previous, current in zip(states, states[1:]):
        assert current.ours_input_safe == previous.safe, (
            "a later state's ours-input safety diverged from the prior verdict"
        )


@given(sequence=REPLAY_SEQUENCES, per_replay_guard=st.booleans())
def test_unsafe_states_never_flip_back_to_safe(
    sequence: list[model.ReplayOutcome], per_replay_guard: bool
) -> None:
    """Once a state is unsafe, every subsequent folded state stays unsafe."""
    states = model.fold_replays(sequence, per_replay_guard=per_replay_guard)

    first_unsafe = next(
        (index for index, state in enumerate(states) if not state.safe), None
    )
    if first_unsafe is None:
        return

    for state in states[first_unsafe + 1 :]:
        assert state.ours_input_safe is False, (
            "an invalid earlier output was accepted as a safe later ours input"
        )
        assert state.safe is False, (
            "a state following an unsafe state was itself marked safe"
        )


@given(sequence=CLEAN_REPLAY_SEQUENCES)
def test_a_structurally_invalid_first_clean_replay_taints_the_rest(
    sequence: list[model.ReplayOutcome],
) -> None:
    """A structurally invalid but clean-exit first replay is never rescued."""
    tainted = [dc.replace(sequence[0], structurally_valid=False), *sequence[1:]]

    without_guard = model.fold_replays(tainted, per_replay_guard=False)
    assert len(without_guard) == len(tainted), (
        "without the guard, Git-accepted clean replays were still dropped"
    )
    assert all(state.git_accepted for state in without_guard), (
        "a clean-exit replay was not recorded as accepted by Git"
    )
    assert not any(state.safe for state in without_guard), (
        "a sequence tainted by an invalid first replay was reported as safe"
    )
    assert model.sequence_is_safe(without_guard) is False, (
        "sequence_is_safe accepted a sequence tainted by an invalid first replay"
    )

    with_guard = model.fold_replays(tainted, per_replay_guard=True)
    assert len(with_guard) == 1, (
        "the per-replay guard failed to stop at the first unsafe replay"
    )


@given(sequence=REPLAY_SEQUENCES, per_replay_guard=st.booleans())
def test_git_acceptance_is_exit_code_only(
    sequence: list[model.ReplayOutcome], per_replay_guard: bool
) -> None:
    """Git's acceptance of a replay depends only on the driver's exit code."""
    states = model.fold_replays(sequence, per_replay_guard=per_replay_guard)

    for state in states:
        expected_accepted = state.outcome.exit_code is model.DriverExit.CLEAN
        assert state.git_accepted == expected_accepted, (
            "git_accepted disagreed with the driver's exit code"
        )


@given(sequence=REPLAY_SEQUENCES, per_replay_guard=st.booleans())
def test_the_fold_stops_after_a_replay_git_did_not_accept(
    sequence: list[model.ReplayOutcome], per_replay_guard: bool
) -> None:
    """No replay follows one that Git left unmerged or failed."""
    states = model.fold_replays(sequence, per_replay_guard=per_replay_guard)

    for previous, _current in zip(states, states[1:]):
        assert previous.git_accepted, (
            "a state followed a replay that Git did not accept"
        )


@given(sequence=REPLAY_SEQUENCES, per_replay_guard=st.booleans())
def test_safe_prefix_length_matches_the_first_unsafe_outcome(
    sequence: list[model.ReplayOutcome], per_replay_guard: bool
) -> None:
    """The safe prefix ends at the first outcome that is not clean and valid."""
    states = model.fold_replays(sequence, per_replay_guard=per_replay_guard)

    expected = next(
        (
            index
            for index, outcome in enumerate(sequence)
            if not (
                outcome.exit_code is model.DriverExit.CLEAN
                and outcome.structurally_valid
            )
        ),
        len(sequence),
    )

    assert model.safe_prefix_length(states) == expected, (
        "safe_prefix_length disagreed with the first non-clean-and-valid outcome"
    )


@given(
    valid_outcomes=st.lists(
        st.builds(
            model.ReplayOutcome,
            exit_code=st.just(model.DriverExit.CLEAN),
            structurally_valid=st.just(True),
        ),
        min_size=1,
        max_size=7,
    ),
    position=st.data(),
)
def test_reordering_the_invalid_outcome_moves_the_safe_prefix_boundary(
    valid_outcomes: list[model.ReplayOutcome], position: st.DataObject
) -> None:
    """Moving the one invalid outcome changes where the safe prefix ends."""
    invalid = model.ReplayOutcome(
        exit_code=model.DriverExit.CLEAN, structurally_valid=False
    )
    length = len(valid_outcomes) + 1
    p = position.draw(st.integers(min_value=0, max_value=length - 1))
    # Construct a distinct position rather than filtering draws.
    offset = position.draw(st.integers(min_value=1, max_value=length - 1))
    q = (p + offset) % length

    sequence_p = [*valid_outcomes[:p], invalid, *valid_outcomes[p:]]
    sequence_q = [*valid_outcomes[:q], invalid, *valid_outcomes[q:]]

    states_p = model.fold_replays(sequence_p, per_replay_guard=False)
    states_q = model.fold_replays(sequence_q, per_replay_guard=False)

    assert model.safe_prefix_length(states_p) == p, (
        "safe_prefix_length disagreed with the inserted invalid outcome's position"
    )
    assert model.safe_prefix_length(states_q) == q, (
        "moving the invalid outcome to a new position did not move the boundary"
    )


@given(
    sequence=st.lists(
        st.builds(
            model.ReplayOutcome,
            exit_code=st.just(model.DriverExit.CLEAN),
            structurally_valid=st.just(True),
        ),
        min_size=2,
        max_size=8,
    ),
    per_replay_guard=st.booleans(),
)
def test_all_valid_clean_sequences_are_fully_safe(
    sequence: list[model.ReplayOutcome], per_replay_guard: bool
) -> None:
    """A sequence of clean, structurally valid replays is safe end to end."""
    states = model.fold_replays(sequence, per_replay_guard=per_replay_guard)

    assert model.sequence_is_safe(states) is True, (
        "an all-valid clean sequence was not reported as fully safe"
    )
    assert model.safe_prefix_length(states) == len(sequence), (
        "an all-valid clean sequence did not have a full-length safe prefix"
    )
