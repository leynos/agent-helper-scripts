---
name: nextest
description: >-
  Use when running Rust tests with cargo-nextest. Keywords: cargo nextest,
  nextest, test runner, run tests, test parallelism, test threads, flaky test,
  retry, slow test, timeout, test group, filterset, test partition, sharding,
  continuous integration (CI) testing, nextest profile, nextest config,
  .config/nextest.toml, cargo nextest run, cargo nextest list, test archive,
  JUnit, stress test, miri, test coverage, cargo-mutants, criterion, debugger,
  tracer.
---

# cargo-nextest: The Rust Test Runner

Target version: `cargo-nextest` 0.9.143. Features marked with a version are
gated on that release; check `cargo nextest --version` before relying on them.

cargo-nextest runs each test in its own process, in parallel. It builds test
binaries, queries them for tests, then executes each test individually. This
eliminates bottlenecks from long-pole tests and provides structured per-test
results. Custom test harnesses may need adaptation for this model.

## Quick Reference

### Running Tests

```bash
cargo nextest run                          # Run all tests
cargo nextest run test_name                # Run tests matching substring
cargo nextest run -p my-crate              # Run tests in a specific package
cargo nextest run --workspace              # Run all workspace tests
cargo nextest run -j 4                     # Limit to 4 concurrent tests
cargo nextest run -j 1                     # Run tests serially
cargo nextest run --no-fail-fast           # Don't stop on first failure
cargo nextest run --retries 2              # Retry failures up to 2 times
cargo nextest run --no-capture             # Show output live (serial)
cargo nextest run -P ci                    # Use the "ci" profile
```

### Listing and Selecting Tests

```bash
cargo nextest list                         # List all tests
cargo nextest list -T json-pretty          # List in JSON format
cargo nextest run -E 'package(my-crate)'   # Filterset: by package
cargo nextest run -E 'test(/regex/)'       # Filterset: by regex
cargo nextest run -E 'deps(my-crate)'      # Filterset: crate + dependencies
cargo nextest run -- --skip slow --exact test_foo  # Skip/exact matching
```

`cargo nextest list` is not guaranteed to be silent: since 0.9.143 it draws a
progress bar if listing takes longer than two seconds. Do not assume empty
output means an empty test set; parse the JSON output instead.

### CI Essentials

```bash
cargo nextest run -P ci --no-fail-fast     # CI profile, run all tests
cargo nextest run --partition slice:1/3    # Shard across 3 runners
cargo nextest archive --archive-file a.tar.zst  # Archive for reuse
cargo nextest run --archive-file a.tar.zst      # Run from archive
```

### Self-Describing Help

Since 0.9.140, nextest ships its own reference material. Prefer these over
guessing at a flag or config key, because they describe the exact build in use:

```bash
cargo nextest help                         # List available topics
cargo nextest help filterset               # alias: filtersets
cargo nextest help repo-config             # .config/nextest.toml schema
cargo nextest help user-config             # ~/.config/nextest/config.toml schema
```

The config schemas are also available as JSON for editor integration, with
stable URLs that can be referenced from `taplo.toml` or an editor's schema
settings:

```bash
cargo nextest self schema repo-config      # since 0.9.134
cargo nextest self schema user-config      # since 0.9.136
```

The repository-config schema works with Tombi and RustRover. Taplo is
explicitly unsupported because it cannot handle the schema's conditional
structure. Persistent URLs:
<https://nexte.st/schemas/repo-config.json> and
<https://nexte.st/schemas/user-config.json>.

---

## Parallelism and Thread Control

By default, nextest runs `num-cpus` tests concurrently. Control this with:

- **CLI**: `-j N` or `--test-threads N` (also `num-cpus`)
- **Env**: `NEXTEST_TEST_THREADS=N`
- **Config**: `test-threads = N` or `test-threads = "num-cpus"`

Negative values are relative to CPU count (e.g., `-2` means `num_cpus - 2`).

### Heavy tests (`threads-required`)

Mark resource-intensive tests to consume multiple thread slots:

```toml
# .config/nextest.toml
[[profile.default.overrides]]
filter = 'test(/^tests::heavy::/)'
threads-required = 2        # Each takes 2 of the thread budget

# Special values:
# threads-required = "num-cpus"          — effectively serial
# threads-required = "num-test-threads"  — monopolise all slots
```

