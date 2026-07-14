"""Property tests for bounded spelling-policy repetition handling."""

import types

from hypothesis import given
from hypothesis import strategies as st


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
