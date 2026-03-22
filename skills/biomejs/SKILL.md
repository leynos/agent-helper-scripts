---
name: biome-typescript
description: Configure and use Biome (biomejs) for TypeScript linting and formatting. Use when setting up Biome in a project, configuring lint rules, migrating from ESLint/Prettier, fixing lint errors, setting up CI pipelines with Biome, or configuring git hooks for code quality. Covers biome.json configuration, file inclusion/exclusion patterns, rule overrides, and integration with build tooling.
---

# Biome TypeScript Linting Skill

## Routing Guide

| Task | Section |
|------|---------|
| Install or update Biome | [Version Discovery](#version-discovery) |
| Initial setup | [Quick Start](#quick-start) |
| Configure rules | [Configuration Patterns](#configuration-patterns) |
| Include/exclude files | [File Targeting](#file-targeting-rough-edges) |
| Fix specific lint errors | See `references/lint-solutions.md` |
| Stricter rules beyond recommended | See `references/strict-rules.md` |
| Migrate from ESLint/Prettier | See `references/migration.md` |
| CI and git hooks | See `references/ci-hooks.md` |

## Version Discovery

**Never trust cached knowledge of Biome versions.** Query the npm registry:

```bash
npm view @biomejs/biome version
```

Or for all recent versions:

```bash
npm view @biomejs/biome versions --json | tail -20
```

Check release notes for breaking changes:

```bash
curl -s https://api.github.com/repos/biomejs/biome/releases/latest | jq -r '.tag_name, .html_url'
```

## Quick Start

Install as dev dependency (always pin exact version):

```bash
npm install --save-dev --save-exact @biomejs/biome@latest
npx biome init
```

This creates `biome.json`. Immediately verify:

```bash
npx biome check .
```

### Minimal biome.json

```json
{
  "$schema": "https://biomejs.dev/schemas/1.9.4/schema.json",
  "vcs": {
    "enabled": true,
    "clientKind": "git",
    "useIgnoreFile": true
  },
  "organizeImports": {
    "enabled": true
  },
  "linter": {
    "enabled": true,
    "rules": {
      "recommended": true
    }
  },
  "formatter": {
    "enabled": true,
    "indentStyle": "space",
    "indentWidth": 2
  }
}
```

**Critical:** Update the `$schema` URL to match your installed version.

## Configuration Patterns

### Rule Severity Levels

```json
{
  "linter": {
    "rules": {
      "recommended": true,
      "suspicious": {
        "noExplicitAny": "error",
        "noArrayIndexKey": "warn"
      },
      "style": {
        "noNonNullAssertion": "off"
      }
    }
  }
}
```

Levels: `"error"` | `"warn"` | `"off"`

### Rules with Options

Some rules accept configuration objects:

```json
{
  "linter": {
    "rules": {
      "style": {
        "useNamingConvention": {
          "level": "error",
          "options": {
            "strictCase": false,
            "conventions": [
              {
                "selector": { "kind": "variable" },
                "formats": ["camelCase", "CONSTANT_CASE"]
              }
            ]
          }
        }
      },
      "complexity": {
        "noExcessiveCognitiveComplexity": {
          "level": "error",
          "options": {
            "maxAllowedComplexity": 15
          }
        }
      }
    }
  }
}
```

### Extending Configurations

```json
{
  "extends": ["./biome.base.json"]
}
```

Arrays merge; later entries override earlier ones.

## File Targeting (Rough Edges)

### Global Include/Exclude

Top-level `files` applies to **all tools** (linter, formatter, organizeImports):

```json
{
  "files": {
    "include": ["src/**", "tests/**"],
    "ignore": ["**/generated/**", "**/*.d.ts", "**/dist/**"]
  }
}
```

**Gotcha:** Patterns are relative to `biome.json` location. Use `**/` prefix for recursive matching.

### Tool-Specific Include/Exclude

Each tool can have its own file scope:

```json
{
  "linter": {
    "include": ["src/**"],
    "ignore": ["src/generated/**"]
  },
  "formatter": {
    "include": ["src/**", "scripts/**"],
    "ignore": ["src/vendor/**"]
  }
}
```

### Per-File Rule Overrides

Apply different rules to specific file patterns:

```json
{
  "overrides": [
    {
      "include": ["**/*.test.ts", "**/*.spec.ts"],
      "linter": {
        "rules": {
          "suspicious": {
            "noExplicitAny": "off"
          }
        }
      }
    },
    {
      "include": ["scripts/**"],
      "linter": {
        "rules": {
          "suspicious": {
            "noConsoleLog": "off"
          }
        }
      }
    },
    {
      "include": ["**/*.config.ts", "**/*.config.js"],
      "linter": {
        "rules": {
          "style": {
            "noDefaultExport": "off"
          }
        }
      }
    }
  ]
}
```

**Critical ordering:** Overrides apply in array order. Later overrides win for the same file.

### VCS Integration

Let Biome respect `.gitignore`:

```json
{
  "vcs": {
    "enabled": true,
    "clientKind": "git",
    "useIgnoreFile": true,
    "defaultBranch": "main"
  }
}
```

With `useIgnoreFile: true`, anything in `.gitignore` is automatically excluded.

## Command Reference

```bash
# Check without modifying (CI mode)
npx biome check .

# Fix all auto-fixable issues
npx biome check --write .

# Lint only (no formatting)
npx biome lint .

# Format only
npx biome format --write .

# Organize imports only
npx biome check --organize-imports-enabled=true --write .

# Check specific files
npx biome check src/index.ts src/utils/**/*.ts

# Output as JSON (for tooling)
npx biome check --reporter=json .

# Show which files would be processed
npx biome check --files-ignore-unknown=true --no-errors-on-unmatched .
```

### Useful Flags

| Flag | Purpose |
|------|---------|
| `--write` | Apply fixes |
| `--unsafe` | Apply unsafe fixes (review carefully) |
| `--staged` | Only check git-staged files |
| `--changed` | Only check files changed since default branch |
| `--reporter=json` | Machine-readable output |
| `--diagnostic-level=error` | Exit non-zero only on errors (ignore warnings) |

## Suppression Comments

Suppress specific rules inline:

```typescript
// biome-ignore lint/suspicious/noExplicitAny: external API requires any
const response: any = await legacyApi.fetch();

// biome-ignore lint/style/noNonNullAssertion: checked above
const element = document.getElementById("root")!;
```

**Always include a reason after the colon.** Biome enforces this—reasonless suppressions fail.

**Avoid these lazy patterns:**

```typescript
// BAD: Will need revisiting
// biome-ignore lint/suspicious/noExplicitAny: TODO fix later
// biome-ignore lint/suspicious/noExplicitAny: too complex to type

// GOOD: Explains why suppression is necessary
// biome-ignore lint/suspicious/noExplicitAny: FFI boundary with untyped C library
// biome-ignore lint/suspicious/noExplicitAny: generic deserializer, caller provides type
```

## Package.json Scripts

```json
{
  "scripts": {
    "lint": "biome check .",
    "lint:fix": "biome check --write .",
    "format": "biome format --write .",
    "check": "biome check --write --unsafe ."
  }
}
```

## TypeScript Integration

Biome does **not** use `tsconfig.json` for path resolution by default. For monorepos or path aliases:

```json
{
  "javascript": {
    "jsxRuntime": "reactClassic",
    "globals": ["React"]
  }
}
```

For JSX:

```json
{
  "javascript": {
    "jsxRuntime": "automatic"
  }
}
```

## When to Consult Reference Files

- **Struggling with a specific lint error?** → `references/lint-solutions.md`
- **Want stricter rules than "recommended"?** → `references/strict-rules.md`
- **Migrating from ESLint or Prettier?** → `references/migration.md`
- **Setting up CI or git hooks?** → `references/ci-hooks.md`
