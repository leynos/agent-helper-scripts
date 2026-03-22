# CodeScene Rules Catalogue

These are all named rules that can appear in `code-health-rules.json` under the
`"rules"` array. The `"name"` value must match exactly (case-sensitive).

Rule names are also used verbatim in `@codescene` directives for function-level smells.

---

## Module Smells

Module smells are **file-level** findings. They **cannot** be suppressed with
`@codescene` directives — only via JSON overrides or refactoring.

| Rule Name | What it Detects | Criticality |
|-----------|-----------------|-------------|
| `"Low Cohesion"` | Module/class has multiple unrelated responsibilities (LCOM4). Indicates an SRP violation. | **Critical** |
| `"Brain Class"` | Large module with many functions and at least one Brain Method — a God Class. | **Critical** |
| `"Lines of Code"` | Large files receive lower scores; raw size is a proxy for accidental complexity. | Advisory |
| `"Developer Congestion"` | Multiple developers frequently edit in parallel — coordination bottleneck. | Advisory |
| `"Complex Code by Former Contributors"` | Low-health hotspot whose primary author has left. Knowledge is gone; risk persists. | Advisory |

---

## Function Smells

Function smells are **method-level** findings and can be suppressed individually
with `@codescene(disable:"<name>")` on the function.

| Rule Name | What it Detects | Criticality |
|-----------|-----------------|-------------|
| `"Brain Method"` | Complex, central function that concentrates too much behaviour (high CC + LoC + nesting). | **Critical** |
| `"Complex Method"` | High cyclomatic complexity — too many branches (if/for/while). | **Critical** |
| `"Nested Complexity"` | Deep nesting of conditionals or loops. Strongly correlated with defect density. | **Critical** |
| `"Bumpy Road"` | Function with multiple separate logical chunks; fails to encapsulate responsibilities. Appears as `"Bumpy Road Ahead"` in directive syntax. | Advisory |
| `"Complex Conditional"` | Branch condition containing multiple logical operators (AND/OR). | Advisory |
| `"Large Method"` | Function exceeds the line-count threshold for understandability. | Advisory |
| `"DRY Violations"` | Duplicated logic detected that is also changed in tandem in commit history. | Advisory |
| `"Primitive Obsession"` | Heavy use of raw primitives (int, string, float) rather than domain types. | Advisory |

---

## Implementation / Test Smells

| Rule Name | What it Detects | Criticality | Scope |
|-----------|-----------------|-------------|-------|
| `"Large Assertion Blocks"` | Long consecutive assert sequences — missing test abstraction. | Advisory | Test code |
| `"Duplicated Assertion Blocks"` | Same assertion block copy-pasted across test suite — DRY violation. | Advisory | Test code |

---

## Criticality Guide

**Critical rules** correlate strongly with defect density and should not be disabled
outright. If they are firing in legitimate code (e.g. a generated parser, a state
machine that cannot be decomposed), prefer:

- A targeted `@codescene` directive with a documented rationale, or
- A down-weight (e.g. `0.3`) scoped to a specific subtree rather than the whole repo.

**Advisory rules** represent real quality signals but may conflict with specific
languages or team conventions. These are safer candidates for `weight: 0.0` scoped
to a path glob where they genuinely do not apply.

---

## Directive-Only Name Variants

Certain rule names differ slightly between the JSON config and the virtual code review
(which is what directives must match):

| JSON `"name"` | `@codescene` directive string |
|---------------|-------------------------------|
| `"Bumpy Road"` | `"Bumpy Road Ahead"` |

When in doubt, copy the exact string shown in the virtual code review for the file
in question.
