# Scrape Options Reference

Complete parameter reference for `firecrawl_scrape`.

## Parameters

### Core

| Parameter         | Type    | Default        | Description                     |
| ----------------- | ------- | -------------- | ------------------------------- |
| `url`             | string  | *required*     | The URL to scrape               |
| `formats`         | array   | `["markdown"]` | Output formats (see below)      |
| `onlyMainContent` | boolean | `true`         | Strip nav, footer, sidebar, ads |
| `timeout`         | integer | —              | Request timeout in milliseconds |

### Content filtering

| Parameter     | Type     | Description                                                                |
| ------------- | -------- | -------------------------------------------------------------------------- |
| `includeTags` | string[] | Only include content within these HTML tags (e.g. `["article", "main"]`)   |
| `excludeTags` | string[] | Exclude content within these HTML tags (e.g. `["nav", "footer", "aside"]`) |

Use `includeTags` when you know the content lives in a specific container. Use
`excludeTags` to strip known noise elements. These operate on the cleaned HTML
before markdown conversion.

### Rendering

| Parameter             | Type    | Description                                                     |
| --------------------- | ------- | --------------------------------------------------------------- |
| `waitFor`             | integer | Milliseconds to wait for JS rendering before extracting content |
| `mobile`              | boolean | Emulate a mobile viewport                                       |
| `skipTlsVerification` | boolean | Skip TLS certificate verification (use for self-signed certs)   |

### Caching

| Parameter      | Type    | Default              | Description                                       |
| -------------- | ------- | -------------------- | ------------------------------------------------- |
| `maxAge`       | integer | `172800000` (2 days) | Maximum cache age in ms. Set `0` for fresh scrape |
| `storeInCache` | boolean | `true`               | Whether to cache the result of this request       |

### Location and language

| Parameter            | Type     | Description                                                                       |
| -------------------- | -------- | --------------------------------------------------------------------------------- |
| `location.country`   | string   | ISO 3166-1 alpha-2 country code (e.g. `"GB"`, `"DE"`, `"JP"`). Defaults to `"US"` |
| `location.languages` | string[] | Preferred languages in priority order (e.g. `["en", "de"]`)                       |

Firecrawl uses an appropriate proxy for the specified country and emulates the
corresponding language and timezone settings.

## Output formats

| Format           | Key in response  | Notes                                                                            |
| ---------------- | ---------------- | -------------------------------------------------------------------------------- |
| `markdown`       | `markdown`       | Clean markdown. Default and recommended for LLM consumption                      |
| `summary`        | `summary`        | AI-generated summary of the page                                                 |
| `html`           | `html`           | Cleaned HTML (boilerplate removed)                                               |
| `rawHtml`        | `rawHtml`        | Unmodified HTML as received. Large — use sparingly                               |
| `screenshot`     | `screenshot`     | URL to screenshot image. Expires after 24 hours                                  |
| `links`          | `links`          | Array of links found on the page                                                 |
| `json`           | `json`           | Structured extraction (configured by `jsonOptions` — see below)                  |
| `changeTracking` | `changeTracking` | Comparison against the previous scrape of the same URL                           |
| `branding`       | `branding`       | Brand identity extraction (colours, fonts, typography, components)               |
| `query`          | `query`          | Answer driven by `queryOptions` (prompt plus a `directQuote` or `freeform` mode) |
| `audio`          | `audio`          | Audio extracted from supported video URLs, as a signed URL                       |

Multiple formats can be requested in a single call. The page is fetched once.

This list is the `formats` enum of the MCP tool. `images` is **not** a scrape
format on this surface — image results come from `firecrawl_search` source
types instead.

### JSON format (structured extraction via scrape)

On the MCP surface, `formats` holds plain strings and the extraction settings
go in a separate top-level `jsonOptions` object:

```json
{
  "formats": ["markdown", "json"],
  "jsonOptions": {
    "prompt": "Extract the page title and price",
    "schema": {
      "type": "object",
      "properties": {
        "title": { "type": "string" },
        "price": { "type": "number" }
      },
      "required": ["title"]
    }
  }
}
```

