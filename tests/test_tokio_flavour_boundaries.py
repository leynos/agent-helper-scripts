"""Generated Python-regex boundary checks for Tokio runtime attributes.

The gate-backed corpus remains the authority for the pinned consumer engine;
these generated properties exercise Python's regular-expression engine only.
They check spelling boundaries, not Tokio macro semantic validity.
Run both focused modules from the repository root with either command::

    make test \
        TEST_TARGETS='tests/test_tokio_flavour_exemption.py tests/test_tokio_flavour_boundaries.py'
    uv run --group dev python -m pytest \
        tests/test_tokio_flavour_exemption.py \
        tests/test_tokio_flavour_boundaries.py -v

The gate-backed cases require ``uv`` and ``git`` on ``PATH``.
"""

import re

from hypothesis import given, settings
from hypothesis import strategies as st

from test_tokio_flavour_exemption import (
    API_KEY,
    CORPUS,
    SpellingCase,
    shared_patterns_for_api_key,
)

WHITESPACE = st.sampled_from(("", " ", "\n", "\t", " \n "))
QUOTES = st.sampled_from(('"', r'\"'))
ARGUMENT_NAMES = ("worker_threads", "start_paused", "unhandled_panic")


def _cases_by_id(case_id: str) -> SpellingCase:
    """Return one shared-positive corpus row by its stable identifier."""
    return next(case for case in CORPUS["shared_positive"] if case["id"] == case_id)


def _quoted_values(key: str, cases: list[SpellingCase]) -> tuple[str, ...]:
    """Read quoted values from authored examples without copying them here."""
    assignment = re.compile(
        rf"{re.escape(key)}\s*=\s*\\?\"([A-Za-z_]+)\\?\""
    )
    return tuple(
        match.group(1)
        for case in cases
        for match in assignment.finditer(case["content"])
    )


def _value_from_case(case_id: str, key: str) -> str:
    """Return the single quoted value for a key in one corpus row."""
    (value,) = _quoted_values(key, [_cases_by_id(case_id)])
    return value


COMMON_VALUES = tuple(
    _value_from_case(case_id, API_KEY)
    for case_id in ("main-current-thread", "main-multi-thread-official")
)
LOCAL_VALUE = _value_from_case("main-local-source", API_KEY)
UNHANDLED_VALUES = tuple(
    dict.fromkeys(
        _quoted_values(
            "unhandled_panic",
            CORPUS["shared_positive"],
        )
    )
)
NEIGHBOUR_WORD = next(
    word
    for case in CORPUS["shared_negative"]
    if case["id"] == "misspelling-before-complete-attribute"
    for word in case["diagnostic"]
)


def _patterns_for_scopes() -> tuple[str, str]:
    """Return the main/test pattern and the separate main-only pattern."""
    patterns = shared_patterns_for_api_key()
    main_test = next(
        pattern
        for pattern in patterns
        if r"\#\[\s*tokio::(?:main|test)" in pattern
    )
    main_local = next(
        pattern
        for pattern in patterns
        if r"\#\[\s*tokio::main" in pattern
        and r"(?:main|test)" not in pattern
    )
    return main_test, main_local


MAIN_TEST_PATTERN, MAIN_LOCAL_PATTERN = _patterns_for_scopes()


def _argument_value_strategy(name: str) -> st.SearchStrategy[str]:
    """Return lexical values from the observed optional-argument vocabulary."""
    if name == "worker_threads":
        return st.integers(min_value=1, max_value=1_000_000).map(str)
    if name == "start_paused":
        return st.booleans().map(lambda value: str(value).lower())
    return st.sampled_from(UNHANDLED_VALUES)


@st.composite
def _rendered_argument(draw: st.DrawFn, name: str, quote: str) -> str:
    """Render one allowed optional argument with generated spacing."""
    value = draw(_argument_value_strategy(name))
    whitespace = draw(WHITESPACE)
    if name == "unhandled_panic":
        value = f"{quote}{value}{quote}"
    return f"{name}{whitespace}={whitespace}{value}"


@st.composite
def _common_attribute(draw: st.DrawFn) -> str:
    """Generate a policy form with up to three options on either side."""
    path = draw(st.sampled_from(("main", "test")))
    value = draw(st.sampled_from(COMMON_VALUES))
    quote = draw(QUOTES)
    before_order = draw(st.permutations(ARGUMENT_NAMES))
    after_order = draw(st.permutations(ARGUMENT_NAMES))
    before_count = draw(st.integers(min_value=0, max_value=3))
    after_count = draw(st.integers(min_value=0, max_value=3))
    before = [
        draw(_rendered_argument(name, quote))
        for name in before_order[:before_count]
    ]
    after = [
        draw(_rendered_argument(name, quote))
        for name in after_order[:after_count]
    ]
    runtime_spacing = draw(WHITESPACE)
    runtime_argument = (
        f"{API_KEY}{runtime_spacing}={runtime_spacing}{quote}{value}{quote}"
    )
    comma = draw(st.sampled_from((",", ", ", ",\n  ", " , ")))
    trailing_comma = "," if draw(st.booleans()) else ""
    opening_spacing = draw(WHITESPACE)
    closing_spacing = draw(WHITESPACE)
    path_spacing = draw(WHITESPACE)
    content = comma.join((*before, runtime_argument, *after))
    return (
        f"#[{opening_spacing}tokio::{path}{path_spacing}({opening_spacing}"
        f"{content}{trailing_comma}{closing_spacing}){closing_spacing}]"
    )


