# Front‑End Semantic Linting — Implementation Guide (BiomeJS + GritQL first)

**Audience:** Implementers enforcing semantic, accessible markup in a
Tailwind CSS v4 + DaisyUI v5 front end.
**Goal:** Enforce semantic, accessible HTML with clean, token‑driven
Tailwind/DaisyUI usage. Prefer **BiomeJS + GritQL** rules; fall back to
**Semgrep**/**Stylelint** when they express rules better.
**Outcome:** Readable, queryable markup; reusable semantic classes via
`@apply`; consistent DaisyUI/Radix‑aligned naming; single CLI for local + CI.

______________________________________________________________________

## 0) Scope & Philosophy

- **Files:** `.tsx`, `.html`, `.css` (Tailwind v4 + DaisyUI v5).
- **Primary tool:** **BiomeJS** linter with **GritQL** rules (diagnostics only).
- **Fallbacks:**
  - **Stylelint** — design‑token enforcement, CSS `@apply` hygiene,
    units/specificity.
  - **Semgrep** — simple cross‑language regex/AST patterns (HTML/JSX) where
    easier than GritQL.
- **Design doctrine:**
  1. **Semantics first** — native elements/landmarks; ARIA fills gaps.
  2. **Tokens over literals** — DaisyUI/Tailwind tokens, not raw hex.
  3. **Compose w/ DaisyUI components** — refine with utilities.
  4. **Readable HTML** — extract repeated utility strings into **semantic
     classes** via `@apply` and sensible cascades.
  5. **Configurable thresholds** — warn on repetition beyond agreed limits.
  6. **Testable interfaces** — expose accessible role/name/label attributes so
     tests avoid brittle selectors.

______________________________________________________________________

## 1) Repository Layout (suggested)

```text
project/
├─ src/
│  ├─ app/...                 # TSX
│  └─ styles/
│     ├─ app.css             # @import "tailwindcss" + @plugin "daisyui"
│     ├─ tokens.css          # (generated or hand-written tokens)
│     ├─ semantic.css        # project semantic classes using @apply
│     └─ utilities.css       # optional @utility shorthands (Tailwind v4)
├─ scripts/
│  ├─ check-classlist-length.ts
│  └─ find-near-duplicate-classes.ts
├─ tools/
│  ├─ grit/
│  │  ├─ rule-a11y.grit
│  │  ├─ rule-daisyui.grit
│  │  ├─ rule-repetition.grit
│  │  └─ rule-allowlist.grit
│  ├─ semgrep-semantic.yml
│  ├─ stylelint.config.cjs
│  └─ semantic-lint.config.json   # thresholds & allowlists
├─ biome.jsonc
├─ package.json
└─ .github/workflows/semantic-lint.yml
```

`semantic.css` stores reusable classes via `@apply`. Use Tailwind v4 CSS‑first
configuration in `app.css`.

______________________________________________________________________

## 2) Tailwind v4 + DaisyUI v5 baseline (CSS‑first)

**`src/styles/app.css`**

```css
@import "tailwindcss";

/* DaisyUI themes */
@plugin "daisyui" {
  themes:
    light --default,
    dark --prefersdark;
}

