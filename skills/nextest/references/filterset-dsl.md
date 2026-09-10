# Filterset Domain-Specific Language (DSL) Reference

Filtersets are specified with `-E` or `--filterset` on the command line, and
in configuration (e.g., `filter` in overrides, `default-filter`).

For the version of this reference that matches the installed binary exactly,
run `cargo nextest help filterset` (since 0.9.140; `filtersets` is an accepted
alias).

## Predicates

| Predicate | Description | Default matcher |
|-----------|-------------|-----------------|
| `all()` | All tests | — |
| `none()` | No tests | — |
| `test(m)` | Tests matching `m` | Contains (`~`) |
| `package(m)` | Tests in packages matching `m` | Glob (`#`) |
| `deps(m)` | Package + transitive dependencies | Glob (`#`) |
| `rdeps(m)` | Package + reverse transitive deps | Glob (`#`) |
| `binary_id(m)` | By binary ID | Glob (`#`) |
| `kind(m)` | By binary kind | Equality (`=`) |
| `binary(m)` | By binary name | Glob (`#`) |
| `platform(host\|target)` | By build platform | Equality (`=`) |
| `default()` | The configured default filter | — |

## Name Matchers

| Prefix | Type | Example |
|--------|------|---------|
| (none) | Default for predicate | `test(foo)` |
| `=` | Exact match | `test(=my_mod::my_test)` |
| `~` | Contains | `package(~serde)` |
| `/regex/` | Regex (matches any part) | `test(/^test_init/)` |
| `#` | Glob | `package(#my-*)` |

**When constructing expressions programmatically, always use a prefix.**

## Operators

Precedence (highest to lowest):

1. `()` — grouping
2. `not`, `!` — negation
3. `and`, `&`, `-` — intersection / difference
4. `or`, `|`, `+` — union

All operators within a group bind left-to-right.

## Token Boundaries

Since 0.9.137, a closing `)` is a token boundary, so these all parse without
an intervening space:

```text
not(test(foo))
all()and(test(foo))
all()or(test(foo))
```

Before 0.9.137 the same expressions had to be written `not (test(foo))`,
`all() and (test(foo))`, and `all() or (test(foo))`. No syntax was removed,
so the spaced forms still parse on every version; prefer them in shared
configuration and in any expression that CI may evaluate on an older
nextest. Anchored expressions such as `all()and(...)` will fail to parse on
pre-0.9.137 releases.

## Escape Sequences (equality, contains, glob matchers)

`\n` (newline), `\r` (carriage return), `\t` (tab), `\\` (backslash),
`\/` (forward slash), `\)` (close paren), `\,` (comma),
`\u{7FFF}` (Unicode code point, up to 6 hex digits).

For glob matchers, escape metacharacters with square brackets: `[*]`, `[?]`.

Regex matchers use standard regex crate escapes plus `\/`.

## Binary Kinds

Used with `kind()`: `lib`, `test`, `bench`, `proc-macro`, `bin`, `example`.

## Examples

```text
# All tests in a crate and its dependencies
deps(my-crate)

# Tests matching "deserialize" in the "serde" package
package(serde) and test(deserialize)

# All tests NOT matching a pattern
not test(/parse[0-9]*/)

# Tests in packages starting with "nextest" and their reverse deps
rdeps(nextest*)

# Cross-compilation: only host-platform tests
platform(host)

# Complex: integration tests in a specific package, excluding slow ones
package(=my-app) and kind(test) - test(slow_)
```

## Interaction with Default Filter

- CLI filtersets are intersected with `default-filter`
- Use `--ignore-default-filter` to bypass
- Config filtersets (overrides, default-filter itself) do NOT auto-intersect
- The `default()` predicate explicitly references the default filter

## Interaction with Substring Filters

If both filtersets and substring filters are given, tests must match BOTH:
the union of filtersets is intersected with the union of substring filters.

```bash
# Tests in package foo matching either test_bar or test_baz
cargo nextest run -E 'package(foo)' -- test_bar test_baz
```

## Filtered-Out Tests Are Not Failures

A test excluded by a filterset is not reported at all by default. If you need
to see what was excluded — for example to confirm a filterset is not hiding
real tests — set `report-skipped = "all"` in the JUnit profile config (since
0.9.143) rather than inferring it from an empty run.
