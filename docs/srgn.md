# srgn: Syntax-Aware Search and Replace

Imagine you need to refactor code *fast*—safely, across an entire project. `srgn` is your scalpel: regex precision combined with language awareness (via `tree-sitter`).

## 🚀 Basic Usage

```sh
# Replace text
# The double hyphen delimits commands and replacements.
# The value after the double hyphen ('--') is a replacement.
# The value before is a search pattern.
# With no files specified, srgn operates on stdin
echo 'Hello World!' | srgn '[wW]orld' -- 'there'
# → Hello there!
```

```sh
# Use -G (--glob) to specify files
# Search mode (like ripgrep, but syntax-aware)
srgn -G 'src/**' --py 'class' 'MyClass'
```

```sh
# Replace only in Python imports
# Files are edited destructively in place, unless --dry-run is specified
srgn -G 'src/**/*.py' --py 'module-names-in-imports' '^old_utils$' -- 'new_core_utils'
```

```sh
# Use the function call scope, narrowed by a regex
# Convert print() to logging
srgn -G 'src/**/*.py' --py 'call' '^print\((.*)\)$' -- 'logging.info($1)'
```

```sh
# Annotate unsafe Rust blocks with a comment
srgn -G 'src/**/*.rs' --rs 'unsafe' 'unsafe' -- $'// TODO: Justify unsafe'
```

## 🔑 Command Anatomy

```sh
srgn [GLOBAL OPTIONS] [LANGUAGE SCOPES] 'REGEX' -- 'REPLACEMENT'
```

- **Global options**: `-G/--glob`, `--dry-run`, `--fail-no-files`, etc. → always **before** regex.
- **Language scopes**: `--py 'class'`, `--rs 'unsafe'`, etc. → also before regex.
- **Regex**: final filter. The last positional argument before the `--` separator.
- **Double hyphen (`--`) separator**: disambiguates. After this, only the replacement string is allowed.
- **Replacement**: exactly one string. Use `$1`, `$2` for capture groups.

👉 **Rule**: once you type `--`, no more flags or globs are allowed. Everything goes before.

### Examples

Correct:

```bash
srgn -G 'src/file.rs' --dry-run --rs 'fn~motion_cases' 'for b in &blocks' -- 'for b in blocks'
```

Incorrect (extra args after replacement → error):

```bash
srgn --rs 'fn~motion_cases' 'for b in &blocks' -- 'for b in blocks' -G src/file.rs --dry-run
```

## 🧭 Core Ideas

- **Scopes**: Define *where* (docstrings, imports, unsafe blocks).
- **Regex**: Defines *what* to match inside that scope.
- **Actions**: Transform matches (`--upper`, `--delete`, `--squeeze`).
- **Pipeline**: Scopes chain with AND by default; use `-j` for OR.

## 🎯 Think in Scopes, Not Mega‑Regex

A common mistake when starting with `srgn` is trying to write one massive multi‑line regex to match an entire function or block of code. This almost always leads to quoting headaches, brittle patterns, and confusing regex errors. The better way is to let `srgn` do the heavy lifting with **language scopes**.

### What is a Scope?

A scope tells `srgn` *where* in the code to look. Instead of scanning raw text, `srgn` asks the parser (via `tree‑sitter`) for specific syntactic regions—functions, imports, attributes, unsafe blocks, comments, and so on. You then layer a small regex *inside* that scope to match exactly what you need.

### Why This Matters

- **Less regex pain**: No more `([\s\S]*?)` monsters just to cross newlines.
- **Safer**: You won’t accidentally match across unrelated code.
- **Readable**: Commands describe intent clearly—`--rust 'unsafe'` is self‑explanatory.
- **Composable**: Chain scopes together (`--py 'class' --py 'doc-strings' 'TODO'`).

### Example: Replace an Entire Function

Instead of one brittle regex:

```bash
srgn $'fn emit_non_strict_warnings[\s\S]*?\n}' -- $'fn emit_non_strict_warnings(...) { ... }'
```

Use scopes:

```bash
srgn --rs 'fn~emit_non_strict_warnings' \
     '(?s).*' -- $'fn emit_non_strict_warnings(missing: &[(proc_macro2::Span, String)]) { ... }'
```

