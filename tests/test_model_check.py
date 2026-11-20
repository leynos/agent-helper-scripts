"""Contract tests for the fail-closed model-checking launcher.

The pinned FizzBee release exits zero when a property fails, drops liveness
checking when it does not recognize the ``liveness`` value, and stops at
``max_actions`` without saying so. ``scripts/model_check.py`` is what stands
between those behaviours and a green gate, so these tests pin its judgement
on the checker's real output text, and then drive the real command line
against a doubled checker that fails, hangs, crashes or is absent.

The output samples below were captured from the pinned v0.5.4 binary. The
last group of tests runs that binary itself; it is skipped where the release
is not installed, except under GitHub Actions, where its absence is a
failure because the workflow installs it before the gates run.
"""

from __future__ import annotations

from collections.abc import Iterator
import hashlib
import importlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tarfile
import textwrap
import types

import pytest

from spelling_policy_support import REPOSITORY_ROOT, SCRIPTS_PATH

CLI_PATH = REPOSITORY_ROOT / "scripts" / "model_check_cli.py"
SUITE_PATH = REPOSITORY_ROOT / "specs" / "pr-readiness" / "suite.toml"
CHECKER_HOME = Path(
    os.environ.get("MODEL_CHECK_HOME", Path.home() / ".cache" / "fizzbee")
)

OPTIONS_ECHO = (
    "StateSpaceOptions: options:{max_actions:1000  max_concurrent_actions:1"
    '  crash_on_yield:false}  liveness:"strict"  deadlock_detection:true'
)
PASSED = f"""Model checking spec.json
configFileName: fizz.yaml
{OPTIONS_ECHO}
Nodes: 95, queued: 0
Valid Nodes: 95 Unique states: 55
Checking eventually always Progress
IsLive: true
PASSED: Model checker completed successfully
"""
INVARIANT_FAILED = f"""{OPTIONS_ECHO}
Nodes: 5, queued: 4
FAILED: Model checker failed. Invariant:  Bounded
------
Init
"""
TRANSITION_FAILED = f"""{OPTIONS_ECHO}
Nodes: 10, queued: 2
FAILED: Model checker failed. Transition Invariant: Monotonic
"""
UNREACHED = f"""{OPTIONS_ECHO}
Nodes: 10, queued: 0
Valid Nodes: 10 Unique states: 10

FAILED: Expected states never reached
Invariant 0: Reaches
"""
LIVENESS_FAILED = f"""{OPTIONS_ECHO}
Nodes: 4, queued: 0
Valid Nodes: 4 Unique states: 4
Checking eventually always Progress
IsLive: false
FAILED: Liveness check failed
Invariant: Progress
------
Init
"""
DEADLOCKED = f"""{OPTIONS_ECHO}
Nodes: 10, queued: 0
DEADLOCK detected
FAILED: Model checker failed
------
Init
"""
REPLAYED = """Model checking spec.json
Loaded trace with 3 links
Nodes: 0, queued: 0
Valid Nodes: 4 Unique states: 4
PASSED: Model checker completed successfully
"""
REFUSED = """Model checking spec.json
Loaded trace with 3 links
Nodes: 0, queued: 0
WARNING: Trace execution incomplete. Expected 3 links, executed 2 links.
The trace may contain links that don't match the model or are unreachable.
"""

SPEC = textwrap.dedent(
    """\
    action Init:
        n = 0

    atomic action Step:
        require n < 2
        n = n + 1

    always assertion Bounded:
        return n <= 2

    eventually always assertion Progress:
        return n == 2
    """
)


@pytest.fixture(name="mc", scope="module")
def model_check_module() -> Iterator[types.ModuleType]:
    """Load ``scripts/model_check.py`` through the runtime path."""
    directory = str(SCRIPTS_PATH)
    sys.path.insert(0, directory)
    try:
        yield importlib.import_module("model_check")
    finally:
        sys.path.remove(directory)


