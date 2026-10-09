"""Exercise the documented local CodeRabbit CLI cooldown helper."""

from __future__ import annotations

import re
import string
import subprocess
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from hypothesis import example, given, strategies as st


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MILESTONE_REVIEW = (
    REPOSITORY_ROOT
    / "skills"
    / "sdlc-implementation"
    / "references"
    / "milestone-review.md"
)
BASH = Path("/bin/bash")
INJECTION_MARKER = "cooldown-input-was-executed"


@dataclass(frozen=True)
class HelperRun:
    """Capture process output and calls made to the isolated command stubs."""

    completed: subprocess.CompletedProcess[str]
    shuf_args: tuple[str, ...] | None
    vsleep_args: tuple[str, ...] | None
    injection_marker_created: bool


def _documented_function() -> str:
    """Return the original function body from its Markdown Bash fence."""
    document = MILESTONE_REVIEW.read_text(encoding="utf-8")
    match = re.search(
        r"(?ms)^```bash\n(?P<body>wait_for_coderabbit_cli\(\) \(\n.*?^\))\n```",
        document,
    )
    assert match is not None, (
        "milestone-review.md must contain the wait_for_coderabbit_cli Bash fence"
    )
    return match.group("body")


def _read_call_log(path: Path) -> tuple[str, ...] | None:
    """Return logged argv lines, or None when the stub was not invoked."""
    if not path.exists():
        return None
    return tuple(path.read_text(encoding="utf-8").splitlines())


def _write_stub(path: Path, source: str) -> None:
    """Install an executable stub in the isolated command directory."""
    path.write_text(source, encoding="utf-8")
    path.chmod(0o755)


def _run_documented_function(
    tmp_path_factory: pytest.TempPathFactory,
    function_source: str,
    requested: str | None,
    *,
    choose_upper: bool = False,
    shuf_exit: int = 0,
    vsleep_exit: int = 0,
    install_shuf: bool = True,
    install_vsleep: bool = True,
) -> HelperRun:
    """Run the extracted function with PATH limited to temporary command stubs."""
    with TemporaryDirectory(
        prefix="sdlc-cooldown-", dir=tmp_path_factory.getbasetemp()
    ) as temporary_directory:
        workdir = Path(temporary_directory)
        bin_directory = workdir / "bin"
        bin_directory.mkdir()
        shuf_log = workdir / "shuf-arguments.txt"
        vsleep_log = workdir / "vsleep-arguments.txt"

        if install_shuf:
            _write_stub(
                bin_directory / "shuf",
                """#!/bin/bash
printf '%s\\n' "$@" > "$SHUF_LOG"
if (( SHUF_EXIT != 0 )); then
    exit "$SHUF_EXIT"
fi
IFS=- read -r lower upper <<< "$2"
if [[ "$CHOOSE_UPPER" == 1 ]]; then
    printf '%s\\n' "$upper"
else
    printf '%s\\n' "$lower"
fi
""",
            )
        if install_vsleep:
            _write_stub(
                bin_directory / "vsleep",
                """#!/bin/bash
printf '%s\\n' "$@" > "$VSLEEP_LOG"
exit "$VSLEEP_EXIT"
""",
            )

        command = f"{function_source}\nwait_for_coderabbit_cli"
        arguments = [str(BASH), "-c", command, "cooldown-test"]
        if requested is not None:
            command += ' "$1"'
            arguments[2] = command
            arguments.append(requested)

        completed = subprocess.run(
            arguments,
            cwd=workdir,
            env={
                "PATH": str(bin_directory),
                "SHUF_LOG": str(shuf_log),
                "VSLEEP_LOG": str(vsleep_log),
                "CHOOSE_UPPER": "1" if choose_upper else "0",
                "SHUF_EXIT": str(shuf_exit),
                "VSLEEP_EXIT": str(vsleep_exit),
            },
            capture_output=True,
            check=False,
            text=True,
            timeout=30,
        )
        return HelperRun(
            completed=completed,
            shuf_args=_read_call_log(shuf_log),
            vsleep_args=_read_call_log(vsleep_log),
            injection_marker_created=(workdir / INJECTION_MARKER).exists(),
        )


