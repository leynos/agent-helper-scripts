# Replace GitHub curl and wget downloads with vendcurl

This ExecPlan (execution plan) is a living document. The sections
`Constraints`, `Tolerances`, `Risks`, `Progress`, `Surprises & Discoveries`,
`Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work
proceeds.

Status: COMPLETE

## Purpose / big picture

The helper scripts in this repository still fetch several GitHub-hosted
artifacts with raw `curl` and `wget`, including three `curl | bash` installers.
After this change, every GitHub-hosted binary or installer artifact in the
scoped scripts will be downloaded with `vendcurl`, while preserving the
existing install destinations, archive extraction steps, checksum verification
where the upstream installer already performed it, and any required `chmod`,
`install`, `mv`, `tar`, or `unzip` post-processing.

The observable success condition is:

1. `rg` no longer finds GitHub-hosted `curl` or `wget` downloads in the scoped
   scripts.
2. The scripts still contain explicit local post-processing for the artifacts
   that used to be installed indirectly through upstream shell installers.
3. The repository validation suite passes with logged evidence.

## Constraints

- Only GitHub-hosted `curl` and `wget` download paths in the helper scripts are
  in scope.
- Non-GitHub downloads such as `sh.rustup.rs`, `astral.sh`, `bun.sh`, and
  `get.opentofu.org` stay unchanged.
- Preserve existing version knobs and install destinations unless a change is
  required to replace the GitHub download mechanism safely.
- `vendcurl` cannot stream to stdout, so every replacement must download to an
  explicit file and then perform local processing.
- Preserve any checksum verification that the upstream installer already did,
  rather than silently weakening integrity checks.
- Validation commands must run sequentially and log via `tee`.

## Tolerances

- If an upstream installer performs non-trivial logic beyond download,
  extraction, checksum verification, and installation, stop and reassess rather
  than guessing.
- If `vendcurl` cannot faithfully replace a GitHub path without a broader
  behavioural change, stop and surface the gap.
- If validation fails outside the touched scope, investigate enough to confirm
  whether the change caused it before deciding whether to proceed.

## Risks

- Replacing `curl | bash` with local logic can accidentally drop checksum
  verification or install to a different path than before.
- GitHub release assets use different naming conventions per project, so OS and
  architecture mapping must match the upstream installer logic.
- Some upstream installers rely on default working directories; replacing them
  directly must preserve the effective destination.

## Inventory

The discovery pass identified the following scoped GitHub download sites.

1. `get-github-tooling`
   - `vk`: direct binary from
     `https://github.com/leynos/vk/releases/download/v${VK_VERSION}/vk`
     followed by `chmod 755` into `~/.local/bin/vk`.
   - `checkmake`: direct binary from
     `https://github.com/checkmake/checkmake/releases/download/${CHECKMAKE_VERSION}/checkmake-${CHECKMAKE_VERSION}.linux.amd64`
     written as `checkmake` and `chmod 755`.
   - `act`: remote installer from
     `https://raw.githubusercontent.com/nektos/act/master/install.sh`.
     Upstream script downloads `act_Linux_x86_64.tar.gz` (or the matching
     platform archive) and `checksums.txt` from
     `https://github.com/nektos/act/releases/download/${TAG}/...`, verifies the
     checksum, extracts `act`, and installs it into the current directory's
     `./bin`. In this repo that resolves to `${HOME}/.local/bin` because the
     script runs from `${HOME}/.local`.
2. `get-open-tofu-tooling`
   - `tflint`: remote installer from
     `https://raw.githubusercontent.com/terraform-linters/tflint/master/install_linux.sh`.
     Upstream script downloads `tflint_${os}.zip` from either
     `releases/latest/download/` or `releases/download/${TFLINT_VERSION}/`,
     unzips it, and installs `tflint` into
     `${TFLINT_INSTALL_PATH:-/usr/local/bin}` with `sudo` when needed.
   - `conftest`: current script uses GitHub API + release asset:
     `https://api.github.com/repos/open-policy-agent/conftest/releases/latest`
     and
     `https://github.com/open-policy-agent/conftest/releases/download/v${LATEST_VERSION}/conftest_${LATEST_VERSION}_${SYSTEM}_${ARCH}.tar.gz`,
     then extracts the tarball and moves `conftest` into `~/.local/bin`.
3. `install-sub-agents`
   - `context_pack`: remote installer from
     `https://raw.githubusercontent.com/AmirTlinov/context_pack/main/scripts/install.sh`.
     Upstream script resolves a tag from GitHub, downloads
     `mcp-context-pack-${target}.tar.gz` plus `checksums.sha256` from
     `https://github.com/AmirTlinov/context_pack/releases/download/${tag}/...`,
     verifies the checksum, extracts `mcp-context-pack`, and installs it to
     `${CONTEXT_PACK_INSTALL_DIR:-$HOME/.local/bin}`.
