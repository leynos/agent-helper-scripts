# v0.3.0 Migration Guide (Unreleased)

This guide records migrations that change how the helper scripts and skills
in this repository behave, and what to do about work produced under the
previous behaviour. It documents changes staged for the next release and is
not yet published as a tagged version.

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
uvx --from "git+https://github.com/leynos/typos-config-builder.git@v0.1.0" \
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
   only as a convenience snapshot that CI never checks for drift.
4. Add `.typos-oxendict-base.toml` and `.typos-oxendict-base.json` to
   `.gitignore`; `gate` writes them as its own cache, and neither is source.
5. Run `gate` once to regenerate.

### Backward compatibility

This rollout is staged, not complete. As of 2026-09-14 no consumer has
migrated yet. Twenty-eight repositories invoke the builder pinned to a
commit, alongside their own phrase-check script; thirty-six still run a
vendored copy of this repository's generator, which receives dictionary
updates but enforces no phrase corrections. Until a repository migrates, it
keeps that legacy tooling. Migration order and status are tracked in
`docs/execplans/audit-missing-functionality.md` in
`leynos/typos-config-builder`.