def _assert_cooldown_invariant(
    result: HelperRun, requested: int, choose_upper: bool
) -> None:
    """Check the documented bounds against observed stub calls and output."""
    expected_lower = requested + 10
    expected_upper = 90 if expected_lower <= 90 else expected_lower + 10

    assert result.completed.returncode == 0, (
        f"helper exited {result.completed.returncode}: {result.completed.stderr}"
    )
    assert result.shuf_args == (
        "-i",
        f"{expected_lower}-{expected_upper}",
        "-n",
        "1",
    ), "the helper must pass the documented inclusive range to shuf"
    sampled = re.search(
        r"CodeRabbit CLI cooldown: ([0-9]+) minutes\.", result.completed.stdout
    )
    assert sampled is not None, "the helper must report its sampled cooldown"
    sampled_minutes = int(sampled.group(1))
    assert expected_lower <= sampled_minutes <= expected_upper, (
        "the reported sample must stay inside the documented inclusive range"
    )
    expected_sample = expected_upper if choose_upper else expected_lower
    assert sampled_minutes == expected_sample, (
        "the stub must return the generated lower or upper range boundary"
    )
    assert result.vsleep_args == (f"{sampled_minutes}m",), (
        "vsleep must receive exactly the sampled whole-minute duration"
    )
    assert not result.injection_marker_created, (
        "cooldown input must remain an argument rather than shell source"
    )


@pytest.fixture(scope="module")
def cooldown_function() -> str:
    """Load the Bash helper directly from its documented fenced block."""
    return _documented_function()


@example(requested=0, choose_upper=False)
@example(requested=0, choose_upper=True)
@example(requested=80, choose_upper=False)
@example(requested=80, choose_upper=True)
@example(requested=81, choose_upper=False)
@example(requested=81, choose_upper=True)
@example(requested=999_999_999, choose_upper=False)
@example(requested=999_999_999, choose_upper=True)
@given(
    requested=st.integers(min_value=0, max_value=999_999_999),
    choose_upper=st.booleans(),
)
def test_documented_cooldown_range_and_sleep_match_the_requested_wait(
    cooldown_function: str,
    tmp_path_factory: pytest.TempPathFactory,
    requested: int,
    choose_upper: bool,
) -> None:
    """Keep range and sleep values aligned across valid requested waits."""
    outcome = _run_documented_function(
        tmp_path_factory,
        cooldown_function,
        str(requested),
        choose_upper=choose_upper,
    )

    _assert_cooldown_invariant(outcome, requested, choose_upper)


@example(bad_input="-1")
@example(bad_input="+1")
@example(bad_input="1.5")
@example(bad_input=" 1")
@example(bad_input="1 ")
@example(bad_input="01")
@example(bad_input="00")
@example(bad_input="1000000000")
@example(bad_input="999999999999999999999999999999")
@example(bad_input="retry")
@example(bad_input="0; touch cooldown-input-was-executed")
@given(
    bad_input=st.one_of(
        st.sampled_from(("-1", "+1")),
        st.sampled_from(("1.5", " 1", "1 ")),
        st.integers(min_value=0, max_value=999_999_999).map(
            lambda value: f"0{value}"
        ),
        st.integers(min_value=1_000_000_000, max_value=10**24).map(str),
        st.text(alphabet=string.ascii_letters, min_size=1, max_size=12),
        st.sampled_from(("0; touch cooldown-input-was-executed",)),
    )
)
def test_malformed_cooldown_inputs_fail_before_invoking_tools(
    cooldown_function: str,
    tmp_path_factory: pytest.TempPathFactory,
    bad_input: str,
) -> None:
    """Reject malformed or shell-like input before invoking cooldown tools."""
    outcome = _run_documented_function(
        tmp_path_factory, cooldown_function, bad_input
    )

    assert outcome.completed.returncode == 2, (
        f"malformed input {bad_input!r} should exit 2, got "
        f"{outcome.completed.returncode}: {outcome.completed.stderr}"
    )
    assert "Invalid cooldown" in outcome.completed.stderr, (
        f"malformed input {bad_input!r} should produce the cooldown diagnostic"
    )
    assert outcome.shuf_args is None, (
        f"shuf must not run for malformed input {bad_input!r}"
    )
    assert outcome.vsleep_args is None, (
        f"vsleep must not run for malformed input {bad_input!r}"
    )
    assert not outcome.injection_marker_created, (
        f"input {bad_input!r} must not be evaluated as shell source"
    )


