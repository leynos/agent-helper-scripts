# Crawl Options Reference

Complete parameter reference for `firecrawl_crawl` and
`firecrawl_check_crawl_status`.

## Crawl parameters

### Core

| Parameter | Type | Default | Description |
|---|---|---|---|
| `url` | string | *required* | Starting URL for the crawl |
| `limit` | integer | `10000` | Maximum pages to crawl. **Always set this explicitly** |
| `maxDiscoveryDepth` | integer | — | Maximum link-following depth from the starting URL |

### Scope control

| Parameter | Type | Default | Description |
|---|---|---|---|
| `allowExternalLinks` | boolean | `false` | Follow links to other domains |
| `allowSubdomains` | boolean | `false` | Include subdomains (e.g. `blog.example.com` when crawling `example.com`) |
| `crawlEntireDomain` | boolean | `false` | Crawl all pages on the domain regardless of path hierarchy |
| `deduplicateSimilarURLs` | boolean | `false` | Skip URLs that differ only trivially (query params, fragments) |

### Path filtering

| Parameter | Type | Description |
|---|---|---|
| `includePaths` | string[] | Only crawl URLs matching these glob patterns (e.g. `["/docs/*", "/api/*"]`) |
| `excludePaths` | string[] | Skip URLs matching these glob patterns (e.g. `["/admin/*", "/login"]`) |

Use path filtering to focus crawls on relevant sections and conserve credits.

### Sitemap

| Parameter | Type | Default | Description |
|---|---|---|---|
| `sitemap` | string | `"include"` | Sitemap handling: `"include"` (discover from sitemap + links), `"skip"` (links only), `"only"` (sitemap only) |

Keep `sitemap: "include"` for maximum coverage. Use `"skip"` if the
sitemap is stale or inaccurate. Use `"only"` for a quick pass over known
pages without traversal.

### Scrape options

All `firecrawl_scrape` options are available via `scrapeOptions`. These
apply to **every page** the crawler visits:

```json
{
  "url": "https://docs.example.com",
  "limit": 50,
  "scrapeOptions": {
    "formats": ["markdown"],
    "onlyMainContent": true,
    "includeTags": ["article"],
    "location": { "country": "GB" }
  }
}
```

## Async workflow

Crawl is asynchronous. The call returns immediately with a job ID.

### Starting a crawl

```json
{
  "name": "firecrawl_crawl",
  "arguments": {
    "url": "https://docs.example.com",
    "limit": 50,
    "maxDiscoveryDepth": 3,
    "deduplicateSimilarURLs": true
  }
}
```

Response:
```json
{
  "success": true,
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "url": "https://api.firecrawl.dev/v2/crawl/550e8400-..."
}
```

### Polling status

```json
{
  "name": "firecrawl_check_crawl_status",
  "arguments": {
    "id": "550e8400-e29b-41d4-a716-446655440000"
  }
}
```

**Poll every 15–30 seconds.** The status field will be one of:
- `scraping` — still in progress; the response includes `total` and
  `completed` counts for progress estimation
- `completed` — results available in the `data` array
- `failed` — an error occurred

### Completed response

```json
{
  "status": "completed",
  "total": 36,
  "completed": 36,
  "creditsUsed": 36,
  "data": [
    {
      "markdown": "...",
      "metadata": { "title": "...", "sourceURL": "..." }
    }
  ]
}
```

If the result set is large, the response may include a `next` URL for
pagination.

## Map parameters

`firecrawl_map` is the lightweight counterpart to crawl. It discovers
URLs without scraping them.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `url` | string | *required* | Base URL to map |
| `search` | string | — | Filter URLs by relevance to this search term |
| `sitemap` | string | `"include"` | Same as crawl: `"include"`, `"skip"`, or `"only"` |
| `includeSubdomains` | boolean | `false` | Include subdomain URLs |
| `limit` | integer | — | Maximum URLs to return |
| `ignoreQueryParameters` | boolean | `false` | Deduplicate URLs differing only by query string |

Map costs **1 credit per call** regardless of how many URLs it returns,
making it very efficient for reconnaissance.

### Map-then-scrape workflow

1. Map the site with a search term to find relevant URLs
2. Review the URL list and filter to the pages you need
3. Scrape each selected URL individually

This is more credit-efficient than a full crawl when you only need a
small subset of a large site's pages.

```json
// Step 1: Map
{
  "name": "firecrawl_map",
  "arguments": {
    "url": "https://docs.example.com",
    "search": "authentication",
    "limit": 50
  }
}

// Step 2: Scrape selected URLs from the map results
{
  "name": "firecrawl_scrape",
  "arguments": {
    "url": "https://docs.example.com/auth/oauth2",
    "formats": ["markdown"],
    "onlyMainContent": true
  }
}
```
