# Search Options Reference

Complete parameter reference for `firecrawl_search`.

## Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `query` | string | *required* | The search query |
| `limit` | integer | — | Maximum results to return. Applies **per source type** when using multiple sources |
| `location` | string | — | Geographic location for results (e.g. `"United States"`, `"United Kingdom"`) |
| `tbs` | string | — | Time-based filter (see below) |
| `filter` | string | — | Additional search filter |
| `sources` | string[] | `["web"]` | Source types to search (see below) |
| `categories` | string[] | — | Category filters (see below) |
| `scrapeOptions` | object | — | Options for scraping each result page (see below) |
| `enterprise` | string[] | — | Enterprise options: `"default"`, `"anon"`, `"zdr"` |

## Time-based filtering (`tbs`)

| Value | Meaning |
|---|---|
| `qdr:h` | Past hour |
| `qdr:d` | Past day |
| `qdr:w` | Past week |
| `qdr:m` | Past month |
| `qdr:y` | Past year |

Use time filters when freshness matters. For news, CVEs, or recent events,
`qdr:d` or `qdr:w` are often appropriate.

## Source types (`sources`)

| Source | Returns |
|---|---|
| `web` | Standard web search results (URL, title, description, position) |
| `news` | News-focused results (URL, title, snippet, date, position) |
| `images` | Image results (imageUrl, dimensions, source URL, position) |

Combine sources in a single call: `sources: ["web", "news"]`. When using
multiple sources, `limit` applies independently to each — so `limit: 5`
with two sources returns up to 10 results total.

If you need different `limit` values or different `scrapeOptions` per
source type, make separate calls.

## Category filters (`categories`)

| Category | Scoped to |
|---|---|
| `github` | GitHub repositories, code, issues, documentation |
| `research` | Academic sites: arXiv, Nature, IEEE, PubMed, etc. |
| `pdf` | PDF documents across the web |

Categories can be combined: `categories: ["github", "research"]`.

## Scrape integration (`scrapeOptions`)

By default, search returns metadata only (no page content). To also
retrieve full page content from each result, add `scrapeOptions`:

```json
{
  "query": "Rust error handling patterns",
  "limit": 3,
  "scrapeOptions": {
    "formats": ["markdown"],
    "onlyMainContent": true
  }
}
```

This performs a scrape on each result URL. Every scrape option from
`firecrawl_scrape` is available here (formats, tags, waitFor, actions,
location, etc.).

**Credit impact:** Each scraped result costs additional credits. A search
with `limit: 5` and `scrapeOptions` costs 1 base + 5 scrape credits
minimum (more with JSON mode or enhanced proxy).

### When to use scrapeOptions vs separate scrape calls

Use `scrapeOptions` in the search call when:
- You want content from all/most results
- You need the same scrape configuration for every result

Use separate `firecrawl_scrape` calls when:
- You only want to scrape specific results (based on title/description)
- Different results need different scrape parameters

## Response structure

### Without scrapeOptions

```json
{
  "data": {
    "web": [
      {
        "url": "https://example.com",
        "title": "Page Title",
        "description": "Page description snippet",
        "position": 1
      }
    ],
    "images": [ ... ],
    "news": [ ... ]
  }
}
```

### With scrapeOptions

Each web result additionally includes the scraped content in the requested
formats (e.g. `markdown`, `html`).

## Usage patterns

### Find recent articles on a topic

```json
{
  "query": "WebTransport browser support",
  "limit": 5,
  "tbs": "qdr:m",
  "scrapeOptions": { "formats": ["markdown"], "onlyMainContent": true }
}
```

### Search GitHub for repositories

```json
{
  "query": "protobuf TypeScript runtime",
  "limit": 5,
  "categories": ["github"]
}
```

### Search for academic papers

```json
{
  "query": "formal verification of concurrent Rust programs",
  "limit": 5,
  "categories": ["research"],
  "scrapeOptions": { "formats": ["markdown"] }
}
```

### Search with geographic context

```json
{
  "query": "best coffee roasters Edinburgh",
  "limit": 5,
  "location": "United Kingdom"
}
```
