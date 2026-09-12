# Quick guide: semantics + utilities with Tailwind v4, daisyUI v5, and Radix

This is a pragmatic layering recipe for building accessible, themeable UIs with
**semantic HTML**, **semantic class names**, **Tailwind v4 utilities**,
**daisyUI v5 components**, and **Radix** primitives.

______________________________________________________________________

## 0) Setup (Tailwind v4 + daisyUI v5)

Create a single entry stylesheet (e.g., `app.css`).

```css
/* app.css */
@import "tailwindcss";

/* Load daisyUI as a plugin (v5 syntax) and choose themes */
@plugin "daisyui" {
  themes: light --default, dark --prefersdark;
}

/* Optional: define project tokens via Tailwind's @theme */
@theme {
  --font-sans: "Inter", system-ui, sans-serif;
  --color-brand-500: oklch(0.65 0.18 260);
  --radius-card: 1rem;
}
```

If you keep your components in unusual places, add explicit sources:

```css
/* Tailwind v4: help the scanner find templates when needed */
@source "./src/**/*.{ts,tsx,js,jsx,mdx}";
```

> **Tip:** daisyUI v5 exposes theme variables like `--color-primary`,
> `--color-base-100`, plus utilities such as `bg-primary`,
> `text-primary-content`, and size tokens like `rounded-box`/`rounded-field`.
> These are theme-aware, so prefer them to raw colours for brand‑consistent
> styling.

______________________________________________________________________

## 1) Mental model: five layers

1. **Semantic HTML**: use the correct element for the job (e.g., `<nav>`,
   `<button>`, `<section>`). Add ARIA only to clarify, never to replace
   semantics.
2. **Headless behaviour**: Radix primitives provide accessibility and state via
   attributes like `data-state`, `data-disabled`, `aria-expanded`.
3. **Component classes**: daisyUI gives structural styles (`btn`, `card`,
   `input`, `menu`, `alert`, …) and colour roles (`btn-primary`,
   `bg-base-100`, …).
4. **Utilities**: Tailwind v4 utilities for spacing, layout, visibility, state
   variants, container queries, etc.
5. **Semantic wrappers**: project-specific _meaningful_ classes (e.g., `.cta`,
   `.product-card`) implemented using Tailwind’s `@utility` (and selective
   `@apply`) to encode intent and keep markup tidy where repetition would
   otherwise explode.

The cascade should flow so that **inline utilities win** over broad component
styles. That keeps local adjustments easy.

______________________________________________________________________

## 2) Semantic HTML (with minimal classes)

```html
<header class="bg-base-100 border-b">
  <nav class="container mx-auto flex items-center gap-4 py-3" aria-label="Primary">
    <a class="btn btn-ghost" href="/">Home</a>
    <a class="link" href="/docs" aria-current="page">Docs</a>
  </nav>
</header>
<main id="content" class="container mx-auto grid gap-6 py-8">
  <section aria-labelledby="features-heading">
    <h2 id="features-heading" class="text-2xl font-semibold">Features</h2>
    <!-- … -->
  </section>
</main>
```

Use native elements first. Where you need a button, use `<button>`; for
navigation, use `<nav>`. This improves keyboard behaviour, form semantics, and
SR (screen reader) output without extra ceremony.

______________________________________________________________________

## 3) Semantic class names: where they help

Create **domain‑level** classes only when they encode intent you reuse (CTA
buttons, product cards, page headers) or when you’re bridging third‑party
markup.

```css
/* app.css */
@utility cta {
  /* Don’t try to @apply daisyUI component classes; style with tokens/utilities */
  border-radius: var(--radius-field);
  padding-inline: --spacing(4);
  padding-block: --spacing(2);
  @apply font-semibold shadow-sm transition; /* Tailwind utilities inline */
  background: var(--color-primary);
  color: var(--color-primary-content);
}
@utility cta/ghost {
  @apply bg-transparent border;
  color: var(--color-primary);
  border-color: color-mix(in oklab, var(--color-primary) 40%, transparent);
}
```

Use them in markup where repetition would otherwise get silly:

```html
<button class="cta">Buy now</button>
<button class="cta/ghost">Learn more</button>
```

