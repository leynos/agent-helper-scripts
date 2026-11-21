"""Behavioural tests for what a model-checking run leaves behind.

A gate run leaves three things: each run's artefacts in its own directory,
the JSON report, and the summary a person reads. ``scripts/model_check.py``
keeps the artefacts through one recorder and ``scripts/model_check_report.py``
renders the report and the summary. These tests build runs and outcomes
directly, with a doubled process boundary, and never run the checker.

They assert what each must say, and that a failure to keep evidence is
explicit: an expected counterexample is never listed as assurance, an empty
run list is never a pass, each run's evidence reaches the report, and a
checker, trace or input that cannot be read, a directory that cannot be
removed or a file that cannot be written stops the invocation with a named
error instead of being read as an empty, missing or stale result.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
import hashlib
import importlib
import os
from pathlib import Path
import sys
import types

import pytest

from spelling_policy_support import SCRIPTS_PATH

EXPECTED_HEADING = "Expected counterexamples (recorded limitations, not assurance)"
ASSURANCE_HEADING = "Assurance (must pass)"


@pytest.fixture(name="modules", scope="module")
def launcher_modules() -> Iterator[types.SimpleNamespace]:
    """Load the launcher's record and report modules through the runtime path."""
    directory = str(SCRIPTS_PATH)
    sys.path.insert(0, directory)
    try:
        yield types.SimpleNamespace(
            mc=importlib.import_module("model_check"),
            judge=importlib.import_module("model_check_judge"),
            report=importlib.import_module("model_check_report"),
            suite=importlib.import_module("model_check_suite"),
        )
    finally:
        sys.path.remove(directory)


def make_run(modules: types.SimpleNamespace, run_id: str, kind: str, **fields: object) -> object:
    """Return a run of one class with every other field at a plain value."""
    run = modules.suite.Run(
        id=run_id,
        tier="routine",
        kind=kind,
        purpose="a behavioural test",
        spec="readiness.fizz",
        options={"max_actions": 1000},
        scenario="",
        mutations=(),
        expectation=modules.suite.Expectation(passes=True),
        obligations=(),
        timeout_seconds=60,
    )
    return replace(run, **fields)


def make_outcome(
    modules: types.SimpleNamespace, run: object, *, ok: bool = True, **reading: object
) -> object:
    """Return a judged outcome for ``run`` with the given checker reading."""
    return modules.mc.Outcome(
        run=run,
        ok=ok,
        status="passed" if ok else "wrong-outcome",
        detail="as expected" if ok else "not as expected",
        reading=modules.judge.Reading(**reading),
        seconds=1.25,
        spec_sha256="0" * 64,
        command=("fizz", "readiness.fizz"),
    )


def make_suite(modules: types.SimpleNamespace) -> object:
    """Return a suite carrying a known checker pin and no runs."""
    checker = modules.suite.Checker(
        version="v0.5.4", url="https://example.invalid/f.tar.gz", archive_sha256="ab" * 32,
        root="fizzbee", files={},
    )
    return modules.suite.Suite(path=Path("specs/suite.toml"), checker=checker, runs=())


def sections(summary: str) -> dict[str, list[str]]:
    """Return the summary's lines grouped under the heading they follow."""
    grouped: dict[str, list[str]] = {}
    current = ""
    for line in summary.splitlines():
        if not line.startswith(" ") and not line.startswith("model-check:"):
            current = line
            grouped[current] = []
        else:
            grouped.setdefault(current, []).append(line)
    return grouped


def test_an_expected_counterexample_is_listed_only_as_a_limitation(
    modules: types.SimpleNamespace,
) -> None:
    """A recorded limitation appears under its own heading, never as assurance."""
    outcomes = [
        make_outcome(modules, make_run(modules, "permitted-path", "assurance")),
        make_outcome(modules, make_run(modules, "stale-ready", "expected-counterexample")),
    ]
    grouped = sections(modules.report.summarize(outcomes, partial=False))
    assert any("stale-ready" in line for line in grouped[EXPECTED_HEADING])
    assert not any("stale-ready" in line for line in grouped[ASSURANCE_HEADING])
    assert any("permitted-path" in line for line in grouped[ASSURANCE_HEADING])


