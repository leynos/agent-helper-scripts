# Developers' Guide

This guide documents how the helper bootstrap is structured and what
maintainers must preserve when changing it. For user-facing bootstrap
configuration, see [docs/users-guide.md](users-guide.md).

## Bootstrap authority boundary

The Rust bootstrap is split by authority boundary:

1. The system phase configures APT repositories, APT packages,
   certificates, and optional global linker state.
2. The home phase clones `agent-helper-scripts` into a managed local checkout
   and executes the remaining helper scripts from that checkout.

This keeps non-cacheable system mutations separate from warm-cache-friendly
`$HOME` mutations while preserving branchable, inspectable helper logic.

The phase dispatcher is `rust-entrypoint`. It reads `RUST_ENTRYPOINT_PHASE` and
runs one of these modes:

- `system`
  - Runs `rust-entrypoint-system`.
  - Must not depend on durable warm `$HOME` state.
  - May mutate `/etc`, `/usr`, `/var/lib/apt`, APT repositories, packages,
    certificates, and linker state.
- `home`
  - Runs `rust-entrypoint-home`.
  - Must keep durable side effects under `$HOME`.
  - Must not run package-manager commands, use privilege escalation, or mutate
    machine-level package state.
- `both`
  - Runs `system` and then `home`.
  - Preserves the old one-shot bootstrap behaviour.

## Mandatory prerequisites

- `git` is required for the cloning-based helper bootstrap model.
- The system phase installs `git` automatically when it is missing, using
  `sudo` on non-root machines.
- If `HELPER_TOOLS_REPO_DIR` already exists and is not a Git checkout, the
  bootstrap treats that as an error and exits rather than deleting the path.

## Managed helper checkout

The home phase owns the durable helper checkout. It uses the shared variables
from `bootstrap-common`:

- `HELPER_TOOLS_REPO_URL`
  - Default: `https://github.com/leynos/agent-helper-scripts.git`
  - Controls the Git remote used by the managed helper checkout.
- `HELPER_TOOLS_REPO_BRANCH`
  - Default: `main`
  - Controls which branch `rust-entrypoint-home`, `install-hooks`, and
    `install-skills` fetch and reset to.
- `HELPER_TOOLS_REPO_NAME`
  - Default: derived from `HELPER_TOOLS_REPO_URL`
  - Used to derive the default clone path when no explicit directory override
    is provided.
- `HELPER_TOOLS_REPO_DIR`
  - Default: `${HOME}/git/${HELPER_TOOLS_REPO_NAME}`
  - Controls the filesystem path of the managed helper checkout.
  - `install-hooks` and `install-skills` respect this value, so the helper
    chain reuses a single checkout.

The system phase deliberately does not mutate `HELPER_TOOLS_REPO_DIR`. It
creates a temporary sparse checkout, uses it to run repository-owned system
helpers, and removes it on exit. This prevents a fresh system-layer bootstrap
from modifying a warm `$HOME` cache.

## Bootstrap flags

The supported user-facing flags are documented in
[docs/users-guide.md](users-guide.md). Maintainers should preserve these
behavioural contracts:

- `RUST_ENTRYPOINT_PHASE`
  - Defaults to `both`.
  - Controls only the wrapper dispatch, not the selected helper list.
- `WITH_ADD_REPOSITORIES`
  - Defaults to `1`.
  - Controls whether `rust-entrypoint-system` runs `add-repositories`.
- `WITH_AI_TOOLING`
  - Defaults to `0`.
  - Adds `get-ai-tooling` to the selected helper list.
- `WITH_LETA_WORKSPACE_ADD`
  - Defaults to `1`.
  - Controls whether `get-github-tooling` runs `leta workspace add .`.
  - Should be disabled for generic warm-home seed images.
- `UBUNTU_APT_MIRROR`
  - Defaults to `http://mirror.math.princeton.edu/pub/ubuntu/`.
  - Controls the Ubuntu mirror written by the system phase.
- `WITH_TRACE`
  - Defaults to `0`.
  - Enables Bash xtrace in deployment entrypoints and helper scripts.
  - Keep tracing opt-in so normal bootstrap logs do not leak environment
    values.

## Helper package metadata

`install-required-apt-packages` reads package declarations from helper script
comments:

```bash
# requires-apt-packages: gh ripgrep fd-find
```

Metadata rules:

- Package names are whitespace-separated after the colon.
- Multiple metadata lines are allowed.
- Comma-separated package lists are not supported.
- Duplicate package names are deduplicated before installation.

`rust-entrypoint-system` runs this helper after `add-repositories`, so
repository-provided packages such as `gh` are available from configured APT
sources before the home phase starts.

Optional system packages such as `kopia`, `glow`, and best-effort Linux tracing
packages are also installed by `rust-entrypoint-system`. Root execution no
longer installs `sudo` as a convenience package; system-phase helpers detect
whether `sudo` is required at their call sites.

## Configuration patterns

### Test a helper branch

```bash
export HELPER_TOOLS_REPO_BRANCH=feature-branch
raw_url="https://raw.githubusercontent.com/leynos/agent-helper-scripts"
curl -fsSL "$raw_url/refs/heads/feature-branch/rust-entrypoint" \
  | bash -euo pipefail
```

### Reuse a non-default checkout path

```bash
export HELPER_TOOLS_REPO_DIR="$HOME/git/agent-helper-scripts-sandbox"
export HELPER_TOOLS_REPO_BRANCH=feature-branch
```

### Enable optional AI tooling

```bash
export WITH_AI_TOOLING=1
```

### Run phases explicitly

```bash
RUST_ENTRYPOINT_PHASE=system bash rust-entrypoint
RUST_ENTRYPOINT_PHASE=home bash rust-entrypoint
```

## Architectural rationale

The cloning-based approach replaces repeated repository-owned `curl | bash`
invocations with a managed checkout. That change was made so that:

- helper scripts execute from a known local tree after bootstrap starts,
- branch-specific helper changes are easy to test with one environment
  variable,
- repository-owned binaries and wrapper scripts can be installed from the same
  checkout,
- helper sub-scripts share one checkout path instead of drifting into multiple
  independent clones.

The phase split adds a second boundary: system helpers use a temporary
checkout, while home helpers use the durable managed checkout. Keep that
distinction visible when adding new bootstrap behaviour.

## Script responsibilities

### `rust-entrypoint`

- Dispatches to `rust-entrypoint-system`, `rust-entrypoint-home`, or both based
  on `RUST_ENTRYPOINT_PHASE`.

### `bootstrap-common`

- `clone_or_update_helper_tools_repo`
  - Ensures the target helper checkout exists.
  - Defaults to `HELPER_TOOLS_REPO_DIR`.
  - Fetches and resets to `HELPER_TOOLS_REPO_BRANCH` for existing clones.
  - Performs sparse checkout for repository-owned helper files and the
    `skills` tree.
- `install_helper_script`
  - Installs repository-owned helper executables from the managed checkout into
    `${HOME}/.local/bin`.
- `build_selected_tools`
  - Builds the home helper list.
  - Adds `get-ai-tooling` when `WITH_AI_TOOLING=1`.
- `package_scripts_for_tools`
  - Selects `get-*` and `install-*` scripts for APT metadata scanning.
- `needs`
  - Returns true when the named command is absent from `PATH`.
  - Used as a lightweight guard: `if needs <cmd>; then ...; fi`.

### `rust-entrypoint-system`

- Configures Ubuntu APT sources using `UBUNTU_APT_MIRROR`.
- Installs hard bootstrap prerequisites.
- Clones a temporary sparse helper checkout without mutating
  `HELPER_TOOLS_REPO_DIR`.
- Runs `add-repositories` when enabled.
- Installs APT packages declared by selected helper script metadata.
- Installs optional system packages.
- Runs certificate updates.
- Applies `WITH_MOLD_LD_OVERRIDE` when requested.

### `rust-entrypoint-home`

- Updates shell profile PATH blocks and the current process PATH.
- Clones or updates `HELPER_TOOLS_REPO_DIR`.
- Installs user-level bootstrap tools.
- Runs the selected home helpers.
- Performs Kopia repository connect, restore, and snapshot work when
  `KOPIA_BUCKET` is set.
