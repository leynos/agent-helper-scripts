# ADR 001: System/Home Phase Split

## Status

Accepted

## Date

2026-04-26

## Context

The previous `rust-entrypoint` model had no explicit authority boundary. One
process configured repositories, installed packages, updated certificates,
changed linker behaviour, installed user-scoped toolchains, and wrote
home-directory configuration.

That made warm-cache bootstrap flows difficult to reason about. Privileged
package mutations and credential-sensitive user operations could run in the
same process, even though the system layer and `$HOME` cache have different
lifecycles, risks, and recovery paths.

## Decision

Split the bootstrap into two phase-specific entrypoints:

- `rust-entrypoint-system`
  - Owns privileged machine-layer work such as APT repositories, packages,
    certificates, and optional linker changes.
- `rust-entrypoint-home`
  - Owns user-scoped work under `$HOME`, including toolchains, helper
    checkouts, shell profile updates, skills, hooks, and agent configuration.

Keep `rust-entrypoint` as the compatibility wrapper and dispatch through
`RUST_ENTRYPOINT_PHASE`.

## Consequences

The system phase can be run and cached at the image or system layer without
intentionally mutating the durable home checkout. The home phase can run during
warm-cache creation or restore without re-acquiring privileges or touching APT
state.

The split also makes boundary checks meaningful: home-phase scripts must avoid
APT, `/etc`, `/usr`, linker mutation, and privilege-escalation side effects.
