# ADR 003 — Shared Oxford spelling base

**Status:** Accepted **Date:** 2026-07-10

## Context

Repositories in the `leynos` estate need consistent en-GB-oxendict spelling. The
`typos` `en-gb` locale enforces British `-our` and `-yse` forms, but prefers
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

Store punctuation-separated corrections in a distinct shared phrase table.
Because Typos splits a form such as `hand-written` into two valid word tokens,
the spelling gate runs a small companion check over Git-tracked UTF-8 text.
That check applies the merged ignore spans and file exclusions, then reports
the exact source location and canonical replacement. Typos remains the general
dictionary engine; the companion exists only for curated phrases that its
tokenizer cannot represent.

Consumers refresh the shared base into ignored `.typos-oxendict-base.toml`,
with source identity and freshness validators in `.typos-oxendict-base.json`.
Refreshes validate content before atomic replacement, preserve a valid cache
when its authority is not newer, and allow explicit offline reuse. Generated
configuration remains tracked so review and CI can detect drift.

Treat source identity as part of cache validity. Conditional validators, stale
fallback, and HTTP `304 Not Modified` reuse require metadata for the exact
requested local path or HTTPS URL. Refresh decisions use bounded structured
logging fields and never expose source or repository paths.

Split the implementation by policy boundary while retaining
`typos_rollout.py` as the stable facade. Dedicated modules own regular
expression policy, cache persistence, HTTP refresh, deterministic rendering,
phrase checking, and harvesting. Every source module remains below 400 lines.

Validate ignore expressions before repository scanning. Reject malformed
expressions, backreferences, and compounded repetition, including Python's
`{,n}` form, while accepting repetitions separated by ordinary atoms. Exercise
the complete brace-quantifier grammar and safe separators with Hypothesis.

Phrase checking and harvesting skip only non-UTF-8 tracked content. Other file
read failures propagate after a bounded structured diagnostic, preventing a
partial scan from being reported as successful.

## Consequences

**Positives:**

- Generic Oxford knowledge is curated once and reused consistently.
- Local exceptions remain narrow and cannot silently weaken conflicting shared
  corrections.
- Conditional refreshes avoid unnecessary downloads and retain offline use.
- Deterministic rendering, TOML parsing, drift checks, and a real-binary smoke
  test make the generated boundary reviewable.
- Exact phrase corrections remain shared and enforceable despite Typos token
  boundaries.
- Source-scoped cache decisions prevent validators or stale content crossing
  authority boundaries.
- Bounded regex validation limits backtracking risk before repository scans.
- Module ownership and generated property tests make the policy easier to
  review without weakening the facade contract.
- Structured diagnostics explain refresh and read decisions without disclosing
  unbounded source or path values.

**Costs and trade-offs:**

- Consumers carry a small generator and tracked generated configuration.
- Consumers run one additional tracked-text pass for the small curated phrase
  table.
- Non-UTF-8 tracked files are intentionally omitted, while all other read
  failures now fail the spelling operation.
- A fresh consumer needs its shared source once before offline generation.
- Curators must inspect harvested context because suffix matches alone include
  genuine `-ise` words and identifiers that are not Oxford stems.
