# Interact Options Reference

Complete parameter reference for `firecrawl_interact` and
`firecrawl_interact_stop` — the live browser-interaction surface of the
Firecrawl MCP server.

## When to use interact

Use `firecrawl_interact` instead of scrape with actions when you need:

- **Multi-step workflows** where each step depends on the previous result
- **Authentication flows** that require maintaining cookies/state
- **Page state that persists across tool calls** — a session opened once can be
  reused by `scrapeId`
- **Full Playwright or CDP access** for complex automation
- **Live inspection** of what the browser is doing (via live view URLs)

For a single "click a button then read the page" step, `firecrawl_scrape` with
`actions` is simpler and cheaper.

Each `firecrawl_interact` call runs **one turn** — a `prompt` or a `code`
snippet — to completion and returns control. You cannot drive the browser
step-by-step from inside a single call; use repeated calls against the same
`scrapeId` instead.

## `firecrawl_interact` parameters

| Parameter       | Type   | Default | Description                                                                                            |
| --------------- | ------ | ------- | ------------------------------------------------------------------------------------------------------ |
| `url`           | string | —       | Page to scrape and open for interaction. Mutually exclusive with `scrapeId`                            |
| `scrapeId`      | string | —       | Continue on a page already opened by a previous scrape or interact call. Mutually exclusive with `url` |
| `prompt`        | string | —       | Natural-language task for the built-in agent. Max 10,000 characters. Mutually exclusive with `code`    |
| `code`          | string | —       | Code to execute in the session. Max 100,000 characters. Mutually exclusive with `prompt`               |
| `language`      | string | `node`  | `"node"`, `"python"`, or `"bash"`. Ignored unless `code` is used                                       |
| `timeout`       | number | `30`    | Seconds allowed for this turn. Range 1–300                                                             |
| `scrapeOptions` | object | —       | Scrape options used when opening from `url`; valid **only** with `url`, never with `scrapeId`          |

Exactly one of `url` or `scrapeId` is required, and exactly one of `prompt` or
`code`. The server rejects any other combination.

`language` defaults to `node`, not `bash`. An omitted `language` therefore runs
your snippet under Node.js with a connected Playwright `page` — pass
`"language": "bash"` explicitly for agent-browser commands and `"python"` for
Playwright's async Python API, or the snippet will be executed by the wrong
interpreter.

### Opening a page

```json
{
  "name": "firecrawl_interact",
  "arguments": {
    "url": "https://example.com",
    "prompt": "Click the pricing link and summarize the visible plans"
  }
}
```

In `url` mode the server scrapes the page, opens the session, and returns the
derived `scrapeId` alongside the interaction result. Keep that ID for follow-up
calls and for `firecrawl_interact_stop`.

### Continuing a page

```json
{
  "name": "firecrawl_interact",
  "arguments": {
    "scrapeId": "scrape-id-here",
    "code": "await page.click('#next-page');\nJSON.stringify({ title: await page.title() });",
    "timeout": 60
  }
}
```

Pass the `scrapeId` from `firecrawl_scrape`'s `metadata.scrapeId` to continue a
page you already scraped under tighter scraper control, or the `scrapeId`
returned by a previous `firecrawl_interact`. The live browser is reused, so
cookies, filled fields, and navigation carry over between calls.

### Response

| Field                    | Description                                                              |
| ------------------------ | ------------------------------------------------------------------------ |
| `output`                 | The agent's answer. Present only in `prompt` mode                        |
| `result`                 | Last evaluated expression in `code` mode; page snapshot in `prompt` mode |
| `stdout` / `stderr`      | Captured process output                                                  |
| `exitCode`               | Exit status of the executed code                                         |
| `killed`                 | Whether the turn was terminated (for example, by `timeout`)              |
| `scrapeId`               | Session handle, returned in `url` mode                                   |
| `cdpUrl`                 | Raw CDP WebSocket endpoint for your own Playwright/Puppeteer client      |
| `liveViewUrl`            | Read-only embeddable stream of the browser                               |
| `interactiveLiveViewUrl` | Stream that also accepts mouse and keyboard control                      |

