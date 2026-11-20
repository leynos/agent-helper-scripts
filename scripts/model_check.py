"""Run a pinned FizzBee model-checking suite and judge it fail-closed.

A suite is a TOML manifest beside its specifications. It pins one checker
release by digest and lists runs. Each run names a specification, the checker
options, a scenario the specification is configured with, and the one outcome
that run must have:

``assurance``
    The unmodified specification must pass, exhaustively.
``negative-control``
    A textual mutation of the specification must fail one named assertion.
    Its ``of`` run is the unmutated twin, so the failure is the mutation's.
``property-control``
    The unmodified specification must fail one named assertion under a
    scenario built to defeat it, which shows the assertion is evaluated.
``expected-counterexample``
    The unmodified specification must fail one named assertion that states a
    property the modelled protocol is known not to have. These record a
    limitation and are reported apart from assurance.
``scenario-trace``
    A named sequence of events is replayed through the unmodified
    specification. It must either run to its end, which shows the sequence
    is a behaviour of the model, or be refused after a stated number of
    steps, which shows the model does not permit the step that follows.

The pinned release reports a failed property on standard output and still
exits zero, drops liveness checking without comment when the ``liveness``
option is not a value it knows, and stops at ``max_actions`` without saying
so. This module therefore decides from the output it can recognize, requires
the checker to echo the options it was given and to name every temporal
assertion it checked, and counts a pass as exhaustive only when fewer nodes
were explored than the action bound allows. Anything else is a gate failure:
an unknown line is never read as success, and a crash, a timeout or a syntax
error is never read as a control detecting its defect.

The process boundary is injected. The sibling ``model_check_cli`` module
supplies the Cuprum-backed runner and the downloader; tests supply doubles.

Examples
--------
Run the mandatory suite::

    uv run --script scripts/model_check_cli.py check \\
        --suite specs/pr-readiness/suite.toml
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import re
import shutil
import tarfile
import tomllib

#: Tiers a run may belong to. The mandatory gate runs ``routine`` only, and a
#: larger exploration never stands in for it.
TIERS = ("routine", "extended")

#: What a run is evidence of; see the module docstring.
CLASSES = (
    "assurance",
    "negative-control",
    "property-control",
    "expected-counterexample",
    "scenario-trace",
)

#: Failure kinds the pinned checker reports, by the names this suite uses.
FAILURE_KINDS = (
    "always",
    "transition",
    "exists",
    "liveness",
    "deadlock",
    "blocked",
)

#: Checker options every run must state. None is left to a default.
REQUIRED_OPTIONS = (
    "max_actions",
    "max_concurrent_actions",
    "crash_on_yield",
    "deadlock_detection",
    "liveness",
)

PASS_LINE = "PASSED: Model checker completed successfully"
_INVARIANT = re.compile(r"^FAILED: Model checker failed\. Invariant:\s+(\w+)$")
_TRANSITION = re.compile(
    r"^FAILED: Model checker failed\. Transition Invariant:\s+(\w+)$"
)
_UNREACHED = "FAILED: Expected states never reached"
_UNREACHED_NAME = re.compile(r"^Invariant \d+: (\w+)$")
_LIVENESS = "FAILED: Liveness check failed"
_LIVENESS_NAME = re.compile(r"^Invariant: (\w+)$")
_DEADLOCK = "DEADLOCK detected"
_BARE_FAILURE = "FAILED: Model checker failed"
_NODES = re.compile(r"^Nodes: (\d+), queued: (\d+)$")
_STATES = re.compile(r"^Valid Nodes: (\d+) Unique states: (\d+)$")
_OPTIONS = re.compile(r"^StateSpaceOptions: (.*)$")
_CHECKING = re.compile(r"^Checking (?:eventually always|always eventually) (\w+)$")
_TEMPORAL = re.compile(
    r"^(?:eventually always|always eventually) assertion (\w+)\s*:", re.MULTILINE
)
_TRACE_LOADED = re.compile(r"^Loaded trace with (\d+) links$")
_TRACE_SHORT = re.compile(
    r"^WARNING: Trace execution incomplete\. Expected (\d+) links,"
    r" executed (\d+) links\.$"
)
_ASSERTION = re.compile(
    r"^(?:always|exists|transition|eventually always|always eventually)"
    r" assertion (\w+)",
    re.MULTILINE,
)


class ModelCheckError(RuntimeError):
    """Report that the suite could not be loaded, located or run."""


@dataclass(frozen=True)
class Checker:
    """The pinned checker release and the digests that identify it."""

    version: str
    url: str
    archive_sha256: str
    root: str
    files: Mapping[str, str]


@dataclass(frozen=True)
class Expectation:
    """The one outcome a run must have."""

    passes: bool
    kind: str = ""
    assertion: str = ""
    via: tuple[str, ...] = ()
    executed: int = 0

    def describe(self) -> str:
        """Return the expectation as it is written in a report."""
        if self.passes:
            return "pass"
        if self.kind == "deadlock":
            return "fail: deadlock"
        if self.kind == "blocked":
            return f"refused after {self.executed} steps"
        return f"fail: {self.kind} {self.assertion}"


@dataclass(frozen=True)
class Run:
    """One configured invocation of the checker and its required outcome."""

    id: str
    tier: str
    kind: str
    purpose: str
    spec: str
    options: Mapping[str, object]
    scenario: str
    mutations: tuple[tuple[str, str], ...]
    expectation: Expectation
    obligations: tuple[str, ...]
    timeout_seconds: int
    of: str = ""
    trace: tuple[str, ...] = ()


@dataclass(frozen=True)
class Suite:
    """A loaded manifest: the checker pin and every run."""

    path: Path
    checker: Checker
    runs: tuple[Run, ...]

    @property
    def directory(self) -> Path:
        """Return the directory specifications are resolved against."""
        return self.path.parent


@dataclass(frozen=True)
class ProcessResult:
    """What the process boundary observed for one checker invocation.

    ``exit_code`` is ``None`` when the checker did not exit of its own accord:
    it was stopped at the timeout or by a signal.
    """

    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool = False
    seconds: float = 0.0


@dataclass(frozen=True)
class Reading:
    """What one invocation's output says, before any expectation is applied."""

    passed: bool = False
    failure_kind: str = ""
    failed_assertions: tuple[str, ...] = ()
    nodes: int | None = None
    queued: int | None = None
    unique_states: int | None = None
    valid_nodes: int | None = None
    options_echo: str = ""
    checked_temporal: tuple[str, ...] = ()
    trace_loaded: int | None = None
    trace_executed: int | None = None
    problem: str = ""


