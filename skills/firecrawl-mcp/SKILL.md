---
name: firecrawl-mcp
description: >
  Using the Firecrawl MCP server to scrape, search, crawl, and interact with
  the web. Use this skill whenever the Firecrawl MCP tools are available and
  you need to retrieve web content, discover URLs on a site, search the web
  with full-page content retrieval, extract structured data from pages, perform
  autonomous multi-source web research, or drive a page through a live browser
  session. Trigger this skill for any task involving firecrawl_scrape,
  firecrawl_search, firecrawl_map, firecrawl_crawl, firecrawl_agent,
  firecrawl_interact, or firecrawl_interact_stop. Also trigger when the user
  asks you to "scrape", "crawl", "map a site", "extract data from a page",
  "search with Firecrawl", or "interact with a page", even if they don't
  mention Firecrawl by name — provided the MCP tools are connected.
---

# Firecrawl MCP — Agent Skill

This skill governs how to use the Firecrawl MCP server tools effectively. It
assumes the MCP server is already connected and authenticated.

## Supported MCP surface

The tool names and payloads in this skill are pinned to the **full profile of
the Firecrawl hosted MCP endpoint**:

```
https://mcp.firecrawl.dev/v2/mcp
```

An equivalent self-hosted `firecrawl-mcp` deployment at the same version serves
the same contracts. Pin one of those two before relying on these examples: the
exposed tool surface varies by deployment, and several profiles expose strict
subsets or extra tools.

| Profile                                               | Tool surface                                                                                        |
| ----------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| `https://mcp.firecrawl.dev/v2/mcp` (full)             | Every tool this skill documents, plus `firecrawl_parse`, developer search, research, and monitoring |
| Same URL without a credential (keyless free tier)     | `firecrawl_scrape`, `firecrawl_search`, `firecrawl_parse` only                                      |
| `https://mcp.firecrawl.dev/v2/mcp-search` (read-only) | `firecrawl_search`, `firecrawl_developer_search`, and the `firecrawl_research_*` tools              |

`firecrawl_extract` is **not** part of the supported surface. The server keeps
it only as a hidden deprecated entry point (`canList: false`) that is absent
from `tools/list` and fails with an error pointing at the replacements. Use
`firecrawl_scrape` with JSON format for a known URL, and `firecrawl_agent` for
multi-source research.

## Tool inventory

| Capability       | Tools                                           | Async?                                             |
| ---------------- | ----------------------------------------------- | -------------------------------------------------- |
| **Scrape**       | `firecrawl_scrape`                              | No                                                 |
| **Search**       | `firecrawl_search`                              | No                                                 |
| **Map**          | `firecrawl_map`                                 | No                                                 |
| **Crawl**        | `firecrawl_crawl`                               | Yes — polled server-side                           |
| **Crawl status** | `firecrawl_check_crawl_status`                  | No — client-invoked for timed-out or external jobs |
| **Agent**        | `firecrawl_agent`, `firecrawl_agent_status`     | Yes — you poll                                     |
| **Interact**     | `firecrawl_interact`, `firecrawl_interact_stop` | Session (one turn per call)                        |

## Choosing the right tool

Apply this decision tree top-to-bottom. Pick the **first** match.

1. **You have a single URL and need its content** → `firecrawl_scrape`
2. **You need to find pages on the open web by query** → `firecrawl_search`
3. **You need to discover URLs within a single domain** → `firecrawl_map`
4. **You need content from many pages under one domain** → `firecrawl_crawl`
5. **You need structured fields from one or more known URLs** →
   `firecrawl_scrape` once per URL with `formats: ["json"]`
6. **You have a complex, open-ended research question spanning multiple unknown
   sources** → `firecrawl_agent`
7. **You need to interact with a page (fill forms, click, authenticate)** →
   `firecrawl_interact`

When in doubt between scrape and search: if you already have the URL, scrape.
If you need to find the URL first, search.

When in doubt between structured scrape and the agent: `firecrawl_scrape` with
`formats: ["json"]` works on one known page per call and can return markdown
*and* structured data from the same page in one call. `firecrawl_agent` handles
several unknown sources in a single job. Use the agent when you cannot name the
URLs up front or the answer must be assembled across sites; use scrape when you
can.

When in doubt between crawl and map-then-scrape: crawl is a single job that
handles traversal and scraping together. Map-then-scrape gives you more control
(you can filter the URL list before scraping selectively). Prefer
map-then-scrape when you only need a subset of pages; prefer crawl when you
want everything under a domain up to a depth/limit.

## Credit costs — be frugal

Every tool call consumes API credits. Minimize unnecessary calls.

| Tool                 | Base cost                                                    |
| -------------------- | ------------------------------------------------------------ |
| `firecrawl_scrape`   | 1 credit per page                                            |
| `firecrawl_search`   | 1 credit per result (+ scrape costs if `scrapeOptions` used) |
| `firecrawl_map`      | 1 credit per call (regardless of URL count returned)         |
| `firecrawl_crawl`    | 1 credit per page crawled                                    |
| `firecrawl_agent`    | Varies by research scope                                     |
| `firecrawl_interact` | 7 credits/minute with `prompt`; 2 credits/minute code-only   |

