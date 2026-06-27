---
name: odw-authoring
description: >
  Author Open Dynamic Workflows (ODW) workflow scripts. Use when the user wants
  to design, write, review, repair, or run-check an ODW workflow; when they
  mention `odw`, Open Dynamic Workflows, Claude Code workflow dialect, dynamic
  workflows, multi-agent orchestration, `agent()`, `parallel()`, `pipeline()`,
  nested `workflow()`, workflow generation, JSON-Schema agent outputs, adapter
  routing, `workspaceMode`, `inplace`, multi-provider handoff, or examples such
  as fan-out/reduce, deep research, adversarial verification, routing,
  tournament, or loop-until-dry workflows.
---

# ODW Authoring

Use this skill to write reliable ODW workflow scripts: plain JavaScript files in
Claude Code's workflow dialect, executed by the `odw` CLI outside the host
agent's context.

ODW is useful when a task benefits from isolated agent subprocesses,
parallelism, adversarial checks, or a long-running plan whose intermediate
output should stay out of the host context. Do the task directly when one normal
agent turn is enough.

## Authoring Flow

1. Classify the orchestration pattern.
2. Draft a workflow script with literal `meta`, injected primitives, bounded
   fan-out, and explicit phases.
3. Use schemas anywhere a later step consumes agent output as data.
4. Validate or dry-check the source before running it.
5. Run with `odw run`, inspect the result, and only then act on outputs.

## Script Contract

Start every workflow with a pure literal `meta` export:

```js
export const meta = {
  name: 'fan-out-reduce',
  description: 'Draft in parallel, then synthesize the best answer.',
  whenToUse: 'Questions worth attacking from independent angles.',
  phases: [{ title: 'Draft' }, { title: 'Synthesize' }],
}
```

Follow these rules:

- Keep `meta.name` and `meta.description` present.
- Keep `meta` literal: no variables, spreads, function calls, or template
  interpolation.
- Use top-level `await` and top-level `return`; ODW wraps the body in an async
  function.
- Do not import primitives. `agent`, `parallel`, `pipeline`, `phase`, `log`,
  `args`, `budget`, `workflow`, and `validate` are injected globals.
- Do not add other top-level `import` or `export` statements.
- Keep helper functions in the same file unless the workflow intentionally uses
  nested `workflow()` for another managed workflow.
- Prefer explicit phase names and pass `{ phase: 'Name' }` inside concurrent
  sections so dashboard lanes stay accurate.

## Primitive Choices

Use `agent(prompt, opts?)` for every real subtask. Important options:

- `schema`: JSON Schema contract; validated replies return objects.
- `label`: short progress name shown in logs and the dashboard.
- `phase`: per-call phase override, especially inside concurrency.
- `adapter`: choose a CLI such as `codex`, `claude`, `gemini`, `qwen`, or
  `kimi`.
- `model`: forward a model id only when the adapter declares a model flag.
- `agentType`: persona injected into the prompt. It is not an adapter name.
- `isolation: 'worktree'`: request isolated workspace semantics. In ODW this is
  satisfied by copy isolation, not by creating a real git worktree.

Use `parallel(thunks)` when the next step needs the whole batch at once:

```js
const drafts = await parallel(
  Array.from({ length: 4 }, (_, i) => () =>
    agent(`Draft #${i + 1}: ${question}`, {
      label: `draft-${i + 1}`,
      phase: 'Draft',
    })
  ),
)
const good = drafts.filter(Boolean)
```

Use `pipeline(items, ...stages)` for multi-stage per-item flow where items can
advance independently:

```js
const judged = await pipeline(
  findings,
  (finding) => agent(`Review this finding:\n${finding.detail}`, {
    phase: 'Verify',
    schema: VERDICT,
  }),
  (verdict, finding) => ({ finding, verdict }),
)
```

Use `workflow(ref, args?)` for one nested child workflow. It shares scheduler,
concurrency cap, total agent counter, budget tally, control state, and event
sink with the parent. The current implementation supports one nested level;
calling `workflow()` again inside a child fails clearly.

Use `validate(source)` when a workflow generates workflow source and needs a
compile check before running or saving it. This is an ODW extension; do not
expect the same script to run unchanged in Claude Code if it depends on
`validate()`.

## Schemas

Use schemas whenever downstream JavaScript needs structured data. Keep schemas
literal and simple. Supported keywords include `type`, `properties`,
`required`, `additionalProperties`, `items`, `minItems`, and `enum`.

```js
const FINDINGS = {
  type: 'object',
  properties: {
    findings: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          title: { type: 'string' },
          detail: { type: 'string' },
        },
        required: ['title', 'detail'],
      },
    },
  },
  required: ['findings'],
}
```

Avoid parsing free text in later stages when a schema would make the hand-off
deterministic.

## Pattern Library

Pick the smallest pattern that fits the task:

- Fan-out/reduce: generate independent drafts with `parallel`, dedupe or filter
  in JavaScript, then synthesize once.
- Deep research: plan angles, fan out searches, extract claims, run skeptical
  votes, then report only verified claims.
- Adversarial verification: one finder proposes candidates; several independent
  refuters try to kill each candidate; keep only survivors.
- Loop until dry: bound a `while` loop with both `maxRounds` and a dry-round
  stop; dedupe with a `Set`.
- Routing: classify against an enum of route keys, call one specialist, then
  grade the result.
- Generate and filter: generate breadth from varied lenses, normalize and
  dedupe in JavaScript, grade each idea against a rubric.
- Tournament: create distinct competitors, then judge pairwise in rounds until
  one remains.
- Multi-adapter loop: use `adapter` per call, for example one CLI implements
  and another reviews. Only use shared on-disk handoff with `workspaceMode:
  "inplace"` and a throwaway `--source` directory unless the user explicitly
  wants real-tree edits.

## Workspace Mode

Assume `workspaceMode: "copy"` unless proven otherwise. In copy mode each
`agent()` call runs in its own throwaway copy of `--source`; files, branches,
worktrees, build artefacts, and other local state created by one agent are not a
handoff channel to later agents.

Use `workspaceMode: "inplace"` only when later agents must observe filesystem or
git state created by earlier agents. This is required for shared-directory
implement/review loops, multi-provider workflows that pass code through disk, and
roadmap-build workflows that intentionally create git worktrees, commit, merge,
or push.

When a workflow needs real git worktrees, make the workflow own that lifecycle in
its prompts and run it in `inplace` mode. Do not rely on
`agent(..., { isolation: "worktree" })` for this; ODW treats that option as a
request for isolated copy workspaces, not a persistent git-worktree lifecycle.

Prefer a throwaway `--source` directory for `inplace` runs. Point `--source` at a
real repository only when the user explicitly wants real-tree edits and accepts
that subagents may modify files, create worktrees, commit, merge, or push.

For multi-provider workflows, keep provider differences explicit:

- Use `adapter` per call for role assignment, such as `claude` for implementation
  and `codex` for review.
- Configure command permissions per adapter in `odw.config.json`; do not assume
  each CLI can edit files, run commands, or use the same model flag.
- Use schemas for cross-provider handoffs so one provider's prose does not become
  another provider's parser contract.
- Serialize shared git operations with a JavaScript lock or single integration
  phase; let providers work concurrently only in independent worktrees or
  independent read-only checks.

## Safety And Determinism

- Bound fan-out with args, `budget.total`, `maxRounds`, and ODW config
  `maxAgents`.
- Filter `null` slots after `parallel` or `pipeline`; failures inside those
  helpers do not sink the whole batch.
- Keep reductions order-independent: dedupe by keys, tally votes, sort by score.
  Do not branch on which agent finished first.
- Treat `budget.spent()` and `budget.remaining()` as estimated output-token
  accounting. Use them to scale depth, not as exact billing.
- Remember that ODW never commits, pushes, or applies diffs by itself. The host
  agent must inspect the returned result before acting.
- When using Claude with command execution, only override it with
  `--dangerously-skip-permissions` against a throwaway source directory.

## Run Commands

Run a script and wait for the final return value:

```bash
odw run workflow.js --wait --args '{"question":"Design a rate limiter."}'
```

Start in the background and supervise separately:

```bash
RUN=$(odw run workflow.js --args @args.json)
odw status "$RUN"
odw logs "$RUN" --follow
odw result "$RUN"
```

Common flags:

- `--source <dir>`: working directory and anchor for relative script paths.
- `--config <path>`: adapter and runtime config.
- `--adapter <name>`: default adapter for this run; explicit per-call
  `agent(..., { adapter })` still wins.
- `--budget <tokens>`: exposes `budget.total` to the script.
- `--timeout <s>` with `--wait`: stop waiting after the timeout; the run
  continues.

## Example Skeleton

```js
export const meta = {
  name: 'review-and-verify',
  description: 'Find candidate issues, then keep only independently verified ones.',
  phases: [{ title: 'Find' }, { title: 'Verify' }, { title: 'Report' }],
}

const FINDINGS = {
  type: 'object',
  properties: {
    findings: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          title: { type: 'string' },
          detail: { type: 'string' },
        },
        required: ['title', 'detail'],
      },
    },
  },
  required: ['findings'],
}

const VERDICT = {
  type: 'object',
  properties: {
    refuted: { type: 'boolean' },
    reason: { type: 'string' },
  },
  required: ['refuted'],
}

const target = (args && args.target) || 'Review this change for correctness bugs.'
const voters = Math.max(1, Number(args && args.voters) || 3)

phase('Find')
const found = await agent(target, {
  label: 'finder',
  phase: 'Find',
  schema: FINDINGS,
})
const findings = found.findings || []

phase('Verify')
const judged = await pipeline(findings, (finding) =>
  parallel(
    Array.from({ length: voters }, (_, i) => () =>
      agent(
        `Try to refute this finding. Default to refuted=true if unsure.\n` +
          `Title: ${finding.title}\nDetail: ${finding.detail}`,
        { label: `refute-${i + 1}`, phase: 'Verify', schema: VERDICT },
      )
    ),
  ).then((votes) => {
    const valid = votes.filter(Boolean)
    const refuted = valid.filter((vote) => vote.refuted).length
    return { finding, kept: refuted <= Math.floor(valid.length / 2), votes: valid }
  }),
)

phase('Report')
const confirmed = judged.filter(Boolean).filter((item) => item.kept)
return {
  considered: findings.length,
  confirmed: confirmed.map((item) => item.finding),
}
```
