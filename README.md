# Agent Helper Scripts

This repository contains bootstrap scripts for preparing development
environments with the system packages, language toolchains, helper utilities,
skills, hooks, and agent configuration used by the Leynos agent workflow. The
Rust bootstrap is split by authority boundary so machine-level setup and
user-home setup can be run independently for cold system layers and warm home
caches.

## Quick start

Start with the [users' guide](docs/users-guide.md) for the bootstrap model,
common commands, and environment-variable configuration.

The main bootstrap entrypoint is [`rust-entrypoint`](rust-entrypoint). It
dispatches to the system, home, or sequential compatibility flow through
`RUST_ENTRYPOINT_PHASE`.

```bash
bash rust-entrypoint
```

For split runs:

```bash
RUST_ENTRYPOINT_PHASE=system bash rust-entrypoint
RUST_ENTRYPOINT_PHASE=home bash rust-entrypoint
```

## Shared spelling dictionary

`data/typos-oxendict-base.toml` is the shared en-GB-oxendict dictionary for the
`leynos` code estate. `scripts/typos_rollout_cli.py` harvests Oxford `-ise` and
`-ize` evidence, conditionally refreshes an untracked local copy of the shared
base, and deterministically generates a repository's tracked `typos.toml`.
Repository-specific product names, identifiers and quoted fixtures belong in a
local `typos.local.toml` overlay rather than the shared base. The same gate
checks curated exact phrase corrections, such as `hand-written` to
`handwritten`, which `typos` cannot enforce after tokenizing punctuation.

Run the repository's own spelling gate with:

```bash
make spelling
```

## Developer guide

See the [developers' guide](docs/developers-guide.md) for repository structure,
phase-split internals, validation targets, and contribution workflow.
