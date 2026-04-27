# Migration Guide

This guide explains how to move from the previous single-phase
`rust-entrypoint` bootstrap to the phase-aware bootstrap model.

## Previous model

The previous bootstrap model ran everything inline through one
`rust-entrypoint` invocation. A single run configured package repositories,
installed APT packages, updated certificates, prepared `$HOME`, installed user
toolchains, cloned helper scripts, and wrote user-level configuration.

That worked for one-shot environments, but it mixed privileged system mutation
with warm-cache-friendly home-directory work.

## New model

The new model keeps `rust-entrypoint` as the public entrypoint, but it dispatches
to phase-specific scripts according to `RUST_ENTRYPOINT_PHASE`.

- `system`
  - Runs privileged machine-layer work.
  - Configures APT sources and third-party repositories.
  - Installs APT packages.
  - Updates certificates.
  - Applies optional global changes such as the `mold` linker override.
- `home`
  - Runs user-scoped work under `$HOME`.
  - Installs user toolchains and helper utilities.
  - Manages the helper checkout.
  - Writes shell profile snippets, skills, hooks, and agent configuration.

The system phase is intended for fresh or reset system layers. The home phase is
intended for durable user-home setup, including warm-cache creation and refresh.

## Backward compatibility

`RUST_ENTRYPOINT_PHASE=both` preserves the previous sequential behaviour by
running the system phase first and the home phase second.

`both` is the default, so existing one-shot calls continue to work:

```bash
bash rust-entrypoint
```

The explicit equivalent is:

```bash
RUST_ENTRYPOINT_PHASE=both bash rust-entrypoint
```

## Transition examples

Run only the system phase when building or refreshing a CI image layer that does
not preserve `$HOME`:

```bash
RUST_ENTRYPOINT_PHASE=system bash rust-entrypoint
```

Run only the home phase after restoring or creating a warm `$HOME` cache:

```bash
RUST_ENTRYPOINT_PHASE=home bash rust-entrypoint
```

A typical warm-cache pipeline runs the phases at different lifecycle points:

```bash
# Fresh system layer or CI image setup.
RUST_ENTRYPOINT_PHASE=system bash rust-entrypoint

# Warm home-cache creation or refresh step.
RUST_ENTRYPOINT_PHASE=home bash rust-entrypoint
```

The home phase expects the system phase to have installed the shared libraries,
APT packages, certificates, and other machine-level prerequisites required by
the tools under `$HOME`.
