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
`**/*.md` explicitly rather than relying on a default.

The `markdownlint` wrapper shipped for consumers appends that glob when the
caller names no path. It treats two arguments as explicit targets rather than
paths, so no glob is appended for either: a standalone `-`, which tells
`markdownlint-cli2` to read the file list from standard input, and the operand
of `--config` or `--configPointer`, which names a configuration file rather
than a document to lint. The repository's own gate does not go through the
wrapper: it calls `markdownlint-cli2` directly, because the shared baseline
this repository is moving to provisions the binary globally, which is the case
the wrapper exists to cover.

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
  - Lints every Markdown file with `markdownlint-cli2`, naming the `**/*.md`
    glob explicitly so the gate cannot pass without having read a file. The
    repository's `markdownlint` wrapper is still shipped for consumers; this
    target does not run it.
  - Reads `.markdownlint-cli2.jsonc`. The wrapper ships its own configuration
    for a consumer repository that has none, so the same script works unchanged
    where `get-markdown-tooling` installs it as `markdownlint`.
- `make nixie`
  - Validates every Mermaid diagram with `nixie`.
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

When extending the procedures module, note two traps at this boundary. A cmd-mox shim
reads standard input, so Git must be run with `stdin=DEVNULL` or the shim and
Git deadlock. Git also hands the driver repository-relative temporary paths,
while handlers run in the pytest process, so `%A` must be resolved against the
repository before writing.

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