def digest(path: Path) -> str:
    """Return a file's SHA-256 digest."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_suite(directory: Path, body: str, *, checker: str = "") -> Path:
    """Write a suite manifest with stated defaults and return its path."""
    pin = checker or textwrap.dedent(
        """\
        [checker]
        version = "v-test"
        url = "file:///nowhere"
        sha256 = "0"
        root = "release"
        [checker.files]
        "fizz" = "0"
        """
    )
    manifest = directory / "suite.toml"
    manifest.write_text(
        pin
        + textwrap.dedent(
            """\
            [defaults]
            spec = "spec.fizz"
            timeout_seconds = 5
            [defaults.options]
            max_actions = 1000
            max_concurrent_actions = 1
            crash_on_yield = false
            deadlock_detection = true
            liveness = "strict"
            """
        )
        + textwrap.dedent(body),
        encoding="utf-8",
    )
    (directory / "spec.fizz").write_text(SPEC, encoding="utf-8")
    return manifest


ASSURANCE = """
[[run]]
id = "base"
class = "assurance"
purpose = "The unmodified specification passes."
expect = "pass"
"""

CONTROL = """
[[run]]
id = "control"
class = "negative-control"
of = "base"
purpose = "Widening the guard breaks the bound."
expect = { fail = "always", assertion = "Bounded" }
[[run.mutation]]
old = "require n < 2"
new = "require n < 3"
"""


def judged(mc: types.ModuleType, suite_text: str, run_id: str, tmp_path: Path, **result):
    """Judge one doubled checker result against a run of a written suite."""
    suite = mc.load_suite(write_suite(tmp_path, suite_text))
    run = next(run for run in suite.runs if run.id == run_id)
    spec = mc.mutate(SPEC, run.mutations, run.id)
    return mc.judge(run, mc.ProcessResult(**result), spec)


def test_a_pass_is_accepted_only_with_every_completion_fact(
    mc: types.ModuleType, tmp_path: Path
) -> None:
    """The positive control: a real pass line with counts, echo and liveness."""
    ok, status, detail, reading = judged(
        mc, ASSURANCE, "base", tmp_path, exit_code=0, stdout=PASSED, stderr=""
    )
    assert (ok, status, detail) == (True, "passed", "exhaustive")
    assert (reading.nodes, reading.unique_states) == (95, 55)


@pytest.mark.parametrize(
    ("output", "status"),
    [
        (INVARIANT_FAILED, "failed"),
        (TRANSITION_FAILED, "failed"),
        (UNREACHED, "failed"),
        (LIVENESS_FAILED, "failed"),
        (DEADLOCKED, "failed"),
        # The release exits zero for all of these; none may read as a pass.
        ("", "unrecognized"),
        (PASSED + INVARIANT_FAILED, "unrecognized"),
        (OPTIONS_ECHO + "\nFAILED: something new in a later release\n", "unrecognized"),
        (PASSED.replace("queued: 0", "queued: 7"), "inconclusive"),
        (PASSED.replace("Nodes: 95", "Nodes: 1000"), "inconclusive"),
        (PASSED.replace("Checking eventually always Progress\n", ""), "unchecked"),
        (PASSED.replace('liveness:"strict"', 'liveness:"eventual"'), "misconfigured"),
        (PASSED.replace("deadlock_detection:true", "deadlock_detection:false"), "misconfigured"),
        (PASSED.replace("max_actions:1000", "max_actions:100"), "misconfigured"),
        (PASSED.replace(OPTIONS_ECHO + "\n", ""), "misconfigured"),
    ],
)
def test_an_assurance_run_fails_closed(
    mc: types.ModuleType, tmp_path: Path, output: str, status: str
) -> None:
    """Zero exit status is not a pass: the output has to say so, completely.

    The rows cover each failure the release reports, output it has never
    produced, a search that stopped at its bound or left nodes queued, a
    temporal assertion the release did not report checking, and options it
    did not echo as requested.
    """
    ok, got, _, _ = judged(
        mc, ASSURANCE, "base", tmp_path, exit_code=0, stdout=output, stderr=""
    )
    assert (ok, got) == (False, status)


@pytest.mark.parametrize(
    ("result", "status"),
    [
        ({"exit_code": 1, "stdout": "Error: Compilation failed\n", "stderr": "line 3"}, "error"),
        ({"exit_code": 2, "stdout": "", "stderr": "panic: Line 15"}, "error"),
        ({"exit_code": None, "stdout": "", "stderr": "", "timed_out": True}, "inconclusive"),
        ({"exit_code": None, "stdout": INVARIANT_FAILED, "stderr": ""}, "interrupted"),
        ({"exit_code": 0, "stdout": PASSED, "stderr": ""}, "undetected"),
        ({"exit_code": 0, "stdout": TRANSITION_FAILED, "stderr": ""}, "wrong-failure"),
        ({"exit_code": 0, "stdout": INVARIANT_FAILED.replace("Bounded", "Other"), "stderr": ""}, "wrong-failure"),
        ({"exit_code": 0, "stdout": DEADLOCKED, "stderr": ""}, "wrong-failure"),
    ],
)
def test_a_control_is_not_satisfied_by_anything_but_its_named_failure(
    mc: types.ModuleType, tmp_path: Path, result: dict, status: str
) -> None:
    """A syntax error, crash, timeout or other assertion is not detection.

    A negative control exists to show that one named assertion catches one
    named defect. A checker that exited non-zero, was stopped, passed, or
    failed something else has shown nothing about that assertion.
    """
    ok, got, _, _ = judged(mc, ASSURANCE + CONTROL, "control", tmp_path, **result)
    assert (ok, got) == (False, status)


def test_a_control_is_satisfied_by_its_named_failure(
    mc: types.ModuleType, tmp_path: Path
) -> None:
    """The positive control for the table above."""
    ok, status, _, _ = judged(
        mc,
        ASSURANCE + CONTROL,
        "control",
        tmp_path,
        exit_code=0,
        stdout=INVARIANT_FAILED,
        stderr="",
    )
    assert (ok, status) == (True, "failed-as-expected")


@pytest.mark.parametrize(
    ("kind", "output"),
    [
        ('{ fail = "transition", assertion = "Monotonic" }', TRANSITION_FAILED),
        ('{ fail = "exists", assertion = "Reaches" }', UNREACHED),
        ('{ fail = "liveness", assertion = "Progress" }', LIVENESS_FAILED),
        ('{ fail = "deadlock" }', DEADLOCKED),
    ],
)
def test_each_failure_kind_is_recognized(
    mc: types.ModuleType, tmp_path: Path, kind: str, output: str
) -> None:
    """Every failure the release reports maps to the kind a suite names."""
    suite = ASSURANCE + CONTROL.replace(
        '{ fail = "always", assertion = "Bounded" }', kind
    )
    ok, status, detail, _ = judged(
        mc, suite, "control", tmp_path, exit_code=0, stdout=output, stderr=""
    )
    assert (ok, status) == (True, "failed-as-expected"), detail


TRACE_RUNS = """
[[run]]
id = "replay"
class = "scenario-trace"
purpose = "The sequence is a behaviour."
trace = ["Step", "Step", "Step"]
expect = "pass"