### Test groups (mutual exclusion / rate-limiting)

Logical semaphores/mutexes for subsets of tests:

```toml
[test-groups]
serial-db = { max-threads = 1 }      # Mutex
rate-limited = { max-threads = 4 }    # Semaphore with 4 permits

[[profile.default.overrides]]
filter = 'package(db-tests)'
test-group = 'serial-db'

[[profile.default.overrides]]
filter = 'test(api_)'
test-group = 'rate-limited'
```

Inspect with `cargo nextest show-config test-groups`.

---

## Configuration

Config file: `.config/nextest.toml` in the workspace root.

### Profiles

Profiles provide named sets of options. Select with `-P <name>` or
`NEXTEST_PROFILE=<name>`.

```toml
[profile.ci]
fail-fast = false
retries = 2
```

For complete profile examples (including `profile.default` and
`profile.ci.junit` for JUnit output), see `references/ci-patterns.md`.

Profiles inherit from `default` unless `inherits` is specified.

### Hierarchical resolution

1. CLI arguments
2. Environment variables
3. Per-test overrides (in profile, then default)
4. Profile configuration
5. Default configuration

### Per-test overrides

```toml
[[profile.default.overrides]]
filter = 'test(test_e2e)'
retries = 3
slow-timeout = { period = "120s", terminate-after = 5 }
threads-required = 2
```

Overrides support: `retries`, `slow-timeout`, `leak-timeout`,
`threads-required`, `test-group`, `success-output`, `failure-output`,
`priority`, `run-extra-args`, `default-filter`, `junit.report-skipped`
(since 0.9.143).

Two override kinds exist and they are not interchangeable:

- **Per-test overrides** in `.config/nextest.toml` match against the platform
  the _tests_ run on.
- **User-config overrides** in `~/.config/nextest/config.toml` match against
  nextest's **build target** — the platform nextest itself was compiled for.
  Since 0.9.134 this is always the build target; earlier versions evaluated it
  against the host in some cases and the build target in others. If you
  cross-compile and rely on a `platform` override in the user config, this
  change can silently stop it matching.

---

## Retries and Flaky Tests

```toml
retries = 3                                              # Simple
retries = { backoff = "fixed", count = 3, delay = "1s" } # Fixed delay
retries = { backoff = "exponential", count = 4, delay = "2s", max-delay = "10s", jitter = true }
```

CLI `--retries N` and env `NEXTEST_RETRIES=N` override all config including
per-test overrides, and disable backoff delays.

A test that fails then succeeds on retry is marked **flaky** (ultimately
passes, exit code 0).

---

## Timeouts

### Slow test warnings

```toml
slow-timeout = "60s"             # Warn after 60s
```

### Terminating hung tests

```toml
slow-timeout = { period = "30s", terminate-after = 4 }
# Warns at 30s, terminates at 120s (4 x 30s)
# Grace period before SIGKILL: default 10s
slow-timeout = { period = "30s", terminate-after = 4, grace-period = "5s" }
```

### Global timeout

```toml
global-timeout = "2h"      # Entire test run must finish in 2 hours
```

### Timeout as success (fuzz tests)

```toml
[[profile.default.overrides]]
filter = 'package(fuzz-targets)'
slow-timeout = { period = "30s", terminate-after = 1, on-timeout = "pass" }
```

---

## Filtersets (Domain-specific language, DSL)

Specified with `-E` / `--filterset`. Core concepts:

- Predicates: `test(...)`, `package(...)`, `deps(...)`, `rdeps(...)`,
  `kind(...)`, `platform(...)`, `default()`
- Matchers: exact (`=`), contains (`~`), regex (`/../`), glob (`#`)
- Operators: `not`/`!`, `and`/`&`/`-`, `or`/`|`/`+` with `()` grouping
- CLI filtersets intersect with `default-filter` unless
  `--ignore-default-filter` is set

Since 0.9.137, a closing `)` counts as a token boundary, so `not(test(foo))`,
`all()and(test(foo))` and `all()or(test(foo))` all parse without a separating
space. Older versions require `not (test(foo))` and `all() and (test(foo))`.
Write the spaced form when the expression must also parse on pre-0.9.137
releases.

