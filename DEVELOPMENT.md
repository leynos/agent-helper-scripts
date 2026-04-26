# Development Notes

## Overview

The helper bootstrap flow is split by authority boundary:

1. Run the system phase to configure APT repositories, APT packages,
   certificates, and optional global linker state.
2. Run the home phase to clone `agent-helper-scripts` locally and execute the
   remaining helper scripts from that managed checkout.

This keeps non-cacheable system mutations separate from warm-cache-friendly
`$HOME` mutations while preserving branchable, inspectable helper logic.

## Mandatory Prerequisites

- `git` is required for the cloning-based helper bootstrap model.
- `rust-entrypoint` installs `git` automatically when it is missing, using
  `$SUDO` on non-root machines.
- If `HELPER_TOOLS_REPO_DIR` already exists and is not a Git checkout,
  `rust-entrypoint` now treats that as an error and exits rather than deleting
  the path.

## Environment Variables

### Helper repository configuration

- `HELPER_TOOLS_REPO_URL`
  - Default: `https://github.com/leynos/agent-helper-scripts.git`
  - Controls the Git remote used by the managed helper checkout.
- `HELPER_TOOLS_REPO_BRANCH`
  - Default: `main`
  - Controls which branch `rust-entrypoint`, `install-hooks`, and
    `install-skills` fetch and reset to.
- `HELPER_TOOLS_REPO_NAME`
  - Default: derived from `HELPER_TOOLS_REPO_URL`
  - Used to derive the default clone path when no explicit directory override
    is provided.
- `HELPER_TOOLS_REPO_DIR`
  - Default: `${HOME}/git/${HELPER_TOOLS_REPO_NAME}`
  - Controls the filesystem path of the managed helper checkout.
  - `install-hooks` and `install-skills` now respect this value, so the helper
    chain reuses a single checkout.

### Bootstrap behaviour flags

- `RUST_ENTRYPOINT_PHASE`
  - Default: `both`
  - `system`: installs APT repositories, APT packages, certificates, and
    optional global linker changes. It is safe to run repeatedly on a fresh
    system layer and must not rely on warm `$HOME` state.
  - `home`: installs tools and configuration under `$HOME`. It is intended for
    warm cache creation or refresh and must not run package-manager commands,
    privilege escalation, or mutate machine-level package state.
  - `both`: runs `system` and then `home` for backwards-compatible one-shot
    setup.
- `WITH_ADD_REPOSITORIES`
  - Default: `1`
  - Enables the prerequisite `add-repositories` run before the main helper
    loop.
- `WITH_AI_TOOLING`
  - Default: `0`
  - Adds `get-ai-tooling` to the helper loop only when explicitly enabled.
- `WITH_LETA_WORKSPACE_ADD`
  - Default: `1`
  - Controls whether `get-github-tooling` runs `leta workspace add .`.
  - Set to `0` when creating a generic warm home cache that should not register
    the current project directory.
- `UBUNTU_APT_MIRROR`
  - Default: `http://mirror.math.princeton.edu/pub/ubuntu/`
  - Controls the Ubuntu mirror written by the system phase.

### Helper package metadata

- `install-required-apt-packages`
  - Reads `# requires-apt-packages: ...` metadata comments from helper scripts.
  - Metadata syntax is whitespace-separated package names after the colon, for
    example `# requires-apt-packages: gh ripgrep fd-find`.
  - Multiple metadata lines are allowed; comma-separated package lists are not
    supported.
  - Deduplicates the declared packages and installs them in one `apt-get
    install -y` pass before the main helper loop begins.
  - `rust-entrypoint-system` runs this helper after `add-repositories`, so
    repository-provided packages such as `gh` are available from configured APT
    sources before the home phase starts.
  - Optional system packages such as `kopia`, `glow`, and best-effort Linux
    tracing packages are installed by `rust-entrypoint-system`.
  - Root execution no longer installs `sudo` as a convenience package; the
    `SUDO` shim is expected to cover system-phase helper scripts in that case.