> **Rule of thumb:** If a class name describes _what the thing is_ to the
> business or user, keep it. If it describes _how it looks_ (e.g., `.blue-btn`,
> `.mt-4`), prefer utilities.

______________________________________________________________________

## 4) Using daisyUI component classes with utilities

daisyUI gives you quick structure; Tailwind refines it per-instance.

```html
<button class="btn btn-primary md:btn-lg shadow-sm @container">
  <span class="@sm:inline hidden">Create</span>
  <span class="@sm:hidden inline">New</span>
</button>

<div class="card bg-base-100 shadow-sm">
  <div class="card-body">
    <h3 class="card-title">Starter</h3>
    <p>Good for prototypes and proofs.</p>
    <div class="card-actions justify-end">
      <button class="btn btn-ghost">Cancel</button>
      <button class="btn btn-primary">Continue</button>
    </div>
  </div>
</div>
```

For state‑specific tweaks, prefer utility colours over toggling component
variants in selectors. For example, with `data-*` states (from Radix):

```html
<button class="btn data-[state=open]:ring data-[state=open]:bg-primary data-[state=open]:text-primary-content">
  Toggle
</button>
```

______________________________________________________________________

## 5) Radix + Tailwind: style via `data-*` & ARIA

Radix sets **state** through data attributes. Tailwind v4 can target them
directly.

```tsx
// Dialog with daisyUI look, Radix behaviour
import * as Dialog from "@radix-ui/react-dialog";

export function ExampleDialog() {
  return (
    <Dialog.Root>
      <Dialog.Trigger className="btn">Open dialog</Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay
          className="fixed inset-0 bg-black/50 data-[state=open]:animate-in
            data-[state=closed]:animate-out"
        />
        <Dialog.Content
          className="modal modal-open grid place-items-center p-6"
          /* The inner panel: use card tokens */
        >
          <div className="rounded-box bg-base-100 shadow-xl p-6 w-full max-w-md">
            <Dialog.Title className="text-xl font-semibold">Title</Dialog.Title>
            <Dialog.Description className="opacity-80">
              Something helpful.
            </Dialog.Description>
            <div className="mt-4 flex justify-end gap-2">
              <Dialog.Close className="btn btn-ghost">Cancel</Dialog.Close>
              <button className="btn btn-primary">Continue</button>
            </div>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
```

Other handy Radix states:

- `data-[highlighted]` for focused/hovered items in menus/lists.
- `data-[state=on]` for toggles/switches.
- `data-[disabled]` for disabled components.

Example for a menu item:

```tsx
<div
  className="px-3 py-2 rounded-field data-[highlighted]:bg-base-200 data-[disabled]:opacity-50"
  role="menuitem"
>
  Preferences
</div>
```

> **Note:** Variants like `data-[state=open]:…` work with **Tailwind
> utilities** (e.g., `bg-primary`, `ring-2`). They won’t magically prefix
> non‑utility classes such as `btn-primary`. If you need to flip a daisyUI
> variant by state, compute the class in your component
> (`clsx(isOn && "btn-primary")`).

______________________________________________________________________

## 6) `@apply` vs `@utility` (v4 reality)

- Use **`@apply`** to inline Tailwind **utilities** into CSS when you must
  style third‑party DOM, author CSS Modules / Vue `<style>` blocks, or reduce
  repetition inside a semantic wrapper. Pair it with `@reference` when applying
  inside component‑scoped styles.
- Use **`@utility`** to register a **custom utility** (or a small family of
  them) that participates in Tailwind’s variant system (`hover:`, `md:`,
  `data-[state=…]:`, etc.). Prefer this for _project‑specific shorthands_ that
  you want to behave like first‑class utilities.

Examples:

```css
/* A tiny semantic wrapper using @apply (utilities only) */
.badge-new {
  @apply inline-flex items-center gap-1 rounded-selector px-2 py-1 text-xs font-medium bg-primary text-primary-content;
}

/* A first-class utility that works with variants */
@utility prose-muted {
  color: color-mix(in oklab, var(--color-base-content) 60%, transparent);
}
/* Usage: <p class="prose-muted md:hover:prose-muted">… */
```

**Avoid** `@apply` with plugin component classes like `btn`/`card` — they are
not Tailwind utilities. Compose them in markup, or rebuild a semantic
equivalent using tokens as shown in `.cta` above.