See `references/filterset-dsl.md` for the complete predicate table, matcher
rules, operator precedence, escape sequences, and advanced examples.

---

## Environment-Aware Configuration

### Per-platform overrides

```toml
[[profile.default.overrides]]
platform = 'cfg(target_os = "linux")'
slow-timeout = "120s"

[[profile.default.overrides]]
platform = { host = "cfg(unix)", target = "aarch64-apple-darwin" }
threads-required = 2
```

For target triples nextest has no built-in data for, it now shells out to
`rustc --print=cfg --target=<triple>` before falling back to heuristics
(since 0.9.134). This makes `platform` overrides correct for custom or very
new targets, at the cost of one `rustc` invocation.

### Agent sandbox considerations

When running inside an agent sandbox (constrained CPU/memory):

- Use `-j 2` or `-j 4` to limit parallelism
- Set generous timeouts:
  `slow-timeout = { period = "120s", terminate-after = 3 }`
- Consider `--no-fail-fast` to gather all failures in one run
- Use `--show-progress=counter` for non-interactive output
- Set `NEXTEST_NO_INPUT_HANDLER=1` to disable terminal key handling

### Continuous integration (CI) workflow overview

For production-ready profile config, sharding strategies, build/run split
archives, and full GitHub/GitLab examples, see `references/ci-patterns.md`.

```bash
cargo nextest run -P ci
cargo nextest run -P ci --partition slice:1/3
cargo nextest archive --workspace --archive-file tests.tar.zst
cargo nextest run --archive-file tests.tar.zst --partition slice:1/3
```

---

## Archiving and Reusing Builds

Build once and run on multiple machines (same platform and source revision):

```bash
cargo nextest archive --archive-file tests.tar.zst
cargo nextest run --archive-file tests.tar.zst
```

Use `--workspace-remap <path>` when the checkout path differs on the target
machine. Since 0.9.138 this flag requires **both** `--cargo-metadata` and
`--binaries-metadata`; supplying it without them is now an up-front error
rather than a silent misconfiguration. The same release made
`--cargo-metadata` without `--binaries-metadata`, combined with exactly one
default workspace member, anchor the build to that member's `Cargo.toml`
instead of the whole workspace.

Since 0.9.143, `cargo nextest archive` with a filterset always includes
dynamic libraries even when the packages' test binaries are all filtered out,
and the "Archiving" message counts non-test binaries rather than packages.

See `references/ci-patterns.md` for full archive patterns, include/exclude
options, and CI artefact workflows.

---

## Stress Testing

```bash
cargo nextest run --stress-count 10 test_flaky    # Run 10 times each
cargo nextest run --stress-count infinite test_x   # Run indefinitely
cargo nextest run --stress-duration 5m test_x      # Run for 5 minutes
```

---

## Record, Replay, and Rerun (Experimental)

Enable in `~/.config/nextest/config.toml`:

```toml
[experimental]
record = true

[record]
enabled = true
```

Then:

```bash
cargo nextest run                   # Automatically recorded
cargo nextest run -R latest         # Rerun only failures
cargo nextest replay                # Replay last run's output
cargo nextest store list            # List recorded runs
cargo nextest store export latest   # Export portable recording
```

Since 0.9.134, `store export` and `store export-chrome-trace` verify the
store format version before exporting, so a recording made by an incompatible
nextest version fails loudly instead of producing a corrupt export.

---

## Test Priorities

```toml
[[profile.default.overrides]]
filter = 'test(smoke_)'
priority = 50          # Run early (range: -100 to 100, default: 0)

[[profile.default.overrides]]
filter = 'test(slow_e2e_)'
priority = -50         # Run late
```

---

## Reporter and Output Control

| Option | Values | Default |
| -------- | -------- | --------- |
| `--failure-output` | `immediate`, `final`, `immediate-final`, `never` | `immediate` |
| `--success-output` | `immediate`, `final`, `immediate-final`, `never` | `never` |
| `--status-level` | `none`, `fail`, `retry`, `slow`, `leak`, `pass`, `skip`, `all` | `pass` |
| `--final-status-level` | `none`, `fail`, `flaky`, `slow`, `skip`, `pass`, `all` | `flaky` |
| `--show-progress` | `auto`, `none`, `bar`, `counter`, `only` | `auto` |

