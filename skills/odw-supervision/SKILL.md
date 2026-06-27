---
name: odw-supervision
description: >
  Supervise Open Dynamic Workflows (ODW) runs. Use when the user wants to
  inspect, monitor, debug, pause, resume, stop, list, follow logs for, retrieve
  results from, or operate the dashboard/API for an ODW workflow run; when they
  mention ODW run IDs, `odw status`, `odw logs`, `odw result`, `odw serve`,
  `events.jsonl`, `status.json`, `result.json`, `error.json`, `worker.log`,
  run directories, dashboard jobs, SSE streams, Claude Code workflow visibility,
  or workflow supervision.
---

# ODW Supervision

Use this skill to observe and control ODW runs without losing the distinction
between ODW state, agent subprocess state, and the host agent's own actions.

ODW runs are detached background workers. The CLI that starts a run may exit,
but the run persists on disk and can be supervised later by run ID, dashboard,
or API.

## Supervision Flow

1. Identify the run handle: run ID, workflow name, run directory, or dashboard
   entry.
2. Read current state before acting.
3. Follow events or inspect artifacts depending on the question.
4. Use controls only when the user asks or the run is clearly exceeding the
   agreed envelope.
5. Inspect `result.json` or `error.json` before taking follow-up action.

## CLI Surface

Use these commands from a shell with the same ODW config/runs root:

```bash
odw list
odw status <run_id>
odw logs <run_id> --follow
odw result <run_id>
odw pause <run_id>
odw resume <run_id>
odw stop <run_id>
odw serve --open
```

`odw run <script.js>` starts a background worker and prints a run ID.
`odw run <script.js> --wait` blocks until terminal state and prints the final
return value. If `--timeout <seconds>` is used with `--wait`, only the waiting
client times out; the background run continues.

Use `odw logs <run_id|--workflow name> [--follow]` when a workflow name is the
only handle available.

## Run Directory

Runs are stored under:

```text
<runsRoot>/<workflow-slug>/<runId>/
```

Default `runsRoot` is `~/.odw/runs` unless config changes it. Each run has:

| File | Meaning |
| --- | --- |
| `meta.json` | immutable run description: script, args, source, config path, workflow name, adapter, origin |
| `status.json` | mutable state and counters: `pending`, `running`, `paused`, `done`, `failed`, or `stopped` |
| `events.jsonl` | append-only event stream for phases, log lines, agent starts, finishes, and failures |
| `result.json` | final successful return value, wrapped as `{ "value": ... }` |
| `error.json` | failure message and stack |
| `control.json` | pause, resume, or stop request written by the CLI/API |
| `worker.log` | detached worker stdout/stderr |

Read JSON files with tooling that tolerates live writes. `events.jsonl` can have
a torn final line while a worker is appending; skip an invalid final line and
retry.

## State Reading

For a quick status:

```bash
odw status <run_id>
```

For live progress:

```bash
odw logs <run_id> --follow
```

For artifact-level diagnosis:

```bash
RUN_DIR=$(find "${ODW_RUNS_ROOT:-$HOME/.odw/runs}" -type d -name '<run_id>' -print -quit)
python3 -m json.tool "$RUN_DIR/status.json"
tail -n 100 "$RUN_DIR/events.jsonl"
python3 -m json.tool "$RUN_DIR/error.json"
tail -n 200 "$RUN_DIR/worker.log"
```

Prefer the CLI first. Drop to files when the CLI cannot find the run, the user
asks for raw artifacts, or you need to distinguish workflow errors from worker
process errors.

Terminal states are `done`, `failed`, and `stopped`. A run in a terminal state
will not change again. A `running` or `paused` run with a dead worker can appear
as stale in the dashboard view; inspect `worker.log`, `status.json`, and recent
event timestamps.

## Controls

Use controls deliberately:

- `odw pause <run_id>` requests a pause at safe checkpoints.
- `odw resume <run_id>` clears a paused state and lets the worker continue.
- `odw stop <run_id>` requests stop; running agent subprocesses may only stop
  once control reaches a checkpoint.