## Configuration Patterns

### Test a helper branch

```bash
export HELPER_TOOLS_REPO_BRANCH=feature-branch
curl -fsSL \
  "https://raw.githubusercontent.com/leynos/agent-helper-scripts/refs/heads/feature-branch/rust-entrypoint" |
  bash -xeuo pipefail
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

## Architectural Rationale

The cloning-based approach replaces repeated repository-owned `curl | bash`
invocations with a single managed checkout. That change was made so that:

- helper scripts execute from a known local tree after bootstrap starts,
- branch-specific helper changes are easy to test with one environment
  variable,
- repository-owned binaries and wrapper scripts can be installed from the same
  checkout,
- helper sub-scripts share one checkout path instead of drifting into multiple
  independent clones.

## Script Responsibilities and Helper Functions

### `rust-entrypoint`

- Dispatches to `rust-entrypoint-system`, `rust-entrypoint-home`, or both based
  on `RUST_ENTRYPOINT_PHASE`.

### `bootstrap-common`

- `clone_or_update_helper_tools_repo`
  - Ensures the managed helper checkout exists at
    `HELPER_TOOLS_REPO_DIR`.
  - Fetches and resets to `HELPER_TOOLS_REPO_BRANCH` for existing clones.
  - Performs sparse checkout for the repository-owned helper files and the
    `skills` tree.
- `install_helper_script`
  - Installs repository-owned helper executables from the managed checkout into
    `${HOME}/.local/bin`.
- `install-required-apt-packages`
  - Scans the `get-*` and `install-*` helpers selected for the current run.
  - Installs their unconditional APT package requirements in a single
    deduplicated pass before those helpers execute.
- `needs`
  - Returns true (exit 0) when the named command is absent from `PATH`.
  - Used as a lightweight guard: `if needs <cmd>; then …; fi`.

### `rust-entrypoint-system`

- Configures Ubuntu APT sources using `UBUNTU_APT_MIRROR`.
- Installs hard bootstrap prerequisites.
- Clones a temporary sparse helper checkout without mutating
  `HELPER_TOOLS_REPO_DIR`.
- Runs `add-repositories` when enabled.
- Installs package metadata from the selected helper scripts.
- Installs optional system packages, runs certificate updates, and applies
  `WITH_MOLD_LD_OVERRIDE` when requested.

### `rust-entrypoint-home`

- Updates shell profile PATH blocks and the current process PATH.
- Clones or updates `HELPER_TOOLS_REPO_DIR`.
- Installs user-level bootstrap tools and runs the selected home helpers.
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

#### `clone_or_update_repo`

```text
clone_or_update_repo <repo_url> <repo_dir> [sparse_set] [repo_branch]
```

- `repo_url`: Git remote to clone when `repo_dir` does not exist.
- `repo_dir`: Absolute path of the local checkout; trailing slashes are
  stripped.
- `sparse_set` *(optional)*: Space-separated list of paths to enable with
  `git sparse-checkout set`.
- `repo_branch` *(optional)*: Branch name to fetch and reset to; omit to use
  `origin/HEAD`.

Control-flow summary:

| `repo_dir` exists | `repo_branch` set | `sparse_set` set | Behaviour |
| --- | --- | --- | --- |
| Yes | Yes | — | `fetch --depth 1 origin <branch>` then `reset --hard FETCH_HEAD` |
| Yes | No | — | `fetch origin` then `reset --hard origin/HEAD` |
| No | Yes | Yes | `git clone --branch … --single-branch --sparse` |
| No | Yes | No | `git clone --branch … --single-branch` |
| No | No | No | shallow-clone the default remote branch |
| No | No | Yes | default clone then apply sparse-checkout selection |

Sparse-checkout selection is applied after clone or update when
`sparse_set` is non-empty.

Example: `clone_or_update_repo "${REPO_URL}" "${REPO_DIR}" "skills" "${HELPER_TOOLS_REPO_BRANCH}"`

## Validation Expectations

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