## `firecrawl_interact_stop`

```json
{
  "name": "firecrawl_interact_stop",
  "arguments": {
    "scrapeId": "scrape-id-here"
  }
}
```

Stops the live session bound to that `scrapeId` and releases its resources. The
call returns a success confirmation. A stopped session cannot be resumed.

Always stop sessions when finished. Sessions auto-expire on a TTL (10 minutes
by default) and on inactivity (5 minutes by default), but they bill at 7
credits/minute in prompt mode and 2 credits/minute code-only, with a minimum of
one browser minute — so relying on expiry costs credits.

## Execution languages

### Node.js (default)

Node is the default interpreter. Playwright is pre-installed and `page` is
already connected, so no setup is needed:

```javascript
await page.goto("https://example.com");
const title = await page.title();
JSON.stringify({ title });
```

### Python

Playwright's async Python API is pre-installed, again with `page` ready:

```python
await page.goto("https://example.com")
title = await page.title()
print(title)

# Fill a form
await page.fill("#email", "user@example.com")
await page.fill("#password", "secret")
await page.click("button[type='submit']")
await page.wait_for_load_state("networkidle")
```

Set `"language": "python"` — the default would otherwise run this as Node.

### Bash with agent-browser commands

The `agent-browser` CLI ships in the sandbox with 40+ commands and provides a
high-level interface ideal for LLM-driven automation. Set `"language": "bash"`
explicitly.

| Command                           | Description                                            |
| --------------------------------- | ------------------------------------------------------ |
| `agent-browser open <url>`        | Navigate to a URL                                      |
| `agent-browser snapshot`          | Get the accessibility tree with clickable element refs |
| `agent-browser click @e5`         | Click an element by ref (from snapshot)                |
| `agent-browser fill @e3 "text"`   | Clear and fill an element by ref                       |
| `agent-browser type @e3 "text"`   | Type into an element by ref                            |
| `agent-browser get text @e1`      | Read an element's text                                 |
| `agent-browser screenshot [path]` | Take a screenshot                                      |
| `agent-browser scroll down`       | Scroll the page down                                   |
| `agent-browser wait 2000`         | Wait for 2 seconds                                     |

The `snapshot` → `click`/`fill` loop is the primary interaction pattern. Take a
snapshot to discover interactive elements (each gets a ref like `@e5`), then
address those elements by ref.

## Choosing an execution language

- **Node (default):** Best when you need complex Playwright scripts or
  JavaScript-specific APIs. The path of least resistance — omit `language`.
- **Bash (agent-browser):** Simplest for LLM-generated commands. Best for
  navigation, form-filling, and extraction tasks. The accessibility tree
  snapshot is particularly useful for understanding page structure. Requires an
  explicit `"language": "bash"`.
- **Python:** Best when you need complex logic, data processing, or interaction
  with Python libraries within the session. Requires an explicit
  `"language": "python"`.

## Prompt mode vs code mode

- **`prompt` mode** hands the task to the built-in agent, which decides how to
  navigate, click, and fill. Keep prompts narrowly scoped — one clear task per
  call — because state carries over between calls in the same session. The
  answer comes back in `output`. `language` is ignored here.
- **`code` mode** executes your snippet directly, which is faster and more
  predictable once you know the page structure. Results come back in `result`,
  `stdout`, `stderr`, and `exitCode`.

## Common workflow: Authenticated scraping

```text
1. Interact (url: https://app.example.com/login, prompt: "sign in with ...")
   → returns scrapeId
2. Interact (scrapeId, prompt: "navigate to the dashboard")
3. Interact (scrapeId, code: "...read the values you need...", language: "node")
4. Interact (scrapeId, code: "agent-browser snapshot", language: "bash")
5. Interact_stop (scrapeId)
```

Each call is a separate tool invocation. State persists across calls within the
same session, and the session ends only when you stop it or it expires.
