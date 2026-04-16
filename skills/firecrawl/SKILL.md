---
name: firecrawl-mcp
description: >
  Using the Firecrawl MCP server to scrape, search, crawl, extract, and browse
  the web. Use this skill whenever the Firecrawl MCP tools are available and
  you need to retrieve web content, discover URLs on a site, search the web
  with full-page content retrieval, extract structured data from pages, perform
  autonomous multi-source web research, or interact with web pages through a
  remote browser sandbox. Trigger this skill for any task involving
  firecrawl_scrape, firecrawl_search, firecrawl_map, firecrawl_crawl,
  firecrawl_extract, firecrawl_agent, or firecrawl_browser_* tools. Also
  trigger when the user asks you to "scrape", "crawl", "map a site",
  "extract data from a page", "search with Firecrawl", or "use the browser
  sandbox", even if they don't mention Firecrawl by name — provided the MCP
  tools are connected.
---

# Firecrawl MCP — Agent Skill

This skill governs how to use the Firecrawl MCP server tools effectively.
It assumes the MCP server is already connected and authenticated.

## Tool inventory

The Firecrawl MCP exposes 12 tools across five capabilities:

| Capability | Tools | Async? |
|---|---|---|
| **Scrape** | `firecrawl_scrape` | No |
| **Search** | `firecrawl_search` | No |
| **Map** | `firecrawl_map` | No |
| **Crawl** | `firecrawl_crawl`, `firecrawl_check_crawl_status` | Yes |
| **Extract** | `firecrawl_extract` | No |
| **Agent** | `firecrawl_agent`, `firecrawl_agent_status` | Yes |
| **Browser** | `firecrawl_browser_create`, `firecrawl_browser_execute`, `firecrawl_browser_delete`, `firecrawl_browser_list` | Session |

## Choosing the right tool

Apply this decision tree top-to-bottom. Pick the **first** match.

1. **You have a single URL and need its content** → `firecrawl_scrape`
2. **You need to find pages on the open web by query** → `firecrawl_search`
3. **You need to discover URLs within a single domain** → `firecrawl_map`
4. **You need content from many pages under one domain** → `firecrawl_crawl`
5. **You need structured fields from one or more known URLs** → `firecrawl_extract`
6. **You have a complex, open-ended research question spanning multiple unknown sources** → `firecrawl_agent`
7. **You need to interact with a page (fill forms, click, authenticate)** → `firecrawl_browser_*`

When in doubt between scrape and search: if you already have the URL, scrape.
If you need to find the URL first, search.

When in doubt between extract and scrape-with-JSON-format: `firecrawl_extract`
operates on multiple URLs and uses Firecrawl's server-side LLM. The JSON
format on `firecrawl_scrape` works on a single page and also uses server-side
extraction. Prefer `firecrawl_extract` when pulling uniform structured data
from several pages. Prefer scrape with JSON format when you want markdown
*and* structured data from the same single page in one call.

When in doubt between crawl and map-then-scrape: crawl is a single async job
that handles traversal and scraping together. Map-then-scrape gives you more
control (you can filter the URL list before scraping selectively). Prefer
map-then-scrape when you only need a subset of pages; prefer crawl when you
want everything under a domain up to a depth/limit.

## Credit costs — be frugal

Every tool call consumes API credits. Minimise unnecessary calls.

| Tool | Base cost |
|---|---|
| `firecrawl_scrape` | 1 credit per page |
| `firecrawl_search` | 1 credit per result (+ scrape costs if `scrapeOptions` used) |
| `firecrawl_map` | 1 credit per call (regardless of URL count returned) |
| `firecrawl_crawl` | 1 credit per page crawled |
| `firecrawl_extract` | Varies; LLM extraction adds cost |
| `firecrawl_agent` | Varies by research scope |
| `firecrawl_browser_*` | Session-based billing |

**Additional surcharges:** JSON mode adds 4 credits/page. Enhanced proxy adds
4 credits/page. PDF parsing adds 1 credit per PDF page.

Always set `limit` on crawl and map calls. The default crawl limit is 10,000
pages — a runaway crawl will burn through credits fast. Start with a low limit
(10–50) and increase only if needed.

## Core patterns

### Pattern 1: Scrape a known URL

