---
name: vidai-mock
description: >-
  Use VidaiMock as a local, offline, wire-accurate mock server for developing
  and testing software that targets OpenAI-, Anthropic-, Gemini-, Bedrock-, and
  compatible chat APIs. Covers startup and run modes, provider and Tera
  template configuration, streaming physics, tool-call and agentic-loop
  simulation, chaos and error injection, and observability-driven validation.
---

# VidaiMock Skill

Target version: `vidaimock` 0.3.1. Every command and response shape below was
checked against that release.

VidaiMock serves provider-accurate HTTP APIs from one local process. It needs
no API key, no network access, and no fixtures: bundled providers and Tera
templates are embedded in the binary, so every endpoint works the moment it
starts.

## When To Use This Skill

Use this skill when you need a local, offline mock server that behaves like
real LLM providers and supports:

- API-compatible chat, responses, embeddings, images, and moderations testing.
- Streaming behaviour: time-to-first-token, token pacing, jitter, and
  provider-native SSE framing.
- Tool/function call payload simulation and agentic loop termination.
- Deterministic fault injection for retry, timeout, and parser hardening tests.
- RAG citation and structured-output test scenarios.
- Agent framework runs (Google ADK, LangGraph, LangChain) in CI with zero
  live-provider spend.

## Level 1: Critical Path (Start Here)

Follow this path before adding advanced behaviour.

1. Confirm the binary is available.

   ```bash
   command -v vidaimock
   vidaimock --version
   ```

2. Start the server. The default bind address is `0.0.0.0`, so bind loopback
   for local work. The default port is 8100.

   ```bash
   vidaimock --host 127.0.0.1
   ```

3. Verify liveness before wiring a client to it.

   ```bash
   curl -sS http://localhost:8100/health
   # {"status":"ok"}
   ```

4. Point the SDK at the local base URL. Any non-empty API key is accepted.

   ```python
   # OpenAI-style client
   from openai import OpenAI

   client = OpenAI(base_url="http://localhost:8100/v1", api_key="sk-local-test")
   ```

   ```python
   # Anthropic-style client
   from anthropic import Anthropic

   client = Anthropic(base_url="http://localhost:8100/v1", api_key="sk-local-test")
   ```

5. Send a baseline request before adding chaos or streaming overrides.

   ```bash
   curl -sS http://localhost:8100/v1/chat/completions \
     -H "Content-Type: application/json" \
     -d '{
       "model": "gpt-4",
       "messages": [{"role": "user", "content": "hello"}]
     }'
   ```

6. Confirm streaming works before asserting on chunk assembly. Use `curl -N`;
   a buffering client hides incremental delivery.

   ```bash
   curl -N -sS http://localhost:8100/v1/chat/completions \
     -H "Content-Type: application/json" \
     -d '{
       "model": "gpt-4",
       "stream": true,
       "messages": [{"role": "user", "content": "count to five"}]
     }'
   ```

## Level 2: Daily Development Workflow

### Run Modes

`--mode` selects the timing profile:

| Mode                  | Behaviour                                                                              |
| --------------------- | -------------------------------------------------------------------------------------- |
| `benchmark` (default) | Emits chunks as fast as possible. Best for throughput tests.                           |
| `realistic`           | Adds TTFT (`--latency`) before the first token, then paces tokens. Streaming-UX tests. |
| `debug`               | Verbose logging for template and stream diagnosis.                                     |

```bash
vidaimock --mode realistic --latency 300
```

Latency settings only shape delivery in `realistic` mode. A `--latency` value
passed in `benchmark` mode still delays the response, but there is no
token-by-token pacing to observe.

### Configuration Precedence

Highest priority first:

1. CLI flags (`--port 3000`).
2. Environment variables (`VIDAIMOCK_PORT=3000`).
3. `mock-server.toml`.
4. Embedded defaults.

Global runtime settings live in `mock-server.toml`:

```toml
host = "0.0.0.0"
port = 8100
log_level = "info"

[latency]
mode = "realistic"   # token-by-token pacing
base_ms = 150        # TTFT before the first token
jitter_pct = 0.2     # ±20% timing variance

[chaos]
enabled = false
drop_pct = 0.01        # 1% of requests fail with a provider-shaped 500
malformed_pct = 0.005  # 0.5% return deliberately broken JSON
trickle_ms = 0         # per-chunk delay during streaming
disconnect_pct = 0.05  # 5% of streams sever mid-generation
```

