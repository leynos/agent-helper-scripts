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

## ⚠️ Safety

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

