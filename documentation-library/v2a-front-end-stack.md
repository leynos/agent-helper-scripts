# v2a front-end stack

This document describes the df12 Productions v2a front-end stack in two tiers:

- the mockup tier, which declares and wires enough of the stack to exercise a
  design end to end, and
- the full application tier, which adds the local-first data and orchestration
  tooling a production application needs.

That distinction matters because the mockup tier already exercises much of the
UI, styling, routing, localization, and map stack, while the full application
tier layers local-first data and orchestration on top without changing the
rendering model.

Where an example needs a concrete name, `app` stands in for the name of the
application that adopts the stack.

## Overview

v2a front ends are client-side single-page applications (SPAs) built on a
shared stack: Bun, Vite, React 19, TanStack Router, Tailwind CSS v4, and
DaisyUI v5. They share Radix UI primitives for interactive components, i18next
with Fluent translation bundles for localization, and a common
data-model-driven card architecture for presenting domain entities.

The map canvas, tile rendering, and location-aware UI belong to map-based
product domains. They are part of the stack for an application that models
map-based exploration, not something every v2a front end needs.

## Stack layers at a glance

### Mockup tier stack

The mockup tier uses:

- Bun,
- Vite 5,
- React 19,
- TanStack Router,
- Tailwind CSS v4,
- DaisyUI v5,
- Radix UI,
- i18next plus Fluent,
- MapLibre GL JS for map-based domains, and
- the test, lint, and type-check toolchain described below.

### Full v2a application stack

The full application tier adds:

- **Zustand** for interactive client and UI state,
- **TanStack Query** for server-state fetching, caching, and synchronization,
- **Dexie** for durable browser-side storage of offline bundles, map tiles, and
  related heavier local data, and
- **XState** for modelling more complex interaction and workflow orchestration
  where a reducer or plain context store becomes too implicit.

In other words, the mockup tier shows the presentation and navigation layer
already working, while the full application tier includes a richer local-first
state and data architecture. The guide to
[local-first React](local-first-react.md) covers that combination in depth.

## Runtime and build toolchain

- **Package manager and runner:** Bun drives local scripts, tests, and token
  generation via `package.json` and `bunfig.toml`.
- **Bundler and dev server:** Vite 5 is the application bundler and development
  server.
- **React integration:** `@vitejs/plugin-react` handles JSX and React Fast
  Refresh.
- **Tailwind integration:** Tailwind v4 runs through `postcss.config.cjs`,
  which Vite uses during both development and production builds.
- **Module format:** Projects are ECMAScript Modules (ESM)-only, declared with
  `"type": "module"` in `package.json`.
- **Base-path handling:** `vite.config.ts`, `src/i18n.ts`, and
  `src/app/routes/app-routes.tsx` normalize `APP_BASE_PATH` and
  `import.meta.env.BASE_URL` so the SPA can run correctly under a subpath such
  as GitHub Pages.

In practice, the front-end entry path is:

1. `src/main.tsx` boots React with `StrictMode` and `Suspense`.
2. `src/app/app.tsx` wires global providers.
3. `src/app/routes/app-routes.tsx` mounts the TanStack Router tree.

The short guide to [React and Tailwind with Bun](react-tailwind-with-bun.md)
covers the mechanics of that toolchain.

## Core application framework

### React

The UI is built with React 19 and `react-dom/client`. The bootstrap file,
`src/main.tsx`, mounts the SPA into `#root`, provides a loading fallback via
Suspense, and avoids rendering during tests.

### Routing

Routing is handled by TanStack Router:

- `src/app/routes/app-routes.tsx` creates the router.
- `src/app/routes/route-tree.tsx` assembles the route tree.
- Route modules live under `src/app/routes/`.

The route tree is explicit and file-shaped in practice, even though it is wired
manually rather than generated. Route groups follow the application's own
sitemap, with a module per screen or flow.

### State management

In the mockup tier there is no declared global client-state library such as
Redux, Zustand, or XState. State is managed through:

- React component state and hooks,
- a `ThemeProvider` plus the i18n runtime, and
- route-local and component-local state for shell and screen behaviour.

That keeps the mockup tier closer to a React-plus-context architecture than a
state-machine or data-cache architecture.

For the full application tier, the state split is broader:

- **Zustand** owns interactive client and UI state,
- **TanStack Query** owns server and synchronized domain state, and
- **XState** is the right fit for explicit multistep workflows or long-running
  interaction logic that benefits from a formal state machine.

## Styling and design system

### Tailwind CSS and DaisyUI

The styling stack is built on Tailwind CSS v4 and DaisyUI v5, described in the
[Tailwind v4 guide](tailwind-v4-guide.md) and the
[DaisyUI v5 guide](daisyui-v5-guide.md).

- `src/index.css` imports Tailwind and the generated token CSS first, then
  layers project-specific component and utility styles on top.
- `tailwind.config.cjs` loads generated Tailwind theme extensions from
  `tokens/dist/tailwind.theme.cjs`.
- DaisyUI is registered as a Tailwind plugin in `tailwind.config.cjs`.