- Must not run package-manager commands, privilege escalation, or mutate
  machine-level package state.

### `install-hooks`

- Reuses the managed helper checkout path when `HELPER_TOOLS_REPO_DIR` is
  exported.
- Fetches the requested helper branch before copying hook files.
- Copies repository hook files into `~/.claude/hooks`; it no longer registers
  any hook in Claude Code settings. The post-turn quality stop hook moved to
  its own project:
  <https://github.com/leynos/post-turn-quality-stop-hook>.

### `install-skills`

- Reuses the managed helper checkout path when `HELPER_TOOLS_REPO_DIR` is
  exported.
- Reapplies sparse checkout for `skills` when a managed clone already exists,
  so older sparse checkouts are repaired before copying skills.
- Delivers the `vidai-mock` skill from the managed helper checkout. The
  installer no longer clones the standalone `leynos/vidai-mock-skill`
  repository: it was copied after the helper checkout's own skills, so the
  older copy would have overwritten the shipped skill on every run.
- Delivers the `nextest` skill from the managed helper checkout for the same
  reason. The `leynos/nextest-skill` clone was removed because its
  `copy_skills` call also ran after the helper checkout's own skills, so the
  external copy won on every run.

## `clone_or_update_repo`

```text
clone_or_update_repo <repo_url> <repo_dir> [sparse_set] [repo_branch]
```

- `repo_url`: Git remote to clone when `repo_dir` does not exist.
- `repo_dir`: Absolute path of the local checkout; trailing slashes are
  stripped.
- `sparse_set`: optional space-separated list of paths to enable with
  `git sparse-checkout set`.
- `repo_branch`: optional branch name to fetch and reset to; omit to use
  `origin/HEAD`.

Control-flow summary:

- Existing checkout with `repo_branch`:
  - Run `fetch --depth 1 origin <branch>`.
  - Reset to `FETCH_HEAD`.
- Existing checkout without `repo_branch`:
  - Run `fetch origin`.
  - Reset to `origin/HEAD`.
- Missing checkout with `repo_branch` and `sparse_set`:
  - Run `git clone --branch <branch> --single-branch --depth 1
    --filter=blob:none --sparse`.
  - Apply sparse-checkout selection.
- Missing checkout with `repo_branch` only:
  - Run `git clone --branch <branch> --single-branch --depth 1`.
- Missing checkout with no `repo_branch` and with `sparse_set`:
  - Run `git clone --depth 1 --filter=blob:none --sparse`.
  - Apply sparse-checkout selection.
- Missing checkout with no `repo_branch` and no `sparse_set`:
  - Run `git clone --depth 1`.

Example:

```bash
clone_or_update_repo \
  "${REPO_URL}" \
  "${REPO_DIR}" \
  "skills" \
  "${HELPER_TOOLS_REPO_BRANCH}"
```

## Makefile targets

The Makefile provides the standard validation entrypoints used locally and in
CI:

### Gate recipes

Each shared gate is one command that lists the files it examines, so no recipe
pipes a producer into a checker. A pipeline reports the last command's status,
and without `pipefail` a producer that fails or matches nothing leaves the
checker unrun while the recipe still exits zero, which reads as a clean pass
over an unread tree. [ADR 006](adr/006-fail-closed-gate-recipes.md) records
the defect and the decision; `set -o pipefail` remains only as an interim
guard for a repository that has not regenerated its recipes.

The recipes call `scripts/gate_runner_cli.py`, which exposes three commands.
`spelling` generates the shared configuration, validates it against the merged
policy, and scans every Git-tracked file. `markdownlint` and `nixie` walk the
tree for `*.md`, pruning build, cache and vendored directories. Each command
raises when discovery produces no file, names a tool it cannot resolve, and
exits with the tool's own status. `GATE_RUNNER_*` environment variables supply
the values the options carry, so a consumer can set `GATE_RUNNER_LINTER`
instead of restating the flag.

The commands themselves live in `scripts/gate_runner.py`, which imports only
the standard library. The Cyclopts front end is a separate module so tests can
drive a gate with a command double standing in for its tool.
`tests/test_gate_discovery.py` and `tests/test_gate_runner.py` pin the
contract: an empty or failed producer fails the gate before its tool is
invoked, the tool receives the whole list in one invocation, and a tool that
reports findings fails the gate with its own status.

### Markdown lint configuration

`.markdownlint-cli2.jsonc` is reconciled against the shared
`agent-template-python` configuration. Prose is limited to 80 columns and code
blocks to 120; tables and headings stay exempt from the line-length rule
because padding or reflowing them costs more than it gains. `MD040` and
`MD041` are enabled, as in the template.

Three rules remain disabled against the template, each with its rationale
recorded beside the entry:

- `MD024` with `siblings_only` — a heading repeats legitimately under different
  parents, as in the code-review skill's paired "Problem" and "Improvement"
  examples.
- `MD033` — agent-facing material under `skills/` uses `<angle-bracketed>`
  placeholders that must reach the reader verbatim rather than escaped.
- `MD036` — skill reference documents lead into example blocks with a bold
  label instead of promoting that label to a heading, which keeps their tables
  of contents navigable.

`markdownlint-cli2` lints nothing when it receives neither a glob argument nor
a `globs` key, yet still reports a clean pass, so `make markdownlint` names
every file it found rather than relying on a default. The gate runner walks
the tree itself and refuses an empty result, which is the property a glob
cannot give: a pattern that matches no file is indistinguishable from a clean
tree.

The `markdownlint` wrapper shipped for consumers appends `**/*.md` when the
caller names no path. It treats two arguments as explicit targets rather than
paths, so no glob is appended for either: a standalone `-`, which tells
`markdownlint-cli2` to read the file list from standard input, and the operand
of `--config` or `--configPointer`, which names a configuration file rather
than a document to lint. The repository's own gate does not go through the
wrapper: it calls `markdownlint-cli2` directly, because the shared baseline
this repository is moving to provisions the binary globally, which is the case
the wrapper exists to cover. The wrapper's widening still cannot tell an empty
match from a clean tree, so a consumer that needs that guarantee calls the
gate runner instead.

CI lints Markdown through the pinned `DavidAnson/markdownlint-cli2-action`
rather than installing the linter by hand. The action's release carries
`markdownlint-cli2` together with its whole dependency graph, so the pinned tag
is what fixes every version it runs; nothing is resolved from npm at run time.
That pin is deliberately Dependabot's job, since `.github/dependabot.yml`
already tracks the `github-actions` ecosystem. CI therefore runs the same gate
sequence with that one gate delegated — `make ci CI_SKIP_MARKDOWNLINT=1` —
while a local `make ci` still runs it.

### Shared en-GB-oxendict spelling data

The architecture and trade-offs are recorded in
[ADR 003](adr/003-shared-oxford-spelling-base.md).

The tracked `data/typos-oxendict-base.toml` file is the estate-wide source of
generic Oxford `-ize` mappings, accepted words and safe exclusions. Add a word
there only when it is valid across repositories. Product names, quoted upstream
terms and fixture-specific vocabulary belong in the consumer repository's
tracked `typos.local.toml` overlay.

Local pattern additions merge with the shared ignore list. A local
`[patterns] remove` list then withdraws exact shared entries, allowing a
consumer to narrow an overly broad authority pattern without forking the
generator. A pattern cannot appear in both the local `ignore` and `remove`
lists; removals that no longer exist upstream remain valid no-ops.

The executable `scripts/typos_rollout_cli.py` provides three commands.
`harvest` emits JSON Lines evidence for both plain-British `-ise` and Oxford
`-ize` forms found in Git-tracked UTF-8 text. `generate` conditionally
refreshes the untracked `.typos-oxendict-base.toml` cache, merges any local
overlay, validates the result as TOML, and atomically writes deterministic
`typos.toml` output. `check` rejects curated exact phrase corrections that
Typos cannot enforce because punctuation separates its word tokens. It masks
the merged ignore patterns and skips the merged file exclusions before
reporting a path, line, column and canonical replacement. The companion
`.typos-oxendict-base.json` stores HTTP validators. When the network is
unavailable, a valid existing cache remains usable with `--offline`; generation
fails rather than silently inventing an empty base when no cache exists.