def test_an_empty_run_list_is_never_a_pass(modules: types.SimpleNamespace) -> None:
    """Running nothing fails both the summary verdict and the report."""
    summary = modules.report.summarize([], partial=False)
    assert summary.splitlines()[-1] == "model-check: FAILED (0 of 0 runs)"
    document = modules.report.report(make_suite(modules), [], tier="routine", partial=False)
    assert document["ok"] is False
    assert document["runs"] == []


def test_a_failed_run_fails_the_verdict_and_a_subset_says_so(
    modules: types.SimpleNamespace,
) -> None:
    """One failed run fails the verdict, and a named subset is never a gate result."""
    failed = make_outcome(modules, make_run(modules, "broken", "assurance"), ok=False)
    lines = modules.report.summarize([failed], partial=True).splitlines()
    assert lines[-2:] == [
        "PARTIAL: a named subset was run; this is not a gate result.",
        "model-check: FAILED (1 of 1 runs)",
    ]


def test_the_report_keeps_each_runs_evidence(modules: types.SimpleNamespace) -> None:
    """Each run's replayed steps, temporal checks, expectation and obligations are kept."""
    expectation = modules.suite.Expectation(
        passes=False, kind="transition", assertion="ReadyNeedsCurrentEvidence"
    )
    run = make_run(
        modules,
        "trace-current-whole-plan",
        "scenario-trace",
        trace=("Init", "AgentInspectsDiscussion", "AgentDecides"),
        expectation=expectation,
        obligations=("PRR-ELIG-01", "PRR-ORDER-01"),
    )
    outcome = make_outcome(modules, run, checked_temporal=("ProgressWhenWarranted",))
    document = modules.report.report(make_suite(modules), [outcome], tier="routine", partial=False)
    [record] = document["runs"]
    assert record["id"] == "trace-current-whole-plan"
    assert record["replayed_steps"] == 3
    assert record["temporal_checked"] == ["ProgressWhenWarranted"]
    assert record["expected"] == "fail: transition ReadyNeedsCurrentEvidence"
    assert record["obligations"] == ["PRR-ELIG-01", "PRR-ORDER-01"]
    assert document["ok"] is True
    assert document["checker"]["version"] == "v0.5.4"


def test_the_run_line_names_checker_tier_jobs_time_and_memory(
    modules: types.SimpleNamespace,
) -> None:
    """The one-line account states what ran, how widely, how long and how large."""
    document = {
        "checker": {"version": "v0.5.4"},
        "tier": "routine",
        "jobs": 4,
        "wall_seconds": 72.2,
        "peak_child_rss_kib": 2_028_544,
    }
    line = modules.report.run_line(document, Path("build/model-check/report.json"))
    assert line == (
        "FizzBee v0.5.4; tier routine; 4 at a time; 72.2s;"
        " peak checker RSS 1981 MiB; report in build/model-check/report.json"
    )


#: The pinned checker's echo of the options ``control_session`` states.
OPTIONS_ECHO = (
    "StateSpaceOptions: options:{max_actions:1000  max_concurrent_actions:1"
    '  crash_on_yield:false}  liveness:"strict"  deadlock_detection:true'
)
FAILED_OUTPUT = f"""{OPTIONS_ECHO}
Nodes: 5, queued: 4
FAILED: Model checker failed. Invariant:  Bounded
"""


def failing_runner(modules: types.SimpleNamespace, graph: str | None):
    """Return a doubled checker that fails ``Bounded`` and writes ``graph``.

    ``graph`` is the text of ``out/error-graph.json``, or None to write none.
    """

    def run(_argv: object, cwd: Path, _timeout: int) -> object:
        """Write the error graph, if any, and report the failed invariant."""
        if graph is not None:
            (cwd / "out").mkdir()
            (cwd / "out" / "error-graph.json").write_text(graph, encoding="utf-8")
        return modules.judge.ProcessResult(exit_code=0, stdout=FAILED_OUTPUT, stderr="")

    return run


