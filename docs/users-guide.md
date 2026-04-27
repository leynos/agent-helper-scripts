# Users' Guide

This guide explains how to run the helper bootstrap and how to configure it
with environment variables. It is written for people using the scripts, not for
people changing the scripts.

## Bootstrap model

The Rust bootstrap is split into two phases:

- `system`
  - Changes the machine layer.
  - Configures Ubuntu APT sources and third-party package repositories.
  - Installs APT packages, updates certificates, and applies optional global
    settings such as the `mold` linker override.
  - Uses a temporary helper checkout and does not intentionally manage the
    durable checkout under `$HOME`.
- `home`
  - Changes the user layer under `$HOME`.
  - Adds helper tool paths to shell startup files.
  - Clones or updates the managed helper checkout.
  - Installs user tools such as `uv`, `bun`, `rustup`, cargo tools, Bun global
    packages, skills, hooks, and sub-agent configuration.
  - Does not run APT, change `/etc`, change `/usr`, or mutate APT state.
- `both`
  - Runs `system` first and then `home`.
  - This is the default for the compatibility wrapper.

Run `system` for a fresh or reset system layer. Run `home` when creating or
refreshing a warm `$HOME` cache. In a warm-cache environment, run the phases
separately:

```bash
RUST_ENTRYPOINT_PHASE=system bash rust-entrypoint
RUST_ENTRYPOINT_PHASE=home bash rust-entrypoint
```

For a normal one-shot setup, use the default:

```bash
bash rust-entrypoint
```

The home phase expects the system phase to have prepared the packages and
shared libraries required by the user tools.

## Upgrading

See the [migration guide](migration-guide.md) when moving from the previous
single-phase `rust-entrypoint` bootstrap to the system/home phase split.

## Common settings

### `RUST_ENTRYPOINT_PHASE`

Default: `both`

Allowed values:

- `system`
- `home`
- `both`

Use this to select which bootstrap phase the `rust-entrypoint` wrapper runs.
Use `both` for ordinary setup, `system` for a fresh system layer, and `home` for
warm `$HOME` cache creation or refresh.

### `UBUNTU_APT_MIRROR`

Default: `http://mirror.math.princeton.edu/pub/ubuntu/`

The system phase writes an Ubuntu source definition that points at this mirror.
Set when a local, regional, private, or provider-managed Ubuntu mirror is
required.

```bash
UBUNTU_APT_MIRROR=http://archive.ubuntu.com/ubuntu/ \
  RUST_ENTRYPOINT_PHASE=system \
  bash rust-entrypoint
```

### `WITH_LETA_WORKSPACE_ADD`

Default: `1`

`get-github-tooling` installs `leta`. By default, it also runs:

```bash
leta workspace add .
```

Set `WITH_LETA_WORKSPACE_ADD=0` when creating a generic warm `$HOME` image or
when the current directory should not be registered as a `leta` workspace.

## Helper checkout settings

The home phase manages a sparse checkout of this repository. Other helper
scripts reuse the same checkout when these variables are exported.

- `HELPER_TOOLS_REPO_URL`
  - Default: `https://github.com/leynos/agent-helper-scripts.git`
  - Git repository to clone for helper scripts.
  - Set this to test a fork or mirror.
- `HELPER_TOOLS_REPO_BRANCH`
  - Default: `main`
  - Branch to fetch and reset the helper checkout to.
  - Set this to test branch-specific bootstrap changes.
- `HELPER_TOOLS_REPO_NAME`
  - Default: derived from `HELPER_TOOLS_REPO_URL`
  - Directory name used when `HELPER_TOOLS_REPO_DIR` is not set.
- `HELPER_TOOLS_REPO_DIR`
  - Default: `${HOME}/git/${HELPER_TOOLS_REPO_NAME}`
  - Managed helper checkout path.
  - Set when an isolated checkout is required.
- `REPO_DIR`
  - Default: `HELPER_TOOLS_REPO_DIR`, then
    `${HOME}/git/agent-helper-scripts`
  - Checkout used by `install-hooks` and `install-skills`.
  - Most users should leave this unset and configure
    `HELPER_TOOLS_REPO_DIR` instead.

Example:

```bash
export HELPER_TOOLS_REPO_BRANCH=my-feature-branch
export HELPER_TOOLS_REPO_DIR="$HOME/git/agent-helper-scripts"
bash rust-entrypoint
```

Use `main` for the published helper scripts, or replace it with a specific
helper branch when testing unpublished bootstrap changes.

## Feature toggles

### Repository and system toggles

- `WITH_ADD_REPOSITORIES`
  - Default: `1`
  - Runs `add-repositories` during the system phase.
  - Set to `0` when the image already has the required repositories.
- `INSTALL_GLOW`
  - Default: `0`
  - Adds the Charm repository and installs the APT `glow` package in the
    system phase.
- `WITH_MOLD_LD_OVERRIDE`
  - Default: `0`
  - Replaces `/usr/bin/ld` with a symlink to `/usr/bin/mold` when enabled.
  - This is a global linker change. Enable it only for images where that
    behaviour is intended.
- `WITH_TRACE`
  - Default: `0`
  - Enables Bash xtrace (`set -x`) in the deployment entrypoints and helper
    scripts.
  - Use for debugging bootstrap failures. Avoid enabling it in logs that may
    contain sensitive environment values.

### Tooling toggles

- `WITH_AI_TOOLING`
  - Default: `0`
  - Adds `get-ai-tooling` to the home-phase helper list.
