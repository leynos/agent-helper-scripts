# Tailwind CSS v4 (May 2025)

## I. Core Architecture & Performance

1. **New Engine - Performance First:**
   - V4 ships with a completely rewritten engine. Expect drastically reduced
     build times – typically sub-10ms for most projects, even large ones
     often under 100ms. This is achieved by more efficiently parsing sources
     and generating CSS on-demand.
2. **CSS-First Configuration via `@theme`:**
   - The primary configuration mechanism shifts from `tailwind.config.js`
     (for theme values) to the main CSS file using the `@theme` directive.

     ```css
     /* app.css */
     @import "tailwindcss";

     @theme {
       --font-sans: "Inter", system-ui, sans-serif;
       --color-brand-500: oklch(0.637 0.237 25.331); /* Example OKLCH colour */
       --breakpoint-lg: 64rem;
       --spacing: 0.25rem; /* Base for numeric spacing utilities */
     }
     ```

   - Theme values are defined as CSS custom properties (variables).
     Tailwind uses these to generate corresponding utility classes (e.g.,
     `font-sans`, `bg-brand-500`, `lg:p-(--spacing-4)`) and also makes
     these variables globally available for use in custom CSS or arbitrary
     values (e.g., `var(--color-brand-500)`).
   - The default theme is still provided but can be extended, overridden,
     or entirely replaced using this CSS-native approach. For instance,
     `--color-*: initial;` within `@theme` will remove all default colour
     utilities, allowing a fully custom palette.
3. **Modern CSS Baseline:**
   - Targets **Safari 16.4+, Chrome 111+, Firefox 128+**. This is
     non-negotiable as v4 relies on features like `@property`,
     `color-mix()`, and modern cascade layers. Older browser support
     requires sticking to v3.4.
   - The default colour palette leverages OKLCH for more vibrant,
     perceptually uniform colours out-of-the-box.

## II. Build & Integration

1. **Simplified Imports:**
   - The `@tailwind base; @tailwind components; @tailwind utilities;`
     directives are deprecated. A single `@import "tailwindcss";` now
     handles the injection of base styles (Preflight), theme variables,
     and utilities into their respective cascade layers.
2. **Modular Tooling Packages:**
   - **CLI:** `npx @tailwindcss/cli ...` (package: `@tailwindcss/cli`)
   - **PostCSS Plugin:** `@tailwindcss/postcss` (package:
     `@tailwindcss/postcss`)
   - **Vite Plugin:** `@tailwindcss/vite` (package: `@tailwindcss/vite`) -
     Recommended for Vite projects due to optimized performance and DX.
3. **Internalized Processing:**
   - `postcss-import` and `autoprefixer` are generally no longer required
     as separate dependencies. Tailwind v4 handles CSS bundling and vendor
     prefixing (via Lightning CSS) internally.

## III. Key Migration Considerations & API Changes (v3 -> v4)

1. **Configuration File Shift:**
   - While `tailwind.config.js` can still be used for plugin definitions
     or complex setups (loaded via `@config "path/to/config.js";`), theme
     customization (colours, spacing, fonts, breakpoints) should
     primarily occur in CSS via `@theme`.
   - The `content` array is no longer used for source scanning in
     Tailwind v4. Source discovery is automatic by default and remains a
     CSS concern managed with directives such as `@source` or `source()`
     in `@import "tailwindcss" source("../src")`, even when `@config`
     loads a legacy JS config file.
2. **Utility Deprecations & Renames:**
   - The `npx @tailwindcss/upgrade` tool is highly recommended and
     automates most of this.
   - Opacity syntax is now consistently `bg-black/50` (no more
     `bg-opacity-50`).
   - Scales for `shadow`, `rounded`, and `blur` have been normalized
     (e.g., `shadow` -> `shadow-sm`, `shadow-sm` -> `shadow-xs`).
   - `ring` default width is now `1px` (was `3px`); use `ring-3` for the
     old default.
3. **Default Value Adjustments:**
   - Default border colour is now `currentColor`. Explicitly add colour
     classes like `border-gray-200` when the v3 default gray was
     previously relied upon.
   - Default ring colour is `currentColor` (was `blue-500`).
