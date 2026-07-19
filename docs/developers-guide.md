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

### `install-skills`

- Reuses the managed helper checkout path when `HELPER_TOOLS_REPO_DIR` is
  exported.
- Reapplies sparse checkout for `skills` when a managed clone already exists,
  so older sparse checkouts are repaired before copying skills.

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

### Shared en-GB-oxendict spelling data

The architecture and trade-offs are recorded in
[ADR 003](adr/003-shared-oxford-spelling-base.md).

The tracked `data/typos-oxendict-base.toml` file is the estate-wide source of
generic Oxford `-ize` mappings, accepted words and safe exclusions. Add a word
there only when it is valid across repositories. Product names, quoted upstream
terms and fixture-specific vocabulary belong in the consumer repository's
tracked `typos.local.toml` overlay.

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
scanner recognizes all Python brace forms, including `{n}`, `{n,}`, `{n,m}`
and `{,n}`. It permits repetitions separated by unquantified atoms. Example
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

- `make ci`
  - Runs the full CI gate in sequence: `check-fmt`, `lint`, `typecheck`, `test`,
    and `spelling`.
  - Use this before pushing; it mirrors what the GitHub Actions workflow
    executes.
- `make lint`
  - Runs `syntax-check`, `shell-syntax-check`, and
    `check-home-phase-boundary`.
- `make shell-syntax-check`
  - Runs `bash -n` over every shell script listed in `SHELL_SCRIPTS` to catch
    syntax errors without executing any code.
- `make check-home-phase-boundary`
  - Rejects APT, `sudo`, and linker mutation patterns in home-phase scripts.
  - Scans non-comment lines only.
- `make test-hooks`
  - Runs the hook-only pytest subset (`HOOK_TESTS`) via
    `uv run python -m pytest`.
- `make test-entrypoints`
  - Runs the entrypoint-only pytest subset (`ENTRYPOINT_TESTS`) via
    `uv run python -m pytest`.
  - Use this when iterating on `rust-entrypoint`, `rust-entrypoint-system`, or
    `rust-entrypoint-home`.

## Subagent manifest

`agents/subagents.yml` is the provider-neutral source of truth for the managed
subagents (`wyvern`, `scribe`, `alchemist`, `scrutineer`). For the user-facing
description of what each subagent does and how downstream provisioning renders
the manifest, see the `## Sub-agent definitions` section in
[docs/users-guide.md](users-guide.md). This section covers the test-loader
concerns only.

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

Two test suites consume the helper:

- `tests/test_subagent_definitions.py` — happy-path deployment-contract
  regressions. It asserts specific model choices, sandbox modes, tool grants,
  and load-bearing instruction prose for each subagent. Any edit that weakens
  one of those values fails a test rather than silently degrading a provisioned
  agent.
- `tests/test_subagent_manifest.py` — error-path coverage of the loader. It
  exercises the typed-error contract directly, confirming that malformed or
  incomplete manifests produce the expected exception types.

### PyYAML dependency

PyYAML is a development-only dependency, declared as `pyyaml>=6.0.3` in the
`[dependency-groups] dev` array of `pyproject.toml`. It is not a runtime
dependency of any bootstrap script; only the manifest test helper imports it.

## Workflow pins and Dependabot

Dependabot owns the upgrade of GitHub Actions and reusable workflows,
including calls into `leynos/shared-actions`. Contract tests that assert a
caller's exact commit SHA create a lockstep dependency: every time Dependabot
opens a bump PR, the test fails until a human edits the pinned constant to
match. That defeats the purpose of automated dependency updates and turns a
routine bump into a manual chore.

Contract tests may still verify the *shape* of a reusable-workflow caller.
They must not verify the specific SHA value.

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
- `module-prefix-strip` — set to `""`, because the flat `hooks/` layout means
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
(`pytestmark = pytest.mark.skipif(not WORKFLOW_PATH.exists(), ...)`), because
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

## Validation expectations

When changing bootstrap behaviour in this repository, replay the usual
validation sequence:

- `make check-fmt`
- `make lint`
- `make typecheck`
- `make test`
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