Press `t` during a run to dump status of currently-running tests (interactive
terminals only). On macOS, Ctrl-T also works. On any Unix, send `SIGUSR1`.

### JUnit reports

```toml
[profile.ci.junit]
path = "junit.xml"
report-name = "nextest-run"
store-success-output = false
store-failure-output = true
report-skipped = "none"   # since 0.9.143: none | ignored | all
```

`report-skipped` controls whether skipped tests appear in the report. The
default `none` omits them; `ignored` includes tests skipped by `#[ignore]`;
`all` includes everything skipped, including by filterset. Use `all` only
with a single unpartitioned run: merging partitioned reports that each use
`all` produces duplicate skipped entries, because every shard reports the
tests it filtered out. It is also settable per-test through
`[[profile.<name>.overrides]]`.

---

## Setup Scripts (Experimental)

Pre-test scripts that can set environment variables for tests:

```toml
experimental = ["setup-scripts"]

[scripts.setup.db-seed]
command = 'cargo run -p seed-db'
slow-timeout = { period = "60s", terminate-after = 2 }

[[profile.default.scripts]]
filter = 'rdeps(db-tests)'
setup = 'db-seed'
```

Scripts write env vars to `$NEXTEST_ENV`:

```bash
echo "DATABASE_URL=postgres://localhost/test" >> "$NEXTEST_ENV"
```

---

## Key Environment Variables

### Nextest reads

| Variable | Purpose |
| ---------- | --------- |
| `NEXTEST_TEST_THREADS` | Override test thread count |
| `NEXTEST_RETRIES` | Override retry count |
| `NEXTEST_PROFILE` | Select profile |
| `NEXTEST_FAILURE_OUTPUT` | Override failure output mode |
| `NEXTEST_VERBOSE` | Verbose output |

### Nextest sets

| Variable | Value |
| ---------- | ------- |
| `NEXTEST` | Always `"1"` |
| `NEXTEST_RUN_ID` | UUID for the run |
| `NEXTEST_EXECUTION_MODE` | `"process-per-test"` |
| `NEXTEST_ATTEMPT` | 1-indexed attempt number |
| `NEXTEST_TEST_GROUP` | Group name or `"@global"` |
| `NEXTEST_STRESS_CURRENT` | Current stress iteration (`"none"` outside stress mode) |
| `NEXTEST_STRESS_TOTAL` | Total stress iterations (`"none"`, or `"unknown"` when no total is given) |
| `NEXTEST_TEST_THREADS` | Thread count available to the test process and setup scripts |
| `NEXTEST_BIN_EXE_<name>` | Path to binary target (integration tests) |
| `NEXTEST_BINARY_ID` | Binary ID of the current test |
| `NEXTEST_ATTEMPT_ID` | Globally unique attempt identifier |
| `NEXTEST_TEST_GLOBAL_SLOT` | Global slot number (0-indexed, unique among running tests) |
| `NEXTEST_TEST_GROUP_SLOT` | Group slot number (`"none"` if not in a group) |

Slot numbers are useful for assigning resources like port numbers to tests.
They are unique for the lifetime of the test, stable across retries, and
compact (each test gets the smallest available slot).

`NEXTEST_VERSION`, `NEXTEST_REQUIRED_VERSION`, `NEXTEST_RECOMMENDED_VERSION`,
`NEXTEST_RUN_ID`, `NEXTEST_BINARY_ID` and `NEXTEST_WORKSPACE_ROOT` are also
set during the **list** phase, not only the run phase, since 0.9.138; as of
0.9.143 the same is true of `NEXTEST_BIN_EXE_<name>`, alongside
`CARGO_BIN_EXE_<name>` (which has been set in both phases since 0.9.130).
`NEXTEST_ATTEMPT`, `NEXTEST_TEST_GROUP`, `NEXTEST_STRESS_CURRENT` and
`NEXTEST_STRESS_TOTAL` remain run-phase only, so a test that reads
`NEXTEST_ATTEMPT` in a listing context sees nothing. `NEXTEST_TEST_THREADS` is
set for test processes and setup scripts, and is also read as the
`--test-threads`/`-j` override.

