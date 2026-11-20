"""Load and validate a model-checking suite manifest.

A suite is a TOML manifest beside its specifications. It pins one checker
release by digest and lists runs; ``model_check`` describes what each run
class is evidence of. This module turns the manifest into frozen records and
refuses any manifest that could make a run test less than it says: an unknown
key, an unstated or relaxed checker option, a class paired with a mutation or
expectation it cannot have, or a negative control without its twin.

Nothing here runs the checker. ``model_check_judge`` reads its output and
``model_check`` executes runs; this module is shared by both.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
import re
import tomllib

#: Tiers a run may belong to. The mandatory gate runs ``routine`` only, and a
#: larger exploration never stands in for it.
TIERS = ("routine", "extended")

#: What a run is evidence of; see the ``model_check`` module docstring.
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

#: Options with exactly one permitted value, and why. Either relaxation would
#: let a run pass without checking what the suite says it checks, and the
#: pinned release would not report the difference.
_FIXED_OPTIONS = {
    "liveness": ("strict", 'must set liveness = "strict"'),
    "deadlock_detection": (True, "must not disable deadlock detection"),
    "crash_on_yield": (
        False,
        "must set crash_on_yield = false; interruption is modelled by an"
        " explicit action",
    ),
}

#: Options that bound the search and must be positive integers.
_COUNT_OPTIONS = ("max_actions", "max_concurrent_actions")

#: Every key a run table may carry.
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

#: Run identifiers name run directories beside the suite's ``report.json``.
_RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
_RESERVED_IDS = ("report.json",)

#: Matches the declaration of any action in a specification.
ACTION = re.compile(r"^(?:atomic |serial )?(?:fair(?:<\w+>)? )?action (\w+)\s*:", re.MULTILINE)

#: Matches the declaration of any assertion in a specification.
ASSERTION = re.compile(
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
        described = {
            "deadlock": "fail: deadlock",
            "blocked": f"refused after {self.executed} steps",
        }
        return described.get(self.kind, f"fail: {self.kind} {self.assertion}")


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
class _Shape:
    """What a run of one class is: mutated or not, passing or not, replayed.

    ``passes`` is ``None`` for a class that may either pass or fail.
    """

    mutated: bool
    passes: bool | None
    traced: bool
    rule: str


#: The shape each class must have, and the sentence that states it.
_SHAPES = {
    "assurance": _Shape(False, True, False, "an assurance run is unmutated and passes"),
    "negative-control": _Shape(
        True, False, False, "a negative control mutates the specification and fails"
    ),
    "property-control": _Shape(
        False, False, False, "a property-control run is unmutated and expected to fail"
    ),
    "expected-counterexample": _Shape(
        False,
        False,
        False,
        "an expected-counterexample run is unmutated and expected to fail",
    ),
    "scenario-trace": _Shape(
        False, None, True, "a scenario trace replays the real model"
    ),
}


def _require(holds: bool, message: str) -> None:
    """Refuse the manifest with ``message`` unless ``holds``."""
    if not holds:
        raise ModelCheckError(message)


def _table(value: object, where: str) -> Mapping[str, object]:
    """Return ``value`` as a TOML table, or refuse a manifest of another shape."""
    _require(isinstance(value, dict), f"{where} must be a table")
    return value  # type: ignore[return-value]


def _text(table: Mapping[str, object], key: str, where: str) -> str:
    """Return a required non-empty string field."""
    value = table.get(key)
    _require(
        isinstance(value, str) and bool(value.strip()),
        f"{where} needs a non-empty string `{key}`",
    )
    return str(value)


def _strings(value: object) -> bool:
    """Return whether ``value`` is a list of non-empty strings."""
    return isinstance(value, list) and all(
        isinstance(item, str) and item.strip() for item in value
    )


def _positive_int(value: object) -> bool:
    """Return whether ``value`` is an ``int``, not a ``bool``, above zero."""
    return type(value) is int and value > 0


def _same(value: object, wanted: object) -> bool:
    """Return whether ``value`` equals ``wanted`` and has its exact type.

    ``True == 1`` in Python, so equality alone would accept ``1`` for a
    Boolean option the release reads differently.
    """
    return type(value) is type(wanted) and value == wanted


def _only(table: Mapping[str, object], allowed: Sequence[str], where: str) -> None:
    """Refuse a key the manifest format does not define.

    A misspelt key would otherwise be ignored, and a run would silently lose
    the mutation or expectation it was written to carry.
    """
    unknown = sorted(set(table) - set(allowed))
    _require(not unknown, f"{where} has unknown keys: {', '.join(unknown)}")


def _checker(table: Mapping[str, object]) -> Checker:
    """Build the checker pin from its manifest table."""
    _only(table, ("version", "url", "sha256", "root", "files"), "[checker]")
    files = _table(table.get("files"), "[checker.files]")
    _require(
        bool(files) and all(isinstance(value, str) for value in files.values()),
        "[checker.files] must map each file to its SHA-256",
    )
    return Checker(
        version=_text(table, "version", "[checker]"),
        url=_text(table, "url", "[checker]"),
        archive_sha256=_text(table, "sha256", "[checker]"),
        root=_text(table, "root", "[checker]"),
        files={str(name): str(value) for name, value in files.items()},
    )


def _blocked(table: Mapping[str, object], via: tuple[str, ...], where: str) -> Expectation:
    """Build a refused-trace expectation, which states only the steps run."""
    executed = table.get("executed")
    _require(
        type(executed) is int and executed >= 0,
        f"{where}: a refused trace states only the steps `executed`",
    )
    _require(
        "assertion" not in table and not via,
        f"{where}: a refused trace states only the steps `executed`",
    )
    return Expectation(passes=False, kind="blocked", executed=int(executed))  # type: ignore[arg-type]


def _deadlock(table: Mapping[str, object], via: tuple[str, ...], where: str) -> Expectation:
    """Build a deadlock expectation, which names no assertion."""
    _require("assertion" not in table, f"{where}: a deadlock names no assertion")
    return Expectation(passes=False, kind="deadlock", via=via)


def _named(kind: str, table: Mapping[str, object], via: tuple[str, ...], where: str) -> Expectation:
    """Build an expectation that one named assertion fails."""
    _require(
        kind != "exists" or not via,
        f"{where}: an unreached state has no trace to check",
    )
    return Expectation(
        passes=False, kind=kind, assertion=_text(table, "assertion", where), via=via
    )


def _expectation(value: object, where: str) -> Expectation:
    """Parse ``expect``: the string ``pass`` or a failure table."""
    if value == "pass":
        return Expectation(passes=True)
    table = _table(value, f"{where} expect")
    _only(table, ("fail", "assertion", "via", "executed"), f"{where} expect")
    kind = _text(table, "fail", f"{where} expect")
    _require(
        kind in FAILURE_KINDS,
        f"{where} expects an unknown failure kind `{kind}`;"
        f" known kinds: {', '.join(FAILURE_KINDS)}",
    )
    via = table.get("via", [])
    _require(_strings(via), f"{where} expect `via` must be a list of trace steps")
    steps = tuple(via)  # type: ignore[arg-type]
    if kind == "blocked":
        return _blocked(table, steps, where)
    _require("executed" not in table, f"{where}: only a refused trace states `executed`")
    if kind == "deadlock":
        return _deadlock(table, steps, where)
    return _named(kind, table, steps, where)


def _mutation(entry: object, where: str) -> tuple[str, str]:
    """Parse one ``[[run.mutation]]`` table into ``(old, new)``."""
    table = _table(entry, f"{where} mutation")
    _only(table, ("old", "new"), f"{where} mutation")
    new = table.get("new")
    _require(isinstance(new, str), f"{where} mutation needs a string `new`")
    return _text(table, "old", f"{where} mutation"), str(new)


def _mutations(value: object, where: str) -> tuple[tuple[str, str], ...]:
    """Parse the ``[[run.mutation]]`` tables of one run."""
    if value is None:
        return ()
    _require(isinstance(value, list), f"{where} mutation must be an array of tables")
    return tuple(_mutation(entry, where) for entry in value)  # type: ignore[union-attr]


def _options(
    defaults: Mapping[str, object], overrides: Mapping[str, object], where: str
) -> Mapping[str, object]:
    """Merge and validate checker options; every option must be stated."""
    merged = {**defaults, **overrides}
    _only(merged, REQUIRED_OPTIONS, f"{where} options")
    missing = [name for name in REQUIRED_OPTIONS if name not in merged]
    _require(not missing, f"{where} leaves options unstated: {', '.join(missing)}")
    for name, (wanted, rule) in _FIXED_OPTIONS.items():
        _require(_same(merged[name], wanted), f"{where} {rule}")
    for name in _COUNT_OPTIONS:
        _require(
            _positive_int(merged[name]),
            f"{where} option `{name}` must be a positive integer",
        )
    return merged


def _member(value: str, key: str, allowed: Sequence[str], where: str) -> str:
    """Return ``value`` when it is one of ``allowed``, naming ``key`` if not."""
    _require(value in allowed, f"{where} has unknown {key} `{value}`")
    return value


def _run_id(table: Mapping[str, object]) -> str:
    """Return a run's identifier, which becomes a directory name.

    It must be one plain path component, and it may not be a name the suite
    report itself uses, or a run directory and the report would collide
    after the checker had already run.
    """
    identifier = _text(table, "id", "a run")
    _require(
        _RUN_ID.fullmatch(identifier) is not None and identifier not in _RESERVED_IDS,
        f"run id `{identifier}` must be one plain path component other than"
        f" {', '.join(_RESERVED_IDS)}",
    )
    return identifier


def _run(
    table: Mapping[str, object],
    defaults: Mapping[str, object],
    default_options: Mapping[str, object],
) -> Run:
    """Build one run from its manifest table and the suite defaults.

    A negative control's options are not validated here: it takes its
    twin's, which ``_resolve`` copies and which were validated as the
    twin's own. Validating the control against the defaults alone would
    refuse a control whose twin states options the defaults do not.
    """
    where = f"run `{table.get('id', '?')}`"
    _only(table, _RUN_KEYS, where)
    kind = _member(_text(table, "class", where), "class", CLASSES, where)
    overrides = _table(table.get("options", {}), where)
    obligations = table.get("obligations", [])
    _require(_strings(obligations), f"{where} obligations must be a list of strings")
    timeout = table.get("timeout_seconds", defaults.get("timeout_seconds"))
    _require(_positive_int(timeout), f"{where} needs a positive integer timeout_seconds")
    scenario = table.get("scenario", "")
    _require(isinstance(scenario, str), f"{where} scenario must be a string")
    trace = table.get("trace", [])
    _require(_strings(trace), f"{where} trace must be a list of non-empty steps")
    return Run(
        id=_run_id(table),
        tier=_member(str(table.get("tier", "routine")), "tier", TIERS, where),
        kind=kind,
        purpose=_text(table, "purpose", where),
        spec=str(table.get("spec", defaults.get("spec", ""))),
        options={}
        if kind == "negative-control"
        else _options(default_options, overrides, where),
        scenario=str(scenario),
        mutations=_mutations(table.get("mutation"), where),
        expectation=_expectation(table.get("expect"), where),
        obligations=tuple(obligations),  # type: ignore[arg-type]
        timeout_seconds=int(timeout),  # type: ignore[arg-type]
        of=str(table.get("of", "")),
        trace=tuple(trace),  # type: ignore[arg-type]
    )


def _check_twin(run: Run, by_id: Mapping[str, Run], where: str) -> None:
    """Require a negative control's twin, and nobody else's.

    The twin is the unmutated assurance run whose specification, options and
    scenario the control borrows, so a failure is the mutation's. It must run
    in the same or an earlier tier, or the extended suite could hold a
    control whose twin the routine suite never runs.
    """
    if run.kind != "negative-control":
        _require(not run.of, f"{where}: only a negative control names `of`")
        return
    twin = by_id.get(run.of)
    _require(
        getattr(twin, "kind", None) == "assurance",
        f"{where}: `of` must name the assurance run it mutates",
    )
    _require(
        TIERS.index(twin.tier) <= TIERS.index(run.tier),  # type: ignore[union-attr]
        f"{where}: its twin `{run.of}` must run in the same or an earlier tier",
    )


def _check_shape(run: Run, by_id: Mapping[str, Run]) -> None:
    """Refuse a run whose class, mutation, expectation and trace disagree."""
    where = f"run `{run.id}`"
    shape = _SHAPES[run.kind]
    _require(bool(run.mutations) == shape.mutated, f"{where}: {shape.rule}")
    _require(shape.passes in (None, run.expectation.passes), f"{where}: {shape.rule}")
    _require(
        shape.traced == bool(run.trace),
        f"{where}: a scenario-trace run, and only that class, lists a trace",
    )
    refused = shape.traced and not run.expectation.passes
    _require(
        (run.expectation.kind == "blocked") == refused,
        f"{where}: a scenario trace runs to its end or is refused, and nothing"
        " else is",
    )
    _require(bool(run.spec), f"{where} names no specification")
    _check_twin(run, by_id, where)


def _read(path: Path) -> Mapping[str, object]:
    """Read a manifest's TOML, refusing an unreadable or malformed file."""
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise ModelCheckError(f"cannot read suite {path}: {error}") from error


