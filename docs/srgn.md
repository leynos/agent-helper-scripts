# srgn: Syntax-Aware Search and Replace

Imagine you need to refactor code *fast*—safely, across an entire project. `srgn` is your scalpel: regex precision combined with language awareness (via `tree-sitter`).

## 🚀 Basic Usage

```sh
# Replace text
echo 'Hello World!' | srgn '[wW]orld' -- 'there'
# → Hello there!

# Search mode (like ripgrep, but syntax-aware)
srgn -G 'src/**' --py 'class' 'MyClass'

# Replace only in Python imports
srgn -G 'src/**/*.py' --py 'module-names-in-imports' '^old_utils$' -- 'new_core_utils'

# Convert print() to logging
srgn -G 'src/**/*.py' --dry-run --py 'call' '^print\((.*)\)$' -- 'logging.info($1)'

# Annotate unsafe Rust blocks
srgn -G 'src/**/*.rs' --rs 'unsafe' 'unsafe' -- $'// TODO: Justify
unsafe'
```

## 🔑 Command Anatomy

```sh
srgn [GLOBAL OPTIONS] [LANGUAGE SCOPES] 'REGEX' -- 'REPLACEMENT'
```

- **Global options**: `-G/--glob`, `--dry-run`, `--fail-no-files`, etc. → always **before** regex.
- **Language scopes**: `--py 'class'`, `--rs 'unsafe'`, etc. → also before regex.
- **Regex**: final filter. The last positional argument before the `--` separator.
- ``\*\* separator\*\*: disambiguates. After this, only the replacement string is allowed.
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

- `class`, `function`, `doc-strings`, `comments`, `strings`, `identifiers`, `module-names-in-imports`, `call`

### Rust (`--rs`)

- `unsafe`, `comments`, `strings`, `attribute`, `names-in-uses-declarations`, `pub-enum`, `type-identifier`, `struct`, `impl`, `fn`, `extern-crate`

## 🧪 Real-World Recipes

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
- **Dry run first**: always add `--dry-run` until you’re confident the pattern is correct.
- **Test small**: pipe a short snippet with `echo` into `srgn` before unleashing on the whole codebase.
- **Measure twice, cut once:** Use `--dry-run` to preview changes.

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

