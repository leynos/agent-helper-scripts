# A Developer's Guide to Behavioural Testing in Rust with Cucumber

Status: historical reference. This document preserves earlier Cucumber
guidance and BDD rationale. Many projects have since migrated their
behavioural testing to `rstest-bdd`; see
[rstest-bdd-users-guide.md](rstest-bdd-users-guide.md) for current guidance.

## Part 1: The Philosophy and Practice of Behaviour-Driven Development (BDD)

Behaviour-Driven Development (BDD) is a software development process that
evolved from Test-Driven Development (TDD). Although testing remains integral,
the primary focus is on collaboration and communication among developers, QA
teams, business analysts, and product owners. This guide walks through
implementing BDD in Rust with the modern `cucumber` testing framework, covering
practical techniques, best practices, and lessons from real-world projects.

### 1.1 Beyond Testing: BDD as a Collaborative Process

At its core, BDD is not merely a testing technique but a methodology for
building a shared understanding of a system's behaviour.[^1] The central goal
is to create a ubiquitous language that both technical and non-technical
stakeholders can use to describe and agree upon software requirements.[^2] This
process is centred on conversation; the discussions about how a feature should
behave are the most valuable output of BDD.[^3]

The tangible artefact of these conversations is a set of specifications written
in a structured, natural language format. These specifications serve a dual
purpose: they are human-readable documentation of the system's features, and
they are also executable tests that verify the system's behaviour. This
approach ensures that documentation and implementation cannot drift apart,
creating a suite of "living documentation."

The value of BDD is realized before a single line of implementation code is
written. When a development team writes behaviour specifications in isolation,
they are simply using a different syntax for their tests. The transformative
potential of BDD is unlocked only when these specifications are co-created and
validated through a collaborative process involving all team members. This
ensures that what is built is precisely what the business needs, reducing
ambiguity and rework.

### 1.2 The Gherkin Language: Structuring Behaviour

To facilitate this process, BDD frameworks like Cucumber use a specific Domain-
Specific Language (DSL) called Gherkin.[^4] Gherkin provides a simple,
structured grammar for writing executable specifications in plain text files
with a `.feature` extension.[^5] Its syntax is designed to be intuitive and
accessible, enabling clear communication across different project roles.[^3]

A Gherkin document is line-oriented, with most lines beginning with a specific
keyword. The primary keywords give structure and meaning to the
specifications.[^6]

| Keyword          | Purpose                                                                                                | Simple Example                                      |
| ---------------- | ------------------------------------------------------------------------------------------------------ | --------------------------------------------------- |
| Feature          | Provides a high-level description of a software feature and groups related scenarios.[^3]              | Feature: User Authentication                        |
| Scenario         | Describes a single, concrete example of the feature's behaviour.[^3]                                   | Scenario: Successful login with valid credentials   |
| Given            | Sets the initial context or preconditions for a scenario.[^4]                                          | Given the user is on the login page                 |
| When             | Describes the key action or event that triggers the behaviour being tested.[^1]                        | When the user enters their username and password    |
| Then             | Specifies the expected outcome or result of the action.[^7]                                            | Then the user should be redirected to the dashboard |
| And, But         | Used to add more steps to a Given, When, or Then clause without repetition, improving readability.[^3] | And the user's name should be displayed             |
| Background       | Defines a set of steps that run before every Scenario in a Feature, used for common setup.[^5]         | Background: Given a registered user "Alice" exists  |
| Scenario Outline | A template for running the same Scenario multiple times with different data sets.[^3]                  | Scenario Outline: Login with various credentials    |
| Examples         | A data table that provides the values for a Scenario Outline.[^3]                                      | username &#124; password &#124; outcome             |

### 1.3 The Given-When-Then Idiom: A Universal Test Pattern

For developers, the `Given-When-Then` structure is not an entirely new concept.
It is a highly effective reformulation of well-established testing patterns
that many are already familiar with from unit testing.[^4] The most common
parallel is the **Arrange-Act-Assert (AAA)** pattern, conceptualized by Bill
Wake.

- **Given** corresponds to **Arrange**: This phase sets up the world. It
  establishes all preconditions, initializes objects, and brings the system
  under test (SUT) to the specific state required for the test. In Gherkin,
  this is where the team describes the context before the behaviour begins.[^4]

- **When** corresponds to **Act**: This is the single, pivotal action performed
  on the SUT. It's the event or trigger whose consequences are being specified.
  This phase should ideally contain only one primary action.[^4]

- **Then** corresponds to **Assert**: This phase verifies the outcome. After
  the action in the `When` step, the `Then` steps check that the SUT's state
  has changed as expected. These steps should contain the assertions and should
  be free of side effects.[^4]

This connection demystifies BDD. It is not an alien methodology but a
structured, collaborative application of a pattern developers already use. The
power of Gherkin lies in making the Arrange-Act-Assert pattern legible and
verifiable by non-programmers, thereby turning a simple test into a piece of
shared, executable documentation.

## Part 2: Project Setup: A First Rust Cucumber Test

Setting up a Rust project to use the `cucumber` crate requires a few specific
configurations in `Cargo.toml` and a well-defined directory structure. This
section walks through creating a minimal, runnable test suite from scratch.

### 2.1 Configuring `Cargo.toml`

To begin, the necessary dependencies must be added and a custom test runner
configured. The `cucumber` crate is async-native and requires an async runtime
to execute tests; `tokio` is the most common choice and is used throughout the
official documentation.[^8]

The key configuration step is defining a `[[test]]` target in `Cargo.toml`.
This tells Cargo to build a specific test executable. Setting `harness = false`
is crucial; it disables Rust's default test harness, allowing the `cucumber`
runner to take control of the process and print its own formatted output to the
console.[^9]