### 6.1 Encode state with selectors, not variant `@apply`

Tailwind v4 only inlines **plain utilities** when you call `@apply`. Variant
helpers such as `hover:`, `group-…`, or `data-[state=…]:…` are _not_ expanded,
which means the rule below will quietly drop the interactive parts:

```css
/* ❌ Variant prefixes are ignored when used inside @apply */
.chip {
  @apply inline-flex items-center gap-2 data-[state=on]:bg-accent;
}
```

Instead, combine `@apply` (for the static bits) with explicit selectors for
stateful styles. This keeps the markup clean _and_ ensures Radix data
attributes toggle the look correctly:

```css
.interest-chip {
  @apply inline-flex items-center gap-2 rounded-full border border-base-300/60
    bg-base-200/60 px-4 py-2 text-sm font-medium text-base-content/70 transition;
}

.interest-chip[data-state="on"] {
  @apply border-accent bg-accent text-base-100;
}

.interest-chip[data-state="on"] .interest-chip__icon {
  @apply text-base-content;
}
```

Markup stays semantic:

```tsx
<ToggleGroup.Item value={id} className="interest-chip">
  <Icon className="interest-chip__icon text-lg transition" aria-hidden />
  {interest.label}
</ToggleGroup.Item>
```

> **Summary:** Use `@apply` for the base utility stack, then express Radix /
> ARIA
> state through selectors. This mirrors daisyUI’s approach and keeps all visual
> logic in the stylesheet instead of scattering utility soup through JSX.
>
> **Ordering hint:** When your markup keeps Tailwind utilities (e.g.
> `bg-base-200/60`
> or `text-base-content/70`) alongside a semantic class, place the stateful
> selectors in the `@layer utilities` block so they compile _after_ the inline
> utilities. Otherwise those utilities will win the cascade and your state
> styles will never show up.

______________________________________________________________________

## 7) Cascading styles without fights

- Keep specificity low. Where you write selectors, prefer `:where()` wrappers
  and attributes over IDs.
- Let utilities win locally. If a component wrapper sets padding, expect a
  nearby `px-*`/`py-*` to override it in markup.
- Encapsulate scope with attributes. For example, theme a section:
  `<section data-theme="retro">…`.
- When you truly need a project‑wide variant, mint one:

```css
@custom-variant scheme-midnight (&:where([data-theme="midnight"] *));
/* Usage: class="scheme-midnight:bg-black scheme-midnight:text-white" */
```

______________________________________________________________________

## 8) Putting it together: a small card with Radix toggle

```tsx
import * as Toggle from "@radix-ui/react-toggle";

export function PlanCard() {
  return (
    <article className="card bg-base-100 shadow-sm">
      <div className="card-body gap-3">
        <header className="flex items-center justify-between">
          <h3 className="card-title">Pro</h3>
          <Toggle.Root
            className="btn btn-ghost data-[state=on]:bg-primary data-[state=on]:text-primary-content"
            aria-label="Enable plan"
          >
            Enable
          </Toggle.Root>
        </header>
        <p className="prose-muted">Unlimited projects, email support.</p>
        <footer className="card-actions justify-end">
          <button className="btn">Cancel</button>
          <button className="btn btn-primary">Upgrade</button>
        </footer>
      </div>
    </article>
  );
}
```

______________________________________________________________________

## 9) Checklist (fast sanity)

- [ ] Semantic element first; ARIA as clarifier.
- [ ] Prefer daisyUI tokens (`bg-primary`, `rounded-box`, `text-base-content`)
  for theme‑aware styles.
- [ ] Use Tailwind utilities for per‑instance polish and state.
- [ ] Create semantic wrappers only for reused intent; implement with
  `@utility`/`@apply` (utilities only).
- [ ] Target Radix state via `data-[state=…]`, `data-[highlighted]`,
  `data-[disabled]`.
- [ ] Keep specificity low; let utilities win locally.
- [ ] Query interactive controls in tests by accessible role, name, or label.

______________________________________________________________________

## 10) Troubleshooting notes

- `@apply` inside CSS Modules/Svelte/Vue: add `@reference "../../app.css";` at
  the top of the scoped style block so Tailwind can resolve tokens/utilities.
