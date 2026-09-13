# Local validation of GitHub Actions with act and pytest (black-box)

This guide focuses on **pre-Continuous Integration (CI) smoke/integration
testing** of a workflow using `act` and `pytest`, treating the workflow as a
**black box**. The assertions target artefacts, workspace side effects, and
structured logs. Host-side command interception is intentionally avoided;
containers execute in isolation.

## TL;DR

- Keep **unit tests** in the action codebase (plain `pytest` or the language's
  runner).
- Integration-test the **workflow** locally via `act`, from a `pytest`
  harness.
- Assert on **artefacts**, **file outputs**, and **logs** (using
  `act --json`).
- Treat results as pre-CI confidence; certify on GitHub runners for
  permissions/OpenID Connect (OIDC) parity.

## Prerequisites

- Container daemon available (Docker or Podman).
- `act` installed.
- Python 3.10+ with `pytest`.
- When using rootless Podman, start the Docker-compatible user socket and
  point `act` at it before running any tests:

  ```bash
  systemctl --user start podman.socket
  export DOCKER_HOST="unix://${XDG_RUNTIME_DIR}/podman/podman.sock"
  ```

  Confirm the socket is listening
  (`systemctl --user status podman.socket`) before invoking `act`. Commands
  that talk to the socket may need escalated permissions if the local
  runtime requires them. If residue from an earlier run remains (stale
  containers or virtual environments), clear it before rerunning.
- Optional but recommended: pin an image to reduce drift:

  ```bash
  act pull_request -P ubuntu-latest=catthehacker/ubuntu:act-latest --list
  ```

## Minimal layout

```plaintext
.github/workflows/selftest.yml
scripts/
  # optional helper scripts used by the workflow
tests/
  fixtures/pull_request.event.json
  test_workflow_integration.py
```

### Example workflow (self-checking)

This job builds a tiny JSON artefact with environment/version data and
uploads it. This provides deterministic material to assert on from the host.

```yaml
# .github/workflows/selftest.yml
name: selftest
on:
  workflow_dispatch:
  pull_request:
jobs:
  selftest:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Build artefact
        run: |
          set -euo pipefail
          mkdir -p out
          python - <<'PY'
          import json, os, platform, sys
          print("Hello from workflow")
          data = {
            "status": "ok",
            "python": sys.version.split()[0],
            "os": platform.platform(),
            "env": {
              "CI": os.getenv("CI", ""),
              "GITHUB_REF": os.getenv("GITHUB_REF", ""),
            },
          }
          with open("out/result.json", "w") as f:
              f.write(json.dumps(data))
          PY
      - name: Upload artefact
        uses: actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02 # v4
        with:
          name: result
          path: out/result.json
```

### Event payload fixture

```json
{
  "pull_request": {"number": 1, "head": {"ref": "test-branch"}},
  "repository": {"full_name": "example/repo"},
  "sender": {"login": "tester"}
}
```

File: `tests/fixtures/pull_request.event.json`.

## Driving `act` from `pytest` (black-box harness)

The harness runs `act`, captures artefacts under a pytest-managed temporary
directory, and reads the JSON log stream. It makes **no attempt** to
intercept commands inside the containers.

```python
# tests/test_workflow_integration.py
import json
import subprocess
from pathlib import Path

EVENT = Path("tests/fixtures/pull_request.event.json")


def run_act(
    job: str = "selftest",
    event_path: Path = EVENT,
    *,
    artifact_dir: Path,
) -> tuple[int, Path, str]:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        "act",
        "pull_request",
        "-j",
        job,
        "-e",
        str(event_path),
        "-P",
        "ubuntu-latest=catthehacker/ubuntu:act-latest",
        "--artifact-server-path",
        str(artifact_dir),
        "--json",  # machine-parseable log stream
        "--rm",  # clean up failed workflow containers
        "-b",  # bind-mount repo as workspace (preserves side effects)
    ]
    completed = subprocess.run(cmd, text=True, capture_output=True)
    logs = completed.stdout + "\n" + completed.stderr
    return completed.returncode, artifact_dir, logs


def test_workflow_produces_expected_artefact_and_logs(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "act-artifacts"
    code, artdir, logs = run_act(artifact_dir=artifact_dir)
    assert code == 0, f"act failed:\n{logs}"

    # Assert artefact presence and contents
    files = list(artdir.rglob("result*/result.json"))
    assert files, f"artefact missing. Logs:\n{logs}"
    data = json.loads(files[0].read_text())
    assert data["status"] == "ok"
    assert data["python"].startswith("3."), data["python"]

    # Assert on log stream: act --json prints one JSON document per line
    saw_greeting = False
    for line in logs.splitlines():
        if not line.lstrip().startswith("{"):
            continue
        try:
            evt = json.loads(line)
        except json.JSONDecodeError:
            continue
        out = evt.get("Output") or evt.get("message") or ""
        if "Hello from workflow" in out:
            saw_greeting = True
            break
    assert saw_greeting, "expected greeting in structured logs"
```