The styling approach is not utility-only. Projects use a hybrid of:

- Tailwind utilities,
- DaisyUI component classes such as `btn`, and
- semantic project classes defined in `src/index.css` and the files under
  `src/styles/`.

The guide to
[semantic Tailwind with DaisyUI](semantic-tailwind-with-daisyui-best-practice.md)
sets out how to divide work between those three layers, and the guide to
[enforcing semantic Tailwind](enforcing-semantic-tailwind-best-practice.md)
covers the lint rules that hold the division in place.

### Design tokens

Design tokens are a first-class part of the stack.

- `tokens/build/style-dictionary.js` uses Style Dictionary to generate token
  artefacts.
- `bun run tokens:build` produces:
  - `tokens/dist/tokens.css` for runtime CSS variables and theme output, and
  - `tokens/dist/tailwind.theme.cjs` for Tailwind theme extension data.
- `vite.config.ts` watches the generated token outputs and triggers a full-page
  reload when they change.

This means the front-end theme layer is not hand-maintained in one place.
Instead, the design source of truth lives in the token package, and both CSS
and Tailwind consume generated outputs.

### Theme handling

Theme selection is handled with a small React context rather than a theme
framework:

- `src/app/providers/theme-provider.tsx` persists the active theme in
  `localStorage`.
- The provider sets `data-theme` on the document root and body.
- Theme names are scoped to the application, conventionally a day and a night
  theme such as `app-day` and `app-night`.

### PostCSS

`postcss.config.cjs` applies:

- `@tailwindcss/postcss`,
- `autoprefixer`, and
- a small custom plugin that removes DaisyUI's `@property --radialprogress`
  rule to avoid Lightning CSS warnings during Vite builds.

## Component primitives and icons

The UI component layer uses Radix UI packages for interaction primitives,
including dialogs, popovers, tabs, switches, sliders, selects, accordions, and
toasts. Those primitives are deliberately unstyled and follow the Accessible
Rich Internet Applications (ARIA) authoring practices, so keyboard support,
focus management, and assistive-technology wiring come from the primitive
rather than from each screen that uses it. The component layer also depends on:

- `@tabler/icons-react` for iconography,
- `@radix-ui/react-icons` for supplemental icons, and
- `clsx` for conditional class composition.

This gives v2a front ends a Radix-behaviour plus Tailwind/DaisyUI-presentation
shape, rather than a single monolithic component framework. The architectural
guide to
[pure, accessible, and localizable React components](pure-accessible-and-localizable-react-components.md)
describes the component layer that sits on those primitives.

## Localization stack

Localization is one of the more specialized parts of the stack.

- `src/i18n.ts` configures `i18next`.
- `react-i18next` integrates translations with React.
- `i18next-fluent` and `i18next-fluent-backend` load Fluent `.ftl` bundles.
- Locale files live in `public/locales/<locale>/common.ftl`.
- `src/app/i18n/supported-locales.ts` defines supported locales and direction
  metadata.

The detection order is intentionally narrow:

- query string first, then
- `localStorage`.

Navigator-based detection is deliberately excluded to keep first loads more
deterministic. The runtime also updates `lang`, `dir`, and related attributes
on the document so right-to-left languages such as Arabic and Hebrew are
handled correctly.

## Map stack

Interactive map views use MapLibre GL JS, but this should be understood as a
domain-specific layer rather than a foundational part of the general front-end
stack. The map, tile, and location elements exist where an application is
map-based, with itinerary, route, and saved-place flows.

- The fuller map stack is expected to lazy-load `maplibre-gl` and its CSS.
- OpenMapTiles-backed styling supplies the base map presentation.
- The integration is expected to register the MapLibre right-to-left text
  plugin when the runtime supports it.
- Shared viewport and layer state should live in a dedicated map-state module.

The map layer is therefore intended to be a real interactive map integration,
not only a static mockup image.

In the full application tier, map-related persistence is also expected to touch
the broader local-first stack:

- TanStack Query for route and place data,
- Dexie for offline bundles, map tile storage, and other heavier offline
  artefacts, and
- UI state or workflow orchestration layered above that with Zustand and, where
  useful, XState.

## Testing and verification stack

v2a front ends carry a broader-than-average verification setup.

### Unit and component tests

- `bun test` is the primary unit and component test runner.
- `tests/setup-happy-dom.ts` creates the DOM environment with Happy DOM.
- React component tests use Testing Library packages.
- `tests/setup-snapshot-guard.ts` fails the run if snapshots are left unchecked
  or updated unexpectedly.

### Accessibility-focused tests

There are two accessibility layers:

- `bun run test:a11y` runs Vitest in a dedicated `jsdom` configuration for
  `*.a11y.test.ts(x)` files.
- `bun run test:e2e` runs Playwright tests, including `@axe-core/playwright`
  sweeps against key routes.

The blueprint for
[high-velocity, accessibility-first testing](high-velocity-accessibility-first-component-testing.md)
sets out how those layers divide responsibility.

### End-to-end tests

