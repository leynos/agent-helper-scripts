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
  the example below. Running the script directly (for example, `./script.py`)
  follows that shebang, so `uv run --script` reads the PEP 723 metadata and
  installs its declared dependencies before execution. By contrast,
  `uv run python script.py` starts Python directly and does not consume the
  script's metadata; use it only when dependencies are managed separately.
- External processes are invoked via
  [`cuprum` v0.2.0-beta2][cuprum-guide] to provide typed, allowlist-based
  command execution rather than ad‑hoc shell strings. Cuprum's catalogue system
  reduces accidental invocation of unregistered executables, but registering an
  interpreter such as `sh`, `bash` or `python` still permits arbitrary code
  execution through caller-supplied arguments. An explicit executable policy
  plus separate validation of caller-supplied arguments remain required.
- File‑system interactions use `pathlib.Path`. Higher‑level operations (for
  example, copying or removing trees) go through the `shutil` standard library
  module.

### Cyclopts CLI pattern (environment‑first)

Employ Cyclopts when a script requires parameters, particularly under CI with
`INPUT_*` variables.

<!-- tested-example: cyclopts-cli -->
```python
from __future__ import annotations

from pathlib import Path
from typing import Optional, Annotated

import cyclopts
from cyclopts import App, Parameter
from cuprum import ExecutionContext, Program, ProgramCatalogue, scoped, sh

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
    tofu = Program("tofu")
    catalogue = ProgramCatalogue.from_programs(tofu, name="packaging")
    with scoped(catalogue=catalogue):
        result = sh.make(tofu, catalogue=catalogue)("plan").run_sync(
            context=ExecutionContext(cwd=build_dir)
        )
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

  <!-- tested-example: cyclopts-parameter-name -->
  ```python
  package_name: Annotated[Optional[str], Parameter(aliases=["--name"])] = None
  ```

- Where a specific delimiter is required for an environment list (for example,
  comma‑separated `formats`), specify it per parameter:

  <!-- tested-example: cyclopts-parameter-config -->
  ```python
  formats: Annotated[list[str] | None, Parameter(env_var_split=",")] = None
  ```

- Per‑parameter environment names can be pinned for backwards compatibility:

  <!-- tested-example: cyclopts-parameter-output -->
  ```python
  config_out: Annotated[Optional[Path], Parameter(env_var="INPUT_CONFIG_PATH")] = None
  ```

## cuprum: typed command execution

All new and updated scripts that launch external processes must use cuprum
v0.2.0-beta2. Pin `cuprum==0.2.0b2` in the script's PEP 723 dependency block or
the project's dependencies. `0.2.0b2` is the Python packaging spelling of
v0.2.0-beta2. Do not add plumbum or direct `subprocess` calls for command
execution. These rules and examples follow the
[tagged users' guide][cuprum-guide].

Cuprum builds argument vectors without a shell. A catalogue declares known
programs; a scope restricts which of them may execute. Registering `sh`, `bash`
or `python` still permits arbitrary code through their arguments. Review the
executable policy and validate caller-supplied arguments separately.

### Shared vs local catalogues

For a multi-script application, declare programs and a shared catalogue in a
common module, for example `project/utils/commands.py`:

<!-- tested-example: catalogue-definition -->
```python
from cuprum import Program, ProgramCatalogue

GIT = Program("git")
CARGO = Program("cargo")
PROJECT_CATALOGUE = ProgramCatalogue.from_programs(GIT, CARGO, name="project")
```

Use `ProgramCatalogue.from_programs()` for a simple executable list. Use
`ProjectSettings` with `ProgramCatalogue(projects=...)` when project metadata,
documentation locations or noise rules are needed. Standalone scripts and tests
should define a local catalogue containing only the programs they require.

<!-- tested-example: catalogue-scoped-use -->
```python
from project.utils.commands import GIT, PROJECT_CATALOGUE
from cuprum import scoped, sh