Freshness metadata is source-scoped. Local modification times, HTTP validators,
stale-cache fallback, and `304 Not Modified` reuse apply only when the saved
source identity exactly matches the requested authority. A missing or different
identity forces refresh or propagates the authority failure. Standard-library
logging records these decisions with bounded `operation`, `source_kind`,
`error_class` and `decision` fields. Never add an authority URL, repository
path, response body or exception message to these records.

Refresh callers bind the metadata path, offline policy and optional test opener
in an immutable `RefreshOptions` value. The helper owns the private local and
remote request records that coordinate freshness and persistence; consumers
should compose the public options value rather than reuse those infrastructure
details.

The `typos_rollout.py` facade preserves the public CLI and import surface.
Sibling modules own one policy boundary each:

- `typos_rollout_policy.py` validates schemas, local exceptions, and bounded
  regular expressions.
- `typos_rollout_cache.py` owns cache records, validator metadata, and atomic
  persistence.
- `typos_rollout_http.py` coordinates source-scoped local and HTTPS refreshes.
- `typos_rollout_render.py` expands Oxford stems and renders deterministic TOML.
- `typos_rollout_check.py` enforces curated exact phrase corrections.
- `typos_rollout_harvest.py` gathers contextual Oxford-form evidence.

Keep each source module below 400 lines and route new behaviour to its owning
boundary rather than expanding the facade. Regular expression validation
rejects malformed patterns, backreferences, and compounded repetition. The
scanner recognizes all Python brace forms, including `{n}`, `{n,}`, `{n,m}` and
`{,n}`. It permits repetitions separated by unquantified atoms. Example
regressions pin known hazards, while Hypothesis properties generate every brace
shape and varied safe separators.

Phrase checking and harvesting read only Git-tracked files. A
`UnicodeDecodeError` identifies non-UTF-8 content and is skipped with a bounded
informational record. Every `OSError`, including permission and disappearance
failures, is logged without a path and propagated so the gate fails closed.
Caplog tests assert structured record fields rather than rendered log text.

Run `make spelling` after dictionary or generator changes. The target generates
the committed config from the local authoritative base, checks exact phrase
policy, and runs the version of `typos` pinned by `TYPOS_VERSION`. The full
`make ci` sequence includes this gate. Tests assert byte-for-byte config drift,
TOML validity, cache freshness, offline recovery, exact phrase boundaries and
real-binary Oxford behaviour. Property tests exercise the regular expression
repetition grammar, and logging tests pin bounded diagnostics for source-scope
decisions and tracked-file read failures.

The initial shared stem set was curated on 10 July 2026 from both correct
Oxford forms and incorrect plain-British forms across the 96 non-empty,
accessible repositories in the estate inventory. Generated spelling configs,
local overlays, dependency locks and build output were excluded before
curation. A suffix match alone is not evidence: `advertise`, `exercise`,
`improvise`, `promise`, `resize` and Rust's `usize`, for example, must not be
treated as Oxford `-ize` families. Future harvests must retain per-repository
JSON Lines evidence until curation and record generic additions here.

The later Dakar audit on 15 July 2026 added the `polymer` stem from four correct
`polymerization` occurrences when the previously empty repository became the
97th candidate.

The netsuke request of 11 September 2026 added nine `s`-to-`z` drift
corrections for `otherwise`, `exercise` and `raise`. Typos reports the exercise
family with competing candidates and misses the raise family entirely, so each
recorded drift form now carries one canonical replacement for every consumer.

- `make ci`
  - Runs the full CI gate in sequence: `check-fmt`, `markdownlint`, `lint`,
    `typecheck`, `test`, and `spelling`.
  - Use this before pushing; it mirrors what the GitHub Actions workflow
    executes, except that the workflow runs the Markdown gate through the
    `markdownlint-cli2` action and so passes `CI_SKIP_MARKDOWNLINT=1`.
- `make markdownlint`
  - Lints every Markdown file the gate runner discovers with
    `markdownlint-cli2`, naming each file explicitly so the gate cannot pass
    without having read one, and failing when the discovery finds none. The
    repository's `markdownlint` wrapper is still shipped for consumers; this
    target does not run it.
  - Reads `.markdownlint-cli2.jsonc`. The wrapper ships its own configuration
    for a consumer repository that has none, so the same script works unchanged
    where `get-markdown-tooling` installs it as `markdownlint`.
- `make nixie`
  - Validates every Mermaid diagram with `nixie` over the files the gate runner
    discovers.
  - Not part of `make ci`. `nixie` renders through an external Mermaid CLI
    (`merman-cli`, or `mmdc` with Chromium), which the CI runner does not
    provide; run it locally before pushing documentation that changes a
    diagram.
- `make lint`
  - Runs `syntax-check`, `shell-syntax-check`, `check-home-phase-boundary`,
    and `skill-manifest-check`.
- `make skill-manifest-check`
  - Aggregate target; runs both `skill-frontmatter-lint` and
    `skill-manifest-validate` below; wired into `make lint`.
  - All three manifest targets read `SKILL_DIRS`, which defaults to every
    `skills/*/SKILL.md` directory and can be overridden (for example
    `make skill-manifest-check SKILL_DIRS=path/to/skill/`) to check a single
    skill or a test fixture; the test suite relies on this.
- `make skill-frontmatter-lint`
  - Extracts the YAML frontmatter block of each `SKILL.md` with `awk` and
    pipes it to `yamllint` using the inline `SKILL_YAMLLINT_CONFIG` (default
    rules with `line-length` disabled).
- `make skill-manifest-validate`
  - Runs `skills-ref validate` over each skill directory to enforce the
    Agent Skills manifest schema.
- `make shell-syntax-check`
  - Runs `bash -n` over every shell script listed in `SHELL_SCRIPTS` to catch
    syntax errors without executing any code.
- `make check-home-phase-boundary`
  - Rejects APT, `sudo`, and linker mutation patterns in home-phase scripts.
  - Scans non-comment lines only.
- `make test-entrypoints`
  - Runs the entrypoint-only pytest subset (`ENTRYPOINT_TESTS`) via
    `uv run python -m pytest`.
  - Use this when iterating on `rust-entrypoint`, `rust-entrypoint-system`, or
    `rust-entrypoint-home`.

## Subagent manifest

`agents/subagents.yml` is the provider-neutral source of truth for the managed
subagents (`wyvern`, `scribe`, `alchemist`, `scrutineer`, `journeyman`,
`artisan`, and `natural-philosopher`). For the user-facing description of what
each subagent does and how downstream provisioning renders the manifest, see
the `## Sub-agent definitions` section in
[docs/users-guide.md](users-guide.md). This section covers the test-loader
concerns and, for the `scrutineer` subagent, its operating contract.

The manifest expresses MCP access according to each provider's inheritance
model. Claude Code provider blocks use named `mcpServers` allow-lists: every
managed subagent gets CodeGraph, and only the journeyman and
natural-philosopher get Firecrawl and DeepWiki as well. Codex provider blocks
omit `mcp_servers`, so the custom agent inherits the parent's complete,
credentialed registry rather than flattening a partial replacement into its
agent file. Goose provider blocks omit
`extensions`, which makes the recipe inherit the parent session's extensions.
The resulting contract keeps Claude access explicit while allowing Codex and
goose to inherit any other parent MCPs that are already configured.

### Test helper: `tests/subagent_manifest.py`

`tests/subagent_manifest.py` loads the manifest with `yaml.safe_load` and
performs structural validation, exposing three public functions:

- `load_subagent_entries()` — returns every `agent_tools_subagents` entry as a
  validated mapping.
- `load_subagent_entry(name)` — returns the single entry whose `name` field
  matches the supplied value; raises `LookupError` if no such entry exists.
- `load_provider(name, provider)` — returns the provider sub-mapping stored
  under `providers[provider]` for the named entry; raises `TypeError` when the
  entry carries no `providers` mapping or the provider value is not a mapping,
  and `LookupError` when the named provider block is absent.

