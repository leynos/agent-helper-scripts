---
name: codescene-cli
description: >
  Run CodeScene code health analyses locally with the `cs` CLI. Use this skill
  whenever the user wants to analyse non-committed or staged changes, compare
  branches or commits with a delta analysis, lint a file for code health issues,
  wire CodeScene into git hooks, editors, or CI, validate or edit
  `.codescene/code-health-rules.json` from the command line, or install,
  update, or activate the CodeScene CLI. Triggers include `cs delta`,
  `cs review`, `cs check`, `cs check-rules`, `cs rules-config`, and requests to
  "run CodeScene locally" or "check code health before committing".
---

# CodeScene CLI (`cs`)

The CodeScene CLI runs code health analyses where developers work: locally, in
pre-commit/push hooks, and in CI. Core workflows:

- **`cs delta`** — change-based analysis between the working tree, commits, or
  branches. Use before opening a PR to see the code health impact of a change.
- **`cs review`** / **`cs check`** — file-focused feedback. `review` prints a
  JSON structure; `check` prints lint-style output for editor integration.
- **`cs rules-config`** / **`cs check-rules`** — validate and edit custom code
  health rules from the command line.

For the semantics of `.codescene/code-health-rules.json` itself (rule names,
weights, thresholds, `@codescene` directives), use the `codescene-health-rules`
skill; this skill covers the CLI tooling around it.

______________________________________________________________________

## Choosing the Right Command

| Task                                             | Command                              |
| ------------------------------------------------ | ------------------------------------ |
| Analyse all non-committed changes                | `cs delta`                           |
| Analyse only staged content (pre-commit hook)    | `cs delta --staged`                  |
| Compare a feature branch against main            | `cs delta main feat`                 |
| Machine-readable findings for a single file      | `cs review file.py`                  |
| Lint-style output for an editor or quick check   | `cs check file.py`                   |
| See which custom rule set matches a file         | `cs check-rules file.py`             |
| Validate or edit `code-health-rules.json`        | `cs rules-config <subcmd>`           |
| Emit a starter `code-health-rules.json` template | `cs docs code-health-rules-template` |

______________________________________________________________________

## `cs delta` — Change-Based Analysis

```bash
cs delta                        # analyse all non-committed changes
cs delta --staged               # examine only staged content
cs delta --file src/Server.js   # analyse one file
cs delta main                   # analyse changes against the main branch
cs delta main feat              # analyse changes between two branches
cs delta main~30 main           # analyse the latest 30 commits on main
cs delta --output-format json   # machine-readable output
```

Key behaviour:

- Specifying any `--output-format` (json or edn) reports **new issues only** —
  no improvements or explanations. Add `--pretty` to pretty-print.
- `--interactive` forces user input for findings (see `cs docs interactive`).
- `--git-hook` adapts the command for use in a git hook (see
  `cs docs git-hooks`).

### Git hook integration

A pre-commit hook running `cs delta --staged --git-hook` catches code health
regressions before they reach the remote. Generate a working example with:

```bash
cs docs pre-commit-hook-example              # plain pre-commit hook
cs docs interactive-pre-commit-hook-example  # interactive variant
```

______________________________________________________________________

## `cs review` and `cs check` — File-Focused Analysis

Both accept a file path, a `<ref>:<path>` git reference, or stdin:

```bash
cs review test.c                        # working-tree file, JSON results
cs review master:./test.c               # the file as it is on master
cs review 801b0c0f:./test.c             # the file at a given commit
cs review --file-name test.c < test.c   # read file data from stdin

cs check test.c                         # same targets, lint-like output
cs check --file-name test.c < test.c
```

- `--file-name` is required when reading from stdin so the CLI can infer the
  language from the extension.
- `cs review` supports `--output-format json|edn` and `--pretty`.
- `cs check` is designed for editor integration — see `cs docs vim` for a
  (neo)vim example.

______________________________________________________________________

## `cs rules-config` — Edit Rules from the CLI

Validates and edits `code-health-rules.json` without hand-editing JSON.
Defaults to `.codescene/code-health-rules.json` in the current git repository;
override with `--config-path <path>`.

```bash
cs rules-config validate
cs rules-config validate --config-path /tmp/code-health-rules.json

# Disable or enable a rule (single rule_set in the file)
cs rules-config set-rule --rule-name "Complex Method" --enabled false

# With multiple rule_sets, select one via its glob
cs rules-config set-rule --matching-content-path "**/*.js" \
  --rule-name "Complex Method" --enabled false

# Set a threshold
cs rules-config set-threshold \
  --threshold-name function_lines_of_code_warning --value 120

# List the threshold names and defaults for a language
cs rules-config list-thresholds --language Python --format json
```

Behavioural notes:

- `--enabled true` stores weight `1.0`; `--enabled false` stores weight `0.0`.
  For intermediate weights (down-prioritizing rather than disabling), edit the
  JSON directly — see the `codescene-health-rules` skill.
- If no config file exists, `set-rule`/`set-threshold` create a minimal one at
  the default path before applying the change.
- With multiple `rule_set` entries and no `--matching-content-path`, the
  command fails and prints the available selectors.
- Unknown rule or threshold names fail with suggestions.
- If an update would create invalid config, the original file is restored.

Use `cs check-rules <file>` to confirm which rule set a given file matches —
invaluable when debugging glob patterns.

______________________________________________________________________

## `cs docs` — Built-In Documentation Topics

```bash
cs docs git-hooks                    # delta in a git hook
cs docs interactive                  # delta interactive mode
cs docs pre-commit-hook-example      # outputs an example pre-commit hook
cs docs vim                          # "check" integration for (neo)vim
cs docs license                      # setting up a license
cs docs file-name                    # file-name and language support
cs docs code-health-rules            # customizing code health rules
cs docs code-health-rules-template   # outputs a rules template
```

______________________________________________________________________

## Environment Variables

| Variable                   | Purpose                                    |
| -------------------------- | ------------------------------------------ |
| `CS_ACCESS_TOKEN`          | Personal Access Token for licensing        |
| `CS_ACCOUNT_ID`            | Cloud account for `cs auth login` (OAuth)  |
| `CS_ONPREM_URL`            | Base URL for CodeScene Enterprise          |
| `CS_DISABLE_VERSION_CHECK` | Disable the automatic version check        |
| `CS_CERTS`                 | Extra trusted certs (DER/PEM/PKCS12 paths) |
| `CS_CERTS_PASSWORD`        | Password for PKCS12 files                  |

Licensing uses a **Personal Access Token** in `CS_ACCESS_TOKEN`; the older
"CodeScene CLI" / devtools tokens are deprecated. `cs version` prints the build
date and SHA of the installed tool.

______________________________________________________________________

## Reference Files

- [`references/command-reference.md`](references/command-reference.md) — Full
  options for every command, verbatim from the upstream reference
- [`references/install-and-activate.md`](references/install-and-activate.md) —
  Installation, updating, licensing, and platform-specific notes
