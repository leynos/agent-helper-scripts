# Development Notes

## Overview

The helper bootstrap flow is split into two phases:

1. Fetch and run `rust-entrypoint`.
2. Clone `agent-helper-scripts` locally and execute the remaining helper
   scripts from that managed checkout.

This keeps the follow-on bootstrap logic branchable, inspectable, and
consistent across scripts that need repository-owned helper files.

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

- `WITH_ADD_REPOSITORIES`
  - Default: `1`
  - Enables the prerequisite `add-repositories` run before the main helper
    loop.
- `WITH_AI_TOOLING`
  - Default: `0`
  - Adds `get-ai-tooling` to the helper loop only when explicitly enabled.

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

- `clone_or_update_helper_tools_repo`
  - Ensures the managed helper checkout exists at
    `HELPER_TOOLS_REPO_DIR`.
  - Fetches and resets to `HELPER_TOOLS_REPO_BRANCH` for existing clones.
  - Performs sparse checkout for the repository-owned helper files and the
    `skills` tree.
- `install_helper_script`
  - Installs repository-owned helper executables from the managed checkout into
    `${HOME}/.local/bin`.

### `install-hooks`

- Reuses the managed helper checkout path when `HELPER_TOOLS_REPO_DIR` is
  exported.
- Fetches the requested helper branch before copying hook files.

### `install-skills`

- Reuses the managed helper checkout path when `HELPER_TOOLS_REPO_DIR` is
  exported.
- Reapplies sparse checkout for `skills` when a managed clone already exists,
  so older sparse checkouts are repaired before copying skills.

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