@pytest.mark.parametrize("requested", (None, ""), ids=("omitted", "empty"))
def test_missing_cooldown_input_uses_the_required_argument_failure(
    cooldown_function: str,
    tmp_path_factory: pytest.TempPathFactory,
    requested: str | None,
) -> None:
    """Require a minute count before checking or invoking cooldown tools."""
    outcome = _run_documented_function(
        tmp_path_factory, cooldown_function, requested
    )

    assert outcome.completed.returncode != 0, (
        f"{requested!r} input should fail the required-argument check"
    )
    assert "Supply the documented remaining wait in minutes" in (
        outcome.completed.stderr
    ), "missing input should report the required minute count"
    assert outcome.shuf_args is None, "shuf must not run without a minute count"
    assert outcome.vsleep_args is None, "vsleep must not run without a minute count"


def test_missing_shuf_fails_without_falling_back_to_a_real_command(
    cooldown_function: str, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """Fail when shuf is absent from the isolated PATH."""
    outcome = _run_documented_function(
        tmp_path_factory,
        cooldown_function,
        "0",
        install_shuf=False,
    )

    assert outcome.completed.returncode != 0, "missing shuf must fail the helper"
    assert outcome.shuf_args is None, "no shuf stub is installed"
    assert outcome.vsleep_args is None, "vsleep must not run without shuf"


def test_missing_vsleep_fails_before_shuf_is_invoked(
    cooldown_function: str, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """Check vsleep availability before sampling a cooldown."""
    outcome = _run_documented_function(
        tmp_path_factory,
        cooldown_function,
        "0",
        install_vsleep=False,
    )

    assert outcome.completed.returncode != 0, "missing vsleep must fail the helper"
    assert outcome.shuf_args is None, "shuf must not run without vsleep"
    assert outcome.vsleep_args is None, "the absent vsleep stub cannot be called"


def test_shuf_failure_propagates_without_sleeping(
    cooldown_function: str, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """Propagate shuf's status and skip vsleep when sampling fails."""
    outcome = _run_documented_function(
        tmp_path_factory,
        cooldown_function,
        "0",
        shuf_exit=33,
    )

    assert outcome.completed.returncode == 33, (
        f"helper must propagate shuf exit 33, got {outcome.completed.returncode}"
    )
    assert outcome.shuf_args == ("-i", "10-90", "-n", "1"), (
        "shuf must receive the range and sample-count arguments"
    )
    assert outcome.vsleep_args is None, "vsleep must not run after shuf fails"


@pytest.mark.parametrize("vsleep_exit", (42, 130), ids=("failure", "interrupted"))
def test_vsleep_failure_or_interruption_propagates(
    cooldown_function: str,
    tmp_path_factory: pytest.TempPathFactory,
    vsleep_exit: int,
) -> None:
    """Propagate vsleep failures, including an interrupted status of 130."""
    outcome = _run_documented_function(
        tmp_path_factory,
        cooldown_function,
        "0",
        vsleep_exit=vsleep_exit,
    )

    assert outcome.completed.returncode == vsleep_exit, (
        f"helper must propagate vsleep exit {vsleep_exit}, "
        f"got {outcome.completed.returncode}"
    )
    assert outcome.shuf_args == ("-i", "10-90", "-n", "1"), (
        "shuf must receive the range and sample-count arguments"
    )
    assert outcome.vsleep_args == ("10m",), (
        "vsleep must receive the sampled ten-minute duration"
    )


def test_cooldown_invariant_detects_a_lower_bound_mutation(
    cooldown_function: str, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """Show that the range invariant catches an altered lower-bound formula."""
    original = _run_documented_function(
        tmp_path_factory, cooldown_function, "0"
    )
    _assert_cooldown_invariant(original, requested=0, choose_upper=False)

    mutation = "q=$((requested_minutes + 10))"
    assert cooldown_function.count(mutation) == 1, (
        "the documented lower-bound expression must appear exactly once"
    )
    mutated_function = cooldown_function.replace(
        mutation, "q=$((requested_minutes + 9))", 1
    )
    mutated = _run_documented_function(
        tmp_path_factory, mutated_function, "0"
    )

    with pytest.raises(AssertionError, match="documented inclusive range"):
        _assert_cooldown_invariant(mutated, requested=0, choose_upper=False)