The module deliberately surfaces typed errors at every structural boundary:
`OSError` (manifest unreadable), `yaml.YAMLError` (invalid YAML), `TypeError`
(unexpected shape), and `LookupError` (missing entry or provider). This ensures
a malformed manifest fails loudly rather than silently producing empty or
incorrect test data.

### Test suites

Three test suites consume the helper:

- `tests/test_subagent_definitions.py` — happy-path deployment-contract
  regressions. It asserts specific model choices, sandbox modes, tool grants,
  and load-bearing instruction prose for each subagent. Any edit that weakens
  one of those values fails a test rather than silently degrading a provisioned
  agent.
- `tests/test_subagent_manifest.py` — error-path coverage of the loader. It
  exercises the typed-error contract directly, confirming that malformed or
  incomplete manifests produce the expected exception types.
- `tests/test_natural_philosopher.py` — pins the `natural-philosopher` entry's
  deployment and step-design contracts specifically: its uniqueness, its
  per-provider configuration, and the load-bearing phrases its instructions
  must retain. These are manifest regression tests, not live-model
  behavioural evaluations.

### PyYAML dependency

PyYAML is a development-only dependency, declared as `pyyaml>=6.0.3` in the
`[dependency-groups] dev` array of `pyproject.toml`. It is not a runtime
dependency of any bootstrap script; only the manifest test helper imports it.

### Scrutineer operating contract

`scrutineer`'s `instructions` body in `agents/subagents.yml` is the
authoritative source for this contract; it is pinned by
`tests/test_subagent_definitions.py`. An assignment combines up to three
independent scopes:

- Deterministic local commit gates: `make check-fmt`, `lint`, `typecheck`,
  `test`, `markdownlint`, `nixie`, plus `test-podman` when the change
  surface touches an Ansible role, module, playbook, or Molecule scenario.
- An optional `coderabbit review --agent` pass, gated on every applicable
  deterministic gate above passing first.
- GitHub Actions monitoring.

A monitoring-only assignment starts neither of the other two scopes and
records them as `not-requested` rather than passed or silently skipped.

Actions monitoring requires an authenticated `gh` CLI and `jq`.
`gh run watch` does not support fine-grained PAT authentication, and the
agent must never broaden permissions or change authentication to make
watching work. A missing `gh` or `jq` is classified
`infrastructure-error` rather than reported as a successful observation.

Correlation is explicit: repository via `--repo OWNER/REPO`, expected
commit SHA, run ID and attempt. Candidate resolution and verification
are published, executable procedures rather than prose guidance.
`gh pr checks` links are parsed into `candidate-runs.txt`, or
`gh run list --commit` resolves commit-scoped work, and every candidate
is confirmed with `gh run view` before it may enter the watch or
evidence steps. Verification records one of three
`candidate-identity.txt` states — `verified`, `pr-head-synthetic-merge`,
or `sha-mismatch` — because a `pull_request` run reports the PR head
as its `headSha` while GitHub actually builds a synthetic merge of
that head into the base. `gh run watch` does not pin an attempt, so the
latest attempt and candidate identity are rechecked before hand-off;
superseded evidence is retained and reported as stale rather than
silently transferred to the new attempt.

Observation is bounded and read-only. `gh run watch` blocks until the
run completes, and neither `--exit-status` nor `--interval` bounds it,
so the watcher is wrapped in `timeout`, using a `remaining_seconds`
value derived from the observation deadline. A `timeout` exit status
of `124` is recorded as a distinct `deadline-reached` watcher outcome,
not a workflow failure. An observation deadline stops only the local
watcher; hosted runs are never cancelled. The assignment never
reruns, dispatches, approves, merges, or edits a workflow.

Only `status=completed` with `conclusion=success` counts as success. Every
other conclusion, and any pending, missing, or inaccessible requested
work, is preserved and never collapsed into an all-success claim. CLI,
credential, permission, and API problems are classified
`infrastructure-error`, distinct from a workflow failure; a nonzero
`gh run watch` exit code is not by itself a verdict.

Evidence is written to a private `mktemp` directory under `/tmp` created
with `umask 077`, with a `run-<id>-attempt-<n>` subdirectory per run and
attempt. Resolution and verification add their own artefacts to that
bundle: `pr.json` and `candidate-runs.txt` for PR-scoped resolution,
with `non-actions-checks.txt` recording checks that are not Actions
runs; `run-list.json` and `candidate-runs.txt` for commit-scoped
resolution, with `candidates.missing` written only when no runs were
found for the commit; and `candidate.json` plus
`candidate-identity.txt` for verification. The bundle also holds
`run.json` and `watch.log` for the watch itself, `recheck.json` from
the attempt recheck before hand-off, with `attempt.superseded`
written only when the latest attempt differs from the one the
evidence covers. `failed.log` and `failed-log.stderr` are conditional:
they are captured only for a run that has reached `status=completed`
with a non-success conclusion. The procedure enforces this condition
itself, reading `status` and `conclusion` from the already-captured
`run.json` with `jq` rather than making a second API call. A
successful, still-pending, missing, or inaccessible run legitimately
has no failure-log artefacts; the procedure instead writes a
`failed-log.omitted` note recording the observed status and
conclusion, so the omission is self-describing. The root `summary.md`
manifest records the reason for any expected artefact's absence, so
an omission is never ambiguous between "not applicable" and
"retrieval failed". Failed-step log capture is never gated on watcher
success with `&&`, and retrieval exit codes are recorded separately
from the observed Actions conclusion. Logs stay private, and secrets
are redacted from any excerpts.

`agents/subagents.yml` is the single authoritative copy of these
procedures. `tests/test_scrutineer_actions_discovery.py` and
`tests/test_scrutineer_actions_procedures.py` extract the `bash`
snippets from the manifest's `instructions` body and execute them
against a `gh` double that validates repository, run ID, attempt,
commit SHA, and required flags, so the tests cannot drift from the
published contract.

### Skill manifest tooling dependencies

`skills-ref` and `yamllint` are also development-only dependencies in the
`[dependency-groups] dev` array:

- `skills-ref` is pinned by git URL to a specific commit, subdirectory
  `skills-ref`; it provides the `skills-ref validate` command that enforces
  the Agent Skills manifest schema. Invoke it via `uv run --group dev
  skills-ref`.
- `yamllint` is invoked via `uv run --group dev yamllint`. It is declared
  explicitly because it was previously called as a bare binary and passed in
  CI only because the GitHub ubuntu runner image happens to ship it, which
  made the gate depend on the runner image rather than the declared
  environment.

## Weave Git merge-driver boundary

The `weave-git-merge` skill documents Weave, an entity-aware Git merge driver
that Git invokes per selected path during merges, rebases, and cherry-picks.
The user-facing summary lives in the "Entity-aware Git merges" section of
[docs/users-guide.md](users-guide.md); this section covers what maintainers
must preserve when changing the skill or its tests.

Weave is an optional local developer tool, not a repository-wide dependency
this project adopts; this branch only ships a skill that documents it, so
adopting Weave repository-wide would need its own ADR.

### Read-only primary checkout

Unattended merge and rebase work belongs in a linked worktree. The primary
checkout is a coordination anchor for that unattended work, not a scratch,
formatting, or conflict-repair surface: do not rebase, resolve conflicts, or
run ad-hoc fixes directly in it.

### Candidate-bound evidence

Before any history rewrite, record `OLD_HEAD`, the exact fetched `TARGET`
commit, and `MERGE_BASE`. A completed rebase produces a new candidate, so any
gate or review evidence bound to the old head is stale for acceptance once the
replay finishes. Preserve the old evidence as historical record, then rerun
the candidate-bound checks the repository requires against the new `HEAD`.

### Ambient Weave bypass rules

Unattended multi-commit or long-lived-branch rebases default to Git's
built-in merge machinery with `merge.conflictStyle=zdiff3` whenever Weave is
selected only by ambient global or clone-local configuration; ambient
selection is not repository consent for that scale of unattended replay. A
tracked `.gitattributes` rule is explicit repository opt-in, and it is
honoured unless an authorized recovery overrides it. Setting
`core.attributesFile=/dev/null` cannot override tracked or clone-local rules —
that limitation is why the scope matrix in the "Bypass recovery" subsection
below exists.