def control_session(modules: types.SimpleNamespace, tmp_path: Path, graph: str | None):
    """Return a negative control requiring ``Step`` and a session that runs it."""
    (tmp_path / "spec.fizz").write_text("action Init:\n    n = 0\n", encoding="utf-8")
    run = make_run(
        modules,
        "control",
        "negative-control",
        spec="spec.fizz",
        options={
            "max_actions": 1000,
            "max_concurrent_actions": 1,
            "crash_on_yield": False,
            "deadlock_detection": True,
            "liveness": "strict",
        },
        expectation=modules.suite.Expectation(
            passes=False, kind="always", assertion="Bounded", via=("Step",)
        ),
    )
    suite = replace(make_suite(modules), path=tmp_path / "suite.toml")
    report = tmp_path / "report"
    report.mkdir()
    session = modules.mc.Session(
        suite=suite, fizz=tmp_path / "fizz", report=report, runner=failing_runner(modules, graph)
    )
    return run, session


def test_a_readable_trace_is_kept_and_judged(
    modules: types.SimpleNamespace, tmp_path: Path
) -> None:
    """The recorder keeps the output and trace; the judgement requires its steps."""
    graph = '[{"Name": "Init"}, {"Name": "Step"}]'
    run, session = control_session(modules, tmp_path, graph)
    outcome = modules.mc.execute(run, session)
    work = session.report / "control"
    assert (outcome.ok, outcome.trace) == (True, ("Init", "Step"))
    assert (work / "stdout.txt").read_text(encoding="utf-8") == FAILED_OUTPUT
    assert (work / "stderr.txt").read_text(encoding="utf-8") == ""
    assert (work / "trace.txt").read_text(encoding="utf-8") == "Init\nStep\n"


def test_an_absent_trace_is_no_trace(modules: types.SimpleNamespace, tmp_path: Path) -> None:
    """With no error graph, a control naming a step fails for the wrong reason."""
    run, session = control_session(modules, tmp_path, None)
    outcome = modules.mc.execute(run, session)
    assert (outcome.ok, outcome.status, outcome.trace) == (False, "wrong-reason", ())
    assert not (session.report / "control" / "trace.txt").exists()


@pytest.mark.parametrize(
    ("graph", "refusal"),
    [("[{", "is not JSON"), ('{"Name": "Init"}', "is not a list of steps")],
    ids=["malformed", "not-a-list"],
)
def test_a_trace_that_cannot_be_parsed_is_an_error_not_a_verdict(
    modules: types.SimpleNamespace, tmp_path: Path, graph: str, refusal: str
) -> None:
    """A present but unparsable graph stops the run, naming the file."""
    run, session = control_session(modules, tmp_path, graph)
    with pytest.raises(modules.suite.ModelCheckError, match=refusal) as raised:
        modules.mc.execute(run, session)
    assert "error-graph.json" in str(raised.value)


def test_a_trace_that_cannot_be_read_is_an_error(
    modules: types.SimpleNamespace, tmp_path: Path
) -> None:
    """A graph path that exists and cannot be read is not an empty trace."""
    (tmp_path / "error-graph.json").mkdir()
    with pytest.raises(modules.suite.ModelCheckError, match="cannot read the error trace"):
        modules.mc.read_trace(tmp_path)


def test_a_trace_that_is_not_text_is_an_error(
    modules: types.SimpleNamespace, tmp_path: Path
) -> None:
    """Invalid UTF-8 in the graph stops the run, naming the file, as a ModelCheckError."""
    run, session = control_session(modules, tmp_path, "")
    graph = session.report / "control" / "out" / "error-graph.json"

    def invalid(_argv: object, cwd: Path, _timeout: int) -> object:
        """Write an error graph that is not UTF-8 and report the failure."""
        (cwd / "out").mkdir()
        (cwd / "out" / "error-graph.json").write_bytes(b"\xff\xfe[")
        return modules.judge.ProcessResult(exit_code=0, stdout=FAILED_OUTPUT, stderr="")

    session = replace(session, runner=invalid)
    with pytest.raises(modules.suite.ModelCheckError, match="is not UTF-8 text") as raised:
        modules.mc.execute(run, session)
    assert str(graph) in str(raised.value)


def test_an_artefact_that_cannot_be_written_is_an_error(
    modules: types.SimpleNamespace, tmp_path: Path
) -> None:
    """The recorder and the report name the file they could not write."""
    result = modules.judge.ProcessResult(exit_code=0, stdout="", stderr="")
    missing = tmp_path / "missing"
    with pytest.raises(modules.suite.ModelCheckError, match="cannot write .*stdout.txt"):
        modules.mc.record_artefacts(modules.mc.RunDirectory(missing), result)
    with pytest.raises(modules.suite.ModelCheckError, match="cannot write .*report.json"):
        modules.report.write_report({}, missing)