Check what the process actually resolved with `GET /status`; secrets are
redacted.

### Workspace Layout

Keep simulation assets close to the app under test. Provider YAML and
templates usually live in a directory passed with `--config-dir`.

```text
.
|- mock-server.toml
`- config/
   |- providers/
   |  |- openai.yaml
   |  `- custom-provider.yaml
   `- templates/
      `- custom/
```

### Provider Routing Model

A provider is a YAML file under `config/providers/`. It maps a request path to
a template and controls status, errors, and streaming.

```yaml
name: "my-provider"                  # unique identifier
matcher: "^/v1/my/endpoint$"         # regex matched against the request path
priority: 10                         # higher wins when several matchers hit
request_mapping:                     # optional: extract context values with Tera
  prompt: "{{ json.messages | last | get(key='content') }}"
response_template: "my/template.j2"  # Tera template for 2xx responses
response_body: |                     # or an inline template instead of a file
  {"ok": true}
error_template: "my/error.j2"        # Tera template for 4xx/5xx responses
status_code: "200"                   # static, or a Tera expression

stream:
  enabled: true
  frame_format: raw                  # "raw" hands SSE framing to the templates
  lifecycle:
    on_start: { template_path: "my/stream_start.j2" }
    on_chunk: { template_path: "my/stream_delta.j2" }
    on_stop:  { template_path: "my/stream_stop.j2" }
```

- `matcher`: regex tested against the request path. The first provider by
  `priority`, then load order, serves the request.
- `priority`: integer, default `0`. Use it to make a specific provider win over
  a broad catch-all.
- `request_mapping`: maps a context key to a Tera expression. Each expression is
  rendered against the request and the result inserted into the template
  context, so templates can read derived values such as an extracted prompt. A
  value that fails to render is logged and skipped rather than failing the
  request.
- `response_template`: path relative to `config/templates/`, rendered for 2xx.
- `response_body`: an inline Tera template used when no `response_template`
  applies. A provider with neither a usable template nor a body returns 404.
- `error_template`: rendered instead of `response_template` whenever the
  resolved status is 400 or above, so every failure path produces a
  provider-shaped envelope. `status_code` is in scope for the template.
- `status_code`: a static string (`"400"`), a Tera expression
  (`"{{ path_segments | last }}"`), or a Tera statement
  (`"{% if json.max_tokens %}200{% else %}400{% endif %}"`). Chaos overrides
  and headers are resolved first, so an injected status wins over this field.
- `stream`: present and `enabled: true` to stream; `lifecycle` names the
  start/chunk/stop templates, each of which may set `template_path`,
  `template_body`, or `event_name`.

### Overriding Bundled Defaults

Bundled providers and templates are embedded in the binary. `--config-dir`
overrides them, so drop in only the files you want to change.

`--isolated` ignores the embedded set entirely and loads only `--config-dir`,
so a missing or broken custom file fails loudly instead of silently falling
back to a bundled default. The equivalent environment variable is
`VIDAIMOCK_ISOLATED=true`.

```bash
vidaimock --config-dir ./my-config --isolated
```

Use isolated mode for CI rigs, security review, and any surface you want
pinned to exactly what you declare.

### Template Runtime Model

Every response is a Tera template, which is what makes the mock dynamic rather
than a fixture. Templates receive:

| Variable        | Contents                                                             |
| --------------- | -------------------------------------------------------------------- |
| `json`          | The parsed request body: `json.model`, `json.messages`, `json.tools` |
| `headers`       | Request headers, lower-cased keys                                    |
| `query`         | URL query parameters                                                 |
| `path_segments` | Path split on `/`, e.g. `["v1", "chat", "completions"]`              |
| `status_code`   | The resolved HTTP status, available in error templates               |
| `chunk`         | Per-chunk content inside a streaming lifecycle template              |

Helper functions:

| Helper                                | Returns               | Use                                         |
| ------------------------------------- | --------------------- | ------------------------------------------- |
| `uuid()`                              | random UUID string    | `chatcmpl-{{ uuid() }}`, `msg_{{ uuid() }}` |
| `timestamp()`                         | unix seconds, integer | `created` / `created_at` fields             |
| `iso_timestamp()`                     | ISO-8601 string       | human-readable timestamps                   |
| `random_int(min, max)`                | integer               | mock token counts, call IDs                 |
| `random_float(min, max)`              | float                 | embedding values, scores                    |
| `has_tool_result(messages, provider)` | boolean               | agentic loop termination                    |