### Setup scopes

`weave setup` writes three mutually exclusive scopes:

- default — tracked `.gitattributes`, shared with the whole team;
- `--local` — untracked `.git/info/attributes`, this clone only;
- `--global` — global Git config plus a global attributes file. When
  `core.attributesFile` is unset, Git falls back to
  `$XDG_CONFIG_HOME/git/attributes` or `$HOME/.config/git/attributes`.

### Driver contract

Setup records `weave-driver %O %A %B %L %P` and Git runs it once per selected
path. Exit `0` means Weave wrote a clean result to `%A`; exit `1` means Weave
wrote a partially merged result with conflict markers to `%A` and Git leaves
the path unmerged; exit `2` is an invocation, input, or output failure and is
not a semantic conflict.

### Validation is mandatory, not optional

A clean exit is not proof of a correct result: Weave can exit `0` having
produced structurally broken output (see
[behaviour.md](../skills/weave-git-merge/references/behaviour.md)). A cheap
structural gate — a parser or compiler for the affected language — must run
before `git add` or `git rebase --continue`. Multi-commit rebases need a
`git rebase --exec` guard as well, because an early silently corrupted replay
can become an input to a later one before any end-of-rebase test runs.

### Recovery completeness

Destructive Git recovery — a `reset`, `clean`, or abort-and-retry sequence —
requires complete evidence for staged, unstaged, and intended untracked work
before it runs. Generate native recovery diffs with
`--no-ext-diff --no-textconv --binary` and keep an explicit untracked-file
manifest; a patch that applies does not by itself prove it captured untracked
files.

### Driver observability

Driver stderr must be preserved and read, including summary lines such as
`weave: N entities auto-resolved (... confidence)`. Set command-scoped
`WEAVE_EVENT=1` to obtain `weave-event:` JSON lines on stderr, and keep those
lines with the operation receipt. Capture must fail closed — a broken pipe or
missing redirect must be treated as lost evidence, not silently discarded.

### Semantic post-operation audit

Run this audit independently of the driver's exit code and every structural
gate, because a clean exit and a passing test suite are not sufficient
evidence on their own:

- every path changed by `TARGET` but untouched by the branch must be
  byte-identical to `TARGET` at the final `HEAD`;
- every deletion against `TARGET` in a branch-touched path must be explained
  by the branch's own intent or a named, reviewed resolution decision;
- newly repeated multi-line blocks must be inspected.

The known Rust cfg-gated sibling test-body replacement (see
[behaviour.md](../skills/weave-git-merge/references/behaviour.md)) parsed,
compiled, and passed the test suite. That incident is exactly why this audit
cannot be waived on a green suite.

### Version recording and `weave check`

Record `weave --version` and `weave-driver --version`; an unexpected mismatch
between them is an andon trigger. Run `weave check` — after feature-probing it
with `weave check --help` — or the MCP `weave_check` tool when supported,
while the independent semantic audit above remains authoritative.

### Bypass recovery

`git -c core.attributesFile=/dev/null` bypasses only the global-scope rule.
Tracked and clone-local rules still apply and need a later, path-specific
`path/to/file.ext !merge` line added to `.git/info/attributes` instead. See
the scope matrix in [SKILL.md](../skills/weave-git-merge/SKILL.md) for the
full set of bypass and verification commands per scope.

### Andon triggers

