# CmdMox Usage Guide

CmdMox provides a fluent API for mocking, stubbing and spying on external
commands in tests. This guide shows common patterns for everyday use.

## Getting started

Install the package and enable the pytest plugin:

```bash
pip install cmd-mox
```

On Windows the wheel also pulls in `pywin32`, which provides the `win32pipe` and
`win32file` modules that power CmdMox's named-pipe IPC transport.

In `conftest.py`:

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
effective `PATHEXT` value, even if developers customized their shell to omit
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
remain invocable while still cleaning up the real directory afterwards. PATH
filtering honours the underlying filesystem semantics too, so variations in
casing no longer leave behind duplicate entries when passthrough spies merge
their lookup paths.

Importing :mod:`cmd_mox.shim` no longer mutates ``sys.path`` or
``sys.modules``. The bootstrap that prefers stdlib modules over editable
installs runs only when the shim entrypoint executes. When shim helpers are
reused directly, ``cmd_mox._shim_bootstrap.bootstrap_shim_path()`` should be
called during setup first.

When a test module needs to make an explicit decision (for instance when using
the context manager API), import the helper re-exported from the package:

```python
from cmd_mox import skip_if_unsupported

skip_if_unsupported()
```

`skip_if_unsupported` defers to `pytest.skip` on unsupported platforms. For
code-path gating only, `cmd_mox.is_supported()` returns a boolean
instead. Advanced tests can override the detected platform by setting the
`CMD_MOX_PLATFORM_OVERRIDE` environment variable (also exported as
`PLATFORM_OVERRIDE_ENV`), which is primarily useful for simulating alternative
environments inside CI pipelines (for example to exercise Windows-specific
shims from a Linux runner).

The cmd-mox test suite also uses the `pytest.mark.requires_unix_sockets` marker
for scenarios that need to bind a Unix domain socket. Marking these tests keeps
them green on platforms (or CI sandboxes) that disallow Unix sockets entirely.

## Basic workflow

CmdMox follows a strict record → replay → verify lifecycle. First declare
expectations, then run the code under test with the shims active, and finally
verify that interactions matched what was recorded.

The three phases are defined in the design document:

1. **Record** – describe each expected command call, including its arguments
   and behaviour.
2. **Replay** – run the code under test while CmdMox intercepts command
   executions.
3. **Verify** – ensure every expectation was met and nothing unexpected
   happened.

These phases form a strict sequence for reliable command-line tests. Calling
`replay()` more than once during the replay phase is explicitly idempotent:
subsequent calls are no-ops.

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

### Argument matchers (comparators)

CmdMox ships with a small set of matcher objects for `with_matching_args`. Each
matcher is callable (`Callable[[str], bool]`) and can be mixed with custom
predicates.

- `Any` – matches any single argument.

  ```python
  from cmd_mox import Any

  cmd_mox.mock("git").with_matching_args("clone", Any()).returns(exit_code=0)
  ```

- `IsA(typ)` – matches arguments convertible to `typ` (for example `int`).

  ```python
  from cmd_mox import IsA

  cmd_mox.mock("tool").with_matching_args("--count", IsA(int)).returns()
  ```

- `Regex(pattern)` – matches when a regular expression search succeeds.

  ```python
  from cmd_mox import Regex

  cmd_mox.mock("curl").with_matching_args(Regex(r"^https://")).returns()
  ```

- `Contains(substring)` – matches when `substring` is present.

  ```python
  from cmd_mox import Contains

  cmd_mox.mock("echo").with_matching_args(Contains("hello")).returns()
  ```

- `StartsWith(prefix)` – matches when an argument begins with `prefix`.

  ```python
  from cmd_mox import StartsWith

  cmd_mox.mock("tool").with_matching_args(StartsWith("--flag=")).returns()
  ```

- `Predicate(func)` – wraps a custom callable and uses its truthiness.

  ```python
  from cmd_mox import Predicate

  cmd_mox.mock("tool").with_matching_args(Predicate(lambda v: v.endswith(".txt"))).returns()
  ```

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

If replay aborts because the code under test raises an exception or the process
receives Ctrl+C, `CmdMox` still tears down the environment before surfacing the
original error. The controller catches interruptions during replay startup,
stops the IPC server, removes the shim directory (and its socket), and restores
`PATH` before re-raising so temporary artefacts do not leak between tests.

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