def _index(runs: Sequence[Run]) -> dict[str, Run]:
    """Return the runs by identifier, refusing a repeated one."""
    by_id: dict[str, Run] = {}
    for run in runs:
        _require(run.id not in by_id, f"run id `{run.id}` is used twice")
        by_id[run.id] = run
    return by_id


def _resolve(table: Mapping[str, object], run: Run, by_id: Mapping[str, Run]) -> Run:
    """Give a negative control its twin's specification, options and scenario.

    The control may state none of them itself: one that did could test a
    configuration its twin was never shown to pass.
    """
    twin = by_id.get(run.of)
    if run.kind != "negative-control" or twin is None:
        return run
    _require(
        not {"spec", "options", "scenario"} & set(table),
        f"run `{run.id}`: a negative control takes its specification, options"
        " and scenario from its twin and may state none",
    )
    return replace(run, spec=twin.spec, options=twin.options, scenario=twin.scenario)


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
    data = _read(path)
    _only(data, ("checker", "defaults", "run"), "the suite")
    defaults = _table(data.get("defaults", {}), "[defaults]")
    _only(defaults, ("spec", "timeout_seconds", "options"), "[defaults]")
    default_options = _table(defaults.get("options", {}), "[defaults.options]")
    tables = data.get("run")
    _require(isinstance(tables, list) and bool(tables), "the suite lists no runs")
    parsed = [_table(table, "a run") for table in tables]  # type: ignore[union-attr]
    runs = [_run(table, defaults, default_options) for table in parsed]
    by_id = _index(runs)
    resolved = [_resolve(table, run, by_id) for table, run in zip(parsed, runs, strict=True)]
    for run in resolved:
        _check_shape(run, by_id)
    checker = _checker(_table(data.get("checker"), "[checker]"))
    return Suite(path=path, checker=checker, runs=tuple(resolved))


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
    _require(tier in TIERS, f"unknown tier `{tier}`; known tiers: {', '.join(TIERS)}")
    chosen = [run for run in suite.runs if TIERS.index(run.tier) <= TIERS.index(tier)]
    return tuple(chosen) if not only else _named_subset(chosen, only, tier)