Tera is unreliable at indexing into arrays of mixed-type objects. For
history-spanning logic such as detecting a tool result, call
`has_tool_result()` rather than hand-rolling `json.messages | …` array walks.

### Built-in Paths

| Path                 | Purpose                                   |
| -------------------- | ----------------------------------------- |
| `GET /health`        | Liveness: `{"status":"ok"}`               |
| `GET /status`        | Effective configuration, secrets redacted |
| `GET /metrics`       | Prometheus metrics                        |
| `POST /error/{code}` | Provider-agnostic error simulator         |

## Level 3: Scenario Playbooks

### Streaming Physics

Streaming requests (`"stream": true`) are delivered with provider-native
framing, not a chunked static download. Design templates around lifecycle
phases, and assert on framing as well as content:

- OpenAI chat: blank-line-separated `data:` chunks, ending with a
  finish-reason chunk, an optional usage chunk, then `data: [DONE]`.
- OpenAI Responses API: typed events, e.g. `event: response.created`,
  `event: response.output_text.delta`, `event: response.completed`.
- Anthropic: the seven-event lifecycle `message_start`,
  `content_block_start`, `ping`, `content_block_delta` (repeated),
  `content_block_stop`, `message_delta`, `message_stop`.
- Gemini: no `[DONE]` sentinel. The stream simply ends; intermediate frames
  carry `finishReason: null` and no `usageMetadata`, while the terminal frame
  carries `finishReason: STOP` and `usageMetadata`.

Request a usage chunk on OpenAI with `"stream_options": {"include_usage":
true}`; it arrives as a chunk with an empty `choices` array before `[DONE]`.

Per-request timing overrides: `X-Vidai-Latency` (TTFT) and
`X-Vidai-Chaos-Trickle` (per-chunk delay). `X-Vidai-Chaos-Disconnect` severs a
stream mid-generation. A chaos-triggered error on a streaming request returns
a non-streaming HTTP error with a JSON body, matching what real providers do
when their upstream fails.

### Tool And Function Calling

The mock reads the caller's declared tools and echoes the requested name.

1. Turn one: declare `tools` and send the user message. The response carries
   `finish_reason: "tool_calls"` (OpenAI) with a populated `tool_calls` array.
2. Turn two: send the same tools plus the tool result in history. The mock
   detects the result and replies with plain text and `finish_reason: "stop"`
   instead of looping.

```bash
# Turn 2: the tool result is already in history, so the loop terminates
curl -sS http://localhost:8100/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4o",
    "tools": [{"type": "function", "function": {"name": "get_weather", "parameters": {}}}],
    "messages": [
      {"role": "user", "content": "Weather in London?"},
      {"role": "assistant", "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "get_weather", "arguments": "{}"}}]},
      {"role": "tool", "tool_call_id": "c1", "content": "15C cloudy"}
    ]
  }'
# -> finish_reason: "stop", message.content: "Based on the tool results, ..."
```

The detection signal differs per provider: an OpenAI message with
`role: "tool"`, an Anthropic user message whose `content[]` holds a
`tool_result` block, or Gemini content whose `parts[]` holds a
`functionResponse`. `has_tool_result()` implements all three and returns
`false` rather than raising on malformed input, so it is safe inside any
`{% if %}` guard.

This is what lets an ADK, LangGraph, or LangChain agent loop run to completion
against the mock. Keep at least one golden-path and one malformed-path test:
this is where most parser and integration regressions appear.

### JSON/Structured Output

Send `response_format` and the response content is valid JSON on success
paths. Return intentionally invalid JSON on negative paths to exercise both
your strict parser and your fallback handling.

### Chaos Injection For Resilience

Every injected failure returns a provider-shaped error envelope, so SDK error
parsers and retry/fallback logic engage as they would against the real API.
All four triggers funnel through the provider's `error_template`.

