---
name: sem
description: "Semantic version control — entity-level diffs on top of Git. Use when reviewing code changes, understanding what changed in a commit/PR, diffing files, analyzing impact of changes, or when line-level diffs are insufficient. Triggers: sem diff, semantic diff, what changed, entity diff, function diff, impact analysis, entity blame, dependency graph, code change summary, what broke, what was renamed, show changes semantically, 语义差异, 实体级别差异"
---

# sem — Semantic Version Control

## Why sem exists

Traditional `git diff` shows **line-level changes** — "line 43 changed in file X." This is noisy, hard to review, and loses the structural meaning of what actually happened.

`sem` shows **entity-level changes** — "function `validateToken` was added in `src/auth.ts`." It understands code structure via tree-sitter, so it can tell you that a function was renamed (not deleted + added), that a change was cosmetic (whitespace only), or that a config property value changed from `5` to `20`.

**Use sem when you need to understand *what* changed, not just *where* lines differ.**

## When to use sem

| Scenario | Why sem helps |
|----------|--------------|
| Reviewing working changes before commit | Shows which functions/types/entities were added, modified, or deleted — not raw line noise |
| Understanding a commit or commit range | Entity-level summary instantly answers "what did this commit do?" |
| Comparing two files outside Git | `sem diff file1.ts file2.ts` works without a repo |
| Detecting renames and moves | Three-phase matching (exact ID, structural hash, fuzzy similarity) catches renames that `git diff` shows as delete+add |
| Distinguishing real logic changes from cosmetic ones | Structural hashing ignores whitespace/comments/formatting |
| Impact analysis | `sem impact <entity>` shows what breaks if an entity changes |
| Entity-level blame | `sem blame <file>` shows who last touched each entity, not each line |
| Dependency graphs | `sem graph` shows entity dependency relationships |
| CI/AI pipelines needing structured change data | `--format json` outputs machine-readable change summaries |
| Filtering diffs to specific languages | `--file-exts .py .rs` limits output to relevant file types |
| Piping file changes from external sources | `--stdin` accepts JSON input for custom integrations |

## When NOT to use sem

- When you need the exact line-level patch (use `git diff`)
- When you need to stage/unstage hunks interactively (use `git add -p`)
- When the file type isn't supported and you need precise diffs (sem falls back to chunk-based diffing for unsupported formats)

## Commands

### `sem diff` — Semantic diff (core command)

```bash
# Working directory changes (unstaged)
sem diff

# Staged changes only
sem diff --staged

# Specific commit
sem diff --commit abc1234

# Commit range
sem diff --from HEAD~5 --to HEAD

# Compare two arbitrary files (no git repo needed)
sem diff file1.ts file2.ts

# JSON output for AI agents and CI pipelines
sem diff --format json

# Filter to specific file types
sem diff --file-exts .py .rs

# Read changes from stdin (JSON format)
echo '[{"filePath":"src/main.rs","status":"modified","beforeContent":"...","afterContent":"..."}]' \
  | sem diff --stdin --format json
```

### `sem graph` — Entity dependency graph

```bash
sem graph
```

Shows how entities depend on each other across the codebase.

### `sem impact` — Impact analysis

```bash
# What breaks if this entity changes?
sem impact validateToken
```

Answers the question: "If I change `validateToken`, what else is affected?"

### `sem blame` — Entity-level blame

```bash
sem blame src/auth.ts
```

Like `git blame` but at the entity level — shows who last modified each function, class, type, etc., not each line.

## Supported languages

17 languages with full entity extraction via tree-sitter:

**Programming languages:** TypeScript, JavaScript, Python, Go, Rust, Java, C, C++, C#, Ruby, PHP, Swift, Elixir, Bash, Fortran, Vue

**Structured data:** JSON, YAML, TOML, CSV, Markdown

Everything else falls back to chunk-based diffing.

## Entity matching

sem uses three-phase matching to detect renames and moves, not just additions/deletions:

1. **Exact ID match** — same entity name in before/after
2. **Structural hash match** — same AST structure, different name = renamed/moved (ignores whitespace/comments)
3. **Fuzzy similarity** — >80% token overlap = probable rename

This means `sem` correctly identifies:
- Renames (not shown as delete + add)
- Moves between files
- Cosmetic changes vs. real logic changes

## JSON output format

```bash
sem diff --format json
```

```json
{
  "summary": {
    "fileCount": 2,
    "added": 1,
    "modified": 1,
    "deleted": 1,
    "total": 3
  },
  "changes": [
    {
      "entityId": "src/auth.ts::function::validateToken",
      "changeType": "added",
      "entityType": "function",
      "entityName": "validateToken",
      "filePath": "src/auth.ts"
    }
  ]
}
```

Use `--format json` when:
- Feeding change data to AI agents for code review
- Integrating with CI pipelines
- Building tooling on top of semantic diffs

## Recommended workflows

### Before committing

```bash
# See what entities you changed
sem diff

# Or just staged changes
sem diff --staged
```

### Reviewing a PR or commit range

```bash
# What changed between main and this branch?
sem diff --from main --to HEAD

# Last 5 commits
sem diff --from HEAD~5 --to HEAD
```

### Impact analysis before refactoring

```bash
# Before renaming/modifying an entity, check what depends on it
sem impact myFunction
```

### AI-assisted code review

```bash
# Get structured change data for an AI agent to review
sem diff --format json --from main --to HEAD
```