[[run]]
id = "refusal"
class = "scenario-trace"
purpose = "The third step is not permitted."
trace = ["Step", "Step", "Step"]
expect = { fail = "blocked", executed = 2 }
"""


@pytest.mark.parametrize(
    ("run_id", "output", "expected"),
    [
        ("replay", REPLAYED, (True, "replayed")),
        ("replay", REFUSED, (False, "refused")),
        ("replay", REPLAYED.replace("3 links", "2 links"), (False, "unrecognized")),
        # The release prints its pass line, with no warning, when the step it
        # refused was the last one. Only the node count says so.
        ("replay", REPLAYED.replace("Valid Nodes: 4", "Valid Nodes: 3"), (False, "refused")),
        ("refusal", REPLAYED.replace("Valid Nodes: 4", "Valid Nodes: 3"), (True, "refused-as-expected")),
        ("replay", REPLAYED.replace("Valid Nodes: 4 Unique states: 4\n", ""), (False, "unrecognized")),
        ("refusal", REFUSED, (True, "refused-as-expected")),
        ("refusal", REPLAYED, (False, "undetected")),
        ("refusal", REFUSED.replace("executed 2", "executed 1"), (False, "wrong-failure")),
    ],
)
def test_a_replayed_trace_runs_to_its_end_or_is_refused_where_stated(
    mc: types.ModuleType,
    tmp_path: Path,
    run_id: str,
    output: str,
    expected: tuple[bool, str],
) -> None:
    """A replay is judged on the steps loaded and the steps executed."""
    ok, status, _, _ = judged(
        mc, TRACE_RUNS, run_id, tmp_path, exit_code=0, stdout=output, stderr=""
    )
    assert (ok, status) == expected


@pytest.mark.parametrize(
    ("body", "complaint"),
    [
        (ASSURANCE.replace('expect = "pass"', 'expect = "pass"\nexpects = 1'), "unknown keys"),
        (ASSURANCE + '[run.options]\nliveness = "eventual"\n', 'liveness = "strict"'),
        (ASSURANCE + "[run.options]\ndeadlock_detection = false\n", "deadlock detection"),
        (ASSURANCE + "[run.options]\ncrash_on_yield = true\n", "crash_on_yield"),
        (ASSURANCE + ASSURANCE, "used twice"),
        (ASSURANCE.replace('expect = "pass"', 'expect = { fail = "always", assertion = "Bounded" }'), "unmutated and passes"),
        (ASSURANCE + CONTROL.replace('of = "base"', 'of = "missing"'), "must name the assurance run"),
        (ASSURANCE + CONTROL.replace('of = "base"', 'of = "base"\nscenario = "X = 1"'), "may state none"),
        (ASSURANCE + CONTROL.replace('expect = { fail = "always", assertion = "Bounded" }', 'expect = "pass"'), "mutates the specification and fails"),
        (ASSURANCE + CONTROL.replace('fail = "always"', 'fail = "sometimes"'), "unknown failure kind"),
        (TRACE_RUNS.replace('trace = ["Step", "Step", "Step"]\nexpect = "pass"', 'expect = "pass"'), "lists a trace"),
        (ASSURANCE.replace('class = "assurance"', 'class = "assurance"\ntier = "nightly"'), "unknown tier"),
    ],
)
def test_a_malformed_suite_is_refused(
    mc: types.ModuleType, tmp_path: Path, body: str, complaint: str
) -> None:
    """A run cannot lose its mutation, twin or strict options to a typo."""
    with pytest.raises(mc.ModelCheckError, match=complaint):
        mc.load_suite(write_suite(tmp_path, body))


def test_an_unstated_option_is_refused(mc: types.ModuleType, tmp_path: Path) -> None:
    """No checker option is left to the release's default."""
    manifest = write_suite(tmp_path, ASSURANCE)
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace("max_actions = 1000\n", ""),
        encoding="utf-8",
    )
    with pytest.raises(mc.ModelCheckError, match="unstated: max_actions"):
        mc.load_suite(manifest)


