# Configuration Reference

Config file: `.config/nextest.toml` at the workspace root.

Validate against the schema for the installed version rather than against
these tables alone — `cargo nextest self schema repo-config` (since 0.9.134)
emits the exact JSON Schema nextest enforces, and
`cargo nextest help repo-config` (since 0.9.140) prints the annotated
reference.

## Top-level

```toml
nextest-version = "0.9.50"
# or
nextest-version = { required = "0.9.20", recommended = "0.9.30" }

experimental = ["setup-scripts", "wrapper-scripts"]

[store]
dir = "target/nextest"    # Default store directory
```

## Profile Configuration

All settings below use `profile.<name>.<key>` notation. The default profile
is `profile.default`.

### Core Test Execution

| Key | Type | Default | Description |
| ----- | ------ | --------- | ------------- |
| `inherits` | string | `"default"` | Profile to inherit from |
| `default-filter` | filterset | `"all()"` | Default set of tests to run |
| `global-timeout` | duration | none | Global timeout for entire run |
| `test-threads` | int/string | `"num-cpus"` | Number of concurrent tests |
| `threads-required` | int/string | `1` | Threads each test consumes |
| `run-extra-args` | string[] | `[]` | Extra args to test binary |

`global-timeout` is unset by default, so no global timeout is applied. The
`30y` value in the embedded configuration below is an internal fallback that
is effectively infinite (30 years, chosen to avoid duration overflows), not
the documented user-facing default.

### Retry

| Key | Type | Default | Description |
| ----- | ------ | --------- | ------------- |
| `retries` | int/object | `0` | Retry policy |

Retry object forms:

```toml
retries = 3
retries = { backoff = "fixed", count = 3, delay = "1s" }
retries = { backoff = "exponential", count = 4, delay = "2s", max-delay = "10s", jitter = true }
```

### Timeouts

| Key | Type | Default | Description |
| ----- | ------ | --------- | ------------- |
| `slow-timeout` | duration/object | `60s` | Slow test threshold |
| `leak-timeout` | duration/object | `200ms` | Leak detection threshold |

Slow-timeout object:

```toml
slow-timeout = { period = "120s", terminate-after = 2, grace-period = "10s" }
slow-timeout = { period = "30s", terminate-after = 4, on-timeout = "pass" }
```

Leak-timeout object:

```toml
leak-timeout = { period = "500ms", result = "fail" }
```

### Reporter

| Key | Type | Default | Description |
| ----- | ------ | --------- | ------------- |
| `status-level` | string | `"pass"` | Status levels to display during run |
| `final-status-level` | string | `"flaky"` | Status levels in final summary |
| `failure-output` | string | `"immediate"` | When to show failure output |
| `success-output` | string | `"never"` | When to show success output |

### Failure Handling

| Key | Type | Default | Description |
| ----- | ------ | --------- | ------------- |
| `fail-fast` | bool/object | `true` | Stop on first failure |

```toml
fail-fast = true
fail-fast = false
fail-fast = { max-fail = 5 }
fail-fast = { max-fail = 1, terminate = "immediate" }
fail-fast = { max-fail = "all" }  # Equivalent to false
```

### Test Grouping

| Key | Type | Default | Description |
| ----- | ------ | --------- | ------------- |
| `test-group` | string | `"@global"` | Assign test to a group |

### JUnit

```toml
[profile.ci.junit]
path = "junit.xml"
report-name = "nextest-run"
store-success-output = false
store-failure-output = true
report-skipped = "none"    # since 0.9.143
```

`report-skipped` accepts `"none"` (default), `"ignored"`, or `"all"`:

- `"none"` — skipped tests are omitted from the report.
- `"ignored"` — includes tests skipped via `#[ignore]`.
- `"all"` — includes everything skipped, including by filterset. Do not use
  this with sharded runs: each shard reports the tests it filtered out, so
  merging partitioned reports duplicates skipped entries.

It is also settable per-test through `[[profile.<name>.overrides]]`.

### Archive

```toml
[profile.default]
archive.include = [
    { path = "fixtures", relative-to = "target", depth = 2, on-missing = "warn" },
]
```

## Override Configuration

```toml
[[profile.<name>.overrides]]
filter = 'test(pattern)'           # At least one of filter/platform required
platform = 'cfg(target_os = "linux")'
# Override settings:
retries = 3
slow-timeout = { period = "60s", terminate-after = 2 }
threads-required = 2
test-group = 'my-group'
priority = 50
leak-timeout = "500ms"
success-output = "immediate"
failure-output = "immediate-final"
run-extra-args = ["--test-threads", "1"]
junit.report-skipped = "all"       # since 0.9.143
```

## Test Groups

```toml
[test-groups]
serial-db = { max-threads = 1 }
rate-limited = { max-threads = 4 }
```

## Script Configuration

### Setup Scripts

```toml
experimental = ["setup-scripts"]

[scripts.setup.my-script]
command = 'my-script.sh'
# or: command = ['script.sh', '-c', 'arg']
# or: command = { command-line = "debug/my-setup", relative-to = "target" }
slow-timeout = { period = "60s", terminate-after = 2 }
leak-timeout = "1s"
capture-stdout = true
capture-stderr = false

[[profile.default.scripts]]
filter = 'rdeps(db-tests)'
setup = 'my-script'
# or: setup = ['script1', 'script2']
```

### Wrapper Scripts

```toml
experimental = ["wrapper-scripts"]

[scripts.wrapper.my-wrapper]
command = 'sudo'
target-runner = "ignore"  # ignore | overrides-wrapper | within-wrapper | around-wrapper

[[profile.ci.scripts]]
filter = 'binary_id(pkg::bin) and test(=root_test)'
platform = 'cfg(target_os = "linux")'
run-wrapper = 'my-wrapper'
```

## User Configuration

`~/.config/nextest/config.toml` is a separate file with a separate schema
(`cargo nextest self schema user-config`, since 0.9.136). It holds
machine-local settings that should not be committed to a repository.

### `ui.max-progress-running`

Since 0.9.136 this accepts only a non-negative integer or the string
`"infinite"`. Numeric strings such as `"8"` were previously accepted through
an undocumented fallback and now fail validation. If you have
`max-progress-running = "8"`, change it to `max-progress-running = 8`.

### User-config platform overrides

`platform` in a user-config `[[overrides]]` section is matched against
nextest's **build target** — the platform nextest was compiled for — and
since 0.9.134 that is always the case. Earlier versions evaluated it against
the host in some situations. This is different from per-test overrides in
`.config/nextest.toml`, which match the platform the tests run on.

## Default Embedded Configuration

The following defaults are built into nextest and apply unless overridden:

```toml
[store]
dir = "target/nextest"

[profile.default]
default-filter = "all()"
retries = 0
test-threads = "num-cpus"
threads-required = 1
run-extra-args = []
status-level = "pass"
final-status-level = "flaky"
failure-output = "immediate"
success-output = "never"
fail-fast = true
slow-timeout = { period = "60s", on-timeout = "fail" }
leak-timeout = "200ms"
global-timeout = "30y"
```
