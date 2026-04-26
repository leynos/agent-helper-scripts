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

The phase dispatcher is `rust-entrypoint`. It reads
`RUST_ENTRYPOINT_PHASE` and runs one of these modes:

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
  `$SUDO` on non-root machines.
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
longer installs `sudo` as a convenience package; the `SUDO` shim is expected to
cover system-phase helper scripts in that case.

## Configuration patterns

### Test a helper branch

```bash
export HELPER_TOOLS_REPO_BRANCH=feature-branch
curl -fsSL \
  "https://raw.githubusercontent.com/leynos/agent-helper-scripts/refs/heads/feature-branch/rust-entrypoint" |
  bash -euo pipefail
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

The phase split adds a second boundary: system helpers use a temporary checkout,
while home helpers use the durable managed checkout. Keep that distinction
visible when adding new bootstrap behaviour.

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
  - Run `git clone --branch ... --single-branch --sparse`.
  - Apply sparse-checkout selection.
- Missing checkout with `repo_branch` only:
  - Run `git clone --branch ... --single-branch`.
- Missing checkout with no `repo_branch`:
  - Shallow-clone the default remote branch.
  - Apply sparse-checkout selection when `sparse_set` is set.

Example:

```bash
clone_or_update_repo \
  "${REPO_URL}" \
  "${REPO_DIR}" \
  "skills" \
  "${HELPER_TOOLS_REPO_BRANCH}"
```

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
