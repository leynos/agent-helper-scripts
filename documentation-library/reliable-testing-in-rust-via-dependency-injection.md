# 🛡️ Reliable testing in Rust via dependency injection

Writing robust, reliable, and parallelizable tests requires an intentional
approach to handling external dependencies such as environment variables, the
filesystem, or the system clock. Functions that directly call `std::env::var` or
`SystemTime::now()` are difficult to test because they depend on global,
non-deterministic state.

This leads to several problems:

- **Flaky Tests:** A test might pass or fail depending on the environment it
  runs in.
- **Parallel Execution Conflicts:** Tests that modify the same global
  environment variable (`std::env::set_var`) will interfere with each other
  when run with `cargo test`.
- **State Corruption:** A test that panics can fail to clean up its changes to
  the environment, poisoning subsequent tests.

The solution is a classic software design pattern: **Dependency Injection
(DI)**. Instead of a function reaching out to the global state, its
dependencies are provided as arguments. The
[mockable](https://docs.rs/mockable/latest/mockable/) crate offers a
convenient set of traits (`Env`, `Clock`, etc.) to implement this pattern for
common system interactions in Rust.

______________________________________________________________________

## ✨ Mocking environment variables

### 1. Add `mockable`

First, add the crate to development dependencies in `Cargo.toml`.

```toml
[dev-dependencies]
mockable = { version = "0.1.4", default-features = false, features = [
    "clock",
    "mock",
] }
```

### 2. The untestable code (before)

Directly calling `std::env` makes it difficult to test all logic paths
exhaustively.

```rust,no_run
pub fn get_api_key() -> Option<String> {
    match std::env::var("API_KEY") {
        Ok(key) if !key.is_empty() => Some(key),
        _ => None,
    }
}
```

### 3. Refactoring for testability (after)

The function is refactored to accept a generic type that implements the
`mockable::Env` trait.

```rust,no_run
use mockable::Env;

pub fn get_api_key(env: &impl Env) -> Option<String> {
    match env.string("API_KEY") {
        Some(key) if !key.is_empty() => Some(key),
        _ => None,
    }
}
```

The function's core logic remains unchanged, but its dependency on the
environment is now explicit and injectable.

### 4. Writing isolated unit tests

Tests can use `MockEnv`, an in-memory mock, to simulate any environmental
condition without touching the actual process environment.

```rust,no_run
#[cfg(test)]
mod tests {
    use super::*;
    use mockable::{MockEnv, Env};

    #[test]
    fn test_get_api_key_present() {
        let mut env = MockEnv::new();
        env.expect_string()
            .withf(|key| key == "API_KEY")
            .returning(|_| Some("secret123".to_string()));
        assert_eq!(get_api_key(&env), Some("secret123".to_string()));
    }

    #[test]
    fn test_get_api_key_missing() {
        let mut env = MockEnv::new();
        env.expect_string()
            .withf(|key| key == "API_KEY")
            .returning(|_| None);
        assert_eq!(get_api_key(&env), None);
    }

    #[test]
    fn test_get_api_key_present_but_empty() {
        let mut env = MockEnv::new();
        env.expect_string()
            .withf(|key| key == "API_KEY")
            .returning(|_| Some(String::new()));
        assert_eq!(get_api_key(&env), None);
    }
}
```

These tests are fast, completely isolated from each other, and will never fail
due to external state.

### 5. Usage in production code

In production code, inject the default implementation, `DefaultEnv`, which
calls the actual `std::env` functions.

```rust,no_run
use mockable::DefaultEnv;

fn main() {
    let env = DefaultEnv::new();
    if let Some(api_key) = get_api_key(&env) {
        println!("API Key found!");
    } else {
        println!("API Key not configured.");
    }
}
```

### 6. Configuring child processes explicitly

End-to-end tests that spawn a child process are the exception to injecting
environment state: the process boundary is the seam, not the harness. Clear
the child's inherited environment and add only the values the command
requires, rather than mutating or relying on the harness process's own
environment:

```rust,no_run
let mut command = assert_cmd::Command::new(program_under_test);
command
    .env_clear()
    .env("HOME", isolated_home)
    .env("PATH", controlled_path)
    .env("APP_CONFIG_PATH", config_path);
```

Configuring a spawned command's environment this way affects only the child
process. It is not licence to fall back on `std::env::set_var` or
`std::env::remove_var` in the harness process itself.

______________________________________________________________________

## 🔩 Handling other non-deterministic dependencies

This dependency injection pattern also applies to other non-deterministic
dependencies, such as the system clock. The `mockable` crate provides a `Clock`
trait for this purpose.

### Untestable code

```rust,no_run
use chrono::{DateTime, Utc};

fn is_cache_entry_stale(creation_time: DateTime<Utc>) -> bool {
    let timeout = chrono::Duration::seconds(300);
    Utc::now() - creation_time > timeout
}
```

### Testable refactor

```rust,no_run
use mockable::Clock;
use chrono::{DateTime, Utc};

fn is_cache_entry_stale(
    creation_time: DateTime<Utc>,
    clock: &impl Clock,
) -> bool {
    let timeout = chrono::Duration::seconds(300);
    clock.utc() - creation_time > timeout
}
```

### Testing with `MockClock`

```rust,no_run
#[cfg(test)]
mod tests {
    use super::*;
    use mockable::{MockClock, Clock};
    use chrono::Utc;

    #[test]
    fn test_cache_is_not_stale() {
        let creation_time = Utc::now();
        let mut clock = MockClock::new();
        clock
            .expect_utc()
            .returning(move || creation_time + chrono::Duration::seconds(100));
        assert!(!is_cache_entry_stale(creation_time, &clock));
    }

    #[test]
    fn test_cache_is_stale() {
        let creation_time = Utc::now();
        let mut clock = MockClock::new();
        clock
            .expect_utc()
            .returning(move || creation_time + chrono::Duration::seconds(301));
        assert!(is_cache_entry_stale(creation_time, &clock));
    }
}
```

In production, an instance of `DefaultClock::new()` would be used.

The same pattern applies more generally to internal timing seams. When a
component measures elapsed time rather than wall-clock time, keep the
override-resolution logic private and test it through the public entry point,
while injecting a narrow monotonic clock seam so duration assertions do not
depend on wall-clock time. Prefer `std::time::Instant` over `SystemTime` for
this seam because duration is elapsed-time data rather than calendar time.
The production adapter calls `Instant::now`, and tests supply a fixed clock
queued with pre-seeded instants. If a test consumes more instants than it
seeded, the fixed clock should panic with a configuration error, so the
failure is immediate and deterministic.

______________________________________________________________________

## 📌 Key takeaways

- **The Problem is Non-Determinism:** Directly accessing global state like
  `std::env` or `SystemTime::now` makes code difficult to test exhaustively.
- **The Solution is Dependency Injection:** Pass dependencies into functions as
  arguments.
- **Use** `mockable` **Traits:** Abstract dependencies behind traits such as
  `impl Env` or `impl Clock`.
- **`Mock*` for Tests:** Use `MockEnv` and `MockClock` in unit tests for
  isolated, deterministic control.
- **`Default*` for Production:** Use `DefaultEnv` and `DefaultClock` in the
  application to interact with the actual system.
- **`DefaultEnv` is NOT a Scope Guard:** `DefaultEnv` directly mutates the
  global process environment without automatic cleanup. For integration tests
  that require modifying the live environment, consider a crate such as
  [temp_env](https://crates.io/crates/temp-env). For unit tests, `MockEnv` is
  preferable. A lock or serialization annotation around such mutation does not
  make it safe; it only serializes it, so prefer injecting the value instead.
