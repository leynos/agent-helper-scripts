"""Property tests for bounded spelling-policy repetition handling."""

import types

from hypothesis import given
from hypothesis import strategies as st
import pytest


def _exact_repetition(count: int) -> str:
    """Render an exact Python regular expression repetition."""
    return f"{{{count}}}"


def _lower_bounded_repetition(count: int) -> str:
    """Render a lower-bounded Python regular expression repetition."""
    return f"{{{count},}}"


def _bounded_repetition(bounds: tuple[int, int]) -> str:
    """Render an inclusive Python regular expression repetition range."""
    lower, width = bounds
    return f"{{{lower},{lower + width}}}"


def _upper_bounded_repetition(count: int) -> str:
    """Render Python's omitted-lower-bound repetition form."""
    return f"{{,{count}}}"


COUNTS = st.integers(min_value=0, max_value=20)
REPETITIONS = st.one_of(
    COUNTS.map(_exact_repetition),
    COUNTS.map(_lower_bounded_repetition),
    st.tuples(COUNTS, COUNTS).map(_bounded_repetition),
    COUNTS.map(_upper_bounded_repetition),
)
PATTERN_NAMES = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
    min_size=1,
    max_size=12,
)
VALID_PATTERN_MEMBERSHIPS = st.dictionaries(
    PATTERN_NAMES,
    st.sampled_from(
        (
            (True, False, False),
            (False, True, False),
            (False, False, True),
            (True, True, False),
            (True, False, True),
        )
    ),
    max_size=12,
)
PATTERN_LISTS = st.lists(PATTERN_NAMES, unique=True, max_size=12).map(tuple)
NON_EMPTY_PATTERN_LISTS = st.lists(
    PATTERN_NAMES,
    unique=True,
    min_size=1,
    max_size=12,
).map(tuple)


@given(repetition=REPETITIONS)
def test_generated_repetition_forms_are_rejected_when_nested(
    rollout: types.ModuleType,
    repetition: str,
) -> None:
    """Every Python repetition spelling is unsafe when an outer repeat compounds it."""
    pattern = f"(a{repetition})+"

    try:
        rollout._compile_ignore_patterns((pattern,))
    except ValueError as error:
        assert "unsafe repetition" in str(error), (
            "nested generated repetition produced the wrong policy failure"
        )
    else:
        raise AssertionError(f"nested generated repetition was accepted: {pattern}")


@given(
    first=REPETITIONS,
    separator=st.text(alphabet="bc", min_size=1, max_size=8),
    second=REPETITIONS,
)
def test_separated_generated_repetitions_remain_safe(
    rollout: types.ModuleType,
    first: str,
    separator: str,
    second: str,
) -> None:
    """Distinct quantified atoms separated by plain text retain bounded matching."""
    pattern = f"a{first}{separator}d{second}"

    compiled = rollout._compile_ignore_patterns((pattern,))

    assert compiled[0].pattern == pattern, "safe separated repetition changed"


@given(memberships=VALID_PATTERN_MEMBERSHIPS)
def test_ignore_pattern_merge_obeys_set_difference_for_every_valid_membership(
    rollout: types.ModuleType,
    memberships: dict[str, tuple[bool, bool, bool]],
) -> None:
    """Every valid finite membership map follows the set-theoretic contract."""
    base_patterns = tuple(
        pattern for pattern, membership in memberships.items() if membership[0]
    )
    local_patterns = tuple(
        pattern for pattern, membership in memberships.items() if membership[1]
    )
    removed_patterns = tuple(
        pattern for pattern, membership in memberships.items() if membership[2]
    )
    expected = tuple(
        sorted((set(base_patterns) | set(local_patterns)) - set(removed_patterns))
    )

    merged = rollout._merge_ignore_patterns(
        rollout.Dictionary(ignore_patterns=base_patterns),
        rollout.Dictionary(
            ignore_patterns=local_patterns,
            removed_patterns=removed_patterns,
        ),
    )
    reordered = rollout._merge_ignore_patterns(
        rollout.Dictionary(ignore_patterns=tuple(reversed(base_patterns))),
        rollout.Dictionary(
            ignore_patterns=tuple(reversed(local_patterns)),
            removed_patterns=tuple(reversed(removed_patterns)),
        ),
    )

    assert merged == expected
    assert reordered == expected, "input ordering changed the merged policy"


@given(base=PATTERN_LISTS, local=PATTERN_LISTS, absent=PATTERN_LISTS)
def test_absent_removals_are_always_no_ops(
    rollout: types.ModuleType,
    base: tuple[str, ...],
    local: tuple[str, ...],
    absent: tuple[str, ...],
) -> None:
    """Removing arbitrary patterns outside both inputs cannot change their union."""
    base_patterns = tuple(f"base:{pattern}" for pattern in base)
    local_patterns = tuple(f"local:{pattern}" for pattern in local)
    absent_patterns = tuple(f"absent:{pattern}" for pattern in absent)

    merged = rollout._merge_ignore_patterns(
        rollout.Dictionary(ignore_patterns=base_patterns),
        rollout.Dictionary(
            ignore_patterns=local_patterns,
            removed_patterns=absent_patterns,
        ),
    )

    assert merged == tuple(sorted(set(base_patterns) | set(local_patterns)))


@given(
    overlap=NON_EMPTY_PATTERN_LISTS,
    base=PATTERN_LISTS,
    local=PATTERN_LISTS,
    removed=PATTERN_LISTS,
)
def test_every_local_add_remove_overlap_is_rejected(
    rollout: types.ModuleType,
    overlap: tuple[str, ...],
    base: tuple[str, ...],
    local: tuple[str, ...],
    removed: tuple[str, ...],
) -> None:
    """Every non-empty exact overlap fails regardless of other inputs or order."""
    local_patterns = (*local, *overlap)
    removed_patterns = (*reversed(removed), *reversed(overlap))

    with pytest.raises(ValueError, match="both ignores and removes patterns"):
        rollout._merge_ignore_patterns(
            rollout.Dictionary(ignore_patterns=tuple(reversed(base))),
            rollout.Dictionary(
                ignore_patterns=local_patterns,
                removed_patterns=removed_patterns,
            ),
        )
