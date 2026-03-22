# Migration Reference

Gotchas and patterns for teams moving from ESLint and/or Prettier.

## From ESLint

### Running the Migration Tool

Biome provides a migration command:

```bash
npx biome migrate eslint --write
```

This reads `.eslintrc.*` and updates `biome.json`. **Review the output carefully**—not all rules map directly.

### Rule Name Differences

Biome uses its own rule names. Common mappings:

| ESLint | Biome |
|--------|-------|
| `no-unused-vars` | `correctness/noUnusedVariables` |
| `no-console` | `suspicious/noConsoleLog` |
| `eqeqeq` | `suspicious/noDoubleEquals` |
| `prefer-const` | `style/useConst` |
| `prefer-template` | `style/useTemplate` |
| `no-var` | `style/noVar` |
| `@typescript-eslint/no-explicit-any` | `suspicious/noExplicitAny` |
| `@typescript-eslint/consistent-type-imports` | `style/useImportType` |
| `react-hooks/exhaustive-deps` | `correctness/useExhaustiveDependencies` |
| `react/jsx-key` | `correctness/useJsxKeyInIterable` |

### Rules Without Direct Equivalents

Some ESLint rules have no Biome equivalent (yet). Check the Biome documentation or issue tracker.

**Common gaps:**
- Complex `import/order` configurations (Biome's import sorting is less configurable)
- Some `@typescript-eslint` rules around type-aware linting
- Plugin-specific rules (e.g., `eslint-plugin-jest`)

### Behavioural Differences

**Unused variables:**
ESLint's `no-unused-vars` has complex ignore patterns. Biome's `noUnusedVariables` uses underscore prefix convention:

```typescript
// ESLint: often configured to allow unused args
function handler(req, res, _next) {}

// Biome: prefix with _ to mark intentionally unused
function handler(_req, res, _next) {}
```

**Type imports:**
Biome's `useImportType` is stricter than `@typescript-eslint/consistent-type-imports`. It will flag more cases.

**React hooks:**
Biome's `useExhaustiveDependencies` may flag different patterns than `react-hooks/exhaustive-deps`. Test thoroughly.

### ESLint Plugins

Biome doesn't support ESLint plugins. Built-in coverage:

| Plugin | Biome Coverage |
|--------|----------------|
| `@typescript-eslint` | Partial—many rules built-in |
| `eslint-plugin-react` | Good—most JSX rules covered |
| `eslint-plugin-react-hooks` | Yes—`useExhaustiveDependencies` |
| `eslint-plugin-import` | Partial—basic import rules |
| `eslint-plugin-jsx-a11y` | Yes—`a11y` category |
| `eslint-plugin-jest` | No |
| `eslint-plugin-testing-library` | No |

For unsupported plugins, consider running ESLint alongside Biome for those specific rules.

### Coexistence Pattern

Run both tools during migration:

```json
{
  "scripts": {
    "lint": "biome check . && eslint --ext .ts,.tsx src/",
    "lint:biome": "biome check .",
    "lint:eslint": "eslint --ext .ts,.tsx src/"
  }
}
```

Configure ESLint to handle only rules Biome doesn't cover:

```javascript
// .eslintrc.js
module.exports = {
  extends: ['plugin:jest/recommended'],
  rules: {
    // Disable rules Biome handles
    'no-unused-vars': 'off',
    'prefer-const': 'off',
    // ... etc
  }
};
```

## From Prettier

### Running the Migration Tool

```bash
npx biome migrate prettier --write
```

This reads `.prettierrc` and updates `biome.json` formatter settings.

### Configuration Mapping

| Prettier | Biome | Notes |
|----------|-------|-------|
| `printWidth` | `lineWidth` | Default 80 |
| `tabWidth` | `indentWidth` | Default 2 |
| `useTabs` | `indentStyle: "tab"` | Default "space" |
| `semi` | `javascript.formatter.semicolons` | "always" or "asNeeded" |
| `singleQuote` | `javascript.formatter.quoteStyle` | "single" or "double" |
| `trailingComma` | `javascript.formatter.trailingCommas` | "all", "es5", "none" |
| `bracketSpacing` | `javascript.formatter.bracketSpacing` | Boolean |
| `arrowParens` | `javascript.formatter.arrowParentheses` | "always" or "asNeeded" |
| `endOfLine` | `formatter.lineEnding` | "lf", "crlf", "cr" |

### Formatting Differences

Biome's formatter produces **different output** from Prettier. Expect diffs. Key differences:

**Object formatting:**
```typescript
// Prettier
const obj = { a: 1, b: 2 };

// Biome (may differ in spacing/breaking decisions)
const obj = { a: 1, b: 2 };
```

**JSX formatting:**
Biome makes different line-breaking decisions for JSX attributes.

**Import sorting:**
Biome's import organizer groups differently than Prettier's plugins.

### Handling the Diff Storm

When switching formatters, you'll get massive diffs. Strategies:

**Option 1: Big Bang**
```bash
npx biome format --write .
git add -A
git commit -m "chore: migrate to Biome formatting"
```

**Option 2: Directory at a Time**
```bash
npx biome format --write src/components/
git add -A && git commit -m "chore: biome format components"
```

**Option 3: Use git blame ignore**
Add the formatting commit to `.git-blame-ignore-revs`:

```bash
# .git-blame-ignore-revs
# Biome formatting migration
abc123def456...
```

Configure git:
```bash
git config blame.ignoreRevsFile .git-blame-ignore-revs
```

### Prettier-Specific Features Not in Biome

- **Markdown formatting**: Biome doesn't format Markdown
- **HTML formatting**: Limited support
- **CSS formatting**: Coming (check current status)
- **Plugin ecosystem**: No Prettier plugins

For these, keep Prettier alongside Biome:

```json
{
  "scripts": {
    "format": "biome format --write . && prettier --write '**/*.md'"
  }
}
```

### Editor Integration Conflicts

If you have both Prettier and Biome extensions installed, they'll fight over formatting.

**VS Code**: Disable Prettier for JS/TS files:

```json
// .vscode/settings.json
{
  "[javascript]": {
    "editor.defaultFormatter": "biomejs.biome"
  },
  "[typescript]": {
    "editor.defaultFormatter": "biomejs.biome"
  },
  "[json]": {
    "editor.defaultFormatter": "biomejs.biome"
  }
}
```

## Unified Migration Checklist

### Pre-Migration

- [ ] Document current ESLint rules and why they exist
- [ ] Document Prettier configuration
- [ ] Identify ESLint plugins that Biome doesn't cover
- [ ] Decide on coexistence vs full replacement strategy

### Migration

- [ ] Install Biome: `npm i -D @biomejs/biome`
- [ ] Run `npx biome migrate eslint --write`
- [ ] Run `npx biome migrate prettier --write`
- [ ] Review generated `biome.json`
- [ ] Run `npx biome check .` and assess violations
- [ ] Configure overrides for test files, config files, etc.
- [ ] Run `npx biome check --write .` to apply fixes

### Post-Migration

- [ ] Update CI pipeline (see `references/ci-hooks.md`)
- [ ] Update editor configurations
- [ ] Update pre-commit hooks
- [ ] Remove ESLint/Prettier (or configure coexistence)
- [ ] Update contributing docs
- [ ] Add formatting commit to `.git-blame-ignore-revs`

### Removal

When fully migrated:

```bash
npm uninstall eslint prettier @typescript-eslint/parser @typescript-eslint/eslint-plugin eslint-plugin-react eslint-plugin-react-hooks
rm .eslintrc* .prettierrc* .eslintignore .prettierignore
```

## Suppression Comment Migration

ESLint and Biome use different suppression syntax:

```typescript
// ESLint
// eslint-disable-next-line no-unused-vars
const _unused = 1;

// Biome
// biome-ignore lint/correctness/noUnusedVariables: legacy code
const _unused = 1;
```

**Bulk conversion** (use with caution):

```bash
# Find ESLint disables
grep -r "eslint-disable" src/

# Manual conversion required—rule names differ
```

No automated tool exists for this. Convert manually during regular development.
