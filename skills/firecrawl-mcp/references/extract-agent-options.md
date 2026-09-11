# Structured Extraction and Agent Options Reference

Complete parameter reference for the two supported ways of getting structured
data out of the Firecrawl MCP surface: `firecrawl_scrape` with JSON format for
known URLs, and `firecrawl_agent` for multi-source research.

## Choosing between them

|                        | `firecrawl_scrape` with JSON format | `firecrawl_agent`                            |
| ---------------------- | ----------------------------------- | -------------------------------------------- |
| Input                  | One known URL per call              | A prompt, optionally seeded with URLs        |
| Schema location        | Top-level `jsonOptions.schema`      | Top-level `schema`                           |
| Prompt location        | Top-level `jsonOptions.prompt`      | Top-level `prompt`                           |
| Also returns markdown? | Yes (add `"markdown"` to `formats`) | No                                           |
| Enables web search     | No                                  | Yes (the agent searches on its own)          |
| Cost model             | 1 credit/page + 4 credits for JSON  | Varies by research scope                     |
| Best for               | Uniform fields from known pages     | Unknown URLs, or data spanning several sites |

`firecrawl_extract` is **not** a supported tool. The server retains it only as
a hidden deprecated entry point (`canList: false`) that is absent from
`tools/list` and returns an error directing callers to the two rows above. Do
not call it, and do not treat an old example that uses it as authoritative.

______________________________________________________________________

## Known-URL extraction (`firecrawl_scrape` with JSON)

Structured extraction from a single known URL. Pass `formats: ["json"]` and a
top-level `jsonOptions` object holding the `prompt` and `schema`.

### Parameters

| Parameter            | Type   | Description                                                    |
| -------------------- | ------ | -------------------------------------------------------------- |
| `formats`            | array  | Use `["json"]`, or add other formats to fetch them in one call |
| `jsonOptions.prompt` | string | Natural-language description of what to extract                |
| `jsonOptions.schema` | object | JSON Schema defining the desired output structure              |

`jsonOptions` sits **beside** `formats`, not inside it. Passing the prompt or
schema as an entry of the `formats` array is rejected by the MCP schema.

### Example

```json
{
  "name": "firecrawl_scrape",
  "arguments": {
    "url": "https://store.example.com/product/widget-a",
    "formats": ["markdown", "json"],
    "jsonOptions": {
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
}
```

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
- Use `description` on properties to guide the LLM (e.g.
  `"description": "Monthly price in USD, not annual"`).
- Keep nesting shallow where possible. Deeply nested schemas are harder
  for the LLM to populate accurately.
- Use consistent naming (snake_case recommended for JSON consumption).

### Without schema

Omit `schema` and provide only `prompt`:

```json
{
  "name": "firecrawl_scrape",
  "arguments": {
    "url": "https://example.com/pricing",
    "formats": ["json"],
    "jsonOptions": {
      "prompt": "Extract all pricing tiers with their names and monthly costs"
    }
  }
}
```

The LLM chooses the structure. Useful for exploratory extraction, but the
output shape is unpredictable. Prefer providing a schema for production
workflows.

### Several known URLs

Make one `firecrawl_scrape` call per URL, reusing the same `jsonOptions`. There
is no MCP tool that takes a URL array; for a genuine bulk operation, use the
Firecrawl batch endpoint outside MCP.

```json
{
  "name": "firecrawl_scrape",
  "arguments": {
    "url": "https://store.example.com/product/widget-b",
    "formats": ["json"],
    "jsonOptions": { "prompt": "Extract product details", "schema": { } }
  }
}
```

### REST equivalent

The MCP server translates the payload above into the REST scrape body, where
the same settings are nested **inside** the formats array. This REST form is
documented for callers using the HTTP API directly — it is not what an MCP
client should send:

```json
{
  "url": "https://store.example.com/product/widget-a",
  "formats": [
    {
      "type": "json",
      "prompt": "Extract product details",
      "schema": { "type": "object" }
    }
  ]
}
```

______________________________________________________________________

## Agent (`firecrawl_agent`)

Autonomous web research agent. Give it a natural language prompt and optionally
a schema; it searches, navigates, and extracts across multiple sites
independently.

### Parameters

| Parameter | Type     | Description                                           |
| --------- | -------- | ----------------------------------------------------- |
| `prompt`  | string   | *required* — What to research (max 10,000 characters) |
| `urls`    | string[] | Optional — specific URLs to focus on                  |
| `schema`  | object   | Optional — JSON Schema for structured output          |

Unlike scrape's JSON mode, the agent takes `prompt` and `schema` as top-level
parameters; there is no `jsonOptions` wrapper and no `urls`-free equivalent on
`firecrawl_scrape`.

### When to use the agent

- **Complex, multi-source research:** "Compare pricing across three SaaS
  providers" — the agent can search for each, navigate their pricing pages, and
  extract/compare.
- **Unknown URL landscape:** When you don't know which sites have the
  information you need.
- **JavaScript-heavy SPAs** that fail with regular scrape: the agent has
  its own browser rendering.

### When NOT to use the agent

- **Single known URL:** Use `firecrawl_scrape` with `formats: ["json"]`.
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

The agent will start with these pages but may follow links and search further
if needed.

### Async workflow

The agent is asynchronous — unlike `firecrawl_crawl`, which polls server-side
and returns its own final result, the agent returns only a job ID that you must
poll yourself.

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

If a schema was provided, `result` will be a structured object matching the
schema. Without a schema, `result` is a natural language summary with `sources`
listing the URLs consulted.

### Writing effective agent prompts

- **Be specific about what you want:** "Find the monthly price of the Pro
  tier" is better than "find pricing".
- **Specify the output shape** via schema when you need structured data.
- **Constrain scope** with `urls` when you can — reduces research time
  and improves accuracy.
- **State comparison criteria** explicitly: "Compare by price, storage
  limits, and number of team members allowed".