@dataclass(frozen=True)
class Outcome:
    """The judgement on one run, with the facts it rests on."""

    run: Run
    ok: bool
    status: str
    detail: str
    reading: Reading
    seconds: float
    spec_sha256: str
    command: tuple[str, ...]
    trace: tuple[str, ...] = ()
    artefacts: Mapping[str, str] = field(default_factory=dict)


#: Runs one checker invocation: ``(argv, cwd, timeout_seconds)``.
Runner = Callable[[Sequence[str], Path, int], ProcessResult]

#: Fetches ``url`` to ``destination``.
Fetcher = Callable[[str, Path], None]


def _sha256(path: Path) -> str:
    """Return the SHA-256 digest of a file, read in bounded chunks."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _table(value: object, where: str) -> Mapping[str, object]:
    """Return ``value`` as a TOML table, or refuse a manifest of another shape."""
    if not isinstance(value, dict):
        raise ModelCheckError(f"{where} must be a table")
    return value


def _text(table: Mapping[str, object], key: str, where: str) -> str:
    """Return a required non-empty string field."""
    value = table.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ModelCheckError(f"{where} needs a non-empty string `{key}`")
    return value


def _only(table: Mapping[str, object], allowed: Sequence[str], where: str) -> None:
    """Refuse a key the manifest format does not define.

    A misspelt key would otherwise be ignored, and a run would silently lose
    the mutation or expectation it was written to carry.
    """
    unknown = sorted(set(table) - set(allowed))
    if unknown:
        raise ModelCheckError(f"{where} has unknown keys: {', '.join(unknown)}")


def _checker(table: Mapping[str, object]) -> Checker:
    """Build the checker pin from its manifest table."""
    _only(table, ("version", "url", "sha256", "root", "files"), "[checker]")
    files = _table(table.get("files"), "[checker.files]")
    if not files or not all(isinstance(value, str) for value in files.values()):
        raise ModelCheckError("[checker.files] must map each file to its SHA-256")
    return Checker(
        version=_text(table, "version", "[checker]"),
        url=_text(table, "url", "[checker]"),
        archive_sha256=_text(table, "sha256", "[checker]"),
        root=_text(table, "root", "[checker]"),
        files={str(name): str(value) for name, value in files.items()},
    )


def _expectation(value: object, where: str) -> Expectation:
    """Parse ``expect``: the string ``pass`` or a failure table."""
    if value == "pass":
        return Expectation(passes=True)
    table = _table(value, f"{where} expect")
    _only(table, ("fail", "assertion", "via", "executed"), f"{where} expect")
    kind = _text(table, "fail", f"{where} expect")
    if kind not in FAILURE_KINDS:
        raise ModelCheckError(
            f"{where} expects an unknown failure kind `{kind}`;"
            f" known kinds: {', '.join(FAILURE_KINDS)}"
        )
    via = table.get("via", [])
    if not isinstance(via, list) or not all(isinstance(step, str) for step in via):
        raise ModelCheckError(f"{where} expect `via` must be a list of trace steps")
    if kind == "blocked":
        executed = table.get("executed")
        if type(executed) is not int or executed < 0 or "assertion" in table or via:
            raise ModelCheckError(
                f"{where}: a refused trace states only the steps `executed`"
            )
        return Expectation(passes=False, kind=kind, executed=executed)
    if "executed" in table:
        raise ModelCheckError(f"{where}: only a refused trace states `executed`")
    if kind == "deadlock":
        if "assertion" in table:
            raise ModelCheckError(f"{where}: a deadlock names no assertion")
        return Expectation(passes=False, kind=kind, via=tuple(via))
    if kind == "exists" and via:
        raise ModelCheckError(f"{where}: an unreached state has no trace to check")
    return Expectation(
        passes=False,
        kind=kind,
        assertion=_text(table, "assertion", where),
        via=tuple(via),
    )


def _mutations(value: object, where: str) -> tuple[tuple[str, str], ...]:
    """Parse the ``[[run.mutation]]`` tables of one run."""
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ModelCheckError(f"{where} mutation must be an array of tables")
    pairs: list[tuple[str, str]] = []
    for entry in value:
        table = _table(entry, f"{where} mutation")
        _only(table, ("old", "new"), f"{where} mutation")
        old = _text(table, "old", f"{where} mutation")
        new = table.get("new")
        if not isinstance(new, str):
            raise ModelCheckError(f"{where} mutation needs a string `new`")
        pairs.append((old, new))
    return tuple(pairs)


def _options(
    defaults: Mapping[str, object], overrides: Mapping[str, object], where: str
) -> Mapping[str, object]:
    """Merge and validate checker options; every option must be stated.

    Deadlock detection may not be switched off and liveness must be strict:
    either relaxation would let a run pass without checking what the suite
    says it checks, and the pinned release would not report the difference.
    """
    merged = {**defaults, **overrides}
    _only(merged, REQUIRED_OPTIONS, f"{where} options")
    missing = [name for name in REQUIRED_OPTIONS if name not in merged]
    if missing:
        raise ModelCheckError(f"{where} leaves options unstated: {', '.join(missing)}")
    if merged["liveness"] != "strict":
        raise ModelCheckError(f'{where} must set liveness = "strict"')
    if merged["deadlock_detection"] is not True:
        raise ModelCheckError(f"{where} must not disable deadlock detection")
    if merged["crash_on_yield"] is not False:
        raise ModelCheckError(
            f"{where} must set crash_on_yield = false; interruption is modelled"
            " by an explicit action"
        )
    for name in ("max_actions", "max_concurrent_actions"):
        if type(merged[name]) is not int or merged[name] < 1:
            raise ModelCheckError(f"{where} option `{name}` must be a positive integer")
    return merged


_RUN_KEYS = (
    "id",
    "tier",
    "class",
    "purpose",
    "spec",
    "options",
    "scenario",
    "mutation",
    "expect",
    "obligations",
    "timeout_seconds",
    "of",
    "trace",
)


def _run(
    table: Mapping[str, object],
    defaults: Mapping[str, object],
    default_options: Mapping[str, object],
) -> Run:
    """Build one run from its manifest table and the suite defaults."""
    where = f"run `{table.get('id', '?')}`"
    _only(table, _RUN_KEYS, where)
    identifier = _text(table, "id", "a run")
    kind = _text(table, "class", where)
    if kind not in CLASSES:
        raise ModelCheckError(f"{where} has unknown class `{kind}`")
    tier = str(table.get("tier", "routine"))
    if tier not in TIERS:
        raise ModelCheckError(f"{where} has unknown tier `{tier}`")
    obligations = table.get("obligations", [])
    if not isinstance(obligations, list) or not all(
        isinstance(item, str) for item in obligations
    ):
        raise ModelCheckError(f"{where} obligations must be a list of strings")
    timeout = table.get("timeout_seconds", defaults.get("timeout_seconds"))
    if type(timeout) is not int or timeout < 1:
        raise ModelCheckError(f"{where} needs a positive integer timeout_seconds")
    scenario = table.get("scenario", "")
    if not isinstance(scenario, str):
        raise ModelCheckError(f"{where} scenario must be a string")
    trace = table.get("trace", [])
    if not isinstance(trace, list) or not all(
        isinstance(step, str) and step.strip() for step in trace
    ):
        raise ModelCheckError(f"{where} trace must be a list of non-empty steps")
    return Run(
        id=identifier,
        tier=tier,
        kind=kind,
        purpose=_text(table, "purpose", where),
        spec=str(table.get("spec", defaults.get("spec", ""))),
        options=_options(
            default_options, _table(table.get("options", {}), where), where
        ),
        scenario=scenario,
        mutations=_mutations(table.get("mutation"), where),
        expectation=_expectation(table.get("expect"), where),
        obligations=tuple(obligations),
        timeout_seconds=timeout,
        of=str(table.get("of", "")),
        trace=tuple(trace),
    )


def _inherit(run: Run, twin: Run) -> Run:
    """Give a negative control its twin's specification, options and scenario."""
    return Run(
        id=run.id,
        tier=run.tier,
        kind=run.kind,
        purpose=run.purpose,
        spec=twin.spec,
        options=twin.options,
        scenario=twin.scenario,
        mutations=run.mutations,
        expectation=run.expectation,
        obligations=run.obligations,
        timeout_seconds=run.timeout_seconds,
        of=run.of,
    )