**Additional surcharges:** JSON mode adds 4 credits/page. Enhanced proxy adds 4
credits/page. PDF parsing adds 1 credit per PDF page.

Always set `limit` on crawl and map calls. The default crawl limit is 10,000
pages — a runaway crawl will burn through credits fast. Start with a low limit
(10–50) and increase only if needed.

Interact sessions bill per browser minute, so call `firecrawl_interact_stop` as
soon as you are finished. They would expire on their own, but not for free.

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

Set `onlyMainContent: true` to strip nav, footer, and sidebar boilerplate. This
reduces token count and improves downstream processing.

**Available formats:** `markdown`, `html`, `rawHtml`, `screenshot`, `links`,
`summary`, `changeTracking`, `branding`, `json`, `query`, `audio`.

Request only the formats you need. Multiple formats in one call are fine — the
page is fetched once.

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

Without `scrapeOptions`, search returns metadata only (URL, title, description,
position). Add `scrapeOptions` to get full page content from each result in one
operation — but note this multiplies credit cost.

**Time-based filtering** with `tbs`: `qdr:d` (past day), `qdr:w` (past week),
`qdr:m` (past month). Essential for finding recent content.

**Source types** via `sources`, as objects with a `type` field:
`[{"type": "web"}]` (default), `[{"type": "news"}]`, `[{"type": "images"}]`, or
combinations such as `[{"type": "web"}, {"type": "news"}]`. The `limit` applies
per source type.

**Category filtering** via `categories`: `["github"]`, `["research"]`,
`["pdf"]`, `["developer"]`. Narrows results to specific domains (GitHub repos,
academic sites, PDF documents, and a developer index respectively).

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

Map returns an array of URLs (with optional title/description). It does **not**
return page content. Use it as a reconnaissance step before selective scraping.

The `search` parameter orders returned URLs by relevance to a term — useful
when you only need the authentication docs from a large site, for instance.

Map includes subdomains and collapses query-parameter variants by default:
`includeSubdomains` and `ignoreQueryParameters` both default to `true`. Set
either to `false` when you need the wider or more granular URL set.

### Pattern 4: Crawl an entire site

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

`firecrawl_crawl` starts the job and then polls it server-side until it reaches
a terminal state, returning the **final status and the collected data** in the
same response. Do not poll it yourself, and do not follow a normal crawl with
`firecrawl_check_crawl_status`. Reserve that tool for a job that outlived the
MCP call (a client timeout) or for a job started outside MCP — see
`references/crawl-options.md`.

By default, crawl stays within the URL's path hierarchy. Set
`allowExternalLinks: true` to follow links to other domains (use with caution —
credit implications). Set `allowSubdomains: true` to include subdomains like
`blog.example.com` when crawling `example.com`.

All scrape options (formats, `onlyMainContent`, actions, location, tags) can be
passed via `scrapeOptions` and apply to every page the crawler visits.

→ For full crawl options, read `references/crawl-options.md`.

### Pattern 5: Extract structured data from a known URL

Use `firecrawl_scrape` with `formats: ["json"]` and a top-level `jsonOptions`
object holding the `prompt` and `schema`:

```json
{
  "name": "firecrawl_scrape",
  "arguments": {
    "url": "https://example.com/product/widget",
    "formats": ["json"],
    "jsonOptions": {
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
}
```

The `schema` follows JSON Schema format. If omitted, the LLM chooses its own
structure guided by `prompt`; supplying a schema is strongly recommended for
consistent, parseable output. Add `"markdown"` to `formats` to receive readable
page content alongside the extracted fields in the same call.

One URL per call — make a separate `firecrawl_scrape` call for each known URL.
For a bulk single operation, use the Firecrawl batch endpoint outside MCP.

→ For schema design and the `firecrawl_agent` alternative, read
`references/extract-agent-options.md`.

### Pattern 6: Autonomous research agent

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

The agent is async from the client's point of view — it returns a job ID, and
you poll `firecrawl_agent_status` every 15–30 seconds. Allow at least 2–3
minutes before treating it as failed. The agent autonomously searches,
navigates, and extracts.

Provide `urls` to focus the agent on specific pages. Omit `urls` to let it
search freely. The `prompt` is limited to 10,000 characters.

Best for: complex cross-site research where you don't know the exact URLs in
advance, or where content is spread across many pages.

### Pattern 7: Interact with a live page

For interactive web tasks (form filling, authentication, multi-step
navigation), use `firecrawl_interact`. Each call runs **one turn** — a
natural-language `prompt` or an executable `code` snippet — and returns control.

```json
{
  "name": "firecrawl_interact",
  "arguments": {
    "url": "https://example.com/login",
    "prompt": "Fill in the demo credentials and sign in"
  }
}
```