- Variant prefixes won’t apply to non‑utility classes: use utilities in the
  variant (e.g., `data-[state=open]:bg-primary`) or compute classes in JS/TS.
- If a class isn’t generated, ensure the literal string exists in your sources
  or safelist via `@source inline("class-name")`.

______________________________________________________________________

### TL;DR defaults

- Build with daisyUI component classes for structure.
- Reach for Tailwind utilities for local, stateful, and responsive tweaks.
- Add a small set of semantic wrappers for concepts you name in your product
  language.
- Let Radix drive state through `data-*` and style it with utilities.

______________________________________________________________________

## 11) Style tokens: define once, reuse everywhere

**Goal:** one place to name the look-and-feel, many places to use it — across
Tailwind utilities, daisyUI roles, and Radix state styling.

### 11.1 Token taxonomy (keep it small and sane)

- **Primitive tokens**: raw scales (colour, spacing, radius, shadows,
  typography). These are technology‑agnostic values.
- **Semantic tokens**: role‑based names you actually design with (primary,
  surface, brand, danger, info).
- **Component tokens**: per‑component knobs (field radius, selector radius,
  border thickness) — daisyUI already ships many.

> Keep **primitive** tokens in Tailwind’s `@theme`. Map **semantic** tokens to
> daisyUI roles (primary, base‑100, etc.). Only introduce **component** tokens
> when the design needs them.

### 11.2 Defining primitives with Tailwind v4 `@theme`

```css
/* app.css */
@import "tailwindcss";

/* 1) Primitive scales (Tailwind consumes these to mint utilities) */
@theme {
  /* Colours (OKLCH recommended) */
  --color-brand-100: oklch(0.96 0.02 250);
  --color-brand-500: oklch(0.67 0.15 250);
  --color-brand-700: oklch(0.48 0.12 250);

  /* Spacing: set the base step for --spacing() */
  --spacing: 4px; /* 1 step = 4 px */

  /* Radius: unlock utilities like rounded-card / rounded-pill */
  --radius-card: 1rem;
  --radius-pill: 9999px;

  /* Shadows: becomes shadow-card, shadow-float */
  --shadow-card: 0 1px 2px rgb(0 0 0 / 0.08), 0 4px 12px rgb(0 0 0 / 0.06);
  --shadow-float: 0 6px 24px rgb(0 0 0 / 0.12);
}
```

**Use them immediately:**

```html
<!-- Colour utilities from your tokens -->
<div class="bg-brand-500 text-white/90 rounded-card shadow-card p-6">Hello</div>

<!-- In custom CSS, use functions that read theme tokens -->
.card-surface {@apply rounded-card shadow-card; padding: --spacing(6);}
```

### 11.3 Mapping semantics to daisyUI roles

daisyUI v5 exposes **role tokens** like `--color-primary`, `--color-base-100`,
`--radius-field`, etc. Set those from your primitives so daisyUI components and
role utilities (`bg-primary`, `text-primary-content`, `rounded-field`) line up
with your brand.

```css
/* 2) Semantic roles (per theme). You can scope by [data-theme] */
:root,[data-theme="light"]{
  --color-primary: var(--color-brand-500);
  --color-primary-content: oklch(0.18 0.03 260);
  --color-base-100: oklch(0.99 0 0);
  --color-base-content: oklch(0.22 0.04 260);
  --radius-box: var(--radius-card);
  --border: 1px;
}
[data-theme="dark"]{
  --color-primary: var(--color-brand-700);
  --color-primary-content: oklch(0.94 0.02 260);
  --color-base-100: oklch(0.16 0.03 260);
  --color-base-content: oklch(0.94 0.02 260);
}
```

Now both **daisyUI component classes** and **role utilities** are token‑driven:

```html
<button class="btn btn-primary rounded-field shadow-card">Continue</button>
<div class="bg-base-100 text-base-content rounded-box p-6">Surface</div>
```

### 11.4 Using tokens directly in utilities

Tailwind v4 lets you reference custom properties in arbitrary values without
writing `var()` yourself:

