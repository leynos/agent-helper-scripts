# OrthoConfig user's guide

Configuration should not be the hardest part of writing a command-line
application. OrthoConfig describes settings as a Rust struct, then loads that
struct from defaults, a configuration file, environment variables, and
command-line arguments.

This guide starts with a small working CLI and grows it one practical task at a
time. Stop as soon as the application has what it needs.

## Install OrthoConfig

OrthoConfig needs Serde to turn merged values into the application's
configuration type. Add `clap` when the application defines its own command or
subcommand parser:

<!-- tested-example: guide-install -->
```toml
[dependencies]
clap = { version = "4.5", features = ["derive"] }
ortho_config = "0.9.0"
serde = { version = "1.0", features = ["derive"] }
```

The default features support TOML and the JSON-backed merge machinery used by
the derive. Optional `json5`, `yaml`, and `metrics` features are covered later.

## Build the first layered CLI

Start with one struct. The `prefix` is used for environment variables and for
the default file-discovery names. A trailing underscore is conventional and
keeps names such as `ACME_PORT` easy to read.

<!-- tested-example: guide-first-cli -->
```rust
use ortho_config::{OrthoConfig, OrthoResult};
use serde::{Deserialize, Serialize};

#[derive(Debug, Deserialize, Serialize, OrthoConfig)]
#[ortho_config(prefix = "ACME_")]
struct Config {
    #[ortho_config(default = String::from("127.0.0.1"))]
    host: String,

    #[ortho_config(default = 8080, cli_short = 'p')]
    port: u16,

    #[ortho_config(default = String::from("info"))]
    log_level: String,
}

fn main() -> OrthoResult<()> {
    let config = Config::load()?;
    println!(
        "host={} port={} log_level={}",
        config.host, config.port, config.log_level
    );
    Ok(())
}
```

That one definition provides three spellings for each field:

| Rust field  | Command line     | Environment      | TOML        |
| ----------- | ---------------- | ---------------- | ----------- |
| `host`      | `--host`         | `ACME_HOST`      | `host`      |
| `port`      | `--port` or `-p` | `ACME_PORT`      | `port`      |
| `log_level` | `--log-level`    | `ACME_LOG_LEVEL` | `log_level` |

_Table 1: Rust fields and their command-line, environment, and TOML names._

Values are merged from lowest to highest precedence:

1. `#[ortho_config(default = ...)]` values;
2. configuration files;
3. environment variables; and
4. command-line arguments.

This means a checked-in file can provide team defaults, an environment variable
can adapt them for a deployment, and a one-off CLI option can override both.

## See the configuration surface

Different sources suit different moments. Start with durable team settings in
`.acme.toml`:

<!-- tested-example: guide-file -->
```toml
host = "0.0.0.0"
port = 9000
log_level = "debug"
```

At deployment time, an environment variable can change the host without
rewriting the file. For a one-off run, a CLI option can change the port again:

<!-- tested-example: guide-file-run -->
```console
$ ACME_HOST=api.internal cargo run -- --port 3000
host=api.internal port=3000 log_level=debug
```

The result shows all three surfaces working together: `log_level` comes from
TOML, `ACME_HOST` supplies `host`, and `--port` wins for `port`. The command
uses POSIX shell syntax; in PowerShell, set `$env:ACME_HOST = "api.internal"`
before running the same Cargo command.