4. **Selector Modifications:**
   - `space-x-*` and `space-y-*` utilities now apply logical margins to
     children via a `:where(...):not(:last-child)` selector:
     `space-x-*` sets `margin-inline-start`/`margin-inline-end`, and
     `space-y-*` sets `margin-block-start`/`margin-block-end`. This
     improves right-to-left behaviour but might affect layouts with
     existing tweaked margins; flex/grid `gap` is often a better
     alternative.
   - Variant stacking order is now left-to-right (e.g.,
     `dark:md:hover:bg-red-500`) for CSS-like consistency.
5. **Custom Utility Definition:**
   - `@utility` directive replaces `@layer components` or `@layer
     utilities` for defining custom, variant-aware utility classes. This
     ensures proper integration with Tailwind's engine and cascade
     layers.

     ```css
     @utility btn-primary {
       background-color: var(--color-brand-500);
       /* ... */
     }
     ```

   - Functional utilities (e.g., `tab-*` matching `tab-2`, `tab-github`)
     are defined using `@utility` with a `--value()` function to parse
     arguments and match theme keys or arbitrary values.
6. **`@apply` in Scoped Styles (Vue SFCs, Svelte, CSS Modules):**
   - Due to isolated processing of these style blocks by build tools,
     theme variables, custom utilities, and variants defined in global
     CSS are not automatically available.
   - Use `@reference "../path/to/main.css";` *inside* the scoped style
     block to make these available without duplicating CSS output.
   - Alternatively, directly use CSS variables (`var(--color-brand-500)`)
     instead of `@apply` for better performance and simpler processing.
7. **Prefix Syntax:**
   - Utility prefixes are now variant-like: `tw:bg-red-500`. Theme
     variables in `@theme` remain unprefixed, but generated CSS
     variables *will* be prefixed (e.g., `--tw-color-red-500`).
8. **Arbitrary Value Syntax for CSS Variables:**
   - Using CSS variables in arbitrary values now uses parentheses:
     `bg-(--my-brand-color)` instead of `bg-[--my-brand-color]`. This
     resolves ambiguity with other arbitrary value types.

## IV. Advanced Capabilities & Modern CSS Integration

1. **Enhanced Variant System:**
   - Comprehensive support for ARIA attributes (`aria-checked:`,
     `aria-disabled:`). Custom `aria-*` variants can be defined.
   - Data attribute variants (`data-[size=large]:`, `data-active:`).
   - `:has()` pseudo-class support via `has-*` variants (e.g.,
     `has-[:focus]:`).
   - Child (`*`) and descendant (`**`) combinator variants (e.g.,
     `*:p-2`, `**:data-avatar:rounded-full`).
   - `group-*` and `peer-*` variants can now be named for more complex
     nesting/sibling scenarios (e.g., `group/item`, `peer-checked/opt1:`).
2. **Container Queries:**
   - Enabled via `@container` class on the parent.
   - Size-based variants (`@sm:`, `@lg:`, or arbitrary `@min-[475px]:`)
     style children based on the container's width.
   - Named containers (`@container/sidebar`, `@lg/sidebar:`) allow
     targeting specific ancestor containers.
   - Container query length units (`cqw`, `cqi`) can be used in
     arbitrary values (e.g., `w-[50cqw]`).
3. **Native CSS Features:**
   - Tailwind v4 is built upon and encourages the use of native CSS
     variables, nesting (processed by Lightning CSS), `color-mix()`,
     `calc()`, etc.

## V. Workflow Adjustments & Deprecations

1. **Preprocessors (Sass/Less/Stylus):**
   - Not designed for use with Tailwind v4. Tailwind itself, with its
     CSS-native features and internal processing via Lightning CSS,
     fulfils most preprocessor roles.
2. **`theme()` Function in CSS:**
   - Deprecated. Use `var(--css-variable-name)` instead. For media
     queries where `var()` isn't supported, `theme(--breakpoint-xl)`
     (using the CSS variable name) can be used.
3. **`corePlugins` in JS Config:**
   - Disabling core plugins via JS config is no longer supported. Manage
     utility generation by not using unwanted classes or explicitly
     excluding them if necessary via `@source not inline(...)`.

Tailwind CSS v4 represents a leaner, faster, and more CSS-idiomatic approach.
The upgrade tool (`npx @tailwindcss/upgrade`) is crucial for v3 projects. For
new projects, understanding the CSS-first configuration and modern CSS
dependencies is key.
