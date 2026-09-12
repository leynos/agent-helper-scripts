# Documentation library

This directory holds the canonical edition of every guidance document that is
shared across the `github.com/leynos` estate. Each estate repository carries
its own copy of these documents under `docs/`; over time those copies drift
as individual repositories fix, extend, or trim them. The library exists so
that a repository can refresh its copy from a single agreed source, and so
that improvements made in one repository are not lost to the others.

## How the canonical editions were produced

Every `docs/` directory across the estate inventory was surveyed. A document
qualified for the library when the same file appeared in at least two
repositories and its content was general guidance rather than a description
of one repository. Names that recur but are always repository-specific
(`users-guide.md`, `developers-guide.md`, `roadmap.md`, `contents.md`,
`repository-layout.md`, execution plans, and audits) were excluded.

One document, the v2a front-end stack, was added after the initial survey at
the maintainer's request. Its third copy lives in `axinite-mockup`, which the
estate inventory does not list, so a copy held only by an off-inventory
repository can be missed by the survey method described here.

For each qualifying document the distinct content variants were identified and
compared against a base edition:

- For general guidance, the base is the most complete and most recent edition,
  which is usually, but not always, the largest.
- For a library's users' guide, the base is the library's own repository.

Every other variant was then diffed against the base. Additions of general
benefit (new sections, corrected facts, newer tool versions, repaired
examples) were folded into the canonical text. Repository-specific material
(crate and project names, local paths, Makefile targets, and examples that
only make sense in one project) was generalized or removed, including where
it appeared in the base itself.

## Conventions

- Documents follow the [documentation style guide](documentation-style-guide.md):
  en-GB Oxford spelling, prose wrapped at 80 columns, dash bullets, and a
  language on every fenced code block.
- Cross-references between library documents use bare relative filenames so
  that they resolve inside this directory and inside any `docs/` directory
  that vendors the same set.
- Library users' guides keep their upstream filename convention
  (`<library>-users-guide.md`) so they can be dropped into a consuming
  repository unchanged.

## Refreshing a repository copy

Copy the canonical file over the repository's `docs/` copy and review the
diff. If the repository's copy carried a general improvement that the library
lacks, add it here first and then refresh; if it carried repository-specific
notes, keep those in a repository-owned document rather than in the shared
file.

## Catalogue

The "copies" column counts the estate repositories holding the document at
the time of the survey; "variants" counts the distinct editions found among
those copies.

### Writing and engineering practice

| Document | Copies | Variants |
| --- | --- | --- |
| [Documentation style guide](documentation-style-guide.md) | 85 | 32 |
| [Scripting standards](scripting-standards.md) | 61 | 29 |
| [Navigating code complexity: a guide for implementers and maintainers](complexity-antipatterns-and-refactoring-strategies.md) | 57 | 23 |
| [Local validation of GitHub Actions with act and pytest (black-box)](local-validation-of-github-actions-with-act-and-pytest.md) | 16 | 11 |
| [Creating a template - copier](creating-a-copier-template.md) | 2 | 1 |
| [Configuring a template - copier](configuring-a-copier-template.md) | 2 | 1 |

### Rust

