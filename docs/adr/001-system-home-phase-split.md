# ADR 001 — System / home phase split

**Status:** Accepted
**Date:** 2026-04-26

## Context

The original `rust-entrypoint` ran both privileged operations and user-scoped
operations in a single process. Privileged operations included APT repository
setup, APT package installation, CA certificate updates, and linker
configuration. User-scoped operations included toolchain installation, profile
wiring, and Kopia restore/snapshot work.

This made it impossible to cache the privilege-requiring layer separately from
the user-specific layer. It also created a risk of credential leakage when
tracing was enabled because credential-sensitive user operations and
privileged package mutations shared one execution path.

## Decision

Split `rust-entrypoint` into two delegate scripts:

- `rust-entrypoint-system`
  - Privileged operations that mutate machine state.
  - Runs as root or via `sudo`.
- `rust-entrypoint-home`
  - User-scoped warm mutations.
  - Must never invoke `apt-get`, invoke `sudo`, or touch system paths.

A dispatcher (`rust-entrypoint`) selects which scripts to run based on
`RUST_ENTRYPOINT_PHASE` (`system`, `home`, or `both`).

## Consequences

- The system phase can be baked into a container image layer, making home-phase
  re-runs cheap.
- The `check-home-phase-boundary` Makefile target statically enforces the
  boundary; violations in non-comment lines fail the lint gate.
- `WITH_TRACE` enables Bash xtrace only after the boundary check, so credentials
  are never unconditionally exposed.