with scoped(catalogue=PROJECT_CATALOGUE):
    git = sh.make(GIT)
    result = git("--no-pager", "log", "-1", "--pretty=%H").run_sync()
    if not result.ok:
        raise SystemExit(result.exit_code)
    last_commit = result.stdout.strip()
```

`sh.make()` resolves an explicit `catalogue=` first, then the innermost
`scoped(catalogue=...)`, then the default catalogue. The builder retains its
resolved catalogue after the scope exits. Prefer a project catalogue rather
than relying on the default catalogue's built-in tools.

Construction and execution are separate checks: an unregistered program raises
`UnknownProgramError` at construction; an active scope that forbids a command
raises `ForbiddenProgramError` at execution, even if its builder used an
explicit catalogue. `scoped(catalogue=...)` activates that catalogue and
narrows the allowlist. Nested scopes cannot widen the enclosing allowlist. A
scope using only `ScopeConfig(allowlist=...)` restricts execution without
selecting a catalogue. Review `allow()` calls as explicit policy changes.

### Capturing output and handling failures

<!-- tested-example: capture-output -->
```python
from cuprum import Program, ProgramCatalogue, RunOutputOptions, scoped, sh

GIT = Program("git")
CATALOGUE = ProgramCatalogue.from_programs(GIT, name="status-script")

with scoped(catalogue=CATALOGUE):
    command = sh.make(GIT)("status", "--short")
    result = command.run_sync(output=RunOutputOptions(capture=True, echo=True))
    if not result.ok:
        raise SystemExit(result.exit_code)
    status = result.stdout
```

By default, `run_sync()` and `await run()` capture decoded stdout and stderr
without echoing them. Use `RunOutputOptions` on the run method to select
capture and echo behaviour. With `capture=False`, captured fields are `None`.
For byte-exact data use `run_bytes_sync()` or `await run_bytes()` rather than
re-encoding text output.

A completed child with a non-zero exit code returns `CommandResult` with
`ok == False`; it does not automatically raise. Check `ok` or `exit_code` and
follow the called tool's exit-code contract. Missing registered executables
raise `FileNotFoundError`; catalogue and policy errors, timeouts, cancellation,
and other execution failures remain exception paths. Do not describe the run
methods as always returning a result.

### Working directory, environment, input, and deadlines

Execution settings belong on `run_sync()` or `run()`, not on the command
builder. Pass directory and environment settings through `ExecutionContext`;
pass `stdin`, `timeout` and `output` to the run method. Builder keywords such as
`cwd=`, `env=` or `timeout=` raise `TypeError` in beta2.

<!-- tested-example: execution-context-input -->
```python
from pathlib import Path
from cuprum import ExecutionContext, Program, ProgramCatalogue, StdinInput, scoped, sh

GIT = Program("git")
CATALOGUE = ProgramCatalogue.from_programs(GIT, name="git-script")
repo_dir = Path(__file__).resolve().parents[1]

with scoped(catalogue=CATALOGUE):
    git = sh.make(GIT)
    result = git("var", "GIT_AUTHOR_IDENT").run_sync(
        context=ExecutionContext(
            cwd=repo_dir,
            env={"GIT_AUTHOR_NAME": "CI", "GIT_AUTHOR_EMAIL": "ci@example.org"},
        ),
        timeout=10,
    )
    if not result.ok:
        raise SystemExit(result.exit_code)

    hashed = git("hash-object", "--stdin").run_sync(
        context=ExecutionContext(cwd=repo_dir),
        stdin=StdinInput(text="release notes\n"),
        timeout=10,
    )
    if not hashed.ok:
        raise SystemExit(hashed.exit_code)
