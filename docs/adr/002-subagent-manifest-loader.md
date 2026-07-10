# ADR 002 — Subagent manifest and loader

**Status:** Accepted
**Date:** 2026-07-06

## Context

Downstream provisioning (the `agent_tools` Ansible role) must render the same
managed subagent contracts for multiple providers — Codex CLI, Claude Code, and
goose. Each provider requires a different native configuration format, but the
underlying model choices, sandbox modes, tool grants, and load-bearing
instruction prose must remain consistent across all of them.

Without a shared source of truth, each provider's rendering can drift
independently. Hard-coding expected values inside tests creates the same
problem: a model choice or directive can be weakened in the manifest and no test
will catch the regression. Over time, this silent drift degrades the provisioned
agents in ways that are difficult to attribute to a specific change.

## Decision

Publish a single provider-neutral manifest at `agents/subagents.yml` as the
public source of truth for the managed subagent definitions. Each entry carries
a shared `description` and `instructions` body alongside per-provider blocks
that downstream tooling renders into provider-native configuration files.

Introduce a small PyYAML-backed loader helper at `tests/subagent_manifest.py`
that reads the manifest with `yaml.safe_load` and performs structural
validation. The loader's public surface (`load_subagent_entries`,
`load_subagent_entry`, `load_provider`) raises typed errors (`OSError`,
`yaml.YAMLError`, `TypeError`, `LookupError`) at every structural boundary so
that a malformed manifest fails loudly. Deployment-contract regression tests
(`tests/test_subagent_definitions.py`) source their assertions directly from the
loader so any weakening of a model choice, sandbox mode, tool grant, or
directive surfaces as a test failure. A second suite
(`tests/test_subagent_manifest.py`) exercises the loader's typed-error contract
directly.

Adopt PyYAML (`pyyaml>=6.0.3`) as a development-only dependency for this
purpose, declared in the `[dependency-groups] dev` array of `pyproject.toml`.

## Consequences

**Positives:**

- A single manifest is the authoritative source for all provider renderings;
  per-provider drift is structurally prevented.
- Tests fail loudly when a deployment contract is weakened, making regressions
  easy to attribute to a specific change.
- Typed errors from the loader localize manifest mistakes to the precise
  structural boundary that is violated.

**Costs and trade-offs:**

- A new development dependency (PyYAML) is introduced. It is not a runtime
  dependency, but it must be kept up to date alongside other dev tooling.
- The regression tests are coupled to the manifest's YAML shape and key names;
  a schema change requires updating both the manifest and the loader.
- The loader performs a degree of structural validation that a dedicated schema
  tool (for example a JSON Schema validator) could otherwise provide in a more
  declarative and maintainable form.