TOML is available by default. Enable the `yaml` or `json5` crate feature when
those formats are a better fit for application users; the
[file-format section](#enable-another-file-format) covers the details.

By default, discovery checks an explicit `--config-path`, the
`ACME_CONFIG_PATH` environment variable, project and home dotfiles, and the
platform configuration directory. Explicitly requested files are required: a
missing `--config-path` is an error rather than a silent fallback.

TOML naturally handles lists and nested values. For example, an application
could add `workers: Vec<Worker>` and `labels: BTreeMap<String, String>` to its
configuration struct, then use:

<!-- tested-example: guide-collection-file -->
```toml
[[workers]]
name = "queue-a"
concurrency = 4

[[workers]]
name = "queue-b"
concurrency = 2

[labels]
region = "eu-west"
tier = "worker"
```

For vectors, `merge_strategy = "append"` appends higher-precedence values;
`merge_strategy = "replace"` replaces the collection. Use
`merge_strategy = "keyed"` for keyed collection merging. Choose the policy
deliberately when operators may combine file, environment, and CLI values.

Configuration files can also contain `extends` entries. Relative paths are
resolved from the file that declares them, and parent layers are merged before
the child. OrthoConfig reports a missing parent with its absolute path and the
referencing file so the failure is actionable.

## Make discovery match the application

Application names do not need to bend around OrthoConfig's defaults. Put the
discovery contract beside the struct when the public flag or filenames are part
of the CLI design:

<!-- tested-example: guide-discovery -->
```rust
use ortho_config::{OrthoConfig, OrthoResult};
use serde::{Deserialize, Serialize};

#[derive(Debug, Deserialize, Serialize, OrthoConfig)]
#[ortho_config(
    prefix = "ACME_",
    discovery(
        app_name = "acme-server",
        config_file_name = "server.toml",
        dotfile_name = ".acme-server.toml",
        project_file_name = ".acme-server.toml",
        config_cli_long = "config",
        config_cli_short = 'c',
        config_cli_visible = true
    )
)]
struct Config {
    #[ortho_config(default = 8080)]
    port: u16,
}

fn main() -> OrthoResult<()> {
    let config = Config::load()?;
    println!("port={}", config.port);
    Ok(())
}
```

This application accepts `--config` and `-c`, reads `ACME_CONFIG_PATH`, looks
for `.acme-server.toml` in project locations, and uses `server.toml` in
platform configuration directories. Keeping these choices in the derive also
exposes them through `OrthoConfigDocs`.

### Handle every `load_first` outcome

`ConfigDiscovery::load_first` distinguishes three outcomes. `Ok(Some(...))`
contains the first successfully parsed candidate. `Ok(None)` means discovery
had no candidates to try. `Err(...)` means candidates existed but none loaded
successfully; surface or map that error rather than treating it as absence:

<!-- tested-example: guide-load-first-outcomes -->
```rust
use ortho_config::{ConfigDiscovery, OrthoResult};

fn load_discovered_config(discovery: &ConfigDiscovery) -> OrthoResult<()> {
    match discovery.load_first() {
        Ok(Some(_config)) => {
            // Merge or deserialize the discovered Figment value.
            println!("discovery=loaded");
            Ok(())
        }
        Ok(None) => {
            // Continue with application defaults.
            println!("discovery=absent");
            Ok(())
        }
        Err(error) => Err(error),
    }
}

fn main() -> OrthoResult<()> {
    let discovery = ConfigDiscovery::builder("acme").build();
    load_discovered_config(&discovery)
}
```

## Test discovery without changing the process environment

Tests that mutate environment variables interfere with one another. Build a
`ConfigDiscovery` with `MapEnv` instead. Each test owns its values and can run
in parallel:

<!-- tested-example: guide-hermetic-discovery -->
```rust
use ortho_config::{ConfigDiscovery, MapEnv};
use std::sync::Arc;

fn main() {
    let environment = Arc::new(
        MapEnv::new()
            .with_var("ACME_CONFIG", "/srv/acme/server.toml")
            .with_var("HOME", "/home/tester"),
    );

    let discovery = ConfigDiscovery::builder("acme")
        .env_var("ACME_CONFIG")
        .env_source(environment)
        .clear_project_roots()
        .build();

    assert_eq!(
        discovery.candidates().first().map(|path| path.as_path()),
        Some(std::path::Path::new("/srv/acme/server.toml"))
    );
    println!("candidate=/srv/acme/server.toml");
}
```

`ProcessEnv` remains the default, so production applications do not need to
change. `EnvSource` deliberately supports lookup by name but not enumeration;
discovery cannot accidentally scan or log unrelated environment values.

## Resolve discovery and merging without process state

Tests and embedded callers can resolve the complete configuration without
mutating the process environment. Use `ScanEnvSource` for the explicit ability
to enumerate variables for the merge layer, and pass it to
`CsvEnv::with_source`. The derive-generated
`OrthoConfig::load_from_iter_with_sources` entry point accepts both the
discovery `SharedEnvSource` and merge `SharedScanEnvSource`, so
configuration-path selection, files, and the environment layer use the same
supplied values.

`MapEnv` implements both source traits. Create one `Arc<MapEnv>`, then coerce
cloned `Arc` values to `SharedEnvSource` and `SharedScanEnvSource`; the same
map can therefore drive discovery lookups and merge enumeration. The ordinary
`load()` and `load_from_iter()` methods continue to use `ProcessEnv` by default.

For an upgrade checklist covering this opt-in API, see the OrthoConfig
v0.10.0 migration guide.

For a directly composed environment layer, attach the scan source to `CsvEnv`
with `with_source`:

<!-- tested-example: guide-csv-env-with-source -->
```rust
use ortho_config::{CsvEnv, MapEnv};
use std::sync::Arc;

let source = Arc::new(
    MapEnv::new()
        .with_var("APP_DATABASE__HOST", "localhost")
        .with_var("APP_TAGS", "one,two"),
);
let provider = CsvEnv::prefixed("APP_")
    .uppercase(true)
    .split("__")
    .with_source(source);
let _figment = ortho_config::figment::Figment::new().merge(provider);
```

The injected provider follows the same declarative rules as the process-backed
provider: prefix matching is case-insensitive and strips the matching prefix,
`uppercase` and `lowercase` transform names at their place in the builder
chain, and each `split` replaces its separator with a dotted key component. CSV
parsing is enabled by default; comma-containing scalar values become lists,
while values beginning with `[`, `{`, or a quote remain structured or quoted
values. Use `csv(false)` when a comma must remain part of a scalar value. The
source-aware path rejects `map()` and `filter_map()` providers because
arbitrary closures cannot be replayed against a `ScanEnvSource`.

For example, this complete load uses one map for the selector and merge layers:

<!-- tested-example: guide-source-aware-load -->
```rust
use ortho_config::{
    MapEnv, OrthoConfig, OrthoResult, SharedEnvSource, SharedScanEnvSource,
};
use serde::{Deserialize, Serialize};
use std::sync::Arc;

#[derive(Debug, Deserialize, Serialize, OrthoConfig)]
#[ortho_config(prefix = "ACME_")]
struct Config {
    #[ortho_config(default = 8080)]
    port: u16,
}

fn main() -> OrthoResult<()> {
    let environment = Arc::new(MapEnv::new().with_var("ACME_PORT", "9000"));
    let discovery: SharedEnvSource = environment.clone();
    let merge: SharedScanEnvSource = environment;

    let config = Config::load_from_iter_with_sources(["acme"], discovery, merge)?;
    println!("port={}", config.port);
    Ok(())
}
```

The example prints `port=9000`. No process variable is read: the discovery
source handles named lookups, while the scan source supplies the merge layer.

## Give each subcommand its own settings

Many CLIs have global options plus commands with different configuration. Derive
`OrthoConfig` for each subcommand's argument struct and merge only the
selected command:

<!-- tested-example: guide-subcommand -->
```rust
use clap::{Args, Parser, Subcommand};
use ortho_config::{OrthoConfig, OrthoResult, SubcmdConfigMerge};
use serde::{Deserialize, Serialize};

#[derive(Debug, Parser)]
#[command(name = "acme")]
struct Cli {
    #[command(subcommand)]
    command: Command,
}

#[derive(Debug, Subcommand)]
enum Command {
    Serve(ServeConfig),
}

#[derive(Debug, Default, Args, Deserialize, Serialize, OrthoConfig)]
#[command(name = "serve")]
#[ortho_config(prefix = "ACME_SERVE_")]
struct ServeConfig {
    #[arg(long)]
    port: Option<u16>,
}

fn main() -> OrthoResult<()> {
    match Cli::parse().command {
        Command::Serve(cli) => {
            let config = cli.load_and_merge()?;
            println!("port={:?}", config.port);
        }
    }
    Ok(())
}
```

For an enum with many variants, derive `SelectedSubcommandMerge` and use
`load_globals_and_merge_selected_subcommand`. The generated match keeps the
entry point small. Add `#[ortho_config(cli_default_as_absent)]` to a field when
a `clap` default should not override a value supplied by a file or environment
variable.

When a subcommand needs the same hermetic merge boundary, pass a
`SharedScanEnvSource` to `load_and_merge_with_sources` instead of using the
process-backed `load_and_merge`. For the `ServeConfig` above, the call is:

Set `ACME_SERVE_CMDS_SERVE_PORT` to `9000`, then bind the map with
`let environment = Arc::new(
MapEnv::new().with_var("ACME_SERVE_CMDS_SERVE_PORT", "9000"));`
and call `let config = cli.load_and_merge_with_sources(environment)?;`.

This supplies the `ACME_SERVE_CMDS_SERVE_PORT` layer while preserving the
existing CLI precedence. Import `MapEnv` and `std::sync::Arc` when using this
pattern.

Some commands only parse arguments and do not participate in configuration
loading. Keep those arguments in a separate clap-only type:

<!-- tested-example: guide-clap-only-parse -->
```rust
use clap::Parser;

#[derive(Debug, Parser)]
struct ParseOnlyArgs {
    #[arg(long)]
    format: Option<String>,
}

let args = ParseOnlyArgs::parse();
println!("format={:?}", args.format);
```

This parse-only workflow calls clap directly and does not load files or merge
environment values. Because `ParseOnlyArgs` does not derive `OrthoConfig`, it
has no `load_and_merge` or source-aware merge API. Use the `OrthoConfig`-derived
`ServeConfig` above when a command needs configuration layering.

## Handle errors at the application boundary

Library APIs return `OrthoResult<T>`, whose error is an `Arc<OrthoError>`.
Propagate it while loading, then render or map it where the application owns
the user experience:

<!-- tested-example: guide-errors -->
```rust
use ortho_config::{OrthoConfig, OrthoError};
use serde::Deserialize;

#[derive(Debug, Deserialize, OrthoConfig)]
struct Config {
    port: u16,
}

fn main() {
    match Config::load_from_iter(["acme", "--port", "not-a-number"]) {
        Ok(config) => println!("port={}", config.port),
        Err(error) => match error.as_ref() {
            OrthoError::CliParsing(clap_error) => eprintln!("{clap_error}"),
            other => eprintln!("configuration error: {other}"),
        },
    }
}
```

Preserve `clap`'s display-only exits for `--help` and `--version`; use
`is_display_request` when a wider application error layer needs to distinguish
them. `OrthoError::try_aggregate` combines independent validation failures
without inventing an error for an empty collection. The result extension traits
`OrthoResultExt`, `OrthoMergeExt`, and `ResultIntoFigment` keep conversions
explicit at integration boundaries.

## Localize help and parse failures together

Localization is most reliable when the command metadata is translated before
parsing and any resulting error goes through the same localizer.
`LocalizedParse` provides that path for the common case:

<!-- tested-example: guide-localization -->
```rust
use clap::Parser;
use ortho_config::{LocalizedParse, NoOpLocalizer};

#[derive(Debug, Parser)]
#[command(name = "acme", bin_name = "acme")]
struct Cli {
    #[arg(long)]
    verbose: bool,
}

fn main() -> Result<(), clap::Error> {
    let localizer = NoOpLocalizer::new();
    let cli = Cli::try_parse_localized_from(
        ["acme", "--verbose"],
        &localizer,
    )?;
    assert!(cli.verbose);
    println!("verbose={}", cli.verbose);
    Ok(())
}
```

Use `FluentLocalizer` for translated catalogues. Use `LocalizeCmd::with_base`
with `parse_localized_command` when catalogue identifiers must use an explicit
root rather than the binary name. Missing translations fall back to the original
`clap` text and emit a warning event, so users still receive a useful error.

## Add production diagnostics

OrthoConfig emits structured `tracing` events for discovery attempts, selected
files, skips, and failures. The library does not install a subscriber; the
binary should do that once during start-up. Add the subscriber with its
environment-filter support:

<!-- tested-example: guide-tracing-install -->
```toml
[dependencies]
tracing-subscriber = { version = "0.3", features = ["env-filter"] }
```

<!-- tested-example: guide-tracing -->
```rust
use ortho_config::{OrthoConfig, OrthoResult};
use serde::Deserialize;

#[derive(Deserialize, OrthoConfig)]
struct Config {
    #[ortho_config(default = 8080)]
    port: u16,
}

fn main() -> OrthoResult<()> {
    tracing_subscriber::fmt()
        .with_env_filter("ortho_config=debug")
        .with_writer(std::io::stderr)
        .try_init()
        .ok();

    let config = Config::load()?;
    println!("port={}", config.port);
    Ok(())
}
```

Do not log configuration values or candidate paths around these events. The
crate's own diagnostics avoid path and value fields because configuration
locations and values may be sensitive.

Metrics are a low-cost opt-in when the application already has a `metrics`
recorder:

<!-- tested-example: guide-metrics-install -->
```toml
[dependencies]
ortho_config = { version = "0.9.0", features = ["metrics"] }
```

The feature emits bounded counters such as discovery attempts, outcomes, and
failures. OrthoConfig never installs a recorder, and enabling the feature does
nothing visible until the application installs one.

## Generate help from the same metadata

`#[derive(OrthoConfig)]` also implements `OrthoConfigDocs`. The metadata
records fields, source names, precedence, discovery, defaults, and nested
subcommands. Derive `OrthoConfigSubcommandDocs` on a `clap::Subcommand` enum so
the generated tree includes every variant.

Inspect the metadata in code:

<!-- tested-example: guide-orthohelp-metadata -->
```rust
use ortho_config::{OrthoConfig, OrthoConfigDocs};
use serde::{Deserialize, Serialize};

#[derive(Deserialize, Serialize, OrthoConfig)]
#[ortho_config(prefix = "ACME_")]
struct Config {
    /// Address on which the service listens.
    #[ortho_config(default = String::from("127.0.0.1"))]
    host: String,
}

fn main() {
    let metadata = Config::get_doc_metadata();
    assert_eq!(metadata.fields.len(), 1);
    assert_eq!(metadata.fields[0].name, "host");
    println!("field={}", metadata.fields[0].name);
}
```

Or use `cargo-orthohelp` to emit intermediate representation (IR), Unix man
pages, PowerShell help, compact agent context, or all formats:

<!-- tested-example: guide-orthohelp-command -->
```console
cargo orthohelp --package hello_world --format agent-context
```

The tool builds a small bridge against the selected package. Keep the root
configuration type public and ensure its documentation metadata is available
from the selected library or binary target. `--format all` includes agent
context as well as IR, man pages, and PowerShell output.

## Offer a compact contract to automation

Agent context complements human help with a small, stable JSON description of
commands, inputs, output modes, interaction, and mutation boundaries. A common
application convention is `context --json`; `cargo-orthohelp` uses
`--format agent-context` for generation.

The smallest valid context created by `AgentContext::new("acme")` serializes to
this shape:

<!-- tested-example: guide-agent-context -->
```json
{
  "schema_version": "1",
  "kind": "acme.agent_context",
  "package": "acme",
  "commands": [],
  "profiles": { "supported": false },
  "feedback": { "supported": false },
  "policy": { "agent_native": "warn" },
  "skill_manifests": []
}
```

Fill `AgentCommand` entries only with claims the executable honours.
`SkillManifest` and `SkillCommandRef` link skills to real commands. They do not
replace command validation or grant an agent capabilities that the CLI does not
have.

## Use an aliased dependency

Cargo permits dependency aliases. In v0.9.0 the derive macros can generate
paths through that alias, which is useful in workspaces that reserve the
canonical crate name:

<!-- tested-example: guide-alias-install -->
```toml
[dependencies]
config_layer = { package = "ortho_config", version = "0.9.0" }
serde = { version = "1.0", features = ["derive"] }
```

Name the alias on every type that derives an OrthoConfig macro:

<!-- tested-example: guide-alias-derive -->
```rust
use config_layer::{OrthoConfig, OrthoResult};
use serde::Deserialize;

#[derive(Deserialize, OrthoConfig)]
#[ortho_config(crate = "config_layer", prefix = "ACME_")]
struct Config {
    #[ortho_config(default = 8080)]
    port: u16,
}

fn main() -> OrthoResult<()> {
    let config = Config::load_from_iter(["acme"])?;
    assert_eq!(config.port, 8080);
    println!("port={}", config.port);
    Ok(())
}
```

The same attribute is supported by `SelectedSubcommandMerge`. OrthoConfig
re-exports the dependencies used by generated code, so a derive-only consumer
does not need direct `figment`, `uncased`, `xdg`, or format-parser dependencies.

## Enable another file format

TOML is enabled by default. Enable `json5` or `yaml` when users already work in
that format. YAML uses YAML 1.2 semantics in v0.9.0: legacy words such as `yes`
and `on` remain strings, and duplicate mapping keys are rejected.

<!-- tested-example: guide-yaml -->
```yaml
enabled: yes
mode: on
port: 8080
```

Enable YAML with `features = ["yaml"]`; this also requires the `serde_json`
feature, which is part of the default feature set. If defaults are disabled,
enable both explicitly. Treat a change from v0.8.0 YAML parsing as a data
migration and run representative production files through v0.9.0 before
deploying.

## A practical path from here

For a new CLI, begin with the first layered struct and add only the required
sections. A typical progression is:

1. choose stable CLI and environment names;
2. add a project file for durable settings;
3. customize discovery if the defaults are not part of the public interface;
4. split independent commands into subcommand configurations;
5. localize help and initialize tracing at the application boundary; and
6. generate human and agent documentation once the command surface stabilizes.

The [Hello World application](https://github.com/leynos/ortho-config/tree/main/examples/hello_world)
demonstrates these pieces in a larger layout. The OrthoConfig v0.9.0
migration guide explains compatibility changes for existing v0.8.0 users, and
the
[API documentation](https://docs.rs/ortho_config) is the source for complete
type and method signatures.
