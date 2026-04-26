# Helper Repo Bootstrap

The helper bootstrap flow starts from `rust-entrypoint`, then splits work by
authority boundary. System work uses a temporary helper checkout. Home-phase
work uses the managed helper checkout under `$HOME`.

This keeps package-manager and machine-level mutations separate from durable
user-cache mutations while still running repository-owned helper scripts from a
known local tree.

## User-facing Behaviour

- The initial bootstrap still starts from a remote `rust-entrypoint`.
- `RUST_ENTRYPOINT_PHASE` selects which phase runs:
  - `system`: configure APT sources, APT repositories, APT packages,
    certificates, and optional global linker state.
  - `home`: install tools and configuration under `$HOME`.
  - `both`: run `system` and then `home`; this is the default.
- `rust-entrypoint-system` clones `agent-helper-scripts` into a temporary
  sparse checkout and removes it on exit.
- `rust-entrypoint-home` clones or updates the managed local checkout at
  `HELPER_TOOLS_REPO_DIR`.
- Home helper scripts are executed from the managed checkout.
- Helper binaries that live in this repository, such as `markdownlint`,
  `mdformat-all`, and `notdeadyet`, are installed from the managed checkout
  instead of `raw.githubusercontent.com`.
- Before the home helper loop runs, the system phase scans the selected
  `get-*` and `install-*` scripts for `# requires-apt-packages: ...` metadata
  and installs the union of those packages in a single APT transaction.
- Helper package metadata uses whitespace-separated package names after the
  colon, and helper authors may repeat the metadata line when needed.
- The system phase installs hard bootstrap prerequisites such as `wget` and
  optional packages such as `kopia` before the home phase needs them.

## Environment Variables

### Phase selection

- `RUST_ENTRYPOINT_PHASE`
  - Default: `both`
  - Purpose: selects the authority boundary to run.
  - `system`: use this for fresh system layers.
  - `home`: use this for warm `$HOME` cache creation or refresh.
  - `both`: use this for ordinary one-shot setup.

### Helper repository selection

- `HELPER_TOOLS_REPO_URL`
  - Default: `https://github.com/leynos/agent-helper-scripts.git`
  - Purpose: sets the Git clone source for helper checkouts.
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

The system phase uses `HELPER_TOOLS_REPO_URL` and `HELPER_TOOLS_REPO_BRANCH`
when creating its temporary checkout, but it does not write to
`HELPER_TOOLS_REPO_DIR`. The home phase uses all four variables to manage the
durable checkout.

### Bootstrap toggles

- `WITH_AI_TOOLING`
  - Default: `0`
  - Purpose: controls whether `get-ai-tooling` runs during the home helper
    loop.
  - Override with a non-zero value to opt into AI-specific bootstrap tools.
- `WITH_ADD_REPOSITORIES`
  - Default: `1`
  - Purpose: controls whether `add-repositories` runs in the system phase.
  - Override with `0` to skip repository setup in constrained or preconfigured
    environments.

## Override Mechanism

Callers can export the environment variables before invoking
`rust-entrypoint`. For example:

```bash
export HELPER_TOOLS_REPO_BRANCH=remove-curl-bash-dependence
export HELPER_TOOLS_REPO_DIR="$HOME/git/agent-helper-scripts-test"
export WITH_AI_TOOLING=1
export RUST_ENTRYPOINT_PHASE=both
curl -fsSL \
  https://raw.githubusercontent.com/leynos/agent-helper-scripts/refs/heads/remove-curl-bash-dependence/rust-entrypoint |
  bash -xeuo pipefail
```

For warm-cache providers, run the phases separately:

```bash
RUST_ENTRYPOINT_PHASE=system bash rust-entrypoint
RUST_ENTRYPOINT_PHASE=home bash rust-entrypoint
```

Once `rust-entrypoint-home` starts, the helper repository configuration is
exported so sub-scripts such as `install-hooks`, `install-skills`,
`get-markdown-tooling`, and `get-rust-tooling` reuse the same managed checkout
instead of creating their own default clone elsewhere.

## Rationale

The cloning-based approach was introduced to solve three practical problems:

- Repeated `curl | bash` of repository-owned helper scripts made it difficult to
  reason about what version of the bootstrap logic was actually running.
- Scripts that needed repository-owned helper files had to keep downloading them
  individually from GitHub user-content URLs.
- Warm-home cache providers need system mutations and `$HOME` mutations to be
  separable.

By using a temporary checkout for system work and a managed checkout for
home-phase work, the bootstrap flow is more consistent, easier to test on
branch-specific changes, and easier to extend without adding more raw GitHub
fetches for repository-owned files.