```

The default environment overlays the live parent environment at spawn time;
`ExecutionContext(env={})` still inherits it. For an exact replacement use
`ExecutionContext(env=values, env_mode=EnvMode.REPLACE)`, importing `EnvMode`
from `cuprum.context`. Import `UNSET` from the same module to remove a variable
from an overlay. A replacement environment can omit `PATH`, so prefer an
absolute executable path for deliberately minimal environments.

A deadline raises `cuprum.TimeoutExpired`, a `TimeoutError` subclass; partial
output is available as `exc.output` and `exc.stderr`. Handle it separately from
a non-zero exit. Async cancellation initiates child teardown and re-raises
`asyncio.CancelledError`; never swallow cancellation. For commands that spawn
descendants, consider `ExecutionContext(process_group=...)` with
`ProcessGroupPolicy.OWN_GROUP` on POSIX when the script must own their cleanup.

### Arguments and presence flags

Each positional argument becomes one argv entry. Spaces and shell
metacharacters remain literal. Keyword arguments become `--name=value`, with
underscores converted to hyphens. Booleans are values: `release=True` produces
`--release=True`, which is unsuitable for Cargo's presence flag. Pass presence
flags positionally and omit optional arguments before building; `None` is not
an accepted argument value.

<!-- tested-example: presence-flags -->
```python
from cuprum import Program, ProgramCatalogue, scoped, sh

CARGO = Program("cargo")
CATALOGUE = ProgramCatalogue.from_programs(CARGO, name="build")

with scoped(catalogue=CATALOGUE):
    cargo = sh.make(CARGO)
    command = cargo("build", "--release", target="x86_64-unknown-linux-gnu")
    assert command.argv == (
        "build", "--release", "--target=x86_64-unknown-linux-gnu",
    )
    result = command.run_sync()
    if not result.ok:
        raise SystemExit(result.exit_code)
```

### Pipelines and concurrent commands

Use `|` between command objects to build a pipeline. Check `PipelineResult.ok`
and inspect `failure_index` or the per-stage results: a successful final stage
alone does not prove pipeline success. Only final-stage stdout is captured;
interior stdout feeds the next stage and is `None` in its stage result.

<!-- tested-example: pipeline-results -->
```python
from cuprum import Program, ProgramCatalogue, scoped, sh

GIT = Program("git")
GREP = Program("grep")
CATALOGUE = ProgramCatalogue.from_programs(GIT, GREP, name="history")

with scoped(catalogue=CATALOGUE):
    git = sh.make(GIT)
    grep = sh.make(GREP)
    result = (git("--no-pager", "log", "--oneline") | grep("fix")).run_sync()
    # grep exits 1 when there are no matches; apply the caller's policy.
    if not result.ok:
        raise SystemExit(1)
    shortlog = result.stdout
```

Prefer `run_concurrent()` for async command batches and `run_concurrent_sync()`
for synchronous callers. Bound the number of children with
`ConcurrentConfig(concurrency=...)`:

<!-- tested-example: concurrent-commands -->
```python
from cuprum import ConcurrentConfig, Program, ProgramCatalogue, run_concurrent, scoped, sh

CARGO = Program("cargo")
CATALOGUE = ProgramCatalogue.from_programs(CARGO, name="checks")

async def run_all(catalogue=CATALOGUE):
    with scoped(catalogue=catalogue):
        cargo = sh.make(CARGO)
        return await run_concurrent(
            cargo("check", "--all-targets"),
            cargo("fmt", "--check"),
            config=ConcurrentConfig(concurrency=2),
        )
```

Inspect the aggregate `ok`, `results` and `failures`. Results follow submission
order. With `fail_fast=True`, a non-zero exit cancels remaining commands; use
`submission_indices` and `failure_submission_indices` to map partial results
back to inputs. For mixed async work, use `asyncio.TaskGroup` when a raised
exception must cancel and await siblings. Default `asyncio.gather` propagates
the first exception without cancelling or waiting for siblings; non-zero
command results do not themselves raise.

### Observability hooks

Use `sh.observe()` for structured lifecycle events. Hooks receive `ExecEvent`,
not an object containing `event.result`. Filter by phase before reading fields
specific to that phase:

<!-- tested-example: observer-exit -->
```python
import logging
from cuprum import Program, ProgramCatalogue, scoped, sh

LOGGER = logging.getLogger(__name__)
CARGO = Program("cargo")
CATALOGUE = ProgramCatalogue.from_programs(CARGO, name="checks")