| Section            | Key      | Value / Description                                                                                        |
|--------------------|----------|------------------------------------------------------------------------------------------------------------|
| [dependencies]     | tokio    | The async runtime. Required with features like macros and rt-multi-thread.[^9]                             |
| [dev-dependencies] | cucumber | The main testing framework crate.[^10]                                                                     |
| [dev-dependencies] | futures  | Often needed for async operations, particularly with older examples or for specific combinators.[^11][^12] |
| [[test]]           | name     | The name of the test-runner file (e.g., "cucumber"). This must match the filename in tests/.               |
| [[test]]           | harness  | Must be set to `false` so cucumber can manage test execution and output.[^13]                              |

Here is a complete `Cargo.toml` configuration snippet:

```toml
[package]
name = "rust-cucumber-guide"
version = "0.1.0"
edition = "2021"

# The application's dependencies go here
[dependencies]

[dev-dependencies]
cucumber = { version = "0.21", features = ["output-junit"] }
tokio = { version = "1", features = ["macros", "rt-multi-thread"] }

[[test]]
name = "cucumber" # Corresponds to `tests/cucumber.rs`
harness = false
```

### 2.2 Directory Structure and File Organization

A well-organized project structure is vital for maintainable BDD tests. The
standard convention separates the human-readable feature specifications from
the Rust implementation code.[^11]

```plaintext
.
├── Cargo.lock
├── Cargo.toml
├── src/
│   └── lib.rs      # The application code
└── tests/
    ├── cucumber.rs   # The main test runner
    ├── features/     # Directory for Gherkin files
    │   └── calculator.feature
    └── steps/        # Directory for step definition modules
        └── calculator_steps.rs
```

This structure physically embodies the BDD philosophy of separating concerns.
The `.feature` files in `tests/features/` define *what* the system should do.
These can be read, written, and reviewed by non-technical stakeholders. The
Rust files in `tests/steps/` define *how* those behaviours are tested. This
clear boundary is a cornerstone of effective BDD practice and is strongly
recommended.[^13]

### 2.3 The `World` Object: Managing Scenario State

The `World` is the most critical concept in `cucumber-rs`. It is a user-defined
struct that encapsulates all the shared state for a single test scenario.[^10]
Each time a scenario begins, a new instance of the `World` is created. This
instance is then passed mutably to each step (`Given`, `When`, `Then`) within
that scenario.[^11]

This design provides a powerful mechanism for test isolation. Because each
scenario gets its private `World` instance, there is no risk of state leaking
from one test to another, even when tests are run concurrently.[^14] This is a
significant advantage of the Rust implementation, leveraging the language's
ownership model to solve a common and difficult problem in test automation.[^15]

To create a `World`, define a struct and derive `cucumber::World`. It is also
conventional to derive `Debug` and `Default`.[^8]

**Worked Example:** For a simple calculator application, the `World` might look
like this:

```rust
// In a shared location, e.g., tests/cucumber.rs
use cucumber::World;

// Assuming `my_crate::Calculator` is defined in the `src` directory.
#[derive(Debug, Default, World)]
pub struct CalculatorWorld {
    pub calculator: my_crate::Calculator,
    pub last_result: Option<i32>,
}
```

By default, `cucumber` will instantiate the `World` using `Default::default()`.
If a `World` requires more complex initialization (for example, starting a mock
server or connecting to a test database), provide a custom constructor function
using the `#[world(init = ...)]` attribute.[^14]

### 2.4 A First `main` Test Runner

With the `harness = false` setting in `Cargo.toml`, supply a custom `main`
function in the test target file (for example, `tests/cucumber.rs`). This
function acts as the entry point for the test suite.

Because `cucumber-rs` is async, the `main` function must be an `async fn` and
is typically annotated with `#[tokio::main]`.[^9] The core of the function is
a single line that invokes the test runner:

`YourWorld::run("path/to/features").await`.[^10]

**Worked Example:**

```rust
// In tests/cucumber.rs

use cucumber::World;

// Define the application's types or import them.
// For this example, assume a simple Calculator struct exists.
pub mod my_crate {
    #[derive(Debug, Default)]
    pub struct Calculator {
        value: i32,
    }

    impl Calculator {
        pub fn add(&mut self, num: i32) {
            self.value += num;
        }
        pub fn set(&mut self, num: i32) {
            self.value = num;
        }
        pub fn get_value(&self) -> i32 {
            self.value
        }
    }
}

// Define the World for the tests
#[derive(Debug, Default, World)]
pub struct CalculatorWorld {
    pub calculator: my_crate::Calculator,
}

// Import the step definitions
mod steps;

#[tokio::main]
async fn main() {
    CalculatorWorld::run("tests/features").await;
}
```

**Pitfall Warning:** Some application frameworks (for example, those with a
single-threaded event loop) do not tolerate a nested multi-threaded Tokio
runtime being started inside their own runtime during integration tests. In
that situation, annotate `main` with
`#[tokio::main(flavor = "current_thread")]` so the runner shares a
single-threaded runtime instead of nesting a multi-threaded one:

```rust
#[tokio::main(flavor = "current_thread")]
async fn main() {
    CalculatorWorld::run("tests/features").await;
}
```

At this point, there is a complete, albeit empty, test suite. Running
`cargo test --test cucumber` will compile the runner, which will then discover
`.feature` files in `tests/features`, find no matching steps, and report them
as undefined.

## Part 3: Writing Step Definitions: Connecting Gherkin to Rust

Step definitions are the "glue" that connects the human-readable Gherkin steps
in `.feature` files to executable Rust code. The `cucumber` crate provides
procedural macros to make this connection seamless and type-safe.

### 3.1 The `#[given]`, `#[when]`, and `#[then]` Macros

The core of step definition is a set of attribute macros: `#[given]`,
`#[when]`, and `#[then]`.[^8] These macros are applied to Rust functions. When
the test runner encounters a Gherkin step, it looks for a function annotated
with the corresponding macro and a matching text pattern.

Each step definition function must accept a mutable reference to the `World`
struct as its first argument (for example, `world: &mut CalculatorWorld`).[^11]
This affords the function the ability to modify the shared state for the
current scenario.