| Trigger                           | Scope             | Use case                                           |
| --------------------------------- | ----------------- | -------------------------------------------------- |
| `?chaos_status=503` URL query     | Per URL           | Primary/fallback routing and circuit-breaker tests |
| `X-Mock-Status: 429` header       | Per request       | Force a status on a real provider route            |
| `X-Vidai-Chaos-Drop: 100` header  | Probabilistic     | Chaos testing: N% of requests return a 500         |
| Provider `status_code` expression | Per request field | Request validation rules                           |

```bash
# Force a 500 response
curl -H "X-Vidai-Chaos-Drop: 100" http://localhost:8100/v1/chat/completions \
  -H "Content-Type: application/json" -d '{"model":"gpt-4","messages":[{"role":"user","content":"Hi"}]}'

# Force a specific status with a provider-shaped body
curl -H "X-Mock-Status: 429" http://localhost:8100/v1/chat/completions \
  -H "Content-Type: application/json" -d '{"model":"gpt-4","messages":[{"role":"user","content":"Hi"}]}'

# Force malformed (non-JSON) content
curl -H "X-Vidai-Chaos-Malformed: 100" http://localhost:8100/v1/chat/completions \
  -H "Content-Type: application/json" -d '{"model":"gpt-4","messages":[{"role":"user","content":"Hi"}]}'

# Add 2s TTFT and jitter
curl -H "X-Vidai-Latency: 2000" -H "X-Vidai-Jitter: 0.2" http://localhost:8100/v1/chat/completions \
  -H "Content-Type: application/json" -d '{"model":"gpt-4","messages":[{"role":"user","content":"Hi"}]}'

# Slow chunk cadence while streaming
curl -N -H "X-Vidai-Chaos-Trickle: 1000" http://localhost:8100/v1/chat/completions \
  -H "Content-Type: application/json" -d '{"model":"gpt-4","stream":true,"messages":[{"role":"user","content":"Hi"}]}'

# Provider-agnostic failing endpoint
curl http://localhost:8100/error/429 -H "Content-Type: application/json" -d '{}'
```

The error envelope is provider-shaped: OpenAI returns
`{"error": {"message", "type", "param", "code"}}`, Anthropic returns
`{"type": "error", "error": {"type", "message"}}`, and Gemini returns
`{"error": {"code", "message", "status"}}`. The `type`/`status` value is
selected per HTTP code, so a 429 is `rate_limit_exceeded`,
`rate_limit_error`, or `RESOURCE_EXHAUSTED` respectively.

`?chaos_status=` is the one to reach for when testing primary/fallback
routing: it is encoded in the URL, so one mock instance can present a broken
endpoint and a healthy endpoint without the client forwarding headers.

Prefer request-level chaos controls in tests: failures stay explicit and
reproducible. Reserve `[chaos]` in `mock-server.toml` for ambient resilience
runs.

### Request Validation

Bundled providers enforce known-required fields, so the mock can fail the way
the real API fails. Anthropic `/v1/messages` without `max_tokens` returns HTTP
400 with the real envelope:

```bash
curl http://localhost:8100/v1/messages \
  -H 'Content-Type: application/json' \
  -d '{"model":"claude","messages":[{"role":"user","content":"Hi"}]}'
# -> HTTP 400 {"type":"error","error":{"type":"invalid_request_error","message":"max_tokens: Field required"}}
```

### RAG And Citation Validation

Use template variants to test:

- Citation markers in generated text.
- Citation metadata blocks in payloads.
- Retrieval-latency effects before the first token (`X-Vidai-Latency`).
- Hallucinated or non-existent references for guardrail tests.

Create separate endpoints or provider matchers for trusted and adversarial RAG
scenarios so each case stays independently addressable.

## Observability And Diagnostics

### Metrics

```text
GET http://localhost:8100/metrics
```

Track request volume by route and status, and request latency. Metrics are
available whenever the metrics endpoint is enabled.

### Logs

Control verbosity with `RUST_LOG` or `log_level` in `mock-server.toml`.

```bash
RUST_LOG=debug vidaimock
```

Use `debug` during template and protocol work, then reduce to `info` for
routine CI runs. `--mode debug` is the equivalent for template and stream
diagnosis.

## Providers

No configuration is needed for any of these. Every response is rendered from a
bundled Tera template you can override.

