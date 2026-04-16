# Extract and Agent Options Reference

Complete parameter reference for `firecrawl_extract`, `firecrawl_agent`,
and `firecrawl_agent_status`.

## Extract (`firecrawl_extract`)

Server-side LLM extraction of structured data from one or more URLs.

### Parameters

| Parameter | Type | Description |
|---|---|---|
| `urls` | string[] | *required* — URLs to extract from |
| `prompt` | string | Natural language description of what to extract |
| `schema` | object | JSON Schema defining the desired output structure |
| `allowExternalLinks` | boolean | Allow the extractor to follow links to other domains |
| `enableWebSearch` | boolean | Allow the extractor to search the web for context |
| `includeSubdomains` | boolean | Include subdomains when extracting |

### Schema design

Provide a JSON Schema object. Use standard JSON Schema properties:

```json
{
  "type": "object",
  "properties": {
    "company_name": { "type": "string" },
    "founded_year": { "type": "integer" },
    "pricing_tiers": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "name": { "type": "string" },
          "price_monthly": { "type": "number" },
          "features": { "type": "array", "items": { "type": "string" } }
        },
        "required": ["name", "price_monthly"]
      }
    }
  },
  "required": ["company_name"]
}
```

**Tips for robust schemas:**
- Mark fields `required` only when they should genuinely always be present.
  Optional fields gracefully handle pages where that data doesn't exist.
- Use `description` on properties to guide the LLM (e.g. `"description":
  "Monthly price in USD, not annual"`).
- Keep nesting shallow where possible. Deeply nested schemas are harder
  for the LLM to populate accurately.
- Use consistent naming (snake_case recommended for JSON consumption).

### Without schema

Omit `schema` and provide only `prompt`:

```json
{
  "urls": ["https://example.com/pricing"],
  "prompt": "Extract all pricing tiers with their names and monthly costs"
}
```

The LLM chooses the structure. Useful for exploratory extraction, but the
output shape is unpredictable. Prefer providing a schema for production
workflows.

### Extract vs scrape with JSON format

| | `firecrawl_extract` | `firecrawl_scrape` with JSON format |
|---|---|---|
| Input | Multiple URLs | Single URL |
| Also returns markdown? | No | Yes (if both formats requested) |
| Schema location | Top-level `schema` param | Inside formats array |
| Enables web search | Yes (`enableWebSearch`) | No |
| Best for | Uniform data across many pages | Single-page extraction alongside other formats |

### Example: Extract from multiple product pages

```json
{
  "name": "firecrawl_extract",
  "arguments": {
    "urls": [
      "https://store.example.com/product/widget-a",
      "https://store.example.com/product/widget-b",
      "https://store.example.com/product/widget-c"
    ],
    "prompt": "Extract product details",
    "schema": {
      "type": "object",
      "properties": {
        "name": { "type": "string" },
        "price": { "type": "number", "description": "Price in USD" },
        "in_stock": { "type": "boolean" },
        "description": { "type": "string" }
      },
      "required": ["name", "price"]
    }
  }
}
```

---

## Agent (`firecrawl_agent`)

Autonomous web research agent. Give it a natural language prompt and
optionally a schema; it searches, navigates, and extracts across multiple
sites independently.

### Parameters

| Parameter | Type | Description |
|---|---|---|
| `prompt` | string | *required* — What to research (max 10,000 characters) |
| `urls` | string[] | Optional — specific URLs to focus on |
| `schema` | object | Optional — JSON Schema for structured output |

### When to use the agent

- **Complex, multi-source research:** "Compare pricing across three SaaS
  providers" — the agent can search for each, navigate their pricing
  pages, and extract/compare.
- **Unknown URL landscape:** When you don't know which sites have the
  information you need.
- **JavaScript-heavy SPAs** that fail with regular scrape: the agent has
  its own browser rendering.

### When NOT to use the agent

- **Single known URL:** Use `firecrawl_scrape` or `firecrawl_extract`.
- **Simple searches:** Use `firecrawl_search` with `scrapeOptions`.
- **Predictable, structured sites:** Map-then-scrape or crawl is faster
  and cheaper.

### Providing focus URLs

When you know some (but not all) relevant URLs, provide them via `urls`:

```json
{
  "name": "firecrawl_agent",
  "arguments": {
    "urls": [
      "https://docs.provider-a.com/pricing",
      "https://provider-b.io/plans"
    ],
    "prompt": "Compare the free tier limits of these two providers"
  }
}
```

The agent will start with these pages but may follow links and search
further if needed.

### Async workflow

The agent is asynchronous — exactly like crawl.

1. Call `firecrawl_agent` → receive a job ID
2. Poll `firecrawl_agent_status` with the ID
3. Poll every 15–30 seconds
4. Allow at least 2–3 minutes before treating as failed

### Status polling

```json
{
  "name": "firecrawl_agent_status",
  "arguments": {
    "id": "job-uuid-here"
  }
}
```

Statuses:
- `processing` — still researching; keep polling
- `completed` — results available in the response
- `failed` — an error occurred

### Completed response

```json
{
  "status": "completed",
  "data": {
    "result": "The comparison shows...",
    "sources": [
      "https://docs.provider-a.com/pricing",
      "https://provider-b.io/plans"
    ]
  }
}
```

If a schema was provided, `result` will be a structured object matching
the schema. Without a schema, `result` is a natural language summary
with `sources` listing the URLs consulted.

### Writing effective agent prompts

- **Be specific about what you want:** "Find the monthly price of the Pro
  tier" is better than "find pricing".
- **Specify the output shape** via schema when you need structured data.
- **Constrain scope** with `urls` when you can — reduces research time
  and improves accuracy.
- **State comparison criteria** explicitly: "Compare by price, storage
  limits, and number of team members allowed".