A spy expectation can also use `times_called(count)`—an alias of `times(count)`
—to require a specific call count during verification.

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

## Recording sessions (fixture capture)

A `RecordingSession` captures passthrough spy interactions and persists them as
versioned JSON fixture files. This is the foundation for Record Mode: run
commands against real systems once, then replay the recorded interactions in
future test runs without external dependencies.

### Creating a recording session

```python
from pathlib import Path
from cmd_mox.record import RecordingSession

session = RecordingSession(
    Path("fixtures/git_clone.json"),
    env_allowlist=["GIT_AUTHOR_NAME", "GIT_COMMITTER_EMAIL"],
)
```

The `env_allowlist` parameter specifies environment variable keys that should
always be included in recordings, even if they would otherwise be filtered.

### Lifecycle: start, record, finalize

A session follows a strict lifecycle:

```python
session.start()                              # Begin the session
session.record(invocation, response)         # Capture an interaction
session.record(invocation2, response2)       # Capture another
fixture = session.finalize()                 # Persist and return FixtureFile
```

- `start()` initializes the session timestamp. Calling `record()` before
  `start()` raises `LifecycleError`.
- `record(invocation, response, *, duration_ms=0)` appends a recording with
  auto-incrementing sequence numbers and filtered environment variables. The
  optional `duration_ms` parameter records execution timing.
- `finalize()` writes the fixture to disk and returns the `FixtureFile`. It
  is idempotent: calling it again returns the same object. Calling `record()`
  after `finalize()` raises `LifecycleError`.

### Environment variable filtering

Recordings capture only a safe, portable subset of environment variables:

- **Excluded by default:** `PATH`, `HOME`, `USER`, `SHELL`, `SSH_AUTH_SOCK`,
  `GPG_AGENT_INFO`, CmdMox internal variables (`CMOX_*`, `CMD_MOX_*`), and keys
  matching sensitive patterns (`*_SECRET`, `*_TOKEN`, `*_PASSWORD`, `*_KEY`,
  `*_CREDENTIALS`).
- **Included by default:** command-specific prefix keys (e.g., `GIT_*` for
  git, `AWS_*` for aws), allowlisted keys, and explicitly requested keys.
- **Override:** use `env_allowlist` to force-include specific keys, or pass
  `explicit_keys` to `filter_env_subset()` for keys from `.with_env()`.

### Fixture file format

Fixtures are stored as JSON with a versioned schema:

```json
{
  "version": "1.0",
  "metadata": {
    "created_at": "2025-01-15T10:30:00+00:00",
    "cmdmox_version": "0.2.0",
    "platform": "linux",
    "python_version": "3.12.0"
  },
  "recordings": [
    {
      "sequence": 0,
      "command": "git",
      "args": ["status"],
      "stdin": "",
      "env_subset": {"GIT_AUTHOR_NAME": "Test User"},
      "stdout": "M file.py\n",
      "stderr": "",
      "exit_code": 0,
      "timestamp": "2025-01-15T10:30:01+00:00",
      "duration_ms": 42
    }
  ],
  "scrubbing_rules": []
}
```

Fixture files can be loaded and round-tripped:

```python
from cmd_mox.record import FixtureFile

fixture = FixtureFile.load(Path("fixtures/git_clone.json"))
assert fixture.version == "1.0"
assert len(fixture.recordings) == 1
```

### Schema versioning and migration

Fixture files include a `version` field following semantic versioning. CmdMox
automatically migrates older fixture files to the current schema when loading
via `FixtureFile.load()` or `FixtureFile.from_dict()`. Minor version
differences within the same major version are tolerated -- for example, a v1.1
fixture loads correctly into v1.0 code because unknown fields are ignored.
Incompatible major versions with no registered migration path raise
`ValueError`.

## Automatic recording with `.record()`

The `CommandDouble.record()` fluent method connects passthrough spies to
recording sessions automatically. Instead of manually creating and managing a
`RecordingSession`, call `.record()` on a passthrough spy:

```python
def test_git_clone(cmd_mox):
    spy = cmd_mox.spy("git").passthrough().record("fixtures/git_clone.json")
    # ... run code that invokes git ...
    # Fixture is written automatically during verify()
```

Each passthrough invocation is captured by the `PassthroughCoordinator` and
persisted to the fixture file when `verify()` is called. When
`verify_on_exit=True` (the default), the context manager calls `verify()`
automatically on exit. If `verify_on_exit=False`, fixtures are **not** written
unless `verify()` is called explicitly.

