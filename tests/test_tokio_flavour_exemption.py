"""Gate-backed regression cases for the Tokio attribute spelling exemption.

The Rust API keeps an American-spelled key on complete Tokio runtime
attributes. The shared policy must cover those attributes while leaving
ordinary identifiers, assignments, prose, and malformed attributes visible.
The authored cases live in JSON so their deliberate spellings stay out of
this module's own spelling scan.

Run the focused examples and generated boundary properties from the repository
root with either command::

    make test \
        TEST_TARGETS='tests/test_tokio_flavour_exemption.py tests/test_tokio_flavour_boundaries.py'
    uv run --group dev python -m pytest \
        tests/test_tokio_flavour_exemption.py \
        tests/test_tokio_flavour_boundaries.py -v

The gate-backed cases require ``uv`` and ``git`` on ``PATH``.
"""

import hashlib
import json
import re
import subprocess
import tomllib
from pathlib import Path
from typing import TypedDict

import pytest

from spelling_policy_support import (
    REPOSITORY_ROOT,
    SHARED_DICTIONARY_PATH,
    require_executable,
)
from test_opentofu_example_exemption import run_consumer_gate

BUILDER_VERSION = "v0.1.3"
FIXTURE_PATH = REPOSITORY_ROOT / "tests" / "fixtures" / "tokio_spelling_cases.json"


class SpellingCase(TypedDict):
    """One file and expected gate diagnostic from the recorded corpus."""

    id: str
    path: str
    content: str
    diagnostic: list[str]


class ConsumerProvenance(TypedDict):
    """Immutable source information for the known consumer snapshot."""

    repository: str
    branch: str
    revision: str
    snapshot_path: str
    overlay_sha256: str
    source_files: list[str]


class RecordedConsumerLane(TypedDict):
    """The inherited consumer overlay and its positive-only cases."""

    provenance: ConsumerProvenance
    scope_note: str
    overlay: str
    cases: list[SpellingCase]


class SpellingCorpus(TypedDict):
    """The shared-policy controls and recorded-consumer examples."""

    runtime_key: str  # The external Tokio API defines this spelling.
    schema_version: int
    official_sources: list[str]
    shared_positive: list[SpellingCase]
    shared_negative: list[SpellingCase]
    recorded_consumer_positive: RecordedConsumerLane


def load_corpus() -> SpellingCorpus:
    """Load authored cases and the immutable consumer-overlay snapshot.

    Returns
    -------
    SpellingCorpus
        The shared-policy cases, source provenance, and recorded overlay.

    Raises
    ------
    OSError
        If the fixture cannot be read.
    UnicodeDecodeError
        If the fixture is not valid UTF-8.
    json.JSONDecodeError
        If the fixture is not valid JSON.
    """
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


CORPUS = load_corpus()
API_KEY = CORPUS["runtime_key"]


def shared_patterns_for_api_key() -> list[str]:
    """Read shared ignore expressions that name the external Tokio key.

    Returns
    -------
    list[str]
        Matching expressions in the order used by the shared dictionary.

    Raises
    ------
    OSError
        If the shared dictionary cannot be read.
    UnicodeDecodeError
        If the shared dictionary is not valid UTF-8.
    tomllib.TOMLDecodeError
        If the shared dictionary is not valid TOML.
    """
    document = tomllib.loads(SHARED_DICTIONARY_PATH.read_text(encoding="utf-8"))
    patterns = document.get("patterns", {}).get("ignore", [])
    return [pattern for pattern in patterns if API_KEY in pattern]


def assert_pinned_gate_tools() -> None:
    """Require gate executables and the repository's pinned builder release.

    Returns
    -------
    None
        The function returns only after both executables and the pin are valid.

    Raises
    ------
    AssertionError
        If ``uv`` or ``git`` is unavailable, or the builder pin is absent or
        differs from the release used by these cases.
    OSError
        If the repository Makefile cannot be read.
    UnicodeDecodeError
        If the repository Makefile is not valid UTF-8.
    """
    require_executable("uv")
    require_executable("git")
    makefile = (REPOSITORY_ROOT / "Makefile").read_text(encoding="utf-8")
    version = re.search(
        r"^TYPOS_CONFIG_BUILDER_VERSION\s*\?=\s*(\S+)$",
        makefile,
        re.MULTILINE,
    )
    assert version is not None, "the builder version is not pinned"
    assert version.group(1) == BUILDER_VERSION, (
        f"expected the consumer gate to use {BUILDER_VERSION}, "
        f"found {version.group(1)}"
    )