See the skill's
["Andon triggers"](../skills/weave-git-merge/SKILL.md#andon-triggers) section
for the authoritative, current trigger list rather than duplicating it here.

### Why this matters here

Three test modules and one support module hold this boundary in place, and
all must stay in step with the skill:

- `tests/test_weave_git_merge_skill.py` asserts the documented wording, so a
  command or heading cannot be reworded out of the skill unnoticed.
- `tests/test_weave_git_merge_procedures.py` executes the procedures against
  real repositories, standing a cmd-mox double named `stub-merge-driver` in
  for the driver, wired in by the shim's absolute path under
  `EnvironmentManager.shim_dir` so resolution never consults `PATH`. It covers
  a driver exiting `0` over unparsable output, the three index stages of an
  unmerged path, the `git rebase --exec` guard stopping a multi-commit
  rebase, and every bypass in the scope matrix across rebase, merge, and
  cherry-pick. It also covers the hardened unattended workflow: the
  ambient-bypass default and `zdiff3` conflict style, tracked opt-in surviving
  that bypass, candidate and merge-base evidence recorded across a replay, the
  target-preservation semantic audit, capture of driver stderr and
  `WEAVE_EVENT` output, resetting to the recorded head after a completed
  operation, and recovery evidence spanning staged, unstaged, and untracked
  work. The
  double stands in for any driver with a given exit status, so the suite
  needs no Weave installation and asserts nothing about Weave's own merge
  quality. Its spy call counts are what prove Git invoked the driver before a
  bypass and stopped invoking it after. It also covers a two-commit chained
  replay in which a clean-exit corrupt first replay is captured verbatim as
  the second replay's `%A` input.
- `tests/weave_git_merge_model.py`: a pure-Python model of the skill's
  stateful rules, using the `Operation`, `Scope`, `Bypass`, and `DriverExit`
  enums, that never calls Git. Attribute-scope fallback (`active_sources`,
  `effective_merge_attribute`, `global_attributes_path`, and the
  `DOCUMENTED_BYPASS` map) encodes that `core.attributesFile=/dev/null`
  disables only the global source, a later path-specific `!merge` line
  outranks every source, and an absent `core.attributesFile` still means a
  default global path applies. Stage validity (`ConflictCase`,
  `existing_stages`, `parseable_stages`, `trusted_stages`,
  `resolution_may_continue`) encodes that a stage must exist and parse to be
  trusted and that stage 2 is untrusted during a rebase with unverified
  earlier replays. Multi-commit replay transitions (`ReplayOutcome`,
  `ReplayState`, `fold_replays`, `sequence_is_safe`, `safe_prefix_length`)
  encode that commit N's `ours` derives from commit N-1's result and a
  clean-exit structurally invalid result is never accepted as a safe later
  `ours`. The model is a transcription of the skill wording, so a rule
  change in the skill must be mirrored in the model.
- `tests/test_weave_git_merge_properties.py`: Hypothesis properties over the
  model, covering both operation types, all three scopes, valid and invalid
  index-stage combinations, and replay sequences of two or more transitions,
  including an ordering property in which moving the single invalid replay
  moves the safe-prefix boundary. It is the search-based complement to the
  fixed-string contract tests and the real-Git procedure tests.

When extending the procedures module, note two traps at this boundary. A
cmd-mox shim reads standard input, so Git must be run with `stdin=DEVNULL` or
the shim and Git deadlock. Git also hands the driver repository-relative
temporary paths, while handlers run in the pytest process, so `%A` must be
resolved against the repository before writing.

## Squash-restack replay boundary

The `rebase` skill restacks a child branch after its parent PR has
squash-merged. The user-facing summary lives in the
"Squash-restack boundaries" section of the [users' guide](users-guide.md) and
in `skills/rebase/SKILL.md`; this section covers what maintainers must
preserve when changing the planner or its tests.
See also [ADR 005](adr/005-squash-restack-replay-boundary.md) for the
decision record behind this boundary model.

### The boundary model

A squash merge collapses the parent PR's original commits into one landing
commit on the target. Restacking the child therefore depends on three
distinct identities, and conflating any two of them corrupts the replay:

- the original parent PR head — the last commit the child actually forked
  from, or later inherited via a rebase onto the parent;
- the parent's squash landing commit (`merge_commit_sha`) — a new commit on
  the target that proves the parent PR integrated, but never existed in the
  child's own history;
- the last inherited commit to exclude, `OLD_BASE` — the exclusive replay
  boundary. It is the parent head when that head is still an ancestor of the
  child, not the first commit the child authored.

None of the tempting shortcuts is sound as a boundary:

- a target merge-base is only a topology fact about the current graph. If the
  parent advanced or was rewritten after the child forked, the ordinary
  merge-base can silently return an earlier, wrong commit, or several
  candidates with no way to choose between them;
- the squash SHA never appears in the child's own history, so it cannot bound
  the child's own commit series; it is useful only as evidence that the
  parent's work landed on the target;
- the apparent first child commit depends on how many commits the parent
  contributed before the child branched, which is not recoverable from the
  child branch in isolation. Guessing it either drops genuine child commits
  or replays inherited parent work as if it were the child's own.

### `plan_restack.py`

`skills/rebase/scripts/plan_restack.py` carries PEP 723 inline script
metadata declaring `requires-python = ">=3.13"` and
`dependencies = ["cyclopts>=4,<5"]`, so it runs directly under `uv run`
without a separate project environment:

```bash
uv run "$SKILL_DIR/scripts/plan_restack.py" . \
  --branch "$BRANCH" --target-ref "$TARGET_REF" \
  --parent-repository "$PARENT_REPOSITORY" --parent-pr "$PARENT_PR"
```

The planner requires the `gh` CLI on `PATH` and network access to the
github.com REST API and Git fetch endpoints; it does not accept a bundled
GitHub client library as a substitute, and it fetches only from
`https://github.com/<parent-repository>.git`, never another host.

### Module layers

`plan_restack.py` is explicitly layered, with banner comments marking each
layer in the source. The layers do not mix:

- **Domain** — typed values and pure policy. The typed values are
  `CommitId` (a `typing.NewType` over `str`), `ParentPullRequest` (whose
  `__str__` renders the `owner/name#number` form used in plans and receipts,
  and whose `matches_receipt_identity()` compares a recorded `stackParent`
  value case-insensitively), `ParentEvidence`, `Evidence`, `ReceiptFacts`,
  `BoundaryFacts`, `Boundary`, `RangeFacts`, `Identities`, `ErrorContext`,
  and the frozen `ReplayPlan` dataclass (`status`, `operation`, `branch`,
  `parent`, `old_head`, `target`, `boundary`, `parent_evidence`, `commits`,
  `review`). `ReplayPlan` deliberately carries no Git command: rendering one
  is an adapter concern, so replay policy never depends on Git's
  command-line surface. The pure policy functions are `check_identities()`,
  `select_boundary()`, `check_receipt_ref()`, `check_range()`,
  `check_unmoved()`, `review_notes()`, and `plan_replay()`, which builds a
  `ReplayPlan` from accepted domain values. None of these take a `Path`, run
  a subprocess, parse GitHub CLI JSON, or use Cyclopts, so the whole policy
  is testable without a repository.
- **Adapters** — `Runner`, a `typing.Protocol` that runs one program in one
  repository and returns its standard output; `Subprocess`, the real process
  adapter; `GitGraph`, which turns Git queries into typed graph facts
  (`boundary_facts()`, `range_facts()`, `identities()`,
  `fetch_parent_head()`, and related helpers); `GitHubCli`, which runs and
  validates `gh api`, returning the reported head and landing commit IDs;
  and two rendering functions that sit outside the domain layer on purpose:
  `rebase_argv(plan)`, which renders the proposed Git replay argv from the
  module's `REBASE_PREFIX` constant (now referenced only from this adapter
  layer), returning `None` when the plan proposes no replay; and
  `render_document(plan)`, the serialization boundary that produces the
  JSON dict the CLI prints, attaching `rebase_argv(plan)` under the
  `rebase_argv` key.
- **Command layer** — `discover()`, the only operation that runs `gh`,
  fetches, or writes a ref.
- **Read path** — `build_plan()`, which consumes an `Evidence` snapshot and
  never invokes discovery, makes no network access, writes no ref, and mints
  no identifier. It composes the domain and adapter layers by calling
  `plan_replay()` to build a `ReplayPlan`, then `render_document()` to
  produce the returned JSON dict.

The CLI sits above all four: `main()` owns the operation identifier, calls
`discover()` first and `build_plan()` second, and wraps both in an
`operation_span()`.

### Query/command split

`discover()` is the only command-layer operation in the module: it is the
sole function that runs `gh`, performs the private evidence fetch, or
otherwise touches the network or a mutable ref. It fetches the parent PR's
actual head (never the synthetic `refs/pull/N/merge` ref) into a fresh
private `refs/agent-rebase/<uuid>/parent-head` ref and returns the result as
an immutable `Evidence` snapshot: `operation`, `parent` (a
`ParentPullRequest`), `old_head` and `target` (the frozen `CommitId` tips),
and `parent_evidence` (a `ParentEvidence` carrying the fetched head, the
validated landing commit, and the retained evidence ref). The raw `gh`
metadata dict is not carried on `Evidence`; that representation stays inside
`GitHubCli`.

`build_plan()` consumes that snapshot and performs only local Git graph
queries: ancestry checks, `rev-list`, and receipt lookups. It never runs
`gh`, never fetches, and never rebases, pushes, prunes, or moves a branch or
tracking ref. This split is a non-mutation contract, not merely a code
organization preference: `build_plan()` must remain safe to call, re-call, or
reason about without any side effect beyond reading the local repository, so
that replay policy stays reviewable apart from the adapters that gather
evidence.

`discover_and_plan()` is the explicit composition of the two: it calls
`discover()` and passes the resulting `Evidence` straight into `build_plan()`.
It exists so that nothing query-shaped performs hidden discovery — a caller
who already holds an `Evidence` snapshot calls `build_plan()` directly, and a
caller who needs both steps calls `discover_and_plan()` and cannot mistake the
result for a side-effect-free query. `main()` calls `discover()` and
`build_plan()` directly rather than `discover_and_plan()`, so it can wrap
both in one `operation_span()` and own the operation identifier passed to
`discover()`.

### Process adapter injection

Every process interaction — `git`, `gh`, and the evidence fetch — goes
through an injected `Runner`, a `typing.Protocol` that runs one program in
one repository and returns its standard output. `Subprocess` is the real
adapter: a frozen dataclass bound to a single repository path, with no shell
parsing and a timeout on every call set by the module constant
`PROCESS_TIMEOUT_SECONDS` (60 seconds).

A non-zero exit raises `PlanError(f"{program} exited {code}",
CATEGORY_PROCESS, detail=<stderr or stdout>)`; a timeout raises
`f"{program} timed out after {PROCESS_TIMEOUT_SECONDS}s"`; a start failure
raises `f"Cannot start {program}"`. All three carry the underlying exception
or captured output on `PlanError.detail`, never in the bounded `reason`; see
"Refusal conditions and exit contract" below for why that separation
matters.

`discover()` and `build_plan()` both take an optional `run: Runner | None`
parameter that defaults to `Subprocess(request.repository)`, so a caller can
substitute a test double without patching module globals. `discover()` also
takes injectable `new_operation_id` and `new_evidence_ref` callables, so
tests can assert against deterministic identifiers instead of random UUIDs.

### Clock injection

A `Clock` type alias (`Callable[[], float]`) is threaded as a keyword-only
`clock` parameter through `phase()`, `operation_span()`, `discover()`,
`build_plan()`, and `discover_and_plan()`, defaulting to `time.monotonic` at
every layer. `main()` is the composition root: it binds the real
`Subprocess`, the real clock, and calls `_new_operation_id()` there and
nowhere below, so every layer beneath stays substitutable. Tests inject a
fake clock to assert deterministic `elapsed_ms` values instead of timing
real process calls.

### Active-operation probe injection

`GitGraph.exists` is an injectable `Callable[[Path], bool]` filesystem
probe, defaulting to a module-level `_path_exists()` that calls
`Path.exists()`. `_refuse_active_operation()` calls it indirectly through
`GitGraph.path_exists(name, repository)`, which resolves the Git-directory
path via `git_path()` and then converts any `OSError` the probe raises into
`PlanError(f"Cannot determine whether {name} exists: {exc}",
CATEGORY_PROCESS)` rather than treating a probe failure as "marker absent" —
doing so would let discovery proceed over an in-flight Git operation.

### Preflight checks

`preflight()` orchestrates two narrower checks and returns the child branch
tip and target ref tip as frozen identities:

- `check_identities()` rejects a malformed parent repository, a
  non-positive parent PR number, or a branch name that is empty or
  option-shaped, and `preflight()` then runs `git check-ref-format` against
  the branch.
- `_refuse_active_operation()` rejects a shallow clone, an in-flight Git
  operation (`rebase-merge`, `rebase-apply`, `MERGE_HEAD`,
  `CHERRY_PICK_HEAD`, `REVERT_HEAD`, or `sequencer`), or a worktree carrying
  staged, unstaged, or untracked work.

### Boundary provenance

`select_boundary()` accepts exactly two forms of evidence for `OLD_BASE`,
recorded on the returned `Boundary`:

- `parent-pr-head` — the fetched parent head is itself an ancestor of the
  child branch, so it is directly usable as the boundary;
- `maintained-receipt:<ref>` — a `refs/stack-bases/<branch>` receipt whose
  paired `branch.<branch>.stackParent` config value names the same parent
  repository and PR, used when the parent head is no longer inherited.

`Boundary.corroborated` records whether preserved parent history proves that
no inherited commit follows `old_base`. Only an inherited parent head can
prove this from Git ancestry alone; a maintained receipt on a non-inherited
parent history is an unverified claim, because nothing in the local graph
shows that no later inherited commit exists beyond the receipted boundary.
The plan carries this as the `boundary_corroborated` key. When it is
`false`, `review_notes()` prepends an explicit warning that the receipt is
uncorroborated and must be proven from preserved parent history or reflog
before replay. A `false` value therefore keeps the plan review-required; it
never becomes silent authorization to replay a receipt the graph cannot
verify.

### Refusal conditions and exit contract

Every unrecoverable evidence gap raises `PlanError`, which carries a bounded
`category` drawn from the module's `CATEGORY_*` constants (`identity`,
`repository-state`, `metadata`, `recovery`, `boundary`, `range`, `race`,
`process`, `unclassified`). `PlanError.__init__(reason, category=...,
*, detail=None)` separates a bounded `reason` from unbounded `detail`:
`reason` must never embed subprocess output, credentials, or repository
contents, while `detail` carries that unbounded text, such as a failing
process's captured standard error. `str(exc)` is `reason` alone, or
`"{reason}: {detail}"` when `detail` is present, so an operator reading a
traceback still sees the full diagnostic. `PlanError` also carries a
`context: ErrorContext | None` attribute, stamped by the innermost enclosing
`phase()` that the error passed through. `ErrorContext` is a frozen
dataclass of `operation` and `phase`; it is how `main()` learns the failing
phase without ever parsing the message text.