@st.composite
def _local_attribute(draw: st.DrawFn) -> str:
    """Generate a standalone main form for the local policy scope."""
    quote = draw(QUOTES)
    spacing = draw(WHITESPACE)
    comma = "," if draw(st.booleans()) else ""
    return (
        f"#[{spacing}tokio::main{spacing}({spacing}{API_KEY}{spacing}="
        f"{spacing}{quote}{LOCAL_VALUE}{quote}{comma}{spacing}){spacing}]"
    )


def _assert_exact_match(pattern: str, attribute: str) -> None:
    """Require the expression to stop at the full attribute boundaries."""
    before = f"{NEIGHBOUR_WORD} = true\n"
    after = f"\n{NEIGHBOUR_WORD} = true"
    for text, start in ((before + attribute, len(before)), (attribute + after, 0)):
        match = re.search(pattern, text)
        assert match is not None, f"{pattern!r} did not match {attribute!r}"
        assert match.span() == (start, start + len(attribute)), (
            f"{pattern!r} matched {match.group(0)!r} across adjacent text"
        )


def _without_closing_parenthesis(attribute: str) -> str:
    """Remove the final attribute delimiter without changing its neighbours."""
    prefix, delimiter, suffix = attribute.rpartition(")")
    if not delimiter:
        raise ValueError("attribute has no closing parenthesis")
    return prefix + suffix


@st.composite
def _near_miss_attributes(draw: st.DrawFn) -> tuple[str, ...]:
    """Generate every key, value, path, and closure near miss together."""
    path = draw(st.sampled_from(("main", "test")))
    value = draw(st.sampled_from(COMMON_VALUES))
    quote = draw(QUOTES)
    spacing = draw(WHITESPACE)
    valid_attribute = (
        f"#[{spacing}tokio::{path}({spacing}{API_KEY}{spacing}={spacing}"
        f"{quote}{value}{quote}{spacing}){spacing}]"
    )
    key_near_miss = valid_attribute.replace(
        API_KEY,
        f"{API_KEY}_unsupported",
        1,
    )
    value_near_miss = valid_attribute.replace(
        f"{quote}{value}{quote}",
        f"{quote}{value}_unsupported{quote}",
        1,
    )
    path_near_miss = valid_attribute.replace(
        f"tokio::{path}",
        f"tokio::{path}_unsupported",
        1,
    )
    return (
        key_near_miss,
        value_near_miss,
        path_near_miss,
        valid_attribute[:-1],
        _without_closing_parenthesis(valid_attribute),
    )


@settings(max_examples=200, deadline=None)
@given(common_attribute=_common_attribute(), local_attribute=_local_attribute())
def test_generated_supported_attributes_match_exact_boundaries(
    common_attribute: str, local_attribute: str
) -> None:
    """Generated policy forms match fully and leave neighbouring text alone."""
    _assert_exact_match(MAIN_TEST_PATTERN, common_attribute)
    _assert_exact_match(MAIN_LOCAL_PATTERN, local_attribute)
    assert re.search(MAIN_TEST_PATTERN, local_attribute) is None, (
        "shared scope must exclude local attributes"
    )


@settings(max_examples=200, deadline=None)
@given(attributes=_near_miss_attributes())
def test_generated_near_misses_do_not_match_either_scope(
    attributes: tuple[str, ...],
) -> None:
    """Unsupported keys, values, paths, and incomplete attributes stay visible."""
    for attribute in attributes:
        assert re.search(MAIN_TEST_PATTERN, attribute) is None, attribute
        assert re.search(MAIN_LOCAL_PATTERN, attribute) is None, attribute


def test_spaced_attribute_without_closing_parenthesis_is_rejected() -> None:
    """The final parenthesis stays required when whitespace precedes the bracket."""
    value = COMMON_VALUES[0]
    complete = f'#[ tokio::main( {API_KEY} = "{value}" ) ]'
    incomplete = _without_closing_parenthesis(complete)
    expected_incomplete = f'#[ tokio::main( {API_KEY} = "{value}"  ]'

    assert incomplete == expected_incomplete, "delimiter spacing changed"
    assert re.search(MAIN_TEST_PATTERN, complete) is not None, (
        "complete form must match the shared scope"
    )
    assert re.search(MAIN_TEST_PATTERN, incomplete) is None, (
        "shared scope must reject a missing parenthesis"
    )
    assert re.search(MAIN_LOCAL_PATTERN, incomplete) is None, (
        "local scope must reject a missing parenthesis"
    )