### Record parameters

The `record()` method accepts optional parameters for controlling what is
recorded:

```python
import dataclasses as dc

from cmd_mox.record.fixture import RecordedInvocation


class RedactSecrets:
    """Scrubber that replaces secret values in stdout."""

    def scrub(self, recording: RecordedInvocation) -> RecordedInvocation:
        return dc.replace(recording, stdout=recording.stdout.replace("AKIA", "****"))


spy = cmd_mox.spy("aws").passthrough().record(
    "fixtures/aws_s3.json",
    scrubber=RedactSecrets(),                      # sanitize sensitive data
    env_allowlist=["AWS_REGION", "AWS_PROFILE"],   # include these env vars
)
```

- **`fixture_path`** (`str | Path`): destination for the fixture JSON file.
- **`scrubber`** (`Scrubber | None`): optional scrubber instance for sanitizing
  recordings before persistence. When `None` (the default), no scrubbing is
  applied.
- **`env_allowlist`** (`list[str] | None`): environment variable keys to always
  include in recordings, in addition to the default command-specific prefixes.

### Record validation

Calling `record()` without first calling `passthrough()` raises `ValueError`:

```python
# This raises ValueError: "record() requires passthrough(); call it first"
cmd_mox.spy("git").record("fixtures/git.json")
```

## Replay sessions (fixture replay)

A `ReplaySession` is the counterpart to `RecordingSession`. Where recording
captures real command interactions to fixture files, replay loads those
fixtures and uses them to respond to invocations without executing real
commands. This enables fast, deterministic tests from previously captured
interactions.

## Automatic replay with `.replay()`

The `CommandDouble.replay()` fluent method attaches a loaded replay fixture to
a spy during test setup. This keeps fixture validation close to the test code
that declares the double:

```python
def test_git_clone(cmd_mox):
    spy = cmd_mox.spy("git").replay("fixtures/git_clone.json")
    # ... run code that invokes git ...
```

Calling `.replay()` loads the fixture immediately. Missing files, malformed
JSON, and schema-version errors therefore fail the test during setup rather
than later during command execution.

Once replay mode is active on the controller, CmdMox consults the attached
replay session before the spy's normal `.returns(...)` or `.runs(...)`
behaviour. When a fixture recording matches, the recorded `stdout`, `stderr`,
and exit code are returned, and the invocation still appears in both
`spy.invocations` and `cmd_mox.journal`.

### Parameters

- **`fixture_path`** (`str | Path`): path to the JSON fixture file to load.
- **`strict`** (`bool`): when `True` (default), replay uses strict matching.
  When `False`, replay uses fuzzy matching.

### Validation

The `.replay()` fluent API is currently limited to spies. It also cannot be
combined with passthrough mode because the two behaviours conflict:

```python
# This raises ValueError: "replay() is only valid for spies"
cmd_mox.mock("git").replay("fixtures/git.json")

# This raises ValueError: "replay() cannot be combined with passthrough()"
cmd_mox.spy("git").passthrough().replay("fixtures/git.json")
```

Calling `.replay()` more than once on the same double raises `RuntimeError`.
The attached session is available via the read-only `replay_session` property,
and `has_replay_session` reports whether a session has been attached.

If strict replay is enabled and no fixture recording matches the live
invocation, CmdMox raises `UnexpectedCommandError` immediately during command
handling. If fuzzy replay is enabled and no fixture recording matches, CmdMox
falls back to the spy's configured response or handler instead of raising.
Either way, `CmdMox.verify()` later calls `verify_all_consumed()` for every
attached replay session. Any fixture entries left unused at verify time raise
`VerificationError` unless the session was created directly with
`allow_unmatched=True`.

### Creating and loading a replay session

```python
from cmd_mox.record import ReplaySession

session = ReplaySession("fixtures/git_clone.json")
session.load()  # loads and validates the fixture from disk
```

The constructor accepts:

- **`fixture_path`** (`str | Path`): path to the JSON fixture file to load.
- **`strict_matching`** (`bool`): when `True` (default), matching requires
  command, args, stdin, and env_subset to match. When `False`, only command and
  args must match (fuzzy mode).
- **`allow_unmatched`** (`bool`): when `True`, `verify_all_consumed()` does
  not raise even if some recordings were not consumed. Defaults to `False`.