- `WITH_VALE`
  - Default: `0`
  - Installs Vale through Bun in `get-markdown-tooling`.
- `WITH_LLVM_COV`
  - Default: `1`
  - Installs `cargo-llvm-cov` in `get-rust-tooling`.
- `WITH_WHITAKER`
  - Default: `0`
  - Installs Whitaker tooling in `get-rust-tooling`.
- `WITH_WHITAKER_EXPERIMENTAL`
  - Default: `0`
  - Installs experimental Whitaker pieces when Whitaker is enabled.
- `RUST_PRE_BUILD`
  - Default: `0`
  - Makes `rust-setup` run `cargo check --workspace --all-targets`.
  - Leave disabled when creating a generic warm `$HOME` cache.
- `RUST_ANALYZER_PRECHECK`
  - Default: `0`
  - Runs `rust-analyzer analysis-stats .` before the optional pre-build when
    `rust-analyzer` is available.

## Tool version settings

Use these variables to pin or override versions installed by the home phase:

- `VENDCURL_VERSION`
  - Default: `0.1.0`
  - Version installed with `uv tool install`.
- `RUST_CHANNEL`
  - Default: `stable`, unless `rust-toolchain.toml` declares a channel.
  - Rust toolchain installed by `rustup`.
- `CARGO_LLVM_COV_VERSION`
  - Default: `0.8.5`
  - Version of `cargo-llvm-cov`.
- `CARGO_NEXTEST_VERSION`
  - Default: `0.9.133`
  - Version of `cargo-nextest`.
- `KANI_VERIFIER_VERSION`
  - Default: `0.67.0`
  - Version of `kani-verifier`.
- `SCCACHE_VERSION`
  - Default: `0.14.0`
  - Version of `sccache` when `SCCACHE_BUCKET` is set.
- `WHITAKER_INSTALLER_VERSION`
  - Default: `0.2.4`
  - Version of `whitaker-installer`.
- `MDTABLEFIX_VERSION`
  - Default: `0.4.0`
  - Version of `mdtablefix`.
- `ACT_VERSION`
  - Default: `latest`
  - GitHub `act` release installed by `get-github-tooling`.
- `MERGIRAF_VERSION`
  - Default: `0.16.3`
  - Version of `mergiraf`.
- `DIFFTASTIC_VERSION`
  - Default: `0.68.0`
  - Version of `difftastic`.
- `LETA_VERSION`
  - Default: `0.13.0`
  - Version of `leta`.
- `ACTION_VALIDATOR_VERSION`
  - Default: `0.9.0`
  - Version of `action-validator`.
- `VK_VERSION`
  - Default: `0.5.0`
  - Version of `vk`.
- `CHECKMAKE_VERSION`
  - Default: `0.2.2`
  - Version of `checkmake`.

## Cache and cloud settings

### Cargo home

- `CARGO_HOME`
  - Default: `${HOME}/.cargo`
  - Cargo home directory used by Rust tooling and Kopia cache restore.

### Kopia cargo cache

Set `KOPIA_BUCKET` to enable Kopia-backed cargo cache restore and snapshot.
The system phase installs the `kopia` package when this is set. The home phase
connects to the repository, restores the cache, and snapshots it again after
tool installation.

- `KOPIA_BUCKET`
  - S3 bucket name.
- `KOPIA_CREATE`
  - Default: `0`
  - Set to `1` to create the Kopia repository before connecting.
- `KOPIA_ENDPOINT`
  - S3-compatible endpoint.
- `KOPIA_REGION`
  - S3 region.
- `AWS_ACCESS_KEY_ID`
  - Access key passed to Kopia.
- `AWS_SECRET_ACCESS_KEY`
  - Secret key passed to Kopia.

### `sccache`

Set `SCCACHE_BUCKET` to install and configure `sccache` for Rust builds.

- `SCCACHE_BUCKET`
  - Enables `sccache` setup.
- `SCCACHE_WEBDAV_ENDPOINT`
  - Optional WebDAV endpoint for `sccache`.
- `SCCACHE_VERSION`
  - Version of `sccache` to install.

## Sub-agent and context-pack settings

`install-sub-agents` can install `mcp-context-pack` into the user environment.
These variables customize that installation:

- `CONTEXT_PACK_REPO`
  - Default: `AmirTlinov/mcp-context-pack`
  - GitHub repository that publishes `mcp-context-pack` releases.
- `CONTEXT_PACK_VERSION`
  - Default: `latest`
  - Release version to install.
- `CONTEXT_PACK_INSTALL_DIR`
  - Default: `${HOME}/.local/bin`
  - Directory that receives the `mcp-context-pack` binary.

## OpenTofu helper settings

These variables apply when running `get-open-tofu-tooling` directly. That helper
is not part of the default `rust-entrypoint` helper list.

- `TFLINT_VERSION`
  - Default: `latest`
  - Version of `tflint`.
- `TFLINT_INSTALL_PATH`
  - Default: `/usr/local/bin`
  - Install path used by the upstream `tflint` installer.
- `CONFTEST_VERSION`
  - Default: `latest`
  - Version of `conftest`.

## Less common process settings

- `DEBIAN_FRONTEND`
  - Default: `noninteractive`
  - Exported by the bootstrap so APT does not prompt during unattended setup.
  - Most users should leave this unset.

Internal variables such as `SELECTED_TOOLS`, `PACKAGE_SCRIPTS`, and
`HELPER_TOOLS_SPARSE_PATHS` are implementation details. They are not stable
configuration points.
