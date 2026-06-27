# ODW Skills User's Guide

This guide explains how to ask an agent to use the Open Dynamic Workflows
(ODW) skills in this repository.

Use the two skills for different parts of the ODW lifecycle:

- `$odw-authoring`: use when you want an agent to design, write, review, or run
  check an ODW workflow script.
- `$odw-supervision`: use when an ODW workflow is already running, finished,
  failed, paused, or needs monitoring or control.

The shortest useful rule is:

- Use `$odw-authoring` to create the workflow that will do the work.
- Use `$odw-supervision` to operate or inspect the workflow once it is running.

## Invoking the skills

When the skills are installed in the agent's skill directory, invoke them
explicitly:

```text
Use $odw-authoring to write an ODW workflow for ...
```

```text
Use $odw-supervision to inspect ODW run <run_id>.
```

Explicit invocation is best because it removes ambiguity. The skill
descriptions should also trigger implicitly for prompts that mention ODW,
dynamic workflows, `agent()`, `parallel()`, `pipeline()`, `odw status`,
`odw logs`, run IDs, or the ODW dashboard.

If the skills are not installed yet, point the agent at a stable repository or
installed path. From this checkout, relative paths are enough:

```text
Use the skill at skills/odw-authoring to write an ODW workflow for ...
```

```text
Use the skill at skills/odw-supervision to inspect run <run_id>.
```

For the managed helper checkout, use:

```text
Use the skill at
${HELPER_TOOLS_REPO_DIR:-$HOME/git/agent-helper-scripts}/skills/odw-authoring
to write an ODW workflow for ...
```

After installation, the Codex paths are also stable:

```text
Use the skill at ~/.codex/skills/odw-authoring to write an ODW workflow for ...
Use the skill at ~/.codex/skills/odw-supervision to inspect run <run_id>.
```

## Using `$odw-authoring`

Use `$odw-authoring` when a task benefits from fan-out, adversarial review,
multiple independent agents, structured multi-stage work, or long-running work
that should stay outside the host agent's context.

Example:

```text
Use $odw-authoring to write an ODW workflow that reviews this repository for
configuration drift. It should fan out across docs, CI, dependency config, and
runtime scripts, then synthesize one prioritized report. Use Codex as the
default adapter and keep the workflow bounded.
```

A good agent should then:

- Load the `odw-authoring` skill.
- Pick a workflow pattern, such as fan-out/reduce, adversarial verification,
  routing, tournament, or loop-until-dry.
- Write a plain JavaScript workflow with `export const meta = { ... }`.
- Use ODW's injected globals, such as `agent()`, `parallel()`, `pipeline()`,
  `phase()`, `log()`, `args`, `budget`, `workflow()`, and `validate()`.
- Add JSON Schemas where later workflow stages need structured data.
- Keep fan-out, loops, and agent calls bounded.
- Use `validate(source)` only inside workflows that generate workflow source.
- Run the workflow with an explicit `odw run <script.js|name>` target when
  asked.

For an implementation-oriented request, give the agent the file path, pattern,
result shape, and run expectation:

```text
Use $odw-authoring to create `.odw/workflows/review-docs.js`.

The workflow should:
- scan README.md, docs/, and skills/
- use three independent reviewers in parallel
- have one synthesizer produce a final Markdown report
- return structured JSON with summary, findings, and followups
- accept { "focus": "..." } as args

After writing it, run it with:
`odw run .odw/workflows/review-docs.js --wait --args '{"focus":"..."}'`.
```

### What to include in an authoring prompt

Include the details that affect orchestration:

- The task or question.
- Whether to save a workflow file or only draft one.
- The target source directory.
- The preferred adapter, such as `codex`, `claude`, `gemini`, `qwen`, `kimi`,
  or a configured custom adapter.
- Whether the workflow should run immediately.
- Bounds such as number of agents, max rounds, budget, or timeout.
- The desired result shape, such as Markdown report, JSON object, patches, or
  findings.
- Whether agents need to share files or git state. Ask for `workspaceMode:
  "inplace"` only when later agents must see files, branches, worktrees, commits,
  or build artefacts created by earlier agents.

Example:

```text
Use $odw-authoring to write and run a bounded ODW workflow for this repo.

Goal: find stale documentation that references moved skills.
Pattern: fan out over docs, tests, and Makefile, then synthesize.
Adapter: codex.
Bounds: max 6 agent calls.
Return: JSON with stale_refs, recommended_edits, and confidence.
```

For side-effecting multi-provider workflows, make the trust boundary explicit:

```text
Use $odw-authoring to adapt the df12-build workflow for ODW.

Goal: run roadmap tasks with Claude implementing and Codex reviewing.
Workspace: this intentionally edits a real repository, creates git-donkey
worktrees, commits, merges, and may push. Use workspaceMode "inplace"; do not
use copy mode for cross-agent worktree handoff.
Providers: assign adapters per phase, e.g. claude for implementation, codex for
code review, and a second provider for adversarial design review where useful.
Safety: serialize integration and pushes behind one merge lock; allow parallel
work only in independent worktrees. Use schemas for all cross-provider returns.
```

Avoid `inplace` for ordinary review or research workflows. In copy mode each
agent gets an isolated workspace, which is safer when no later agent needs to see
that agent's filesystem changes.

## Using `$odw-supervision`

Use `$odw-supervision` when there is already a run ID, a workflow name, a
suspected stuck run, a failed run, or a dashboard/API question.

Example:

```text
Use $odw-supervision to inspect ODW run abc123. Tell me whether it is still
running, what phase it is in, how many agents have completed, and whether there
are any failures.
```

The agent should prefer ODW's supervision commands first:

```bash
odw status abc123
odw logs abc123
odw result abc123
```

If needed, it can inspect the run directory under the configured runs root,
usually:

```text
~/.odw/runs/<workflow-slug>/<runId>/
```

Useful files in a run directory:

- `meta.json`: script, args, source, config, workflow name, and adapter.
- `status.json`: current state and counters.
- `events.jsonl`: phase, log, and agent event stream.
- `result.json`: successful final return value.
- `error.json`: failure message and stack.
- `control.json`: pause, resume, or stop request.
- `worker.log`: detached worker stdout and stderr.

### Failure diagnosis

Ask for diagnosis without allowing a rerun when you want a clean explanation:

```text
Use $odw-supervision to diagnose why run abc123 failed. Check the CLI status,
events, error.json, worker.log, and meta.json. Do not rerun it yet; just tell me
the concrete cause and the safest next step.
```

The agent should separate:

- Workflow source or argument errors.
- Adapter launch errors.
- Agent subprocess failures.
- Schema validation failures.
- Workspace or config mismatches.
- Runaway loops, dispatch caps, or stop requests.

For `inplace` or multi-provider runs, ask the agent to inspect both ODW state and
the real repository state:

```text
Use $odw-supervision to diagnose run abc123. This was intended to be an
inplace, multi-provider roadmap build. Check meta.json, config, events.jsonl,
adapter labels, returned worktree paths, git status, git worktree list, recent
branches, and whether integration/push phases were serialized. Do not rerun it
until you have identified whether this is a workflow bug, adapter failure, or
workspaceMode mismatch.
```

When a workflow passes files, branches, or worktree paths between agents, a run
launched in copy mode is usually a configuration error. When a workflow runs in
`inplace`, assume it may have left real repository side effects and inspect them
before rerunning or cleaning up.

### Controls

Ask explicitly before using control actions:

```text
Use $odw-supervision to pause run abc123, confirm it paused, and summarize what
was active when it paused.
```

The agent should use:

```bash
odw pause abc123
odw status abc123
```

Control commands are:

- `odw pause <run_id>`
- `odw resume <run_id>`
- `odw stop <run_id>`

Do not ask an agent to stop a run unless you actually want it stopped. Other
agents may be working on the same machine.

### Dashboard and API

Use `$odw-supervision` for dashboard work:

```text
Use $odw-supervision to start the ODW dashboard for this repo and tell me the
local URL. Use project-scoped Claude Code visibility if the config supports it.
```

Expected command:

```bash
odw serve --open
```

The default dashboard URL is:

```text
http://127.0.0.1:4317
```

Use the API when you need machine-readable state:

```bash
curl -s http://127.0.0.1:4317/api/runs | python3 -m json.tool
curl -s http://127.0.0.1:4317/api/runs/"$RUN" | python3 -m json.tool
curl -s http://127.0.0.1:4317/api/runs/"$RUN"/events?since=0
curl -s http://127.0.0.1:4317/api/runs/"$RUN"/result | python3 -m json.tool
```

## End-to-end example

First, ask the agent to author and start a workflow:

```text
Use $odw-authoring to write a workflow that performs adversarial verification
of this branch. It should have one finder agent, three refuter agents per
finding, and a final reporter. Save it under
`.odw/workflows/adversarial-review.js` and run it in the background.
```

The agent writes the workflow and starts it:

```bash
odw run .odw/workflows/adversarial-review.js --args '{"target":"current branch"}'
```

ODW prints a run ID. Then supervise that run:

```text
Use $odw-supervision to follow run <run_id> until it reaches a terminal state.
If it fails, diagnose it. If it succeeds, summarize the result and point me to
the returned JSON or artifact.
```

This keeps the responsibilities clear. `$odw-authoring` designs the workflow.
`$odw-supervision` watches and operates the detached run.

## Prompt templates

Use these as starting points.

Author a workflow:

```text
Use $odw-authoring to create <path>.

Goal: <what the workflow should accomplish>.
Pattern: <fan-out/reduce, adversarial verification, routing, tournament, etc.>.
Adapter: <adapter name or "use the project default">.
Bounds: <max agents, max rounds, budget, timeout>.
Inputs: <args shape>.
Return: <Markdown, JSON, findings, patch summary, etc.>.
Run: <yes/no, background/wait>.
```

Inspect a run:

```text
Use $odw-supervision to inspect run <run_id>.

Report:
- current state
- active or most recent phase
- completed, running, and failed agent counts
- last useful log lines
- whether result.json or error.json exists

Do not stop, resume, or rerun it.
```

Diagnose a failed run:

```text
Use $odw-supervision to diagnose failed run <run_id>.

Check status, events, error.json, worker.log, and meta.json. Tell me the
concrete cause, whether this is a workflow bug, adapter/config issue, or agent
subprocess failure, and the safest next action. Do not rerun it yet.
```

Start the dashboard:

```text
Use $odw-supervision to start `odw serve --open` for this repo. Tell me the URL
and whether it is using all Claude Code jobs or project-scoped visibility.
```

## Common mistakes

- Asking `$odw-authoring` to supervise a run. Use `$odw-supervision` once a run
  exists.
- Asking `$odw-supervision` to invent a workflow. Use `$odw-authoring` for
  script design.
- Omitting bounds for loops or large fan-out. Always set max rounds, max agent
  counts, or budget guidance.
- Treating `result.json` as an instruction to blindly apply changes. Inspect
  the result, then validate any local edits through the target repo's gates.
- Using shared `workspaceMode: "inplace"` without a throwaway source directory.
  Keep copy isolation unless the workflow intentionally needs shared on-disk
  handoff.