@pytest.mark.parametrize(
    ("old", "found"), [("require n < 9", 0), ("n", 9)]
)
def test_a_mutation_anchor_must_match_exactly_once(
    mc: types.ModuleType, old: str, found: int
) -> None:
    """A drifted anchor fails the control instead of testing nothing."""
    with pytest.raises(mc.ModelCheckError, match="expected exactly once"):
        mc.mutate(SPEC, ((old, "x"),), "control")
    assert (SPEC.count(old) == 0) == (found == 0)


def test_a_counterexample_must_pass_through_the_named_step(
    mc: types.ModuleType,
) -> None:
    """A control that fails by another route did not fail for its reason."""
    expected = mc.Expectation(
        passes=False, kind="always", assertion="Bounded", via=("EnvChanges",)
    )
    assert mc.missing_steps(expected, ("Init", "Step")) == ["EnvChanges"]
    assert mc.missing_steps(expected, ("Init", "EnvChanges", "Step")) == []


def test_the_extended_tier_includes_the_routine_runs(
    mc: types.ModuleType, tmp_path: Path
) -> None:
    """A larger exploration is run as well as the mandatory suite, never instead."""
    extended = ASSURANCE.replace('id = "base"', 'id = "wide"\ntier = "extended"')
    suite = mc.load_suite(write_suite(tmp_path, ASSURANCE + CONTROL + extended))
    assert [run.id for run in mc.select(suite, "routine")] == ["base", "control"]
    assert [run.id for run in mc.select(suite, "extended")] == ["base", "control", "wide"]
    assert [run.id for run in mc.select(suite, "routine", ["control"])] == ["base", "control"]
    with pytest.raises(mc.ModelCheckError, match="no such run"):
        mc.select(suite, "routine", ["wide"])