@pytest.mark.skipif(os.geteuid() == 0, reason="root can remove a read-only directory's entries")
def test_a_report_directory_that_cannot_be_removed_is_an_error(
    modules: types.SimpleNamespace, tmp_path: Path
) -> None:
    """A stale report that survives deletion stops the run instead of being reused."""
    report = tmp_path / "report"
    stale = report / "stale-run"
    stale.mkdir(parents=True)
    (stale / "stdout.txt").write_text("old evidence", encoding="utf-8")
    stale.chmod(0o500)
    try:
        with pytest.raises(modules.suite.ModelCheckError, match="cannot remove .*report"):
            modules.mc.reset_report(report)
    finally:
        stale.chmod(0o700)
    assert (stale / "stdout.txt").exists()
    modules.mc.reset_report(report)
    assert report.is_dir() and not any(report.iterdir())
    modules.mc.remove_tree(tmp_path / "never-existed")


def test_inputs_that_are_not_utf_8_are_named(
    modules: types.SimpleNamespace, tmp_path: Path
) -> None:
    """A suite or specification that is not text is a named error, not a crash."""
    manifest = tmp_path / "suite.toml"
    manifest.write_bytes(b"\xff\xfe")
    with pytest.raises(modules.suite.ModelCheckError, match="cannot read suite .*suite.toml"):
        modules.suite.load_suite(manifest)
    run, session = control_session(modules, tmp_path, None)
    (tmp_path / "spec.fizz").write_bytes(b"\xff\xfe")
    with pytest.raises(modules.suite.ModelCheckError, match="cannot read specification .*spec.fizz"):
        modules.suite.unknown_assertions(replace(session.suite, runs=(run,)))
    with pytest.raises(modules.suite.ModelCheckError, match="cannot read .*spec.fizz"):
        modules.mc.execute(run, session)


@pytest.mark.skipif(os.geteuid() == 0, reason="root can read a file without read permission")
def test_an_unreadable_checker_is_named_and_never_reinstalled(
    modules: types.SimpleNamespace, tmp_path: Path
) -> None:
    """A pinned file that cannot be read is an error, not a missing release.

    Installing would download over a release nobody could inspect, so the
    install path must stop with the same named error instead of fetching.
    """
    fizz = tmp_path / "release" / "fizz"
    fizz.parent.mkdir()
    fizz.write_text("#!/bin/bash\ntrue\n", encoding="utf-8")
    checker = replace(
        make_suite(modules).checker,
        root="release",
        files={"fizz": hashlib.sha256(fizz.read_bytes()).hexdigest()},
    )

    def fetch(_url: str, _destination: Path) -> None:
        """Fail the test: an unreadable release must not be replaced."""
        raise AssertionError("the installer fetched over an unreadable release")

    assert modules.mc.verify_checker(tmp_path, checker) == fizz
    fizz.chmod(0)
    try:
        with pytest.raises(modules.suite.ModelCheckError, match="cannot read the pinned checker file") as raised:
            modules.mc.verify_checker(tmp_path, checker)
        assert not isinstance(raised.value, modules.mc.CheckerAbsentError)
        with pytest.raises(modules.suite.ModelCheckError, match="cannot read the pinned checker file .*fizz"):
            modules.mc.install_checker(tmp_path, checker, fetch)
    finally:
        fizz.chmod(0o700)


class MemoryFiles:
    """An in-memory run directory: what the launcher wrote, by file name."""

    def __init__(self, path: Path, trace: tuple[str, ...] = ()) -> None:
        """Hold no files yet, and the trace the doubled checker left."""
        self.path = path
        self.files: dict[str, str] = {}
        self.created = False
        self._trace = trace

    def create(self) -> None:
        """Record that the run's directory was made."""
        self.created = True

    def write(self, name: str, text: str) -> None:
        """Keep one run file in memory."""
        self.files[name] = text

    def trace(self) -> tuple[str, ...]:
        """Return the trace the doubled checker left."""
        return self._trace


