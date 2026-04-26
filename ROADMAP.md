# Roadmap

This roadmap tracks follow-up work for the phase-aware bootstrap split.

## Completed

- Split `rust-entrypoint` into system and home phases.
- Add `RUST_ENTRYPOINT_PHASE` dispatch with `system`, `home`, and `both`.
- Preserve one-shot compatibility through the default `both` phase.
- Move privileged APT, repository, certificate, and linker work into the system
  phase.
- Keep home-phase work scoped to `$HOME` toolchains, helper checkout state,
  skills, hooks, and agent configuration.
- Add Makefile targets for CI, linting, syntax checks, home-phase boundary
  checks, hook tests, and entrypoint tests.
- Add pytest coverage for phase dispatch, trace behaviour, home/system
  boundary protection, managed config updates, and APT list detection.
- Add user, developer, bootstrap, README, and migration documentation for the
  phase-split model.

## Open warnings

- Property tests
  - Expand legacy Codex config cleanup coverage with property-based generation
    for malformed, duplicated, and partially matched candidate blocks.
- Snapshot tests
  - Add snapshot coverage for generated Codex configuration and managed blocks
    so repeated home-phase runs are easier to review.
- Flock guards
  - Review remaining helper scripts for shared checkout or cache mutation that
    may need explicit filesystem locking.
- Observability
  - Add structured, non-sensitive phase progress logging for bootstrap runs so
    failures are easier to diagnose without enabling `WITH_TRACE`.