def _named_subset(chosen: Sequence[Run], only: Sequence[str], tier: str) -> tuple[Run, ...]:
    """Return the named runs of a tier, each control with its twin."""
    known = {run.id: run for run in chosen}
    unknown = sorted(set(only) - set(known))
    _require(not unknown, f"no such run in tier `{tier}`: {', '.join(unknown)}")
    twins = {known[name].of for name in only} - {""}
    wanted = set(only) | twins
    return tuple(run for run in chosen if run.id in wanted)


def _source(suite: Suite, spec: str) -> str:
    """Return one specification's text, refusing one that cannot be read.

    An unreadable specification is a broken suite, not one that declares
    nothing: reading it as empty would report every expectation as naming an
    undeclared assertion and hide the actual fault.
    """
    path = suite.directory / spec
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise ModelCheckError(f"cannot read specification {path}: {error}") from error


def _declared(suite: Suite, spec: str) -> set[str]:
    """Return the assertions one specification declares."""
    return set(ASSERTION.findall(_source(suite, spec)))


def unknown_assertions(suite: Suite) -> list[str]:
    """Return expectations naming an assertion its specification lacks.

    A control that expects a misspelt assertion could only ever fail, but it
    would fail as "wrong failure" after a full run; this reports it first.
    """
    named = [run for run in suite.runs if run.expectation.assertion]
    declared = {spec: _declared(suite, spec) for spec in {run.spec for run in named}}
    return [
        f"run `{run.id}` expects `{run.expectation.assertion}`, which"
        f" {run.spec} does not declare"
        for run in named
        if run.expectation.assertion not in declared[run.spec]
    ]


def _undeclared_steps(run: Run, actions: set[str]) -> list[str]:
    """Return the action steps of a trace its specification does not declare.

    Choice lines (``Any:...``) name values, not actions, and are left to the
    checker.
    """
    return [step for step in run.trace if not step.startswith("Any:") and step not in actions]


def unknown_trace_steps(suite: Suite) -> list[str]:
    """Return trace steps naming an action their specification lacks.

    The pinned checker stops a replay at the first step it cannot match,
    whether the action is misspelt or merely disabled, and reports both the
    same way. A refused trace must be refused by the model, so every step,
    including the one expected to be refused, must name a declared action.
    """
    traced = [run for run in suite.runs if run.trace]
    actions = {
        spec: set(ACTION.findall(_source(suite, spec)))
        for spec in {run.spec for run in traced}
    }
    return [
        f"run `{run.id}` replays `{step}`, which {run.spec} does not declare"
        for run in traced
        for step in _undeclared_steps(run, actions[run.spec])
    ]