```html
<!-- Shorthand for bg-[var(--color-primary)] -->
<div class="bg-(--color-primary) text-(color:--color-primary-content)">Tokenised</div>

<!-- Tokenised outline and ring -->
<button class="ring-(--color-primary) ring-2 outline-(--color-primary)">Focus</button>
```

### 11.5 Project utilities that _feel_ first‑class

Where you need semantic _wrappers_, register them as **custom utilities** so
they inherit variants (`hover:`, `md:`, `data-[state=...]`) like any Tailwind
class.

```css
/* A semantic CTA built from tokens (no component class @apply) */
@utility cta {
  @apply inline-flex items-center gap-2 font-semibold transition shadow-card;
  border-radius: var(--radius-field);
  padding-inline: --spacing(4);
  padding-block: --spacing(2.5);
  background: var(--color-primary);
  color: var(--color-primary-content);
}
@utility cta/ghost {
  background: transparent;
  border: 1px solid color-mix(in oklab, var(--color-primary) 50%, transparent);
  color: var(--color-primary);
}
```

Usage:

```html
<button class="cta data-[state=on]:ring-2 data-[state=on]:ring-(--color-primary)">Buy now</button>
```

### 11.6 Tokens × Radix state

Radix sets `data-state`, `data-disabled`, `data-highlighted`, etc. Pair those
with tokenized utilities for consistent theming and good contrast.

```tsx
<Toggle.Root
  className="btn btn-ghost data-[state=on]:bg-(--color-primary) data-[state=on]:text-(color:--color-primary-content)"
>
  Enable
</Toggle.Root>
```

### 11.7 Theming strategies

- **System‑driven:** set
  `@plugin "daisyui" { themes: light --default, dark --prefersdark; }` and
  override role tokens in `[data-theme]` blocks for fine control.
- **Manual switch:** toggle `<html data-theme="…">` at runtime. Add a helper
  variant for per‑theme tweaks:

```css
@custom-variant theme-abyss (&:where([data-theme="abyss"] *));
/* <button class="theme-abyss:ring-(--color-primary)">… */
```

- **Section theming:** scope a subtree with
  `<section data-theme="retro">…</section>`; token mapping above will cascade
  to just that block.

### 11.8 Radius/size tokens that match daisyUI

Use daisyUI’s component radius/size tokens to keep edges consistent:

```html
<!-- rounded-box / rounded-field / rounded-selector are theme-aware -->
<article class="card rounded-box shadow-card">…</article>
<button class="btn rounded-field">Click</button>
<span class="badge rounded-selector">New</span>
```

If you want matching Tailwind utilities, back them with `@theme`:

```css
@theme { --radius-field: .75rem; } /* now rounded-field works everywhere */
```

### 11.9 Contrast discipline (critical for tokens)

- Ensure `--color-*-content` provides at least **4.5:1** contrast against its
  background.
- Derive hovers/focus with `color-mix()` to keep hue/Chroma stable:

```css
@utility hover-primary-bg { background: color-mix(in oklab, var(--color-primary) 88%, black); }
```

### 11.10 Quick recipes

#### a) Elevation system

```css
@theme {
  --shadow-surface-1: 0 1px 2px rgb(0 0 0 / .06);
  --shadow-surface-2: 0 4px 12px rgb(0 0 0 / .08);
}
.card-1 {@apply shadow-surface-1 rounded-box;}
.card-2 {@apply shadow-surface-2 rounded-box;}
```

#### b) Tokenized prose

```css
@utility prose-muted { color: color-mix(in oklab, var(--color-base-content) 65%, transparent); }
```

#### c) Container-aware sizes

```css
@theme { --container-compact: 400px; }
/* Use with @sm: variant on container‑named elements */
```

### 11.11 Troubleshooting tokens

- If a `bg-foo-500`‑style class doesn’t exist, confirm you declared the token
  in the right **namespace** under `@theme` (e.g., `--color-foo-500`).
- In component‑scoped styles, add `@reference "../app.css";` before using
  `@apply` so Tailwind can resolve your tokens.
- Don’t `@apply` plugin component classes (`btn`, `card`); compose them in
  markup or rebuild with tokens.

**Bottom line:** put _values_ in `@theme`, map _roles_ to daisyUI tokens, and
style _states_ with Radix data‑attrs + utility variants. One vocabulary, zero
fights.
