# Crawl Options Reference

Complete parameter reference for `firecrawl_crawl` and
`firecrawl_check_crawl_status`.

## Crawl parameters

### Core

| Parameter           | Type    | Default    | Description                                            |
| ------------------- | ------- | ---------- | ------------------------------------------------------ |
| `url`               | string  | *required* | Starting URL for the crawl                             |
| `limit`             | integer | `10000`    | Maximum pages to crawl. **Always set this explicitly** |
| `maxDiscoveryDepth` | integer | —          | Maximum link-following depth from the starting URL     |

### Scope control

| Parameter                | Type    | Default | Description                                                              |
| ------------------------ | ------- | ------- | ------------------------------------------------------------------------ |
| `allowExternalLinks`     | boolean | `false` | Follow links to other domains                                            |
| `allowSubdomains`        | boolean | `false` | Include subdomains (e.g. `blog.example.com` when crawling `example.com`) |
| `crawlEntireDomain`      | boolean | `false` | Crawl all pages on the domain regardless of path hierarchy               |
| `deduplicateSimilarURLs` | boolean | `false` | Skip URLs that differ only trivially (query params, fragments)           |

### Path filtering

`includePaths` and `excludePaths` are arrays of **regular-expression strings**,
not globs. They are matched against the URL pathname, so `^/docs/.*$` matches
the docs section while `/docs/*` matches nothing.

| Parameter      | Type     | Description                                                                                      |
| -------------- | -------- | ------------------------------------------------------------------------------------------------ |
| `includePaths` | string[] | Only crawl URLs whose pathname matches one of these regexes (e.g. `["^/docs/.*$", "^/api/.*$"]`) |
| `excludePaths` | string[] | Skip URLs whose pathname matches one of these regexes (e.g. `["^/admin/.*$", "^/login$"]`)       |

Anchor with `^` and `$` — an unanchored pattern is a substring match. The
starting URL is itself tested against `includePaths`, so an include list that
excludes the start URL returns zero pages.

Use path filtering to focus crawls on relevant sections and conserve credits.

Matching against the full URL including the query string (`regexOnFullURL`) is
available on the REST crawl body but is not exposed by the MCP
`firecrawl_crawl` schema.

### Sitemap

| Parameter | Type   | Default     | Description                                                                                                   |
| --------- | ------ | ----------- | ------------------------------------------------------------------------------------------------------------- |
| `sitemap` | string | `"include"` | Sitemap handling: `"include"` (discover from sitemap + links), `"skip"` (links only), `"only"` (sitemap only) |

Keep `sitemap: "include"` for maximum coverage. Use `"skip"` if the sitemap is
stale or inaccurate. Use `"only"` for a quick pass over known pages without
traversal.

### Scrape options

All `firecrawl_scrape` options are available via `scrapeOptions`. These apply
to **every page** the crawler visits:

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

## Completion: the MCP tool polls for you

Calling `firecrawl_crawl` starts the job **and** polls it server-side until it
reaches a terminal state. The response it returns is the final crawl status and
the collected page data — not a pending job handle.

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

**Do not poll after a normal crawl call.** There is no job to chase: the tool
has already waited the job out. Terminal statuses are `completed`, `failed`, and
`cancelled`.

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

## Checking status: timed-out or externally started jobs

`firecrawl_check_crawl_status` reads an existing crawl by ID. It is the right
tool in exactly two situations:

1. **The MCP call returned before completion.** If the client timed out or the
   transport dropped mid-poll, poll with the crawl ID to collect the result.
2. **The job was started outside MCP** — for example, by a direct REST call to
   `POST /v2/crawl`.

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
- `cancelled` — the job was stopped before finishing

### REST job creation (not an MCP workflow)

Everything below is the plain HTTP API, documented so the two paths are not
confused. MCP clients never need it.

A REST `POST /v2/crawl` returns a job handle immediately and does no polling:

```json
{
  "success": true,
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "url": "https://api.firecrawl.dev/v2/crawl/550e8400-..."
}
```

That ID must then be polled — via `firecrawl_check_crawl_status` if you are
back in MCP, or `GET /v2/crawl/{id}` if you are not. The MCP `firecrawl_crawl`
tool wraps exactly this create-then-poll sequence, which is why the polling
step disappears when you call it.

## Map parameters

`firecrawl_map` is the lightweight counterpart to crawl. It discovers URLs
without scraping them.

| Parameter               | Type    | Default     | Description                                       |
| ----------------------- | ------- | ----------- | ------------------------------------------------- |
| `url`                   | string  | *required*  | Base URL to map                                   |
| `search`                | string  | —           | Order URLs by relevance to this search term       |
| `sitemap`               | string  | `"include"` | Same as crawl: `"include"`, `"skip"`, or `"only"` |
| `includeSubdomains`     | boolean | `true`      | Include subdomain URLs                            |
| `limit`                 | integer | —           | Maximum URLs to return                            |
| `ignoreQueryParameters` | boolean | `true`      | Drop URLs differing only by query string          |

Both boolean defaults are `true`: a bare `firecrawl_map` call already spans
subdomains and collapses query-parameter duplicates. Pass `false` explicitly to
narrow the subdomain scope or to keep per-query-string URLs.

Map costs **1 credit per call** regardless of how many URLs it returns, making
it very efficient for reconnaissance.

### Map-then-scrape workflow

1. Map the site with a search term to find relevant URLs
2. Review the URL list and filter to the pages you need
3. Scrape each selected URL individually

This is more credit-efficient than a full crawl when you only need a small
subset of a large site's pages.

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