| Document | Copies | Variants |
| --- | --- | --- |
| [Mastering test fixtures in Rust with `rstest`](rust-testing-with-rstest-fixtures.md) | 51 | 24 |
| [A Systematic Guide to Effective, Ergonomic, and DRY Doctests in Rust](rust-doctest-dry-guide.md) | 50 | 26 |
| [Reliable testing in Rust via dependency injection](reliable-testing-in-rust-via-dependency-injection.md) | 47 | 9 |
| [A Developer's Guide to Behavioural Testing in Rust with Cucumber](behavioural-testing-in-rust-with-cucumber.md) | 4 | 4 |
| [Architecting localizable Rust libraries with Fluent](localizable-rust-libraries-with-fluent.md) | 5 | 5 |
| [A comprehensive guide to testing logos, chumsky, and rowan parsers in Rust](rust-parser-testing-comprehensive-guide.md) | 2 | 2 |
| [Don't panic: a hitchhiker’s guide to building an error-recovering parser with Chumsky](building-an-error-recovering-parser-with-chumsky.md) | 2 | 2 |

### Python

| Document | Copies | Variants |
| --- | --- | --- |
| [Testing SQLAlchemy 2.x with Postgres: PyTest and py-pglite Guide](testing-sqlalchemy-with-pytest-and-py-pglite.md) | 2 | 2 |
| [A comprehensive guide to testing asynchronous Falcon endpoints with pytest](testing-async-falcon-endpoints.md) | 2 | 2 |
| [A Comprehensive Guide to Asynchronous SQLAlchemy 2.0 with PostgreSQL and Falcon](async-sqlalchemy-with-pg-and-falcon.md) | 2 | 2 |

### Front end

`v2a` is the estate's shared front-end model and stack; the remaining
front-end documents describe parts of it in depth.

| Document | Copies | Variants |
| --- | --- | --- |
| [v2a front-end stack](v2a-front-end-stack.md) | 3 | 3 |
| [Tailwind CSS v4 LLM Development Guidelines](tailwind-v4-guide.md) | 5 | 5 |
| [Tailwind CSS v4 (May 2025)](tailwind-v3-v4-migration-guide.md) | 5 | 5 |
| [daisyUI 5](daisyui-v5-guide.md) | 5 | 5 |
| [Quick guide: semantics + utilities with Tailwind v4, daisyUI v5, and Radix](semantic-tailwind-with-daisyui-best-practice.md) | 4 | 4 |
| [Front‑End Semantic Linting — Implementation Guide (BiomeJS + GritQL first)](enforcing-semantic-tailwind-best-practice.md) | 4 | 4 |
| [React + Tailwind with Bun 1.3.0 — a short, no‑nonsense guide](react-tailwind-with-bun.md) | 4 | 3 |
| [A Comprehensive Architectural Guide to Pure, Accessible, and Localizable React Components with Radix, Tanstack, and DaisyUI](pure-accessible-and-localizable-react-components.md) | 4 | 4 |
| [An Architectural Blueprint for High-Velocity, Accessibility-First Testing](high-velocity-accessibility-first-component-testing.md) | 4 | 4 |
| [Data model-driven card architecture](data-model-driven-card-architecture.md) | 4 | 3 |
| [The Definitive Guide to Building Accessible and Responsive Progressive Web Applications](building-accessible-and-responsive-progressive-web-applications.md) | 4 | 4 |
| [Architecting Resilient Local-First Applications in React: An Expert Guide to Zustand, Tanstack Query, and Real-Time Synchronization](local-first-react.md) | 2 | 2 |
| [Mocking services with Simulacrum, actors, and stable keyset connections](mocking-services-with-simulacrum-actors-and-stable-keyset-connections.md) | 2 | 2 |

### Infrastructure

| Document | Copies | Variants |
| --- | --- | --- |
| [OpenTofu HashiCorp Configuration Language (HCL) coding standards](opentofu-coding-standards.md) | 4 | 3 |
| [A comprehensive developer's guide to HashiCorp configuration language (HCL) for OpenTofu](opentofu-hcl-syntax-guide.md) | 4 | 4 |
| [A Comprehensive Guide to Unit Testing OpenTofu Modules and Scripts](opentofu-module-unit-testing-guide.md) | 4 | 4 |
| [Using Cloudflare DNS with OpenTofu](using-cloudflare-dns-with-opentofu.md) | 2 | 2 |

### Library users' guides

These guides are owned by the library repositories named below; the canonical
edition is that repository's own `docs/users-guide.md`, and the copies found
elsewhere are vendored snapshots.

| Document | Upstream repository | Copies | Variants |
| --- | --- | --- | --- |
| [`rstest-bdd` user's guide](rstest-bdd-users-guide.md) | `rstest-bdd` | 30 | 23 |
| [OrthoConfig user's guide](ortho-config-users-guide.md) | `ortho-config` | 17 | 15 |
| [Whitaker User's Guide](whitaker-users-guide.md) | `whitaker` | 10 | 10 |
| [pg_embedded_setup_unpriv user guide](pg-embed-setup-unpriv-users-guide.md) | `pg-embed-setup-unpriv` | 5 | 5 |
| [CmdMox Usage Guide](cmd-mox-users-guide.md) | `cmd-mox` | 4 | 3 |
| [Lading user guide](lading-users-guide.md) | `lading` | 3 | 2 |
| [Wireframe library guide](wireframe-users-guide.md) | `wireframe` | 2 | 2 |
| [Femtologging user guide](femtologging-users-guide.md) | `femtologging` | 2 | 2 |
| [cuprum Users' Guide](cuprum-users-guide.md) | `cuprum` | 2 | 2 |