Do not stop another user's run just because it is noisy. This machine can have
other agents working concurrently.

After any control command, re-read status:

```bash
odw pause "$RUN"
odw status "$RUN"
```

## Dashboard And API

Start the local dashboard:

```bash
odw serve --open
```

Defaults:

- URL: `http://127.0.0.1:4317`
- Read endpoints work from the dashboard server.
- Write endpoints work only on loopback with JSON content type and same-origin
  protections.
- Binding with `--host` off-loopback makes the dashboard readable but refuses
  writes.

Read endpoints:

```text
GET /api/runs
GET /api/runs/:id
GET /api/runs/:id/events
GET /api/runs/:id/events?since=N
GET /api/stream
GET /api/adapters
GET /api/capabilities
```

Write endpoints on loopback:

```text
POST /api/generate
POST /api/runs
POST /api/workflows
POST /api/runs/:id/control
```

Use the API when building tooling or when the user specifically wants machine
readable state:

```bash
curl -s http://127.0.0.1:4317/api/runs | python3 -m json.tool
curl -s http://127.0.0.1:4317/api/runs/"$RUN" | python3 -m json.tool
curl -s http://127.0.0.1:4317/api/runs/"$RUN"/events?since=0
```

Control over API:

```bash
curl -s -X POST http://127.0.0.1:4317/api/runs/"$RUN"/control \
  -H 'content-type: application/json' \
  -d '{"action":"pause"}'
```

Allowed actions are `pause`, `resume`, and `stop`.

## Claude Code Run Visibility

The dashboard can also surface Claude Code workflow runs as
`provider: "claude"`. These entries are read-only:

- ODW can list and display Claude workflow metadata, log-style progress, and
  final result surfaces.
- ODW must not expose raw Claude agent transcripts as if they were ODW events.
- Pause, resume, stop, and write operations are refused for Claude provider
  runs.
- The default scope can include Claude projects across the machine. Narrow it
  with `claudeJobsScope: "project"` in `odw.config.json` when the user wants
  only the served repo and its worktrees.

Use provider tags in API or dashboard output to avoid mixing ODW-owned runs
with observed Claude runs.

## Failure Diagnosis

Use this order:

1. `odw status <run_id>` for state and dispatched agent count.
2. `odw logs <run_id>` for phase and agent-level events.
3. `error.json` for workflow-level failure.
4. `worker.log` for detached worker stderr/stdout, crashes, missing executables,
   adapter launch errors, or config load problems.
5. `meta.json` for source directory, script path, config path, args, budget, and
   adapter override.
6. Adapter config and PATH when the error is "command not found" or an agent CLI
   is not installed.

Common causes:

- Bad workflow source: loader rejects non-literal `meta`, stray imports, syntax
  errors, or invalid top-level exports.
- Bad args: `--args` that looks like JSON but does not parse is rejected.
- Adapter routing: `agent(..., { model })` only works when the adapter declares
  a model flag; otherwise a routing note appears in logs.
- Workspace mismatch: copy mode isolates edits, so generated file changes are
  in the agent workspace/diff, not the real source tree.
- Unsafe shared workspace: `workspaceMode: "inplace"` means agents share and
  modify the real `--source` directory.
- Runaway loop: total dispatch cap or budget guard aborts the run.

## Acting On Results

Treat `result.json` as workflow output, not as an instruction to blindly apply
changes. Before acting:

- Confirm terminal state is `done`.
- Read the returned value with `odw result <run_id>` or `result.json`.
- Inspect any file paths, patches, summaries, or recommendations referenced by
  the result.
- Validate changes in the target repo with that repo's gates before committing.
- Report failed or stopped runs with the concrete state, useful log lines, and
  artifact paths.

ODW does not commit, push, merge, or apply diffs by itself. Those remain host
agent responsibilities after inspection.
