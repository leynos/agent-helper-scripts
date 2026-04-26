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

Downstream services can fetch metadata via `catalogue.visible_settings()` to
propagate noise filters and documentation links alongside the allowlist.

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

from cuprum import ECHO, Program, ProgramCatalogue, ProjectSettings, scoped, sh

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

with scoped(allowlist=catalogue.allowlist):
    result = pipeline.run_sync()

print(result.stdout)  # "HELLO"
print([stage.exit_code for stage in result.stages])  # per-stage exit codes
```

Notes:

- Only the final stage's stdout is captured; intermediate stage stdout is
  streamed and represented as `None` in `result.stages`.
- `echo=True` echoes the final stage stdout and all stage stderr streams to
  their configured sinks.
- Pipelines fail fast: when a stage exits non-zero, Cuprum terminates the
  remaining stages. The failing stage is available via `result.failure` /
  `result.failure_index`.

## Execution runtime

`SafeCmd.run` executes curated commands asynchronously with predictable capture
and echo semantics and returns a structured `CommandResult`:

- `stdout` and `stderr` are captured by default. Set `capture=False` to stream
  only; the result will carry `None` for output fields.
- `echo=True` tees stdout/stderr to the parent process while still capturing
  them when `capture=True`.
- Pass an `ExecutionContext` via the `context` parameter to override execution
  details:
  - `env` overlays key/value pairs on top of the current environment without
    mutating `os.environ`; use it to pass per-command settings.
  - `cwd` sets the working directory for the subprocess when provided.
  - `cancel_grace` controls how long Cuprum waits after `SIGTERM` (termination
    signal) before escalating to `SIGKILL` (kill signal).
  - `stdout_sink` and `stderr_sink` route echoed output to alternative text
    streams when `echo=True`.
  - `encoding` and `errors` configure how captured output is decoded; defaults
    are `"utf-8"` with `"replace"`.
- `exit_code`, `pid`, and `ok` on the `CommandResult` make it easy to branch on
  success.

```python
from cuprum import ECHO, ExecutionContext, sh


async def greet() -> None:
    cmd = sh.make(ECHO)("-n", "hello runtime")
    ctx = ExecutionContext(env={"GREETING": "1"})
    result = await cmd.run(echo=True, context=ctx)
    if not result.ok:
        raise RuntimeError(f"echo failed: {result.exit_code}")
    print(result.stdout)
```

If the awaiting task is cancelled while a command is running, Cuprum sends
`SIGTERM` to the subprocess, waits for a short grace period, and then escalates
to `SIGKILL` to ensure the child process is cleaned up.

### Synchronous execution

For scripts or contexts where async/await is not available, use `run_sync()`:

```python
from cuprum import ECHO, ExecutionContext, sh


def greet() -> None:
    cmd = sh.make(ECHO)("-n", "hello sync")
    ctx = ExecutionContext(env={"GREETING": "1"})
    result = cmd.run_sync(echo=True, context=ctx)
    if not result.ok:
        raise RuntimeError(f"echo failed: {result.exit_code}")
    print(result.stdout)
```

`run_sync()` accepts the same parameters as `run()` and returns an identical
`CommandResult`. It drives the event loop internally via `asyncio.run()`.

## Execution context and hooks

Cuprum provides `CuprumContext` to scope allowlists and execution hooks across
your application. Contexts are backed by a `ContextVar`, giving you automatic
isolation across threads and async tasks.

When you call `SafeCmd.run()` or `run_sync()`, Cuprum automatically:

1. Checks the current context's allowlist and raises `ForbiddenProgramError` if
   the program is not permitted.
2. Invokes all registered before hooks (in FIFO order) before process execution.
3. Invokes all registered after hooks (in LIFO order) after the process
   completes.

**Empty allowlist behaviour:** When no context is established (or the context
has an empty allowlist), all programs are permitted. This permissive default is
intentional to ease adoption but weakens safety; establish an explicit
allowlist via `scoped()` to enforce policy once onboarded.

### Scoped contexts

Use `scoped()` to establish a narrowed execution context within a code block:

```python
from cuprum import ECHO, LS, scoped

# Start with a base allowlist
with scoped(allowlist=frozenset([ECHO, LS])) as ctx:
    assert ctx.is_allowed(ECHO)  # True
    assert ctx.is_allowed(LS)  # True

    # Narrow further in nested scope
    with scoped(allowlist=frozenset([ECHO])) as inner:
        assert inner.is_allowed(ECHO)  # True
        assert inner.is_allowed(LS)  # False (narrowed out)