A key design choice in `cucumber-rs` is the strict separation of these step
types. A function marked with `#[then]` cannot be used to satisfy a `Given`
step in a feature file.[^14] This is a deliberate feature, not a limitation. It
encourages developers to maintain the clean Arrange-Act-Assert structure by
preventing them from accidentally using assertion logic during setup, or
performing actions during verification. This discipline leads to more readable,
robust, and maintainable tests.

**Worked Example:**

```rust
// In tests/steps/calculator_steps.rs
use crate::CalculatorWorld; // Import the World from the test runner
use cucumber::{given, when, then};

#[given("a calculator")]
fn a_calculator(world: &mut CalculatorWorld) {
    // The world is already initialized with a default Calculator
    // via `CalculatorWorld::default()`, so this step can be empty.
    // It exists to make the Gherkin readable.
}

#[when(expr = "I input {int}")]
fn input_number(world: &mut CalculatorWorld, number: i32) {
    world.calculator.set(number);
}

#[when(expr = "I add {int}")]
fn add_number(world: &mut CalculatorWorld, number: i32) {
    world.calculator.add(number);
}

#[then(expr = "the result should be {int}")]
fn check_result(world: &mut CalculatorWorld, expected: i32) {
    assert_eq!(world.calculator.get_value(), expected);
}
```

### 3.2 Capturing Arguments: Regex vs. Cucumber Expressions

To make steps dynamic, captured fragments of the Gherkin text must be passed as
arguments to the corresponding Rust functions. `cucumber-rs` supports two
mechanisms for this: regular expressions and Cucumber Expressions.[^10]

- **Cucumber Expressions (**`expr = "..."`**)**: This is the recommended
  default. They are less powerful than regex but are more readable and
  explicitly designed for this purpose. They provide built-in parsing for
  common types like `{int}`, `{float}`, `{word}`, and `{string}` (in
  quotes).[^10] The framework automatically handles parsing the captured string
  into the corresponding Rust type in the function signature.

- **Regular Expressions (**`regex = "..."`**)**: For more complex matching
  needs, full regex syntax can be used. Capture groups `(...)` in the regex
  correspond to function arguments.[^11] The framework will still attempt to
  parse the captured `&str` into the function's argument type. It is a best
  practice to anchor the regex with `^` and `$` to ensure the entire step text
  is matched, preventing partial or ambiguous matches.[^11].

| Feature         | Cucumber Expression Example                                          | Regex Example                                                          | Recommendation                                               |
| --------------- | -------------------------------------------------------------------- | ---------------------------------------------------------------------- | ------------------------------------------------------------ |
| Basic Capture   | expr = "I have {int} cucumbers"                                      | regex = r"^I have (\d+) cucumbers$"                                    | Use expressions for clarity.                                 |
| Type Conversion | {int} automatically maps to i32, u64, etc.                           | Capture group (\\d+) is a &str, parsed to the function's numeric type. | Expressions are more direct and less error-prone.            |
| Readability     | High. The intent is clear from the expression itself.                | Medium to Low. Regex can become complex and hard to read.              | Expressions are superior for collaboration.                  |
| Flexibility     | Limited to its defined syntax (e.g., cannot match complex patterns). | High. Can match almost any text pattern.                               | Use Regex as a power tool when expressions are insufficient. |

### 3.3 Handling Test Outcomes: `assert!` and `Result`

The `Then` steps are where the system's state is verified. The most
straightforward way to do this is with Rust's standard assertion macros, like
`assert_eq!` or `assert!`.[^10] If an assertion fails, the thread will panic,
and `cucumber` will mark the step as failed.

However, a more idiomatic and powerful approach is to have step functions
return a `Result`.[^14] A step that returns

`Ok(())` passes, while one that returns an `Err(...)` fails. This has two major
benefits:

1. **Cleaner Code:** Using the `?` operator propagates errors from the
   application logic or from parsing steps, leading to more concise and
   readable code.

2. **Richer Failure Messages:** A panic from an `assert!` often gives a limited
   error message. Returning a custom error type that implements
   `std::error::Error` provides detailed, contextual information about *why*
   the test failed. This is invaluable for debugging.

Rust's error handling philosophy is built around the `Result` enum for
recoverable errors, and a test failure is a recoverable error from the test
runner's perspective.[^16] Embracing this pattern in step definitions is a
significant best practice.

**Worked Example (using** `Result`**):**

```rust
use anyhow::Context;
use thiserror::Error;

#[derive(Debug, Error)]
pub enum TestError {
    #[error("API call failed: {0}")]
    Api(#[from] reqwest::Error),
    #[error("response has not been captured yet")]
    MissingResponse,
    #[error("Unexpected status code: expected {expected}, got {actual}")]
    UnexpectedStatus { expected: u16, actual: u16 },
    #[error("response body parse error: {0}")]
    Parse(#[from] serde_json::Error),
}

#[then(expr = "the response status should be {int}")]
fn check_status(world: &mut ApiWorld, expected_status: u16) -> Result<(), TestError> {
    let response = world
        .last_response
        .as_ref()
        .ok_or(TestError::MissingResponse)?;
    let actual_status = response.status().as_u16();

    if actual_status != expected_status {
        return Err(TestError::UnexpectedStatus {
            expected: expected_status,
            actual: actual_status,
        });
    }

    Ok(())
}
```

This approach provides a clear, structured error that is much more informative
than a simple assertion failure.

## Part 4: Advanced Gherkin & Step Definition Techniques

As test suites grow in complexity, more advanced Gherkin features become
necessary to keep them maintainable and expressive. This section covers
techniques for data-driven testing, handling complex inputs, and managing
asynchronous operations.

### 4.1 Data-Driven Testing: `Scenario Outline` and `Examples`

Often, the same behaviour must be tested with various inputs and expected
outputs. Writing a separate `Scenario` for each case would be highly
repetitive. Gherkin solves this with the `Scenario Outline` keyword.[^3]

