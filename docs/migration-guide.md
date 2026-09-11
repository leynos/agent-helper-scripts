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

## VidaiMock skill

This repository now ships the [`vidai-mock`](../skills/vidai-mock/SKILL.md)
skill, which documents VidaiMock as a local mock server for LLM provider APIs.
It replaces the standalone `leynos/vidai-mock-skill` checkout that
`install-skills` used to clone and copy.

Deleting `~/.codex/skills/vidai-mock` and `~/.claude/skills/vidai-mock` is
required before the next `install-skills` run: the installer never deletes,
and `cp -a` merges into an existing directory, so files unique to the old
standalone copy survive the copy and leave a hybrid skill tree. Deleting the
`~/git/vidai-mock-skill` checkout is optional cleanup only, because the
installer no longer reads that path. A reinstated checkout is no longer
fetched, so deleting it is not undone by the installer.

The shipped skill is verified against `vidaimock` 0.3.1 and covers behaviour
the earlier copy did not:

- The `benchmark`, `realistic`, and `debug` run modes, and where `--latency`
  actually takes effect.
- `--config-dir` and `--isolated` for overriding or replacing the bundled
  provider and template set.
- The built-in paths `GET /health`, `GET /status`, and `POST /error/{code}`,
  alongside `GET /metrics`.
- The `X-Mock-Status` header, the `?chaos_status=` query, the
  `X-Vidai-Chaos-Disconnect` header, and the provider-shaped error envelopes
  each of them returns.
- Agentic loop termination through `has_tool_result()`, which is what lets an
  ADK, LangGraph, or LangChain loop finish instead of calling the mock
  forever.
- Provider coverage beyond OpenAI and Anthropic: Gemini, Azure OpenAI,
  Bedrock, Vertex AI, Cohere, Mistral, and Groq, plus the embeddings, images,
  moderations, and Responses endpoints.

The `get-ai-tooling` helper still downloads v0.1.2 rather than the 0.3.1
release the skill documents, so some documented commands and flags may not
be available until 0.3.1 is installed.

## Nextest skill

This repository now ships the [`nextest`](../skills/nextest/SKILL.md) skill,
which documents `cargo-nextest` as the Rust test runner. It replaces the
standalone `leynos/nextest-skill` checkout that `install-skills` used to clone
and copy.

As with the VidaiMock skill, removing the clone call in the installer was
required rather than tidy: `copy_skills` ran the external checkout after the
helper checkout's own `skills` directory, so the standalone copy won on every
run while that call remained.

Deleting `~/.codex/skills/nextest` and `~/.claude/skills/nextest` is required
before the next `install-skills` run: the installer never deletes, and `cp -a`
merges into an existing directory, so files unique to the old standalone copy
survive the copy and leave a hybrid skill tree. Deleting the
`~/git/nextest-skill` checkout is optional cleanup only, because the installer
no longer reads that path. A reinstated checkout is no longer fetched, so
deleting it is not undone by the installer.

The shipped skill is verified against `cargo-nextest` 0.9.143 and covers
behaviour the earlier copy did not:

- The version-gated surface added since 0.9.133: the `cargo nextest help`
  topics and `cargo nextest self schema` config schemas (0.9.134–0.9.140),
  and the `junit.report-skipped` setting (0.9.143).
- The `--workspace-remap` validation change, which now requires both
  `--cargo-metadata` and `--binaries-metadata` (0.9.138).
- The filterset parsing relaxation that allows `not(...)`, `all()and(...)` and
  `all()or(...)` without an intervening space (0.9.137).
- The six `NEXTEST_*` variables that are now also set during the list phase
  (0.9.138), and the user-config `platform` override semantics that now always
  match the build target (0.9.134).
- The dynamic library search path reordering that follows Cargo 1.93 (0.9.143),
  which matters for archived and cross-compiled test runs.

The skill marks every version-gated feature inline. The `get-rust-tooling`
bootstrap still installs `cargo-nextest` 0.9.133 through
`CARGO_NEXTEST_VERSION` with `cargo binstall`, so those features are
documented but not available until that variable is raised.

## Markdown lint gate

A bare `markdownlint` invocation previously forwarded its arguments with no
glob, so `markdownlint-cli2` linted zero files and reported a clean pass. It
now lints every Markdown file in the tree. A consumer repository whose CI or
hooks called it with no arguments will start reporting violations it never
saw; those violations are real and need fixing, or a rule change in that
repository's own configuration.

The wrapper prefers `markdownlint-cli2` on `PATH` and falls back to the bun
global install, so a consumer that previously relied on one provisioning
route is unaffected provided one of the two resolves.

`make markdownlint` is now part of `make ci`, so a consumer running `make ci`
from this checkout lints Markdown as part of the gate sequence.