```

Key properties of `scoped()`:

- When the parent allowlist is empty, the provided allowlist becomes the new
  base.
- When the parent has programs, the new allowlist is intersected (can only
  narrow, never widen).
- Context is automatically restored when the block exits, even on exception.

### Accessing the current context

Use `current_context()` or `get_context()` to access the current execution
context:

```python
from cuprum import ECHO, current_context, scoped

with scoped(allowlist=frozenset([ECHO])):
    ctx = current_context()
    if ctx.is_allowed(ECHO):
        print("ECHO is allowed")
```

### Dynamic allowlist extension

Use `allow()` to temporarily add programs to the current context:

```python
from cuprum import ECHO, LS, allow, current_context, scoped

with scoped(allowlist=frozenset([ECHO])):
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
from cuprum import LS, allow, current_context, scoped

with scoped():
    reg = allow(LS)
    assert current_context().is_allowed(LS)
    reg.detach()  # Remove LS from allowlist
    assert not current_context().is_allowed(LS)
```

### Before and after hooks

Register hooks to run before or after command execution:

```python
from cuprum import ECHO, before, after, scoped, sh


def log_before(cmd):
    print(f"About to run: {cmd.program}")


def log_after(cmd, result):
    print(f"Finished {cmd.program} with exit code {result.exit_code}")


with scoped(allowlist=frozenset([ECHO])):
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
from cuprum import before, current_context, scoped


def my_hook(cmd):
    pass


with scoped():
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

from cuprum import ECHO, logging_hook, scoped, sh

logger = logging.getLogger("myapp.commands")

with scoped(allowlist=frozenset([ECHO])):
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

Hooks can be used for structured logging, metrics, or tracing without coupling
Cuprum to a specific telemetry library.

```python
from cuprum import ECHO, ExecEvent, scoped, sh
from cuprum.sh import ExecutionContext


events: list[ExecEvent] = []


def capture(ev: ExecEvent) -> None:
    events.append(ev)


with scoped(allowlist=frozenset([ECHO])), sh.observe(capture):
    ctx = ExecutionContext(tags={"run_id": "demo"})
    sh.make(ECHO)("-n", "hello events").run_sync(context=ctx)

stdout_lines = [ev.line for ev in events if ev.phase == "stdout"]
exit_events = [ev for ev in events if ev.phase == "exit"]
assert "hello events" in stdout_lines
assert exit_events[0].tags["run_id"] == "demo"
```

`ExecutionContext.tags` is merged into each event's `tags` mapping. Cuprum also
adds default tags such as the project name and pipeline stage metadata.

### Thread and async task isolation

`CuprumContext` uses Python's `ContextVar` mechanism, which provides automatic
isolation:

- Each thread gets its own context value.
- Each async task inherits the context from its creator and can modify it
  independently.

This isolation allows `scoped()` to be used in concurrent code without context
leaking between threads or tasks:

```python
import asyncio

from cuprum import ECHO, LS, current_context, scoped


async def worker(name: str, programs):
    with scoped(allowlist=programs):
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

from cuprum import ECHO, scoped, sh
from cuprum.adapters.logging_adapter import structured_logging_hook

logging.basicConfig(level=logging.DEBUG)

with scoped(allowlist=frozenset([ECHO])):
    hook = structured_logging_hook()
    with sh.observe(hook):
        sh.make(ECHO)("hello").run_sync()
```

The hook attaches `cuprum_*` prefixed extra fields to log records:

- `cuprum_phase`: Event phase (plan, start, stdout, stderr, exit)
- `cuprum_program`: Program being executed
- `cuprum_argv`: Full argument vector
- `cuprum_pid`: Process ID (when available)
- `cuprum_exit_code`: Exit code (for exit events)
- `cuprum_duration_s`: Duration in seconds (for exit events)
- `cuprum_tags`: Event tags as a dict

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
from cuprum import ECHO, scoped, sh
from cuprum.adapters.metrics_adapter import InMemoryMetrics, MetricsHook

metrics = InMemoryMetrics()

with scoped(allowlist=frozenset([ECHO])):
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

All metrics include `program` and `project` labels.

To integrate with a real metrics library like `prometheus_client`, implement
the `MetricsCollector` protocol:

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
from cuprum import ECHO, scoped, sh
from cuprum.adapters.tracing_adapter import InMemoryTracer, TracingHook

tracer = InMemoryTracer()

with scoped(allowlist=frozenset([ECHO])):
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
- `cuprum.exit_code`: Exit code (set on span end)
- `cuprum.duration_s`: Duration in seconds (set on span end)
- `cuprum.project`: Project name from tags
- `cuprum.pipeline_stage_index`: Pipeline stage index (if applicable)

Output lines (stdout/stderr) are recorded as span events when
`record_output=True` (the default).

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