A `Scenario Outline` acts as a template. The steps are written using
placeholders enclosed in angle brackets, like `<input>` or `<output>`. Below
the outline, an `Examples` table provides the concrete values. Each row in
this table represents a concrete run of the scenario, with the column headers
matching the placeholders in the steps.[^17]

**Worked Example:**

```gherkin
# In tests/features/calculator.feature
Feature: Basic arithmetic
  As a user
  I want to perform calculations
  So I can avoid doing math in my head

  Scenario Outline: Adding various numbers
    Given a calculator
    When I input <num1>
    And I add <num2>
    Then the result should be <total>

    Examples:

| num1 | num2 | total |
| 2 | 3 | 5 |
| -5 | 5 | 0 |
| 100 | 0 | 100 |
| 0 | -20 | -20 |
```

This single `Scenario Outline` will generate and run four separate tests, each
with its own `World` instance, providing excellent test coverage with minimal
boilerplate.

### 4.2 Passing Structured Data with Data Tables

Sometimes, a step requires a more complex data structure than can be passed
with simple arguments. For example, setting up an initial inventory or
providing a list of users. For this, Gherkin provides **Data Tables**.[^18]

A Data Table is a pipe-delimited table placed directly after a Gherkin step. To
access this table in a Rust step definition, add a
`step: &cucumber::gherkin::Step` argument to the function. The table can then
be accessed via `step.table` (which is an `Option<Table>`).[^18]

