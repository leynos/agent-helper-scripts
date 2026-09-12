# Scripting standards

Project scripts must prioritize clarity, reproducibility, and testability.

Cyclopts is the default command‑line interface (CLI) framework for new and
updated scripts. This document supersedes prior guidance that recommended Typer
as a default.

## Rationale for adopting Cyclopts

- Environment‑first configuration without glue. Cyclopts reads environment
  variables with a defined prefix (for example, `INPUT_`) and maps them to
  parameters directly. Bash argument assembly and bespoke parsing can be
  removed.
- Typed lists and paths from env. Parameters annotated as `list[str]` or
  `list[pathlib.Path]` are populated from whitespace‑ or delimiter‑separated
  environment values. Custom split/trim helpers are unnecessary.
- Clear precedence model. CLI flags override environment variables, which
  override code defaults. Behaviour is predictable in both CI and local runs.
- Small API surface. The API is explicit and integrates cleanly with type
  hints, aiding readability and testing.
- Backwards‑compatible migration. Option aliases and per‑parameter
  environment variable names permit preservation of existing interfaces while
  removing shell glue.

## Language and runtime

- Target Python 3.14 for all new scripts. Older versions may only be used when
  integration constraints require them, and any exception must be documented
  inline.
- Each script starts with an `uv` script block so runtime and dependency
  expectations travel with the file. Prefer the shebang
  `#!/usr/bin/env -S uv run --script` followed by the metadata block shown in
  the example below. `uv run --script` reads the PEP 723 inline metadata block
  and installs its declared dependencies before execution; `uv run python`
  invokes the interpreter directly and silently ignores the metadata block, so
  a directly executed script (`./script.py`) fails at import time because its
  dependencies were never installed.
