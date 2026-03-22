# Strict Rules Reference

Rules beyond "recommended" for teams wanting tighter code quality. Organised by goal.

## Type Safety Hardening

These rules catch type-related issues that slip through "recommended":

```json
{
  "linter": {
    "rules": {
      "suspicious": {
        "noExplicitAny": "error",
        "noConfusingVoidType": "error",
        "noEmptyBlockStatements": "error",
        "noImplicitAnyLet": "error"
      },
      "style": {
        "noNonNullAssertion": "error",
        "noInferrableTypes": "error",
        "useAsConstAssertion": "error"
      }
    }
  }
}
```

### noImplicitAnyLet

Catches `let` declarations without type annotations that become implicit `any`:

```typescript
// ERROR: implicit any
let value;
value = getUnknownThing();

// GOOD
let value: string | undefined;
```

### useAsConstAssertion

Prefer `as const` over literal type assertions:

```typescript
// WARN
const routes = ['home', 'about'] as readonly string[];

// GOOD
const routes = ['home', 'about'] as const;
```

## Code Complexity Limits

Prevent sprawling functions and deep nesting:

```json
{
  "linter": {
    "rules": {
      "complexity": {
        "noExcessiveCognitiveComplexity": {
          "level": "error",
          "options": { "maxAllowedComplexity": 15 }
        },
        "noExcessiveNestedCallbacks": {
          "level": "error",
          "options": { "maxAllowedCallbacks": 3 }
        },
        "noVoid": "error",
        "useLiteralKeys": "error",
        "useSimplifiedLogicExpression": "error"
      }
    }
  }
}
```

### Cognitive Complexity Thresholds

| Threshold | Use Case |
|-----------|----------|
| 10 | Strict—small utility functions |
| 15 | Standard—most business logic |
| 25 | Relaxed—state machines, parsers |

Start strict (10-15), loosen for specific files via overrides.

## Consistency and Style

Enforce uniform code style beyond formatting:

```json
{
  "linter": {
    "rules": {
      "style": {
        "noDefaultExport": "error",
        "noNamespace": "error",
        "noNamespaceImport": "error",
        "useBlockStatements": "error",
        "useCollapsedElseIf": "error",
        "useConst": "error",
        "useExportType": "error",
        "useImportType": "error",
        "useNodejsImportProtocol": "error",
        "useNumberNamespace": "error",
        "useSelfClosingElements": "error",
        "useShorthandArrayType": "error",
        "useSingleCaseStatement": "error",
        "useTemplate": "error"
      }
    }
  }
}
```

### Key Rules Explained

**noNamespaceImport**: Forbids `import * as foo`:
```typescript
// ERROR
import * as utils from './utils';

// GOOD
import { parseDate, formatDate } from './utils';
```

**useExportType / useImportType**: Enforces `type` keyword for type-only imports:
```typescript
// ERROR
import { User } from './types';

// GOOD
import type { User } from './types';
```

**useNodejsImportProtocol**: Requires `node:` prefix for Node.js built-ins:
```typescript
// ERROR
import { readFile } from 'fs';

// GOOD
import { readFile } from 'node:fs';
```

## Naming Conventions

Enforce consistent naming patterns:

```json
{
  "linter": {
    "rules": {
      "style": {
        "useNamingConvention": {
          "level": "error",
          "options": {
            "strictCase": false,
            "requireAscii": true,
            "conventions": [
              {
                "selector": { "kind": "variable" },
                "formats": ["camelCase", "CONSTANT_CASE"]
              },
              {
                "selector": { "kind": "function" },
                "formats": ["camelCase"]
              },
              {
                "selector": { "kind": "typeLike" },
                "formats": ["PascalCase"]
              },
              {
                "selector": { "kind": "enumMember" },
                "formats": ["CONSTANT_CASE"]
              },
              {
                "selector": { "kind": "objectLiteralProperty" },
                "formats": ["camelCase", "CONSTANT_CASE"]
              }
            ]
          }
        }
      }
    }
  }
}
```

### Handling External APIs

When interfacing with APIs using different conventions:

```json
{
  "overrides": [{
    "include": ["**/api/**/*.ts"],
    "linter": {
      "rules": {
        "style": {
          "useNamingConvention": {
            "level": "error",
            "options": {
              "conventions": [{
                "selector": { "kind": "objectLiteralProperty" },
                "formats": ["camelCase", "snake_case"]
              }]
            }
          }
        }
      }
    }
  }]
}
```

## Security-Focused Rules

Rules that catch potential security issues:

```json
{
  "linter": {
    "rules": {
      "security": {
        "noDangerouslySetInnerHtml": "error",
        "noGlobalEval": "error"
      },
      "suspicious": {
        "noGlobalAssign": "error",
        "noPrototypeBuiltins": "error",
        "noThenProperty": "error"
      }
    }
  }
}
```

## Performance Rules

Rules that catch performance anti-patterns:

```json
{
  "linter": {
    "rules": {
      "performance": {
        "noAccumulatingSpread": "error",
        "noBarrelFile": "error",
        "noReExportAll": "error",
        "noDelete": "warn"
      }
    }
  }
}
```

### noBarrelFile / noReExportAll

Barrel files (`index.ts` that re-exports everything) hurt tree-shaking:

```typescript
// ERROR: barrel file
// src/utils/index.ts
export * from './date';
export * from './string';
export * from './number';

// GOOD: direct imports
import { formatDate } from './utils/date';
```

**Override for intentional public APIs:**

```json
{
  "overrides": [{
    "include": ["**/index.ts"],
    "linter": {
      "rules": {
        "performance": {
          "noBarrelFile": "off",
          "noReExportAll": "off"
        }
      }
    }
  }]
}
```

## Complete Strict Configuration

Combine the above for a comprehensive strict setup:

```json
{
  "$schema": "https://biomejs.dev/schemas/1.9.4/schema.json",
  "linter": {
    "enabled": true,
    "rules": {
      "recommended": true,
      "suspicious": {
        "noExplicitAny": "error",
        "noConfusingVoidType": "error",
        "noEmptyBlockStatements": "error",
        "noImplicitAnyLet": "error"
      },
      "style": {
        "noNonNullAssertion": "error",
        "noDefaultExport": "error",
        "noNamespaceImport": "error",
        "useBlockStatements": "error",
        "useConst": "error",
        "useExportType": "error",
        "useImportType": "error",
        "useTemplate": "error"
      },
      "complexity": {
        "noExcessiveCognitiveComplexity": {
          "level": "error",
          "options": { "maxAllowedComplexity": 15 }
        },
        "noVoid": "error"
      },
      "performance": {
        "noAccumulatingSpread": "error"
      }
    }
  }
}
```

## Gradual Adoption Strategy

Don't enable all strict rules at once. Phased approach:

### Phase 1: Foundation (Week 1)
```json
{
  "rules": {
    "recommended": true,
    "style": {
      "useConst": "error",
      "useTemplate": "error"
    }
  }
}
```

### Phase 2: Type Safety (Week 2-3)
Add `noExplicitAny: "warn"`, `useImportType: "error"`, `noNonNullAssertion: "warn"`

### Phase 3: Strictness (Week 4+)
Upgrade warnings to errors, add complexity limits.

### Tracking Progress

```bash
# Count violations by rule
npx biome check --reporter=json . 2>/dev/null | \
  jq -r '.diagnostics[].category' | sort | uniq -c | sort -rn
```
