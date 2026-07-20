# CodeScene CLI Command Reference

Condensed from the upstream command reference. Run any command with `-h` /
`--help` for the authoritative help text of the installed version.

______________________________________________________________________

## `cs delta`

Run a delta analysis: compare current work against a previous state of the
code. See also `cs docs git-hooks`.

```text
USAGE
  $ cs delta [<options>] [<branch> [<branch>]]

OPTIONS
      --staged        Examine only staged content.
      --interactive   Interactive mode, forcing user input for findings.
                      See `cs docs interactive`.
      --git-hook      Run as a git hook. See `cs docs git-hooks`.
      --output-format Output in json or edn format. Default human-readable.
      --pretty        Use with --output-format to pretty-print.
      --verbose       Verbose output
  -h, --help          Show help
```

Examples:

```bash
cs delta                       # analyse all non-committed changes
cs delta --file src/Server.js  # analyse one file
cs delta --output-format json  # json output; reports NEW issues only —
                               # no improvements or explanations
cs delta main                  # analyse changes against the main branch
cs delta main feat             # analyse changes between two branches
cs delta main~30 main          # analyse the latest 30 commits on main
```

______________________________________________________________________

## `cs review`

Check a file for code health issues and print the results as JSON.

```text
USAGE
  $ cs review [<options>] [<file>]

OPTIONS
      --file-name     File-name when reading from stdin
      --output-format Output in json or edn format. Default human-readable.
      --pretty        Use with --output-format to pretty-print.
      --verbose       Verbose output
  -h, --help          Show help
```

Examples:

```bash
cs review test.c                       # check the file test.c
cs review master:./test.c              # test.c as on the master branch
cs review 801b0c0f:./test.c            # test.c at the given commit
cs review --file-name test.c < test.c  # read file data from stdin
```

______________________________________________________________________

## `cs check`

Check a file for code health issues and print the results in a lint-like manner.

```text
USAGE
  $ cs check [<options>] [<file>]

OPTIONS
      --file-name File-type/extension when reading from stdin
      --verbose   Verbose output
  -h, --help      Show help
```

Examples:

```bash
cs check test.c                       # check the file test.c
cs check master:./test.c              # test.c as on the master branch
cs check 801b0c0f:./test.c            # test.c at the given commit
cs check --file-name test.c < test.c  # read file data from stdin
```

______________________________________________________________________

## `cs check-rules`

Find out which custom rules, if any, match the given file. Useful when creating
a custom `code-health-rules.json`.

```bash
cs check-rules test.c   # which code health rule set matches test.c
```

______________________________________________________________________

## `cs rules-config`

Validate and edit a `code-health-rules.json` configuration file. Four
subcommands: `validate`, `set-rule`, `set-threshold`, `list-thresholds`.

```text
USAGE
  $ cs rules-config validate [--config-path <path>]
  $ cs rules-config set-rule --rule-name <name> --enabled true|false
        [selector-options]
  $ cs rules-config set-threshold --threshold-name <name>
        --value <positive-int> [selector-options]
  $ cs rules-config list-thresholds --language <name> [--format json]
        [--config-path <path>]

SELECTOR OPTIONS
  --matching-content-path <glob>  Required when multiple rule sets exist

COMMON OPTIONS
  --config-path <path>  Defaults to .codescene/code-health-rules.json in the
                        current git repo
  --language <name>     Language name, e.g. Python, JavaScript, Java
  --format json         Output format (only json is supported)
```

Examples:

```bash
cs rules-config validate
cs rules-config validate --config-path /tmp/code-health-rules.json
cs rules-config set-rule --rule-name "Complex Method" --enabled false
cs rules-config set-rule --matching-content-path "**/*.js" \
  --rule-name "Complex Method" --enabled false
cs rules-config set-threshold \
  --threshold-name function_lines_of_code_warning --value 120
cs rules-config set-threshold \
  --threshold-name function_lines_of_code_warning --value 120 \
  --matching-content-path "**/*.js"
cs rules-config list-thresholds --language Python --format json
cs rules-config list-thresholds --language Java --format json
cs rules-config list-thresholds --language "C#" --format json
```

Semantics:

- Default file: with no `--config-path`, the command uses
  `.codescene/code-health-rules.json` from the current git repository.
- With a single `rule_set` in the file, `set-rule` and `set-threshold` update
  it directly. With multiple `rule_set` entries, pass `--matching-content-path`
  to select which rule set to edit; omitting it makes the command fail and
  print the available selectors.
- `--enabled true` stores weight `1.0`; `--enabled false` stores weight `0.0`.
- If no config file exists when running `set-rule` or `set-threshold`, a
  minimal file is created automatically at the default path first.
- Unknown rule or threshold names fail with suggestions.
- If an update creates invalid config, the original file is restored.

______________________________________________________________________

## `cs docs`

CodeScene CLI documentation topics: `cs docs <topic>`.

| Topic                                 | Covers                              |
| ------------------------------------- | ----------------------------------- |
| `git-hooks`                           | Using delta in a git hook           |
| `interactive`                         | Delta interactive mode              |
| `interactive-pre-commit-hook-example` | Example interactive pre-commit hook |
| `pre-commit-hook-example`             | Example pre-commit hook             |
| `vim`                                 | `check` integration for (neo)vim    |
| `license`                             | Setting up a license                |
| `file-name`                           | File-name and language support      |
| `code-health-rules`                   | Customizing code health rules       |
| `code-health-rules-template`          | Outputs a rules template            |

______________________________________________________________________

## `cs version`

Displays the version, including the build date and SHA of the installed tool.

______________________________________________________________________

## Environment Variables

| Variable                   | Purpose                                    |
| -------------------------- | ------------------------------------------ |
| `CS_ACCESS_TOKEN`          | Personal Access Token for licensing        |
| `CS_ACCOUNT_ID`            | Cloud account selector for `cs auth login` |
| `CS_ONPREM_URL`            | Base URL for CodeScene Enterprise          |
| `CS_DISABLE_VERSION_CHECK` | Disable the automatic version update check |
| `CS_CERTS`                 | Extra trusted certs (DER/PEM/PKCS12 paths) |
| `CS_CERTS_PASSWORD`        | Password for PKCS12 files, if any          |