/* Tailwind v4: optionally hint sources if needed */
@source "../**/*.{ts,tsx,js,jsx,html}";
```

**Where to put semantic classes** — `src/styles/semantic.css` (imported from
the entry). Apply DaisyUI component classes directly in markup, and only use
`@apply` with Tailwind utility classes when defining semantic wrappers:

```css
/* Prefer DaisyUI roles directly in markup: class="btn btn-primary" */
.primary-action {
  @apply inline-flex items-center justify-center rounded-field px-4 py-2 font-semibold bg-primary text-primary-content;
}
.form-section-title {
  @apply text-lg font-semibold text-base-content;
}
.nav__link {
  @apply inline-flex items-center gap-2 text-sm font-medium text-base-content hover:text-primary;
}
.nav__link--active {
  @apply text-primary;
}
```

> Use semantic classes for **repeated patterns**; keep one‑offs directly in
> markup.

______________________________________________________________________

## 3) Configure BiomeJS + GritQL

**Install** (example):

```bash
pnpm add -D @biomejs/biome
```

**`biome.jsonc`** (illustrative excerpt)

```jsonc
{
  "$schema": "https://biomejs.dev/schemas/stable/schema.json",
  "plugins": [
    "./tools/grit/rule-a11y.grit",
    "./tools/grit/rule-a11y-trailing.grit",
    "./tools/grit/rule-a11y-leading.grit",
    "./tools/grit/rule-a11y-span.grit",
    "./tools/grit/rule-a11y-span-trailing.grit",
    "./tools/grit/rule-a11y-span-leading.grit",
    "./tools/grit/rule-daisyui-btn-div.grit",
    "./tools/grit/rule-daisyui-btn-span.grit",
    "./tools/grit/rule-daisyui-btn-section.grit",
    "./tools/grit/rule-daisyui-btn-article.grit",
    "./tools/grit/rule-daisyui-btn-li.grit",
    "./tools/grit/rule-daisyui-btn-p.grit",
    "./tools/grit/rule-daisyui-input-div.grit",
    "./tools/grit/rule-daisyui-input-span.grit",
    "./tools/grit/rule-daisyui-input-section.grit",
    "./tools/grit/rule-daisyui-input-article.grit",
    "./tools/grit/rule-daisyui-input-li.grit",
    "./tools/grit/rule-daisyui-input-p.grit",
    "./tools/grit/rule-utility-wrapper.grit",
    "./tools/grit/rule-landmark-slot.grit",
    "./tools/grit/rule-state-slot-data-state.grit",
    "./tools/grit/rule-state-slot-aria-selected.grit",
    "./tools/grit/rule-state-slot-aria-current.grit",
    "./tools/grit/rule-state-slot-role-tab.grit",
    "./tools/grit/rule-layout-wrapper-div-flex.grit",
    "./tools/grit/rule-layout-wrapper-div-grid.grit",
    "./tools/grit/rule-layout-wrapper-section-flex.grit",
    "./tools/grit/rule-layout-wrapper-section-grid.grit",
    "./tools/grit/rule-heading-semantic-h1.grit",
    "./tools/grit/rule-heading-semantic-h2.grit",
    "./tools/grit/rule-heading-semantic-h3.grit",
    "./tools/grit/rule-heading-semantic-h4.grit",
  ],
  "linter": { "enabled": true, "rules": { "recommended": true } },
}
```

> Biome’s current Grit integration accepts one pattern per file. This guide
> therefore keeps the rules granular (for example, separate files for `<div>`
> and `<span>` button misuse). If the plugin grows support for multi‑pattern
> files, this list can be collapsed into fewer modules.
> When a Biome build does not natively load GritQL, use a small Node wrapper
> that executes Grit rules and prints Biome‑style diagnostics. Maintain the
> same paths and thresholds.

**`tools/semantic-lint.config.json`** (thresholds & policy)

```json
{
  "repeatMinClasses": 4,
  "repeatMinOccurrences": 2,
  "maxClasslistLength": 24,
  "allowProjectPrefixes": ["btn", "card", "nav__", "form-", "app-"],
  "disallowRawHex": true,
  "nearDuplicateClasses": {
    "minTokenCount": 4,
    "maxJaccardDistance": 0.25,
    "minOccurrences": 2,
    "tokenIndexSample": 5,
    "suppressPrefixes": ["prose-", "wysiwyg-"],
    "failOnViolation": false
  },
  "loopSiblingHints": {
    "loopMinOccurrences": 3,
    "siblingMinOccurrences": 3
  },
  "utilitySemanticScoring": {
    "minUtilityTokens": 8,
    "scoreThreshold": 6,
    "semanticWeight": 2
  },
  "conceptHints": {
    "disabled": []
  }
}
```

______________________________________________________________________

## 4) GritQL rules (practical starters)

> Syntax below illustrates intent; adapt to the configured Grit adapter’s
> exact grammar. Keep messages **actionable**.

### A) Semantic interactivity (no clickable `<div>` / `<span>`)

Files:

- `tools/grit/rule-a11y.grit`
- `tools/grit/rule-a11y-trailing.grit`
- `tools/grit/rule-a11y-leading.grit`
- `tools/grit/rule-a11y-span.grit`
- `tools/grit/rule-a11y-span-trailing.grit`
- `tools/grit/rule-a11y-span-leading.grit`

Each file targets a common attribute ordering, for example:

```grit
`<div ... onClick={$CALL}>$body</div>` where {
  register_diagnostic(
    span = $CALL,
    message = "Replace this clickable <div> with a semantic <button> or <a>."
  )
}
```

### B) Landmarks & labels (gentle suggestions)

```grit
language tsx