`playwright.config.ts` launches or reuses a Vite dev server, targets a mobile
viewport, and runs the browser suite under Chromium. That fits the mobile-first
nature of the stack.

## Linting, type-checking, and semantic checks

The front-end quality stack goes beyond a simple formatter plus linter.

- `bun fmt` runs Biome formatting.
- `bun lint` runs Biome checks across source, tests, tools, and docs.
- `bun check:types` runs strict TypeScript checking with `tsc --noEmit`.
- `bun run semantic` layers on extra structural checks:
  - class-list length and near-duplicate class scripts,
  - Semgrep rules from `tools/semgrep-semantic.yml`, and
  - Stylelint checks for CSS.
- `bun run lint:ftl-vars` validates Fluent variable usage.

The strict TypeScript settings in `tsconfig.json` include:

- `strict`,
- `noUncheckedIndexedAccess`,
- `exactOptionalPropertyTypes`,
- `noImplicitOverride`, and
- `noPropertyAccessFromIndexSignature`.

## Data model-driven card architecture

All v2a front ends share a common pattern for presenting domain entities on
cards, lists, and detail screens. Entity models carry their own localized
strings rather than delegating display-text responsibility to the Fluent
translation bundles. This keeps Fluent bundles focused on UI chrome (button
labels, ARIA labels, section headings, format strings) while letting each
entity own its names, descriptions, and badge text per locale.

### Shared primitives

The following types form the shared vocabulary across all v2a front ends:

- **`LocaleCode`** — a branded string identifying a supported locale (e.g.
  `en-GB`, `ja`).
- **`LocalizedStringSet`** — a record mapping `LocaleCode` keys to translated
  display strings.
- **`EntityLocalizations`** — a per-entity bundle that groups together every
  `LocalizedStringSet` the entity needs (name, description, badge text, and so
  on).
- **`LocalizedAltText`** — a `LocalizedStringSet` specifically for image alt
  text, kept as a distinct type so that accessibility tooling can enforce its
  presence.
- **`ImageAsset`** — a reference to an image file together with its
  `LocalizedAltText`.

### Locale resolution

A small pure helper, `pickLocalization(localizations, locale)`, resolves a
`LocalizedStringSet` for the requested locale. If the exact locale is not
present, the helper falls back to `en-GB`. This single function is the only
place where locale-fallback logic lives, keeping the rest of the rendering code
free of null checks or conditional chains.

### Descriptor registries

Stable internal identifiers (e.g. `task-status:in-progress`, `priority:high`)
are resolved to localized display strings through descriptor registries. Each
registry maps an identifier to a descriptor object whose labels are
`LocalizedStringSet` values. This means that badge colours, icons, and display
names for status values, priority levels, and similar enumerations are defined
once and shared by every component that renders them.

### Folder layout

The conventional folder layout is:

- `src/app/domain/entities/` — TypeScript interfaces and type aliases for
  entity models and their localization shapes.
- `src/data/entities/` — fixture data used during the mockup phase, structured
  to match the entity interfaces exactly.
- `src/data/registries/` — descriptor registry modules that map stable
  identifiers to localized descriptors.

### Application-specific schemas

The shared
[data model-driven card architecture](data-model-driven-card-architecture.md)
defines the pattern itself. Each application maintains its own edition of that
document, which defines the application-specific entity schemas, enumerations,
and migration roadmap. The per-application edition is the authoritative
reference for which entities exist, what fields they carry, and how the card
architecture evolves as a mockup matures toward production data sources.

## Effective stack summary

For the shortest accurate summary of the mockup tier, the front-end stack is:

- Bun for package management, scripts, and the primary test runner,
- Vite 5 for bundling and development,
- React 19 for the SPA runtime,
- TanStack Router for routing,
- Tailwind CSS v4 plus DaisyUI v5 for styling,
- Style Dictionary for generated design tokens and themes,
- Radix UI primitives for interactive components,
- i18next plus Fluent for localization,
- a data-model-driven card architecture for entity display strings,
- Biome, TypeScript, Stylelint, Semgrep, and custom scripts for code quality,
  and
- Happy DOM, Testing Library, Vitest, Playwright, and axe-core for testing.

For map- and location-based applications specifically, add a domain layer atop
that stack:

- MapLibre GL JS for interactive maps,
- OpenMapTiles-backed tile styling, and
- location-centric UI and state for itinerary and route experiences.

For the shortest accurate summary of the full application tier, add:

- Zustand for interactive state,
- TanStack Query for server-state caching and synchronization,
- Dexie for offline bundle and map tile storage, and
- XState for explicit interaction orchestration where state machines are
  warranted.

## What the mockup tier leaves out

To avoid confusion, this section refers to the mockup tier, not the full
application tier described above.

A mockup declares the presentation, navigation, styling, and localization
layers, but not the local-first data layer: Zustand, TanStack Query, Dexie, and
XState arrive with the full application tier.

The following common front-end tools belong to neither tier:

- TanStack Table,
- Redux,
- Next.js, Remix, or any server-side rendering (SSR) framework, and
- Framer Motion.