Here `--rust 'fn~emit_non_strict_warnings'` selects the function body for you; `(?s).*` just says “replace all of it.”

### Example: Insert Blank Line Before `#[test]`

Bad way (regex‑only, fragile):

```bash
srgn '}\n    #\[test\]' -- $'}\n\n    #[test]'
```

Better way (scoped + small regex):

```bash
srgn --rs 'fn' $'}\n\s*(#\[test\])' -- $'}\n\n$1'
```

### Rule of Thumb

1. Pick the narrowest **scope** (`fn`, `comments`, `strings`, `uses`).
2. Apply a **small regex** inside.
3. Pass your **replacement** after `--`.

👉 If you find yourself writing a regex with `{`, `}`, and `\s\S`, stop—there’s probably a scope for that.

## 📚 Scope Reference

### Python (`--py`)

Scopes (no parameterised variants at present):

- `class`, `function`, `doc-strings`, `comments`, `strings`, `identifiers`, `module-names-in-imports`, `call`

> **Tip:** Narrow with a Python scope, then use a concise regex for the exact target. Example: find TODOs only in docstrings:
>
> ```bash
> srgn -G 'src/**/*.py' --py 'doc-strings' 'TODO'
> ```

### TypeScript (`--ts` / `--typescript`)

Scopes (no parameterised variants):

- `comments`, `strings`, `imports` (module specifiers)
- `function`, `async-function`, `sync-function`
- `method`, `constructor`, `class`
- `enum`, `interface`
- `try-catch`
- `var-decl`, `let`, `const`, `var`
- `type-params`, `type-alias`
- `namespace`, `export`

> **Tips**
> - Use `imports` to touch only module specifiers in `import … from '…'`.
> - Use `var` to target the `var` keyword **inside** declarations without hitting `var` in strings or comments.
> - Use `try-catch` to constrain edits (e.g., logging changes) to exception-handling blocks only.

### Rust (`--rs`)

Rust offers both **plain** scopes and **parameterised** scopes of the form `name~<PATTERN>`, where `<PATTERN>` is a regex matched against the **item name** (not its path). Parameterised variants are marked **(param)** below.

**General/textual:**

- `comments`, `doc-comments`, `strings`, `uses`, `attribute`, `identifier`, `type-identifier`, `closure`, `unsafe`

**Items (parameterisable where noted):**

- `struct~<PATTERN>` **(param)**
- `enum~<PATTERN>` **(param)**, `enum-variant`
- `trait~<PATTERN>` **(param)**
- `mod~<PATTERN>` **(param)**, `mod-tests`
- `fn~<PATTERN>` **(param)**, plus filtered variants:
  - `impl-fn`, `priv-fn`, `pub-fn`, `pub-crate-fn`, `pub-self-fn`, `pub-super-fn`, `const-fn`, `async-fn`, `unsafe-fn`, `extern-fn`, `test-fn`
- `type-def`, `extern-crate`
- `impl` (all impl blocks), `impl-type` (inherent impl Type {}), `impl-trait` (trait impl impl Trait for Type {})

> **Parameter semantics:** For `name~<PATTERN>`, `<PATTERN>` matches the **identifier name** only. Example: `--rs 'fn~emit_non_strict_warnings'` selects just that function, not calls to it.

#### Locating a specific `impl` (non‑parameterised)

Because `impl` / `impl-type` / `impl-trait` **do not** take `~<PATTERN>`, combine the appropriate scope with a targeted regex on the header line.

**Trait impl: impl MyTrait for MyType**

```bash
# Search only
srgn -G 'src/**/*.rs' --rs 'impl-trait' 'impl MyTrait for MyType'
```

**Inherent impl: impl MyType { ... }**

```bash
# Search only
srgn -G 'src/**/*.rs' --rs 'impl-type' 'impl MyType'
```

**Narrow further to avoid false positives:**

- Prefer `impl-trait` vs `impl-type` instead of the generic `impl`.
- Add nearby context to the regex (e.g., include where-clause text or a unique method name) if names are common.

**Replace the entire impl block (example):**

```bash
# Select the impl block with the scope, then replace its contents
srgn -G 'src/**/*.rs' --rs 'impl-trait' '(?s).*' -- 'impl MyTrait for MyType { /* TODO */ }'
```

## 🔬 Tree‑sitter queries (advanced)

