---
name: codescene-health-rules
description: >
  Generate, modify, or audit `.codescene/code-health-rules.json` files that control
  CodeScene's code health scan behaviour. Use this skill whenever the user wants to
  customize CodeScene rule weights, disable specific smells, adjust metric thresholds,
  scope rules to test vs application code, apply language-specific overrides, or add
  in-source `@codescene` directives. Also trigger when the user asks why a CodeScene
  rule is firing, or wants to suppress a smell across a repo or folder subtree.
---

# CodeScene Code Health Rules

CodeScene evaluates 25+ code health factors and aggregates them into a 1–10
score. You control that behaviour via two mechanisms:

1. **`.codescene/code-health-rules.json`** — repo-scoped (or global) overrides
   for
   rule weights and low-level thresholds.
2. **`@codescene` source directives** — per-function suppression as inline
   comments.

______________________________________________________________________

## Workflow

When the user asks to generate or modify `code-health-rules.json`:

1. **Clarify scope** — which files/paths need different rules? (test vs src, a
   specific language, a legacy subdirectory?)
2. **Clarify intent per rule** — disable entirely (`0.0`), down-weight
   (`0.1–0.9`),
   or tighten/loosen a raw threshold?
3. **Start from CodeScene's template if available** — a documented JSON
   template is
   downloadable via the Hotspots section of the project configuration; remove
   any rules that should stay at defaults.
4. **Emit only the overrides** — omit rules the user wants kept at defaults;
   this is
   how CodeScene itself recommends it and it reduces config drift.
5. **Place the file at `.codescene/code-health-rules.json`** in the repo root
   and
   commit it alongside application code.

______________________________________________________________________

## JSON Schema

```jsonc
{
  "usage": "optional human note — ignored by CodeScene",
  "rule_sets": [
    {
      // Required. Glob relative to repo root. Examples:
      //   "**"           → all files
      //   "test/**"      → top-level test directory
      //   "**/*.js"      → all JavaScript files
      //   "src/legacy/**" → specific subtree
      "matching_content_path": "<glob>",

      // Optional — a prose note for humans, ignored by CodeScene.
      "matching_content_path_doc": "Why this rule set exists",

      // Zero or more rule weight overrides.
      // Omit rules you want at their defaults.
      "rules": [
        {
          "name": "<exact rule name>",  // See references/rules-catalogue.md
          "weight": 0.5                 // 0.0 = disabled, 0.1–0.9 = partial, 1.0 = default
        }
      ],

      // Zero or more low-level threshold overrides.
      // Only needed for granular control inside compound rules.
      "thresholds": [
        {
          "name": "<threshold key>",    // See references/thresholds.md
          "value": 10
        }
      ]
    }
  ]
}
```

Multiple `rule_sets` are allowed in one file — each matching a different glob.

### Precedence

```text
local .codescene/code-health-rules.json
  ↳ global rules repo (configured in Project > Hotspots)
      ↳ CodeScene built-in defaults
```

A local repo file always wins. Global rules come from one designated
repository, set via the **"Repository with global code health rules"** field in
the Hotspots tab of the project configuration. When updating global rules,
trigger a full analysis before delta analyses pick up the changes.

______________________________________________________________________

## Weight Semantics

| `weight` | Effect                                                           |
| -------- | ---------------------------------------------------------------- |
| `1.0`    | Default impact (no need to specify)                              |
| `0.5`    | Rule still fires; contributes at 50% of default severity         |
| `0.1`    | Near-invisible; useful for "track but don't fail PR gates"       |
| `0.0`    | Rule disabled: excluded from score, virtual review, and PR gates |

**Consequences of disabling a rule** (all three apply at `weight: 0.0`):

- The rule leaves the code health calculation entirely, so the reported score
  can
  look *better* than the previously reported baseline.
- The rule is not presented in the virtual code review.
- The rule is not supervised by delta analysis or PR quality gates.

