# srgn: Syntax-Aware Search and Replace

Imagine you need to refactor code *fast*—safely, across an entire project.
`srgn` is your scalpel: regex precision combined with language awareness
(via `tree-sitter`).

## 🚀 Basic Usage

```sh
# Replace text
echo 'Hello World!' | srgn '[wW]orld' -- 'there'
# → Hello there!

# Search mode (like ripgrep, but syntax-aware)
srgn --python 'class' 'MyClass' src/

# Replace only in Python imports
srgn --py 'module-names-in-imports' '^old_utils$' -- 'new_core_utils' src/

# Convert print() to logging
srgn --py 'call' '^print\((.*)\)$' -- 'logging.info($1)' src/ --dry-run

# Annotate unsafe Rust blocks
srgn --rs 'unsafe' 'unsafe' -- '// TODO: Justify\nunsafe' src/
```

## 🔑 Command Anatomy

```sh
srgn [scopes/actions] 'regex' -- 'replacement' [files...]
```

- **Scopes**: Limit where to search (`--py 'class'`, `--rs 'unsafe'`).
- **Regex**: Final filter applied.
- **Replacement**: Optional. Use `$1`, `$2` for captures.
- **Files**: If omitted, stdin is used.
- ``: Show a diff without writing.

## 🧭 Core Ideas

- **Scopes**: Define *where* (docstrings, imports, unsafe blocks).
- **Regex**: Defines *what* to match inside that scope.
- **Actions**: Transform matches (`--upper`, `--delete`, `--squeeze`).
- **Pipeline**: Scopes chain with AND by default; use `-j` for OR.

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

---

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

---

### 3. General Guidelines

- **Use single quotes** for regex and replacement arguments. This prevents Bash from interpreting `$1`, backticks, and `\n`.
- **Escape carefully**: within single quotes, you usually don’t need double escaping, but when combining with regex you may.
- **Dry run first**: always add `--dry-run` until you’re confident the pattern is correct.
- **Test small**: pipe a short snippet with `echo` into `srgn` before unleashing on the whole codebase.

---

#### Fixed Examples

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

- Use `--dry-run` to preview changes.

## 📚 Scope Reference

### Python (`--py`)

- `class`, `function`, `doc-strings`, `comments`, `strings`,
  `identifiers`, `module-names-in-imports`, `call`

### Rust (`--rs`)

- `unsafe`, `comments`, `strings`, `attribute`, `names-in-uses-declarations`,
  `pub-enum`, `type-identifier`, `struct`, `impl`, `fn`, `extern-crate`

## 🛠 When to Use

- **grep/ripgrep**: fast, dumb text search.
- **sed/awk**: fast, line-based replace.
- **srgn**: syntax-aware batch surgery (imports, unsafe, print→logging).

---

`srgn`: grep with a scalpel.