def _check_shape(run: Run, by_id: Mapping[str, Run]) -> None:
    """Refuse a run whose class, mutation and expectation disagree."""
    where = f"run `{run.id}`"
    mutated = bool(run.mutations)
    if run.kind == "assurance" and (mutated or not run.expectation.passes):
        raise ModelCheckError(f"{where}: an assurance run is unmutated and passes")
    if run.kind == "negative-control":
        if not mutated or run.expectation.passes:
            raise ModelCheckError(
                f"{where}: a negative control mutates the specification and fails"
            )
        twin = by_id.get(run.of)
        if twin is None or twin.kind != "assurance":
            raise ModelCheckError(
                f"{where}: `of` must name the assurance run it mutates"
            )
        if TIERS.index(twin.tier) > TIERS.index(run.tier):
            raise ModelCheckError(
                f"{where}: its twin `{twin.id}` must run in the same or an"
                " earlier tier"
            )
    elif run.of:
        raise ModelCheckError(f"{where}: only a negative control names `of`")
    if run.kind in ("property-control", "expected-counterexample") and (
        mutated or run.expectation.passes
    ):
        raise ModelCheckError(
            f"{where}: a {run.kind} run is unmutated and expected to fail"
        )
    traced = run.kind == "scenario-trace"
    if traced != bool(run.trace):
        raise ModelCheckError(
            f"{where}: a scenario-trace run, and only that class, lists a trace"
        )
    if traced and mutated:
        raise ModelCheckError(f"{where}: a scenario trace replays the real model")
    if (run.expectation.kind == "blocked") != (traced and not run.expectation.passes):
        raise ModelCheckError(
            f"{where}: a scenario trace runs to its end or is refused, and"
            " nothing else is"
        )
    if not run.spec:
        raise ModelCheckError(f"{where} names no specification")


