# v0.3.0 Migration Guide (Unreleased)

This guide records migrations that change how the helper scripts and skills
in this repository behave, and what to do about work produced under the
previous behaviour. It documents changes staged for the next release and is
not yet published as a tagged version.

## Repository scratch sidecars

The `scratch` skill standardizes repository-specific experiments, recovery
artefacts, evidence and reproducible caches in a `<repository>.scratch` sidecar.
Linked Git worktrees remain in the separate `<repository>.worktrees` sidecar;
system temporary storage remains for short-lived process scratch. The
authoritative categories, `scratch.toml` contract, retention rules and
cleanup checks are in the
[scratch layout contract](../skills/scratch/references/layout.md).

### Migrating a flat projects directory

Inventory the projects directory and classify registered worktrees separately
from standalone repositories, directories, symlinks and files. Move related
scratch artefacts into a task directory under the matching category in
`<repository>.scratch`, add `scratch.toml`, and verify paths recorded in
patches, receipts and scripts. Keep registered worktrees under
`<repository>.worktrees`.
Migration is not mandatory immediately when the existing flat layout remains
usable; migrate before cleanup or when adopting the sidecar conventions.

## Shared spelling consumption

Moving from a vendored generator and phrase-check script to the pinned
`typos-config-builder gate` command.

### Previous model

A consumer vendored `scripts/generate_typos_config.py` alongside the
`typos_rollout*.py` modules, fetching `data/typos-oxendict-base.toml` from
this repository's `main`. The consumer tracked the generated `typos.toml`
and ran its own repository-local phrase-check script over Git-tracked text.

### New model

A consumer runs `typos-config-builder gate`, pinned to a released tag:

```bash
uvx --from "git+https://github.com/leynos/typos-config-builder.git@v0.1.1" \
  typos-config-builder gate
```

`gate` fetches the shared dictionary live from this repository's `main`,
merges the consumer's optional `typos.local.toml` overlay, rewrites
`typos.toml` on every run, runs the pinned `typos` binary, and enforces the
shared phrase corrections. The fetched dictionary is cached in ignored
`.typos-oxendict-base.toml`, with freshness metadata in
`.typos-oxendict-base.json`, so a valid cache still supports offline runs.

### Migrating an existing consumer

1. Delete the vendored generator and phrase-check scripts, and their tests.
2. Replace the repository's spelling Makefile targets with the single
   `gate` call.
3. Decide whether `typos.toml` stays tracked. Either untrack it — add it to
   `.gitignore` and run `git rm --cached typos.toml` — or keep it tracked
   only as a convenience snapshot that continuous integration never checks
   for drift. This repository (agent-helper-scripts) keeps it tracked
   because it curates the shared dictionary the snapshot is rendered from.
4. Add `.typos-oxendict-base.toml` and `.typos-oxendict-base.json` to
   `.gitignore`; `gate` writes both files as cache files, and neither is
   a policy source.
5. Run `gate` once to regenerate.

### This repository

As of 2026-09-16 the generator is gone from here too. The
`scripts/typos_rollout*.py` modules and their tests are deleted, and
`make spelling` runs the pinned `gate` command against this checkout's own
`data/typos-oxendict-base.toml` with `--scope all`. A repository that copied
those scripts should migrate rather than keep a copy: nothing here maintains
them any longer.

`scripts/oxford_form_harvest_cli.py` remains, because proposing a new shared
word still starts from evidence. It is a curation tool for this repository,
not something a consumer runs.

### Backward compatibility

This rollout is staged, not complete. Migration order and status are tracked
in `docs/execplans/audit-missing-functionality.md` in
`leynos/typos-config-builder`. Until a repository migrates, it keeps its
legacy tooling, which receives dictionary updates but enforces no phrase
corrections.