// Div used as nav
`<div role="navigation" $attrs>$body</div>` => diag("Prefer <nav> for primary navigation.")

// Input without associated label (simple heuristic)
`<input $attrs />`
where { not(match($attrs, /aria-label=|id=/)) }
=> diag("Inputs need a label: use <label htmlFor=...> in TSX (or <label for=...> in plain HTML) or aria-label.")
```

### C) DaisyUI usage sanity

Files:

- `tools/grit/rule-daisyui-btn-div.grit`
- `tools/grit/rule-daisyui-btn-span.grit`
- `tools/grit/rule-daisyui-btn-section.grit`
- `tools/grit/rule-daisyui-btn-article.grit`
- `tools/grit/rule-daisyui-btn-li.grit`
- `tools/grit/rule-daisyui-btn-p.grit`
- `tools/grit/rule-daisyui-input-div.grit`
- `tools/grit/rule-daisyui-input-span.grit`
- `tools/grit/rule-daisyui-input-section.grit`
- `tools/grit/rule-daisyui-input-article.grit`
- `tools/grit/rule-daisyui-input-li.grit`
- `tools/grit/rule-daisyui-input-p.grit`

Each file inverts a common misuse, e.g.

```grit
`<div ... className="... btn ..."` ...`>$body</div>` where {
  register_diagnostic(
    span = $body,
    message = "DaisyUI `btn` belongs on interactive elements (<button>, <a>, or submit <input>)."
  )
}
```

The duplication keeps messages targeted whilst Biome’s current Grit plugin
restricts repositories to one pattern per file.

### D) Repetition → extract with `@apply`

- `scripts/check-classlist-length.ts`
- `scripts/find-near-duplicate-classes.ts`

Lightweight TypeScript checkers (run as part of `bun run semantic`) flag class
strings that exceed the configured threshold **and** warn about near-duplicate
utility sets. The scripts read thresholds from
`tools/semantic-lint.config.json`, normalize whitespace, and report literals
that violate the agreed limits.

> Adjust `maxClasslistLength` **and** the `nearDuplicateClasses` block and
> re-run `bun run semantic` to enforce different ceilings.

### E) Near duplicate detection

The near-duplicate checker tokenizes each literal, deduplicates utilities, and
compares token sets using Jaccard similarity. Any pair (or group) whose
similarity exceeds the configured threshold produces a single diagnostic
summarizing the overlap and paths. Suggested defaults are bundled in
`tools/semantic-lint.config.json`:

```jsonc
"nearDuplicateClasses": {
  "minTokenCount": 4,
  "maxJaccardDistance": 0.25,
  "minOccurrences": 2,
  "tokenIndexSample": 5,
  "suppressPrefixes": ["prose-", "wysiwyg-"]
}
```

Adjust these knobs to tune the signal. When the checker fires, extract a
semantic `@apply` class (for example inside `semantic.css`) and reuse it
instead of cloning similar utility lists.

______________________________________________________________________

## Proposed meaning-first semantic checks (roadmap)

These heuristics focus on **structural intent** rather than raw class
similarity. Each item describes what to detect, why it matters, and the
preferred fix to recommend in future lint passes.

### 1) “Div/span soup” (utility-only wrapper chains)

- **Signal**: Two or more nested `<div>`/`<span>` nodes whose only attribute is
  a utility-heavy `className` (no `role`, `aria-*`, `id`, `data-*`, event
  handlers).
- **Meaning**: The wrapper is expressing a _layout concept_ (stack, cluster,
  surface) without naming it.
- **Action**: Warn and suggest extracting a named container class (e.g.
  `.stack`, `.cluster`, `.card__body`) via `@apply`.
- **Implementation notes**: GritQL rule that walks parent/child utility-only
  nodes and fires when depth ≥ 2; fallback AST walker if needed.

### 2) Landmarks and slot semantics

- **Signal**: Utility-only child elements inside semantic regions such as
  `<nav>`, `<header>`, `<ul>`, `<form>`.
- **Meaning**: These are _slots_ (navigation links, menu items, form controls)
  that deserve a named semantic class.
- **Action**: Suggest contextual names like `.nav__link`, `.nav__link--active`,
  `.menu__item`, `.form__label`.
- **Implementation notes**: GritQL ancestor constraint rules that tailor the
  suggestion to the enclosing landmark.

### 3) Repeated sibling pattern (loop intent)

- **Signal**: Identical or near-identical class lists applied to siblings,
  especially those produced by `.map()` in TSX.
- **Meaning**: Indicates a row/tile/card abstraction that should become a
  shared class.
- **Action**: Recommend extracting both a container class (e.g. `.card-grid`)
  and an item class (e.g. `.card`).
- **Implementation notes**: Extend the existing near-duplicate script to
  consider siblings grouped by parent, or add a dedicated GritQL rule for
  `.map()` return values.

### 4) Token-to-concept mapping

- **Signal**: Utility combinations that scream a known component (button, chip,
  badge, toolbar, tabs trigger).
- **Meaning**: The element already behaves like a component but lacks a
  semantic name.
- **Action**: Issue prescriptive suggestions derived from a concept dictionary
  (e.g. `.chip`, `.toolbar`, `.tabs__trigger`).
- **Implementation notes**: Dictionary-driven matcher in the companion script
  or GritQL predicates that match presence/absence token sets.

### 5) Stateful slots (Radix/DaisyUI attributes)

- **Signal**: Elements with `data-state`, `aria-selected`, `aria-current`,
  `role="tab"` and long utility lists.
- **Meaning**: State-driven UI pieces should expose a semantic class for
  styling the base and active states.
- **Action**: Recommend classes like `.tabs__trigger` plus state modifiers in
  CSS.
- **Implementation notes**: GritQL rule watching for state attributes plus
  utility load.

### 6) Anonymous layout wrappers

- **Signal**: Elements using only layout utilities
  (flex/grid/gap/justify/space) without semantics.
- **Meaning**: These are layout patterns (stack/cluster/switcher) that deserve
  named abstractions.
- **Action**: Suggest layout semantics (e.g. `.stack`, `.cluster`, `.sidebar`).
- **Implementation notes**: Token classifier that recognizes layout-only
  sets; fire in GritQL or the script.

### 7) Heading/title repetition

- **Signal**: The same utility bundle repeated across multiple headings (`<h1>`-
  `<h4>`) or section titles.
- **Meaning**: Editorial roles should be expressed via `.section-title`,
  `.card__title`, etc.
- **Action**: Recommend extracted title classes with `@apply`.
- **Implementation notes**: GritQL rule that tracks heading class repetition
  counts.

### 8) Utility load vs. semantic signal score

- **Signal**: Elements with heavy utility usage but little semantic metadata
  (no role/id/aria/data).
- **Meaning**: Frequent offender list for “this should have a name”.
- **Action**: Soft warning nudging authors to introduce a semantic class
  summarizing intent.
- **Implementation notes**: Extend the companion script to compute a heuristic
  score `(tokenCount - semanticSignals)` and warn above a configurable
  threshold.

Each proposal will ship with a concrete class name suggestion and will
reference `src/styles/semantic.css` (or `@utility` helpers) so fixes are
straightforward.

### F) Class allowlist (Tailwind, DaisyUI, project semantics)

The current Biome plugin does not yet expose helpers such as `split_classes`.
Until that changes, enforce the allowlist via **Semgrep**
(`tools/semgrep-semantic.yml`, rule `class-token-uppercase`), which catches
camelCase tokens and other non‑Tailwind/DaisyUI class names. Migration back
into Grit can be performed when the integration grows richer predicates.

### G) Testing-selector rules

Files:

- `tools/grit/rule-testing-datatestid.grit`
- `tools/grit/rule-testing-queryselector.grit`
- `tools/grit/rule-testing-text-click.grit`

Test code should prefer role, label, and text queries over `data-testid`,
raw `querySelector` calls, class selectors, or fragile text-click shortcuts.
Flag these patterns unless no accessible query is available, and require a
local, reviewed exception when one is used:

```grit
`screen.getByTestId($ARG)` where {
  register_diagnostic(
    span = $ARG,
    message = "Prefer an accessible query (role, label, or text) over data-testid."
  )
}
```

Rules in this family keep test code aligned with the same semantic and
accessibility signals the markup rules enforce, so tests break when
accessibility regresses.

______________________________________________________________________

## 5) Stylelint (focused rules only)

### Install

```bash
pnpm add -D stylelint stylelint-declaration-strict-value
```

**`tools/stylelint.config.cjs`**

```js
module.exports = {
  plugins: ["stylelint-declaration-strict-value"],
  rules: {
    // Disallow hex/named colors; require tokens or Tailwind classes
    "color-no-hex": true,
    "color-named": "never",

    // Enforce tokens for key props (allow CSS variables + keywords)
    "scale-unlimited/declaration-strict-value": [
      [
        [
          "/^color$/",
          "^background(-color)?$",
          "^border(-.*)?-color$",
          "fill",
          "stroke",
          "outline-color",
        ],
      ],
      { ignoreValues: ["transparent", "currentColor", "/^var\\(--/"] },
    ],

    // Discourage !important; keep specificity sane
    "declaration-no-important": true,

    // Optional unit policy (px allowed in borders etc.)
    "declaration-property-unit-disallowed-list": {
      "/^(margin|padding|gap|inset|top|right|bottom|left)$/": ["px"],
    },
  },
};
```

> Stylelint is **not** used for general formatting; it only enforces tokens and
> a few hygiene rules.

______________________________________________________________________

## 6) Semgrep (targeted HTML/JSX checks)

### Install and configuration

```bash
uv tool install semgrep
```

**`tools/semgrep-semantic.yml`**

```yaml
rules:
  # Raw Tailwind color utilities instead of semantic roles
  - id: tailwind-raw-color-class
    patterns:
      - pattern-regex: "\\b(text|bg|border)-(red|blue|green|gray|slate|zinc|stone|amber|rose)-[0-9]{2,3}\\b"
    message: "Prefer DaisyUI role classes (e.g., bg-primary, text-base-content) over raw Tailwind color scale."
    languages: [javascript, typescript, jsx, tsx, html]
    severity: WARNING

  # Dynamic daisyUI token in template literal (build-time discovery issue)
  - id: daisyui-dynamic-token
    pattern-regex: "`[^`]*\\b(btn|badge|alert|tab)-\\${[^}]+}[^`]*`"
    message: "Avoid dynamic DaisyUI token names (e.g. `btn-${color}`) — Tailwind cannot statically include them."
    languages: [javascript, typescript, jsx, tsx]
    severity: WARNING

  # Overly long class attribute (coarse backstop)
  - id: classlist-too-long
    pattern-regex: "class(Name)?=\\{?['\"][^'\"]{120,}['\"]\\}?"
    message: "Long class list — extract into a semantic class with @apply."
    languages: [javascript, typescript, jsx, tsx, html]
    severity: WARNING