Calling `load()` a second time raises `LifecycleError`. Calling `match()` or
`verify_all_consumed()` before `load()` also raises `LifecycleError`.

### Matching invocations

```python
from cmd_mox.ipc import Invocation

invocation = Invocation(
    command="git", args=["status"], stdin="", env={}
)
response = session.match(invocation)
if response is not None:
    print(response.stdout)  # the recorded stdout
```

`match()` searches the loaded recordings and returns a `Response` built from
the best-fit unconsumed recording. When multiple recordings qualify, the
matcher selects the most appropriate one deterministically based on stdin
exactness and environment specificity. Each matched recording is marked as
consumed and will not match again.

### Matching modes

**Strict mode** (default) requires all of the following to match:

- Command name (exact equality)
- Arguments (exact list equality)
- Standard input (exact string equality)
- Environment subset (every key-value pair in the recorded `env_subset` must
  be present in the invocation `env`; extra keys in the invocation are allowed)

**Fuzzy mode** (`strict_matching=False`) requires only:

- Command name (exact equality)
- Arguments (exact list equality)

Stdin and environment differences are ignored, which is useful when those
fields contain non-deterministic values such as timestamps or UUIDs.

```python
# Fuzzy mode: matches on command + args only
session = ReplaySession("fixtures/git.json", strict_matching=False)
session.load()
```

### Best-fit selection

When a fixture contains multiple recordings with the same command and
arguments, the replay session selects the most appropriate match
deterministically:

**In strict mode**, all recordings must fully match (command, args, stdin, and
env_subset). When multiple recordings qualify, the matcher prefers the one with:

1. More matching environment pairs
2. Larger `env_subset` (indicating greater specificity)
3. Lower recording `sequence` value (if scores tie)

**In fuzzy mode**, only command and args are required. Among qualifying
recordings, the matcher prefers the one with:

1. Exact stdin match (if stdin matches the invocation)
2. More matching environment pairs
3. Larger `env_subset`
4. Lower recording `sequence` value (if scores tie)

This ensures that when the same command is recorded with different contexts
(for example, `git status` with and without environment variables), replay
selects the recording that best matches the live invocation rather than always
consuming the first compatible entry.

### Consumed-record tracking

Each successful `match()` call marks the matched recording as consumed.
Consumed recordings are skipped in subsequent `match()` calls. When the fixture
contains two identical recordings, the first call consumes the first recording
and the second call consumes the second.

### Verifying all recordings were consumed

```python
session.verify_all_consumed()
```

`verify_all_consumed()` raises `VerificationError` if any recording was not
consumed, listing the unconsumed recordings by index, command, and arguments.
`CmdMox.verify()` applies the same check automatically to replay-backed spies,
so attaching a fixture through `.replay()` means tests must consume every
recording before verification completes.

When `allow_unmatched=True`, `verify_all_consumed()` always succeeds regardless
of how many recordings remain unconsumed. This is useful for fixtures that
contain more recordings than a specific test exercises. The fluent `.replay()`
helper does not expose this opt-out; use `ReplaySession` directly when
partial-consumption verification is the intended behaviour.

## Pipelines and shell syntax

CmdMox intercepts individual executables by prepending shims to `PATH`. It does
not interpret shell syntax itself, so constructs like pipelines (`|`) and I/O
redirection (`>`, `<`) are handled by the shell. To test pipeline behaviour,
mock each command in the pipeline separately and execute the full command line
with `shell=True` so the shell wires stdout to stdin:

```python
def test_pipeline(cmd_mox):
    cmd_mox.mock("grep").with_args("foo", "file.txt").returns(stdout="c a b")
    cmd_mox.mock("sort").with_args("-r").with_stdin("c a b").returns(stdout="c b a")

    result = subprocess.run(
        "grep foo file.txt | sort -r",
        shell=True,
        text=True,
        capture_output=True,
        check=True,
    )

    assert result.stdout.strip() == "c b a"
```

## Controller configuration and journals

`CmdMox` offers configuration hooks that surface through both the fixture and
the context-manager API:

- `verify_on_exit` (default `True`) automatically calls `verify()` when a replay
  phase ends inside a `with CmdMox()` block. Disable it when manual
  verification management is required. Verification still runs if the body
  raises; when both verification and the body fail, the verification error is
  suppressed so the original exception surfaces.
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
- `assert_called()`, `assert_not_called()`,
  `assert_called_with(*args, stdin=None, env=None)` – spy-only helpers for
  post-verification assertions.