For transparency, CodeScene shows a searchable summary of all overridden rules
under the **Scope** section of each analysis, and overridden thresholds appear
in the virtual code review of every impacted file.

**Do not disable the critical rules** — see `references/rules-catalogue.md` for
which rules are advisory vs critical. Disabling a critical rule means you lose
early warning on the findings most correlated with defect density.

______________________________________________________________________

## Common Patterns

### Test code leniency

```json
{
  "rule_sets": [
    {
      "matching_content_path": "test/**",
      "rules": [
        { "name": "Large Method",               "weight": 0.0 },
        { "name": "Large Assertion Blocks",     "weight": 0.0 },
        { "name": "Duplicated Assertion Blocks","weight": 0.0 },
        { "name": "Brain Method",               "weight": 0.5 }
      ],
      "thresholds": [
        { "name": "function_cyclomatic_complexity_warning", "value": 15 }
      ]
    }
  ]
}
```

### Language-specific overrides

```json
{
  "rule_sets": [
    {
      "matching_content_path": "**/*.js",
      "matching_content_path_doc": "JS files — allow some Primitive Obsession given dynamic typing",
      "rules": [
        { "name": "Primitive Obsession", "weight": 0.3 }
      ]
    }
  ]
}
```

### Multi-scope config (src + test + legacy)

```json
{
  "rule_sets": [
    {
      "matching_content_path": "**",
      "rules": [
        { "name": "Developer Congestion", "weight": 0.5 }
      ]
    },
    {
      "matching_content_path": "test/**",
      "rules": [
        { "name": "Large Assertion Blocks",      "weight": 0.0 },
        { "name": "Duplicated Assertion Blocks", "weight": 0.0 }
      ]
    },
    {
      "matching_content_path": "src/legacy/**",
      "matching_content_path_doc": "Legacy module — tracked but not gated",
      "rules": [
        { "name": "Brain Class",  "weight": 0.3 },
        { "name": "Low Cohesion", "weight": 0.3 }
      ]
    }
  ]
}
```

______________________________________________________________________

## In-Source `@codescene` Directives

For per-function suppression where a JSON config would be too broad:

```c
// @codescene(disable:"Complex Method")
void parse_protocol_frame(Frame* f) { … }

// @codescene(disable:"Complex Method", disable:"Bumpy Road Ahead")
void execute(ProgramOptions* options) { … }

// @codescene(disable-all) Scheduled refactor — 2025-Q3
void legacy_dispatch(Event* e) { … }
```

**Rules for directives:**

- A directive **always applies to the function/method immediately following**
  it.
- Works for **all function-level smells, and only those** — cannot suppress
  module/file-level issues (Lines of Code, Low Cohesion, Brain Class, etc.).
- The smell name must **exactly match** what the virtual code review shows.
  Unknown
  or misspelled names are **silently ignored** — no error, no suppression. Note
  that "Bumpy Road" appears as `"Bumpy Road Ahead"` in directive context.
- Directives may sit inside a **larger multi-line comment** (e.g. a Java
  `/** … */`
  doc block); they need not be a standalone comment line.
- The virtual code review includes a **non-blocking warning** about any
  directives
  in use, together with their impact, and CodeScene flags **new** directives in
  its PR review summary. Nothing flies under the radar.

**Best practices** (per CodeScene's own guidance):

- **Be restrictive** — the clear majority of code health findings are real
  problems
  that should be refactored, not suppressed.
- **Inspect new directives in review** — the PR review summary calls them out to
  make this easy.
- **Document the rationale on the directive line, with a date**, so future
  maintainers can reassess whether it still applies:
  `// @codescene(disable-all) Rewrite next week (2020-01-30)`

______________________________________________________________________

## Reference Files

- [`references/rules-catalogue.md`](references/rules-catalogue.md) — All named
  rules
  with category, criticality, and recommended handling
- [`references/thresholds.md`](references/thresholds.md) — Known threshold keys
  with
  descriptions and typical override values