def load_suite(path: Path) -> Suite:
    """Load and validate a suite manifest.

    Parameters
    ----------
    path : Path
        The TOML manifest. Specifications are resolved against its directory.

    Returns
    -------
    Suite
        The checker pin and the validated runs, negative controls already
        carrying their twin's specification, options and scenario.

    Raises
    ------
    ModelCheckError
        Raised when the manifest is unreadable, uses a key the format does
        not define, leaves a checker option unstated, or pairs a class with a
        mutation or expectation that class cannot have.
    """
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ModelCheckError(f"cannot read suite {path}: {error}") from error
    _only(data, ("checker", "defaults", "run"), "the suite")
    defaults = _table(data.get("defaults", {}), "[defaults]")
    _only(defaults, ("spec", "timeout_seconds", "options"), "[defaults]")
    default_options = _table(defaults.get("options", {}), "[defaults.options]")
    tables = data.get("run")
    if not isinstance(tables, list) or not tables:
        raise ModelCheckError("the suite lists no runs")
    runs = [_run(_table(table, "a run"), defaults, default_options) for table in tables]
    by_id: dict[str, Run] = {}
    for run in runs:
        if run.id in by_id:
            raise ModelCheckError(f"run id `{run.id}` is used twice")
        by_id[run.id] = run
    resolved = []
    for table, run in zip(tables, runs, strict=True):
        twin = by_id.get(run.of)
        if run.kind == "negative-control" and twin is not None:
            if {"spec", "options", "scenario"} & set(table):
                raise ModelCheckError(
                    f"run `{run.id}`: a negative control takes its specification,"
                    " options and scenario from its twin and may state none"
                )
            run = _inherit(run, twin)
        _check_shape(run, by_id)
        resolved.append(run)
    return Suite(
        path=path, checker=_checker(_table(data.get("checker"), "[checker]")),
        runs=tuple(resolved),
    )


def locate_checker(home: Path, checker: Checker) -> Path:
    """Return the pinned ``fizz`` launcher, verified file by file.

    Parameters
    ----------
    home : Path
        The directory the release was unpacked into.
    checker : Checker
        The pin the unpacked files must match.

    Returns
    -------
    Path
        The ``fizz`` launcher inside the unpacked release.

    Raises
    ------
    ModelCheckError
        Raised when a pinned file is absent, which is a missing checker, or
        has another digest, which is an incompatible one.
    """
    root = home / checker.root
    for name, expected in checker.files.items():
        candidate = root / name
        if not candidate.is_file():
            raise ModelCheckError(
                f"FizzBee {checker.version} is not installed: {candidate} is"
                " missing. Run `make fizzbee` to fetch the pinned release."
            )
        actual = _sha256(candidate)
        if actual != expected:
            raise ModelCheckError(
                f"FizzBee at {root} is not the pinned {checker.version}:"
                f" {name} has SHA-256 {actual}, expected {expected}"
            )
    return root / "fizz"