def test_an_expectation_naming_an_undeclared_assertion_is_reported(
    mc: types.ModuleType, tmp_path: Path
) -> None:
    """A misspelt assertion is caught before any run starts."""
    suite = mc.load_suite(
        write_suite(tmp_path, ASSURANCE + CONTROL.replace('"Bounded"', '"Bounden"'))
    )
    assert "Bounden" in mc.unknown_assertions(suite)[0]


def fake_release(home: Path, script: str) -> str:
    """Write a doubled ``fizz`` under ``home`` and return a matching pin."""
    root = home / "release"
    root.mkdir(parents=True)
    fizz = root / "fizz"
    fizz.write_text("#!/bin/bash\n" + textwrap.dedent(script), encoding="utf-8")
    fizz.chmod(fizz.stat().st_mode | stat.S_IXUSR)
    return textwrap.dedent(
        f"""\
        [checker]
        version = "v-test"
        url = "file:///nowhere"
        sha256 = "0"
        root = "release"
        [checker.files]
        "fizz" = "{digest(fizz)}"
        """
    )


def test_a_missing_or_altered_checker_is_refused(
    mc: types.ModuleType, tmp_path: Path
) -> None:
    """The gate needs the pinned release, byte for byte."""
    suite = mc.load_suite(write_suite(tmp_path, ASSURANCE, checker=fake_release(tmp_path / "home", "true\n")))
    assert mc.locate_checker(tmp_path / "home", suite.checker).name == "fizz"
    with pytest.raises(mc.ModelCheckError, match="is not installed"):
        mc.locate_checker(tmp_path / "elsewhere", suite.checker)
    (tmp_path / "home" / "release" / "fizz").write_text("#!/bin/bash\nfalse\n")
    with pytest.raises(mc.ModelCheckError, match="is not the pinned v-test"):
        mc.locate_checker(tmp_path / "home", suite.checker)


def test_installation_verifies_the_archive_before_unpacking(
    mc: types.ModuleType, tmp_path: Path
) -> None:
    """A download with another digest unpacks nothing."""
    staging = tmp_path / "staging"
    pin = fake_release(staging, "true\n")
    archive = tmp_path / "release.tar.gz"
    with tarfile.open(archive, "w:gz") as bundle:
        bundle.add(staging / "release", arcname="release")
    good = pin.replace('sha256 = "0"', f'sha256 = "{digest(archive)}"')

    def fetch(_url: str, destination: Path) -> None:
        """Stand in for the download."""
        shutil.copy(archive, destination)

    wrong = mc.load_suite(write_suite(tmp_path, ASSURANCE, checker=pin))
    with pytest.raises(mc.ModelCheckError, match="nothing was unpacked"):
        mc.install_checker(tmp_path / "home", wrong.checker, fetch)
    assert not (tmp_path / "home" / "release").exists()

    right = mc.load_suite(write_suite(tmp_path, ASSURANCE, checker=good))
    assert mc.install_checker(tmp_path / "home", right.checker, fetch).is_file()

    def refuse(_url: str, _destination: Path) -> None:
        """Fail if an intact installation is fetched again."""
        raise AssertionError("an intact installation must not be downloaded again")

    assert mc.install_checker(tmp_path / "home", right.checker, refuse).is_file()