**Lifecycle:**

1. `firecrawl_interact` with `url` — scrapes the page, opens a session, and
   returns a `scrapeId` alongside the interaction result.
2. `firecrawl_interact` with that `scrapeId` — continues on the same live page,
   so state (cookies, filled fields, navigation) persists.
3. `firecrawl_interact_stop` with the `scrapeId` — ends the session and releases
   its resources.

**Always stop sessions when done.** They have TTLs, but leaving them open
wastes credits while they bill per browser minute.

→ For the full parameter set and code-mode examples, read
`references/browser-options.md`.

## Handling asynchronous tools

The two async surfaces behave differently.

**`firecrawl_crawl` — polled for you.** The tool starts the job and polls it
internally until it completes, fails, or the client times out, then returns the
final status and data. There is nothing to poll in the normal case. Reach for
`firecrawl_check_crawl_status` only when:

- the MCP call returned before completion (for example, the client timed out),
  in which case poll with the returned crawl ID; or
- the crawl job was started outside MCP, such as by a direct
  `POST /v2/crawl` REST call.

**`firecrawl_agent` — you poll.** The agent returns a job ID immediately:

1. Call `firecrawl_agent` → receive a job ID.
2. Poll `firecrawl_agent_status` with that ID every 15–30 seconds.
3. On `completed`, the response includes the results.
4. On `failed`, report the error. Consider retrying with adjusted parameters.

Do not poll more frequently than every 15 seconds — it wastes rate-limit budget
and the status endpoints have their own rate limits.

## Error handling

The MCP server handles retries internally with exponential backoff (default: 3
attempts, starting at 1s, doubling each time, capped at 10s). If a call still
fails after retries, you will receive an error response.

Common errors:

- **Rate limit exceeded:** Back off and retry after the indicated delay. Check
  whether you're making unnecessary calls that can be consolidated.
- **Credit limit warnings:** The server emits warnings at configurable
  thresholds. If you see a credit warning, inform the user and stop
  non-essential operations.
- **Timeout:** Increase the `timeout` parameter or simplify the request
  (fewer actions, simpler schema, lower page count).
- **Tool not found:** The connected profile does not expose that tool. Check
  the supported surface above before assuming a transient failure.

## Anti-patterns

- **Calling `firecrawl_extract`:** It is hidden and deprecated, and returns an
  error. Use `firecrawl_scrape` with `formats: ["json"]` for a known URL, or
  `firecrawl_agent` for multi-source research.
- **Scraping then extracting the same page:** Use `firecrawl_scrape` with
  `formats: ["markdown", "json"]` and top-level `jsonOptions` to get both in
  one call.
- **Polling `firecrawl_crawl` yourself:** It already polls internally and
  returns final results. Only use `firecrawl_check_crawl_status` for timed-out
  or externally started jobs.
- **Crawling an entire domain to find one page:** Use `firecrawl_map` with
  the `search` parameter first, then scrape the specific URL.
- **Polling agent status every 2 seconds:** Wastes rate-limit budget. Use 15–30
  second intervals.
- **Omitting `limit` on crawl:** The default is 10,000 pages. Always set an
  explicit limit.
- **Using `firecrawl_agent` for single-page tasks:** The agent is designed
  for multi-source research. For single pages, `firecrawl_scrape` is faster,
  cheaper, and more predictable.
- **Requesting `rawHtml` when `markdown` suffices:** `rawHtml` is large
  and rarely needed for LLM consumption. Use `markdown` by default; `html`
  (cleaned) if you need structure; `rawHtml` only for debugging or when you
  need the exact original markup.
- **Leaving interact sessions open:** Always call `firecrawl_interact_stop`
  when your task is complete. Sessions bill per browser minute until they end.

## Caching

Firecrawl caches scraped pages with a default freshness window of 2 days
(`maxAge: 172800000` ms). Cached responses are significantly faster (up to 5×).
Set `maxAge: 0` to force a fresh scrape — but only when you genuinely need the
absolute latest content. A non-zero `maxAge` is almost always the right choice.

## Reference files

For detailed parameter documentation on each tool, read the appropriate
reference file:

| File                                  | Contents                                                                                        |
| ------------------------------------- | ----------------------------------------------------------------------------------------------- |
| `references/scrape-options.md`        | All `firecrawl_scrape` parameters, formats, `jsonOptions`, actions, and location settings       |
| `references/search-options.md`        | All `firecrawl_search` parameters, source types, categories, and scrape integration             |
| `references/crawl-options.md`         | All `firecrawl_crawl` parameters, path filtering, scope, and status polling                     |
| `references/browser-options.md`       | `firecrawl_interact` session lifecycle, execution languages, agent-browser commands, TTL config |
| `references/extract-agent-options.md` | Structured extraction via `firecrawl_scrape` JSON and `firecrawl_agent` usage patterns          |

Read these files when you need parameter-level detail beyond what this document
covers. For most tasks, the patterns above are sufficient.