def install_checker(home: Path, checker: Checker, fetch: Fetcher) -> Path:
    """Fetch, verify and unpack the pinned release unless it is present.

    Parameters
    ----------
    home : Path
        The directory to unpack into. It is created when absent.
    checker : Checker
        The release to install and the digests it must have.
    fetch : Fetcher
        Downloads the archive. This is the only step that uses the network.

    Returns
    -------
    Path
        The verified ``fizz`` launcher.

    Raises
    ------
    ModelCheckError
        Raised when the downloaded archive has another digest, or the
        unpacked files do not match the pin.
    """
    try:
        return locate_checker(home, checker)
    except ModelCheckError:
        pass
    home.mkdir(parents=True, exist_ok=True)
    archive = home / f"{checker.root}.tar.gz.partial"
    try:
        fetch(checker.url, archive)
        actual = _sha256(archive)
        if actual != checker.archive_sha256:
            raise ModelCheckError(
                f"downloaded FizzBee archive has SHA-256 {actual}, expected"
                f" {checker.archive_sha256}; nothing was unpacked"
            )
        shutil.rmtree(home / checker.root, ignore_errors=True)
        with tarfile.open(archive) as bundle:
            bundle.extractall(home, filter="data")
    except (OSError, tarfile.TarError) as error:
        raise ModelCheckError(f"cannot install FizzBee: {error}") from error
    finally:
        archive.unlink(missing_ok=True)
    return locate_checker(home, checker)


def mutate(source: str, mutations: Sequence[tuple[str, str]], run_id: str) -> str:
    """Apply each textual mutation, which must match exactly once.

    Parameters
    ----------
    source : str
        The specification text.
    mutations : sequence of (str, str)
        ``(old, new)`` pairs applied in order.
    run_id : str
        Names the run in a refusal.

    Returns
    -------
    str
        The mutated specification.

    Raises
    ------
    ModelCheckError
        Raised when an anchor matches nowhere or more than once. A control
        whose anchor has drifted would otherwise run the unmutated text and
        prove nothing.
    """
    for old, new in mutations:
        found = source.count(old)
        if found != 1:
            raise ModelCheckError(
                f"run `{run_id}`: a mutation anchor matches {found} times,"
                f" expected exactly once: {old.strip().splitlines()[0]!r}"
            )
        source = source.replace(old, new)
    return source


def render_options(options: Mapping[str, object]) -> str:
    """Return the ``fizz.yaml`` that states every checker option."""
    flag = {True: "true", False: "false"}
    return (
        f"deadlock_detection: {flag[bool(options['deadlock_detection'])]}\n"
        f'liveness: "{options["liveness"]}"\n'
        "options:\n"
        f"  max_actions: {options['max_actions']}\n"
        f"  max_concurrent_actions: {options['max_concurrent_actions']}\n"
        f"  crash_on_yield: {flag[bool(options['crash_on_yield'])]}\n"
    )


def read_output(stdout: str) -> Reading:
    """Read one invocation's standard output into facts.

    Parameters
    ----------
    stdout : str
        Everything the checker printed.

    Returns
    -------
    Reading
        The pass or failure it reports, the assertions it names, its
        counts, the options it echoed and the temporal assertions it says it
        checked. ``problem`` is set when the output reports neither or both
        outcomes, or reports a failure without naming it.
    """
    lines = [line.rstrip() for line in stdout.splitlines()]
    nodes = queued = unique = valid = loaded = executed = None
    echo = ""
    checked: list[str] = []
    passed = False
    kinds: list[str] = []
    names: list[str] = []
    for index, line in enumerate(lines):
        if match := _NODES.match(line):
            nodes, queued = int(match[1]), int(match[2])
        elif match := _STATES.match(line):
            valid, unique = int(match[1]), int(match[2])
        elif match := _OPTIONS.match(line):
            echo = match[1]
        elif match := _CHECKING.match(line):
            checked.append(match[1])
        elif match := _TRACE_LOADED.match(line):
            loaded = int(match[1])
        elif match := _TRACE_SHORT.match(line):
            executed = int(match[2])
        elif line == PASS_LINE:
            passed = True
        elif match := _INVARIANT.match(line):
            kinds.append("always")
            names.append(match[1])
        elif match := _TRANSITION.match(line):
            kinds.append("transition")
            names.append(match[1])
        elif line == _UNREACHED:
            kinds.append("exists")
            for later in lines[index + 1 :]:
                if not (unreached := _UNREACHED_NAME.match(later)):
                    break
                names.append(unreached[1])
        elif line == _LIVENESS:
            kinds.append("liveness")
            if index + 1 < len(lines) and (
                live := _LIVENESS_NAME.match(lines[index + 1])
            ):
                names.append(live[1])
        elif line == _BARE_FAILURE:
            kinds.append("deadlock" if _DEADLOCK in lines[:index] else "unnamed")
        elif line.startswith("FAILED"):
            kinds.append("unknown")
    facts = {
        "nodes": nodes,
        "queued": queued,
        "unique_states": unique,
        "valid_nodes": valid,
        "options_echo": echo,
        "checked_temporal": tuple(checked),
        "trace_loaded": loaded,
        "trace_executed": executed,
    }
    if passed and kinds:
        return Reading(problem="output reports both a pass and a failure", **facts)
    if passed:
        return Reading(passed=True, **facts)
    if executed is not None and not kinds:
        return Reading(failure_kind="blocked", **facts)
    if len(kinds) != 1 or kinds[0] in ("unknown", "unnamed"):
        return Reading(
            problem="output reports no recognized pass or failure", **facts
        )
    if kinds[0] != "deadlock" and not names:
        return Reading(problem="a failure names no assertion", **facts)
    return Reading(failure_kind=kinds[0], failed_assertions=tuple(names), **facts)