When scopes aren’t enough—e.g. you need to express *relationships* between nodes ("methods inside impls for a given trait and type", "items with a particular attribute attached")—use **tree‑sitter queries**. These are S‑expressions that select syntax nodes structurally. In `srgn`, a tree‑sitter query becomes **the scope**; you then add a small regex and optional replacement as usual.

> Heuristic: **Prefer scopes + small regex** for single‑node matching (docstrings, strings, identifiers, a specific `fn` by name). **Prefer tree‑sitter queries** when you need multi‑node constraints (ancestor/descendant or sibling relations) that a single named scope can’t express.

### Rust CLI (`--rust-query`)

**Example A — list impls for a given trait (search‑only):**

```bash
srgn -G 'src/**/*.rs' \
  --rust-query '
  (impl_item
    trait: (type_path (type_identifier) @trait)
    type: (type_identifier) @type)
  (#eq? @trait "Display")
  ' \
  '.*'
```

This scope matches only `impl Display for <Type>` blocks. The `' .* '` regex is just a trivial match to print each scope’s header lines.

**Example B — rename a method only inside those impls:**

```bash
srgn -G 'src/**/*.rs' \
  --rust-query '
  (impl_item
    trait: (type_path (type_identifier) @trait)
    (declaration_list (function_item name: (identifier) @method)))
  (#eq? @trait "Display")
  ' \
  '^as_str$' -- 'to_string'
```

Only method identifiers named `as_str` *within* `impl Display for …` are touched; calls elsewhere are unaffected.

**Example C — target inherent impl for a specific type (with generics tolerated):**

```bash
srgn -G 'src/**/*.rs' \
  --rust-query '
  (impl_item
    type: [(type_identifier) (type_arguments (type_identifier))] @ty)
  ' \
  '^MyType$' -- $'impl MyType { /* TODO */ }'
```

The query selects all inherent `impl` blocks and exposes the type identifier as text for the regex to match (`MyType`).

### TypeScript CLI (`--typescript-query`)

**Example A — rewrite imports from a specific module**
```bash
srgn -G 'src/**/*.{ts,tsx}' \
  --typescript-query '
  (import_statement
    source: (string) @src)
  ' \
  '@old/lib' -- '@new/lib'
```
Scopes to `import` statements and lets the regex touch only the module specifier text inside them.

**Example B — rename a method by structural position (definitions only)**
```bash
srgn -G 'src/**/*.{ts,tsx}' \
  --typescript-query '
  (class_declaration
    (class_body
      (method_definition
        name: (property_identifier) @name)))
  ' \
  '^ngOnInit$' -- 'onInit'
```
Targets **method definitions** named `ngOnInit` without touching call sites or similarly named variables.

**When to prefer tree-sitter over scope + regex**
- You need multi-node relationships: “methods *inside* classes” or “methods inside classes with a particular decorator”.
- You want to constrain edits to a syntactic position, not just a token string (e.g., rename only **definitions**, not calls).
- Named scopes aren’t precise enough (e.g., `class` + regex is fine for `implements Interface`, but decorator-gated edits usually want a structural query).

### Python

At present the CLI exposes custom query flags for Rust (`--rust-query`) and TypeScript (`--typescript-query`), **not** Python. For Python you’ll usually:

- Use the prepared scopes (`--py 'function'`, `--py 'strings'`, `--py 'module-names-in-imports'`) **plus** a small regex; or
- Drop to the **library** if you need a true tree‑sitter query (e.g., “functions with a specific decorator”, “async defs returning `Awaitable[T]`”).

**Approximate example — change calls only in test functions (scope + regex):**

```bash
# Limit to function defs, then small regex for call names
srgn -G 'tests/**/*.py' --py 'function' '^print\(' -- 'logger.info('
```

For decorator‑sensitive refactors (e.g., only functions decorated with `@pytest.mark.parametrize`), the CLI can’t currently express the *decorator → function* relation directly. Use the library’s tree‑sitter API for that level of structure.

---

## 🧪 Real-World Recipes

### TypeScript

- **Migrate import sources** (module specifiers only)

```bash
srgn -G 'src/**/*.{ts,tsx}' --typescript 'imports' '^@old/lib$' -- '@new/lib'
```

- **Prefer `let` over `var` in declarations**