def run_cli(*arguments: str, timeout: int = 300) -> subprocess.CompletedProcess[str]:
    """Run the real command line, as the Makefile target does."""
    uv = shutil.which("uv")
    assert uv, "uv is required to run the model-check command line"
    return subprocess.run(
        [uv, "run", "--script", str(CLI_PATH), *arguments],
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=REPOSITORY_ROOT,
    )


@pytest.mark.slow
@pytest.mark.parametrize(
    ("script", "status", "detail"),
    [
        (f"cat <<'OUT'\n{PASSED}OUT\n", 0, "1 runs met their expectations"),
        (f"cat <<'OUT'\n{INVARIANT_FAILED}OUT\n", 1, "expected a pass"),
        ("echo 'Error: Compilation failed'; exit 1\n", 1, "exited with status 1"),
        ("sleep 60\n", 1, "did not finish within 2s"),
        ("kill -KILL $$\n", 1, "stopped by a signal"),
        ("true\n", 1, "no recognized pass or failure"),
    ],
    ids=["passes", "fails", "crashes", "hangs", "killed", "silent"],
)
def test_the_command_line_fails_closed_on_a_doubled_checker(
    tmp_path: Path, script: str, status: int, detail: str
) -> None:
    """The real process boundary: a checker that fails, crashes or hangs.

    Each double is a real executable run through the launcher's own Cuprum
    boundary, so the timeout, the signal and the exit status are the ones
    the gate would see.
    """
    pin = fake_release(tmp_path / "home", script)
    suite = write_suite(tmp_path, ASSURANCE.replace("purpose", "timeout_seconds = 2\npurpose"), checker=pin)
    result = run_cli(
        "check", "--suite", str(suite), "--home", str(tmp_path / "home"),
        "--report", str(tmp_path / "report"),
    )
    assert result.returncode == status, result.stdout + result.stderr
    assert detail in result.stdout, result.stdout + result.stderr
    document = json.loads((tmp_path / "report" / "report.json").read_text())
    assert document["ok"] is (status == 0)
    assert document["checker"]["version"] == "v-test"


@pytest.mark.slow
def test_the_command_line_refuses_a_missing_checker(tmp_path: Path) -> None:
    """Without the pinned release there is no result, and the exit says so."""
    suite = write_suite(tmp_path, ASSURANCE)
    result = run_cli("check", "--suite", str(suite), "--home", str(tmp_path / "home"))
    assert result.returncode == 1
    assert "is not installed" in result.stderr


@pytest.mark.slow
def test_a_named_subset_is_reported_as_partial(tmp_path: Path) -> None:
    """Selecting runs while iterating can never be mistaken for the gate."""
    pin = fake_release(tmp_path / "home", f"cat <<'OUT'\n{PASSED}OUT\n")
    suite = write_suite(tmp_path, ASSURANCE, checker=pin)
    result = run_cli(
        "check", "--suite", str(suite), "--home", str(tmp_path / "home"),
        "--report", str(tmp_path / "report"), "--only", "base",
    )
    assert "PARTIAL" in result.stdout
    assert json.loads((tmp_path / "report" / "report.json").read_text())["partial"]