def _echo_disagreement(echo: str, options: Mapping[str, object]) -> str:
    """Return how the echoed options differ from the requested ones, if at all.

    The checker prints protobuf text, whose spacing is deliberately unstable,
    so each field is matched on its own.
    """
    wanted = {
        "max_actions": str(options["max_actions"]),
        "max_concurrent_actions": str(options["max_concurrent_actions"]),
        "crash_on_yield": str(options["crash_on_yield"]).lower(),
        "deadlock_detection": str(options["deadlock_detection"]).lower(),
        "liveness": f'"{options["liveness"]}"',
    }
    for name, value in wanted.items():
        found = re.search(rf"\b{name}:\s*(\"[^\"]*\"|\w+)", echo)
        if found is None or found[1] != value:
            return f"the checker did not echo {name}:{value}"
    return ""


def judge(run: Run, result: ProcessResult, spec_text: str) -> tuple[bool, str, str, Reading]:
    """Judge one invocation against its run's expectation.

    Parameters
    ----------
    run : Run
        The run and the outcome it must have.
    result : ProcessResult
        What the process boundary observed.
    spec_text : str
        The specification as it was checked, after any mutation.

    Returns
    -------
    tuple of (bool, str, str, Reading)
        Whether the run met its expectation, a one-word status, the reason,
        and the facts read from the output.
    """
    reading = read_output(result.stdout)
    if result.timed_out:
        return False, "inconclusive", (
            f"the checker did not finish within {run.timeout_seconds}s"
        ), reading
    if result.exit_code is None:
        return False, "interrupted", "the checker was stopped by a signal", reading
    if result.exit_code != 0:
        last = (result.stderr.strip() or result.stdout.strip() or "no output")
        return False, "error", (
            f"the checker exited with status {result.exit_code}:"
            f" {last.splitlines()[-1]}"
        ), reading
    if reading.problem:
        return False, "unrecognized", reading.problem, reading
    if run.trace:
        return _judge_trace(run, reading)
    if reading.failure_kind == "blocked" or reading.trace_loaded is not None:
        return False, "unrecognized", "trace output from an exploration", reading
    if disagreement := _echo_disagreement(reading.options_echo, run.options):
        return False, "misconfigured", disagreement, reading
    if run.expectation.passes:
        return _judge_pass(run, reading, spec_text)
    return _judge_failure(run, reading)


def _judge_trace(run: Run, reading: Reading) -> tuple[bool, str, str, Reading]:
    """Judge a replayed event sequence: run to its end, or refused where stated.

    The pinned checker stops a replay at a step the model does not enable or
    that would break an assertion. It warns, with the number of steps it
    executed, when it stops early, but it prints its pass line with no
    warning when the step it could not take was the last one. The executed
    count is therefore taken from the nodes it reports, one for the initial
    state and one per step, and the warning is only a cross-check. A replay
    explores nothing else, so this is evidence about one sequence only.
    """
    steps = len(run.trace)
    if reading.trace_loaded != steps:
        return False, "unrecognized", (
            f"the checker loaded {reading.trace_loaded} trace steps, not {steps}"
        ), reading
    executed = reading.trace_executed
    if reading.passed:
        if reading.valid_nodes is None or executed is not None:
            return False, "unrecognized", "a replay without a usable step count", reading
        executed = reading.valid_nodes - 1
    if executed is None or not 0 <= executed <= steps:
        return False, "unrecognized", "a replay without a usable step count", reading
    if run.expectation.passes:
        if executed == steps:
            return True, "replayed", f"all {steps} steps are a behaviour", reading
        return False, "refused", (
            f"the model refused the trace after {executed} of {steps} steps"
        ), reading
    if executed == steps:
        return False, "undetected", (
            f"expected {run.expectation.describe()}; the trace ran to its end"
        ), reading
    if executed != run.expectation.executed:
        return False, "wrong-failure", (
            f"expected {run.expectation.describe()}; refused after {executed}"
        ), reading
    return True, "refused-as-expected", run.expectation.describe(), reading


def _judge_pass(run: Run, reading: Reading, spec_text: str) -> tuple[bool, str, str, Reading]:
    """Judge a run that must pass, exhaustively and with liveness checked."""
    if not reading.passed:
        named = ", ".join(reading.failed_assertions) or reading.failure_kind
        return False, "failed", (
            f"expected a pass; the checker reports {reading.failure_kind}: {named}"
        ), reading
    if reading.nodes is None or reading.queued is None or reading.unique_states is None:
        return False, "unrecognized", "a pass without state counts", reading
    if reading.queued != 0:
        return False, "inconclusive", (
            f"{reading.queued} nodes were still queued"
        ), reading
    bound = run.options["max_actions"]
    if reading.nodes >= bound:
        return False, "inconclusive", (
            f"{reading.nodes} nodes reached the max_actions bound of {bound};"
            " exploration may have been cut short"
        ), reading
    missing = sorted(set(_TEMPORAL.findall(spec_text)) - set(reading.checked_temporal))
    if missing:
        return False, "unchecked", (
            "the checker did not report checking: " + ", ".join(missing)
        ), reading
    return True, "passed", "exhaustive", reading