Data tables encourage a more declarative style of testing. Instead of writing a
series of imperative steps to build up a state (e.g., "Given I add a user
'Alice'", "And I set her role to 'Admin'"), the entire state can be described
in a single, readable table.[^19].

This makes the

`Given` steps more concise and focused on the initial context.

**Worked Example:**

```gherkin
# In tests/features/inventory.feature
Scenario: Checking stock levels
  Given the following items are in the warehouse:

| name | quantity | location |
| Widgets | 100 | Aisle 1 |
| Gadgets | 50 | Aisle 3 |
  When a customer orders 20 "Widgets"
  Then the stock level for "Widgets" should be 80
```

```rust
// In tests/steps/inventory_steps.rs
use anyhow::{Context, Result};
use cucumber::{gherkin::Step, given};
use crate::InventoryWorld;

#[given("the following items are in the warehouse:")]
fn given_items_in_warehouse(world: &mut InventoryWorld, step: &Step) -> Result<()> {
    let table = step
        .table
        .as_ref()
        .context("step must include a data table")?;

    let header = table
        .rows
        .first()
        .context("data table must include a header row")?;
    let name_idx = header
        .iter()
        .position(|h| h == "name")
        .context("data table missing `name` column")?;
    let quantity_idx = header
        .iter()
        .position(|h| h == "quantity")
        .context("data table missing `quantity` column")?;

    for row in table.rows.iter().skip(1) {
        let name = row
            .get(name_idx)
            .context("row missing `name` value")?
            .to_owned();
        let quantity: u32 = row
            .get(quantity_idx)
            .context("row missing `quantity` value")?
            .parse()
            .with_context(|| format!("invalid quantity for item {name}"))?;
        world.stock.insert(name, quantity);
    }

    Ok(())
}
```

### 4.3 Managing Common Preconditions with `Background`

If every scenario in a `.feature` file shares the same set of initial `Given`
steps, the `Background` keyword can be used to reduce duplication.[^5] The
steps listed under

`Background` will be executed before *each* `Scenario` in that feature
file.[^20]

**Worked Example:**

```gherkin
Feature: User account management

  Background:
    Given the user is logged in as "Alice"
    And the user navigates to the "Profile" page

  Scenario: Updating user's email
    When the user changes their email to "alice.new@example.com"
    Then a confirmation email should be sent to "alice.new@example.com"

  Scenario: Changing user's password
    When the user updates their password
    Then the user should be logged out
```

**Pitfall Warning:** Use `Background` with caution. If it becomes too long or
is not relevant to every single scenario, it can make the tests harder to
understand by hiding essential context. If only some scenarios share setup, it
is better to create a dedicated `Given` step and repeat it.[^15]

### 4.4 Asynchronous Operations: Testing in the Real World

Modern Rust applications, especially those involving networking, databases, or
file I/O, are heavily asynchronous. The `cucumber-rs` crate is designed with
this in mind, making it an excellent choice for integration and end-to-end
(E2E) testing.

Step definition functions can be declared as `async fn`.[^8] Inside these
functions, any `Future` – such as a database query or HTTP request – can be
`.await`-ed. This requires that the test runner's `main` function is powered
by an async runtime like `tokio`.[^9]

The async-first design of `cucumber-rs` is one of its most powerful features.
It allows for writing tests that accurately reflect the asynchronous nature of
the application under test. Furthermore, because `cucumber` can run scenarios
concurrently by default, I/O-bound tests can execute in parallel, dramatically
reducing the total runtime of the test suite compared with traditional
synchronous, serial test runners.[^14] This makes it feasible to run
comprehensive integration test suites as part of a regular development
workflow.

**Worked Example (Async Step):**

```rust
// In tests/steps/api_steps.rs
use crate::ApiWorld;
use cucumber::when;
use std::time::Duration;

#[when(expr = "the client requests the user profile for {word}")]
async fn request_user_profile(world: &mut ApiWorld, username: String) {
    // Simulate a network request
    tokio::time::sleep(Duration::from_millis(50)).await;

    let client = &world.http_client;
    let url = format!("{}/users/{}", world.server_address, username);

    let response = client.get(&url).send().await.unwrap();
    world.last_response = Some(response);
}
```

## Part 5: Worked Example: Behavioural Testing for a REST API

This section synthesizes the concepts from previous parts into a complete,
practical example: testing a simple key-value store REST API. This demonstrates
a realistic use case for `cucumber-rs` as an integration testing tool,
leveraging `reqwest` for HTTP requests and `wiremock-rs` for creating an
isolated, in-process mock server.

### 5.1 Defining the Feature (`kv_store.feature`)

First, the desired behaviour is defined in a Gherkin `.feature` file. This file
serves as the executable specification for the API.

```gherkin
# In tests/features/kv_store.feature
Feature: Key-Value Store API
  As a client of the service
  I want to store and retrieve values by key
  So that I can persist simple data

  Scenario: Successfully storing and retrieving a value
    Given the key "hello" does not exist in the store
    When the client sends "world" to "/kv/hello"
    Then the response status should be 201
    When the client requests "/kv/hello"
    Then the response status should be 200
    And the response body should be "world"

  Scenario: Retrieving a non-existent key
    Given the key "goodbye" does not exist in the store
    When the client requests "/kv/goodbye"
    Then the response status should be 404
```

### 5.2 Designing the `World` for API Testing

The `World` for this test suite needs to manage the state of the HTTP client
and the mock server. It will also store the last API response so that `Then`
steps can perform assertions on it.

A crucial aspect of this design is that the mock server is part of the `World`.
This means each scenario gets its own, completely isolated mock server instance
running on a random port. This is the key to enabling fast, reliable, and
parallelizable integration tests.[^14]

```rust
// In tests/cucumber.rs
use cucumber::World;
use reqwest::Response;
use wiremock::MockServer;

#[derive(Debug, World)]
#[world(init = Self::new)]
pub struct ApiWorld {
    pub server: MockServer,
    pub client: reqwest::Client,
    pub last_response: Option<Response>,
}

impl ApiWorld {
    async fn new() -> Self {
        Self {
            server: MockServer::start().await,
            client: reqwest::Client::new(),
            last_response: None,
        }
    }
}

mod steps;

#[tokio::main]
async fn main() {
    ApiWorld::run("tests/features/kv_store.feature").await;
}
```

Note the use of `#[world(init = Self::new)]` and the `async fn new()`
implementation. This is necessary because starting the `MockServer` is an
async operation and cannot be done in a `Default::default()`
implementation.[^14]

### 5.3 Mocking Dependencies with `wiremock-rs`

`wiremock-rs` is a pure-Rust library for mocking HTTP-based APIs.[^21]
Expectations can be defined (for example, "expect a GET request to `/foo`") and
specify responses. This is done in the `Given` steps to set up the state of the
external world before the `When` action occurs.

Using an in-process mock server like `wiremock-rs` is a superior pattern for
integration testing. It avoids the complexity and slowness of managing external
services or Docker containers, leading to faster and more reliable test
execution.[^21]

### 5.4 Implementing the API Step Definitions

The step definitions will use the `server` from the `ApiWorld` to set up mocks
and the `client` to make requests.

```rust
// In tests/steps/api_steps.rs
use crate::ApiWorld;
use anyhow::Context;
use cucumber::{given, then, when};
use std::sync::{Arc, Mutex};
use thiserror::Error;
use wiremock::matchers::{method, path};
use wiremock::{Mock, Request, ResponseTemplate};

#[derive(Debug, Error)]
pub enum ApiError {
    #[error("no HTTP response recorded; call a client step first")]
    MissingResponse,
    #[error("unexpected status code: expected {expected}, found {actual}")]
    StatusMismatch { expected: u16, actual: u16 },
    #[error("unexpected response body: expected {expected}, found {actual}")]
    BodyMismatch { expected: String, actual: String },
    #[error(transparent)]
    Transport(#[from] anyhow::Error),
}

type StepResult = std::result::Result<(), ApiError>;

#[given(expr = "the key {string} does not exist in the store")]
async fn key_does_not_exist(world: &mut ApiWorld, key: String) -> StepResult {
    let resource_path = format!("/kv/{}", key);
    let stored_value: Arc<Mutex<Option<Vec<u8>>>> = Arc::new(Mutex::new(None));

    // Mount the GET responder first, before any POST can run. It reads the
    // shared state below, so it serves 404 until a value has been posted and
    // 200 with the stored body afterwards. Mounting completes before this
    // function returns, closing the race between the POST and GET mocks.
    let get_state = Arc::clone(&stored_value);
    Mock::given(method("GET"))
        .and(path(resource_path.clone()))
        .respond_with(move |_request: &Request| match &*get_state.lock().unwrap() {
            Some(body) => ResponseTemplate::new(200).set_body_bytes(body.clone()),
            None => ResponseTemplate::new(404),
        })
        .mount(&world.server)
        .await;

    // For a POST, store the request body in the shared state so the GET
    // responder above can serve it on subsequent requests.
    let post_state = Arc::clone(&stored_value);
    Mock::given(method("POST"))
        .and(path(resource_path))
        .respond_with(move |request: &Request| {
            *post_state.lock().unwrap() = Some(request.body.clone());
            ResponseTemplate::new(201)
        })
        .mount(&world.server)
        .await;

    Ok(())
}

#[when(expr = "the client sends {string} to {string}")]
async fn client_posts_value(world: &mut ApiWorld, value: String, path: String) -> StepResult {
    let url = format!("{}{}", world.server.uri(), path);
    let response = world
        .client
        .post(&url)
        .body(value)
        .send()
        .await
        .context("send POST request")?;
    world.last_response = Some(response);
    Ok(())
}

#[when(expr = "the client requests {string}")]
async fn client_gets_path(world: &mut ApiWorld, path: String) -> StepResult {
    let url = format!("{}{}", world.server.uri(), path);
    let response = world
        .client
        .get(&url)
        .send()
        .await
        .context("send GET request")?;
    world.last_response = Some(response);
    Ok(())
}

#[then(expr = "the response status should be {int}")]
async fn check_response_status(world: &mut ApiWorld, expected_status: u16) -> StepResult {
    let response = world
        .last_response
        .as_ref()
        .ok_or(ApiError::MissingResponse)?;
    let actual = response.status().as_u16();
    if actual != expected_status {
        return Err(ApiError::StatusMismatch {
            expected: expected_status,
            actual,
        });
    }
    Ok(())
}

#[then(expr = "the response body should be {string}")]
async fn check_response_body(world: &mut ApiWorld, expected_body: String) -> StepResult {
    let response = world
        .last_response
        .take()
        .ok_or(ApiError::MissingResponse)?;
    let body = response
        .text()
        .await
        .context("read response body")?;
    if body != expected_body {
        return Err(ApiError::BodyMismatch {
            expected: expected_body,
            actual: body,
        });
    }
    Ok(())
}
```

This complete example demonstrates the full BDD cycle: defining behaviour,
setting up an isolated test environment in the `World`, mocking dependencies,
executing actions, and asserting outcomes, all within Rust's powerful async
ecosystem.

## Part 6: Best Practices for Scalable and Maintainable Test Suites

As a project grows, so does its test suite. Adhering to best practices is
essential to ensure that Cucumber tests remain a valuable asset rather than a
maintenance burden.

### 6.1 The "One-to-One" Rule: One Scenario, One Behaviour

A fundamental principle for writing clean Gherkin is that **each scenario
should test exactly one behaviour**.[^5] A common anti-pattern is to chain
multiple actions and outcomes within a single scenario, often indicated by
multiple

`When-Then` pairs.

**Anti-Pattern:**

```gherkin
Scenario: User manages their cart
  Given a user has an item in their cart
  When the user increases the item quantity
  Then the cart total should update
  And when the user applies a discount code
  Then the final price should be lower
```

This scenario is testing two distinct behaviours: updating quantity and
applying a discount. If the second `Then` fails, it's unclear if the issue is
with the discount logic or if the state from the first action was incorrect.

**Best Practice:** Split this into two focused scenarios.

```gherkin
Scenario: Updating item quantity updates cart total
  Given a user has an item in their cart
  When the user increases the item quantity
  Then the cart total should update

Scenario: Applying a valid discount code reduces the final price
  Given a user has an item in their cart
  When the user applies a valid discount code
  Then the final price should be lower
```

This approach isolates failures, improves clarity, and makes each scenario an
independent specification of a single rule.[^5]

### 6.2 Declarative vs. Imperative Steps: Finding the Balance

The most maintainable test suites favour a **declarative** style over an
**imperative** one.

- **Imperative steps** describe *how* an action is performed, often coupling the
  test to specific UI elements or implementation details (e.g., "When I click
  the 'submit-button'"). This makes tests brittle; a small UI change can break
  many tests.[^19]

- **Declarative steps** describe *what* the user is trying to achieve, focusing
  on intent and behaviour (e.g., "When I submit my registration").

The collective set of step definitions should evolve into a project-specific
Domain-Specific Language (DSL).[^3] A step like

`When I register my account` is declarative. Internally, its Rust
implementation might perform several imperative actions (fill form fields,
click a button, wait for an API response), but these details are abstracted
away from the `.feature` file. This abstraction is the key to creating a robust
and maintainable test suite that communicates business value.

### 6.3 `World` Management in Large Projects

In large projects, the `World` struct can become a "god object," accumulating
dozens of fields and becoming difficult to manage. To avoid this, use
composition.

**Best Practice:** Instead of a monolithic `World`, structure it with smaller,
focused context structs.

```rust
// Less maintainable
pub struct MonolithicWorld {
    user_id: Option<u32>,
    auth_token: Option<String>,
    api_client: ApiClient,
    db_connection: DbPool,
    last_api_response: Option<ApiResponse>,
    //… and 20 more fields
}

// More maintainable
pub struct AuthContext {
    user_id: Option<u32>,
    auth_token: Option<String>,
}

pub struct ComposedWorld {
    pub auth: AuthContext,
    pub api_client: ApiClient,
    pub db_pool: DbPool,
    pub last_response: Option<ApiResponse>,
}
```

This approach organizes state logically and makes the `World` easier to reason
about. For complex setup, always prefer a custom constructor with
`#[world(init =...)]` over trying to force everything into `Default`.[^14]

### 6.4 Organizing Features and Steps

Test code should be organized in the same way as application code.

- **Feature Files:** Group `.feature` files by application capability or user
  story.[^20] For example,

  `tests/features/authentication/`, `tests/features/product_catalog/`, etc.

- **Step Definitions:** Mirror the feature file structure in the `tests/steps/`
  directory. Create a Rust module for each feature area (e.g.,
  `tests/steps/ authentication_steps.rs`, `tests/steps/catalog_steps.rs`). This
  prevents having a single, massive step definition file and makes it easier to
  find the code corresponding to a Gherkin step.

## Part 7: Common Pitfalls and Troubleshooting

Even with best practices, developers can encounter common issues when
implementing BDD. Recognizing these pitfalls is the first step to avoiding them.

### 7.1 State Leakage and Concurrency Issues

**Pitfall:** Sharing state between scenarios using `static` variables, global
state, or external files. This is a primary cause of flaky, non-deterministic
tests, especially because `cucumber-rs` runs scenarios concurrently by
default.[^14]

**Solution:** The `World` object is the *only* sanctioned place for scenario
state. Treat each scenario as if it could be running at the same time as any
other. If a scenario must interact with a shared, singular resource (like a
physical hardware device), tag the relevant scenarios with `@serial`. This
forces them to run one at a time.[^14] However, overuse of `@serial` is often a
sign of a poor test design and negates the performance benefits of concurrency.
This tag should be used sparingly.

### 7.2 Flaky Tests from Asynchronous Code

**Pitfall:** Tests that fail intermittently, often due to timing issues or race
conditions in asynchronous code.[^22] A common mistake is using fixed delays (

`tokio::time::sleep`) to "wait" for an operation to complete.

**Solution:**

1. **Avoid Arbitrary Sleeps:** Never use fixed delays to wait for an event. The
   correct duration is impossible to guess and will lead to either slow tests
   or flaky tests.

2. **Use Deterministic Mocks:** When possible, use tools like `wiremock-rs`.
   The interactions are deterministic and immediate, eliminating timing issues
   related to network latency.[^21]

3. **Implement Explicit Synchronization:** When testing against real systems,
   use mechanisms like polling with a timeout, waiting for a specific log
   message, or checking a database flag to know when an operation is complete.

4. **Use Built-in Retries:** For tests that are inherently prone to transient
   failures (e.g., E2E tests over a real network), use the `cucumber` runner's
   retry mechanism (`--retry <count>`) to automatically re-run failed
   scenarios.[^23]

### 7.3 The `unwrap()` Trap and Poor Error Handling

**Pitfall:** Littering step definitions with `.unwrap()` and `.expect()`. When
these panic, the resulting error message is often generic and lacks the context
needed to quickly diagnose the problem.[^16] For example, a panic on

`world.last_response.as_ref().unwrap()` does not indicate which API call failed
to produce a response.

**Solution:** As discussed in section 3.3, step functions should return a
`Result`. Define custom, descriptive error types using crates like `thiserror`
or `anyhow` to wrap underlying errors and add context. A well-defined `Err`
variant is far more valuable for debugging than a stack trace from a panic.[^14]

### 7.4 Ambiguous Step Definitions

**Pitfall:** The test run fails with an "ambiguous step" error. This means a
single Gherkin step matches the patterns of two or more Rust functions.[^15]

**Solution:**

1. **Be More Specific:** Make the Gherkin step text or the matching pattern
   more precise to eliminate the ambiguity.

2. **Anchor Regex:** When using regular expressions, always anchor them with
   `^` at the start and `$` at the end (e.g.,
   `regex = r"^the user is logged in$"`). This prevents a step like
   `"the admin user is logged in"` from accidentally matching a less specific
   pattern like `regex = r"user is logged in"`.[^11]

## Part 8: Integrating into the Development Lifecycle

BDD is most effective when it is an integral part of the daily development
workflow and the automated CI/CD pipeline.

### 8.1 The Cucumber CLI: Running Tests with Precision

Running the entire test suite can be slow. The `cucumber` test runner supports
a rich set of command-line arguments that allow a targeted subset of scenarios
to be run. These arguments are passed to the test executable after a `--`
separator: `cargo test --test cucumber --`.[^24]

| Flag                    | Purpose                                                          | Example Usage                                             |
| ----------------------- | ---------------------------------------------------------------- | --------------------------------------------------------- |
| `-t, --tags <EXPR>`     | Filter scenarios by a tag expression. Supports and, or, and not. | cargo test --test cucumber -- -t "@wip and not @slow"     |
| `-n, --name <REGEX>`    | Filter scenarios by a regular expression matching their name.    | cargo test --test cucumber -- -n "login"                  |
| --fail-fast             | Stop the test run on the first failure.                          | cargo test --test cucumber -- --fail-fast                 |
| `-c, --concurrency <N>` | Limit the number of scenarios running concurrently.              | cargo test --test cucumber -- -c 1 (for serial execution) |
| `--retry <N>`           | Retry failed scenarios up to N times.                            | cargo test --test cucumber -- --retry 2                   |

These flags are essential for developer productivity, enabling rapid feedback
by running only the tests relevant to the current work.

### 8.2 Continuous Integration (CI/CD): Living Documentation in Practice

The ultimate goal of BDD is to have a suite of executable specifications that
continuously validate the system's behaviour. Integrating Cucumber tests into a
CI/CD pipeline is what brings this "living documentation" to life.[^25]

The process involves two main steps:

1. **Run the tests:** The CI job executes `cargo test --test cucumber`. The
   `cucumber` runner will exit with a non-zero status code if any scenario
   fails, which automatically fails the CI build.[^25]

2. **Publish reports:** Many CI platforms can parse and display test results
   in a structured format. The `cucumber` crate's `output-junit` feature flag
   enables a `writer::JUnit` writer, and it is the custom runner, not a CLI
   flag, that configures this writer and produces the JUnit XML report.[^10]
   These XML files can then be published as test artefacts for platforms like
   GitHub Actions, GitLab CI, or Jenkins to consume.[^25]

The custom runner in `tests/cucumber.rs` writes the report directly:

```rust
// In tests/cucumber.rs
use cucumber::{writer, World as _};
use std::fs;
use std::io;

#[tokio::main]
async fn main() -> io::Result<()> {
    fs::create_dir_all("target/junit")?;
    let file = fs::File::create("target/junit/junit.xml")?;
    YourWorld::cucumber()
        .with_writer(writer::JUnit::new(file, 0))
        .run("tests/features")
        .await;
    Ok(())
}
```

This CI integration closes the BDD loop. The `.feature` files, once checked
into version control, are no longer static documents. They become active
participants in the build process. A CI failure on a Cucumber test provides
immediate, unambiguous feedback that the implementation has diverged from the
agreed- upon behaviour, prompting a conversation to either fix the code or
update the specification.

**Worked Example (GitHub Actions):**

```YAML
# .github/workflows/ci.yml
name: Rust CI

on:
  push:
    branches: [ "main" ]
  pull_request:
    branches: [ "main" ]

jobs:
  test:
    name: Run tests
    runs-on: ubuntu-latest
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Install Rust toolchain
        uses: actions-rs/toolchain@v1
        with:
          toolchain: stable
          components: clippy, rustfmt

      - name: Run linter
        run: cargo clippy -- -D warnings

      - name: Check formatting
        run: cargo fmt -- --check

      - name: Run Cucumber tests and generate JUnit report
        run: cargo test --test cucumber

      - name: Publish Test Report
        uses: actions/upload-artifact@v4
        if: always() # Upload report even if the test step fails
        with:
          name: junit-test-report
          path: target/junit/*.xml
```

This workflow demonstrates a standard CI setup for a Rust project, including
linting, formatting, and running the Cucumber tests. The final step ensures
that the test results are always available for inspection, providing a clear
and continuous record of the application's behavioural health.[^26]

### Conclusion

Behaviour-Driven Development with the `cucumber` crate offers a powerful
paradigm for building robust, well-documented, and correct Rust applications.
By shifting the focus from "testing" to "specifying behaviour," BDD fosters
collaboration and creates a shared language that bridges the gap between
business and technical teams.

For Rust developers, the `cucumber-rs` ecosystem provides a modern, idiomatic,
and high-performance toolset. Its async-first design, combined with the safety
of the `World`-based state management, makes it uniquely suited for writing the
comprehensive integration and E2E tests required by today's complex, I/O-bound
systems. By mastering the Gherkin syntax, embracing best practices for scenario
and step definition, and integrating these executable specifications into an
automated CI/CD pipeline, development teams can build higher-quality software
with greater confidence and clarity, ensuring that what they build is always
aligned with what is needed.

#### **Works cited**

[^1]: "Given When Then" Framework: a step-by-step guide with examples — Miro,
    accessed on 14 July 2025,
    <https://miro.com/agile/given-when-then-framework/>

[^2]: *Is it acceptable to write a "Given When Then When Then" test in
    Gherkin?* — Stack Overflow, accessed on 14 July 2025,
    <https://stackoverflow.com/questions/12060011/is-it-acceptable-to-write-a-given-when-then-when-then-test-in-gherkin>

[^3]: *Gherkin in Testing: A Beginner's Guide* — Rafał Buczyński, Medium,
    accessed on 14 July 2025,
    <https://medium.com/@buczynski.rafal/gherkin-in-testing-a-beginners-guide-f2e179d5e2df>

[^4]: *Given When Then* — Martin Fowler, accessed on 14 July 2025,
    <https://martinfowler.com/bliki/GivenWhenThen.html>

[^5]: How To Start Writing Gherkin Test Scenarios? -
    [Selleo.com](http://Selleo.com), accessed on 14 July 2025,
    <https://selleo.com/blog/how-to-start-writing-gherkin-test-scenarios>

[^6]: *Reference — Cucumber*, accessed on 14 July 2025,
    <https://cucumber.io/docs/gherkin/reference/>

[^7]: Given-When-Then - Wikipedia, accessed on 14 July 2025,
    <https://en.wikipedia.org/wiki/Given-When-Then>

[^8]: *Cucumber Rust Book — Introduction*, accessed on 14 July 2025,
    <https://cucumber-rs.github.io/cucumber/main/>

[^9]: Rust BDD tests with Cucumber - DEV Community, accessed on 14 July 2025
    <https://dev.to/rogertorres/rust-bdd-with-cucumber-4p68>

[^10]: cucumber - Rust - [Docs.rs](http://Docs.rs), accessed on 14 July 2025,
    <https://docs.rs/cucumber>

[^11]: *Quickstart* — Cucumber Rust Book, accessed on 14 July 2025,
    <https://cucumber-rs.github.io/cucumber/current/quickstart.html>

[^12]: on 14 July 2025,
    <https://www.florianreinhard.de/cucumber-in-rust-beginners-tutorial/>

[^13]: *Cucumber-rs* — fully-native Cucumber testing framework for Rust with no
    external test runners or dependencies. GitHub, accessed on 14 July 2025,
    <https://github.com/AidaPaul/cucumber-rust>

[^14]: Quickstart - Cucumber Rust Book, accessed on 14 July 2025,
    <https://cucumber-rs.github.io/cucumber/main/quickstart.html>

[^15]: Common Pitfalls and Troubleshooting in Cucumber - GeeksforGeeks, accessed
    on July 14, 2025,
    <https://www.geeksforgeeks.org/software-testing/common-pitfalls-and-troubleshooting-in-cucumber/>

[^16]: How to do error handling in Rust and what are the common pitfalls? -
    Stack Overflow, accessed on 14 July 2025,
    <https://stackoverflow.com/questions/30505639/how-to-do-error-handling-in-rust-and-what-are-the-common-pitfalls>

[^17]: *Writing scenarios with Gherkin syntax* — CucumberStudio Documentation,
    accessed on 14 July 2025,
    <https://support.smartbear.com/cucumberstudio/docs/bdd/write-gherkin-scenarios.html>

[^18]: Data tables - Cucumber Rust Book, accessed on 14 July 2025,
    <https://cucumber-rs.github.io/cucumber/main/writing/data_tables.html>

[^19]: Best practices for scenario writing | CucumberStudio Documentation

[^20]: Cucumber Best Practices to follow for efficient BDD Testing | by
    KailashPathak - Medium, accessed on 14 July 2025,
    <https://kailash-pathak.medium.com/cucumber-best-practices-to-follow-for-efficient-bdd-testing-b3eb1c7e9757>

[^21]: Rust Solutions - WireMock, accessed on 14 July 2025,
    <https://wiremock.org/docs/solutions/rust/>

[^22]: Common Challenges in Cucumber Testing and How to Overcome Them - Medium,
    accessed on July 14, 2025,
    <https://medium.com/@realtalkdev/common-challenges-in-cucumber-testing-and-how-to-overcome-them-dc95fffb43c8>

[^23]: Cucumber in cucumber - Rust - [Docs.rs](http://Docs.rs), accessed on
    14 July 2025,
    <https://docs.rs/cucumber/latest/cucumber/struct.Cucumber.html>

[^24]: CLI (command-line interface) - Cucumber Rust Book, accessed on
    14 July 2025, <https://cucumber-rs.github.io/cucumber/main/cli.html>

[^25]: Continuous Integration - Cucumber, accessed on 14 July 2025,
    <https://cucumber.io/docs/guides/continuous-integration>

[^26]: Setting up effective CI/CD for Rust projects - a short primer -
    [shuttle.dev](http://shuttle.dev), accessed on 14 July 2025,
    <https://www.shuttle.dev/blog/2025/01/23/setup-rust-ci-cd>