def pinned_checker(mc: types.ModuleType) -> Path:
    """Return the real pinned launcher, skipping where it is not installed."""
    suite = mc.load_suite(SUITE_PATH)
    try:
        return mc.locate_checker(CHECKER_HOME, suite.checker)
    except mc.ModelCheckError as error:
        if os.environ.get("GITHUB_ACTIONS"):
            pytest.fail(f"the workflow installs FizzBee before the gates: {error}")
        pytest.skip(f"run `make fizzbee` to exercise the pinned checker: {error}")


REAL_RUNS = """
[[run]]
id = "base"
class = "assurance"
purpose = "The unmodified specification passes."
expect = "pass"

[[run]]
id = "control"
class = "negative-control"
of = "base"
purpose = "Widening the guard breaks the bound."
expect = { fail = "always", assertion = "Bounded", via = ["Step"] }
[[run.mutation]]
old = "require n < 2"
new = "require n < 3"

[[run]]
id = "deadlock-control"
class = "negative-control"
of = "base"
purpose = "Narrowing the guard strands the model short of its terminal state."
expect = { fail = "deadlock" }
[[run.mutation]]
old = "require n < 2"
new = "require n < 1"

[[run]]
id = "progress-control"
class = "negative-control"
of = "base"
purpose = "Without fairness the model may idle forever before its goal."
expect = { fail = "liveness", assertion = "Progress" }
[[run.mutation]]
old = "atomic fair action Step:"
new = "atomic action Step:"
[[run.mutation]]
old = "require n == 2"
new = "require n >= 0"
"""


@pytest.mark.slow
def test_the_pinned_checker_meets_the_launcher_contract(
    mc: types.ModuleType, tmp_path: Path
) -> None:
    """The real release: a pass, and one detected failure of each kind used.

    The controls break an invariant, strand the model short of its terminal
    state, and remove the fairness its progress depends on; the launcher
    must read each as the failure the suite names.
    """
    pinned_checker(mc)
    real = SUITE_PATH.read_text(encoding="utf-8")
    pin = real[real.index("[checker]") : real.index("[defaults]")]
    suite = write_suite(tmp_path, REAL_RUNS, checker=pin)
    spec = tmp_path / "spec.fizz"
    spec.write_text(
        SPEC.replace("atomic action Step:", "atomic fair action Step:")
        + "\natomic action Settled:\n    require n == 2\n    pass\n",
        encoding="utf-8",
    )
    result = run_cli(
        "check", "--suite", str(suite), "--home", str(CHECKER_HOME),
        "--report", str(tmp_path / "report"),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "4 runs met their expectations" in result.stdout


@pytest.mark.slow
@pytest.mark.parametrize(
    ("damage", "detail"),
    [
        (("    n = 0\n", "    n = \n"), "exited with status 1"),
        (("return n <= 2", "return undefined_name <= 2"), "exited with status"),
    ],
    ids=["syntax-error", "runtime-error"],
)
def test_the_pinned_checker_rejecting_a_specification_is_not_detection(
    mc: types.ModuleType, tmp_path: Path, damage: tuple[str, str], detail: str
) -> None:
    """An invalid specification fails the gate even where a failure is expected."""
    pinned_checker(mc)
    real = SUITE_PATH.read_text(encoding="utf-8")
    pin = real[real.index("[checker]") : real.index("[defaults]")]
    broken = ASSURANCE + CONTROL.replace(
        'old = "require n < 2"\nnew = "require n < 3"',
        f"old = {json.dumps(damage[0])}\nnew = {json.dumps(damage[1])}",
    )
    suite = write_suite(tmp_path, broken, checker=pin)
    (tmp_path / "spec.fizz").write_text(
        SPEC.replace("atomic action Step:", "atomic fair action Step:")
        + "\natomic action Settled:\n    require n == 2\n    pass\n",
        encoding="utf-8",
    )
    result = run_cli(
        "check", "--suite", str(suite), "--home", str(CHECKER_HOME),
        "--report", str(tmp_path / "report"),
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert detail in result.stdout, result.stdout
    assert "control: error" in result.stdout, result.stdout
