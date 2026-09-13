# Architecting localizable Rust libraries with Fluent

When building a reusable Rust library (a crate), providing localized text for
elements such as error messages and user interface (UI) components presents a
unique challenge. The library itself cannot and should not make assumptions
about the end user's language preference. The final application that consumes
the library is the sole authority on the current locale.

The solution is a robust architectural pattern based on a clear separation of
concerns and dependency injection. In this model, the library provides the
localizable _resources_ (the `.ftl` files), and the consuming application
provides the localization _context_ (the configured `LanguageLoader`). This
ensures that the application maintains full control over language negotiation
and resource loading, while the library remains agnostic and highly reusable.

This guide outlines the standard pattern for creating and consuming localizable
libraries in Rust using the Fluent ecosystem.

## Core principles

1. **The application is the authority:** The application is solely responsible
   for detecting the locale, creating and configuring a single authoritative
   `LanguageLoader`, and managing the overall localization state.
2. **Libraries provide resources:** The library's role is to embed its `.ftl`
   translation files as assets and expose public functions that require a
   `LanguageLoader` to produce a translated string. The library defines _what_
   can be translated.
3. **Localization via dependency injection:** The application injects its
   configured `LanguageLoader` into the library's functions when a localized
   message is needed. The library never creates its own loader.
4. **Composability:** This pattern is highly composable. An application can
   aggregate translation assets from multiple independent libraries into one
   unified localization context, ensuring consistency across the entire program.

## Implementing the pattern: A two-crate workspace example

To illustrate this pattern, the following example uses a simple workspace
containing an application (`my-app`) that consumes a localizable library
(`my-lib`).

### 1. Workspace setup

First, create the workspace structure.

```plaintext
i18n-workspace/
├── Cargo.toml
├── my-app/
│   ├── Cargo.toml
│   ├── i18n.toml
│   └── src/main.rs
└── my-lib/
    ├── Cargo.toml
    ├── i18n/
    │   └── en-US/
    │       └── errors.ftl
    └── src/lib.rs
```

The root `Cargo.toml` defines the workspace members:

`i18n-workspace/Cargo.toml`

```toml
[workspace]
members = ["my-app", "my-lib"]
```

### 2. The library crate (`my-lib`)

The library contains its own Fluent Translation List (FTL) resources and
exposes a function to retrieve localized messages.

`my-lib/Cargo.toml`

The library needs `i18n-embed` for Fluent abstractions and `rust-embed` to
bundle `.ftl` files into the binary.[^1]

```toml
[package]
name = "my-lib"
version = "0.1.0"
edition = "2024"

[dependencies]
i18n-embed = { version = "0.14", features = ["fluent-system"] }
rust-embed = "8.0"
```

`my-lib/i18n/en-US/errors.ftl`

This file contains the library's localizable strings.

```fluent
error-not-found = The requested item could not be found.
error-permission-denied = You do not have permission to perform this action.
```

`my-lib/src/lib.rs`

The library's code exposes embedded assets and a function that accepts the
application's `LanguageLoader`.

```rust,no_run
use i18n_embed::fluent::FluentLanguageLoader;
use rust_embed::RustEmbed;

// 1. Embed the `i18n` directory into the library binary.
// This makes the FTL files available to the consuming application.
#[derive(RustEmbed)]
#[folder = "i18n/"]
pub struct MyLibLocalizations;

// 2. Define a public function that accepts a LanguageLoader via dependency
// injection.
// The library does not create its own loader; it uses the loader provided by
// the application.
pub fn get_error_message(loader: &FluentLanguageLoader, error_id: &str) -> String {
    // 3. Use the provided loader to look up a message from the library's own
    // resources.
    loader.get(error_id)
}
```

### 3. The application crate (`my-app`)

The application is responsible for setting up the localization context and
calling the library.

`my-app/Cargo.toml`

The application depends on the library and adds the `desktop-requester` feature
to `i18n-embed` to detect the system locale.[^2]

```toml
[package]
name = "my-app"
version = "0.1.0"
edition = "2024"

[dependencies]
my-lib = { path = "../my-lib" }
i18n-embed = { version = "0.14", features = ["fluent-system", "desktop-requester"] }
rust-embed = "8.0"
unic-langid = "0.9"
```

`my-app/i18n.toml`

The `fluent_language_loader!()` macro reads this file at compile time to learn
where the application's own Fluent resources live and which domain to
request. The `errors` domain makes the loader request `en-US/errors.ftl`,
matching the file that `MyLibLocalizations` embeds.

```toml
fallback_language = "en-US"

[fluent]
assets_dir = "i18n"
domain = "errors"
```

`my-app/src/main.rs`

The application's `main` function orchestrates the entire process.

```rust,no_run
use i18n_embed::{
    fluent::{fluent_language_loader, FluentLanguageLoader},
    DesktopLanguageRequester,
};
use my_lib::{get_error_message, MyLibLocalizations};

fn main() {
    // 1. Create the application's single authoritative LanguageLoader.
    let loader: FluentLanguageLoader = fluent_language_loader!();

    // 2. Determine the preferred language from the system.
    let requester = DesktopLanguageRequester::new();
    let requested_locales = requester.requested_languages();

    // 3. Perform language negotiation. The `select` function finds the best
    // matching language and loads all corresponding resources from the
    // library's assets into the application's loader. `RustEmbed` types
    // automatically satisfy `I18nAssets`, so `MyLibLocalizations` can be
    // passed directly, without a hand-written adapter.
    i18n_embed::select(&loader, &MyLibLocalizations, &requested_locales)
        .expect("Failed to select a language");

    // 4. Call the library's function, injecting the fully configured loader.
    let error_msg = get_error_message(&loader, "error-not-found");
    println!("Received from library: {}", error_msg);

    let perm_msg = get_error_message(&loader, "error-permission-denied");
    println!("Received from library: {}", perm_msg);
}
```

## Conclusion

This dependency injection pattern provides a clean, robust, and scalable
architecture for internationalization in a modular Rust ecosystem.[^1]

- **For library authors:** This pattern enables shipping localizable components
  without imposing a specific localization strategy on consuming applications.
  The library remains focused on core functionality while exposing translatable
  resources.
- **For application teams:** This pattern preserves full control over the user
  experience. Teams can manage locales, provide fallbacks, and aggregate
  resources from any number of third-party crates into a single consistent
  localization context.

By following this separation of concerns, the Rust ecosystem can provide
composable internationalized libraries that work together seamlessly.

## Works cited

[^1]: i18n_embed - Rust - [Docs.rs](https://docs.rs/i18n-embed), accessed on
      August 18, 2025.
[^2]: i18n_embed - Rust -
      [Docs.rs](https://docs.rs/i18n-embed/0.14.1/i18n_embed/),
      accessed on August 18, 2025.
