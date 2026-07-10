# ADR 003 — Shared Oxford spelling base

**Status:** Accepted
**Date:** 2026-07-10

## Context

Repositories in the `leynos` estate need consistent en-GB-oxendict spelling.
The `typos` `en-gb` locale enforces British `-our` and `-yse` forms, but prefers
plain-British `-ise` over Oxford `-ize`. Duplicating curated overrides in every
repository would make corrections drift and would turn each newly observed
Oxford stem into many unrelated edits.

Consumers must also remain reproducible and usable after their first online
generation. Repository-specific product names, quoted APIs, and fixtures must
not become global exceptions that hide mistakes elsewhere.

## Decision

Publish `data/typos-oxendict-base.toml` as the tracked estate-wide source of
generic Oxford stems, accepted terms, ignore patterns, and file exclusions.
Generate deterministic `typos.toml` files by merging that base with a tracked
consumer `typos.local.toml` overlay. The renderer accepts Oxford inflections
and corrects corresponding plain-British `-ise` forms.

Consumers refresh the shared base into ignored `.typos-oxendict-base.toml`,
with source identity and freshness validators in
`.typos-oxendict-base.json`. Refreshes validate content before atomic
replacement, preserve a valid cache when its authority is not newer, and allow
explicit offline reuse. Generated configuration remains tracked so review and
CI can detect drift.

## Consequences

**Positives:**

- Generic Oxford knowledge is curated once and reused consistently.
- Local exceptions remain narrow and cannot silently weaken conflicting shared
  corrections.
- Conditional refreshes avoid unnecessary downloads and retain offline use.
- Deterministic rendering, TOML parsing, drift checks, and a real-binary smoke
  test make the generated boundary reviewable.

**Costs and trade-offs:**

- Consumers carry a small generator and tracked generated configuration.
- A fresh consumer needs its shared source once before offline generation.
- Curators must inspect harvested context because suffix matches alone include
  genuine `-ise` words and identifiers that are not Oxford stems.