`main()` catches `PlanError` and writes a bounded, six-field blocked record
to stderr via `blocked_record()`, then exits with status 2:

- `status` — always the literal `"blocked"`;
- `operation` — the run's correlation identifier, taken from the error's
  `context` when present;
- `phase` — the `PHASE_*` name the error was stamped with;
- `outcome` — always the literal `"blocked"`;
- `category` — the error's `CATEGORY_*` value;
- `reason` — `exc.reason`, the bounded message, reported verbatim. This is
  never `str(exc)` and never `exc.detail`.

The record never carries command output, credentials, or repository
contents, and stdout stays empty on a blocked run. A successful run prints
the indented JSON plan on stdout, with a `status` of `review-required` or
`no-op-decision-required`; neither status is an authorization to replay.

`trace()` writes bounded, structured JSON diagnostics to stderr, one line per
event, each keyed by an `operation` identifier generated once per run. That
same `operation` identifier is carried in the plan's own `operation` field,
so a reviewer can correlate the diagnostics for one run with its resulting
plan. Diagnostics never carry repository contents, only identities the plan
already reports, and stdout stays reserved for the plan JSON alone.

Diagnostics form one `operation_span()` per run, emitting an
`operation-started` and a terminal `operation-finished` record, with child
`phase()` records nested inside it emitting `phase-started` and
`phase-finished`. The bounded phase names are the `PHASE_*` constants:
`operation`, `preflight`, `parent-metadata`, `landing-validation`,
`parent-head-fetch`, `boundary-selection`, and `graph-planning`. The
previously separate `range-validation` and `identity-recheck` phases are now
one `graph-planning` phase in `build_plan()`, which computes the range and
rechecks that the branch and target have not moved in the same phase.

Every terminal record — `phase-finished` and `operation-finished` — carries
`phase`, `outcome` (`ok` or `blocked`), and `elapsed_ms`; a failing record
additionally carries `error_category` taken from the raised `PlanError`. A
reviewer can therefore aggregate phase and operation outcomes and timings
without parsing human-readable reasons.

### Test strategy

`tests/test_rebase_plan.py` and `tests/test_rebase_replay.py` exercise the
real planner against real Git repositories built by
`tests/rebase_test_support.py`, using real Git transport throughout. Only
`gh` is mocked, through [`leynos/cmd-mox`](https://github.com/leynos/cmd-mox).
`tests/test_rebase_plan.py` also pins the `PlanError.reason`/`detail` split:
a blocked record excludes subprocess output entirely, while `str(exc)`
still retains it for an operator reading a traceback, and phase durations
come from an injected `clock` rather than real elapsed time.

Each test builds an `M-A-B-C-D` graph plus a squash-merged target in an
isolated working repository and a bare stand-in remote. A repository-local
`url.<file-uri>.insteadOf` rule rewrites the explicit
`https://github.com/<parent-repository>.git` fetch URL to that bare
repository, which exposes the parent head at `refs/pull/<PR>/head`.
`GIT_ALLOW_PROTOCOL=file` is set for every test so that Git can only use the
file transport, preventing accidental live network traffic even if the
rewrite rule were ever missing or wrong.

Fixtures under `tests/fixtures/rebase-gh/` were recorded from a real `gh
2.100.0` run against `leynos/agent-helper-scripts#50` and a real 404 for a
missing PR. `tests/fixtures/rebase-gh/manifest.json` records the exact argv,
exit code, capture timestamp, and CLI version for each recorded command.
Tests assert the mocked `gh` invocation's argv against this manifest rather
than against the module's own constants, so a change that silently altered
the real query would be caught even if the same mistake were also made in
`PARENT_QUERY`. Tests never refresh these fixtures and never call the real
`gh` or GitHub; see `tests/fixtures/rebase-gh/README.md` for the manual
refresh procedure maintainers must follow instead.

`tests/test_rebase_plan_properties.py` covers the range invariants across
generated histories with Hypothesis. Because `build_plan()` needs no process
or network access, these properties drive it directly with a hand-built
`Evidence` snapshot and no `gh` double at all: for any bounded linear graph
with an inherited parent head, the derived range must be exactly the child
commits in order and must exclude every inherited parent commit and the
landing commit. Keep that separation intact — a property test that needed a
`gh` double would be a sign that discovery had leaked back into plan
construction.

`tests/test_rebase_plan_domain.py` exercises the whole boundary and range
policy as a domain: it builds no Git repository, runs no `gh`, and stands up
no process double at all. It drives `check_identities()`,
`select_boundary()`, `check_receipt_ref()`, `check_range()`,
`check_unmoved()`, and `plan_replay()` directly against hand-built typed
facts (`BoundaryFacts`, `ReceiptFacts`, `RangeFacts`, `Identities`). It also
asserts that `ReplayPlan` carries no Git command at all — no field name
containing `argv` or `command` — and that `rebase_argv()` renders the
documented replay command from a `ReplayPlan`, or `None` for an empty range.
This module is the practical proof that the domain layer is pure: a test in
it that needed a process double would mean discovery had leaked back into
the domain. Parametrized guards enforce that structurally: every documented
domain symbol is parsed and asserted to reference no adapter concern, so a
future `Path`, subprocess, or `REBASE_PREFIX` reference fails a test rather
than merely contradicting this paragraph.

### Running these tests locally

```bash
uv run --group dev python -m pytest \
  tests/test_rebase_plan.py tests/test_rebase_replay.py \
  tests/test_rebase_plan_properties.py tests/test_rebase_plan_domain.py -v
```

## Workflow pins and Dependabot

Dependabot owns the upgrade of GitHub Actions and reusable workflows, including
calls into `leynos/shared-actions`. Contract tests that assert a caller's exact
commit SHA create a lockstep dependency: every time Dependabot opens a bump PR,
the test fails until a human edits the pinned constant to match. That defeats
the purpose of automated dependency updates and turns a routine bump into a
manual chore.

Contract tests may still verify the *shape* of a reusable-workflow caller. They
must not verify the specific SHA value.

- Do assert the workflow references the correct reusable workflow path.
- Do assert the ref is pinned to a full 40-character commit SHA, not a
  mutable branch such as `main` or `rolling`.
- Do assert the expected `on:` triggers, least-privilege `permissions:`, and
  the inputs the caller relies on.
- Do not hard-code the current SHA value as an expected string. Match it with
  a pattern instead.
- Do not fail a test purely because Dependabot bumped the pinned SHA.

```python
import re

SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def test_uses_pinned_full_sha(caller_step):
    ref = caller_step["uses"].split("@")[-1]
    assert SHA_RE.match(ref), f"expected a 40-hex commit SHA, got {ref!r}"
```

If a workflow's behaviour genuinely depends on a feature only present from a
particular commit onwards, express that as a comment or a changelog note, not
as a test assertion on the SHA string.

## Mutation-testing workflow contract tests

This repository runs scheduled, informational mutation testing through a thin
caller workflow, [`.github/workflows/mutation-testing.yml`](../.github/workflows/mutation-testing.yml),
which delegates to the shared reusable workflow
`leynos/shared-actions/.github/workflows/mutation-mutmut.yml`. The heavy
lifting — running `mutmut` and summarizing survivors — lives in
`shared-actions`; this repository carries only declarative configuration. The
run is **informational only**: it never gates a pull request. Survivors are
reported through the job summary and downloadable artefacts so they can be
triaged into tests, not enforced as a blocking check. The mutation targets and
test selection themselves are configured in `[tool.mutmut]` in
`pyproject.toml` (`source_paths`, `do_not_mutate`,
`pytest_add_cli_args_test_selection`).

The workflow runs in two modes. A **daily schedule** fires a change-scoped run
that mutates only the source files touched within the detection window, so
quiet days are cheap no-ops. A **manual dispatch** (the Actions "Run workflow"
control) mutates the whole package; select a branch in that control to
exercise a feature branch.

The caller passes two configuration inputs:

- `paths` — set to `hooks/`, the change-detection glob bounding scheduled runs
  to the repository's only importable product code (the Stop-hook script and
  its co-located tests).