- External processes are invoked via
  [`cuprum`](https://github.com/leynos/cuprum/) to provide typed,
  allowlist-based command execution rather than ad‑hoc shell strings. Cuprum's
  catalogue system ensures only registered programs can be executed, preventing
  accidental shell access.
- File‑system interactions use `pathlib.Path`. Higher‑level operations (for
  example, copying or removing trees) go through the `shutil` standard library
  module.

### Cyclopts CLI pattern (environment‑first)

Employ Cyclopts when a script requires parameters, particularly under CI with
`INPUT_*` variables.

```python
from __future__ import annotations

from pathlib import Path
from typing import Optional, Annotated

import cyclopts
from cyclopts import App, Parameter
from cuprum import Catalogue, sh

# Map INPUT_<PARAM> → function parameter without additional glue
app = App(config=cyclopts.config.Env("INPUT_", command=False))


@app.default
def default(
    *,
    # Required parameters
    bin_name: Annotated[str, Parameter(required=True)],
    version: Annotated[str, Parameter(required=True)],

    # Optional scalars
    package_name: Optional[str] = None,
    target: Optional[str] = None,
    outdir: Optional[Path] = None,
    dry_run: bool = False,

    # Lists (whitespace/newline separated by default)
    formats: list[str] | None = None,
    man_paths: Annotated[list[Path] | None, Parameter(env_var="INPUT_MAN_PATHS")] = None,
    deb_depends: list[str] | None = None,
    rpm_depends: list[str] | None = None,
):
    name = package_name or bin_name

    project_root = Path(__file__).resolve().parents[1]
    build_dir = (outdir or (project_root / "dist")) / name

    if dry_run:
        print({
            "name": name,
            "version": version,
            "target": target,
            "formats": formats,
            "man_paths": [str(p) for p in (man_paths or [])],
            "deb_depends": deb_depends,
            "rpm_depends": rpm_depends,
            "build_dir": str(build_dir),
        })
        return

    build_dir.mkdir(parents=True, exist_ok=True)
    catalogue = Catalogue.from_programs("tofu")
    with sh.scoped(catalogue):
        result = sh.make("tofu")("plan", cwd=build_dir).run_sync()
        if result.exit_code != 0:
            raise SystemExit(result.exit_code)

def main():
    """CLI Entrypoint"""
    app()


if __name__ == "__main__":
    main()

```

Guidance:

- Parameter names should be descriptive and stable. Where a legacy flag name
  must remain available, add an alias:

  ```python
  package_name: Annotated[Optional[str], Parameter(aliases=["--name"])] = None
  ```

- Where a specific delimiter is required for an environment list (for example,
  comma‑separated `formats`), specify it per parameter:

  ```python
  formats: Annotated[list[str] | None, Parameter(env_var_split=",")] = None
  ```

- Per‑parameter environment names can be pinned for backwards compatibility:

  ```python
  config_out: Annotated[Optional[Path], Parameter(env_var="INPUT_CONFIG_PATH")] = None
  ```

## cuprum: typed command execution

Cuprum provides allowlist-based command execution with built-in observability.
Programs must be registered in a catalogue before they can be executed,
preventing accidental shell access.

### Shared vs local catalogues

For application code in a multi-script repository, use a shared catalogue in a
common module (for example, `project/utils/commands.py`). This centralizes the
list of allowed programs and ensures consistent access control across the
codebase:

```python
from project.utils.commands import PROJECT_CATALOGUE
from cuprum import Catalogue, sh

with sh.scoped(PROJECT_CATALOGUE):
    # All project code uses the shared catalogue
    ...
```

For standalone scripts and tests, define a local catalogue scoped to that
file's requirements. This keeps scripts self-contained and avoids coupling to
the main application:

```python
# In a standalone script or test file
CATALOGUE = Catalogue.from_programs("git", "cargo")
```

### Catalogue and allowlisting

```python
from cuprum import Catalogue, sh

# Define allowed programs for this script
CATALOGUE = Catalogue.from_programs("git", "cargo", "grep")

# Commands can only be constructed within a scoped catalogue
with sh.scoped(CATALOGUE):
    git = sh.make("git")
    result = git("--no-pager", "log", "-1", "--pretty=%H").run_sync()
    last_commit = result.stdout.strip()
```

### Capturing output and handling failures

```python
from cuprum import Catalogue, sh

CATALOGUE = Catalogue.from_programs("git", "grep")

with sh.scoped(CATALOGUE):
    git = sh.make("git")

    # run_sync() returns CommandResult with exit_code, stdout, stderr
    result = git("status").run_sync()
    if result.exit_code != 0:
        # handle gracefully; result.stderr is available for logging
        ...

    # Pipelines via the | operator with backpressure handling
    log_cmd = git("--no-pager", "log", "--oneline")
    grep_cmd = sh.make("grep")("fix")
    shortlog = (log_cmd | grep_cmd).run_sync().stdout
```

### Working directory and environment management

```python
from pathlib import Path
from cuprum import Catalogue, sh

CATALOGUE = Catalogue.from_programs("git")
repo_dir = Path(__file__).resolve().parents[1]

with sh.scoped(CATALOGUE):
    git = sh.make("git")

    # Working directory via cwd parameter
    result = git("tag", "--list", cwd=repo_dir).run_sync()
    tags = result.stdout

    # Read-only environment-sensitive command via env parameter
    result = git(
        "var", "GIT_AUTHOR_IDENT",
        env={"GIT_AUTHOR_NAME": "CI", "GIT_AUTHOR_EMAIL": "ci@example.org"},
    ).run_sync()
```

### Keyword arguments as flags

Cuprum transforms keyword arguments into `--flag=value` format automatically,
with underscores converted to hyphens:

```python
from cuprum import Catalogue, sh

CATALOGUE = Catalogue.from_programs("cargo")

with sh.scoped(CATALOGUE):
    cargo = sh.make("cargo")
    # Equivalent to: cargo build --release --target=x86_64-unknown-linux-gnu
    result = cargo("build", release=True, target="x86_64-unknown-linux-gnu").run_sync()
```

### Observability hooks

```python
import logging
from cuprum import Catalogue, sh, Hook

LOGGER = logging.getLogger(__name__)
CATALOGUE = Catalogue.from_programs("cargo")

def log_before(event):
    LOGGER.info("Executing: %s", event.command)

def log_after(event):
    LOGGER.info("Completed with exit code %d", event.result.exit_code)

with sh.scoped(CATALOGUE):
    with sh.observe(Hook(before=log_before, after=log_after)):
        sh.make("cargo")("check").run_sync()
```

### Async execution

For I/O-bound workflows, Cuprum supports async execution:

```python
import asyncio
from cuprum import Catalogue, sh

CATALOGUE = Catalogue.from_programs("cargo")

async def run_checks():
    with sh.scoped(CATALOGUE):
        cargo = sh.make("cargo")
        # Async execution with run()
        result = await cargo("check", "--all-targets").run()
        return result.exit_code == 0

asyncio.run(run_checks())
```

#### Task lifetime and `asyncio.gather`

When multiple async commands run concurrently, each task's lifetime must be
bounded by the enclosing coroutine. Await the tasks with `asyncio.gather`, or
with `asyncio.TaskGroup` on Python 3.11 and later, so background command work
cannot escape the calling coroutine.

```python
import asyncio
from cuprum import Catalogue, sh

CATALOGUE = Catalogue.from_programs("cargo", "python")

async def run_all():
    with sh.scoped(CATALOGUE):
        cargo = sh.make("cargo")
        python = sh.make("python")
        results = await asyncio.gather(
            cargo("check", "--all-targets").run(),
            python("-m", "pytest", "--tb=short").run(),
            return_exceptions=True,
        )
    return results
```

`return_exceptions=True` prevents a single task failure from cancelling sibling
tasks. Callers must inspect each result individually.

#### Cancellation handling

`asyncio.CancelledError` is not suppressed by Cuprum. If a task running `run()`
is cancelled, for example by a timeout or external signal, the coroutine raises
`CancelledError` as normal. Authors must not catch `CancelledError` silently.

```python
async def check_with_timeout():
    with sh.scoped(CATALOGUE):
        cargo = sh.make("cargo")
        try:
            result = await asyncio.wait_for(
                cargo("build", "--release").run(), timeout=120.0
            )
        except asyncio.TimeoutError:
            # Handle or re-raise; do not swallow CancelledError
            raise
    return result
```

#### Error propagation

`run()` returns a `CommandResult` and does not raise on non-zero exit codes.
Subprocess errors are propagated as field values such as `exit_code` and
`stderr`, not as exceptions. Callers must check `result.exit_code` explicitly.
The exceptions raised are those from the Python event loop itself, such as
`CancelledError` and `TimeoutError`, or from catalogue violations such as
`UnknownProgramError`.

#### Catalogue safety across concurrent tasks

A `Catalogue` instance is safe to share across concurrent tasks because it is
read-only after construction. `sh.scoped(CATALOGUE)` is a context manager that
binds the catalogue for the current execution scope. Authors must not mutate
the catalogue inside a concurrent task. Construct the catalogue once at module
level and re-use it.

#### Concurrent testing patterns with cmd-mox

Concurrent async script paths use the same catalogue and scoped context in
tests as they do in production code. `cmd-mox` intercepts at the catalogue
boundary regardless of whether `run()` or `run_sync()` is used.

```python
import pytest


@pytest.mark.asyncio
async def test_concurrent_commands_all_succeed(mock_catalogue):
    mock_catalogue.register("cargo", exit_code=0, stdout="ok\n")
    mock_catalogue.register("python", exit_code=0, stdout="passed\n")

    results = await run_all()  # function under test

    assert all(r.exit_code == 0 for r in results)


@pytest.mark.asyncio
async def test_gather_continues_after_one_failure(mock_catalogue):
    mock_catalogue.register("cargo", exit_code=1, stderr="error\n")
    mock_catalogue.register("python", exit_code=0, stdout="passed\n")

    results = await run_all()

    exit_codes = [r.exit_code for r in results]
    assert 1 in exit_codes
    assert 0 in exit_codes
```

The `mock_catalogue` fixture replaces the real `CATALOGUE`. Authors must inject
it via a parameter or monkeypatch rather than relying on the module-level
constant directly.

## pathlib: robust path manipulation

### Project roots, joins, and ensuring directories

```python
from __future__ import annotations
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DIST = PROJECT_ROOT / "dist"
(DIST / "artifacts").mkdir(parents=True, exist_ok=True)

# Portable joins and normalisation
cfg = PROJECT_ROOT.joinpath("config", "release.toml").resolve()
```

### Reading / writing files and atomic updates

```python
from pathlib import Path
import tempfile

f = Path("./dist/version.txt")

# Text I/O
f.write_text("1.2.3\n", encoding="utf-8")
version = f.read_text(encoding="utf-8").strip()

# Atomic write pattern (tmp → replace)
with tempfile.NamedTemporaryFile("w", delete=False, dir=f.parent, encoding="utf-8") as tmp:
    tmp.write("new-contents\n")
    tmp_path = Path(tmp.name)

tmp_path.replace(f)  # atomic on POSIX
```

### Globbing, filtering, and safe deletion

```python
from pathlib import Path

# Recursive glob
md_files = sorted(Path("docs").glob("**/*.md"))

# Filter by suffix / size
small_md = [p for p in md_files if p.stat().st_size < 4096 and p.suffix == ".md"]

# Safe deletion (ignore missing)
try:
    (Path("build") / "temp.bin").unlink()
except FileNotFoundError:
    pass
```

## Cyclopts + cuprum + pathlib together (reference script)

```python
#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = ["cyclopts>=2.9", "cuprum", "cmd-mox"]
# ///

from __future__ import annotations
from pathlib import Path
from typing import Optional, Annotated

import cyclopts
from cyclopts import App, Parameter
from cuprum import Catalogue, sh

CATALOGUE = Catalogue.from_programs("git")

app = App(config=cyclopts.config.Env("INPUT_", command=False))

@app.default
def main(
    *,
    bin_name: Annotated[str, Parameter(required=True)],
    version: Annotated[str, Parameter(required=True)],
    formats: list[str] | None = None,
    outdir: Optional[Path] = None,
    dry_run: bool = False,
):
    project_root = Path(__file__).resolve().parents[1]
    dist = (outdir or (project_root / "dist")) / bin_name
    dist.mkdir(parents=True, exist_ok=True)

    if not dry_run:
        with sh.scoped(CATALOGUE):
            git = sh.make("git")
            git("tag", f"v{version}", cwd=project_root).run_sync()

    print({
        "bin_name": bin_name,
        "version": version,
        "formats": formats or [],
        "dist": str(dist),
    })

if __name__ == "__main__":
    app()
```

## Testing expectations

- Automated coverage via `pytest` is required for every script. Fixtures from
  `pytest-mock` support Python‑level mocking; `cmd-mox` simulates external
  executables without touching the host system.
- Behavioural flows that map cleanly to scenarios should adopt Behaviour‑Driven
  Development (BDD) via `pytest-bdd` so that intent is captured in
  human‑readable Given/When/Then narratives.
- Tests reside in `scripts/tests/`, mirroring script names. For example,
  `scripts/bootstrap_doks.py` pairs with `scripts/tests/test_bootstrap_doks.py`.
- Where scripts rely on environment variables, both happy paths and failure
  modes must be asserted; tests should demonstrate graceful error handling
  rather than opaque stack traces.

### Mocking Python dependencies (pytest-mock) and environment (monkeypatch)

```python
import os
from pathlib import Path
from cyclopts.testing import invoke
from scripts.package import app


def test_reads_env_and_defaults(monkeypatch, tmp_path):
    # Arrange env for Cyclopts
    monkeypatch.setenv("INPUT_BIN_NAME", "demo")
    monkeypatch.setenv("INPUT_VERSION", "1.2.3")
    monkeypatch.setenv("INPUT_FORMATS", "deb rpm")  # whitespace or newlines

    # Exercise
    result = invoke(app, [])

    # Assert
    assert result.exit_code == 0
    assert '"version": "1.2.3"' in result.stdout


def test_patch_python_dependency(mocker):
    # Example: patch a helper function used by the script
    from scripts import helpers

    mocker.patch.object(helpers, "compute_checksum", return_value="deadbeef")
    assert helpers.compute_checksum(b"abc") == "deadbeef"
```

### Mocking external executables with cmd-mox (record → replay → verify)

Enable the plugin in `conftest.py`:

```python
pytest_plugins = ("cmd_mox.pytest_plugin",)
```

```python
from cuprum import Catalogue, sh

CATALOGUE = Catalogue.from_programs("git")


def test_git_tag_happy_path(cmd_mox, tmp_path):

    # Mock external command behaviour
    cmd_mox.mock("git").with_args("tag", "v1.2.3").returns(exit_code=0)

    # Run the code under test while shims are active
    cmd_mox.replay()
    with sh.scoped(CATALOGUE):
        sh.make("git")("tag", "v1.2.3", cwd=tmp_path).run_sync()
    cmd_mox.verify()


def test_git_tag_failure_surface_error(cmd_mox, tmp_path):

    cmd_mox.mock("git").with_args("tag", "v1.2.3").returns(exit_code=1, stderr="denied")

    cmd_mox.replay()
    with sh.scoped(CATALOGUE):
        result = sh.make("git")("tag", "v1.2.3", cwd=tmp_path).run_sync()
        assert result.exit_code == 1
        assert "denied" in result.stderr
    cmd_mox.verify()
```

### Spies and passthrough capture (turn real calls into fixtures)

```python
from cuprum import Catalogue, sh

CATALOGUE = Catalogue.from_programs("echo")


def test_spy_and_record(cmd_mox, tmp_path):

    # Spy records actual usage; passthrough runs the real command
    spy = cmd_mox.spy("echo").passthrough()

    cmd_mox.replay()
    with sh.scoped(CATALOGUE):
        sh.make("echo")("hello world", cwd=tmp_path).run_sync()
    cmd_mox.verify()

    # Inspect what happened
    spy.assert_called()
    assert spy.call_count == 1
    args = spy.invocations[0].argv[1:]
    assert args == ["hello world"]
```

## Operational guidelines

- Scripts must be idempotent. Re‑running should converge state without
  destructive side effects. Guard conditions (for example, checking the secrets
  manager for existing secrets) should precede writes or rotations.
- Pure functions that accept configuration objects are preferred over global
  state so that tests can exercise logic deterministically.
- Exit codes should follow UNIX conventions: `0` for success, non‑zero for
  actionable failures. Human‑friendly error messages should highlight
  remediation steps.
- Dependencies must remain minimal. Any new package should be added to the `uv`
  block and the rationale documented within the script or companion tests.

## Migration guidance (Typer → Cyclopts)

1. Dependencies: replace Typer with Cyclopts in the script's `uv` block.
2. Entry point: replace `app = typer.Typer(...)` with `app = App(...)` and
   configure `Env("INPUT_", command=False)` where environment variables are
   authoritative in CI.
3. Parameters: replace `typer.Option(...)` with annotations and
   `Parameter(...)`. Mark required options with `required=True`. Map any
   non‑matching environment names via `env_var=...`.
4. Lists: remove custom split/trim code. Use list‑typed parameters; add
   `env_var_split=","` where a non‑whitespace delimiter is required.
5. Compatibility: retain legacy flag names using `aliases=["--old-name"]`.
6. Bash glue: delete argument arrays and conditional appends in GitHub
   Actions. Export `INPUT_*` environment variables and call `uv run` on the
   script.

## Migration guidance (plumbum → cuprum)

**Important semantic change:** Plumbum raises `ProcessExecutionError` on
non-zero exit codes by default, whereas Cuprum's `run_sync()` always returns a
`CommandResult` without raising. Code that relied on exception handling for
failure detection must be rewritten to check `result.exit_code` explicitly.
This shift improves predictability but requires careful attention when porting
existing error handling logic.

1. Dependencies: replace `plumbum` with `cuprum` in `pyproject.toml` or the
   script's `uv` block.
2. Define a catalogue: create a `Catalogue.from_programs(...)` listing all
   executables the script requires.
3. Scope execution: wrap command construction in `with sh.scoped(CATALOGUE):`.
4. Command construction: replace `local["git"]["args"]` with
   `sh.make("git")("args")`.
5. Execution: replace `command()` with `command.run_sync()` and access
   `result.stdout`, `result.stderr`, `result.exit_code`.
6. Non‑raising execution: replace `.run(retcode=None)` patterns with
   `run_sync()` and check `result.exit_code` explicitly. Note that this is now
   the default behaviour, not a special case.
7. Working directory: replace `with local.cwd(path):` context manager with
   `cwd=path` parameter on the command.
8. Environment: replace `with local.env(VAR=value):` with `env={"VAR": value}`
   parameter on the command.
9. Pipelines: the `|` operator works identically; ensure both commands are
   constructed via `sh.make()`.
10. Error handling: replace `CommandNotFound` with cuprum's
    `UnknownProgramError`; replace `ProcessExecutionError` with exit code
    checks on `CommandResult`.

## CI wiring: GitHub Actions (Cyclopts‑first)

```yaml
- name: Build
  shell: bash
  working-directory: ${{ inputs.project-dir }}
  env:
    INPUT_BIN_NAME: ${{ inputs.bin-name }}
    INPUT_VERSION: ${{ inputs.version }}
    INPUT_FORMATS: ${{ inputs.formats }}               # multiline or space‑sep
    INPUT_OUTDIR: ${{ inputs.outdir }}
  run: |
    set -euo pipefail
    uv run "${GITHUB_ACTION_PATH}/scripts/package.py"
```

## Notes and gotchas

- Newline‑separated lists are preferred for CI inputs to avoid shell quoting
  issues across platforms.
- Cuprum's `run_sync()` always returns a `CommandResult`; check `exit_code`
  explicitly rather than relying on exceptions for non‑zero exits.
- Production code should present friendly error messages; tests may assert raw
  behaviours (non‑zero exits, stderr contents) via `cmd-mox`.
- On Windows, newline‑separated lists are recommended for `list[Path]` to
  sidestep `;`/`:` semantics.
- Cuprum's catalogue must include all programs used by the script; attempting
  to construct a command for an unregistered program raises
  `UnknownProgramError`.

This document should be referenced when introducing or updating automation
scripts to maintain a consistent developer experience across projects.