### Environment safety

Because nextest runs each test in its own process, calling `std::env::set_var`
at the beginning of a test is safe provided no other thread concurrently reads
or writes the environment — which is why such mutations must happen before
spawning threads. On Rust edition 2024 the call is `unsafe` and must be
wrapped in an `unsafe` block; pre-2024 editions permit the plain call, but the
contract is unchanged.

---

## Debugger and Tracer Support

```bash
cargo nextest run --debugger "rust-gdb --args" test_name
cargo nextest run --debugger "rust-lldb --" test_name
cargo nextest run --tracer strace test_name
cargo nextest run --tracer "strace -f" test_name     # Follow child processes
```

Both modes disable timeouts and output capture, and require exactly one test
to be selected. Key differences:

- `--debugger`: Passes stdin through, disables signal handling and process
  groups (interactive debugging with gdb, lldb, WinDbg, CodeLLDB)
- `--tracer`: Null stdin, standard signal handling, process groups for
  isolation (non-interactive tracing with strace, dtruss, truss)

---

## Integrations

### Miri (undefined behaviour detection)

```bash
cargo miri nextest run
cargo miri nextest run --target mips64-unknown-linux-gnuabi64  # Cross-interpretation
```

Nextest auto-selects the `default-miri` profile under Miri. Configure it in
`.config/nextest.toml`:

```toml
[profile.default-miri]
slow-timeout = { period = "60s", terminate-after = 2 }
```

Miri tests run in parallel with nextest (Miri itself is single-threaded, so
`cargo miri test` is limited to serial execution). Archiving is not supported
under Miri.

### Test coverage

```bash
cargo llvm-cov nextest
```

Merge with doctests (nextest doesn't run doctests):

```bash
cargo llvm-cov --no-report nextest
cargo llvm-cov --no-report --doc
cargo llvm-cov report --doctests --lcov --output-path lcov.info
```

### Mutation testing (cargo-mutants)

```bash
cargo mutants --test-tool=nextest
```

Or set permanently in `.cargo/mutants.toml`:

```toml
test_tool = "nextest"
```

### Criterion benchmarks in test mode

By default, `cargo nextest run` excludes benchmarks. To verify benchmarks
compile and don't panic (single iteration, no measurement):

```bash
cargo nextest run --all-targets   # Include benchmarks
cargo nextest run --benches       # Only benchmarks
```

Requires Criterion 0.5.0+. For actual performance measurement, use the
experimental `cargo nextest bench` (requires `experimental = ["benchmarks"]`).

---

## Troubleshooting

### Tests fail under nextest but pass under `cargo test`

Nextest runs one process per test, so tests that share global state, rely on
running in the same process, or depend on `--test-threads` semantics behave
differently. Check for global statics, environment mutation, and tests that
assume they run concurrently with a sibling.

### Dynamic library load failures

Since 0.9.143 the dynamic library search path is ordered the way current
Cargo orders it: the artefact directory before `deps`. Cargo swapped those
in 1.93, and this release also fixes dylib resolution under the v2 build
directory layout (nightly default since 2026-07-30), under
`build.build-dir`, and for `[[example]]` targets, which Cargo places in
`examples` rather than `deps`. If you set `LD_LIBRARY_PATH` or `DYLD_*`
yourself around a nextest run, match that ordering or a pre-0.9.143 nextest
will disagree with a post-1.93 Cargo.

### A test is silently skipped

Check `default-filter`, any `-E` filterset, and the `report-skipped` setting
above. A test filtered out by a filterset is not a failure and does not
appear in the report unless `report-skipped = "all"`.

### `cargo nextest list` produced unexpected output

Since 0.9.143, listing draws a progress bar when it exceeds two seconds. Use
`-T json-pretty` and parse the JSON rather than parsing human-readable output.

---

## Reference

For detailed reference on specific topics, see the `references/` directory in
this skill:

- `references/config-reference.md` — Full configuration parameter reference
- `references/filterset-dsl.md` — Complete filterset DSL reference
- `references/ci-patterns.md` — CI/CD patterns for archiving, sharding, and
  GitHub Actions