def run_case_gate(
    repository: Path,
    case: SpellingCase,
    overlay: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run one corpus case through the pinned gate and shared dictionary.

    Parameters
    ----------
    repository
        Scratch repository directory that receives the case files.
    case
        Authored path, content, and expected diagnostics for one case.
    overlay
        Optional local overlay staged beside the case files.

    Returns
    -------
    subprocess.CompletedProcess[str]
        The gate's exit status and captured output streams.

    Raises
    ------
    AssertionError
        If a required executable or the pinned builder version is unavailable.
    OSError
        If a file or subprocess cannot be accessed.
    UnicodeDecodeError
        If the repository Makefile is not valid UTF-8.
    subprocess.CalledProcessError
        If initializing or staging the scratch repository fails.
    subprocess.TimeoutExpired
        If the pinned gate does not finish within its timeout.
    """
    assert_pinned_gate_tools()
    files = {case["path"]: case["content"]}
    if overlay is not None:
        files["typos.local.toml"] = overlay
    return run_consumer_gate(repository, files)


def gate_output(result: subprocess.CompletedProcess[str]) -> str:
    """Combine captured streams for useful gate assertion messages.

    Parameters
    ----------
    result
        Completed gate process whose output streams were captured as text.

    Returns
    -------
    str
        Standard output followed by standard error.
    """
    return result.stdout + result.stderr


def assert_diagnostics_present(case: SpellingCase, output: str) -> None:
    """Require each expected Typos correction header, ignoring case.

    Parameters
    ----------
    case
        Corpus record naming the expected diagnostic words.
    output
        Combined gate output to inspect for correction headers.

    Returns
    -------
    None
        The function returns only when every expected header is present.

    Raises
    ------
    AssertionError
        If any expected word lacks a Typos correction header.
    """
    headers = re.findall(r"(?im)^error: `([^`]+)` should be `[^`]+`$", output)
    reported_words = {word.casefold() for word in headers}
    for diagnostic in case["diagnostic"]:
        assert diagnostic.casefold() in reported_words, (
            f"{case['id']} did not report {diagnostic!r}:\n{output}"
        )


def test_shared_policy_has_two_scoped_attribute_patterns() -> None:
    """The shared source names one main/test and one main-local scope."""
    document = tomllib.loads(SHARED_DICTIONARY_PATH.read_text(encoding="utf-8"))
    patterns = shared_patterns_for_api_key()
    scope_markers = {
        "main_test": r"\#\[\s*tokio::(?:main|test)",
        "main_local": r"\#\[\s*tokio::main",
    }
    scoped_patterns = {
        scope: [pattern for pattern in patterns if marker in pattern]
        for scope, marker in scope_markers.items()
    }

    assert {
        scope: len(scope_patterns)
        for scope, scope_patterns in scoped_patterns.items()
    } == {"main_test": 1, "main_local": 1}
    named_patterns = [
        pattern
        for scope in scope_markers
        for pattern in scoped_patterns[scope]
    ]
    assert sorted(named_patterns) == sorted(patterns), (
        f"unscoped shared patterns: {patterns!r}"
    )
    main_test_pattern = scoped_patterns["main_test"][0]
    main_local_pattern = scoped_patterns["main_local"][0]

    for pattern in (main_test_pattern, main_local_pattern):
        assert pattern.lstrip().startswith("(?x)"), (
            "the expression is not verbose-mode"
        )
        assert API_KEY + r"\s*=" in pattern
        assert pattern.rstrip().endswith(r"\)\s*\]")
        re.compile(pattern)

    assert r"\#\[\s*tokio::(?:main|test)\s*\(" in main_test_pattern
    assert r"\#\[\s*tokio::main\s*\(" in main_local_pattern
    assert r"(?:current_thread|multi_thread)" in main_test_pattern
    assert r'(?:\\"local\\"|"local")' in main_local_pattern
    assert r"(?:\s*,\s*|\s*)\)\s*\]" in main_local_pattern
    assert all(
        argument not in main_local_pattern
        for argument in ("worker_threads", "start_paused", "unhandled_panic")
    )
    assert API_KEY not in document.get("words", {}).get("accepted", [])
    assert API_KEY not in document.get("words", {}).get("corrections", {})


def test_corpus_ids_are_unique_and_negative_cases_name_diagnostics() -> None:
    """Each report row stays readable and every shared negative is observable."""
    consumer_cases = CORPUS["recorded_consumer_positive"]["cases"]
    all_cases = [
        *CORPUS["shared_positive"],
        *CORPUS["shared_negative"],
        *consumer_cases,
    ]
    identifiers = [case["id"] for case in all_cases]
    negative_cases = CORPUS["shared_negative"]

    assert len(CORPUS["shared_positive"]) == 16
    assert len(negative_cases) == 15
    assert len(consumer_cases) == 3
    assert len(identifiers) == len(set(identifiers))
    assert all(case["path"] in {"src.rs", "guide.md"} for case in all_cases)
    assert all(case["diagnostic"] for case in negative_cases)
    assert all(not case["diagnostic"] for case in CORPUS["shared_positive"])
    assert all(not case["diagnostic"] for case in consumer_cases)


def test_diagnostic_oracle_ignores_setup_errors_with_expected_word_in_path() -> None:
    """A failure mentioning a case word is not itself a spelling diagnostic."""
    case = next(
        case for case in CORPUS["shared_negative"] if case["id"] == "function-name"
    )
    output = f"error: could not read {case['diagnostic'][0]}.toml"

    with pytest.raises(AssertionError, match="did not report"):
        assert_diagnostics_present(case, output)


@pytest.mark.slow
@pytest.mark.parametrize(
    "case",
    CORPUS["shared_positive"],
    ids=lambda case: case["id"],
)
def test_shared_positive_cases_pass_gate(tmp_path: Path, case: SpellingCase) -> None:
    """Every valid attribute or documentation example passes the shared gate."""
    result = run_case_gate(tmp_path, case)

    assert result.returncode == 0, f"{case['id']}:\n{gate_output(result)}"


@pytest.mark.slow
@pytest.mark.parametrize(
    "case",
    CORPUS["shared_negative"],
    ids=lambda case: case["id"],
)
def test_shared_negative_cases_fail_with_diagnostic(
    tmp_path: Path, case: SpellingCase
) -> None:
    """Invalid contexts and neighbouring typos remain visible to each consumer."""
    result = run_case_gate(tmp_path, case)
    output = gate_output(result)

    assert result.returncode == 2, f"{case['id']}:\n{output}"
    assert_diagnostics_present(case, output)


def test_recorded_consumer_overlay_matches_its_provenance() -> None:
    """The positive-only legacy lane retains its exact reviewed snapshot."""
    lane = CORPUS["recorded_consumer_positive"]
    provenance = lane["provenance"]
    overlay_digest = hashlib.sha256(lane["overlay"].encode("utf-8")).hexdigest()

    assert provenance["repository"] == "leynos/rstest-bdd"
    assert provenance["branch"] == "main"
    assert provenance["revision"] == "b6afd1e46a6dea4735b754fe7b64cc970dd27442"
    assert provenance["overlay_sha256"] == overlay_digest
    assert "Positive-only" in lane["scope_note"]


@pytest.mark.slow
@pytest.mark.parametrize(
    "case",
    CORPUS["recorded_consumer_positive"]["cases"],
    ids=lambda case: case["id"],
)
def test_recorded_consumer_cases_pass_with_recorded_overlay(
    tmp_path: Path, case: SpellingCase
) -> None:
    """Recorded consumer inputs pass when staged with their captured overlay."""
    overlay = CORPUS["recorded_consumer_positive"]["overlay"]
    result = run_case_gate(tmp_path, case, overlay)

    assert result.returncode == 0, f"{case['id']}:\n{gate_output(result)}"