def _judge_failure(run: Run, reading: Reading) -> tuple[bool, str, str, Reading]:
    """Judge a run that must fail one named assertion and no other."""
    expected = run.expectation
    if reading.passed:
        return False, "undetected", (
            f"expected {expected.describe()}; the checker passed"
        ), reading
    if reading.failure_kind != expected.kind:
        named = ", ".join(reading.failed_assertions) or "no assertion"
        return False, "wrong-failure", (
            f"expected {expected.describe()}; got {reading.failure_kind}: {named}"
        ), reading
    if expected.kind != "deadlock" and reading.failed_assertions != (expected.assertion,):
        return False, "wrong-failure", (
            f"expected {expected.describe()}; got {reading.failure_kind}:"
            f" {', '.join(reading.failed_assertions)}"
        ), reading
    return True, "failed-as-expected", expected.describe(), reading


def missing_steps(expected: Expectation, trace: Sequence[str]) -> list[str]:
    """Return the `via` steps the counterexample does not pass through.

    A control fails for its intended reason only when its counterexample
    uses the behaviour the control was written about: the reply shape it
    names, or the environment event it names.
    """
    return [step for step in expected.via if step not in trace]


def _trace(output: Path) -> tuple[str, ...]:
    """Return the action names of the checker's error trace, if it wrote one."""
    graph = output / "error-graph.json"
    if not graph.is_file():
        return ()
    try:
        steps = json.loads(graph.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ()
    if not isinstance(steps, list):
        return ()
    names = []
    for step in steps:
        name = step.get("Name") if isinstance(step, dict) else None
        if isinstance(name, str) and name:
            # The scenario choice in Init prints the whole record; one word
            # says as much.
            names.append("Any:cfg" if name.startswith("Any:cfg=") else name)
    return tuple(names)


def execute(run: Run, suite: Suite, fizz: Path, work: Path, runner: Runner) -> Outcome:
    """Prepare, run and judge one run in its own working directory.

    Parameters
    ----------
    run : Run
        The run to execute.
    suite : Suite
        Supplies the directory specifications are read from.
    fizz : Path
        The verified checker launcher.
    work : Path
        A directory for this run alone. The checker writes beside the
        specification it is given, so the specification is copied here and
        the source tree is never written to.
    runner : Runner
        The process boundary.

    Returns
    -------
    Outcome
        The judgement, its facts, and the artefacts kept for inspection.

    Raises
    ------
    ModelCheckError
        Raised when the specification is unreadable or a mutation anchor
        does not match exactly once.
    """
    source = suite.directory / run.spec
    try:
        original = source.read_text(encoding="utf-8")
    except OSError as error:
        raise ModelCheckError(f"run `{run.id}`: cannot read {source}: {error}") from error
    text = mutate(original, run.mutations, run.id)
    work.mkdir(parents=True, exist_ok=True)
    (work / "spec.fizz").write_text(text, encoding="utf-8")
    (work / "fizz.yaml").write_text(render_options(run.options), encoding="utf-8")
    command = [str(fizz), "--test", "--output-dir", "out"]
    if run.scenario.strip():
        (work / "scenario.cfg").write_text(run.scenario, encoding="utf-8")
        command += ["--preinit-hook-file", "scenario.cfg"]
    if run.trace:
        (work / "replay.txt").write_text("\n".join(run.trace) + "\n", encoding="utf-8")
        command += ["--trace-file", "replay.txt"]
    command.append("spec.fizz")
    result = runner(command, work, run.timeout_seconds)
    (work / "stdout.txt").write_text(result.stdout, encoding="utf-8")
    (work / "stderr.txt").write_text(result.stderr, encoding="utf-8")
    ok, status, detail, reading = judge(run, result, text)
    trace = _trace(work / "out")
    if trace:
        (work / "trace.txt").write_text("\n".join(trace) + "\n", encoding="utf-8")
    if ok and (absent := missing_steps(run.expectation, trace)):
        ok, status = False, "wrong-reason"
        detail = "the counterexample does not pass through: " + ", ".join(absent)
    return Outcome(
        run=run,
        ok=ok,
        status=status,
        detail=detail,
        reading=reading,
        seconds=result.seconds,
        spec_sha256=hashlib.sha256(original.encode("utf-8")).hexdigest(),
        command=tuple(command),
        trace=trace,
        artefacts={"directory": str(work)},
    )


def select(suite: Suite, tier: str, only: Sequence[str] = ()) -> tuple[Run, ...]:
    """Return the runs a tier covers, or a named subset of them.

    Parameters
    ----------
    suite : Suite
        The loaded suite.
    tier : str
        ``routine`` selects the mandatory runs. ``extended`` selects every
        run, so the larger exploration includes the mandatory one and can
        never be run in its place.
    only : sequence of str, optional
        Run identifiers to restrict the selection to. A negative control
        brings its twin with it.

    Returns
    -------
    tuple of Run
        The selected runs in manifest order.

    Raises
    ------
    ModelCheckError
        Raised for an unknown tier or run identifier.
    """
    if tier not in TIERS:
        raise ModelCheckError(f"unknown tier `{tier}`; known tiers: {', '.join(TIERS)}")
    chosen = [
        run for run in suite.runs if TIERS.index(run.tier) <= TIERS.index(tier)
    ]
    if not only:
        return tuple(chosen)
    known = {run.id: run for run in chosen}
    unknown = sorted(set(only) - set(known))
    if unknown:
        raise ModelCheckError(
            f"no such run in tier `{tier}`: {', '.join(unknown)}"
        )
    wanted = set(only) | {known[name].of for name in only if known[name].of}
    return tuple(run for run in chosen if run.id in wanted)


def unknown_assertions(suite: Suite) -> list[str]:
    """Return expectations naming an assertion its specification lacks.

    A control that expects a misspelt assertion could only ever fail, but it
    would fail as "wrong failure" after a full run; this reports it first.
    """
    problems = []
    declared: dict[str, set[str]] = {}
    for run in suite.runs:
        if run.expectation.passes or run.expectation.kind in ("deadlock", "blocked"):
            continue
        if run.spec not in declared:
            try:
                text = (suite.directory / run.spec).read_text(encoding="utf-8")
            except OSError:
                text = ""
            declared[run.spec] = set(_ASSERTION.findall(text))
        if run.expectation.assertion not in declared[run.spec]:
            problems.append(
                f"run `{run.id}` expects `{run.expectation.assertion}`, which"
                f" {run.spec} does not declare"
            )
    return problems


def report(suite: Suite, outcomes: Sequence[Outcome], *, tier: str, partial: bool) -> dict:
    """Return the run metadata as a JSON-serializable report.

    Parameters
    ----------
    suite : Suite
        The suite that was run.
    outcomes : sequence of Outcome
        One judgement per executed run.
    tier : str
        The tier that was selected.
    partial : bool
        Whether a named subset was run, which is never a gate result.

    Returns
    -------
    dict
        Checker identity, selection, completion status and per-run facts.
    """
    return {
        "checker": {
            "name": "FizzBee",
            "version": suite.checker.version,
            "archive_sha256": suite.checker.archive_sha256,
        },
        "suite": str(suite.path),
        "tier": tier,
        "partial": partial,
        "exploration": "exhaustive breadth-first search of a finite model",
        "ok": bool(outcomes) and all(outcome.ok for outcome in outcomes),
        "runs": [
            {
                "id": outcome.run.id,
                "class": outcome.run.kind,
                "tier": outcome.run.tier,
                "spec": outcome.run.spec,
                "spec_sha256": outcome.spec_sha256,
                "mutated": bool(outcome.run.mutations),
                "replayed_steps": len(outcome.run.trace),
                "options": dict(outcome.run.options),
                "command": list(outcome.command),
                "expected": outcome.run.expectation.describe(),
                "status": outcome.status,
                "ok": outcome.ok,
                "detail": outcome.detail,
                "nodes": outcome.reading.nodes,
                "queued": outcome.reading.queued,
                "unique_states": outcome.reading.unique_states,
                "temporal_checked": list(outcome.reading.checked_temporal),
                "seconds": round(outcome.seconds, 2),
                "obligations": list(outcome.run.obligations),
                "trace": list(outcome.trace),
            }
            for outcome in outcomes
        ],
    }


def summarize(outcomes: Sequence[Outcome], *, partial: bool) -> str:
    """Return the human-readable summary, one section per run class.

    Expected counterexamples are listed under their own heading so that a
    recorded limitation is never read as a passing assurance claim.
    """
    headings = {
        "assurance": "Assurance (must pass)",
        "negative-control": "Negative controls (a mutation must fail its assertion)",
        "property-control": "Property controls (the assertion must be able to fail)",
        "expected-counterexample": (
            "Expected counterexamples (recorded limitations, not assurance)"
        ),
        "scenario-trace": "Scenario traces (one named event sequence each)",
    }
    lines: list[str] = []
    for kind in CLASSES:
        group = [outcome for outcome in outcomes if outcome.run.kind == kind]
        if not group:
            continue
        lines.append(headings[kind])
        for outcome in group:
            mark = "ok  " if outcome.ok else "FAIL"
            counts = ""
            if outcome.reading.unique_states is not None:
                counts = (
                    f" [{outcome.reading.unique_states} states,"
                    f" {outcome.seconds:.1f}s]"
                )
            lines.append(
                f"  {mark} {outcome.run.id}: {outcome.status}"
                f" ({outcome.detail}){counts}"
            )
            if not outcome.ok and outcome.trace:
                lines.append("       trace: " + " -> ".join(outcome.trace))
                lines.append(f"       kept in {outcome.artefacts['directory']}")
    failed = [outcome for outcome in outcomes if not outcome.ok]
    if partial:
        lines.append("PARTIAL: a named subset was run; this is not a gate result.")
    if failed or not outcomes:
        lines.append(f"model-check: FAILED ({len(failed)} of {len(outcomes)} runs)")
    else:
        lines.append(f"model-check: {len(outcomes)} runs met their expectations")
    return "\n".join(lines)
