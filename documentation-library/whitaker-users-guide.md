# Whitaker User's Guide

Whitaker is a collection of opinionated Dylint lints for Rust. This guide
explains how to integrate the lints into a project and configure them.

For contributors who want to develop new lints or work on Whitaker itself, see
Whitaker's own developer's guide.

## Quick Setup

### Prerequisites

Install `cargo-dylint` and `dylint-link`:

```sh
cargo install cargo-dylint dylint-link
```

The published `whitaker-installer` crate requires Rust 1.85 or newer. This is
the first stable compiler that supports the Rust 2024 edition used by the
installer.

Published x86_64 GNU/Linux installer, dependency, and lint artefacts target the
Ubuntu 22.04 `GLIBC_2.35` baseline and do not require a newer glibc version. On
an incompatible system, build Whitaker and its dependencies from source instead
of using the published Linux artefacts.

### Standalone installation (recommended)

The simplest way to use Whitaker is via the standalone installer, which handles
setup automatically:

```sh
cargo install whitaker-installer
whitaker-installer
whitaker --all
```

This:

1. Installs `cargo-dylint` and `dylint-link` if not present
   The installer first attempts to download pre-built dependency binaries from
   Whitaker's GitHub Releases page for the current platform. If the release
   asset is absent (HTTP 404 or 410), the installer skips `cargo binstall` and
   falls back directly to building from source with `cargo install`, pinned to
   the version recorded in the dependency manifest. If the release asset is
   present but the download fails for another reason, the installer falls back
   to `cargo binstall` when available and then to `cargo install`. When the
   source-build path is taken, the installer reports that it is falling back to
   Cargo, and on success it prints
   `Installed <tool> from source with cargo install.`. After installation,
   `cargo-dylint` is verified by running `cargo dylint --version`.
   `dylint-link` is never executed: it is a linker wrapper that forwards its
   arguments to the underlying linker, so it has no reliable self-reporting
   subcommand. A release artefact is trusted once its checksum, extraction, and
   executable permissions have been established, and a Cargo-managed copy is
   checked by resolving it on `PATH` and comparing the version Cargo recorded.
2. Clones the Whitaker repository to a platform-specific data directory
3. Builds the lint libraries
4. Creates `whitaker` and `whitaker-ls` wrapper scripts. `whitaker` invokes
   `cargo dylint` with the correct `DYLINT_LIBRARY_PATH`, and `whitaker-ls`
   lists installed Whitaker suite libraries
5. Ensures the pinned Rust toolchain and components are installed via rustup

After installation, run `whitaker --all` in any Rust project to lint it. Use
`whitaker-ls` to list the installed Whitaker suite libraries.

On Windows, the installer's `PATH` check honours `PATHEXT` and falls back to
the usual executable suffixes when `PATHEXT` is unset, so a normal
Cargo-installed executable such as `dylint-link.exe` in
`%USERPROFILE%\.cargo\bin` is located correctly and then matched against the
version Cargo recorded for it, without needing a separate wrapper or manual
environment-variable workaround.

**Options:**

- `--cranelift` — Tell the installer to add the
  `rustc-codegen-cranelift` component via `rustup component add`. The
  `rustc-codegen-cranelift` component is not included in the standard nightly
  toolchain, so enable `--cranelift` when a project or CI pipeline requires the
  Cranelift back-end and would otherwise need an explicit
  `rustc-codegen-cranelift` component-add step before running the installer.
- `--skip-deps` — Skip `cargo-dylint`/`dylint-link` installation check
- `--skip-wrapper` — Skip wrapper script generation (prints
  `DYLINT_LIBRARY_PATH` instructions instead)