- `module-prefix-strip` — set to `""` because the flat `hooks/` layout means
  changed-file paths already map to module globs unaltered, with no package
  prefix to strip.

The repository does not set `exclude-globs` or `extra-args`; both default in
the shared workflow.

The `uses:` reference pins the shared workflow to a full 40-character commit
SHA rather than a branch or tag, so a force-push upstream cannot silently
change what runs here. The contract test asserts only that the pin is a full
commit SHA, not a particular value, so Dependabot bumps it automatically
without any accompanying test edit.

Because the caller is configuration rather than code, `tests/test_workflow_contract.py`
pins the shape it must uphold, failing the pull request when the caller drifts
— repointing the pin at a branch, widening the token scope, or dropping a
configuration input — rather than letting the breakage surface only in a
scheduled run. The test module self-skips when the workflow file is absent
(`pytestmark = pytest.mark.skipif(not WORKFLOW_PATH.exists(), ...)`) because
`mutmut` copies sources into a `mutants/` sandbox that omits `.github/`, and
the contract test would otherwise fail there for the wrong reason. Run it
locally with
`uv run --group dev python -m pytest tests/test_workflow_contract.py -v`, or
as part of the full suite via `make test`. The test validates:

- the `uses:` reference targets `mutation-mutmut.yml` pinned to a full commit
  SHA;
- the `with:` block carries exactly `paths: hooks/` and
  `module-prefix-strip: ""`, nothing more and nothing less;
- job permissions are least-privilege (`contents: read`, `id-token: write`)
  and the workflow-level default token scope is empty;
- `concurrency` serializes runs per ref (`mutation-testing-${{ github.ref }}`)
  without cancelling one in progress; and
- the triggers keep the daily schedule (`50 12 * * *`) and a plain
  `workflow_dispatch` with no inputs.

## Ansible testing skill contract

The `ansible-testing` skill documents local-first Ansible testing of
collections, roles, and modules. The user-facing summary lives in the "Ansible
testing" section of [docs/users-guide.md](users-guide.md); the skill at
[skills/ansible-testing/SKILL.md](../skills/ansible-testing/SKILL.md) carries
the full Molecule and native worker mode rules.

The scheduling rules are restated in two places (the closing bullet of section
3f and the closing bullet of item 7 in section 3g) and must stay word for word
identical. `tests/test_ansible_testing_skill.py` pins them, failing on
restatement drift, a users' guide rule loss, or a missing native worker mode
constraint.

This repository does not depend on Molecule. Molecule and `ansible-test` are
what the skill documents for downstream Ansible projects that adopt it; the
skill's install recipe pins `"molecule>=26.3.0"` because native worker mode
(`--workers`) first shipped in that release.

The skill fixes these constraints:

- Native worker mode is upstream-experimental; CI or dedicated runners only.
- Native worker mode requires `shared_state: true` and must not be combined
  with `--destroy=never`.
- The fact cache is scoped per scenario through `${MOLECULE_SCENARIO_NAME}`.
- `molecule test --all` is the sequential fallback.

## Validation expectations

When changing bootstrap behaviour in this repository, replay the usual
validation sequence:

- `make check-fmt`
- `make lint`
- `make typecheck`
- `make test`
- `make markdownlint`
- `make nixie` when a Mermaid diagram changed
- targeted `bash -n` on changed shell scripts
- targeted `shellcheck` on changed shell scripts
- `git diff --check`

Split-specific checks:

- `make lint` includes `check-home-phase-boundary`, which rejects forbidden
  machine-level operations in the home phase scripts.
- Run the system phase twice in a clean container when package-manager
  behaviour changes.
- Run the home phase with package-manager and privilege-escalation commands
  shadowed to fail when home/system boundary behaviour changes.
- Run the home phase twice against the same `$HOME` when managed config output
  changes.
- Restore a warm `$HOME` into a fresh system layer, clear APT lists, then run
  the system phase when `apt-update-if-stale` changes.

### Test helper: `tests/biome_typescript_pipeline_support.py`

`tests/biome_typescript_pipeline_support.py` is shared plumbing for the tests
of the changed-file pipeline documented in
`skills/biome-typescript/references/ci-hooks.md`, the one part of the skill
that runs in a shell. It exposes:

- `git_environment()` — returns an environment that ignores the host's Git
  configuration, so difftool, signing and identity settings cannot affect a
  test.
- `run_git(repository, *args, check=True)` — runs Git in a temporary
  repository with captured output.
- `run_body(block)` — extracts and dedents the `run: |` block scalar from a
  workflow step.
- `documented_pipeline()` — returns the changed-file pipeline exactly as the
  skill documents it.
- `PipelineRepository` — a frozen dataclass whose `write`, `remove`, `rename`
  and `commit` methods change and record repository state, and whose `run`
  executes the documented body under Bash with a stub `biome` first on `PATH`,
  so no test requires Biome to be installed. Its `biome_calls` and `arguments`
  describe the most recent run, whose stub log is cleared first so an assertion
  cannot be satisfied by an earlier run's argument.
- `pipeline` — a function-scoped fixture that builds a repository whose
  `origin/main` precedes the feature branch.

The tests run the documented `run:` body itself rather than a copy of it.
`tests/conftest.py` re-exports the `pipeline` fixture, so a test module names
it without importing the support module's other contents. Two modules consume
it: `tests/test_biome_typescript_procedures.py` uses fixed filenames with one
test per behaviour, covering spaces, newlines, renames, deleted paths, an
empty change set and a failing Biome, while
`tests/test_biome_typescript_procedures_properties.py` runs a Hypothesis
property over generated path components, marked `slow`. The tests are
POSIX-only: the documented command is POSIX shell relying on GNU `xargs -r`,
which the skill names as an extension already present on its `ubuntu-latest`
runner, so the tests that execute it skip on a host that is not POSIX. This is
a deliberate scope, not a gap.
