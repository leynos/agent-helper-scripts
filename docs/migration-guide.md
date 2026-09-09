# Migration Guide

This guide records migrations that change how the helper scripts and skills
in this repository behave, and what to do about work produced under the
previous behaviour.

## Bootstrap phases

Moving from the previous single-phase `rust-entrypoint` bootstrap to the
phase-aware bootstrap model.

### Previous model

The previous bootstrap model ran everything inline through one
`rust-entrypoint` invocation. A single run configured package repositories,
installed APT packages, updated certificates, prepared `$HOME`, installed user
toolchains, cloned helper scripts, and wrote user-level configuration.

That worked for one-shot environments, but it mixed privileged system mutation
with warm-cache-friendly home-directory work.

### New model

The new model keeps `rust-entrypoint` as the public entrypoint, but it
dispatches to phase-specific scripts according to `RUST_ENTRYPOINT_PHASE`.

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

The system phase is intended for fresh or reset system layers. The home phase
is intended for durable user-home setup, including warm-cache creation and
refresh.

### Backward compatibility

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

### Transition examples

Run only the system phase when building or refreshing a CI image layer that
does not preserve `$HOME`:

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

## Debugging plan filenames

The [`hypothesis-debugging`](../skills/hypothesis-debugging/SKILL.md) skill
previously wrote its output to `docs/debugging/debugging-plan-{timestamp}.md`.
It now writes `debugging-plan-<year>-<month>-<day>-<problem-slug>.md`, for
example `debugging-plan-2026-08-20-acp-skill-agent-menu.md`.

The output directory is unchanged, so nothing needs moving. Existing plans keep
working where they are; the skill only governs the names it writes from now on.

Rename older plans opportunistically, when you next touch one, by replacing the
timestamp with the date the plan was written and a short lower-case,
hyphen-separated slug naming the problem it investigates:

```bash
git mv docs/debugging/debugging-plan-1755710308.md \
  docs/debugging/debugging-plan-2026-08-20-acp-skill-agent-menu.md
```

Update any links to the old filename in the same commit. A bulk rename is not
required, because the date and slug must come from the plan's contents rather
than from its timestamp.

## CodeRabbit review skill

This repository now ships the
[`comenq-coderabbit`](../skills/comenq-coderabbit/SKILL.md) skill, which
documents the queue-based CodeRabbit review workflow and its recovery
procedures. `install-skills` copies every immediate skill directory into the
agent skill paths, so a deployment that already installs an independently
maintained copy of the same name has two candidates for one skill name.

Choose one authoritative version before rollout, compare the copies, and keep
approved connection and identity settings in deployment configuration. Do not
rely on installer ordering to combine two different copies.
