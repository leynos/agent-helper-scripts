# Roadmap

## Completed

- [x] Split bootstrap into system and home phases (PR `#10`)
- [x] Centralize shared logic into `bootstrap-common`
- [x] Opt-in tracing via `WITH_TRACE`
- [x] Sentinel-balance validation in `replace_managed_block`
- [x] Unified `apt_lists_exist` across `add-repositories` and
  `apt-update-if-stale`
- [x] Eliminate ambient `SUDO` global; use `_detect_sudo()`

## Planned

- [ ] Property-based tests (Hypothesis) for idempotency and sentinel
  invariants
- [ ] Snapshot tests (syrupy) for TOML and execution-log output
- [ ] `flock`-based serialization for `append_block_if_missing` and
  `clone_or_update_helper_tools_repo`
- [ ] Structured observability at phase transition points
- [ ] Formal adapter layer separating git/filesystem from domain logic
