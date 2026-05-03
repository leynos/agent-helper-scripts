# CI and Git Hooks Reference

## GitHub Actions

### Basic Lint Check

```yaml
# .github/workflows/lint.yml
name: Lint

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: 'npm'

      - run: npm ci

      - name: Run Biome
        run: npx biome check .
```

### Using Biome's Official Action

More efficient—doesn't require full npm install:

```yaml
# .github/workflows/lint.yml
name: Lint

on:
  push:
    branches: [main]
  pull_request:

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Run Biome
        uses: biomejs/setup-biome@v2
        with:
          version: latest

      - run: biome check .
```

Pin version for reproducibility:

```yaml
      - uses: biomejs/setup-biome@v2
        with:
          version: 1.9.4
```

### PR Annotations

Biome can output GitHub-compatible annotations:

```yaml
      - name: Run Biome
        run: npx biome check --reporter=github .
```

This adds inline annotations to PR diffs showing exactly where issues are.

### Checking Only Changed Files

For faster CI on large repos:

```yaml
jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0  # Need history for diff

      - uses: biomejs/setup-biome@v2

      - name: Lint changed files
        run: |
          FILES=$(git diff --name-only origin/${{ github.base_ref }}...HEAD -- '*.ts' '*.tsx' '*.js' '*.jsx')
          if [ -n "$FILES" ]; then
            echo "$FILES" | xargs biome check
          fi
```

Or use Biome's built-in VCS integration:

```yaml
      - name: Lint changed files
        run: biome check --changed --since=origin/${{ github.base_ref }}
```

### Separate Format and Lint Jobs

Parallel execution for faster feedback:

```yaml
jobs:
  format:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: biomejs/setup-biome@v2
      - run: biome format --check .

  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: biomejs/setup-biome@v2
      - run: biome lint .
```

### Caching Biome Binary

The official action handles caching. For manual setup:

```yaml
      - name: Cache Biome
        uses: actions/cache@v4
        with:
          path: ~/.cache/biome
          key: biome-${{ runner.os }}-${{ hashFiles('package-lock.json') }}
```

### Complete Production Workflow

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [main]
  pull_request:

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  biome:
    name: Lint & Format
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: biomejs/setup-biome@v2
        with:
          version: 1.9.4

      - name: Check formatting
        run: biome format --check .

      - name: Run linter
        run: biome lint --reporter=github .

      - name: Check imports
        run: biome check --organize-imports-enabled=true .

  typecheck:
    name: Type Check
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: 'npm'

      - run: npm ci
      - run: npx tsc --noEmit
```

## Git Hooks

### Using Husky

Install Husky:

```bash
npm install --save-dev husky
npx husky init
```

Create pre-commit hook:

```bash
# .husky/pre-commit
npx biome check --staged --no-errors-on-unmatched
```

**Critical flags:**
- `--staged`: Only check files staged for commit
- `--no-errors-on-unmatched`: Don't fail if no files match (e.g., docs-only commits)

### Using Lefthook

Lefthook is faster than Husky for complex setups:

```bash
npm install --save-dev lefthook
npx lefthook install
```

```yaml
# lefthook.yml
pre-commit:
  parallel: true
  commands:
    biome:
      glob: "*.{js,jsx,ts,tsx,json}"
      run: npx biome check --staged --no-errors-on-unmatched {staged_files}