def test_run_files_are_written_only_through_the_boundary(
    modules: types.SimpleNamespace, tmp_path: Path
) -> None:
    """Inputs and artefacts go through ``RunFiles``; nothing touches the disk."""
    run = make_run(
        modules, "replayed", "scenario-trace",
        options={"max_actions": 10, "max_concurrent_actions": 1, "crash_on_yield": False,
                 "deadlock_detection": True, "liveness": "strict"},
        scenario="SCENARIOS = []", trace=("Init", "Step"),
    )
    files = MemoryFiles(tmp_path / "never-made", trace=("Init", "Step"))
    text, argv = modules.mc.prepare_inputs(run, "action Init:\n    n = 0\n", files)
    result = modules.judge.ProcessResult(exit_code=0, stdout="out", stderr="err")
    trace = modules.mc.record_artefacts(files, result)
    assert files.created and not files.path.exists()
    assert sorted(files.files) == [
        "fizz.yaml", "replay.txt", "scenario.cfg", "spec.fizz", "stderr.txt", "stdout.txt", "trace.txt",
    ]
    assert (files.files["spec.fizz"], files.files["replay.txt"]) == (text, "Init\nStep\n")
    assert argv[-1] == "spec.fizz" and "--trace-file" in argv
    assert trace == ("Init", "Step") and files.files["trace.txt"] == "Init\nStep\n"


def test_the_exit_status_follows_the_report(modules: types.SimpleNamespace) -> None:
    """A failure exits one, a passing subset exits partial, a full pass exits zero."""
    document = modules.report.gate_document(
        make_suite(modules), [], selection=("routine", False), cost=(72.24, 4, 2048)
    )
    assert (document["wall_seconds"], document["jobs"], document["peak_child_rss_kib"]) == (72.2, 4, 2048)
    status = modules.report.exit_status
    assert status(document) == 1
    assert status({"ok": True, "partial": True}) == modules.report.PARTIAL_STATUS == 3
    assert status({"ok": True, "partial": False}) == 0


def test_the_launcher_path_is_computed_without_reading(
    modules: types.SimpleNamespace, tmp_path: Path
) -> None:
    """Where the launcher is needs no file; verifying it does."""
    checker = replace(make_suite(modules).checker, root="release", files={"fizz": "0"})
    assert modules.mc.checker_launcher(tmp_path, checker) == tmp_path.resolve() / "release" / "fizz"
    with pytest.raises(modules.mc.CheckerAbsentError, match="is not installed"):
        modules.mc.verify_checker(tmp_path, checker)


@pytest.mark.skipif(os.geteuid() == 0, reason="root writes into a read-only directory")
def test_an_install_names_a_home_it_cannot_create(
    modules: types.SimpleNamespace, tmp_path: Path
) -> None:
    """A checker home that cannot be created is a named error, not a crash."""
    checker = replace(make_suite(modules).checker, root="release", files={"fizz": "0"})
    parent = tmp_path / "locked"
    parent.mkdir(mode=0o500)
    try:
        with pytest.raises(modules.suite.ModelCheckError, match="cannot create the checker home .*locked"):
            modules.mc.install_checker(parent / "home", checker, lambda *_: None)
    finally:
        parent.chmod(0o700)


@pytest.mark.skipif(os.geteuid() == 0, reason="root removes from a read-only directory")
def test_a_failed_install_keeps_its_error_when_cleanup_also_fails(
    modules: types.SimpleNamespace, tmp_path: Path
) -> None:
    """The install's own error is reported, with the cleanup failure as a note."""
    checker = replace(make_suite(modules).checker, root="release", files={"fizz": "0"})
    home = tmp_path / "home"

    def fetch(_url: str, destination: Path) -> None:
        """Write an archive with the wrong digest, then lock its directory."""
        destination.write_bytes(b"not the pinned archive")
        destination.parent.chmod(0o500)

    try:
        with pytest.raises(modules.suite.ModelCheckError, match="has SHA-256") as raised:
            modules.mc.install_checker(home, checker, fetch)
    finally:
        home.chmod(0o700)
    notes = getattr(raised.value, "__notes__", [])
    assert any("cannot remove the downloaded archive" in note for note in notes), notes