```bash
srgn -G 'src/**/*.{ts,tsx}' --typescript 'var' '\bvar\b' -- 'let'
```

- **Harden error logging inside `try/catch` only**

```bash
srgn -G 'src/**/*.{ts,tsx}' --typescript 'try-catch' 'console\.log\(' -- 'console.error('
```

- **Find classes implementing an interface** (search-only)

```bash
srgn -G 'src/**/*.{ts,tsx}' --typescript 'class' 'implements\s+MyInterface\b'
```

### Python

- **Rename imports**

```sh
srgn --py 'module-names-in-imports' '^old_utils$' -- 'new_core_utils' src/
```

- **Find functions missing docstrings**

```sh
srgn --py 'function' 'def\s+\w+\(.*\):\n\s+[^"'#\s]'
```

### Rust

- **Upgrade lint attributes**

```sh
srgn --rs 'attribute' 'allow\((clippy::some_lint)\)' -- 'expect($1)' src/
```

- **Mass crate renaming in use declarations**

```sh
srgn --rs 'names-in-uses-declarations' '^old_api' -- 'new_api' src/
```

## ⚠️ Common Pitfalls Using `srgn`

### 1. Bash interpreting replacements as commands

Example:

```sh
srgn --glob crates/rstest-bdd-macros/src/step_keyword.rs "centralised in\n//! `validation::steps::resolve_keywords` ..." -- "centralized in\n//! `validation::steps::resolve_keywords` ..."
```

**Problem**: Backticks (`` `...` ``) are *shell command substitution*. Bash tries to execute `validation::steps::resolve_keywords`.

**Fix**: Always quote or escape backticks inside patterns and replacements. For safety, prefer single quotes.

```sh
srgn --glob crates/rstest-bdd-macros/src/step_keyword.rs \
  'centralised in\n//! `validation::steps::resolve_keywords` and consumed by code generation,' \
  -- 'centralized in\n//! `validation::steps::resolve_keywords` and consumed by validation and code generation,'
```

Or escape backticks:

```sh
\`validation::steps::resolve_keywords\`
```

### 2. Invalid regex errors

Example:

```sh
srgn --glob crates/... 'rejects_invalid_keyword_via_from_str\(\) {\n ...' -- '...'
```

**Problem**: Regex parsing fails because you’re trying to match across *multiple lines* with explicit `\n`. By default, regex engines don’t treat `.` as spanning newlines, and `srgn` requires the pattern to fully parse.

**Fix options**:

- Use the `(?s)` flag (`dotall`) so `.` matches newlines.

```sh
'(?s)rejects_invalid_keyword_via_from_str\(\).*?\#\[test\]'
```

- Or keep `\n` but make sure all braces/escapes are balanced. Your original pattern likely ended prematurely.

### 3. General Guidelines

- **Use single quotes** for regex and replacement arguments. This prevents Bash from interpreting `$1`, backticks, and `\n`.
- **Escape carefully**: within single quotes, you usually don’t need double escaping, but when combining with regex you may.
- **Measure twice, cut once:** Use `--dry-run` to preview changes. Always add `--dry-run` (before the `--`, until you’re confident the pattern is correct.)
- **Test small**: pipe a short snippet with `echo` into `srgn` before unleashing on the whole codebase.

#### Further Examples

##### Import comment replacement

```sh
srgn --glob crates/rstest-bdd-macros/src/step_keyword.rs \
  'centralised in\n//! `validation::steps::resolve_keywords` and consumed by code generation,' \
  -- 'centralized in\n//! `validation::steps::resolve_keywords` and consumed by validation and code generation,'
```

##### Function test refactor

```sh
srgn --glob crates/rstest-bdd-macros/src/step_keyword.rs \
  '(?s)rejects_invalid_keyword_via_from_str\(\).*?\#\[test\]' \
  -- 'rejects_invalid_keyword_via_from_str() {\n        assert!("invalid".parse::<StepKeyword>().is_err());\n    }\n\n    #[test]'
```

## 🛠 When to Use

- **grep/ripgrep**: fast, dumb text search.
- **sed/awk**: fast, line-based replace.
- **srgn**: syntax-aware batch surgery (imports, unsafe, print→logging).

---

`srgn`: grep with a scalpel.
