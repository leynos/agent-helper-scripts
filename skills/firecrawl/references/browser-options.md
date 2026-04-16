# Browser Options Reference

Complete parameter reference for `firecrawl_browser_create`,
`firecrawl_browser_execute`, `firecrawl_browser_delete`, and
`firecrawl_browser_list`.

## When to use the browser sandbox

Use the browser sandbox instead of scrape with actions when you need:
- **Persistent sessions** that survive across multiple tool calls
- **Multi-step workflows** where each step depends on the previous result
- **Authentication flows** that require maintaining cookies/state
- **Full Playwright or CDP access** for complex automation
- **Live inspection** of what the browser is doing (via live view URL)

For simple "click a button then scrape" workflows, `firecrawl_scrape`
with `actions` is simpler and cheaper.

## Session lifecycle

### 1. Create a session

```json
{
  "name": "firecrawl_browser_create",
  "arguments": {
    "ttl": 120,
    "activityTtl": 60
  }
}
```

| Parameter | Type | Range | Description |
|---|---|---|---|
| `ttl` | integer | 30–3600 | Total session lifetime in seconds |
| `activityTtl` | integer | 10–3600 | Idle timeout in seconds (resets on each execute call) |

Both parameters are optional. If omitted, the server applies defaults.

**Response:**
```json
{
  "id": "session-uuid",
  "cdpUrl": "wss://cdp-proxy.firecrawl.dev/cdp/session-uuid",
  "liveViewUrl": "https://liveview.firecrawl.dev/session-uuid",
  "interactiveLiveViewUrl": "https://liveview.firecrawl.dev/session-uuid?interactive=true"
}
```

The `cdpUrl` is a Chrome DevTools Protocol WebSocket endpoint for direct
Playwright/Puppeteer connection. The `liveViewUrl` shows a real-time stream
of the browser. The `interactiveLiveViewUrl` allows direct mouse/keyboard
interaction.

### 2. Execute code

```json
{
  "name": "firecrawl_browser_execute",
  "arguments": {
    "sessionId": "session-uuid",
    "code": "agent-browser open https://example.com",
    "language": "bash"
  }
}
```

| Parameter | Type | Description |
|---|---|---|
| `sessionId` | string | *required* — session ID from create |
| `code` | string | *required* — code to execute |
| `language` | string | `"bash"` (default), `"python"`, or `"node"` |

**Response:**
```json
{
  "result": "...",
  "stdout": "...",
  "stderr": "...",
  "exitCode": 0
}
```

### 3. Delete a session

```json
{
  "name": "firecrawl_browser_delete",
  "arguments": {
    "sessionId": "session-uuid"
  }
}
```

Always delete sessions when finished. Do not rely solely on TTL expiry.

### 4. List sessions

```json
{
  "name": "firecrawl_browser_list",
  "arguments": {
    "status": "active"
  }
}
```

| Parameter | Type | Description |
|---|---|---|
| `status` | string | Optional: `"active"` or `"destroyed"` |

Use this to check for orphaned sessions or verify cleanup.

## Execution languages

### Bash with agent-browser commands

The `agent-browser` CLI is pre-installed in the sandbox with 40+ commands.
It provides a high-level interface ideal for LLM-driven automation.

| Command | Description |
|---|---|
| `agent-browser open <url>` | Navigate to a URL |
| `agent-browser snapshot` | Get the accessibility tree with clickable element refs |
| `agent-browser click @e5` | Click an element by ref (from snapshot) |
| `agent-browser type @e3 "text"` | Type into an element by ref |
| `agent-browser screenshot [path]` | Take a screenshot |
| `agent-browser scroll down` | Scroll the page down |
| `agent-browser scroll up` | Scroll the page up |
| `agent-browser wait 2000` | Wait for 2 seconds |

The `snapshot` → `click`/`type` loop is the primary interaction pattern.
Take a snapshot to discover interactive elements (each gets a ref like
`@e5`), then address those elements by ref.

### Python with Playwright

Playwright is pre-installed. The `page` object is available without setup:

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

### Node.js with Playwright

Same as Python — `page` is pre-configured:

```javascript
await page.goto("https://example.com");
const title = await page.title();
console.log(title);
```

## Choosing an execution language

- **Bash (agent-browser):** Simplest for LLM-generated commands. Best for
  navigation, form-filling, and extraction tasks. The accessibility tree
  snapshot is particularly useful for understanding page structure.
- **Python:** Best when you need complex logic, data processing, or
  interaction with Python libraries within the session.
- **Node.js:** Best when you need complex Playwright scripts or want to
  use JavaScript-specific APIs.

## Common workflow: Authenticated scraping

```
1. Create session (ttl: 300, activityTtl: 120)
2. Execute: agent-browser open https://app.example.com/login
3. Execute: agent-browser snapshot
4. Execute: agent-browser type @e3 "user@example.com"
5. Execute: agent-browser type @e5 "password123"
6. Execute: agent-browser click @e7
7. Execute: agent-browser wait 2000
8. Execute: agent-browser open https://app.example.com/dashboard
9. Execute: agent-browser snapshot  (capture the content you need)
10. Delete session
```

Each execute call is a separate tool invocation. State persists across
calls within the same session.
