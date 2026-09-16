# Agent Helper Scripts

This repository contains bootstrap scripts for preparing development
environments with the system packages, language toolchains, helper utilities,
skills, hooks, and agent configuration used by the Leynos agent workflow. The
Rust bootstrap is split by authority boundary so machine-level setup and
user-home setup can be run independently for cold system layers and warm home
caches.

## Quick start

Start with the [users' guide](docs/users-guide.md) for the bootstrap model,
common commands, environment-variable configuration, and the installed skill
workflows, including CodeScene analysis, stacked pull requests, entity-aware
merges, CodeRabbit reviews through the `comenq` queue, local LLM mock testing
with VidaiMock, and Rust test execution with cargo-nextest.

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

The post-turn quality stop hook is no longer provided here. See
<https://github.com/leynos/post-turn-quality-stop-hook> for installation,
configuration, and support.

## Shared spelling dictionary

`data/typos-oxendict-base.toml` is the shared en-GB-oxendict dictionary for the
`leynos` code estate, and this repository is its authority: every consumer
fetches it from `main` at run time. Repository-specific product names,
identifiers and quoted fixtures belong in a local `typos.local.toml` overlay
rather than the shared dictionary.

Consumers, and this repository itself, run one pinned command,
[`typos-config-builder gate`](https://github.com/leynos/typos-config-builder).
It renders `typos.toml` from the dictionary and the overlay, runs the Typos
binary it pins, and enforces the curated exact phrase corrections, such as
`hand-written` to `handwritten`, that `typos` cannot apply after tokenizing
punctuation. No repository vendors a generator or a phrase-check script.

Run the gate over this checkout with:

```bash
make spelling
```

Proposing a new estate-wide word means editing
`data/typos-oxendict-base.toml` in a pull request here. Nothing else moves: no
consumer edit, version bump, or regenerated commit is required.
`scripts/oxford_form_harvest_cli.py` gathers the Oxford-form evidence that
supports such a proposal.

## Gate recipes

The `markdownlint` and `nixie` recipes in the Makefile are each one command
that lists the files it examines, so neither pipes a producer into a checker
whose status hides the producer's. `scripts/gate_runner_cli.py` runs both gates
over the list each discovers, and fails when that list is empty, when a tool is
missing, or when the tool reports a finding. The `spelling` recipe has the same
shape: one pinned command that discovers its own files. Consumers regenerate
their recipes from this template; see
[ADR 006](docs/adr/006-fail-closed-gate-recipes.md).

## Developer guide

See the [developers' guide](docs/developers-guide.md) for repository structure,
phase-split internals, validation targets, and contribution workflow.
