# CmdMox Usage Guide

CmdMox provides a fluent API for mocking, stubbing and spying on external
commands in your tests. This guide shows common patterns for everyday use.

## Getting started

Install the package and enable the pytest plugin:

```bash
pip install cmd-mox
```

On Windows the wheel also pulls in `pywin32`, which provides the `win32pipe`
and `win32file` modules that power CmdMox's named-pipe IPC transport.

In your `conftest.py`:

```python
pytest_plugins = ("cmd_mox.pytest_plugin",)
```

Each test receives a `cmd_mox` fixture that provides access to the controller
object. The plugin enters replay mode before the test body executes and
performs verification during teardown, so most tests only need to declare
expectations and exercise the code under test. If both the test body and
verification fail, the verification error is suppressed so the original test
failure surfaces. Automatic replay/verify can be disabled globally via the
``cmd_mox_auto_lifecycle`` pytest.ini option or per test with
``@pytest.mark.cmd_mox(auto_lifecycle=False)``. Command-line flags
``--cmd-mox-auto-lifecycle`` and ``--no-cmd-mox-auto-lifecycle`` override both
settings for a single pytest run.

## Platform support

CmdMox supports Linux, macOS and Windows. Shims are generated as POSIX symlinks
on Unix-like systems and as `.cmd` launchers on Windows so that `CreateProcess`
resolves them via `PATHEXT`. The batch launchers embed the active Python
interpreter and forward all arguments to the shared `shim.py`, so no additional
wrappers or entry points are required.

When CmdMox enters replay mode on Windows it ensures `.CMD` is present in the
effective `PATHEXT` value, even if developers customised their shell to omit
the extension. The generated launchers always emit CRLF line endings and escape
carets/percent signs so the Windows command processor parses them consistently
with native batch scripts, even when arguments or installation paths include
spaces and other metacharacters. CmdMox also filters duplicate command names on
case-insensitive filesystems so two mocks whose names only differ by casing
cannot trample each other's shim files. At runtime the shim collapses doubled
carets (``^^``) in Windows arguments into single carets so multi-layer batch
escaping does not leak into IPC payloads. Arguments that genuinely need
repeated carets will therefore reach the server with a single literal caret.

Deeply nested workspaces can easily exceed the traditional `MAX_PATH` limit on
Windows. The environment manager now asks the filesystem for a short (8.3)
alias whenever the shim directory path would overflow the limit, ensuring shims
remain invokable while still cleaning up the real directory afterwards. PATH
filtering honours the underlying filesystem semantics too, so variations in
casing no longer leave behind duplicate entries when passthrough spies merge
their lookup paths.

Importing :mod:`cmd_mox.shim` no longer mutates ``sys.path`` or
``sys.modules``. The bootstrap that prefers stdlib modules over editable
installs runs only when the shim entrypoint executes. When shim helpers are
reused directly, ``cmd_mox._shim_bootstrap.bootstrap_shim_path()`` should be
called during setup first.

When you need to make an explicit decision in a test module (for instance when
using the context manager API), import the helper re-exported from the package:

```python
from cmd_mox import skip_if_unsupported

skip_if_unsupported()
```

`skip_if_unsupported` defers to `pytest.skip` on unsupported platforms. If you
only need to gate a code path, `cmd_mox.is_supported_platform()` returns a
boolean instead. Advanced tests can override the detected platform by setting
the `CMD_MOX_PLATFORM_OVERRIDE` environment variable, which is primarily useful
for simulating alternative environments inside CI pipelines (for example to
exercise Windows-specific shims from a Linux runner).

The cmd-mox test suite also uses the `pytest.mark.requires_unix_sockets` marker
for scenarios that need to bind a Unix domain socket. Marking these tests keeps
them green on platforms (or CI sandboxes) that disallow Unix sockets entirely.

## Basic workflow

CmdMox follows a strict record → replay → verify lifecycle. First declare
expectations, then run your code with the shims active, finally verify that
interactions matched what was recorded.

The three phases are defined in the design document:

1. **Record** – describe each expected command call, including its arguments
   and behaviour.
2. **Replay** – run the code under test while CmdMox intercepts command
   executions.
3. **Verify** – ensure every expectation was met and nothing unexpected
   happened.

These phases form a strict sequence for reliable command-line tests.

A typical test brings the three phases together:

```python
cmd_mox.mock("git").with_args("clone", "repo").returns(exit_code=0)

my_tool.clone_repo("repo")
# Replay begins automatically before the test function executes; verification runs during teardown.
```

## Stubs, mocks and spies

Use the controller to register doubles:

```python
cmd_mox.stub("ls")
cmd_mox.mock("git")
cmd_mox.spy("curl")
```

- **Stubs** provide canned responses without strict checking.
- **Mocks** enforce exact usage during verification.
- **Spies** record every call for later inspection and can behave like stubs.

Each call returns a `CommandDouble` that offers a fluent DSL to configure
behaviour.

## Defining expectations

Combine methods to describe how a command should be invoked:

```python
cmd_mox.mock("git") \
    .with_args("clone", "https://example.com/repo.git") \
    .returns(exit_code=0)
```

You can match arguments more flexibly using comparators:

```python
from cmd_mox import Regex, Contains

cmd_mox.mock("curl") \
    .with_matching_args(Regex(r"--header=User-Agent:.*"), Contains("example"))
```

The design document lists the available comparators:

- `Any`
- `IsA`
- `Regex`
- `Contains`
- `StartsWith`
- `Predicate`

Each comparator is a callable that returns `True` on match.
`with_matching_args` expects one comparator per argv element (excluding the
program name, i.e., `argv[1:]`), and `with_stdin` accepts either an exact
string or a predicate `Callable[[str], bool]` for flexible input checks.

## Running tests

Typical pytest usage looks like this:

```python
def test_clone(cmd_mox):
    cmd_mox.mock("git").with_args("clone", "repo").returns(exit_code=0)

    my_tool.clone_repo("repo")
    # No explicit replay() or verify() calls required.
```

The context manager interface is available when pytest fixtures are not in play:

```python
with CmdMox() as mox:
    mox.stub("ls").returns(stdout="")
    mox.replay()
    subprocess.run(["ls"], check=True)
```

If replay aborts—whether because your code raised an exception or you hit
Ctrl+C—`CmdMox` still tears down the environment before surfacing the original
error. The controller catches interruptions during replay startup, stops the
IPC server, removes the shim directory (and its socket), and restores `PATH`
before re-raising so you never leak temporary artefacts between tests.

## Parallel execution and isolation

CmdMox test runs are isolated even when executed in parallel with
``pytest-xdist`` or other multiprocessing strategies. Every controller instance
creates its own temporary shim directory via ``tempfile.mkdtemp`` and the IPC
socket lives inside that directory (`ipc.sock`). The pytest plugin further
decorates the directory prefix with the worker ID and process ID so concurrent
workers never clash on shared filesystems. When the fixture tears down the
environment manager removes the directory, ensuring sockets and shims do not
leak between tests.

To verify that the test suite behaves correctly in parallel, run pytest with
multiple workers:

```bash
pytest -n auto
```

On Windows the dedicated smoke workflow that powers CI can be run via the
Makefile:

```bash
make windows-smoke
```

The target captures IPC debug output in `windows-ipc.log`, facilitating
attachment of shim diagnostics to CI artefacts or reproduction of
Windows-specific issues locally.

Each test continues to receive an independent ``cmd_mox`` fixture; the
environmental changes are scoped to the worker process, so tests cannot observe
one another's shims or sockets. When controllers are constructed manually
outside pytest, the same pattern should be followed—instantiate a new
``cmd_mox.CmdMox`` per test case so that every run receives its own environment
manager.

## Spies and passthrough mode

Spies expose `invocations` (a list of `Invocation` objects) and `call_count`
during and after replay, making it easy to inspect what actually ran:

```python
def test_spy(cmd_mox):
    spy = cmd_mox.spy("curl").returns(stdout="ok")
    run_download()
    assert spy.call_count == 1
```

A spy expectation can also use `times_called(count)`—an alias of
`times(count)`—to require a specific call count during verification.

A spy can also forward to the real command while recording everything:

```python
mox.spy("aws").passthrough()
```

This "record mode" is helpful for capturing real interactions and later turning
them into mocks. During passthrough, the IPC server sends the shim a
`PassthroughRequest` containing the original `PATH` and any
expectation-specific environment overrides. The shim resolves and runs the real
command, then reports the captured `stdout`, `stderr`, and `exit_code` back to
the server before the call returns. The calling process therefore observes the
genuine behaviour while CmdMox records the interaction for later assertions.

For integration tests that need deterministic control over which executable a
passthrough spy invokes, set ``CMOX_REAL_COMMAND_<NAME>`` in the shim
environment. When present, the shim bypasses the PATH lookup and executes the
absolute path specified by the variable. This override is intended solely for
tests—production scenarios should allow the shim to resolve commands from the
original ``PATH`` to avoid masking misconfigurations.

Spies provide assertion helpers inspired by `unittest.mock` that can be called
in the test body or after verification:

```python
spy.assert_called()
spy.assert_called_with("--silent", stdin="payload")
# or, to ensure the spy never executed:
spy.assert_not_called()
```

These methods raise `AssertionError` when expectations are not met and are
restricted to spy doubles.

## Controller configuration and journals

`CmdMox` offers configuration hooks that surface through both the fixture and
the context-manager API:

- `verify_on_exit` (default `True`) automatically calls `verify()` when a replay
  phase ends inside a `with CmdMox()` block. Disable it when you need to manage
  verification manually. Verification still runs if the body raises; when both
  verification and the body fail, the verification error is suppressed so the
  original exception surfaces.
- `max_journal_entries` bounds the number of stored invocations (oldest entries
  are evicted FIFO when the bound is reached). The journal is exposed via
  `cmd_mox.journal`, a `collections.deque[Invocation]` recorded during replay.

The journal is especially handy when debugging:

```python
exercise_system()
assert [call.command for call in cmd_mox.journal] == ["git", "curl"]
# Verification will run during fixture teardown.
```

To intercept a command without configuring a double—for example, to ensure it
is treated as unexpected—register it explicitly. Any invocation of a registered
command without a matching double will be reported as unexpected during
verification:

```python
cmd_mox.register_command("name")
```

CmdMox creates the shim at replay start (or immediately when registration
occurs during an active replay) so the command is routed through the IPC
server, even without a stub, mock, or spy. Shims are cleaned up automatically
during fixture teardown.

## Fluent API reference

The DSL methods closely mirror those described in the design specification. A
few common ones are:

- `with_args(*args)` – require exact arguments.
- `with_matching_args(*matchers)` – match arguments using comparators.
- `with_stdin(data_or_matcher)` – expect specific standard input (`str`) or
  validate it with a predicate `Callable[[str], bool]`.
- `with_env(mapping)` – inject additional environment variables into the
  invocation. The mapping is merged into the recorded `Invocation.env`, applied
  when custom handlers or canned responses run, and does not mutate the test
  process's `os.environ`. Conflicting keys override the caller-provided
  environment so passthrough commands honour the injected values.
- `returns(stdout="", stderr="", exit_code=0)` – static response using text
  values; CmdMox operates in text mode—pass `str` (bytes are not supported).
  Note: For binary payloads, prefer `passthrough()` or encode/decode at the
  boundary (e.g., base64) so handlers exchange `str`.
- `runs(handler)` – call a function to produce dynamic output. The handler
  receives an `Invocation` and should return either a
  `(stdout, stderr, exit_code)` tuple or a `Response` instance.

  Example:

  ```python
  def handler(inv: Invocation) -> tuple[str, str, int]:
      if "--fail" in inv.argv:
          return ("", "boom", 2)  # non-zero exit
      return ("ok", "", 0)

  cmd_mox.mock("tool").with_args("run").runs(handler)
  ```

- `times(count)` – expect the command exactly `count` times.
- `times_called(count)` – alias for `times` that emphasizes spy call counts.

- `in_order()` – enforce strict ordering with other expectations.
- `any_order()` – allow the expectation to be satisfied in any position.
- `passthrough()` – for spies, run the real command while recording it.
- `assert_called()`, `assert_not_called()`, `assert_called_with(*args,
  stdin=None, env=None)` – spy-only helpers for post-verification assertions.

Refer to the [design document](./python-native-command-mocking-design.md) for
the full table of methods and examples.

## Using the IPC server directly

Most projects interact with the IPC server through `CmdMox`, but advanced
scenarios can instantiate `cmd_mox.ipc.IPCServer` themselves. The server
accepts optional callbacks so invocation handling can be customised without
subclassing:

```python
from cmd_mox.ipc import IPCHandlers, IPCServer, Response

def handle(invocation):
    return Response(stdout="custom output")

handlers = IPCHandlers(handler=handle)

with IPCServer(socket_path, handlers=handlers):
    ...
```

Providing `passthrough_handler=` to `IPCHandlers` intercepts passthrough
completions in the same fashion. When no callbacks are supplied the server
keeps its default echo behaviour, so existing code continues to work unchanged.
On Windows the transport can be forced explicitly by swapping `IPCServer` for
:class:`NamedPipeServer`; `CmdMox` selects it automatically based on
``os.name``.

Projects that rely on :class:`CallbackIPCServer` can still customise startup
and accept timeouts by passing a :class:`TimeoutConfig` dataclass:

```python
import os

from cmd_mox.ipc import (
    CallbackIPCServer,
    CallbackNamedPipeServer,
    IPCHandlers,
    TimeoutConfig,
    Response,
)

Server = CallbackNamedPipeServer if os.name == "nt" else CallbackIPCServer

def handle_passthrough(result):
    return Response(stdout=result.stdout, stderr=result.stderr, exit_code=result.exit_code)

server = Server(
    socket_path,
    handler=handle,
    passthrough_handler=handle_passthrough,
    timeouts=TimeoutConfig(timeout=1.5, accept_timeout=0.05),
)
```

## Environment variables

CmdMox exposes two environment variables to coordinate shims with the IPC
server.

- `CMOX_IPC_SOCKET` – path to the Unix domain socket used by shims on POSIX
  systems. Entering an `EnvironmentManager` sets this automatically and
  `IPCServer.start()` refreshes it, so manual overrides are rarely needed. On
  Windows `EnvironmentManager.export_ipc_environment` still exports a logical
  socket path, and the IPC layer hashes that path into a deterministic named
  pipe so existing PATH-filtering logic keeps working. Shims exit with an error
  if the variable is missing.
- `CMOX_IPC_TIMEOUT` – communication timeout in seconds. When the IPC server
  starts under an active `EnvironmentManager`, the configured timeout is
  exported automatically (default `5.0`). Override this to tune how long
  clients wait for each connect/send/receive attempt before raising a
  `TimeoutError`.

Most tests should rely on the fixture to manage these variables.