4. `get-rust-tooling`
   - Already contains the model replacement pattern to follow:
     `vendcurl https://github.com/cargo-bins/cargo-binstall/releases/latest/download/cargo-binstall-x86_64-unknown-linux-musl.tgz`
     followed by local extraction and installation.

## Plan

1. Replace the direct GitHub release downloads in `get-github-tooling` with
   `vendcurl`, keeping the same final filenames and `chmod` steps.
2. Replace each GitHub-backed `curl | bash` flow with explicit local logic:
   download the real release asset with `vendcurl`, download the upstream
   checksum file with `vendcurl` where the installer previously verified
   checksums, validate locally, then extract and install.
3. Replace the `wget`-based `conftest` lookup with a `vendcurl` download from a
   `releases/latest/download/` or pinned release asset URL, then keep the local
   tar extraction and move step.
4. Re-scan the repository to confirm the scoped scripts contain no GitHub
   `curl` or `wget` downloads.
5. Run sequential validation with log capture, then commit the change.

## Progress

- [x] 2026-04-22T14:06:00+01:00: Checked branch state, loaded relevant repo
  instructions, and reviewed prior memory for helper bootstrap download
  patterns.
- [x] 2026-04-22T14:06:00+01:00: Identified all scoped GitHub `curl`/`wget`
  usage in the helper scripts and inspected the three upstream installer
  scripts to recover their real binary URLs and post-processing.
- [x] 2026-04-22T14:10:54+01:00: Patched the helper scripts to replace the
  scoped GitHub download sites with `vendcurl`, including local extraction and
  installation logic for the former `curl | bash` installers.
- [x] 2026-04-22T14:10:54+01:00: Re-scanned the touched scripts and confirmed
  there are no remaining GitHub-backed `curl` or `wget` invocations in scope.
- [x] 2026-04-22T14:10:54+01:00: Ran sequential validation with tee logs and
  confirmed every gate passed.
- [ ] Commit the change.

## Surprises & Discoveries

- `grepai` is available on this machine, but `agent-helper-scripts` is not yet
  listed as an indexed `Projects` workspace project, so exact search was
  necessary for the discovery pass.
- `vendcurl --help` says the default output path is the URL basename, but the
  task requirements explicitly state that content-disposition naming should be
  assumed when no second positional filename is supplied. The implementation
  should therefore pass explicit output paths whenever the local filename must
  be stable.
- The `act` and `context_pack` upstream installers both verify release
  checksums. That integrity step must survive the rewrite.
- `vendcurl` already provides `--sha256`, so the cleanest replacement is to
  download the upstream checksum manifest with `vendcurl`, extract the expected
  digest, and feed it back into the artifact download instead of re-implementing
  checksum validation separately.

## Decision Log

- 2026-04-22T14:06:00+01:00: Treat the user request as approval to both draft
  and execute this plan in one pass, because the prompt explicitly says to plan
  the process and then implement it once the inventory is complete.
- 2026-04-22T14:06:00+01:00: Use `releases/latest/download/...` URLs where that
  removes a separate GitHub API request without changing behaviour.
- 2026-04-22T14:06:00+01:00: Preserve upstream checksum verification for `act`
  and `context_pack` by downloading the checksum files with `vendcurl` and
  verifying them locally after download.
- 2026-04-22T14:10:54+01:00: Replace the manual checksum verification draft
  with `vendcurl --sha256` once the user pointed out that `vendcurl` already
  exposes SHA-256 validation.

## Outcomes & Retrospective

- Replaced the scoped GitHub `curl`/`wget` downloads in `get-github-tooling`,
  `get-open-tofu-tooling`, and `install-sub-agents` with `vendcurl`.
- Converted the former `curl | bash` installers for `act`, `tflint`, and
  `context_pack` into explicit local download, checksum, extraction, and
  install steps.
- Kept `conftest` on a GitHub release flow, but replaced both the GitHub API
  metadata fetch and the release tarball download with `vendcurl`.
- Validation passed with logs:
  - `/tmp/bash-n-agent-helper-scripts-adopt-vendcurl.out`
  - `/tmp/shellcheck-agent-helper-scripts-adopt-vendcurl.out`
  - `/tmp/check-fmt-agent-helper-scripts-adopt-vendcurl.out`
  - `/tmp/lint-agent-helper-scripts-adopt-vendcurl.out`
  - `/tmp/typecheck-agent-helper-scripts-adopt-vendcurl.out`
  - `/tmp/test-agent-helper-scripts-adopt-vendcurl.out`
  - `/tmp/diff-check-agent-helper-scripts-adopt-vendcurl.out`