Refer to the CmdMox design documentation for the full table of methods and
examples.

## Using the IPC server directly

Most projects interact with the IPC server through `CmdMox`, but advanced
scenarios can instantiate `cmd_mox.ipc.IPCServer` themselves. The server
accepts optional callbacks for simple composition:

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
Request dispatch invokes the public `handle_invocation()` and
`handle_passthrough_result()` hooks. Subclass `IPCServer` when server behaviour
requires overriding those hooks:

```python
from cmd_mox.ipc import IPCServer, Invocation, PassthroughResult, Response

class CustomIPCServer(IPCServer):
    def handle_invocation(self, invocation: Invocation) -> Response:
        return Response(stdout=f"handled {invocation.command}")

    def handle_passthrough_result(self, result: PassthroughResult) -> Response:
        return Response(stdout=f"recorded {result.invocation_id}")

with CustomIPCServer(socket_path):
    ...
```

The same dispatch contract applies to both the Unix-domain-socket transport
and the Windows named-pipe transport. Use callbacks for simple composition and
subclassing for behaviour that requires overridden hooks.

On Windows the transport can be forced explicitly by swapping `IPCServer` for
:class:`NamedPipeServer`; `CmdMox` selects it automatically based on
``os.name``.

Both transports emit bounded, structured observability events with
correlation identifiers, and the Windows named-pipe transport bounds
concurrent clients, message size, and per-client read time. See the CmdMox
design documentation for the event vocabulary and the specific limits.

Projects that rely on :class:`CallbackIPCServer` can still customize startup
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

## Public API reference

<!-- api-reference:start -->

This section lists the symbols exported directly from `cmd_mox` (the package
top-level). It mirrors `cmd_mox.__all__` so consumers can quickly find the
supported surface area without navigating modules.

### Controller and test doubles

- `CmdMox` – controller implementing record → replay → verify.
- `CommandDouble` – the fluent test-double object returned by factory methods.
- `StubCommand` – stub double type (returned by `CmdMox.stub()`).
- `MockCommand` – mock double type (returned by `CmdMox.mock()`).
- `SpyCommand` – spy double type (returned by `CmdMox.spy()`).
- `Expectation` – expectation model that powers argument/stdin/env matching.
- `Invocation` – captured invocation details (command, args, stdin, env,
  results).
- `Response` – result payload returned from `returns()`/`runs()` handlers.

### Matchers (comparators)

- `Any` – match any string argument.
- `IsA` – match values convertible to a type.
- `Regex` – regex search matcher.
- `Contains` – substring matcher.
- `StartsWith` – prefix matcher.
- `Predicate` – wrap a custom predicate function.

### IPC servers

- `IPCServer` – IPC server (Unix socket on POSIX, named pipe on Windows).
- `NamedPipeServer` – explicit Windows named-pipe transport implementation.

### Shims and environment helpers

- `EnvironmentManager` – manages shim directory, `PATH`, and IPC env vars.
- `temporary_env` – context manager to temporarily set `os.environ` entries.
- `create_shim_symlinks` – low-level helper to generate command shims.
- `SHIM_PATH` – filesystem path to the shared `shim.py` entrypoint used by
  shims.

### Platform helpers

- `is_supported` – return `True` when cmd-mox supports the platform.
- `skip_if_unsupported` – `pytest.skip()` on unsupported platforms.
- `unsupported_reason` – return a human-readable reason when unsupported.
- `PLATFORM_OVERRIDE_ENV` – name of the platform override env var
  (`CMD_MOX_PLATFORM_OVERRIDE`).

### Exceptions

- `CmdMoxError` – base exception for cmd-mox errors.
- `LifecycleError` – raised on invalid record/replay/verify transitions.
- `MissingEnvironmentError` – raised when replay cannot start due to missing
  env.
- `UnexpectedCommandError` – raised when a command runs without a matching
  double.
- `UnfulfilledExpectationError` – raised when expected calls did not occur.
- `VerificationError` – base class for verification failures.

### Pytest helper

- `cmd_mox_fixture` – alias for the pytest `cmd_mox` fixture function
  (lazy-loaded).

<!-- api-reference:end -->