def log_exit(event):
    if event.phase == "exit":
        LOGGER.info("Completed with exit code %s", event.exit_code)


with scoped(catalogue=CATALOGUE), sh.observe(log_exit):
    result = sh.make(CARGO)("check").run_sync()
    if not result.ok:
        raise SystemExit(result.exit_code)
```

Use the `settled` phase and `terminal_outcome` for definitive completion,
including timeout, cancellation, and spawn failure. Register `after(hook)` with
a `hook(cmd, result)` callback when completed command results are needed. Hooks
can affect a run if they raise; protect logging code accordingly. Redact
secrets before exporting arguments, environment values or output to telemetry.

## pathlib: robust path manipulation

### Project roots, joins, and ensuring directories

<!-- tested-example: path-roots -->
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

<!-- tested-example: atomic-file-write -->
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

<!-- tested-example: safe-globbing -->
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

<!-- tested-example: reference-script -->
```python
#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = ["cyclopts>=2.9", "cuprum==0.2.0b2", "cmd-mox"]
# ///

from __future__ import annotations
from pathlib import Path
from typing import Optional, Annotated

import cyclopts
from cyclopts import App, Parameter
from cuprum import ExecutionContext, Program, ProgramCatalogue, scoped, sh

GIT = Program("git")
CATALOGUE = ProgramCatalogue.from_programs(GIT, name="package-script")

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

    if not dry_run:
        dist.mkdir(parents=True, exist_ok=True)
        with scoped(catalogue=CATALOGUE):
            git = sh.make(GIT, catalogue=CATALOGUE)
            tag = f"v{version}"
            result = git("tag", tag).run_sync(context=ExecutionContext(cwd=project_root))
            if result.exit_code != 0:
                head = git("rev-parse", "HEAD").run_sync(context=ExecutionContext(cwd=project_root))
                # Resolve the peeled ref: a bare tag name returns the tag
                # object for an annotated tag, not the commit it points at,
                # so the comparison below would never match. The explicit
                # `refs/tags/` namespace also stops a same-named branch from
                # shadowing the tag.
                tagged = git(
                    "rev-parse", f"refs/tags/{tag}^{{}}"
                ).run_sync(context=ExecutionContext(cwd=project_root))
                tag_matches_head = (
                    head.exit_code == 0
                    and tagged.exit_code == 0
                    and tagged.stdout.strip() == head.stdout.strip()
                )
                if not tag_matches_head:
                    raise SystemExit(result.exit_code)

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

<!-- tested-example: pytest-environment -->
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

<!-- tested-example: pytest-plugin -->
```python
pytest_plugins = ("cmd_mox.pytest_plugin",)
```

The tests below disable the plugin's automatic lifecycle so they can show each
record, replay and verify step explicitly. Cmd-mox intercepts executable lookup
through PATH shims; keep the production catalogue in place. This also applies
to async command batches.

<!-- tested-example: cmd-mox-tests -->
```python
import pytest
from cuprum import ExecutionContext, Program, ProgramCatalogue, scoped, sh

GIT = Program("git")
CATALOGUE = ProgramCatalogue.from_programs(GIT, name="git-tests")


@pytest.mark.cmd_mox(auto_lifecycle=False)
def test_git_tag_happy_path(cmd_mox, tmp_path):

    # Mock external command behaviour
    cmd_mox.mock("git").with_args("tag", "v1.2.3").returns(exit_code=0)

    # Run the code under test while shims are active
    cmd_mox.replay()
    with scoped(catalogue=CATALOGUE):
        sh.make(GIT, catalogue=CATALOGUE)("tag", "v1.2.3").run_sync(
            context=ExecutionContext(cwd=tmp_path)
        )
    cmd_mox.verify()


@pytest.mark.cmd_mox(auto_lifecycle=False)
def test_git_tag_failure_surface_error(cmd_mox, tmp_path):

    cmd_mox.mock("git").with_args("tag", "v1.2.3").returns(exit_code=1, stderr="denied")

    cmd_mox.replay()
    with scoped(catalogue=CATALOGUE):
        result = sh.make(GIT, catalogue=CATALOGUE)("tag", "v1.2.3").run_sync(
            context=ExecutionContext(cwd=tmp_path)
        )
        assert result.exit_code == 1
        assert "denied" in result.stderr
    cmd_mox.verify()
```

