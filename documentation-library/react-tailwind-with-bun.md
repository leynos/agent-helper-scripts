# React + Tailwind with Bun 1.3.0+ — a short, no‑nonsense guide

This is a pragmatic walkthrough for building and serving a tiny React +
Tailwind app using **Bun 1.3.0 or later**. It leans on Bun’s built‑in dev
server (HMR, React Fast Refresh) and production bundler.

______________________________________________________________________

## 0) Prerequisites

- Node/npm not required, but fine to have.
- Bun **1.3.0 or later** installed:

```bash
# Linux/macOS
curl -fsSL https://bun.sh/install | bash

# Homebrew (macOS)
brew tap oven-sh/bun
brew install bun

# Windows (PowerShell)
powershell -c "irm bun.sh/install.ps1 | iex"

# Or globally via npm (works, but native installer is preferred)
npm install -g bun
```

Verify:

```bash
bun --version  # expect 1.3.0 or later
```

______________________________________________________________________

## 1) Scaffold a React + Tailwind project

Bun ships templates. Use the Tailwind variant to avoid manual setup.

```bash
mkdir my-app && cd my-app
bun init --react=tailwind
# Follow the prompts; accept defaults if unsure.
```

The scaffold provides:

- React + TS/JS wired up for Bun’s **HTML‑first** dev server.
- Tailwind preconfigured with the v4 CSS-first entry and automatic source
  detection.

______________________________________________________________________

## 2) Run the dev server (with HMR)

Bun 1.3 can serve HTML entry points directly and handle bundling/transpilation
under the hood.

```bash
bun './**/*.html'
# or simply:
bun ./index.html
```

A URL like `http://localhost:3000/` and a routes table are displayed. Open the
address in a browser. Edits to React components hot‑reload instantly (React
Fast Refresh).

> Tip: Bun pipes browser `console.log` back to the terminal, which helps with
> quick debugging.

______________________________________________________________________

## 3) Hello React + Tailwind

The template includes a basic app. If starting from a blank template, here’s
the minimal shape.

**`index.html`** (HTML import entry; Bun resolves and bundles dependencies):

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Bun + React + Tailwind</title>
    <link rel="stylesheet" href="./src/index.css" />
  </head>
  <body class="min-h-screen bg-slate-950 text-slate-100">
    <div id="root"></div>
    <script type="module" src="./src/main.tsx"></script>
  </body>
</html>
```

**`src/index.css`** (Tailwind v4 CSS-first entry):

```css
@import "tailwindcss";
/* Add @source only when templates live outside Tailwind's automatic scan roots. */
```

**`src/main.tsx`**:

```tsx
import React from "react";
import { createRoot } from "react-dom/client";

function App() {
  return (
    <main className="grid min-h-screen place-items-center p-6">
      <section className="text-center">
        <h1 className="text-3xl font-bold tracking-tight">Hello, Bun 🥖</h1>
        <p className="mt-2 text-slate-300">
          React + Tailwind served by Bun 1.3 with hot reload.
        </p>
        <button className="mt-6 rounded-xl bg-emerald-500 px-4 py-2 font-medium text-emerald-950 hover:bg-emerald-400">
          Click me
        </button>
      </section>
    </main>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
```

Tailwind config (`tailwind.config.{js,ts}`) should omit `content` globs. Add
`@source` directives in CSS only when scan roots are outside Tailwind's
automatic detection, e.g.:

```js
export default {
  theme: { extend: {} },
  plugins: [],
};
```

______________________________________________________________________

## 4) Build for production

Bun bundles HTML, TS/JS, CSS assets. Use `--production` for minification and
tree‑shaking.

```bash
bun build ./index.html --production --outdir=dist
```

The result is a _fully bundled_ `dist/` directory ready to host anywhere.

______________________________________________________________________

## 5) Serve the production build

### Easiest: any static file host

- Copy `dist/` to S3/Cloudflare Pages/Netlify/Vercel/nginx/Apache. Done.

### With Bun itself (simple static server)

For local preview or DIY hosting, a tiny Bun server can serve the `dist`
folder. Example SPA‑safe server that falls back to `index.html`:

```ts
// server.ts
import { serve } from "bun";

serve({
  port: 3000,
  async fetch(req) {
    const url = new URL(req.url);
    const filePath = url.pathname === "/" ? "/index.html" : url.pathname;
    const file = Bun.file(`./dist${filePath}`);

    if (await file.exists()) return new Response(file);

    // SPA fallback (client‑side routing)
    return new Response(Bun.file("./dist/index.html"), {
      headers: { "Content-Type": "text/html; charset=utf-8" },
    });
  },
});
```

Run it:

```bash
bun run server.ts
```

______________________________________________________________________

## 6) (Optional) One‑process full‑stack dev

For a single process serving the SPA **and** APIs during development, use HTML
imports + `Bun.serve()` routes.

```ts
// dev-serve.ts
import homepage from "./index.html";
import { serve } from "bun";

serve({
  development: { hmr: true, console: true },
  routes: {
    "/": homepage,
    "/api/health": () => Response.json({ status: "ok" }),
  },
});
```

Start it:

```bash
bun run dev-serve.ts
```

The setup still provides HMR, HTML bundling, and a tidy `/api/*` space without
CORS faff.

______________________________________________________________________

## 7) Troubleshooting

- **Tailwind classes not applying**: ensure `index.css` is linked in
  `index.html`; add an `@source` directive only when templates are stored
  outside Tailwind's automatic scan roots.
- **404s in production for client‑side routes**: add the SPA fallback (see
  server example) or configure the static host’s rewrite rules.
- **HMR not triggering**: ensure the dev server started via `bun
  './**/*.html'` or a `Bun.serve()` with `development.hmr: true`.
- **TypeScript module quirks**: Bun defaults to `"module": "Preserve"`; avoid
  incompatible TS transforms in the project's own config.

______________________________________________________________________

## 8) Bonus: compile to a single executable (advanced)

Compiling `./index.html` directly only bundles the static asset; it cannot
produce a server. Instead, compile a small entry point that imports the HTML
and starts `Bun.serve()`:

```ts
// server.ts
import homepage from "./index.html";
import { serve } from "bun";

serve({
  routes: {
    "/": homepage,
    "/api/health": () => Response.json({ status: "ok" }),
  },
});
```

```bash
bun build --compile ./server.ts --outfile myapp
./myapp  # launches the HTTP server; more routes can be added in code
```

Use this for kiosk‑style SPAs or internal tools where “download and run” beats
provisioning infra.

______________________________________________________________________

## That’s it

The flow is: scaffold → dev server with HMR → Tailwind styling → production
bundle → optional Bun‑served hosting. Compact, fast, and pleasantly free of
yak‑hair.