- `--no-update` — Don't update existing repository clone
- `--suite-version REF` (alias `--suite-ref`) — Build the lint suite from a
  given tag, branch or commit rather than from the default branch tip. See
  [Pinning the lint suite](#pinning-the-lint-suite)
- `--no-source-fallback` — Fail rather than build from source when a published
  artefact is absent. See [Refusing a source build](#refusing-a-source-build)

### Adding Whitaker to a project

Add the following to the workspace `Cargo.toml`:

```toml
[workspace.metadata.dylint]
libraries = [
  { git = "https://github.com/leynos/whitaker", pattern = "whitaker_suite" }
]
```

Then run the lints:

```sh
cargo dylint --all
```

### Pinning the lint suite

The installer builds the suite from a Whitaker checkout. Without a pin it uses
whatever is at the default branch tip, so a change to that branch alters lint
results with no commit in the consuming repository: a gate can turn red on a
branch that has not been touched. `--suite-version` names the reference to
build from instead, so a suite change arrives as a reviewed bump.

```sh
whitaker-installer --suite-version v0.2.7
```

It accepts a tag, a branch or a commit, and the installer hands it to `git` to
resolve.

Two consequences are worth knowing before pinning.

**A pinned suite is built from source.** Prebuilt lint libraries are published
only for the branch tip, under the `rolling` tag, so a pin can never be served
from them; the installer does not attempt the download at all when a pin is
set, and compiles the suite locally instead. Pinning trades install time for
reproducibility, and that is the whole of the trade: a pinned lane is slower on
a cold cache and does not change what it produces.

The prebuilt path would not help a pin even if artefacts existed for every tag.
A lint library must be built with the exact toolchain that will load it, and
artefacts are named for the toolchain they were built with, so a pin held
against a newer `rust-toolchain.toml` misses and builds from source anyway. The
guarantee a pin buys is reproducibility, not speed.

**A pin cannot be applied from inside a Whitaker checkout.** Checking out a
reference there would move the working tree, so the installer refuses and says
so. Run it from another directory, where it manages its own clone, or check out
the reference directly.

Pinning the installer and pinning the suite are separate decisions. The
installer's version selects the tool; `--suite-version` selects the lints it
builds.

### Version pinning through Cargo metadata

When Dylint is driven directly rather than through the installer, pin to a
specific release tag or commit:

```toml
[workspace.metadata.dylint]
libraries = [
  { git = "https://github.com/leynos/whitaker", pattern = "whitaker_suite", tag = "v0.1.0" }
]
```

Or pin to a specific commit:

```toml
[workspace.metadata.dylint]
libraries = [
  { git = "https://github.com/leynos/whitaker", pattern = "whitaker_suite", rev = "abc123def456" }
]
```

### Rolling release downloads

Whitaker publishes a `rolling` pre-release tag that is continuously updated and
overwritten on every push to `main`. It is intended for early adopters who want
the latest available build outputs before the next stable release is cut.

Rolling releases are best-effort builds. If some matrix legs fail, Whitaker
still publishes the artefacts that were built successfully. For example, a
target-specific `cargo-dylint` archive may be missing from one rolling release
even though other target archives were updated successfully. Do not assume that
every supported target is present in every rolling release.

Stable releases differ from `rolling`: a stable tag is expected to contain the
complete artefact set for the release. For production installs, pin to a stable
release tag rather than consuming `rolling`.

Scripts or CI pipelines that consume rolling-release archives should verify
that the required target archive exists before proceeding. Treat missing
archives as an expected condition for rolling releases rather than assuming the
artefact set is complete.

### Refusing a source build

The installer prefers published binaries and falls back to building from source
when one is missing: a prebuilt lint library becomes a local compilation, and a
Dylint tool archive becomes `cargo install`. Both succeed, which is the
difficulty. A run that took either reports success while having built something
nobody pinned, and the only sign is a line in the log.

`--no-source-fallback`, or `WHITAKER_NO_SOURCE_FALLBACK` in the environment for
callers that cannot easily add a flag, turns each fallback into an error naming
the artefact and why it could not be fetched:

```sh
whitaker-installer --no-source-fallback
```

Any value other than an empty string, `0` or `false` enables the rule. The
comparison ignores case and surrounding whitespace, so `FALSE` and ` false `
also turn it off. Exporting the variable at all expresses an intention, and
reading an unrecognized value as off would quietly remove a protection; a value
that is not valid text enables the rule for the same reason.

The flag is rejected alongside `--build-only`, `--experimental` and
`--suite-version`. Each of those requires a source build, so combining them is
a contradiction rather than a preference, and the installer says so instead of
silently preferring one.

Each installation that selects a suite source prints the path it took on
standard output. A dry run selects none, so it prints nothing:

```text
whitaker-installer: suite-source=prebuilt
```

The value is `prebuilt` or `source`. It reports where the suite came from and
adds to the existing checks rather than replacing them: `install-whitaker`
still scans the installer's standard error for the fallback notice and fails an
unapproved source build on what it finds there. Reading only the marker would
let a source build the marker missed pass as `prebuilt`.

The streams are separate on purpose. The marker is the only thing on standard
output, so it can be parsed; the fallback notice and every other diagnostic go
to standard error.

The rolling release is the reason this exists. It is republished on every push
to `main`, and a consumer whose install starts during a republish can miss an
archive that is present moments later. In CI a source build is a defect rather
than a degraded mode, so fail and retry rather than proceeding.

### Selecting individual lints

To load specific lints instead of the full suite, specify each lint explicitly:

```toml
[workspace.metadata.dylint]
libraries = [
  { git = "https://github.com/leynos/whitaker", pattern = "crates/module_max_lines" },
  { git = "https://github.com/leynos/whitaker", pattern = "crates/no_expect_outside_tests" }
]
```

### Standard vs Experimental Lints

Whitaker lints are divided into two categories:

- **Standard lints** are stable, well-tested, and included in the default suite.
  They are recommended for general use and have predictable behaviour.
- **Experimental lints** are newer or more aggressive checks that may produce
  false positives or undergo breaking changes between releases. They must be
  explicitly enabled.

The default `whitaker_suite` pattern includes only standard lints. Whitaker
currently ships one experimental lint, `rstest_helper_should_be_fixture`, which
is available only when experimental lints are enabled.

### Enabling experimental lints

#### Via standalone installer

```sh
whitaker-installer --experimental
```

This enables experimental suite features when building `whitaker_suite`. To
build experimental lints as individual libraries, combine it with
`--individual-lints`. Explicit `--lint` requests for experimental lints also
require `--experimental`; without that opt-in the installer rejects the request
before building anything.

## Lint Configuration

Configure lint behaviour in `dylint.toml` at the workspace root:

```toml
# Diagnostic language (default: en-GB)
locale = "cy"

# Module size threshold (default: 400)
[module_max_lines]
max_lines = 500

# Conditional branch limit (default: 2)
[conditional_max_n_branches]
max_branches = 3

# Custom test attributes
[no_expect_outside_tests]
additional_test_attributes = ["my_framework::test", "wasm_bindgen_test"]

# Additional test markers for `test_must_not_have_example`
[test_must_not_have_example]
additional_test_attributes = ["actix_rt::test", "my_framework::test"]

# Allow panics in main
[no_unwrap_or_else_panic]
allow_in_main = true

# Experimental rstest fixture extraction lint
[rstest_helper_should_be_fixture]
min_calls = 2
min_distinct_tests = 2
require_identical_fixture_arg_names = false
provider_param_attributes = ["case", "values", "files", "future", "context"]
use_source_callee_fallback = false
```

## Localized Diagnostics

Whitaker supports multiple languages for diagnostic messages. Set the locale
via the `DYLINT_LOCALE` environment variable or in `dylint.toml`:

```toml
locale = "cy"
```

Available locales:

- `en-GB` (default) - English
- `cy` - Welsh (Cymraeg)
- `gd` - Scottish Gaelic (Gàidhlig)

______________________________________________________________________

## Available Lints

### `bumpy_road_function`

#### Purpose <!-- bumpy_road_function -->

Detects functions with multiple distinct clusters of nested conditional
complexity.

#### Scope and behaviour <!-- bumpy_road_function -->

Flags a function when peak detection finds two or more separated complexity
regions above the configured threshold. Detection smooths the local complexity
signal with the configured `window` and only considers peaks spanning at least
`min_bump_lines`.

The default threshold was lowered from 3.0 to 2.5 to detect bumpy road patterns
in match expressions with nested conditionals. The moving-average smoothing
(window=3) reduces raw peaks by approximately 15–20%, so a threshold of 3.0 can
mask genuine two-bump patterns in match arms with nested `if` guards.

#### Configuration <!-- bumpy_road_function -->

```toml
[bumpy_road_function]
threshold = 2.5  # Raise to 3.0 or higher to reduce false positives
window = 3
min_bump_lines = 2
```

#### What is allowed <!-- bumpy_road_function -->

- A single complexity peak in a function.
- Simple predicates that remain below the configured threshold.

#### What is denied <!-- bumpy_road_function -->

- Two or more separated complexity peaks above the configured threshold.

#### How to fix <!-- bumpy_road_function -->

Split complex regions into helper functions and simplify branch-heavy
predicates.

______________________________________________________________________

### `conditional_max_n_branches`

Limits the complexity of conditional predicates by enforcing a maximum number
of boolean branches.

**Configuration:**

```toml
[conditional_max_n_branches]
max_branches = 2
```

The default threshold is 2 branches. A predicate like `a && b && c` has three
branches and would trigger the lint.

**How to fix:** Extract complex conditions into helper functions:

```rust
// Before: Too many branches
if condition_a && condition_b && condition_c {
    // action
}

// After: Extract to helper function
fn should_proceed() -> bool {
    condition_a && condition_b && condition_c
}

if should_proceed() {
    // action
}
```

______________________________________________________________________

### `function_attrs_follow_docs`

#### Purpose

Ensures doc comments appear before other outer attributes on functions,
methods, and trait methods.

#### Scope and behaviour

When attributes are generated or reordered by a procedural macro (for example,
`rstest` or `derive`), the lint recovers the original source span from the
macro expansion chain. Attributes whose spans cannot be traced back to any
user-written source location (macro-only glue) are silently excluded from the
ordering check, so the lint never fires on compiler- or macro-generated code
that the developer cannot edit.

#### Configuration

`function_attrs_follow_docs` has no configuration knobs.

#### What is allowed

- Doc comments that appear before every other outer attribute on the same
  function, method, or trait method.
- Macro-generated attributes whose spans are excluded because they are
  macro-only.
- Inner attributes, which are outside the lint's scope.

#### What is denied

- Outer attributes that appear before a doc comment on the same function,
  method, or trait method.
- Macro-expanded attributes that recover to a user-editable source span and
  sort before the doc comment.

#### How to fix

Move doc comments so they appear before other outer attributes:

```rust
// Wrong
#[inline]
/// This function does something.
fn example() {}

// Correct
/// This function does something.
#[inline]
fn example() {}
```

With `rstest`, place the doc comment before all attributes, including the test
annotation:

```rust
// Wrong
#[rstest]
#[case(1, 2, 3)]
/// Verifies addition.
fn adds(#[case] a: i32, #[case] b: i32, #[case] expected: i32) {
    assert_eq!(a + b, expected);
}

// Correct
/// Verifies addition.
#[rstest]
#[case(1, 2, 3)]
fn adds(#[case] a: i32, #[case] b: i32, #[case] expected: i32) {
    assert_eq!(a + b, expected);
}
```

______________________________________________________________________

### `module_max_lines`

Warns when modules exceed a configurable line count threshold.

**Configuration:**

```toml
[module_max_lines]
max_lines = 400
```

**How to fix:** Split large modules into smaller, focused submodules.

______________________________________________________________________

### `module_must_have_inner_docs`

Enforces that every module begins with an inner documentation comment (`//!`).

**How to fix:**

```rust
mod my_module {
    //! Explain the module's purpose here.
    pub fn value() {}
}
```

______________________________________________________________________

### `no_expect_outside_tests`

#### Purpose

Detect test attributes correctly so `no_expect_outside_tests` can allow
`.expect()` in recognized test-only code while still flagging production use.

#### Scope and behaviour

Whitaker recognizes `#[test]`, prelude-qualified `#[test]` forms,
`#[tokio::test]`, `#[async_std::test]`, `#[gpui::test]`, `#[rstest]`,
`#[rstest::rstest]`, `#[rstest_parametrize]`, `#[rstest::rstest_parametrize]`,
`#[case]`, and `#[rstest::case]` by default. The `additional_test_attributes`
setting extends that matching list with project-specific markers, so the lint
treats those annotated functions as tests too.

#### Configuration

```toml
[no_expect_outside_tests]
additional_test_attributes = ["my_framework::test", "wasm_bindgen_test"]
```

Set `additional_test_attributes` to an array of attribute paths written as
strings. Each entry should match the path Whitaker sees on the test function,
for example `my_framework::test` or `wasm_bindgen_test`.

#### Ancestor context propagation

`additional_test_attributes` now apply during ancestor context detection as
well as direct annotation matching. If a parent function is annotated with a
configured custom test attribute, Whitaker treats nested code within that
function as test context too, so `.expect()` remains allowed throughout that
ancestry chain.

```rust
// dylint.toml
// [no_expect_outside_tests]
// additional_test_attributes = ["my_framework::test"]

#[my_framework::test]
async fn my_test() {
    helper(); // allowed — ancestor is a recognized test function
}

fn helper() {
    let v: Option<u32> = Some(1);
    let _ = v.expect("value present"); // allowed — called from within test ancestry
}
```

#### What is allowed

- Default markers such as `#[test]`, `#[::test]`,
  `#[::std::prelude::v1::test]`, `#[tokio::test]`, `#[async_std::test]`,
  `#[gpui::test]`, `#[rstest]`, `#[rstest::rstest]`, `#[rstest_parametrize]`,
  `#[rstest::rstest_parametrize]`, `#[case]`, and `#[rstest::case]`
- Project-specific markers listed in `additional_test_attributes`, such as
  `#[wasm_bindgen_test]`

#### What is denied

Functions using `.expect()` will still be flagged when their test attribute is
not in Whitaker's default list and is not listed in
`additional_test_attributes`.

#### How to fix

- Add the missing test marker to `additional_test_attributes` if the function is
  genuinely part of a supported test framework
- Change the attribute usage to a recognized form such as `#[test]`,
  `#[::test]`, `#[::std::prelude::v1::test]`, `#[tokio::test]`,
  `#[async_std::test]`, `#[gpui::test]`, `#[rstest]`, `#[rstest::rstest]`,
  `#[rstest_parametrize]`, `#[rstest::rstest_parametrize]`, `#[case]`, or
  `#[rstest::case]` where appropriate
- If the function is not test-only code, replace `.expect()` with explicit error
  handling such as `?` or `map_err`

______________________________________________________________________

### `rstest_helper_should_be_fixture`

#### Purpose

Bootstraps the experimental lint that will recommend converting repeated helper
calls inside `#[rstest]` tests into injected `#[fixture]` parameters.

#### Scope and behaviour

This lint is experimental. The current implementation registers the lint, loads
configuration defaults, and passively collects local helper calls inside strict
`#[rstest]` tests, fingerprinting fixture-local, literal, `const`, and `static`
arguments for later aggregation. The lint remains diagnostic-silent: threshold
evaluation and actionable diagnostics are tracked by 8.2.3, while UI pass/fail
coverage is tracked by 8.2.4.

#### Configuration

```toml
[rstest_helper_should_be_fixture]
min_calls = 2
min_distinct_tests = 2
require_identical_fixture_arg_names = false
provider_param_attributes = ["case", "values", "files", "future", "context"]
use_source_callee_fallback = false
```

`provider_param_attributes` lists `rstest` parameter attributes that should be
treated as data providers rather than fixture-local bindings. Entries may be
written either as bare names such as `case` or qualified names such as
`rstest::case`; Whitaker normalizes them to the shared detection policy.

#### What is allowed

- Single-use helper calls inside `#[rstest]` tests
- Helper calls whose totals stay below `min_calls` or `min_distinct_tests`
- Parameter-provider uses covered by `provider_param_attributes`, such as
  `case`, `values`, `files`, `future`, and `context`

#### What is denied

When diagnostic phases are implemented, `rstest_helper_should_be_fixture` will
deny repeated non-provider helper invocations across `#[rstest]` tests when
they meet or exceed both `min_calls` and `min_distinct_tests`. The
`require_identical_fixture_arg_names` setting controls whether candidate
fixture arguments must use the same names, and `use_source_callee_fallback`
controls whether source-callsite recovery may be used for macro-expanded callee
locations.

#### How to fix

- Replace repeated helper calls with a shared `#[fixture]` parameter.
- If `require_identical_fixture_arg_names` is enabled, rename helper arguments
  so repeated calls use the same fixture argument names.
- Prefer provider attributes listed in `provider_param_attributes` for
  parameterized data inputs rather than modelling them as fixture-local helper
  calls.
- Tune `min_calls`, `min_distinct_tests`, and `use_source_callee_fallback` when
  repository conventions need stricter or looser matching.

______________________________________________________________________

### `test_must_not_have_example`

Warns when test function documentation includes example headings (for example
`# Examples`) or fenced code blocks.

**Configuration:**

```toml
[test_must_not_have_example]
additional_test_attributes = ["actix_rt::test", "my_framework::test"]
```

Use `additional_test_attributes` for frameworks not covered by default test
markers such as `#[test]`, `#[tokio::test]`, `#[async_std::test]`,
`#[gpui::test]`, and `#[rstest]`.

**How to fix:** Keep test docs focused on intent and assertions, and move
example/tutorial snippets into user-facing documentation.

```rust
// Before
#[test]
/// # Examples
/// ```rust
/// assert_eq!(sum(2, 2), 4);
/// ```
fn sums_values() { /* ... */ }

// After
#[test]
/// Verifies summation handles two positive integers.
fn sums_values() { /* ... */ }
```

______________________________________________________________________

### `no_std_fs_operations`

Enforces capability-based filesystem access by forbidding direct use of
`std::fs` operations.

**Configuration:**

```toml
[no_std_fs_operations]
excluded_crates = ["my_cli_entrypoint", "my_test_utilities"]
excluded_paths = ["my_app::legacy_io", "my_app::bin::migrate"]
```

The `excluded_crates` option allows specified crates to use `std::fs`
operations without triggering diagnostics. This is useful for:

- CLI entry points where ambient filesystem access is the intended boundary
- Test support utilities that manage fixtures with ambient access
- Build scripts or code generators that require direct filesystem operations

The `excluded_paths` option narrows an exclusion to individual modules rather
than a whole crate. Each entry is a fully qualified path anchored at the crate
identifier, and it matches on segment boundaries: `my_app::legacy_io` exempts
that module and everything nested beneath it (for example
`my_app::legacy_io::reader`), but never a sibling such as
`my_app::legacy_io_utils`. Reach for this when only a bounded corner of a crate
needs ambient filesystem access, while the rest stays under the capability
policy.

> **Note:** For both options, use Rust identifiers (underscores), not Cargo
> package names (hyphens). For example, use `my_cli_app` rather than
> `my-cli-app`, and `my_app::legacy_io` rather than `my-app::legacy_io`.
>
> **Tip:** For an ad hoc, single-site exemption that travels with the code, a
> standard `#[allow(no_std_fs_operations)]` attribute on the item or module
> also works, since the lint honours Rust's lint-level attributes.

**How to fix:** Replace `std::fs` with `cap_std`:

```rust
// Before
use std::fs;
fn read_config() -> std::io::Result<String> {
    fs::read_to_string("config.toml")
}

// After
use cap_std::fs::Dir;
use camino::Utf8Path;
fn read_config(config_dir: &Dir, path: &Utf8Path) -> std::io::Result<String> {
    config_dir.read_to_string(path)
}
```

______________________________________________________________________

### `no_unwrap_or_else_panic`

Denies panicking `unwrap_or_else` fallbacks on `Option`/`Result`, including
tests. Doctest runs remain exempt.

**Configuration:**

```toml
[no_unwrap_or_else_panic]
allow_in_main = true
```

**What is allowed:**

- Panicking `unwrap_or_else` fallbacks inside doctests
- Panicking `unwrap_or_else` fallbacks inside `main` when
  `allow_in_main = true`
- `unwrap_or_else(|| panic!("value was {:?}", value))` inside test code when
  the closure interpolates a runtime value into the panic message
- Non-panicking `unwrap_or_else` fallbacks

**What is denied:**

- `unwrap_or_else(|| panic!(..))` outside tests, subject to the standard
  denial
- `unwrap_or_else(|| panic!(..))` in tests unless the `panic!` message
  interpolates runtime values
- `unwrap_or_else(|| panic!("static message"))` in tests; use
  `.expect("static message")` instead
- `unwrap_or_else(|| value.unwrap())`

**How to fix:** Propagate errors with `?` or use `.expect()` with a clear
message if a panic is truly intended. In tests, replace
`unwrap_or_else(|| panic!("msg"))` with `.expect("msg")` for clarity and
brevity, unless the closure needs to interpolate runtime state for a more
useful diagnostic. The rule denies only closures whose `panic!` message does
not meet the interpolated-only test exception. When the closure contains a
static string literal in tests, prefer `.expect("static message")`; only
interpolated-only `panic!` fallbacks are permitted there.

## Clone Detection: AST Feature Extraction

Whitaker's experimental clone detector runs in two passes. Pass A is a token
scan over the workspace; Pass B lifts each candidate span into an abstract
syntax tree (AST) substrate that later scoring will consume. This release ships
the Pass B substrate only — it does not yet report clones (see below).

**What the substrate does.** Given a source file and a candidate byte range,
`lower_span` validates a non-empty, UTF-8-aligned `ByteSpan`, parses the
supplied source, and lowers the smallest syntax subtree that covers the span
into a parser-independent `NormalizedTree`. Working from the smallest covering
subtree keeps the representation tied to the candidate rather than the whole
file.

**Feature vectors.** From a `NormalizedTree`, extraction derives a
deterministic set of features:

- exact counts of each syntax kind;
- dyadic fixed-point depth weighting (`2^63 >> depth`), so weights halve with
  depth and collapse to zero beyond depth 63;
- production bigrams and trigrams (parent-to-child and
  grandparent-to-parent-to-child kind sequences); and
- an opaque hexadecimal canonical hash of the normalized subtree.

**Schema-versioned hashes.** Every canonical hash mixes in
`PARSER_SCHEMA_VERSION`, which is tied to the pinned parser snapshot. A
parser-schema change therefore changes every hash by design, intentionally
invalidating persisted snapshots and caches so stale AST fingerprints are never
reused across incompatible parser versions.

**Parser feature.** `whitaker_clones_core` enables its exact-pinned
`ra_ap_syntax` parser adapter through the default `parser` feature. The feature
is on by default; building the crate with it disabled makes `lower_span` return
`AstError::ParserUnavailable` instead of lowering anything.

**Not yet emitted.** Type-3 clone scoring and SARIF Run 1 emission are deferred
to roadmap item 7.3.2. This release builds and exposes the AST substrate only;
it does not score clones or emit AST-based SARIF results.

Contributors maintaining the pinned parser should follow the `ra_ap_syntax`
re-pinning runbook in Whitaker's own developer's guide.

## Agent skills

Whitaker ships an agent-facing skill under
`skills/addressing-whitaker-findings/`.
It distils the remediation patterns from adopting the suite across more than
forty repositories: what each lint expects, which fixes hold up under review,
when an exclusion is legitimate, and the traps that cost earlier adopters
rework. The skill is written for an agent rather than a human reader, and it
covers the lints described in [Available Lints](#available-lints).

The skill lives in the Whitaker repository rather than in a separate package,
so it tracks the suite as the lints change.

A skill is a directory holding a `SKILL.md` whose YAML frontmatter is an Agent
Skills manifest. The manifest `name` is the discovery name a strict loader
uses, so a manifest that omits it leaves the skill undiscoverable. Every
shipped skill directory matches its manifest `name`, so one identifier names
the skill both on disk and at the point of discovery.

Making the skill available means copying its directory into the skills
directory that an agent tool reads. For Claude Code that directory is
`~/.claude/skills/`; other tools that consume Agent Skills use their own:

```sh
git clone --depth 1 https://github.com/leynos/whitaker.git /tmp/whitaker
mkdir -p ~/.claude/skills/
cp -R /tmp/whitaker/skills/addressing-whitaker-findings ~/.claude/skills/
```

Whitaker's own lint gate validates every shipped manifest — its frontmatter,
its manifest schema, and its metadata — so a malformed manifest cannot reach a
copy taken from it.