```json
{
  "name": "firecrawl_scrape",
  "arguments": {
    "url": "https://example.com/pricing",
    "formats": ["markdown"],
    "onlyMainContent": true
  }
}
```

Set `onlyMainContent: true` to strip nav, footer, and sidebar boilerplate.
This reduces token count and improves downstream processing.

**Available formats:** `markdown`, `html`, `rawHtml`, `screenshot`,
`links`, `json`, `images`, `branding`, `summary`.

Request only the formats you need. Multiple formats in one call are
fine — the page is fetched once.

For pages that require JavaScript rendering or contain dynamic content,
Firecrawl handles this automatically. If a standard scrape fails or returns
incomplete content, consider using `waitFor` (milliseconds) to let JS finish,
or use `actions` for pages that need interaction before content appears.

→ For full scrape options, read `references/scrape-options.md`.

### Pattern 2: Search the web

```json
{
  "name": "firecrawl_search",
  "arguments": {
    "query": "Rust async runtime benchmarks 2025",
    "limit": 5
  }
}
```

Without `scrapeOptions`, search returns metadata only (URL, title,
description, position). Add `scrapeOptions` to get full page content
from each result in one operation — but note this multiplies credit cost.

**Time-based filtering** with `tbs`: `qdr:d` (past day), `qdr:w` (past
week), `qdr:m` (past month). Essential for finding recent content.

**Source types** via `sources`: `["web"]` (default), `["news"]`,
`["images"]`, or combinations. The `limit` applies per source type.

**Category filtering** via `categories`: `["github"]`, `["research"]`,
`["pdf"]`. Narrows results to specific domains (GitHub repos, academic
sites, PDF documents respectively).

→ For full search options, read `references/search-options.md`.

### Pattern 3: Map a site's URL structure

```json
{
  "name": "firecrawl_map",
  "arguments": {
    "url": "https://docs.example.com",
    "search": "authentication",
    "limit": 100
  }
}
```

Map returns an array of URLs (with optional title/description). It does
**not** return page content. Use it as a reconnaissance step before
selective scraping.

The `search` parameter filters returned URLs by relevance to a term —
useful when you only need the authentication docs from a large site,
for instance.

Set `ignoreQueryParameters: true` to deduplicate URLs that differ only
by query string.

### Pattern 4: Crawl an entire site (async)

```json
{
  "name": "firecrawl_crawl",
  "arguments": {
    "url": "https://docs.example.com",
    "maxDiscoveryDepth": 2,
    "limit": 50,
    "deduplicateSimilarURLs": true
  }
}
```

Crawl is **asynchronous**. It returns a job ID immediately. Poll with
`firecrawl_check_crawl_status` using that ID. Allow 15–30 seconds between
polls. The status will be `scraping`, `completed`, or `failed`.

By default, crawl stays within the URL's path hierarchy. Set
`allowExternalLinks: true` to follow links to other domains (use with
caution — credit implications). Set `allowSubdomains: true` to include
subdomains like `blog.example.com` when crawling `example.com`.

All scrape options (formats, `onlyMainContent`, actions, location, tags)
can be passed via `scrapeOptions` and apply to every page the crawler
visits.

→ For full crawl options, read `references/crawl-options.md`.

### Pattern 5: Extract structured data

```json
{
  "name": "firecrawl_extract",
  "arguments": {
    "urls": ["https://example.com/product/1", "https://example.com/product/2"],
    "prompt": "Extract the product name, price, and availability status",
    "schema": {
      "type": "object",
      "properties": {
        "name": { "type": "string" },
        "price": { "type": "number" },
        "in_stock": { "type": "boolean" }
      },
      "required": ["name", "price"]
    }
  }
}
```

The `schema` follows JSON Schema format. If omitted, the LLM chooses
its own structure guided by `prompt`. Providing a schema is strongly
recommended for consistent, parseable output.

### Pattern 6: Autonomous research agent (async)

```json
{
  "name": "firecrawl_agent",
  "arguments": {
    "prompt": "Find the pricing tiers and feature limits for Vercel, Netlify, and Cloudflare Pages. Compare them.",
    "schema": {
      "type": "object",
      "properties": {
        "providers": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "name": { "type": "string" },
              "tiers": { "type": "array", "items": { "type": "object" } }
            }
          }
        }
      }
    }
  }
}
```