| Provider              | Endpoint                                  | Streaming                          |
| --------------------- | ----------------------------------------- | ---------------------------------- |
| OpenAI Chat           | `POST /v1/chat/completions`               | Yes                                |
| OpenAI Responses      | `POST /v1/responses`                      | Yes, typed SSE events              |
| OpenAI Embeddings     | `POST /v1/embeddings`                     | No                                 |
| OpenAI Images         | `POST /v1/images/generations`             | No                                 |
| OpenAI Moderations    | `POST /v1/moderations`                    | No                                 |
| Anthropic             | `POST /v1/messages`                       | Yes, all seven SSE event types     |
| Gemini Generate       | `POST /v1beta/models/*:generateContent`   | Yes, terminal `finishReason: STOP` |
| Gemini Embeddings     | `POST /v1beta/models/*:embedContent`      | No                                 |
| Gemini Token Count    | `POST /v1beta/models/*:countTokens`       | No                                 |
| Gemini Models         | `GET /v1beta/models`                      | No                                 |
| Gemini OpenAI Shim    | `/v1beta/openai/*`                        | Yes                                |
| Azure OpenAI          | `POST /openai/deployments/*`              | Yes                                |
| Bedrock               | `POST /model/*/invoke`                    | Yes                                |
| Vertex AI             | `POST /v1/projects/*/...:generateContent` | Yes                                |
| Cohere, Mistral, Groq | OpenAI-compatible                         | Yes                                |
| Error Simulator       | `ANY /error/{code}`                       | No                                 |

## Running It

- **Docker**: `docker run --rm -p 8100:8100 ghcr.io/vidaiuk/vidaimock:latest`,
  or the published Compose file when you want mounted overrides.
- **Binary**: download an archive from the GitHub releases page and run
  `./vidaimock`. Archives bundle `config/` and `examples/`.
- **Rust library**: add `vidaimock` as a dev-dependency and start a server
  in-process on an ephemeral port, which avoids port juggling and teardown in
  parallel tests.

## Agent Operating Checklist

1. Start with a no-chaos baseline request and assert schema compatibility.
2. Enable streaming and validate chunk assembly and framing.
3. Enable tool-call response shapes and validate tool dispatch parsing.
4. Add the tool-result turn and confirm the agentic loop terminates.
5. Add structured-output success and failure cases.
6. Add resilience tests using deterministic chaos headers.
7. Add RAG citation positive and negative cases.
8. Verify metrics and log signals for each scenario.

## Troubleshooting

- No response from the client:
  - Check base URL and path compatibility (`/v1/...`).
  - Confirm the process is running and bound to the expected host and port;
    `GET /health` is the cheapest check.
  - A default bind of `0.0.0.0` is not a bind failure, but a client pointed at
    the wrong interface will not reach it.
- Unexpected template output:
  - Verify the route matcher regex and provider priority.
  - Confirm mapped fields exist in the incoming request shape; render
    `GET /status` to see the resolved configuration.
  - Add `--isolated` to confirm whether a bundled default is masking a custom
    file that failed to load.
- Streaming does not appear incremental:
  - Confirm `"stream": true` in the request body.
  - Use `curl -N`, or a client that does not buffer SSE chunks.
  - Check the run mode: `benchmark` emits chunks as fast as possible by
    design.
- Tool-call parser failures:
  - Recheck the provider-specific tool schema and finish-state semantics.
  - Validate argument encoding expectations in the app under test.
- Chaos has no effect:
  - Confirm the percentage is non-zero; `X-Vidai-Chaos-Drop: 0` never fires.
  - Confirm the injected header reaches the server through any proxy in
    front of it, or move the trigger into the URL with `?chaos_status=`.

## Reference

Upstream documentation: <https://docs.vidai.uk/mock/intro/>. Project source and
releases: <https://github.com/vidaiUK/VidaiMock>.

Relevant pages:

- [CLI and headers reference](https://docs.vidai.uk/mock/getting-started/cli-reference/)
- [Chaos and error injection](https://docs.vidai.uk/mock/chaos-and-errors/)
- [Agentic workflow testing](https://docs.vidai.uk/mock/agentic-testing/)
- [Streaming](https://docs.vidai.uk/mock/streaming/)
- [Templating](https://docs.vidai.uk/mock/templating/)
- [Provider config](https://docs.vidai.uk/mock/configuration/provider-config/)

Use this skill as the default local harness for LLM integration tests before
spending budget on external provider calls.