| Field                | Type   | Description                                       |
| -------------------- | ------ | ------------------------------------------------- |
| `jsonOptions.prompt` | string | Natural-language description of what to extract   |
| `jsonOptions.schema` | object | JSON Schema defining the desired output structure |

Alternatively, omit `schema` and provide only `prompt` for freeform extraction:

```json
{
  "formats": ["json"],
  "jsonOptions": { "prompt": "Extract all product names and prices" }
}
```

`jsonOptions` is a sibling of `formats`, not an element of it. Format objects
such as `{ "type": "json", "schema": ... }` are rejected by the MCP tool schema
— that nesting belongs to the REST API body, which the server builds for you.

JSON mode adds **4 credits per page** on top of the base scrape cost.

### Branding format

Returns a `BrandingProfile` object containing:

- `colorScheme`: `"light"` or `"dark"`
- `logo`: URL of the primary logo
- `colors`: primary, secondary, accent, background, text, semantic colours
- `fonts`: array of font families
- `typography`: font families, sizes, weights, line heights
- `spacing`: base unit, border radius, padding, margins
- `components`: button, input styles
- `images`: logo, favicon, og:image URLs
- `personality`: tone, energy, target audience

Useful for design system analysis, brand-aware content generation, and building
tools that need to match a site's visual identity.

## Actions

Actions let you interact with a page before scraping. Each action is an object
in the `actions` array, executed in sequence.

| Action type         | Parameters                                          | Purpose                                                                |
| ------------------- | --------------------------------------------------- | ---------------------------------------------------------------------- |
| `wait`              | `milliseconds`                                      | Pause execution. Use before/after other actions to let the page settle |
| `click`             | `selector`                                          | Click an element matching the CSS selector                             |
| `write`             | `text`                                              | Type text into the currently focused element                           |
| `press`             | `key`                                               | Press a keyboard key (e.g. `"Tab"`, `"Enter"`)                         |
| `screenshot`        | `fullPage` (bool)                                   | Take a screenshot at this point in the action sequence                 |
| `scroll`            | `direction` (`"up"` or `"down"`), `amount` (pixels) | Scroll the page                                                        |
| `scrape`            | —                                                   | Scrape the page at this point (captures intermediate state)            |
| `executeJavascript` | `script`                                            | Run a JavaScript snippet in the page                                   |
| `generatePDF`       | —                                                   | Render the current page to a PDF                                       |

The screenshot action takes `fullPage`, not `full_page` — the server ignores or
rejects the snake_case spelling, and the capture stays viewport-sized.

**Always include `wait` actions** before and after actions that trigger page
navigation or content loading. Pages need time to render.

### Example: Log in and scrape dashboard

```json
{
  "url": "https://app.example.com/login",
  "formats": ["markdown"],
  "actions": [
    { "type": "wait", "milliseconds": 1000 },
    { "type": "write", "text": "user@example.com" },
    { "type": "press", "key": "Tab" },
    { "type": "write", "text": "p4ssw0rd" },
    { "type": "click", "selector": "button[type='submit']" },
    { "type": "wait", "milliseconds": 2000 },
    { "type": "screenshot", "fullPage": true }
  ]
}
```

In safe mode only `wait`, `screenshot`, `scroll`, and `scrape` actions are
accepted; `click`, `write`, `press`, `executeJavascript`, and `generatePDF` are
rejected by the schema. Use `firecrawl_interact` when a locked-down deployment
still needs to drive the page.

The final page state (after all actions complete) is what gets scraped.
Screenshots taken via actions are returned in `data.actions.screenshots`.
Intermediate scrapes appear in `data.actions.scrapes`.

## PDF parsing

Firecrawl handles PDFs automatically. Control parsing with the `parsers` option:

```json
{
  "parsers": [{ "type": "pdf", "mode": "auto", "maxPages": 50 }]
}
```

Modes:

- `auto` (default): text extraction first, falls back to OCR if needed
- `fast`: text-based only — fastest, but skips scanned/image-heavy pages
- `ocr`: forces OCR on every page — best for scanned documents

PDF parsing costs 1 additional credit per PDF page.