The agent is async — it returns a job ID. Poll `firecrawl_agent_status`
every 15–30 seconds. Allow at least 2–3 minutes before treating it as
failed. The agent autonomously searches, navigates, and extracts.

Provide `urls` to focus the agent on specific pages. Omit `urls` to let
it search freely. The `prompt` is limited to 10,000 characters.

Best for: complex cross-site research where you don't know the exact URLs
in advance, or where content is spread across many pages.

### Pattern 7: Browser sandbox sessions

For interactive web tasks (form filling, authentication, multi-step
navigation), use the browser sandbox.

**Lifecycle:**
1. `firecrawl_browser_create` — start a session (returns session ID)
2. `firecrawl_browser_execute` — run code in the session (repeatable)
3. `firecrawl_browser_delete` — destroy the session when finished

**Always delete sessions when done.** Sessions have TTLs but leaving
them open wastes resources.

→ For full browser options and commands, read `references/browser-options.md`.

## Handling asynchronous tools

Both `firecrawl_crawl` and `firecrawl_agent` are async. The workflow is:

1. Call the tool → receive a job ID.
2. Poll the status tool with that ID every 15–30 seconds.
3. On `completed`, the response includes the results.
4. On `failed`, report the error. Consider retrying with adjusted parameters.

Do not poll more frequently than every 15 seconds — it wastes rate-limit
budget and the status endpoints have their own rate limits.

## Error handling

The MCP server handles retries internally with exponential backoff (default:
3 attempts, starting at 1s, doubling each time, capped at 10s). If a call
still fails after retries, you will receive an error response.

Common errors:
- **Rate limit exceeded:** Back off and retry after the indicated delay. Check
  whether you're making unnecessary calls that can be consolidated.
- **Credit limit warnings:** The server emits warnings at configurable
  thresholds. If you see a credit warning, inform the user and stop
  non-essential operations.
- **Timeout:** Increase the `timeout` parameter or simplify the request
  (fewer actions, simpler schema, lower page count).

## Anti-patterns

- **Scraping then extracting the same page:** Use `firecrawl_scrape` with
  `formats: ["markdown", "json"]` to get both in one call, or use
  `firecrawl_extract` if you only need structured data.
- **Crawling an entire domain to find one page:** Use `firecrawl_map` with
  the `search` parameter first, then scrape the specific URL.
- **Polling status every 2 seconds:** Wastes rate-limit budget. Use 15–30
  second intervals.
- **Omitting `limit` on crawl:** The default is 10,000 pages. Always set an
  explicit limit.
- **Using `firecrawl_agent` for single-page tasks:** The agent is designed
  for multi-source research. For single pages, `firecrawl_scrape` or
  `firecrawl_extract` are faster, cheaper, and more predictable.
- **Requesting `rawHtml` when `markdown` suffices:** `rawHtml` is large
  and rarely needed for LLM consumption. Use `markdown` by default;
  `html` (cleaned) if you need structure; `rawHtml` only for debugging
  or when you need the exact original markup.
- **Leaving browser sessions open:** Always call `firecrawl_browser_delete`
  when your task is complete. Use `firecrawl_browser_list` to check for
  orphaned sessions.

## Caching

Firecrawl caches scraped pages with a default freshness window of 2 days
(`maxAge: 172800000` ms). Cached responses are significantly faster (up to
5×). Set `maxAge: 0` to force a fresh scrape — but only when you genuinely
need the absolute latest content. A non-zero `maxAge` is almost always the
right choice.

## Reference files

For detailed parameter documentation on each tool, read the appropriate
reference file:

| File | Contents |
|---|---|
| `references/scrape-options.md` | All `firecrawl_scrape` parameters, formats, actions, and location settings |
| `references/search-options.md` | All `firecrawl_search` parameters, source types, categories, and scrape integration |
| `references/crawl-options.md` | All `firecrawl_crawl` parameters, path filtering, scope, and status polling |
| `references/browser-options.md` | Browser session lifecycle, execute languages, agent-browser commands, TTL config |
| `references/extract-agent-options.md` | `firecrawl_extract` schema design and `firecrawl_agent` usage patterns |

Read these files when you need parameter-level detail beyond what this
document covers. For most tasks, the patterns above are sufficient.