```

______________________________________________________________________

## 7) Unified CLI & Dev Workflow

**`package.json`** (current scripts)

```json
{
  "scripts": {
    "semantic:lint": "bun run semantic:biome && bun run semantic:checks",
    "semantic:checks": "bun run lint:classlist && bun run lint:dupes && bun run lint:semgrep && bun run lint:style",
    "semantic:biome": "bunx biome ci src tests tools docs",
    "semantic": "bun run semantic:lint",
    "lint:classlist": "bun run scripts/check-classlist-length.ts",
    "lint:class-duplicates": "bun run scripts/find-near-duplicate-classes.ts",
    "lint:dupes": "bun run lint:class-duplicates",
    "lint:semgrep": "uvx semgrep -c tools/semgrep-semantic.yml --include {src,tests}/**/*.tsx --include '**/*.html'",
    "lint:style": "bun run lint:stylelint",
    "lint:stylelint": "bunx stylelint 'src/**/*.css' --config tools/stylelint.config.cjs"
  }
}
```

- **Local dev:** `bun semantic` runs Biome + Grit, class length, near-duplicate
  - loop/sibling/concept checks, Semgrep, and Stylelint.
- **Pre-commit (optional):** wire a Husky hook to `bun semantic`.
- **CI:** `bun semantic` is the single gate invoked by `semantic-lint.yml`
  (see `.github/workflows/semantic-lint.yml` in the repo).

> `uvx semgrep` expects `uv` to be installed
> (<https://github.com/astral-sh/uv>).
> The repo keeps the command consistent across local + CI environments.

______________________________________________________________________

## 8) Companion semantic checker signals

The `scripts/find-near-duplicate-classes.ts` analyser now emits several
actionable diagnostics beyond near-duplicate detection:

- **Near-duplicate class strings:** still groups similar utility stacks via
  token Jaccard similarity. Use it to extract shared semantic classes.
- **Loop / sibling repetition:** flags identical class strings produced inside a
  `.map()` or rendered as repeated siblings. Suggestion: extract a named slot
  (for example `.card-grid__item`) or move layout utilities to the container.
- **Concept dictionary hints:** matches well-known Tailwind/DaisyUI patterns
  (button-like, chip, card surface, toolbar, tabs trigger, nav link) and
  proposes semantic class names with `@apply`.
- **Utility-vs-semantics score:** highlights heavy utility stacks on elements
  lacking semantic signals (role, aria, state attributes, semantic tags). Use
  it to name the element, add landmarks, or move styling into `semantic.css`.

Each diagnostic surfaces the paths, representative utilities, and a concrete
next action. All heuristics are configurable via
`tools/semantic-lint.config.json`.

______________________________________________________________________

## 9) Tuning thresholds and suppressing diagnostics

- **Near duplicates:** tweak `nearDuplicateClasses` thresholds. To exempt whole
  families (for example prose content), add prefixes to `suppressPrefixes`.
  Setting `failOnViolation` to `true` escalates the check to a hard failure.
- **Loop/sibling warnings:** raise `loopMinOccurrences` or
  `siblingMinOccurrences` if a component intentionally repeats short utility
  bursts (for example icon strips).
- **Concept hints:** add a concept `id` to `conceptHints.disabled` to silence
  that pattern across the project.
- **Utility scoring:** adjust `minUtilityTokens`, `scoreThreshold`, or
  `semanticWeight` to match the team’s tolerance for inline utilities.
- **Project-specific allowlists:** keep semantic class prefixes in
  `allowProjectPrefixes`. When adding a new family, extend this array (this
  unblocks class-length and repetition rules).

Prefer addressing the underlying markup first, then reach for configuration.
Inline suppression comments are intentionally not supported yet to encourage
semantic fixes over ad hoc opt-outs.

______________________________________________________________________

## 10) How to refactor into `@apply` (+ cascades)

1. **Spot repetition:** linter warns that a class chunk is repeated (e.g.,
   `inline-flex items-center gap-2 text-sm font-medium text-base-content`).
2. **Name the concept:** choose a **semantic** name that reflects purpose, not
   appearance: e.g., `.nav__link`.
3. **Define once:** in `src/styles/semantic.css`:

   ```css
   .nav__link {
     @apply inline-flex items-center gap-2 text-sm font-medium text-base-content hover:text-primary;
   }
   .nav__link--active {
     @apply text-primary;
   }
   ```

4. **Replace usages:** change `className` to the new class (keep any **unique**
   one-off utilities alongside if needed: `className="nav__link md:pl-3"`).
5. **Use cascades where logical:** if a set of children share
   typography/spacing, apply a parent class and let children inherit or use
   low‑specificity selectors:

   ```css
   .form-section {
     @apply space-y-3;
   }
   .form-section .form-section-title {
     @apply text-lg font-semibold;
   }
   ```

**Naming guidance:**

- Mirror DaisyUI where it fits: `.btn`, `.btn-primary`, `.card`, `.card-title`.
- For bespoke patterns: BEM‑ish and role‑based, e.g. `.walk-card`,
  `.walk-card__title`; or `.nav__link--active`.
- Prefer **role tokens** (`primary`, `secondary`, `accent`, `success`, `error`)
  to colour words.

______________________________________________________________________

## 11) Quick rule checklists (what the lints enforce)

- **Semantic & a11y**
  - No clickable `div/span` without role+keyboard; prefer `<button>/<a>`.
  - Use `<nav>/<main>/<header>/<footer>` over `div[role=...]`.
  - Inputs must be labelled (`<label htmlFor=...>` in TSX, `<label for=...>` in
    plain HTML, or `aria-label`).

- **DaisyUI composition**
  - `btn` belongs on interactive elements.
  - `input`/`select`/`textarea` use matching DaisyUI classes.

- **Design tokens**
  - No hex/named colours in CSS.
  - Prefer role utilities (`bg-primary`, `text-base-content`) over raw Tailwind
    colour scales.

- **Repetition & readability**
  - Warn on long/repeated class chunks → extract with `@apply` into
    `semantic.css`.
  - Unknown class tokens flagged (must be Tailwind, DaisyUI, or project
    semantic class prefix).

- **Testing**
  - Tests query controls by role, label, or text; `data-testid` and CSS
    selectors require a reviewed exception.

______________________________________________________________________

## 12) IDE tips

- Enable Tailwind IntelliSense for class hints and token names.
- Configure Biome to format on save; run `bun run semantic:lint` before
  commits.
- Configure an editor task to open `semantic.css` quickly when a repetition
  warning appears.

______________________________________________________________________

## 13) Future extensions

- **Cross‑file repetition index** (cache normalized chunks to detect repeats
  across the whole repo).
- **Contrast checks** (static heuristics on text/background utility pairs).
- **Autofix codemods** (Grit rewrite scripts that scaffold a new class and
  replace duplicates in a file).

______________________________________________________________________

## 14) FAQ

**Q: Will `@apply` bloat CSS?**  
A: Only repeated patterns are extracted. Tailwind still tree‑shakes class‑based
styles; the few semantic classes added remain minimal and intentionally reused.

**Q: When is it _okay_ to keep utilities inline?**  
A: One‑offs, quick prototypes, and tiny adjustments local to a component. Once
the same chunk appears twice, prefer extracting it.

**Q: How strict are thresholds?**  
A: Configurable. Start with `repeatMinClasses=4`, `repeatMinOccurrences=2`.
Tighten as the design system matures.

______________________________________________________________________

## 15) Ready-to-run checklist

1. Add files: `tools/grit/*.grit`, `tools/semantic-lint.config.json`,
   `tools/stylelint.config.cjs`, `tools/semgrep-semantic.yml`.
2. Wire **Biome** plugin or wrapper to execute Grit rules (paths above).
3. Add **`semantic.css`** and begin extracting repeated patterns with `@apply`.
4. Add **`semantic:lint`** as the primary script and the CI workflow.
5. Iterate on thresholds, allowlist prefixes, and rule messages as the team
   gains patterns.
6. Document each custom rule and the policy it enforces.
7. Add fixture examples for each custom rule family, and mark advisory checks
   explicitly when they are not yet gate-worthy.
