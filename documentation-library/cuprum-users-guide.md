# cuprum Users' Guide

## Program catalogue

Cuprum exposes a typed `Program` NewType to identify executables. The library
ships with a curated catalogue (`DEFAULT_CATALOGUE`) that defines an allowlist
of programs and project metadata. Requests for unknown executables raise
`UnknownProgramError` so accidental shell access is blocked by default.

- Import curated programs from `cuprum` (for example `ECHO`, `LS`).
- Each project in the catalogue includes `noise_rules` (output lines that
  downstream loggers can safely drop) and `documentation_locations` (links for
  operators and reviewers).

```python
from cuprum import DEFAULT_CATALOGUE, ECHO

entry = DEFAULT_CATALOGUE.lookup(ECHO)
print(entry.project.noise_rules)
```

### Adding project-specific programs

Use `ProjectSettings` and `ProgramCatalogue` to extend or replace the default
catalogue:

```python
from cuprum import Program, ProgramCatalogue, ProjectSettings

project = ProjectSettings(
    name="data-pipeline",
    programs=(Program("python"),),
    documentation_locations=("docs/pipelines.md",),
    noise_rules=(r"^progress:",),
)
catalogue = ProgramCatalogue(projects=(project,))
```

Downstream services can fetch metadata via the `catalogue.visible_settings`
property to propagate noise filters and documentation links alongside the
allowlist. It returns a cached, read-only mapping from project name to
`ProjectSettings`.

Callers upgrading from a release that exposed `visible_settings()` should
remove the parentheses and adopt `catalogue.visible_settings` in the next minor
release. The callable form remains a compatibility path during the transition;
both forms return the same read-only mapping, and attempts to mutate it fail as
before.

### Handling duplicate catalogue entries

Catalogue construction rejects ambiguous project metadata before any command is
built. If two project entries use the same name, `ProgramCatalogue` raises
`DuplicateProjectError`; the exception carries the duplicated name in its
`project_name` attribute. If two projects claim the same `Program`, catalogue
construction raises `DuplicateProgramError`; the exception carries the contested
`program` and the first owning project name in `owner`.

Both duplicate exceptions subclass `ValueError`, so existing configuration
loading code that catches `ValueError` continues to work while newer callers
can inspect the structured payloads directly.

## Typed command core

Cuprum provides `sh.make` to build typed `SafeCmd` instances from curated
programs. Builders enforce the catalogue allowlist up front and carry project
metadata alongside argv, so downstream services can apply noise rules or link
to documentation without a second lookup.

- `sh.make` raises `UnknownProgramError` when the program is not in the current
  catalogue.
- Positional arguments are stringified with `str()`.
- Keyword arguments become `--flag=value` entries with underscores in flag
  names converted to hyphens.
- `None` is rejected; decide whether to skip or substitute a flag before
  calling the builder.

```python
from cuprum import ECHO, sh

echo = sh.make(ECHO)
cmd = echo("-n", "hello world")
print(cmd.argv_with_program)  # ('echo', '-n', 'hello world')
print(cmd.project.noise_rules)  # metadata for downstream loggers
```

### Writing project-specific builders

Wrap `sh.make` in project modules to centralize validation and expose a clear
API for callers:

```python
from pathlib import Path

from cuprum import Program, SafeCmd, sh

SAFE_CAT = Program("cat")


def _safe_path(path: Path) -> str:
    path = path.resolve()
    if not path.is_file():
        msg = f"{path} is not a readable file"
        raise ValueError(msg)
    return path.as_posix()


def cat_file(path: Path, numbered: bool = False) -> SafeCmd:
    args: list[str] = []
    if numbered:
        args.append("-n")
    args.append(_safe_path(path))
    return sh.make(SAFE_CAT)(*args)
```

Builders keep argv construction in one place, making it easier to validate
inputs, document behaviour, and reuse the same allowlisted program across a
codebase.

### Inspecting argv construction

Use `sh.build_argv` when code needs to inspect Cuprum's argument normalization
without creating a command builder or consulting a catalogue. The helper uses
the same argument rules as `sh.make`: positional arguments are stringified in
order, keyword arguments become `--flag=value` entries, underscores in keyword
names become hyphens, and `None` raises `TypeError`.

```python
from cuprum import sh

argv = sh.build_argv("status", porcelain=True, branch="main")
print(argv)  # ('status', '--porcelain=True', '--branch=main')
```

### Core builders for common tools

Cuprum ships a small builder library for common tools in `cuprum.builders`.
These builders are optional but provide a consistent, typed entry point for
git, rsync, and tar commands.

The library includes typed argument helpers:

- `safe_path()` produces a `SafePath` by validating filesystem paths. It
  rejects empty strings, NUL characters, and `..` segments. By default it
  requires absolute paths; set `allow_relative=True` to permit relative paths.
- `git_ref()` produces a `GitRef` by validating git ref names. It rejects
  whitespace, leading `-`, `..`, `//`, `@{`, trailing `.lock`, trailing `.`,
  and refs with characters outside `[A-Za-z0-9._/-]`.

Builder functions validate inputs internally, so callers may pass `str` or
`Path` values directly, or call the helper functions for explicitness.

```python
from pathlib import Path

from cuprum.builders import (
    Compression,
    RsyncOptions,
    TarCreateOptions,
    git_checkout,
    rsync_sync,
    tar_create,
    tar_extract,
)

git_cmd = git_checkout("main", create_branch=True)
rsync_cmd = rsync_sync(
    Path("/srv/data"),
    Path("/backups/data"),
    options=RsyncOptions(archive=True, delete=True),
)
tar_cmd = tar_create(
    Path("/backups/data.tar.gz"),
    [Path("/srv/data")],
    options=TarCreateOptions(compression=Compression.GZIP),
)
restore_cmd = tar_extract(
    Path("/backups/data.tar.gz"),
    destination=Path("/srv/restore"),
)
```

Relative paths require `allow_relative=True` on the relevant option objects
(for example, `RsyncOptions`) or using `safe_path(..., allow_relative=True)`
before passing the result into a builder.

## Pipeline execution

Compose `SafeCmd` instances into a `Pipeline` via the `|` operator. Pipelines
stream data from each stage's stdout into the next stage's stdin and apply
backpressure using `asyncio`'s pipe `drain()` semantics.

Running a pipeline returns a `PipelineResult` that exposes:

- The captured output of the final stage (via `result.stdout`).
- Per-stage exit metadata (via `result.stages`).

```python
import sys
from pathlib import Path

from cuprum import (
    ECHO,
    Program,
    ProgramCatalogue,
    ProjectSettings,
    ScopeConfig,
    scoped,
    sh,
)

PYTHON = Program(str(Path(sys.executable)))
project = ProjectSettings(
    name="pipeline-example",
    programs=(ECHO, PYTHON),
    documentation_locations=(),
    noise_rules=(),
)
catalogue = ProgramCatalogue(projects=(project,))

echo = sh.make(ECHO, catalogue=catalogue)
python = sh.make(PYTHON, catalogue=catalogue)

pipeline = echo("-n", "hello") | python(
    "-c",
    "import sys; sys.stdout.write(sys.stdin.read().upper())",
)

with scoped(ScopeConfig(allowlist=catalogue.allowlist)):
    result = pipeline.run_sync()

print(result.stdout)  # "HELLO"
print([stage.exit_code for stage in result.stages])  # per-stage exit codes
```

Notes:

- Only the final stage's stdout is captured; intermediate stage stdout is
  streamed and represented as `None` in `result.stages`.
- `Pipeline.run` / `run_sync` accept the same `output: RunOutputOptions`
  parameter as `SafeCmd.run` / `run_sync`, so generic helpers can call either
  type with one convention. The flat `capture` / `echo` keyword arguments are
  deprecated and emit a `DeprecationWarning`.
- `RunOutputOptions(echo=True)` echoes the final stage stdout and all stage
  stderr streams to their configured sinks.
- Pipelines fail fast on the *first* non-final stage to exit non-zero when at
  least one other stage remains running: that stage terminates every other
  still-running stage — upstream producers as well as downstream consumers, not
  only the stages after the failure. A failing **final** stage or any
  single-stage pipeline does not request fail-fast termination by policy. A
  non-final failure whose potential targets have already settled likewise has
  no targets to terminate. Only the first failure counts, since later non-zero
  exits are usually its consequences. The failing stage is available via
  `result.failure` / `result.failure_index`.