```

### Using lint-staged

With Husky or standalone:

```bash
npm install --save-dev lint-staged
```

```json
// package.json
{
  "lint-staged": {
    "*.{js,jsx,ts,tsx}": ["biome check --write"],
    "*.json": ["biome format --write"]
  }
}
```

Hook:
```bash
# .husky/pre-commit
npx lint-staged
```

### Auto-Fixing on Commit

Apply fixes automatically before commit:

```bash
# .husky/pre-commit
npx biome check --staged --write --no-errors-on-unmatched
git add -u  # Re-stage fixed files
```

**Caution:** This modifies files. Some teams prefer failing and requiring manual fixes.

### Pre-Push Hook

For more expensive checks:

```bash
# .husky/pre-push
npx biome check .
```

### Bypassing Hooks

For emergency commits:

```bash
git commit --no-verify -m "hotfix: critical prod issue"
```

Document when this is acceptable in your contributing guide.

## Performance Optimization

### Parallel Execution

Biome is already parallel internally. For CI, parallelize at the job level rather than calling Biome multiple times.

### Incremental Checking

Use `--changed` for repos with VCS configured:

```bash
# Check only files changed since main
biome check --changed --since=origin/main
```

In CI:
```yaml
      - run: biome check --changed --since=origin/${{ github.base_ref }}
```

### Binary Size Considerations

Biome's binary is ~50MB. In CI:
- The official action caches the binary
- For Docker builds, consider multi-stage builds
- For monorepos, install once at root

### Timeout Configuration

For CI timeouts, Biome is typically fast. If hitting limits:

```yaml
      - name: Run Biome
        run: biome check .
        timeout-minutes: 5
```

## Commit Message Enforcement

Biome doesn't lint commit messages. Use Commitlint alongside:

```bash
npm install --save-dev @commitlint/cli @commitlint/config-conventional
```

```javascript
// commitlint.config.js
module.exports = { extends: ['@commitlint/config-conventional'] };
```

```bash
# .husky/commit-msg
npx commitlint --edit $1
```

## Branch Protection

Configure GitHub branch protection to require Biome checks:

1. Settings → Branches → Branch protection rules
2. Add rule for `main`
3. Enable "Require status checks to pass"
4. Select "Lint & Format" (or your job name)

## Monorepo Considerations

### Root-Level Configuration

Single `biome.json` at root with overrides per package:

```json
{
  "files": {
    "include": ["packages/**"]
  },
  "overrides": [
    {
      "include": ["packages/server/**"],
      "javascript": {
        "jsxRuntime": "reactClassic"
      }
    },
    {
      "include": ["packages/client/**"],
      "javascript": {
        "jsxRuntime": "automatic"
      }
    }
  ]
}
```

### Per-Package Configuration

Alternatively, each package can have its own `biome.json` extending a base:

```json
// packages/client/biome.json
{
  "extends": ["../../biome.base.json"],
  "linter": {
    "rules": {
      // Package-specific overrides
    }
  }
}
```

### CI for Monorepos

Check only affected packages:

```yaml
jobs:
  detect-changes:
    runs-on: ubuntu-latest
    outputs:
      packages: ${{ steps.filter.outputs.changes }}
    steps:
      - uses: actions/checkout@v4
      - uses: dorny/paths-filter@v3
        id: filter
        with:
          filters: |
            client:
              - 'packages/client/**'
            server:
              - 'packages/server/**'

  lint:
    needs: detect-changes
    if: needs.detect-changes.outputs.packages != '[]'
    strategy:
      matrix:
        package: ${{ fromJson(needs.detect-changes.outputs.packages) }}
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: biomejs/setup-biome@v2
      - run: biome check packages/${{ matrix.package }}
```

## Troubleshooting

### "No files matched"

```bash
# Debug which files Biome sees
biome check --files-ignore-unknown=true --no-errors-on-unmatched --verbose .
```

Check:
- `files.include` in `biome.json`
- VCS ignore settings
- File extensions

### Hook Running on Wrong Files

Ensure `--staged` is used in pre-commit hooks. Without it, Biome checks all files.

### CI Passes but Local Fails

Version mismatch. Pin versions:

```json
{
  "devDependencies": {
    "@biomejs/biome": "1.9.4"
  }
}
```

Use exact version in CI action too.

### Performance Issues in CI

- Use `--changed` for incremental checks
- Split into parallel jobs
- Cache Biome binary
- Don't run on documentation-only changes