## Artefact layout under `act`

When `actions/upload-artifact` runs under `act`, the artefact server writes a
zip file rather than the raw file. Expect a path such as:

- `<artifact-server-path>/<run-id>/<artifact-name>/<artifact-name>.zip`

Unpack the zip in the test harness if the original file is not available
directly.

## Record -> replay -> verify (closing the loop)

`cmd-mox` complements this harness when a workflow drives helper scripts
that shell out to external command-line interfaces (CLIs). The tooling
follows a record, replay, and verify loop:

1. **Record** a golden trace with passthrough spies.

   ```python
   def test_record(tmp_path: Path, cmd_mox) -> None:
       artifact_dir = tmp_path / "act-artifacts"
       gh = cmd_mox.spy("gh").passthrough()
       cmd_mox.replay()
       code, _, logs = run_act(artifact_dir=artifact_dir)
       assert code == 0, logs
       cmd_mox.verify()
       assert gh.call_count == 1
   ```

2. **Replay** deterministically with mocks. Configure expectations using
   the fluent API and keep verification mandatory, so regressions surface
   quickly.

   ```python
   def test_replay(tmp_path: Path, cmd_mox) -> None:
       artifact_dir = tmp_path / "act-artifacts"
       cmd_mox.mock("gh").with_args(
           "release",
           "view",
           "--json",
           "tagName",
       ).returns(stdout='{"tagName":"v9.9.9"}\n')
       cmd_mox.replay()
       code, _, logs = run_act(artifact_dir=artifact_dir)
       assert code == 0, logs
       cmd_mox.verify()
   ```

3. **Inspect** the journal. After verification, `cmd_mox.journal` exposes
   the captured `Invocation` objects. Serialize the data into JSON lines or
   YAML, so future tests can bootstrap mocks from the same expectations.

## What to assert (beyond exit code)

- **Artefacts:** existence, schema, and specific fields; normalize line
  endings when CRLF matters.
- **Workspace side effects:** files created/modified when using `-b`.
- **Structured logs:** look for key lines (cache keys, matrix values, tool
  versions). Prefer `--json` and parse rather than grepping raw TTY output.
- **Idempotence:** run the same job twice and assert identical artefacts
  (or intentional cache hits).

## Useful `act` flags in this setup

- `-P ubuntu-latest=catthehacker/ubuntu:act-latest`: pin a close runner
  image.
- `-b/--bind`: bind mount the repository; enables checking file side
  effects.
- `--artifact-server-path <dir>`: export uploaded artefacts to a host
  directory.
- `--json`: emit a line-delimited JSON log stream suitable for parsing.
- `--rm`: remove containers after each run to avoid leftover state.
- `-e <event.json>` / `--env` / `--env-file`: control the event and
  environment under test.

## Known limitations (by design)

- **Runner parity:** `act` images are close, not identical, to
  `ubuntu-latest`.
- **Permissions/OIDC:** token scopes, OIDC federation, and GitHub-provided
  credentials cannot be faithfully validated locally; rely on GitHub
  runners.
- **Service containers & networking:** usually fine but can diverge under
  load or with subtle DNS/health-check timing.

## Validation ladder

1. **Local fast loop:** unit tests -> `act` black-box tests via `pytest`.
2. **Authoritative CI:** run the same workflow on GitHub-hosted runners.
3. **End-to-end (privileged paths):** GitHub-only with least-privilege
   tokens; gate behind labels/paths.

This arrangement provides tight feedback for workflow correctness and
orchestration logic, without pretending local containers are perfect
stand-ins for GitHub's environment.