- When a downstream writer closes early, Cuprum drains the upstream reader
  until EOF or a short timeout elapses, even on a stalled upstream, so
  discarded input stays bounded. On the Rust backend that drain is reported —
  see [Rust stream observability](#rust-stream-observability-internal) for the
  `broken pipe; draining reader` event and the `bytes_transferred` count, which
  record *that* the downstream stage stopped reading and how much it received
  first. Neither says why it stopped; read them alongside that stage's exit
  status.

### Diagnosing a fail-fast pipeline

`result.failure_index` reports the index of the stage that failed first, in
completion order — whether or not that failure went on to trigger fail-fast
termination — but not why the other stages ended when they did. When the first
non-final failure still has stages to stop, the wait path publishes one
`pipeline_fail_fast` `ExecEvent` to the registered observe hooks immediately
before termination begins. The wait path also reports three fixed completion
records through the optional pipeline-wait reporter:
`pipeline_stage_first_failure` when the first failure is latched,
`pipeline_fail_fast_termination` before termination starts, and
`pipeline_fail_fast_terminated` with the termination outcome. The optional
pipeline-wait reporter emits these canonical wait records at a fixed WARNING
level on `cuprum._pipeline_wait`. `structured_logging_hook()` separately
renders the `pipeline_fail_fast` `ExecEvent` at `LogLevels.fail_fast_level`.
The latter two records occur only when there are stages to terminate; the
first-failure record still documents a final-stage, single-stage, or
already-settled non-final failure. The closing record's
`cuprum_terminated_stage_count` counts only confirmed process terminations, so
a stage that settles after termination selection is excluded. The
`pipeline_fail_fast` observe event is separate from these records; metrics,
tracing, and `structured_logging_hook()` project that event through the
configurable event adapter channel without requiring log parsing.

The event carries the failing stage's index, pipeline width, exit code,
duration, and execution token. It is sanitized by removing caller-controlled
`argv`, `cwd`, `env`, and `tags`; it retains the runtime fields `program`,
`pid`, `timestamp`, trusted configured project, typed decision fields, and
`ExecEvent.exec_id`. All projections consume this same sanitized event, so they
do not need to parse log text. The metrics adapter labels
`cuprum_pipeline_fail_fast_total` with `program` and `project` alone; `project`
comes from the trusted configured project and falls back to `unknown` only when
absent, and the execution token remains event and trace detail rather than a
metric label. It also distinguishes concurrent pipelines whose stage indices
would otherwise look identical.

`structured_logging_hook()` consumes the event at `LogLevels.fail_fast_level`,
which defaults to `logging.WARNING`. Once that hook is registered, no extra
level configuration is needed for fail-fast records. Its fail-fast projection
deliberately omits `argv` and arbitrary `tags`, so command-line secrets and
user-supplied tag values do not reach the warning record. Other event phases
retain their documented projections; see
[Structured logging adapter](#structured-logging-adapter).

The event fires only when the first non-final failure leaves at least one other
stage running. A final-stage failure, a single-stage pipeline, and a failure
whose sibling stages have all already exited therefore emit no event. The
failure is still latched and reported as `failure_index` in each case; what is
absent is the termination decision because there was nothing left to terminate.
Only the first failure counts, since later non-zero exits are usually the
consequences of the fail-fast decision.

The reported stage follows the order in which the stages actually finished.
When two stages finish too close together for that order to be observed —
because they settled in the same underlying wait batch — the earlier stage in
the pipeline is reported instead, so the reported stage is the upstream cause
rather than a downstream stage it took down with it. That tie-break only
applies within such a batch: across batches, whichever stage genuinely finished
first is the one reported.

## Execution runtime

`SafeCmd.run` executes curated commands asynchronously with predictable capture
and echo semantics and returns a structured `CommandResult`:

- `stdout` and `stderr` are captured by default. Set
  `output=RunOutputOptions(capture=False)` to stream only; the result will carry
  `None` for output fields.
- `output=RunOutputOptions(echo=True)` tees stdout/stderr to the parent process
  while still capturing them when `capture=True`; configured text sinks
  preserve multibyte characters split across subprocess reads.
- Pass an `ExecutionContext` via the `context` parameter to override execution
  details:
  - `env` overlays key/value pairs on top of the current environment without
    mutating `os.environ`; use it to pass per-command settings.
  - `cwd` sets the working directory for the subprocess when provided.
  - `cancel_grace` controls how long Cuprum waits after `SIGTERM` (termination
    signal) before escalating to `SIGKILL` (kill signal).
  - `timeout` sets a default wall-clock limit in seconds when the call does not
    pass an explicit `timeout` parameter.
  - `stdout_sink` and `stderr_sink` route echoed output to alternative text
    streams when `echo=True`.
  - `encoding` and `errors` configure how captured output is decoded; defaults
    are `"utf-8"` with `"replace"`.
    The same settings are used when `StdinInput.text` is encoded for
    subprocess stdin.
- `exit_code`, `pid`, and `ok` on the `CommandResult` make it easy to branch on
  success.

### Output options

`RunOutputOptions` is the public contract for command output handling on
`SafeCmd.run()` and `SafeCmd.run_sync()`. Pass it with the `output` parameter
when a call needs output behaviour that differs from the default.

- `capture=True` stores stdout and stderr on the returned `CommandResult`.
  Set it to `False` when the caller does not need captured output; `stdout` and
  `stderr` will then be `None`.
- `echo=False` keeps output out of the parent process streams. Set it to `True`
  to tee stdout and stderr while the command runs. When `capture=True`, echoed
  output is still captured.

If a text-only echo sink cannot represent the subprocess output (for example a
CP1252 console receiving UTF-8 text), Cuprum no longer aborts the run with
`UnicodeEncodeError`. It disables echoing for only the affected stream
(`stdout` or `stderr` independently), capture continues, and the run returns
its complete captured output. Cuprum logs one `WARNING` on the `cuprum.stream`
logger. A sink exposing a binary buffer still receives the original bytes.

Each first failure on a drain is also published as an opt-in observation for
metrics integrations. Registering `EchoMetricsHook` from
`cuprum.adapters.echo_metrics` with `cuprum.echo_observation.observe_echo`
counts one increment of `cuprum_echo_encoding_failures_total` per affected
stream. The metric carries exactly two labels: `stream`, whose value is
`stdout` or `stderr`, and `error_category`, whose only value is
`unicode_encode`. No subprocess payload, sink type, encoding, exception text,
command, path, PID, or execution identifier becomes a metric label; the
structured `cuprum_*` extras on the `cuprum.stream` warning carry that
diagnostic detail instead. The hook is opt-in: without it, no observation is
emitted and no telemetry dependency is added. A failing metrics collector is
reported and skipped rather than changing the run's capture behaviour.

`RunOutputOptions(capture=True, echo=False)` is the default; you only need to
supply it explicitly when overriding either flag.

```python
from cuprum import ECHO, ExecutionContext, RunOutputOptions, sh


async def greet() -> None:
    cmd = sh.make(ECHO)("-n", "hello runtime")
    ctx = ExecutionContext(env={"GREETING": "1"})
    result = await cmd.run(output=RunOutputOptions(echo=True), context=ctx)
    if not result.ok:
        raise RuntimeError(f"echo failed: {result.exit_code}")
    print(result.stdout)
```

### Migrating from `capture`/`echo` keyword arguments

`IOOptions` is a deprecated alias for `RunOutputOptions`; keep using
`RunOutputOptions` in new code.

Prior to this release, `Pipeline.run()` and `Pipeline.run_sync()` accepted
`capture` and `echo` directly:

```python
# Before
result = pipeline.run_sync(capture=False, echo=True)

# After
from cuprum import RunOutputOptions

result = await cmd.run(output=RunOutputOptions(capture=True, echo=False))
result = cmd.run_sync(output=RunOutputOptions(capture=False))
result = pipeline.run_sync(output=RunOutputOptions(capture=False, echo=True))
```

If existing code constructs `IOOptions`, replace it with `RunOutputOptions`.
`IOOptions` remains a deprecated alias for the same `capture` and `echo` values
and emits a `DeprecationWarning` on construction. Migrate by replacing
`IOOptions(capture=..., echo=...)` usage with
`RunOutputOptions(capture=..., echo=...)` passed as `output=...`.

`RunOutputOptions(capture=True, echo=False)` is the default. Supply it
explicitly only when overriding either flag.

The flat `capture` / `echo` keyword arguments on `Pipeline.run` / `run_sync`
remain accepted for backwards compatibility but emit a `DeprecationWarning`;
passing them together with `output` raises `ValueError`.

If the awaiting task is cancelled while a command is running, Cuprum sends
`SIGTERM` to the subprocess, waits for a short grace period, and then escalates
to `SIGKILL` to ensure the child process is cleaned up.

### Cancellation during teardown

Timeout and fail-fast teardown survives repeated caller cancellation. Cuprum
keeps the teardown task alive through `SIGTERM`, the grace period, `SIGKILL`,
and process reaping, then re-raises the first cancellation. Later cancellation
requests do not interrupt escalation.

### Direct stdin input

Use `StdinInput` on `run()` / `run_sync()` to feed data directly to a command's
standard input without adding an extra allowlisted program to a pipeline.
`StdinInput(text=...)` is encoded with the execution context's `encoding` and
`errors` settings. `StdinInput(data=...)` writes the supplied bytes unchanged.
Supplying both values is invalid.

```python
from cuprum import GIT, StdinInput, sh

cmd = sh.make(GIT)("hash-object", "--stdin")
result = cmd.run_sync(stdin=StdinInput(text="hello\n"))
print(result.stdout)
```

If the subprocess closes its stdin pipe before all data is written (e.g. `head`
reads only the first lines), the write failure is silently recorded as a
`stdin_error` trace event and execution continues normally.

### Timeouts

Use the `timeout` parameter on `run()` / `run_sync()` to enforce a wall-clock
limit in seconds. Timeouts are opt-in; when left as `None` no limit is
enforced. When a timeout expires, Cuprum terminates the subprocess, waits for
`cancel_grace`, escalates to `SIGKILL` if needed, and raises `TimeoutExpired`
(mirroring `subprocess.TimeoutExpired`).

Any output already captured before the timeout fired is preserved on the
exception: `exc.output` / `exc.stderr` hold the partial stdout/stderr (or
`None` when `capture=False`), so callers can inspect what the command produced
before it was killed.

Under `capture=True` those attributes are always strings, never `None`: a
stream that produced nothing before the deadline reports the empty string.
Cuprum gives the readers a brief bounded window to observe end-of-file once the
process has died, and keeps whatever a reader had already read even when the
window closes first and that reader has to be cancelled — which is what happens
when a grandchild process inherited the pipe and holds it open. The window is
short and fixed, because teardown must never wait on a pipe that may never
close.

**Non-positive timeout behaviour:** a `timeout` of `0` or a negative value is
treated as an already-elapsed deadline, so the command expires immediately: it
never waits for the process to exit on its own. Cuprum instead terminates the
running process (or every pipeline stage), waits for it to actually exit —
honouring `cancel_grace` and escalating to `SIGKILL` if needed — drains the
stream consumers, and then raises `TimeoutExpired`.

**Timeout diagnostics.** Every expiry writes a structured `WARNING` record to
the `cuprum.timeout` logger, even when no observe hook is registered. The
`subprocess_timeout_expired pid=… timeout=… mode=…` record carries:

- `cuprum_operation`: `"wait"`
- `cuprum_pid`: the subprocess PID (`None` when no process was spawned)
- `cuprum_timeout_s`: the configured timeout in seconds
- `cuprum_timeout_mode`: `"elapsed_deadline"` or `"non_positive_immediate"`
- `cuprum_error_type`: `"TimeoutError"`

If cleanup fails to drain a stream consumer, an `ERROR`
`subprocess_teardown_drain_failed pid=… errors=…` record carries
`cuprum_operation` (`"drain"`), `cuprum_teardown_outcome` (`"drain_error"`),
`cuprum_pid`, and `cuprum_error_type` with the comma-joined failure classes.
The failure is absorbed so it cannot displace `TimeoutExpired` or
`CancelledError`. Logging is best-effort; the same values are emitted as
`timeout` and `teardown_error` events, so the channels cannot disagree.

Timeout resolution order:

- Explicit `timeout` argument on `run()` / `run_sync` when not `None`.
- `ExecutionContext.timeout` when provided and not `None`.
- `ScopeConfig(timeout=...)` default set via `scoped()` when present.

`ScopeConfig(timeout=...)` and `CuprumContext(timeout=...)` validate their
timeouts when constructed. Values must be finite and non-negative; `None` means
no timeout, and numeric values are stored as `float`. Negative values, `NaN`,
and positive or negative infinity raise `ValueError`. A value too large to
convert to `float` also raises `ValueError` rather than leaking the conversion
`OverflowError`.

Example usage:

```python
from cuprum import ECHO, ScopeConfig, TimeoutExpired, scoped, sh

cmd = sh.make(ECHO)("-n", "hello")

with scoped(ScopeConfig(timeout=3.0)):
    try:
        cmd.run_sync()
    except TimeoutExpired as exc:
        print(f"timed out after {exc.timeout}s")
```

Pipeline timeouts apply to the entire pipeline run; partial output is surfaced
using the same capture rules as successful runs.

A pipeline enforces its deadline once for the whole run, but reports it per
stage: each stage gets a `timeout` event, a `cuprum.timeout` record with its
`pid`, and one `cuprum_timeouts_total` increment. The fields and `timeout_mode`
values match the single-command case.

### Synchronous execution

For scripts or contexts where async/await is not available, use `run_sync()`:

```python
from cuprum import ECHO, ExecutionContext, RunOutputOptions, sh


def greet() -> None:
    cmd = sh.make(ECHO)("-n", "hello sync")
    ctx = ExecutionContext(env={"GREETING": "1"})
    result = cmd.run_sync(output=RunOutputOptions(echo=True), context=ctx)
    if not result.ok:
        raise RuntimeError(f"echo failed: {result.exit_code}")
    print(result.stdout)
```

`run_sync()` accepts `RunOutputOptions` for synchronous output handling and
returns the same `CommandResult` shape as `run()`. It drives the event loop
internally via `asyncio.run()`.

## Execution context and hooks

Cuprum provides `CuprumContext` to scope allowlists and execution hooks across
your application. Contexts are backed by a `ContextVar`, giving you automatic
isolation across threads and async tasks.

**Upgrade note (v0.2.0):** `scoped()` now accepts a single `ScopeConfig`
argument instead of keyword parameters. Update calls like
`with scoped(allowlist=...)` to `with scoped(ScopeConfig(allowlist=...))`.

When you call `SafeCmd.run()` or `run_sync()`, Cuprum automatically:

1. Checks the current context's allowlist and raises `ForbiddenProgramError` if
   the program is not permitted.
2. Invokes all registered before hooks (in FIFO order) before process execution.
3. Invokes all registered after hooks (in LIFO order) after the process
   completes.

**Empty allowlist behaviour:** When no parent context is established,
`scoped(ScopeConfig())` is the permissive root context (all programs allowed),
which supports adoption by defaulting to non-restrictive execution for
first-time callers. Nested `scoped(ScopeConfig())` calls inherit the current
parent policy, so they cannot widen permissions. If an explicit empty allowlist
is introduced in an already restricted path, that scope remains restrictive and
permits no programs.

### Scoped contexts

Use `scoped(ScopeConfig(allowlist=...))` to establish a narrowed execution
context within a code block:

```python
from cuprum import ECHO, LS, ScopeConfig, scoped

# Start with a base allowlist
with scoped(ScopeConfig(allowlist=frozenset([ECHO, LS]))) as ctx:
    assert ctx.is_allowed(ECHO)  # True
    assert ctx.is_allowed(LS)  # True

    # Narrow further in nested scope
    with scoped(ScopeConfig(allowlist=frozenset([ECHO]))) as inner:
        assert inner.is_allowed(ECHO)  # True
        assert inner.is_allowed(LS)  # False (narrowed out)
```

Key properties of `scoped(ScopeConfig())`:

- At root/no-parent, `ScopeConfig()` remains permissive by default.
- In nested scopes, `ScopeConfig()` inherits the parent allowlist and therefore
  remains restricted when the parent is restricted.
- Context is automatically restored when the block exits, even on exception.

### Accessing the current context

Use `current_context()` or `get_context()` to access the current execution
context:

```python
from cuprum import ECHO, current_context, ScopeConfig, scoped

with scoped(ScopeConfig(allowlist=frozenset([ECHO]))):
    ctx = current_context()
    if ctx.is_allowed(ECHO):
        print("ECHO is allowed")
```

### Dynamic allowlist extension

Use `allow()` to temporarily add programs to the current context:

```python
from cuprum import ECHO, LS, allow, current_context, ScopeConfig, scoped

with scoped(ScopeConfig(allowlist=frozenset([ECHO]))):
    # LS is not currently allowed
    assert not current_context().is_allowed(LS)

    # Temporarily allow LS
    with allow(LS):
        assert current_context().is_allowed(LS)

    # LS is no longer allowed after the block
    assert not current_context().is_allowed(LS)
```

For manual control, use the `AllowRegistration` handle directly:

```python
from cuprum import ECHO, LS, allow, current_context, ScopeConfig, scoped

with scoped(ScopeConfig(allowlist=frozenset([ECHO]))):
    reg = allow(LS)
    assert current_context().is_allowed(LS)
    reg.detach()  # Remove LS from allowlist
    assert not current_context().is_allowed(LS)
```

### Scoped environment overlays

**Breaking behaviour note:** `env(...)` resolves overlays against the live
`os.environ` when a subprocess is spawned, not against an import-time or
scope-entry snapshot. Code that relied on snapshot semantics should pass stable
values explicitly through `env(...)` or the per-call `ExecutionContext.env`
mapping.

Use `env()` to overlay environment variables on top of the live `os.environ`
for the duration of a scope. The overlay is resolved at subprocess spawn time,
not at registration time, so variables added to `os.environ` *after* the scope
is entered (the common `monkeypatch.setenv` case under pytest) remain visible
to subprocesses spawned inside the scope:

```python
import os

from cuprum import GIT, ScopeConfig, env, scoped, sh

os.environ["GIT_AUTHOR_NAME"] = "Cuprum"
os.environ["GIT_AUTHOR_EMAIL"] = "cuprum@example.com"

with scoped(ScopeConfig(allowlist=frozenset([GIT]))):
    with env(PATH="/usr/bin:/usr/local/bin"):
        # The subprocess sees PATH overlaid on the *live* os.environ,
        # including GIT_AUTHOR_NAME / GIT_AUTHOR_EMAIL above.
        sh.make(GIT)("commit", "--allow-empty", "-m", "noop").run_sync()
```

Precedence, from lowest to highest, is:

1. The current process's `os.environ`, read at spawn time.
2. The overlay registered via `env(...)` (later entries win when scopes
   nest).
3. The per-call `ExecutionContext.env` mapping.

`env()` accepts both positional mappings and keyword arguments, mirroring
`dict(...)`. The function returns an `EnvRegistration` handle which can be used
as a context manager or detached manually:

```python
from cuprum import current_context, env

reg = env({"DATABASE_URL": "sqlite:///tmp/test.db"}, LOG_LEVEL="DEBUG")
try:
    assert current_context().env_overlay["DATABASE_URL"].startswith("sqlite")
finally:
    reg.detach()
```

This intentionally departs from plumbum's `local.env`, which snapshots
`os.environ` once at module import time and can therefore miss variables that
are set later in the process.

### Before and after hooks

Register hooks to run before or after command execution:

```python
from cuprum import ECHO, before, after, ScopeConfig, scoped, sh


def log_before(cmd):
    print(f"About to run: {cmd.program}")


def log_after(cmd, result):
    print(f"Finished {cmd.program} with exit code {result.exit_code}")


with scoped(ScopeConfig(allowlist=frozenset([ECHO]))):
    with before(log_before), after(log_after):
        cmd = sh.make(ECHO)("hello")
        # Hooks will be invoked when cmd.run() is called
```

Hook ordering:

- **Before hooks** execute in registration order (FIFO): parent hooks run
  before child hooks.
- **After hooks** execute in reverse order (LIFO): child hooks run before
  parent hooks, enabling cleanup patterns.

Like `allow()`, hook registrations can be detached manually:

```python
from cuprum import before, current_context, ScopeConfig, scoped


def my_hook(cmd):
    pass


with scoped(ScopeConfig()):
    reg = before(my_hook)
    assert my_hook in current_context().before_hooks
    reg.detach()
    assert my_hook not in current_context().before_hooks
```

### Logging hook

Use `logging_hook()` to register paired hooks that emit structured start and
exit events through the standard library `logging` module. The helper wires a
before hook (start) and after hook (exit) into the current context and returns
a registration handle that can be used as a context manager:

```python
import logging

from cuprum import ECHO, logging_hook, ScopeConfig, scoped, sh

logger = logging.getLogger("myapp.commands")

with scoped(ScopeConfig(allowlist=frozenset([ECHO]))):
    with logging_hook(logger=logger):
        sh.make(ECHO)("-n", "hello logging").run_sync()
```

By default, the hook logs to `logging.getLogger("cuprum")` at `INFO` level. The
logger or the log levels can be overridden via `start_level` and `exit_level`.
Start events include the program and argv; exit events include the program,
pid, exit code, duration, and lengths of captured stdout/stderr (zero when
capture is disabled).

### Structured execution events

For richer observability, register an observe hook with `sh.observe()`. Observe
hooks receive `ExecEvent` values describing:

- `plan` — intent to execute the program (argv/cwd/env resolved).
- `start` — subprocess spawned (pid available).
- `stdout` / `stderr` — decoded output emitted as lines.
- `exit` — subprocess finished (exit code and duration).
- `timeout` — the run exceeded its deadline (ancillary; emitted before the
  preserved `exit` event and the public `TimeoutExpired`).
- `teardown_error` — a stream consumer drained with an unexpected error during
  cleanup (ancillary; the error is absorbed to preserve the primary exception).
- `capture_eof_grace_expired` — a capturing drain exhausted its fixed EOF grace
  budget while one or more readers remained pending (ancillary).
- `pipeline_fail_fast` — a pipeline is being torn down early because a
  non-final stage was the first to fail. Emitted at most once per pipeline,
  before every other still-running stage — upstream producers and downstream
  consumers alike — is terminated, and carrying `stage_index`, `stage_count`,
  `exit_code`, and `duration_s` for the failing stage. It is a decision rather
  than a lifecycle phase: the failing stage's own `exit` event still follows,
  and no stage's events are skipped or reordered because of it. Read
  `stage_index` and `stage_count` from these typed fields rather than from the
  event's tags: `ExecutionContext.tags` are merged last, so a caller that sets
  its own `pipeline_stage_index` or `pipeline_stages` tag shadows the tag
  copies, whereas the typed fields always report the stage the pipeline
  actually acted on.

Hooks can be used for structured logging, metrics, or tracing without coupling
Cuprum to a specific telemetry library.

The `timeout` event carries `operation` (`"wait"`), `pid`, `timeout_s`,
`error_type` (`"TimeoutError"`), and `timeout_mode`: `"elapsed_deadline"` for a
positive elapsed deadline or `"non_positive_immediate"` for a non-positive
deadline that expires without awaiting the process. The `teardown_error` event
carries `operation` (`"drain"`), `pid`, and `error_type`, the comma-joined
classes raised while cancelling and draining stream consumers. It fires at most
once per execution and excludes expected `CancelledError` failures.

The `capture_eof_grace_expired` event carries the execution's `exec_id` and
`pid`, `operation` (`"drain"`), `eof_grace_s`, and `pending_readers` (one or
two). It is emitted only when a capturing drain reaches the fixed grace limit;
the corresponding `cuprum_capture_eof_grace_expired_total` metric uses only the
`program` and `project` labels, and tracing adds a
`cuprum.capture_eof_grace_expired` event to the matching span. The grace-expiry
event itself carries no captured stdout or stderr payload.

These ancillary events preserve the public outcome: `start` and `exit` are
unchanged, and synchronous hook failures handling `timeout`, `teardown_error`,
or `capture_eof_grace_expired` are suppressed rather than masking
`TimeoutExpired` or `CancelledError`.

Each event carries a stable `exec_id` correlation token: every lifecycle event
for one execution — a single command, or one stage of a pipeline — shares the
same token. Hooks that track per-execution state should correlate by `exec_id`
rather than `pid`, which the operating system can recycle across executions.
Events with `exec_id=None` cannot be correlated, so correlation-consuming hooks
(such as the tracing adapter) drop them.

Awaitable hook results are scheduled as `asyncio.Task` instances and awaited
before the run completes.

#### When an observe hook raises

A failing observe hook fails the run. Cuprum logs the failure and then
re-raises the hook's *own* exception type out of `run()` / `run_sync()`; it is
never swallowed. The two hook kinds differ only in when that happens:

- A **synchronous** hook raises inline, at the moment the event is emitted.
  Emission of that event stops there, so hooks registered after it do not
  receive that event, and the exception surfaces immediately — before the
  subprocess is spawned, if the hook failed on `plan`. The raised exception is
  the hook's own; Cuprum's internal wrapper appears only as its `__cause__`.
- An **awaitable** hook raises inside its scheduled task. Every hook still
  receives the event, and the exception surfaces when Cuprum awaits the pending
  tasks before the run returns. When several awaitable hooks fail, only the
  first is raised.

This matters most for hooks that match exhaustively on `ExecEvent.phase` and
reject unknown values. `pipeline_fail_fast` is a new phase, so such a hook
raises on it — and so fails the pipeline — until it grows an arm for it. A hook
that must never influence the run should catch its own exceptions.

```python
from cuprum import ECHO, ExecEvent, ExecHook, ScopeConfig, scoped, sh
from cuprum.sh import ExecutionContext


events: list[ExecEvent] = []


def capture(ev: ExecEvent) -> None:
    events.append(ev)


hook: ExecHook = capture

with scoped(ScopeConfig(allowlist=frozenset([ECHO]))), sh.observe(hook):
    ctx = ExecutionContext(tags={"run_id": "demo"})
    sh.make(ECHO)("-n", "hello events").run_sync(context=ctx)

stdout_lines = [ev.line for ev in events if ev.phase == "stdout"]
exit_events = [ev for ev in events if ev.phase == "exit"]
assert "hello events" in stdout_lines
assert exit_events[0].tags["run_id"] == "demo"
```

`ExecHook` is defined in `cuprum.events` and re-exported from `cuprum`. Import
it with `from cuprum import ExecHook` or `from cuprum.events import ExecHook`.
The former `from cuprum.context import ExecHook` path is no longer supported;
update that import without changing the hook implementation.

`ExecutionContext.tags` is merged into each event's `tags` mapping. Cuprum also
adds default tags such as the project name and pipeline stage metadata.

### Thread and async task isolation

`CuprumContext` uses Python's `ContextVar` mechanism, which provides automatic
isolation:

- Each thread gets its own context value.
- Each async task inherits the context from its creator and can modify it
  independently.

This isolation allows `scoped(ScopeConfig())` to be used in concurrent code
without context leaking between threads or tasks:

```python
import asyncio

from cuprum import ECHO, LS, current_context, ScopeConfig, scoped


async def worker(name: str, programs):
    with scoped(ScopeConfig(allowlist=programs)):
        await asyncio.sleep(0.1)  # Simulate work
        ctx = current_context()
        print(f"{name}: ECHO allowed = {ctx.is_allowed(ECHO)}")


async def main():
    await asyncio.gather(
        worker("task1", frozenset([ECHO])),
        worker("task2", frozenset([LS])),
    )
    # task1 sees ECHO allowed, task2 does not


asyncio.run(main())
```

### Checking allowlist membership

Use `is_allowed()` to check if a program is permitted:

```python
from cuprum import ECHO, CuprumContext

ctx = CuprumContext(allowlist=frozenset([ECHO]))
if ctx.is_allowed(ECHO):
    print("ECHO is allowed")
```

Use `check_allowed()` to raise `ForbiddenProgramError` if a program is not
allowed:

```python
from cuprum import ECHO, LS, CuprumContext, ForbiddenProgramError

ctx = CuprumContext(allowlist=frozenset([ECHO]))
try:
    ctx.check_allowed(LS)
except ForbiddenProgramError as e:
    print(f"Access denied: {e}")
```

## Telemetry adapters

Cuprum provides example adapters in `cuprum.adapters` that demonstrate how to
integrate execution events with common observability backends. These adapters
are optional and non-blocking; they do not depend on external telemetry
libraries but define protocols that can be implemented with any backend.

### Structured logging adapter

The `logging_adapter` module provides an observe hook that emits structured log
records for each execution phase. Unlike the simpler `logging_hook()`, this
adapter uses the full `ExecEvent` stream for fine-grained observability.

```python
import logging

from cuprum import ECHO, ScopeConfig, scoped, sh
from cuprum.adapters.logging_adapter import structured_logging_hook

logging.basicConfig(level=logging.DEBUG)

with scoped(ScopeConfig(allowlist=frozenset([ECHO]))):
    hook = structured_logging_hook()
    with sh.observe(hook):
        sh.make(ECHO)("hello").run_sync()
```

The hook attaches selected `cuprum_*` prefixed extra fields to log records:

- `cuprum_phase`: Event phase (plan, start, stdout, stderr, stdin,
  stdin_error, timeout, teardown_error, capture_eof_grace_expired, exit,
  pipeline_fail_fast)
- `cuprum_program`: Program being executed
- `cuprum_argv`: The command's argument vector, recorded verbatim for phases
  that project it (see the security note below)
- `cuprum_pid`: Process ID (when available)
- `cuprum_exit_code`: Exit code (for exit and `pipeline_fail_fast` events)
- `cuprum_duration_s`: Duration in seconds (for exit and `pipeline_fail_fast`
  events)
- `cuprum_stage_index` / `cuprum_stage_count`: Failing stage position and
  pipeline width (for `pipeline_fail_fast` events)
- `cuprum_eof_grace_s` / `cuprum_pending_readers`: Fixed EOF-grace duration
  and pending-reader count (for `capture_eof_grace_expired` events). Event tags
  are not emitted by this structured logging adapter.

When registered, `structured_logging_hook()` emits `pipeline_fail_fast` at
`LogLevels.fail_fast_level`, which defaults to `logging.WARNING`. This default
means the registered adapter needs no extra level configuration; set the field
to change it.

> **Security note — argument logging.** For phases that project it,
> `cuprum_argv` is emitted verbatim and is **not** redacted for phases that
> project it. Any secret passed on the command line — a `--password=…`, an API
> token, a connection string —
> is written into that log record (and into the `JsonLoggingFormatter` output)
> exactly as supplied. The same applies to the plain-text `logging_hook()`.
> The `pipeline_fail_fast` and `capture_eof_grace_expired` projections omit
> `cuprum_argv`, so those records do not expose command-line arguments. Event
> tags are not emitted by the structured adapter. Prefer passing secrets via the
> environment or files rather than as arguments, and scope log destinations
> accordingly.

For JSON output suitable for log aggregation systems, use the
`JsonLoggingFormatter`:

```python
import logging

from cuprum.adapters.logging_adapter import JsonLoggingFormatter

handler = logging.StreamHandler()
handler.setFormatter(JsonLoggingFormatter())
logger = logging.getLogger("cuprum.exec")
logger.addHandler(handler)
```

### Metrics adapter

The `metrics_adapter` module provides a Prometheus-style metrics hook that
collects counters and histograms. It uses a protocol class so the backend can
be implemented with any preferred metrics library.

```python
from cuprum import ECHO, ScopeConfig, scoped, sh
from cuprum.adapters.metrics_adapter import InMemoryMetrics, MetricsHook

metrics = InMemoryMetrics()

with scoped(ScopeConfig(allowlist=frozenset([ECHO]))):
    with sh.observe(MetricsHook(metrics)):
        sh.make(ECHO)("hello").run_sync()

print(metrics.counters)  # {'cuprum_executions_total': 1.0, ...}
print(metrics.histograms)  # {'cuprum_duration_seconds': [...]}
```

The hook collects:

- `cuprum_executions_total`: Counter incremented on each command start
- `cuprum_failures_total`: Counter incremented on non-zero exit
- `cuprum_duration_seconds`: Histogram of execution durations
- `cuprum_stdout_lines_total`: Counter of stdout lines emitted
- `cuprum_stderr_lines_total`: Counter of stderr lines emitted
- `cuprum_stdin_bytes_total`: Counter of successful stdin bytes written
- `cuprum_stdin_errors_total`: Counter of stdin writer failures
- `cuprum_timeouts_total`: Counter of subprocess timeout expiries
- `cuprum_teardown_errors_total`: Counter of stream-consumer drain failures
  during cleanup
- `cuprum_capture_eof_grace_expired_total`: Counter of capturing drains that
  reach the fixed EOF-grace limit with readers still pending
- `cuprum_pipeline_fail_fast_total`: Counter incremented once per pipeline torn
  down early because a non-final stage was the first to fail

All metrics include `program` and `project` labels, and only those. Missing,
empty, or explicit `None` project tags fall back to `unknown`.

`cuprum_timeouts_total` counts both modes; use the `timeout` event's
`timeout_mode`, or the `cuprum.timeout` record, to distinguish an elapsed
deadline from an immediate non-positive expiry.

`cuprum_pipeline_fail_fast_total` in particular does **not** use `exec_id`,
stage index, exit code, command arguments, or paths as labels. `exec_id` is
unique per execution and would give the series unbounded cardinality; the
others would multiply series for no aggregate a dashboard needs. Those fields
remain on the `pipeline_fail_fast` event itself and on the trace span, which is
where per-incident detail belongs. A counter spike therefore cannot be joined
to a span through the metric: when reading the observe event, use
`ExecEvent.exec_id`; when reading its matching structured log record, use
`cuprum_exec_id`. Both fields carry the same existing execution token, which
identifies the individual stage spans behind the spike.

To integrate with a real metrics library like `prometheus_client`, implement the
`MetricsCollector` protocol:

```python
from prometheus_client import Counter, Histogram

from cuprum.adapters.metrics_adapter import MetricsCollector, MetricsHook


class PrometheusMetrics:
    def __init__(self) -> None:
        self._exec_total = Counter(
            "cuprum_executions_total",
            "Total command executions",
            ["program", "project"],
        )
        self._duration = Histogram(
            "cuprum_duration_seconds",
            "Execution duration",
            ["program", "project"],
        )

    def inc_counter(self, name, value, labels):
        if name == "cuprum_executions_total":
            self._exec_total.labels(**labels).inc(value)

    def observe_histogram(self, name, value, labels):
        if name == "cuprum_duration_seconds":
            self._duration.labels(**labels).observe(value)


hook = MetricsHook(PrometheusMetrics())
```

### Tracing adapter

The `tracing_adapter` module provides an OpenTelemetry-style tracing hook that
creates spans for command execution. It uses protocol classes so you can
implement the backend with your preferred tracing library.

```python
from cuprum import ECHO, ScopeConfig, scoped, sh
from cuprum.adapters.tracing_adapter import InMemoryTracer, TracingHook

tracer = InMemoryTracer()

with scoped(ScopeConfig(allowlist=frozenset([ECHO]))):
    with sh.observe(TracingHook(tracer)):
        sh.make(ECHO)("hello").run_sync()

span = tracer.spans[0]
print(span.name)  # 'cuprum.exec echo'
print(span.attributes)  # {'cuprum.program': 'echo', ...}
```

The hook creates spans with these attributes:

- `cuprum.program`: The program being executed
- `cuprum.argv`: Full argument vector
- `cuprum.pid`: Process ID
- `cuprum.cwd`: Working directory (when set)
- `cuprum.exit_code`: Exit code (set on span end)
- `cuprum.duration_s`: Duration in seconds (set on span end)
- `cuprum.project`: Project name from tags
- `cuprum.pipeline_stage_index`: Pipeline stage index (if applicable)
- `cuprum.pipeline_stages`: Total pipeline stages (when applicable)

Output lines (stdout/stderr) are recorded as span events when
`record_output=True` (the default).

**Ancillary span events.** `stdin_error`, `timeout`, `teardown_error`, and
`capture_eof_grace_expired` are recorded as `cuprum.<phase>` events on the
execution's open span. They leave it neither ended nor marked; a later `exit`
closes it normally. `timeout` is always followed by `exit`, while
`teardown_error` may be the final event. Ancillary events carry their set
`line`, `operation`, `error_type`, `note`, `timeout_s`, `timeout_mode`,
`eof_grace_s`, and `pending_readers` fields, and correlate by `exec_id`; an
event without a matching open span is dropped. The grace-expiry event carries
no captured stdout or stderr payload.

**Correlation note:** the hook correlates an execution's `start`, `stdout`,
`stderr`, and `exit` events by `ExecEvent.exec_id`, a stable token minted once
per execution (per pipeline stage for pipelines) — not by `pid`, since the
operating system can recycle a `pid` across executions. `pid` is still recorded
as the `cuprum.pid` attribute for observability. Events emitted by Cuprum
always carry an `exec_id`, so ordinary usage is unaffected. Only hand-built or
legacy events that omit `exec_id` are affected: the hook cannot correlate them,
so it ignores them — a `start` without an `exec_id` creates no span, and
`stdout`/`stderr`/`stdin_error`/`timeout`/`teardown_error`/
`capture_eof_grace_expired`/`pipeline_fail_fast`/`exit` without one are dropped.

A pipeline's `pipeline_fail_fast` event is recorded as a
`cuprum.pipeline_fail_fast` span event on the failing stage's already-open
span, carrying `stage_index`, `stage_count`, `exit_code`, and `duration_s`. It
is `cuprum_exec_id` that joins the record, the event, and that span: the
decision reuses the failing stage's existing execution token rather than
minting one of its own, so the teardown appears in the trace of the stage that
caused it. No separate span is started, and the stage's own `exit` event still
closes and marks the span.

To integrate with OpenTelemetry, implement the `Tracer` and `Span` protocols:

```python
from opentelemetry import trace

from cuprum.adapters.tracing_adapter import Span, Tracer, TracingHook


class OTelSpan:
    def __init__(self, otel_span) -> None:
        self._span = otel_span

    def set_attribute(self, key, value):
        self._span.set_attribute(key, value)

    def add_event(self, name, attributes=None):
        self._span.add_event(name, attributes=attributes or {})

    def set_status(self, *, ok):
        from opentelemetry.trace import StatusCode

        code = StatusCode.OK if ok else StatusCode.ERROR
        self._span.set_status(code)

    def end(self):
        self._span.end()


class OTelTracer:
    def __init__(self, tracer) -> None:
        self._tracer = tracer

    def start_span(self, name, attributes=None):
        span = self._tracer.start_span(name, attributes=attributes)
        return OTelSpan(span)


otel_tracer = trace.get_tracer("cuprum")
hook = TracingHook(OTelTracer(otel_tracer))
```

### Rust-pump executor-hop spans

Rust-backed pipelines can expose the executor hop that moves bytes between
stages as an opt-in span. The example below requires the Rust backend; run it
with `CUPRUM_STREAM_BACKEND=rust uv run python my_script.py`. Register a
`Tracer` with `observe_pump_span` in the context where the pipeline runs. The
registration is context-local and can be used as a context manager:

```python
import sys
from pathlib import Path

from cuprum import (
    ECHO,
    Program,
    ProgramCatalogue,
    ProjectSettings,
    ScopeConfig,
    observe_pump_span,
    scoped,
    sh,
)
from cuprum.adapters.tracing_memory import InMemoryTracer

PYTHON = Program(str(Path(sys.executable)))
project = ProjectSettings(
    name="pipeline-example",
    programs=(ECHO, PYTHON),
    documentation_locations=(),
    noise_rules=(),
)
catalogue = ProgramCatalogue(projects=(project,))
echo = sh.make(ECHO, catalogue=catalogue)
python = sh.make(PYTHON, catalogue=catalogue)
pipeline = echo("-n", "hello") | python(
    "-c",
    "import sys; sys.stdout.write(sys.stdin.read().upper())",
)

tracer = InMemoryTracer()
with scoped(ScopeConfig(allowlist=catalogue.allowlist)):
    with observe_pump_span(tracer):
        pipeline.run_sync()

span = tracer.spans[0]
print(span.name)  # 'cuprum.rust_pump_hop'
print(span.attributes["cuprum.outcome"])  # 'succeeded'
```

One span is opened for each registered tracer and each Rust-pump hop that is
actually scheduled. A fast-path decline creates no hop span. The span starts
immediately before executor scheduling and ends from the completion callback,
after the native worker has settled; cancellation therefore includes the
cleanup drain. The Rust-internal pump span remains parentless across PyO3.

Hop spans contain only bounded attributes: `cuprum.operation` (currently
`rust_pump`), `cuprum.buffer_size`, and `cuprum.outcome`, whose values are
`succeeded`, `failed`, `cancelled`, or `failed_after_cancel`. Successful hops
also include `cuprum.total_bytes` and receive status `OK`; other outcomes do
not receive a success status. The existing `PumpEvent` channel and
`observe_pump` registrations are unchanged. Ordinary tracer observer failures
are contained so they do not alter pump execution, while control-flow
exceptions continue to propagate.

### Design principles for adapters

The adapters follow these design principles:

1. **Optional dependencies**: Adapters do not import external telemetry
   libraries. They define protocols that can be implemented with any backend.

2. **Non-blocking execution**: Hooks are synchronous and complete quickly.
   For high-throughput scenarios, consider buffering or async handlers.

3. **Protocol-based integration**: Use Python's `Protocol` classes to define
   the interface, making it easy to swap implementations without inheritance.

4. **Reference implementations**: The `InMemoryMetrics` and `InMemoryTracer`
   classes serve as both documentation and test utilities.

## Concurrent command execution

Cuprum provides `run_concurrent` to execute multiple `SafeCmd` instances
concurrently with optional concurrency limits. Results are returned in
submission order, and hooks fire per command to preserve existing semantics.

### Basic usage

```python
from cuprum import ECHO, ScopeConfig, run_concurrent_sync, scoped, sh

echo = sh.make(ECHO)
commands = [echo("-n", f"task-{i}") for i in range(5)]

with scoped(ScopeConfig(allowlist=frozenset([ECHO]))):
    result = run_concurrent_sync(*commands)

print(f"All succeeded: {result.ok}")
for cmd_result in result.results:
    print(cmd_result.stdout)
```

For async code, use `run_concurrent`:

```python
import asyncio

from cuprum import ECHO, ScopeConfig, run_concurrent, scoped, sh


async def main() -> None:
    echo = sh.make(ECHO)
    commands = [echo("-n", f"task-{i}") for i in range(5)]

    with scoped(ScopeConfig(allowlist=frozenset([ECHO]))):
        result = await run_concurrent(*commands)

    print(f"All succeeded: {result.ok}")


asyncio.run(main())
```

### ConcurrentConfig

Configure execution via the `ConcurrentConfig` dataclass:

```python
from cuprum import ECHO, ConcurrentConfig, run_concurrent_sync, scoped, sh

echo = sh.make(ECHO)
commands = [echo("-n", f"task-{i}") for i in range(10)]

config = ConcurrentConfig(
    concurrency=3,  # At most 3 commands run simultaneously
    capture=True,  # Capture stdout/stderr (default)
    echo=False,  # Do not tee output (default)
    fail_fast=False,  # Continue after failures (default)
)

with scoped(allowlist=frozenset([ECHO])):
    result = run_concurrent_sync(*commands, config=config)
```

Configuration attributes:

- `concurrency`: Maximum parallel commands. `None` (default) runs all in
  parallel; `1` runs sequentially.
- `capture`: When `True` (default), capture stdout/stderr into results.
- `echo`: When `True`, tee output to configured sinks.
- `context`: Shared `ExecutionContext` for all commands.
- `fail_fast`: When `True`, cancel remaining commands after first failure.

When `config` is `None` (the default), `ConcurrentConfig()` is used.

### Limiting concurrency

Pass a `ConcurrentConfig` with `concurrency=N` to limit parallel execution.
This uses an `asyncio.Semaphore` internally:

```python
from cuprum import ECHO, ConcurrentConfig, run_concurrent_sync, scoped, sh

echo = sh.make(ECHO)
commands = [echo("-n", f"task-{i}") for i in range(10)]

with scoped(allowlist=frozenset([ECHO])):
    # At most 3 commands run simultaneously
    result = run_concurrent_sync(*commands, config=ConcurrentConfig(concurrency=3))
```

### Failure handling

By default, `run_concurrent` uses collect-all mode: all commands run to
completion regardless of failures. The `ConcurrentResult.failures` tuple
contains indices of commands that exited non-zero. In fail-fast mode, `results`
may omit cancelled commands, so `failures` indices are positions within the
compacted `results`, whereas `failure_submission_indices` recovers the original
submission positions:

```python
from cuprum import run_concurrent_sync, scoped

with scoped(allowlist=...):
    result = run_concurrent_sync(cmd1, cmd2, cmd3)

if not result.ok:
    print(f"Failed command indices: {result.failures}")
    print(f"Original submission positions: {result.failure_submission_indices}")
    print(f"First failure: {result.first_failure}")
```

### Fail-fast mode

Enable `fail_fast=True` in the config to cancel remaining commands after the
first failure:

```python
from cuprum import ConcurrentConfig, run_concurrent_sync, scoped

with scoped(allowlist=...):
    result = run_concurrent_sync(*commands, config=ConcurrentConfig(fail_fast=True))

if not result.ok:
    print(f"First failure: {result.first_failure}")
    # Remaining commands were cancelled
```

In fail-fast mode, commands that were already running receive cancellation
(SIGTERM (termination signal) then SIGKILL (kill signal) after the grace
period). Commands that had not yet started are not scheduled.

### Hook semantics

Hooks fire per command, preserving consistency with single-command execution:

- **Before hooks** run when each command starts (may be interleaved).
- **After hooks** run when each command completes (may be interleaved).
- **Observe hooks** receive `ExecEvent` values for each command.

Commands share the execution context, so all commands see the same hooks and
allowlist:

```python
from cuprum import ECHO, before, run_concurrent_sync, scoped, sh


def log_start(cmd) -> None:
    print(f"Starting: {cmd.program}")


echo = sh.make(ECHO)
commands = [echo("-n", f"task-{i}") for i in range(3)]

with scoped(allowlist=frozenset([ECHO])), before(log_start):
    # log_start fires for each command
    result = run_concurrent_sync(*commands)
```

### ConcurrentResult properties

The `ConcurrentResult` dataclass provides:

- `results`: Tuple of `CommandResult` in submission order.
- `failures`: Tuple of indices where commands exited non-zero.
- `ok`: `True` when all commands succeeded.
- `first_failure`: The first failed `CommandResult`, or `None` if all
  succeeded.
- `submission_indices`: Tuple parallel to `results` giving each result's
  original submission index. In collect-all mode this is the identity sequence;
  in fail-fast mode it records the submission position of each completed
  command.
- `failure_submission_indices`: Tuple mapping each failure back to its
  original submission position. Unlike `failures` (positions within the
  possibly compacted `results`), these are stable across collect-all and
  fail-fast modes.

### Validation and error handling

`ConcurrentConfig` and `ConcurrentResult` validate their arguments eagerly, so
misuse is reported at construction time rather than surfacing later as a
confusing failure.

`ConcurrentConfig(concurrency=...)`:

- `None` (the default) means unthrottled concurrency; otherwise the value
  must be an `int` greater than or equal to `1`.
- A non-integer value raises `TypeError`. `bool` values are rejected too:
  since `True`/`False` are `int` subclasses in Python, they are excluded
  deliberately rather than being silently treated as `1`/`0`.
- A value below `1` (for example `0` or `-1`) raises `ValueError`.

```python
from cuprum import ConcurrentConfig

ConcurrentConfig(concurrency=0)  # ValueError: concurrency must be >= 1
ConcurrentConfig(concurrency=True)  # TypeError: concurrency must be an int, got bool
```

`ConcurrentResult` is normally returned by `run_concurrent`/
`run_concurrent_sync` rather than constructed directly, but the same validation
applies when constructed directly in tests:

- Each entry in `failures` must be an `int` (again, `bool` is rejected),
  otherwise `TypeError` is raised.
- A failure index outside `range(len(results))` raises `ValueError`.
- `failures` must be strictly ascending, and therefore unique; duplicate or
  descending indices raise `ValueError`.
- `submission_indices` defaults to `None`, which backfills the identity
  sequence `(0, 1, …, n-1)`, including the empty tuple when `results` is empty.
  Any supplied sequence whose length differs from `results` raises
  `ValueError`; an explicit empty tuple paired with non-empty `results` is
  therefore rejected rather than backfilled.
- A supplied sequence must also satisfy entry-level constraints, in addition
  to matching the length of `results`: each entry must be an exact `int`
  (`bool` is rejected, raising `TypeError`), non-negative, and strictly
  ascending (and therefore unique); violations raise `ValueError`. Entries are
  *not* bounded above by `len(results)` — after fail-fast compaction a
  surviving command's original submission index can exceed the compacted result
  length, so direct construction must permit values greater than or equal to
  `len(results)`.

## Performance extensions (optional Rust)

Cuprum ships as a pure Python wheel by default. Some platforms also provide
native wheels that bundle an optional Rust extension used by stream performance
optimizations. The Rust extension is not required to use Cuprum and does not
change behaviour for pure Python installations.

Cuprum does not use cibuildwheel; native wheels are built with maturin
directly, and the pure Python wheel is built with `uv_build`.

### Checking Rust availability

It is possible to check whether the optional extension is available in the
current environment using the public helper `cuprum.is_rust_available()`. The
helper delegates to `cuprum._backend._check_rust_available()`, the cached
resolver used by stream-backend dispatch. When
`set_rust_availability_for_testing()` is active, it short-circuits that
resolver before the raw import probe runs and clears both backend caches, so
test overrides take effect immediately. Cached answers only drift if a
long-lived interpreter survives a wheel swap or another out-of-band import-path
or installation-state change.

The module `cuprum._rust_backend` is private and not semver-stable, so
production code should avoid calling `_rust_backend.is_available()` directly
except when explicitly testing the raw import probe:

```python
import cuprum as c

if c.is_rust_available():
    print("Rust extension is available")
else:
    print("Rust extension is not installed")
```

The helper returns `False` on pure Python installations and does not raise when
native wheels are missing. Other native-extension import failures still surface
so broken installations are visible.

### Rust stream pump (internal)

The Rust extension now includes an internal pump function exposed as
`cuprum._streams_rs.rust_pump_stream`. This private API is intended for
Cuprum's internal pipeline dispatcher and may change without notice. Public
command execution remains unchanged until the dispatcher integration lands.

Both `rust_pump_stream` and `rust_consume_stream` accept an optional
`buffer_size` (bytes, default 64 KiB). It must be a positive integer no larger
than 1 GiB (`1 << 30`). Once PyO3 has converted the argument to a signed 64-bit
integer, Rust validation runs and rejects a value below 1 or above the cap with
`ValueError`. A value that cannot be converted to that integer in the first
place — a non-integer, or a Python integer outside the signed 64-bit range —
may instead fail earlier, during PyO3 argument conversion, with a different
exception.

### Rust stream consumption (internal)

The Rust extension also exposes `cuprum._streams_rs.rust_consume_stream`, which
reads a file descriptor and returns decoded text. This private API is intended
for the internal stream dispatcher and may change without notice.

`rust_consume_stream` is currently **implemented but not yet integrated**:
unlike the pump side (which is routed through a Rust-then-Python dispatcher),
no production code path routes stream consumption through it, and every
consume uses the pure-Python implementation regardless of the selected
backend. Consume-side dispatch is planned future work, gated on further
evidence. The tee hot-path profiling baseline now supports a future
capture-only dispatcher, but that dispatcher has not landed yet and will be
limited to fd-backed, UTF-8/replace, capture-only streams without echo sinks
or line callbacks.

The Rust consume helper always decodes UTF-8 with replacement semantics for
invalid sequences. Other encodings or error modes require the Python
implementation.

Backend selection for stream operations is controlled by the
`CUPRUM_STREAM_BACKEND` environment variable:

- `auto` (default): use Rust when available, otherwise fall back to Python.
- `rust`: force the Rust pathway and raise `ImportError` if the extension is
  unavailable.
- `python`: force the pure Python pathway.

The backend is resolved once on first use and the result is cached for the
lifetime of the process. Changing the environment variable after the first
resolution has no effect.

### Rust stream error handling (internal)

Not every I/O failure reaches the caller: `rust_pump_stream` treats a broken
pipe or connection reset as the expected result of a downstream stage exiting
early, so it drains the reader and returns successfully. When either helper
*does* propagate a failure, it raises an `OSError` that behaves like one raised
by Python itself, so it can be handled the same way:

- `errno` is populated, so failures are told apart by number rather than by
  matching message text — which is not a stable interface.
- `strerror` carries the system's description on its own. Rust renders a raw OS
  error as `"Bad file descriptor (os error 9)"`; that trailing `(os error N)`
  is removed, so the number is stated once, by Python's own `[Errno N]` prefix.
- The exception is the **subclass** the error implies, not a bare `OSError`, so
  `except BrokenPipeError:` and `except IsADirectoryError:` work as expected.

```python
import errno

from cuprum._streams_rs import rust_consume_stream

try:
    text = rust_consume_stream(fd)
except IsADirectoryError:
    text = ""  # the descriptor was a directory
except OSError as exc:
    if exc.errno != errno.EBADF:
        raise
    text = ""  # the descriptor was already closed
```

On Windows the native code is a Win32 error rather than an `errno`, so it is
carried in `winerror`; `errno` and the subclass are derived from it. Branch on
`winerror` for Windows-specific codes.

Failures that never reached the operating system — an internal overflow or
bounds condition — surface as a plain `OSError` with a descriptive message and
no `errno`, because there is no system code to report.

### Rust stream observability (internal)

Both internal helpers emit `tracing` diagnostics; the crate installs no
subscriber, so the embedding application owns subscriber configuration. Each
successful read or write logs a `debug` event (with the byte count and
platform), every `EINTR` retry logs a `warn`, and fatal I/O failures,
zero-progress writes, and length-conversion overflows log an `error`. The pump
and consume loops run inside an operation span that carries the `operation` and
`buffer_size` fields and, on completion, records `total_bytes` and the
cumulative `EINTR` `read_retries`/`write_retries` counts. The span sits at
`error` level so the `warn`/`error` events retain their operation context even
when the subscriber is filtered to `warn`/`error`; it emits no log line itself.

One further `debug` event reports the pump's own state rather than an
individual read or write. When a downstream stage hangs up early — the
`head`-style exit, where a consumer stops reading before the producer has
finished — the pump latches its writer closed and keeps draining the upstream
reader to EOF. That transition logs:

```text
broken pipe; draining reader    bytes_transferred=<count>
```

`bytes_transferred` is the number of bytes that reached the downstream stage
before it hung up, so `0` means it closed before receiving anything.

The event is not itself an error. It records that the pump classified the
writer's closure as non-fatal and *began* draining the rest of the input, which
is what stops a producer blocking forever on a pipe nobody is reading.

It is emitted the moment the writer latches closed, before the drain finishes,
so it is not a report of success. The pump returns success only if the drain
then reaches EOF; a read that fails fatally afterwards still propagates as an
`OSError`, on a run where this event was already emitted.

It does not, on its own, say *why* the downstream stage stopped reading. A
consumer that finished by design, as `head` does, and one that crashed partway
through can both close the pipe after the same number of bytes. Read the event
alongside that stage's exit status: a zero exit means the early stop was
deliberate, and a non-zero exit means the stage failed — in which case the
pipeline still fails through the usual fail-fast path, even though the pump
itself succeeded.

Both the `splice` fast path and the read/write fallback emit the event
identically, so the message does not depend on which path handled the transfer.

### Why a hop fell back to Python

Selecting the `rust` backend does not guarantee every inter-stage hop takes it.
Handing the raw pipe descriptors to the Rust pump can fail in ways that are not
errors — the hop simply runs on the Python pump instead and produces the same
result, slower. Nothing surfaces to the caller, so a deployment that has
quietly stopped taking the fast path looks exactly like one that never had it.

Each fall-back is recorded on the `cuprum._pipeline_streams` logger with a
`cuprum_action` of `rust_pump_declined` and a `cuprum_reason`:

Table 1: reasons an inter-stage hop declines the Rust pump

| `cuprum_reason`             | Meaning                                                                                     |
| --------------------------- | ------------------------------------------------------------------------------------------- |
| `raw_fd_unavailable`        | at least one asyncio transport exposed no raw descriptor, so there was nothing to hand over |
| `reader_unresumable`        | the reader transport exposes `pause_reading` but not `resume_reading`, left unpaused        |
| `reader_pause_failed`       | the reader transport could not be paused, so asyncio might still consume the descriptor     |
| `blocking_mode_unavailable` | the descriptors could not be switched to the blocking mode the pump requires                |

These sit at `DEBUG`, not `WARNING`: a fall-back is a routing decision rather
than a fault, and on platforms where the fast path does not apply every hop
would otherwise warn. Raise that one logger when investigating throughput:

```python
import logging

logging.basicConfig(level=logging.INFO)
logging.getLogger("cuprum._pipeline_streams").setLevel(logging.DEBUG)
```

`raw_fd_unavailable` on every hop usually means the streams are not real OS
pipes. The others indicate the descriptors were found but could not be borrowed
safely, which is worth investigating rather than accepting.

### A pump failure hidden by cancellation

Cancelling a pipeline while the Rust pump is mid-transfer tells the caller
about the cancellation, not about anything that went wrong inside the pump.
Such a failure is recorded on the same logger under a `cuprum_action` of
`rust_pump_failed_after_cancel`, with the original traceback attached, so it
stays diagnosable instead of vanishing behind the cancellation. It sits at
`DEBUG` too, so the logger adjustment above reveals it.

### A teardown step that failed and was ignored

Handing the descriptors back is best-effort: resuming the reader transport,
restoring the descriptors' blocking mode, and closing the writer after the pump
has settled all run while the hop is unwinding, so an error there is suppressed
rather than raised. The asyncio transport owns the original writer descriptor.
Rust owns and closes only the separate resource derived from the duplicate
after the native call begins; the native shim closes the duplicate itself if
native loading or platform preparation fails. Python closes that duplicate only
when setup or executor submission fails. No descriptor number is closed by both
owners. Each suppression records a `DEBUG` event with a `cuprum_action` of
`rust_pump_teardown_failed`, a `cuprum_site` naming the step — `resume`,
`restore_blocking`, or `writer_close` — and the exception class and errno. The
record carries nothing drawn from the transfer itself.

An `EBADF` at `writer_close` is therefore not expected merely because Rust
completed: the transport is closing its distinct original descriptor. Any
`writer_close` error, like errors at the other two sites, indicates a teardown
problem worth investigating. The `resume` and `restore_blocking` records come
from the `cuprum._pipeline_stream_fds` logger; `writer_close` comes from
`cuprum._pipeline_streams`.

### Counting pump routing decisions

Aggregating debug logs answers "why did this hop fall back?" one record at a
time. To count the same decisions instead, register a pump observer. It is a
separate channel from `sh.observe`: pump events describe an internal routing
decision rather than a command's lifecycle, so they are not `ExecEvent` values
and never reach an observe hook. An `ExecEvent` consumer registered elsewhere
in the process is unaffected.

The channel counts declines, Rust writer-resource hand-off outcomes,
post-cancellation failures, and native-pump cleanup. A successful hand-off
emits a `handoff` event and increments
`cuprum_rust_pump_handoff_total{outcome="submitted"}` once. The same counter
records each failed hand-off outcome once, so it can show both the number of
hops that were submitted successfully and each terminal hand-off failure.

Cancellation emits `PumpEvent.phase="cleanup_started"` when it starts waiting
for native worker cleanup. It emits `PumpEvent.phase="cleanup_completed"` when
that cleanup releases descriptor ownership. `PumpEvent.duration_s` is the
monotonic cleanup-wait duration and is set only on `cleanup_completed`. The
executor worker retains descriptor ownership until it settles, so this cleanup
must complete before the pipeline can finish tearing down the hop.

Cleanup can also be correlated with the active pipeline-stage span. Register
the same `TracingHook` with both `sh.observe(hook)` and
`observe_pump(hook.record_pump_event)`. For each inter-stage hop, the cleanup
events reuse the source stage's `ExecId` only to find its existing open span;
the token is not a trace attribute, and no PID is used for correlation. The
hook emits `cuprum.cleanup_started` and `cuprum.cleanup_completed`. Both events
carry the bounded attributes `operation="native_pump_cleanup"` and `outcome`
(`"started"` or `"completed"`); only the completion event carries `duration_s`,
in monotonic seconds. No descriptor numbers, command arguments, exception text,
or other unbounded values are emitted. An event without a matching active span
is dropped safely; cleanup tracing neither changes span status nor ends the
span.

#### Cleanup DEBUG records

Cancellation cleanup also emits `DEBUG` records on the
`cuprum._pipeline_streams` logger. Each record has
`cuprum_action="rust_pump_cleanup"` and
`cuprum_operation="native_pump_cleanup"`; start records have
`cuprum_outcome="started"`, while completion records have
`cuprum_outcome="completed"` and the completion-only `cuprum_duration_s` field.
A completion record is emitted only after the native worker has released
descriptor ownership. These logs and pump events are emitted during
cancellation cleanup.

```python
from cuprum.adapters.metrics_adapter import InMemoryMetrics
from cuprum.adapters.pump_metrics import PumpMetricsHook
from cuprum.pump_observation import observe_pump

metrics = InMemoryMetrics()

with observe_pump(PumpMetricsHook(metrics)):
    pipeline.run_sync()

print(metrics.counters)  # {'cuprum_rust_pump_declined_total': 2.0}
```

`PumpMetricsHook` takes the same `MetricsCollector` protocol as `MetricsHook`,
so one collector can back both channels:

```python
from cuprum import sh
from cuprum.adapters.metrics_adapter import MetricsHook

with sh.observe(MetricsHook(metrics)), observe_pump(PumpMetricsHook(metrics)):
    pipeline.run_sync()
```

Table 2: counters emitted by `PumpMetricsHook`

| Counter                                      | Labels    | Incremented when                                                 |
| -------------------------------------------- | --------- | ---------------------------------------------------------------- |
| `cuprum_rust_pump_declined_total`            | `reason`  | a hop fell back from the Rust pump to the Python pump            |
| `cuprum_rust_pump_failed_after_cancel_total` | none      | a cancelled hop's Rust worker failure was consumed and recorded  |
| `cuprum_rust_pump_cleanup_total`             | none      | native cleanup completed after cancellation                      |
| `cuprum_rust_pump_cleanup_duration_seconds`  | none      | one monotonic duration was observed for completed native cleanup |
| `cuprum_rust_pump_handoff_total`             | `outcome` | a Rust writer-resource hand-off outcome was reached              |

The cleanup metrics are emitted only when callers register
`observe_pump(PumpMetricsHook(metrics))`. `cuprum_rust_pump_cleanup_total` is
incremented once for every completed native cleanup, and
`cuprum_rust_pump_cleanup_duration_seconds` records one duration observation
for each such cleanup. Both metrics are unlabelled. The `reason` label on the
decline counter retains the bounded cardinality described below.

The `outcome` label on `cuprum_rust_pump_handoff_total` is closed to exactly
`submitted`, `blocking_setup_failed`, `executor_submission_rejected`,
`native_load_failed`, `buffer_validation_failed`,
`platform_writer_transfer_failed`, `native_io_failed`,
`duplicate_writer_failed`, and `reader_preparation_failed`. `outcome` is the
only label on this counter. Descriptor numbers, Windows handle values, errno
values, exception types, exception messages, and tracebacks never become metric
labels.

The `reason` label takes exactly the values in Table 1, plus `unknown`, and
nothing else. Table 1's values are published as the `RustPumpDeclineReason`
enum and `unknown` as `cuprum.adapters.pump_metrics.UNKNOWN_DECLINE_REASON`, so
a dashboard can enumerate the series it will see:

```python
from cuprum import RustPumpDeclineReason
from cuprum.adapters.pump_metrics import UNKNOWN_DECLINE_REASON

print([reason.value for reason in RustPumpDeclineReason] + [UNKNOWN_DECLINE_REASON])
```

`unknown` is a guard rather than an outcome: it is what a decline whose reason
is not an enum member would be labelled, and no call site produces one. It is
listed because a dashboard filtering on the enum alone would drop such a
decline silently rather than showing it.

`PumpEvent` is a public dataclass and performs no run-time validation, so a
caller can construct one carrying any object as its `reason`. The hook
therefore checks the value against `RustPumpDeclineReason` before labelling and
degrades anything else to `unknown`; a hand-built event cannot widen the label
domain.

Nothing derived from a descriptor, an argument vector, or an exception reaches
a label, so the series count is fixed. A successful hand-off increments the
handoff counter once with `outcome="submitted"`. The `DEBUG` records above are
unchanged — the counters supplement them rather than replacing them.

> **Note**
> A pump hook that raises is reported on the `cuprum.pump_observation` logger
> at `WARNING` with its traceback, and the hop continues. This differs from
> `sh.observe` hooks, whose exceptions fail the command being observed. The
> difference is deliberate: a decline is recorded on the path that falls back
> to the Python pump and completes the hop, so a misconfigured metrics backend
> must not be able to abort a pipe hop that would otherwise have succeeded.
> Only `Exception` instances are reported and suppressed. Everything else
> propagates unchanged: `SystemExit`, `KeyboardInterrupt`, and
> `asyncio.CancelledError`. The last matters because one of the two emission
> sites is cancellation unwinding, so a hook running there must not be able to
> absorb the cancellation the caller asked for. Hooks must be synchronous; one
> that returns an awaitable is reported and discarded.

### A pump hand-off failed before submission

If Cuprum cannot duplicate the writer descriptor, the hand-off is rolled back
and the original exception is re-raised without a hand-off outcome. If executor
submission is rejected, Cuprum emits `executor_submission_rejected` and
re-raises after rollback. A blocking-mode failure selects the Python fallback
and emits `blocking_setup_failed`. The `cuprum._pipeline_streams` logger
records a bounded `DEBUG` diagnostic for these setup failures with
`cuprum_action="rust_pump_handoff_failed"`, the exception class, and `errno`
when available. Descriptor numbers and exception text are not logged.

### Choosing a stream backend

Most users should leave backend selection on `auto`. This uses the Rust pathway
when the native extension is installed and falls back cleanly to pure Python
otherwise. Select `python` when the pure Python path is required regardless of
wheel availability, for example when debugging, reproducing an issue on a pure
Python installation, or relying on Python-only capture features. Select `rust`
for benchmarking or throughput-heavy workloads and to require the native
extension (fail if unavailable).

Set `CUPRUM_STREAM_BACKEND` before first backend resolution in the process. For
example:

```bash
CUPRUM_STREAM_BACKEND=rust uv run python my_script.py
```

If the environment variable is changed after Cuprum has already resolved the
backend in the current process, the cached result will continue to be used.

The backend selection is active for inter-stage stream pumping in pipelines.
When the Rust backend is selected, data transfer between pipeline stages uses
the Rust extension outside the GIL via `loop.run_in_executor()`. Stream
consumption (stdout/stderr capture) currently always uses the Python pathway
regardless of the backend setting; this ensures line callbacks and echo
features remain available.

Pipeline pumping applies an additional safety guard: if Rust is selected but
Cuprum cannot extract raw file descriptors from asyncio transports for a
specific transfer, it falls back to the Python pump for that transfer. This
fallback is automatic and transparent to callers.

Forced Rust mode is intentionally strict. If `CUPRUM_STREAM_BACKEND=rust` is
set and the Rust extension is unavailable, pipeline execution raises
`ImportError` instead of silently falling back.

Current Rust acceleration applies to inter-stage pipeline pumping. For
high-throughput, multi-stage pipelines, this can reduce per-chunk overhead and
deliver substantial multi-fold throughput improvements on large transfers,
especially on Linux pipe-to-pipe workloads where `splice()` is available. For
small outputs, the difference is often negligible. When stdout/stderr capture,
custom encoding/error handling, or line-oriented callbacks matter more than raw
throughput, prefer `python`. The current backend selection does not change
capture semantics: stdout/stderr capture still uses the Python pathway.

Run Cuprum's end-to-end benchmark suite to measure a workload before
standardizing on `rust` for a production path. The benchmark suite gives a
better answer than a fixed rule of thumb when payload size, platform, or
callback behaviour differ from the default scenarios.

For parent-side tee and capture profiling, use the dedicated harness documented
in `benchmarks/README.md`. That harness replays deterministic base64 fixtures
into the parent process and records text-first `perf` artefacts for the
`echo=True` and `capture=True` consumption paths. It is the right tool when
investigating sink write cost, line-callback overhead, capture accumulation, or
the boundary between inter-stage pumping and final stream consumption.

The profiling harness accepts a `BackendSelector` dependency for benchmark
workers that need to force a backend around a single parent-side run. The
default selector mutates `CUPRUM_STREAM_BACKEND` process-wide while holding a
backend lock, clears Cuprum's cached backend choice for the scoped run, and
restores the original environment afterwards. It is intentionally non-reentrant
on the same thread: nested selector activation raises `RuntimeError` rather
than risking a stale environment value or backend cache leak. Avoid wrapping one
`BackendSelector` activation inside another; start a separate worker process
or let the outer selector own the full profiled run.

Both backends are tested for behavioural parity across edge cases including
empty streams, multibyte UTF-8 at chunk boundaries, broken pipes (where the
downstream stage exits before the upstream finishes), and backpressure under
large payloads. The test suite verifies that pipeline output is identical
regardless of which backend is active, so switching between backends does not
change observable behaviour.

The stream test suite also includes property-based coverage using Hypothesis.
These tests generate randomized payload bytes and randomized chunk boundaries,
run them through real pipelines, and assert byte-preservation by comparing
deterministic hexadecimal output. This provides broad regression coverage for
content integrity across both Python and Rust pumping pathways.

Cuprum also tests the Python backend's pure line-callback splitting helpers
directly. Those tests prove that completed lines and final partial lines
account for all generated text, and that recognized line endings are stripped
without editing the rest of the line. In development environments, CrossHair
adds bounded symbolic checks for the same contracts; those checks are skipped
on Python versions where CrossHair cannot trace the active bytecode.

### Benchmark suite

Cuprum includes an opt-in benchmark suite for stream-performance tracking.
Benchmark modules are intentionally excluded from normal test runs unless
`CUPRUM_RUN_BENCHMARKS=1` is set.

Run microbenchmarks (pytest-benchmark):

```bash
make benchmark-micro
```

This executes `benchmarks/test_stream_microbenchmarks.py` and writes benchmark
results to `dist/benchmarks/microbenchmarks.json`.

Run end-to-end throughput benchmarks (hyperfine):

```bash
make benchmark-e2e
```

This executes `benchmarks/pipeline_throughput.py` and writes throughput results
to `dist/benchmarks/pipeline-throughput.json`.

Generate a dry-run benchmark plan without executing hyperfine:

```bash
UV_CACHE_DIR=.uv-cache UV_TOOL_DIR=.uv-tools uv run python \
  benchmarks/pipeline_throughput.py \
  --smoke \
  --dry-run \
  --worker-iterations 20 \
  --output /tmp/pipeline-throughput-plan.json
```

Dry-run output includes scenario metadata, command lines, benchmark profile
metadata, worker iteration count, and whether the Rust extension is available
in the current environment.

The `--worker-iterations` option (default `20`) controls how many pipeline
executions are batched inside a single measured worker process. Higher values
reduce hyperfine timing overhead per pipeline run; the recorded mean is the
total elapsed time for all iterations combined. The worker `--iterations` flag,
which hyperfine scenario commands pass directly, mirrors this setting. Do not
compare ratchet baselines produced with different `worker_iterations` values;
the benchmark profile validation rejects mismatched plans automatically.

Benchmark commands invoke the Python interpreter directly via `python_bin`
(resolved from `sys.executable` at plan-generation time) rather than through
`uv run`, so measured runtimes exclude launcher overhead.

Benchmark iteration options are intentionally bounded to prevent accidental
resource exhaustion in local runs or CI jobs. Pipeline throughput runs accept
`--warmup` and `--runs`; tee profiling runs accept `--warmup-count` and
`--repeat-count`. Each value must be at most `1000`.

Interpretation notes:

- pump-latency microbenchmarks reflect inter-stage pipeline transfer overhead;
- consume-throughput microbenchmarks reflect captured stdout read/decode
  throughput (currently the Python consume path);
- end-to-end hyperfine runs measure batched worker-pipeline runtime and include
  a Rust scenario only when the Rust extension is available.

#### Scenario matrix

The end-to-end throughput suite exercises a systematic matrix of benchmark
scenarios for each available backend:

- payload sizes: small (1 KB), medium (1 MB), and large (100 MB);
- pipeline depth: single-stage (writer|sink, no passthrough) and multi-stage
  (writer|passthrough|sink);
- line callbacks: with (line-by-line sink processing) and without (binary bulk
  read).

This produces 12 scenarios per backend. In smoke mode, payload sizes are
reduced (1 KB, 64 KB, 1 MB) to keep validation fast while exercising the full
matrix shape. Scenarios follow a systematic naming convention:
`{backend}-{size}-{depth}-{callbacks}`, for example `python-small-single-nocb`
or `rust-large-multi-cb`.

### Linux splice() optimization

On Linux, the Rust extension automatically uses the `splice()` system call for
pipe-to-pipe transfers. This provides zero-copy data movement entirely within
the kernel, offering significant throughput improvements for large pipeline
transfers.

The optimization is transparent to users:

- Automatically enabled on Linux when using pipe file descriptors
- Falls back to read/write for unsupported file descriptor types (files, some
  sockets)
- No configuration required

For maximum benefit, ensure pipeline stages use pipes (the default for
`Pipeline` execution) rather than temporary files.

### Build prerequisites for native extensions

Contributors who want to build or develop the optional Rust extension from
source need the following tools installed:

- **Rust toolchain (rustc and cargo) 1.85 or later.** The Rust crate uses
  `edition = "2024"`, which requires Rust 1.85+. Install via
  [rustup](https://rustup.rs/):

  ```bash
  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
  ```

  cargo ships as part of the standard rustup installation and does not need to
  be installed separately.

- **maturin** (the Rust-to-Python build bridge). maturin is pinned as a dev
  dependency and is installed automatically when you run `uv sync --group dev`.
  Alternatively, install it manually:

  ```bash
  pip install maturin==1.15.0
  ```

To build and install the Rust extension in development mode, run
`maturin develop` from the project root:

```bash
maturin develop
```

This compiles the Rust crate, links the resulting shared library into the
Cuprum package, and makes the extension available for import. To verify the
extension is working:

```bash
python -c "import cuprum; print(cuprum.is_rust_available())"
```

The command should print `True` when the Rust extension is available.

Pure Python wheels do not require a Rust toolchain. Running `uv build --wheel`
produces a pure Python wheel using `uv_build` without any Rust dependencies.

### Troubleshooting

This section addresses common issues when working with the optional Rust
extension.

**Missing wheels on unsupported platforms.** Pre-built native wheels are
published for common platforms: Linux (x86_64, aarch64), macOS (x86_64, arm64),
and Windows (x86_64, arm64). On other platforms, `pip install cuprum` installs
the pure Python wheel automatically. The pure Python wheel provides the same
functionality without Rust acceleration. Contributors who want Rust
acceleration on unsupported platforms can build from source using the
prerequisites described above and running `maturin develop`.

**Forced fallback behaviour.** The `CUPRUM_STREAM_BACKEND` environment variable
controls which stream implementation is used:

- `auto` (default): uses the Rust pathway when available, otherwise falls
  back to the Python pathway and emits a fallback log.
- `python`: forces the pure Python pathway regardless of whether the Rust
  extension is installed.
- `rust`: forces the Rust pathway and raises `ImportError` if the extension
  is unavailable.

If `CUPRUM_STREAM_BACKEND=rust` is set but the Rust extension is not installed,
pipeline execution raises `ImportError` instead of falling back. To diagnose
whether the extension is available, run:

```bash
python -c "import cuprum; print(cuprum.is_rust_available())"
```

See the "Choosing a stream backend" section above for full details on backend
selection.

**Benchmark result interpretation.** When reading benchmark results, keep the
following in mind:

- Small payloads show negligible difference between Python and Rust pathways.
  The overhead being avoided is per-chunk, and small payloads have few chunks.
- The `splice()` optimization is Linux-only. macOS and Windows use
  read/write loops, so Rust throughput gains are smaller on those platforms.
- The CI comparison summary reports speedup as `python_mean / rust_mean`.
  Values above `1.0x` mean Rust was faster.
- Run the end-to-end benchmark suite to measure performance on the target
  workload and platform before drawing conclusions.

See the "Benchmark suite" section above for scenario definitions and metric
details.

### CI build commands

The package's continuous integration runs type checking and tests across a
Python version matrix (currently 3.12 through 3.14, with pre-release
interpreters tracked on an experimental, allowed-to-fail basis), plus
formatting, lint, and coverage checks.

A benchmark ratchet also runs on changes to performance-relevant code and
compares the Rust and Python backends against rolling history from prior
runs. It fails a build when a scenario's `rust_mean / python_mean` ratio
regresses beyond a fixed, noise-adjusted threshold, so the two backends are
kept behaviourally and performance-comparable release over release. A single
noisy measurement is confirmed by a second run before it can fail a build,
which keeps runner-to-runner variance from being mistaken for a genuine
regression.

To build distributable artefacts:

- Pure Python wheel:

```bash
uv build --wheel --out-dir dist
```

- Native wheel (per platform):

```bash
maturin build --release --out wheelhouse \
  --manifest-path rust/cuprum-rust/Cargo.toml
```

For Linux wheels, the native build runs inside a manylinux-compatible container
and uses a matching compatibility tag plus explicit interpreter selection:

```bash
maturin build --release --manylinux 2_28 \
  -i python3.13 --out wheelhouse \
  --manifest-path rust/cuprum-rust/Cargo.toml
```

The CI workflow supplies `manylinux 2_28` via the maturin action configuration
to ensure the resulting wheel tags are manylinux-compatible.

### Verification procedure

The canonical verification sequence is:

1. Install the pure Python wheel and confirm the Rust probe returns `False`.
2. Force-reinstall the native wheel and confirm the Rust probe returns `True`.
3. Compare metadata (name, version, requires-python, dependencies, and
   classifiers) across the two installs to detect drift.
