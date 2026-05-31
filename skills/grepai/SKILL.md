---
name: grepai
description: "Workspace-first GrepAI search workflow for programming agents (v0.34+): project-scoped semantic search, token-efficient output, and reliable fallbacks."
---

# GrepAI Workspace Search (Agent-Focused)

Use this skill when you need to find code by intent in one or more projects
inside a GrepAI workspace.

## Scope and Priority

- Primary tool for intent-based code search: `grepai search`.
- Primary context model: `--workspace <name>` with optional `--project <name>`.
- Use exact-text tools only for exact literals, symbol names, or imports.

Semantic intent examples:

- "where authentication is enforced"
- "how retries are handled"
- "where config is loaded and validated"

Exact-text examples (do not use semantic search):

- exact function name
- exact env var key
- exact import statement

## Current CLI Facts (v0.34.0)

- `grepai search` supports `--workspace <name>`.
- `grepai search` supports repeatable `--project <name>` (`stringArray`).
- `grepai search` supports `--path <prefix>` to constrain results.
- `grepai search` supports `--limit <n>` for result count.
- `grepai search` supports `--json` and `--toon` output modes.
- `--compact` requires `--json` or `--toon`.
- `grepai workspace` provides multi-project management.
- Workspace storage backends are `postgres` or `qdrant` (not GOB).

## Agent Defaults

Use these defaults unless the user asks otherwise:

- Output mode: `--toon --compact` for token efficiency.
- Scope: always include `--workspace`; add `--project` when known.
- Query language: English.
- Query style: describe behavior and intent, not symbol spelling.

## Standard Workflow

1. Verify GrepAI availability and workspace context.

   ```bash
   grepai version
   grepai workspace status Projects
   ```

2. Ensure the workspace is indexed and current.

   ```bash
   grepai workspace status Projects
   ```

   If workspace metadata or index data is missing, report it and ask the user
   to run workspace/index setup tasks.

3. Run an initial scoped semantic search.

   ```bash
   grepai search --workspace Projects --project "$(get-project)" \
     "request validation and auth checks" --toon --compact --limit 8
   ```

4. Refine scope and phrasing iteratively.

   ```bash
   # Multi-project search (repeat --project)
   grepai search --workspace Projects --project api --project web \
     "JWT refresh token rotation" --toon --compact --limit 10

   # Restrict to path prefix inside indexed project(s)
   grepai search --workspace Projects --project api --path src/auth \
     "authorization failure handling" --toon --compact --limit 10
   ```

5. Open top results for full context, then optionally use trace.

   ```bash
   grepai trace callers "ValidateToken" \
     --workspace Projects --project api --toon
   grepai trace callees "HandleLogin" \
     --workspace Projects --project api --toon
   ```

## Query Quality Rules

Good query examples:

- `user authentication middleware and token validation`
- `database retry logic with backoff`
- `startup config loading from environment`

Bad query examples:

- `auth`
- `function`
- exact symbol names (use exact-text search for those)

Guidelines:

- 3 to 7 words is usually best.
- Prefer behavior and outcomes over syntax.

## Output Mode Selection

- `--toon --compact`: default for AI-agent loops.
- `--json --compact`: when downstream tooling needs JSON parsing.
- Human-readable output: manual debugging only.

## Troubleshooting and Recovery

1. Workspace missing (`no grepai project found` style errors).

   Report the missing workspace and ask the user to create/add projects. Do not
   run `workspace create`, `workspace add`, `workspace remove`, or
   `workspace delete` as part of this skill.

2. Empty index (`files/chunks = 0`) or stale results.

   ```bash
   grepai workspace status Projects
   ```

   If the index is empty or stale, report it and ask the user to run indexing.

3. Watcher uncertainty in background mode.

   Report watcher/daemon issues and ask the user to restart watcher services.

4. Embedder/provider failures.

   Verify provider endpoint and model. If using OpenAI provider, verify API key
   presence.

## Fallback Policy

If GrepAI is unavailable or still returns unusable results after setup checks:

1. State the failure mode clearly.
2. Fall back to exact/file-pattern tooling to keep progress.
3. Keep follow-up file reads tightly scoped.

## Quick Command Set

```bash
# Agent baseline (workspace + single project)
grepai search --workspace Projects --project "$(get-project)" \
  "input validation and error mapping" --toon --compact --limit 8

# Cross-project search (subset)
grepai search --workspace Projects --project core --project cli \
  "configuration merge precedence" --toon --compact --limit 10

# JSON compact for scriptable pipelines
grepai search --workspace Projects --project "$(get-project)" \
  "retry policy implementation" --json --compact --limit 5
```

## Keywords

grepai, workspace search, semantic code search, project-scoped search, toon,
compact, agent workflow, token-efficient search, cross-project exploration
