# Helper Repo Bootstrap

The helper bootstrap flow now downloads `rust-entrypoint` once, then switches to
running helper scripts from a managed local checkout of
`agent-helper-scripts`. This keeps the follow-on bootstrap steps on a single
local source of truth instead of repeatedly fetching repository scripts from
GitHub and piping them into `bash`.

## User-facing Behaviour

- The initial bootstrap still starts from a remote `rust-entrypoint`.
- `rust-entrypoint` clones `agent-helper-scripts` into a local checkout.
- The remaining helper scripts are executed from that local checkout.
- Helper binaries that live in this repository, such as `markdownlint`,
  `mdformat-all`, and `notdeadyet`, are installed from the managed checkout
  instead of `raw.githubusercontent.com`.
- Before the helper loop runs, `rust-entrypoint` scans the selected `get-*`
  and `install-*` scripts for `# requires-apt-packages: ...` metadata and
  installs the union of those packages in a single APT transaction.
- Entry-point-owned optional packages, such as `wget` and `kopia`, are queued
  and installed immediately before the bootstrap step that first needs them,
  rather than at first mention.

## Environment Variables

### Helper repository selection

- `HELPER_TOOLS_REPO_URL`
  - Default: `https://github.com/leynos/agent-helper-scripts.git`
  - Purpose: sets the Git clone source for the managed helper checkout.
  - Override when testing a fork or mirror that should behave like the
    canonical helper repository.
- `HELPER_TOOLS_REPO_BRANCH`
  - Default: `main`
  - Purpose: selects the helper-repo branch to fetch and reset to.
  - Override when testing bootstrap changes from a non-main helper branch.
- `HELPER_TOOLS_REPO_DIR`
  - Default: `${HOME}/git/${HELPER_TOOLS_REPO_NAME}`
  - Purpose: chooses where the managed helper checkout lives on disk.
  - Override when a caller needs the helper checkout under a non-standard
    parent directory or wants multiple isolated helper clones.
- `HELPER_TOOLS_REPO_NAME`
  - Default: derived from `HELPER_TOOLS_REPO_URL`
  - Purpose: names the default clone directory when
    `HELPER_TOOLS_REPO_DIR` is not explicitly set.

### Bootstrap toggles

- `WITH_AI_TOOLING`
  - Default: `0`
  - Purpose: controls whether `get-ai-tooling` runs during the helper loop.
  - Override with a non-zero value to opt into AI-specific bootstrap tools.
- `WITH_ADD_REPOSITORIES`
  - Default: `1`
  - Purpose: controls whether `add-repositories` runs before the main helper
    loop.
  - Override with `0` to skip repository setup in constrained or preconfigured
    environments.

## Override Mechanism

Callers can export the environment variables before invoking
`rust-entrypoint`. For example:

```bash
export HELPER_TOOLS_REPO_BRANCH=remove-curl-bash-dependence
export HELPER_TOOLS_REPO_DIR="$HOME/git/agent-helper-scripts-test"
export WITH_AI_TOOLING=1
curl -fsSL \
  https://raw.githubusercontent.com/leynos/agent-helper-scripts/refs/heads/remove-curl-bash-dependence/rust-entrypoint |
  bash -xeuo pipefail
```

Once `rust-entrypoint` starts, the helper repository configuration is exported
so sub-scripts such as `install-hooks`, `install-skills`,
`get-markdown-tooling`, and `get-rust-tooling` reuse the same checkout instead
of creating their own default clone elsewhere.

## Rationale

The cloning-based approach was introduced to solve two practical problems:

- Repeated `curl | bash` of repository-owned helper scripts made it difficult to
  reason about what version of the bootstrap logic was actually running.
- Scripts that needed repository-owned helper files had to keep downloading them
  individually from GitHub user-content URLs.

By cloning once and then executing local helper scripts, the bootstrap flow is
more consistent, easier to test on branch-specific changes, and easier to
extend without adding more raw GitHub fetches for repository-owned files.