### Spies and passthrough capture (turn real calls into fixtures)

<!-- tested-example: cmd-mox-spy -->
```python
import pytest
from cuprum import ExecutionContext, Program, ProgramCatalogue, scoped, sh

ECHO = Program("echo")
CATALOGUE = ProgramCatalogue.from_programs(ECHO, name="echo-tests")


@pytest.mark.cmd_mox(auto_lifecycle=False)
def test_spy_and_record(cmd_mox, tmp_path):

    # Spy records actual usage; passthrough runs the real command
    spy = cmd_mox.spy("echo").passthrough()

    cmd_mox.replay()
    with scoped(catalogue=CATALOGUE):
        sh.make(ECHO, catalogue=CATALOGUE)("hello world").run_sync(
            context=ExecutionContext(cwd=tmp_path)
        )
    cmd_mox.verify()

    # Inspect what happened
    spy.assert_called()
    assert spy.call_count == 1
    args = spy.invocations[0].args
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

Plumbum's default non-zero-exit exception becomes an explicit result check.
Preserve the original command's success criteria and test both failed child
results and exceptions that prevent completion.

1. Replace `plumbum` with the exact `cuprum==0.2.0b2` dependency pin.
2. Declare each executable as a `Program` and construct the shared or local
   `ProgramCatalogue` with `from_programs()`.
3. Activate `scoped(catalogue=CATALOGUE)` and use `sh.make(GIT)` or explicitly
   bind `sh.make(GIT, catalogue=CATALOGUE)` inside the scope.
4. Replace `local["git"]["args"]` with `sh.make(GIT)("args")`. Pass presence
   flags such as `"--release"` positionally, not as Boolean keyword arguments.
5. Replace `command()` and `.run(retcode=None)` with `.run_sync()`. Inspect
   `result.ok` or `result.exit_code` and consume `stdout` and `stderr`.
6. Replace `local.cwd(path)` with
   `.run_sync(context=ExecutionContext(cwd=path))`.
7. Replace `local.env(VAR=value)` with
   `.run_sync(context=ExecutionContext(env={"VAR": value}))`. Use
   `EnvMode.REPLACE` for exact environments and `UNSET` for removals.
8. Keep `|` between cuprum commands, but check the whole `PipelineResult`
   rather than assuming the final stage's exit code represents all stages.
9. Replace executable-discovery `CommandNotFound` handling with
   `FileNotFoundError`. Handle `UnknownProgramError` for catalogue membership
   and `ForbiddenProgramError` for execution policy separately.
10. Replace `ProcessExecutionError` handling with explicit result checks for
    completed children. Catch `TimeoutExpired` for deadlines and preserve
    async cancellation propagation.
11. Update command tests to use cmd-mox PATH shims and the production catalogue;
    exercise cwd, environment, argv, output and failure semantics.

## CI wiring: GitHub Actions (Cyclopts‑first)

<!-- tested-example: ci-build-workflow -->
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
- Completed cuprum commands return a `CommandResult`; check `ok` or
  `exit_code`. Launch failures, policy errors, and deadlines can still raise.
- Production code should present friendly error messages; tests may assert raw
  behaviours (non‑zero exits, stderr contents) via `cmd-mox`.
- On Windows, newline‑separated lists are recommended for `list[Path]` to
  sidestep `;`/`:` semantics.
- Cuprum's catalogue must include all programs used by the script; attempting
  to construct a command for an unregistered program raises
  `UnknownProgramError`.

This document should be referenced when introducing or updating automation
scripts to maintain a consistent developer experience across projects.

[cuprum-guide]: https://github.com/leynos/cuprum/blob/v0.2.0-beta2/docs/users-guide.md
