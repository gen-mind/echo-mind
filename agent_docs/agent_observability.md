# Agent Observability Design

End-to-end observability for EchoMind's sandboxed agent system covering ephemeral Docker containers, MCP server mediation, and the full request lifecycle.

> **Decision (2026-02-16):** Use **direct Langfuse SDK** (`langfuse_helper.py`) + **direct Prometheus** (`prometheus_client`) for all agent and MCP gateway observability. This matches the existing codebase pattern used by API, Ingestor, and Connector services.

---

## 1. Existing Observability Stack Analysis

### 1.1 Infrastructure (Already Deployed)

| Component | Image | Role | Network |
|-----------|-------|------|---------|
| Prometheus | `prom/prometheus:v3.5.1` | Metrics backend (30d retention) | backend |
| Loki | `grafana/loki:3.6.0` | Log aggregation | backend |
| Grafana | `grafana/grafana:12.3.2` | Visualization + alerting | frontend+backend |
| Alloy | `grafana/alloy:v1.11.3` | Docker log collector (replaces Promtail) | backend |
| cAdvisor | `gcr.io/cadvisor/cadvisor:v0.51.0` | Container metrics | backend |
| node-exporter | `prom/node-exporter:v1.9.0` | Host metrics | backend |
| NATS exporter | `natsio/prometheus-nats-exporter` | NATS metrics bridge | backend |
| Postgres exporter | `prometheuscommunity/postgres-exporter` | PostgreSQL metrics bridge | backend |

All gated behind `--profile observability` (`ENABLE_OBSERVABILITY=true`).

### 1.2 Langfuse (Already Deployed)

| Component | Image | Role |
|-----------|-------|------|
| langfuse-web | `langfuse/langfuse:3` | UI + API |
| langfuse-worker | `langfuse/langfuse-worker:3` | Async event processing |
| langfuse-clickhouse | `clickhouse/clickhouse-server:24.12` | OLAP trace storage |

Gated behind `--profile langfuse` (`ENABLE_LANGFUSE=true`).

**Key Langfuse details:**
- Bootstrap project: `echomind-rag` (ID: `echomind-rag`)
- Public key env: `LANGFUSE_PUBLIC_KEY` (default: `pk-echomind-dev`)
- Secret key env: `LANGFUSE_SECRET_KEY` (default: `sk-echomind-dev`)
- Internal URL: `http://langfuse-web:3000`
- Trace endpoint: `http://langfuse-web:3000/api/public/traces`
- S3 event upload via shared MinIO (bucket: `langfuse`)

### 1.3 Current Langfuse Integration

**File: `src/echomind_lib/helpers/langfuse_helper.py`**

Existing helper provides:
- `init_langfuse()` / `shutdown_langfuse()` lifecycle
- `create_trace()` with user_id, session_id, metadata, tags
- `score_trace()` for RAGAS score attachment
- `_NoOpTrace` / `_NoOpSpan` / `_NoOpGeneration` for zero-overhead disabled mode

**File: `src/api/websocket/chat_handler.py`**

Current trace structure for RAG chat:
```
trace: "chat-completion" (user_id, session_id, tags=["chat", mode])
  |-- span: "retrieval" (input=query, output=source_count+scores)
  |-- generation: "llm-completion" (model, provider, temperature, usage)
```

**File: `src/api/middleware/metrics.py`**

Prometheus metrics already exposed at `/metrics`:
- `ragas_faithfulness_score` (histogram)
- `ragas_response_relevancy_score` (histogram)
- `ragas_context_precision_score` (histogram)
- `ragas_evaluations_total` (counter, by status)
- `ragas_evaluation_duration_seconds` (histogram)

### 1.4 Prometheus Configuration

**File: `config/observability/prometheus/prometheus.yml`**

Currently scraping:
- Infrastructure: traefik, nats, qdrant, minio, loki, alloy, cadvisor, node-exporter, postgres
- EchoMind: `echomind-api` at `api:8000/metrics` (10s interval)
- Embedder scrape is commented out (placeholder)

### 1.5 Grafana Dashboards

Existing dashboards:
- `echomind-overview.json` -- service health overview
- `ragas-evaluation.json` -- RAG quality metrics
- `docker-containers.json`, `traefik.json`, `postgres.json`, `qdrant.json`, `minio.json`
- `nats-server.json`, `nats-jetstream.json`, `node-exporter.json`, `loki.json`, `loki-logs-explorer.json`

### 1.6 Grafana Datasources

Currently configured:
- Prometheus (default, at `http://prometheus:9090`)
- Loki (at `http://loki:3100`)

**Gap: No Tempo or Jaeger datasource for distributed tracing visualization in Grafana.**

---

## 2. Agent System Architecture (Observability Targets)

### 2.1 Components to Instrument

```
User Request
    |
    v
[API Service] -- existing Langfuse traces for RAG chat
    |
    v
[Agent Sandbox] -- ephemeral Docker container
    |-- BasicAgentWrapper (agent.py)
    |-- ToolPolicyEngine (9-layer filter)
    |-- ToolPolicyMiddleware (ChatMiddleware)
    |-- PathRestrictionMiddleware (FunctionMiddleware)
    |-- SessionManager (JSONL persistence)
    |-- ToolsRegistry (30 native tools)
    |
    v
[MCP Server(s)] -- tool execution via stdio/http/websocket
    |-- MCPManager (lifecycle)
    |-- MCPStdioTool / MCPStreamableHTTPTool / MCPWebsocketTool
```

### 2.2 Agent Lifecycle

1. **Session creation**: `SessionManager.create_session()` -- new JSONL file with header
2. **Agent initialization**: `AgentFactory.create_agent()` -- policy engine, middleware, MCP tools
3. **Agent execution**: `BasicAgentWrapper.run()` or `run_stream()` -- LLM calls + tool invocations
4. **Tool invocations**: Policy-filtered, path-restricted, approval-gated
5. **MCP tool calls**: Via framework MCPTool instances (stdio/http/websocket)
6. **Session persistence**: `SessionManager.append_message()` -- JSONL append
7. **Container teardown**: Ephemeral container destroyed

### 2.3 Key Observability Challenge: Ephemeral Containers

Agent sandboxes are ephemeral Docker containers that:
- Have no persistent storage for telemetry
- Cannot be scraped by Prometheus (no known endpoints)
- Must export telemetry before container dies
- Need trace context propagation from the parent API request

---

## 3. Instrumentation Plan

### 3.1 Telemetry Collection (DEFERRED — Future Feature)

> **Status: DEFERRED (2026-02-16).** The design below is preserved as reference for when ephemeral sandbox containers are implemented. For now, use direct Langfuse SDK + Prometheus (see decision note at top of document).

Deploy a telemetry collector as a shared sidecar/service that receives telemetry from ephemeral containers and forwards to Langfuse + Prometheus.

**Docker Compose addition (`docker-compose-observability.yml`):**

```yaml
  telemetry-collector:
    image: telemetry/observability-collector-contrib:0.118.0
    container_name: observability-telemetry-collector
    profiles: ["observability"]
    volumes:
      - ${CONFIG_PATH}/observability/telemetry-collector/config.yaml:/etc/telemetrycol/config.yaml:ro
    command: ["--config=/etc/telemetrycol/config.yaml"]
    healthcheck:
      test: ["CMD", "wget", "--spider", "-q", "http://localhost:13133/"]
      interval: 15s
      timeout: 5s
      retries: 3
    restart: unless-stopped
    networks:
      - backend
```

**Collector config (`config/observability/telemetry-collector/config.yaml`):**

```yaml
receivers:
  trace:
    protocols:
      http:
        endpoint: 0.0.0.0:4318
      grpc:
        endpoint: 0.0.0.0:4317

processors:
  batch:
    send_batch_size: 512
    timeout: 5s
  memory_limiter:
    check_interval: 5s
    limit_mib: 256
  resource:
    attributes:
      - key: service.namespace
        value: echomind
        action: upsert

exporters:
  # Traces -> Langfuse trace endpoint
  tracehttp/langfuse:
    endpoint: http://langfuse-web:3000/api/public/telemetry
    headers:
      Authorization: "Basic ${LANGFUSE_Telemetry_AUTH}"
    compression: gzip

  # Metrics -> Prometheus trace receiver
  tracehttp/prometheus:
    endpoint: http://prometheus:9090/api/v1/trace
    tls:
      insecure: true

  # Debug exporter (dev only)
  debug:
    verbosity: basic

extensions:
  health_check:
    endpoint: 0.0.0.0:13133

service:
  extensions: [health_check]
  pipelines:
    traces:
      receivers: [trace]
      processors: [memory_limiter, resource, batch]
      exporters: [tracehttp/langfuse]
    metrics:
      receivers: [trace]
      processors: [memory_limiter, resource, batch]
      exporters: [tracehttp/prometheus]
```

### 3.2 Why Telemetry Collector (Not Direct Export)

1. **Ephemeral containers** cannot guarantee flush before termination; the collector acts as a reliable buffer
2. **Fan-out**: Single trace intake, multiple backends (Langfuse for traces, Prometheus for metrics)
3. **Enrichment**: Resource processor adds `service.namespace=echomind` uniformly
4. **Decoupling**: Agent code exports to one endpoint; backend routing is config-only
5. **Batching**: Reduces network calls from ephemeral containers

### 3.3 Prometheus Scrape Addition

Add Telemetry Collector self-monitoring to `prometheus.yml`:

```yaml
  - job_name: "telemetry-collector"
    static_configs:
      - targets: ["telemetry-collector:8888"]
        labels:
          service: "telemetry-collector"
```

---

## 4. Trace Propagation Design

### 4.1 W3C Trace Context Flow

```
[Browser/Client]
    | (HTTP request with no trace context)
    v
[API Service] -- creates root trace
    | traceparent: 00-{trace_id}-{api_span_id}-01
    v
[Agent Sandbox Container] -- receives trace context via env vars
    | TRACEPARENT=00-{trace_id}-{api_span_id}-01
    | Creates child spans under same trace_id
    v
[MCP Server] -- receives trace context via tool call metadata
    | Creates child spans under same trace_id
    v
[Telemetry Collector] -- receives all spans, forwards to Langfuse
```

### 4.2 Context Propagation Mechanism

Since agent sandboxes are separate Docker containers, trace context must be passed explicitly:

**Option A: Environment Variables (Recommended)**

When the API spawns the agent container:

```python
# In API service (container spawner)
from observability import trace
from observability.context import get_current

span = trace.get_current_span()
ctx = span.get_span_context()
traceparent = f"00-{format(ctx.trace_id, '032x')}-{format(ctx.span_id, '016x')}-01"

# Pass to Docker container as env var
container_env = {
    "TRACEPARENT": traceparent,
    "Telemetry_EXPORTER_trace_ENDPOINT": "http://telemetry-collector:4318",
    "Telemetry_SERVICE_NAME": "echomind-agent-sandbox",
    "AGENT_RUN_ID": run_id,
    "AGENT_USER_ID": user_id,
    "AGENT_SESSION_ID": session_id,
}
```

**Option B: NATS Message Headers (If Using NATS for Agent Dispatch)**

```python
# Inject trace context into NATS headers
headers = {}
inject(headers, setter=nats_header_setter)
await nc.publish(subject, payload, headers=headers)
```

### 4.3 Agent-Side Trace Initialization

```python
# In agent sandbox entry point
import os
from observability import trace
from observability.sdk.trace import TracerProvider
from observability.sdk.trace.export import BatchSpanProcessor
from observability.exporter.trace.proto.http.trace_exporter import traceSpanExporter
from observability.trace.propagation import TraceContextTextMapPropagator

def init_agent_telemetry() -> trace.Tracer:
    """Initialize Telemetry tracing in agent sandbox with parent context."""
    provider = TracerProvider(
        resource=Resource.create({
            "service.name": "echomind-agent-sandbox",
            "service.version": os.getenv("AGENT_VERSION", "unknown"),
            "agent.run.id": os.getenv("AGENT_RUN_ID", ""),
            "agent.user.id": os.getenv("AGENT_USER_ID", ""),
        })
    )

    exporter = traceSpanExporter(
        endpoint=os.getenv("Telemetry_EXPORTER_trace_ENDPOINT", "http://telemetry-collector:4318") + "/v1/traces",
    )
    provider.add_span_processor(BatchSpanProcessor(
        exporter,
        max_export_batch_size=64,
        schedule_delay_millis=2000,
    ))

    trace.set_tracer_provider(provider)

    # Extract parent context from TRACEPARENT env var
    traceparent = os.getenv("TRACEPARENT")
    if traceparent:
        ctx = TraceContextTextMapPropagator().extract(
            {"traceparent": traceparent}
        )
        # Store as current context for child spans
        return trace.get_tracer("echomind.agent"), ctx

    return trace.get_tracer("echomind.agent"), None
```

### 4.4 Graceful Shutdown (Critical for Ephemeral Containers)

```python
async def shutdown_telemetry(provider: TracerProvider) -> None:
    """Flush all pending spans before container exits."""
    # Force flush with timeout -- critical for ephemeral containers
    provider.force_flush(timeout_millis=10000)
    provider.shutdown()
```

This MUST be called in a `finally` block or `atexit` handler.

---

## 5. Agent Sandbox Instrumentation

### 5.1 Span Hierarchy (Per Agent Run)

Following Observability GenAI Semantic Conventions:

```
invoke_agent {agent_name}                    [gen_ai.operation.name=invoke_agent]
  |
  |-- chat {model}                           [gen_ai.operation.name=chat]
  |     |-- (LLM request/response)
  |
  |-- execute_tool {tool_name}               [gen_ai.operation.name=execute_tool]
  |     |-- (tool execution)
  |
  |-- chat {model}                           [gen_ai.operation.name=chat]
  |     |-- (LLM with tool results)
  |
  |-- execute_tool {tool_name}               [gen_ai.operation.name=execute_tool]
  |     |-- mcp_call {server_name}           [custom span for MCP]
  |
  |-- chat {model}                           [gen_ai.operation.name=chat]
  |     |-- (final response)
  |
  |-- policy_filter                          [custom span]
  |     |-- (9-layer filter evaluation)
```

### 5.2 GenAI Semantic Convention Attributes

**invoke_agent span:**

```python
{
    "gen_ai.operation.name": "invoke_agent",
    "gen_ai.agent.name": config.name,
    "gen_ai.agent.id": config.id,
    "gen_ai.provider.name": "openai",  # or detected provider
    "gen_ai.request.model": config.model,
    "gen_ai.conversation.id": session_key,
    # EchoMind-specific
    "echomind.agent.profile": tools_policy.profile,
    "echomind.agent.tool_count": len(tools),
    "echomind.agent.mcp_server_count": len(mcp_tools),
    "echomind.sandbox.enabled": sandbox.enabled,
}
```

**chat span:**

```python
{
    "gen_ai.operation.name": "chat",
    "gen_ai.request.model": "gpt-4o-mini",
    "gen_ai.request.temperature": 0.7,
    "gen_ai.request.max_tokens": 4096,
    "gen_ai.usage.input_tokens": 1250,
    "gen_ai.usage.output_tokens": 340,
    "gen_ai.response.model": "gpt-4o-mini-2024-07-18",
    "gen_ai.response.finish_reasons": ["tool_calls"],
    "server.address": "api.openai.com",
}
```

**execute_tool span:**

```python
{
    "gen_ai.operation.name": "execute_tool",
    "gen_ai.tool.name": "grep",
    "gen_ai.tool.type": "function",
    "gen_ai.tool.call.id": "call_abc123",
    # Opt-in (may contain sensitive data)
    "gen_ai.tool.call.arguments": '{"pattern": "TODO", "path": "/workspace"}',
    "gen_ai.tool.call.result": '{"matches": 42}',
    # EchoMind-specific
    "echomind.tool.approval_mode": "never_require",
    "echomind.tool.source": "native",  # or "mcp"
    "echomind.tool.mcp_server": "",     # populated for MCP tools
    "echomind.tool.path_restricted": False,
    "echomind.tool.policy_layer_removed": False,
}
```

### 5.3 Implementation in BasicAgentWrapper

The agent framework already uses middleware for tool policy and path restriction. Observability should be added as another middleware layer:

```python
# src/agent/observability/middleware.py

class ObservabilityMiddleware(ChatMiddleware):
    """Records Telemetry spans for each LLM call in the agent loop."""

    def __init__(self, tracer: trace.Tracer) -> None:
        self.tracer = tracer

    async def process(self, context: ChatContext, call_next: Any) -> None:
        model = context.options.get("model", "unknown")
        with self.tracer.start_as_current_span(
            f"chat {model}",
            attributes={
                "gen_ai.operation.name": "chat",
                "gen_ai.request.model": model,
            },
        ) as span:
            await call_next()

            # Extract usage from response
            if hasattr(context, "response") and context.response:
                usage = getattr(context.response, "usage", None)
                if usage:
                    span.set_attribute("gen_ai.usage.input_tokens",
                                       getattr(usage, "prompt_tokens", 0))
                    span.set_attribute("gen_ai.usage.output_tokens",
                                       getattr(usage, "completion_tokens", 0))


class ToolObservabilityMiddleware(FunctionMiddleware):
    """Records Telemetry spans for each tool invocation."""

    def __init__(self, tracer: trace.Tracer) -> None:
        self.tracer = tracer

    async def process(
        self,
        context: FunctionInvocationContext,
        call_next: Callable[[], Awaitable[None]],
    ) -> None:
        tool_name = context.function.name
        with self.tracer.start_as_current_span(
            f"execute_tool {tool_name}",
            attributes={
                "gen_ai.operation.name": "execute_tool",
                "gen_ai.tool.name": tool_name,
                "gen_ai.tool.type": "function",
            },
        ) as span:
            start = time.monotonic()
            await call_next()
            duration = time.monotonic() - start

            span.set_attribute("echomind.tool.duration_ms",
                               int(duration * 1000))

            if context.result is not None:
                result_str = str(context.result)
                span.set_attribute("echomind.tool.result_length",
                                   len(result_str))
                # Truncate for safety
                if len(result_str) > 1000:
                    result_str = result_str[:1000] + "..."
                span.set_attribute("gen_ai.tool.call.result", result_str)
```

### 5.4 Langfuse Attribute Mapping

Using the Telemetry-to-Langfuse attribute mapping, set these on the root span:

```python
root_span.set_attribute("langfuse.trace.name", f"agent-run:{agent_config.id}")
root_span.set_attribute("langfuse.user.id", user_id)
root_span.set_attribute("langfuse.session.id", session_id)
root_span.set_attribute("langfuse.trace.tags", json.dumps(["agent", agent_config.id]))
```

This ensures Langfuse correctly maps the Telemetry trace to its data model with proper user/session correlation.

---

## 6. MCP Server Observability

### 6.1 MCP Call Tracing

Every MCP tool call should be wrapped in a span:

```python
# Enhancement to MCPManager or as middleware on MCP tools

async def traced_mcp_call(
    tool: MCPTool,
    server_name: str,
    tool_name: str,
    arguments: dict,
    tracer: trace.Tracer,
) -> Any:
    """Execute MCP tool call with Telemetry tracing."""
    with tracer.start_as_current_span(
        f"mcp_call {server_name}/{tool_name}",
        attributes={
            "gen_ai.operation.name": "execute_tool",
            "gen_ai.tool.name": tool_name,
            "gen_ai.tool.type": "function",
            "echomind.tool.source": "mcp",
            "echomind.mcp.server_name": server_name,
            "echomind.mcp.transport": tool._transport_type,
        },
    ) as span:
        start = time.monotonic()
        try:
            result = await tool.call(tool_name, arguments)
            span.set_status(StatusCode.OK)
            return result
        except Exception as e:
            span.set_status(StatusCode.ERROR, str(e))
            span.set_attribute("error.type", type(e).__name__)
            raise
        finally:
            duration = time.monotonic() - start
            span.set_attribute("echomind.tool.duration_ms", int(duration * 1000))
```

### 6.2 MCP Audit Log

Every MCP tool call generates a structured audit log entry written to the agent's JSONL session file and also emitted as an Telemetry event:

```python
@dataclass
class MCPAuditEntry:
    """Audit log entry for MCP tool calls."""
    timestamp: str          # ISO 8601
    trace_id: str           # Telemetry trace ID
    span_id: str            # Telemetry span ID
    user_id: str            # Requesting user
    agent_id: str           # Agent that made the call
    mcp_server: str         # MCP server name
    tool_name: str          # Tool invoked
    arguments_hash: str     # SHA-256 of arguments (not raw args)
    duration_ms: int        # Execution time
    result_status: str      # "success" | "error" | "denied"
    error_message: str | None
```

Emit as Telemetry event on the MCP span:

```python
span.add_event(
    "mcp.tool.call",
    attributes={
        "mcp.server": server_name,
        "mcp.tool": tool_name,
        "mcp.status": "success",
        "mcp.duration_ms": 42,
        "mcp.user_id": user_id,
    },
)
```

### 6.3 MCP Rate Limiting Metrics

```python
# Prometheus metrics for MCP tool calls
mcp_tool_calls_total = Counter(
    "echomind_mcp_tool_calls_total",
    "Total MCP tool calls",
    ["server_name", "tool_name", "status"],  # status: success/error/denied
)

mcp_tool_call_duration = Histogram(
    "echomind_mcp_tool_call_duration_seconds",
    "MCP tool call duration",
    ["server_name", "tool_name"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
)

mcp_active_connections = Gauge(
    "echomind_mcp_active_connections",
    "Currently connected MCP servers",
    ["server_name", "transport"],
)
```

---

## 7. Cost Tracking

### 7.1 Token Usage Per Run

Every `chat` span captures `gen_ai.usage.input_tokens` and `gen_ai.usage.output_tokens`. Aggregate at the `invoke_agent` span level:

```python
# At end of agent run, compute totals
total_input_tokens = sum(
    span.attributes.get("gen_ai.usage.input_tokens", 0)
    for span in chat_spans
)
total_output_tokens = sum(
    span.attributes.get("gen_ai.usage.output_tokens", 0)
    for span in chat_spans
)

root_span.set_attribute("echomind.cost.total_input_tokens", total_input_tokens)
root_span.set_attribute("echomind.cost.total_output_tokens", total_output_tokens)
root_span.set_attribute("echomind.cost.total_tokens",
                        total_input_tokens + total_output_tokens)
root_span.set_attribute("echomind.cost.estimated_usd",
                        _estimate_cost(model, total_input_tokens, total_output_tokens))
```

### 7.2 Cost Estimation Model

```python
# Model pricing (USD per 1M tokens) -- update as prices change
MODEL_PRICING: dict[str, tuple[float, float]] = {
    # (input_per_1M, output_per_1M)
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4.1": (2.00, 8.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "claude-sonnet-4-20250514": (3.00, 15.00),
    "claude-haiku-3.5": (0.80, 4.00),
}

def _estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate USD cost for a model run."""
    pricing = MODEL_PRICING.get(model, (1.00, 3.00))  # fallback
    return (input_tokens * pricing[0] + output_tokens * pricing[1]) / 1_000_000
```

### 7.3 Prometheus Cost Metrics

```python
agent_run_tokens_total = Counter(
    "echomind_agent_run_tokens_total",
    "Total tokens consumed by agent runs",
    ["agent_id", "model", "token_type"],  # token_type: input/output
)

agent_run_cost_usd = Counter(
    "echomind_agent_run_cost_usd_total",
    "Estimated USD cost of agent runs",
    ["agent_id", "model"],
)

agent_run_cost_per_user = Counter(
    "echomind_agent_run_cost_per_user_usd_total",
    "Estimated USD cost per user",
    ["user_id"],
)
```

### 7.4 Langfuse Cost Integration

Langfuse natively supports cost tracking via the `gen_ai.usage.*` attributes. Additionally, set:

```python
span.set_attribute("langfuse.observation.cost_details",
                   json.dumps({"input": input_cost, "output": output_cost}))
```

Langfuse will display cost per trace, per user, per session in its UI.

---

## 8. Langfuse Integration Patterns for Agent Runs

### 8.1 Dual-Path Strategy

| Path | Source | Target | Protocol |
|------|--------|--------|----------|
| RAG Chat (existing) | API service | Langfuse directly | Langfuse Python SDK |
| Agent Runs (new) | Agent sandbox | Telemetry Collector -> Langfuse | trace/HTTP |

The RAG chat path continues using the existing `langfuse_helper.py` SDK integration. Agent runs use Telemetry because:
- Ephemeral containers benefit from the collector's buffering
- Telemetry provides vendor-neutral instrumentation
- The collector handles auth (base64 key encoding) centrally

### 8.2 Langfuse Trace Structure for Agent Runs

```
Trace: "agent-run:coder" (user_id, session_id, tags=["agent", "coder"])
  |
  |-- Generation: "chat gpt-4o-mini" (model, usage, duration)
  |     input: system prompt + user query
  |     output: "I'll search for that file..."
  |
  |-- Span: "execute_tool grep" (duration)
  |     input: {"pattern": "TODO", "path": "/workspace"}
  |     output: {"matches": 42, "files": [...]}
  |
  |-- Span: "execute_tool read" (duration)
  |     input: {"file_path": "/workspace/src/main.py"}
  |     output: {truncated file content}
  |
  |-- Span: "mcp_call filesystem/list_directory" (duration)
  |     input: {"path": "/workspace/docs"}
  |     output: {"entries": [...]}
  |
  |-- Generation: "chat gpt-4o-mini" (model, usage, duration)
  |     input: tool results + conversation
  |     output: final response
  |
  Score: "cost_usd" = 0.0034
  Score: "total_tokens" = 2847
  Score: "tool_calls" = 3
```

### 8.3 Telemetry-to-Langfuse Mapping Rules

| Telemetry Attribute | Langfuse Field |
|----------------|---------------|
| `langfuse.trace.name` | Trace name |
| `langfuse.user.id` | User ID |
| `langfuse.session.id` | Session ID |
| `gen_ai.request.model` | Model (auto-detects as "generation" type) |
| `gen_ai.usage.input_tokens` | Input tokens |
| `gen_ai.usage.output_tokens` | Output tokens |
| `langfuse.observation.cost_details` | Cost breakdown |
| Span with `model` attribute | Becomes "generation" observation |
| Span without `model` attribute | Becomes "span" observation |

### 8.4 Telemetry Collector Auth Configuration

The collector needs the Langfuse API keys encoded as Basic Auth:

```bash
# In .env
LANGFUSE_Telemetry_AUTH=$(echo -n "${LANGFUSE_PUBLIC_KEY}:${LANGFUSE_SECRET_KEY}" | base64)
```

Pass to collector via environment:

```yaml
  telemetry-collector:
    environment:
      - LANGFUSE_Telemetry_AUTH=${LANGFUSE_Telemetry_AUTH}
```

---

## 9. Correlation Across Boundaries

### 9.1 Full Request Trace

```
Browser -> API -> Agent Sandbox -> MCP Server -> Tool Execution
   |         |          |              |              |
   |     trace_id   trace_id      trace_id       trace_id
   |     span_A     span_B        span_C         span_D
   |         |          |              |              |
   |         +----parent-+----parent---+----parent----+
```

All spans share the same `trace_id`. Each creates a child span under its parent.

### 9.2 Correlation IDs

Every agent run carries these correlation IDs across all boundaries:

| ID | Source | Propagated Via |
|----|--------|---------------|
| `trace_id` | Telemetry (W3C Trace Context) | `TRACEPARENT` env var |
| `agent_run_id` | API generates UUID | Container env var |
| `user_id` | JWT token claim | Container env var |
| `session_id` | Chat session or routing key | Container env var |
| `conversation_id` | Agent session key | `gen_ai.conversation.id` attribute |

### 9.3 Log Correlation

Alloy already collects Docker container logs. Add trace context to log messages:

```python
import logging

class TraceContextFilter(logging.Filter):
    """Inject Telemetry trace/span IDs into log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        span = trace.get_current_span()
        ctx = span.get_span_context()
        if ctx.is_valid:
            record.trace_id = format(ctx.trace_id, '032x')
            record.span_id = format(ctx.span_id, '016x')
        else:
            record.trace_id = "0" * 32
            record.span_id = "0" * 16
        return True
```

Log format with trace context:

```python
LOG_FORMAT = (
    "%(asctime)s - %(levelname)s - %(name)s - "
    "trace_id=%(trace_id)s span_id=%(span_id)s - %(message)s"
)
```

This enables Grafana Loki -> Tempo correlation: click a log line, jump to the trace.

---

## 10. Grafana Dashboard Specifications

### 10.1 Dashboard: Agent Runs Overview

**File: `config/observability/grafana/dashboards/agent-runs.json`**

**Panels:**

| Panel | Type | Query | Description |
|-------|------|-------|-------------|
| Agent Runs (rate) | Time series | `rate(echomind_agent_runs_total[5m])` | Runs per second by agent_id |
| Agent Run Duration | Heatmap | `echomind_agent_run_duration_seconds` | P50/P95/P99 latency distribution |
| Tool Calls Per Run | Stat | `avg(echomind_agent_tool_calls_per_run)` | Average tool calls per agent run |
| Active Runs | Gauge | `echomind_agent_active_runs` | Currently executing agent runs |
| Error Rate | Time series | `rate(echomind_agent_runs_total{status="error"}[5m]) / rate(echomind_agent_runs_total[5m])` | Error percentage |
| Top Tools | Bar chart | `topk(10, sum by (tool_name) (echomind_tool_calls_total))` | Most-used tools |
| Token Usage | Time series | `sum(rate(echomind_agent_run_tokens_total[5m])) by (token_type)` | Input vs output token rate |
| Estimated Cost | Stat | `sum(increase(echomind_agent_run_cost_usd_total[24h]))` | Daily cost estimate |

### 10.2 Dashboard: MCP Server Health

**File: `config/observability/grafana/dashboards/mcp-servers.json`**

**Panels:**

| Panel | Type | Query | Description |
|-------|------|-------|-------------|
| Connected Servers | Stat | `echomind_mcp_active_connections` | Connected vs configured |
| Tool Call Rate | Time series | `rate(echomind_mcp_tool_calls_total[5m])` | Calls/sec by server |
| Tool Call Duration | Heatmap | `echomind_mcp_tool_call_duration_seconds` | Latency distribution |
| Error Rate | Time series | `rate(echomind_mcp_tool_calls_total{status="error"}[5m])` | Errors by server |
| Denied Calls | Counter | `sum(echomind_mcp_tool_calls_total{status="denied"})` | Policy-blocked calls |
| Tool Usage Breakdown | Pie chart | `sum by (tool_name) (echomind_mcp_tool_calls_total)` | Distribution by tool |

### 10.3 Dashboard: Agent Cost Analysis

**File: `config/observability/grafana/dashboards/agent-cost.json`**

**Panels:**

| Panel | Type | Query | Description |
|-------|------|-------|-------------|
| Daily Cost | Time series | `sum(increase(echomind_agent_run_cost_usd_total[1d]))` | USD per day |
| Cost by Model | Stacked bar | `sum by (model) (increase(echomind_agent_run_cost_usd_total[1d]))` | Model cost breakdown |
| Cost by Agent | Stacked bar | `sum by (agent_id) (increase(echomind_agent_run_cost_usd_total[1d]))` | Agent cost breakdown |
| Cost by User | Table | `topk(20, sum by (user_id) (increase(echomind_agent_run_cost_per_user_usd_total[30d])))` | Top 20 users by spend |
| Token Efficiency | Stat | `avg(echomind_agent_run_tokens_total{token_type="output"} / echomind_agent_run_tokens_total{token_type="input"})` | Output/input ratio |
| Monthly Projection | Stat | `sum(increase(echomind_agent_run_cost_usd_total[7d])) * 4.3` | 30-day cost projection |

---

## 11. Prometheus Metrics Summary

### 11.1 Agent Metrics (New)

```python
# All metrics use prefix: echomind_agent_

echomind_agent_runs_total = Counter(
    "echomind_agent_runs_total",
    "Total agent runs",
    ["agent_id", "model", "status"],  # status: success/error/cancelled
)

echomind_agent_run_duration_seconds = Histogram(
    "echomind_agent_run_duration_seconds",
    "Agent run duration",
    ["agent_id", "model"],
    buckets=(0.5, 1, 2, 5, 10, 30, 60, 120, 300),
)

echomind_agent_active_runs = Gauge(
    "echomind_agent_active_runs",
    "Currently active agent runs",
    ["agent_id"],
)

echomind_agent_tool_calls_per_run = Histogram(
    "echomind_agent_tool_calls_per_run",
    "Number of tool calls per agent run",
    ["agent_id"],
    buckets=(0, 1, 2, 3, 5, 10, 20, 50),
)

echomind_agent_llm_calls_per_run = Histogram(
    "echomind_agent_llm_calls_per_run",
    "Number of LLM calls per agent run (agentic loop iterations)",
    ["agent_id", "model"],
    buckets=(1, 2, 3, 5, 10, 20),
)
```

### 11.2 Tool Metrics (New)

```python
echomind_tool_calls_total = Counter(
    "echomind_tool_calls_total",
    "Total tool calls across all agents",
    ["tool_name", "source", "status"],  # source: native/mcp, status: success/error/denied
)

echomind_tool_call_duration_seconds = Histogram(
    "echomind_tool_call_duration_seconds",
    "Tool call duration",
    ["tool_name", "source"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)

echomind_tool_policy_filtered_total = Counter(
    "echomind_tool_policy_filtered_total",
    "Tools removed by policy engine",
    ["layer"],  # profile, global, agent, sandbox, subagent
)
```

### 11.3 Session Metrics (New)

```python
echomind_agent_sessions_total = Counter(
    "echomind_agent_sessions_total",
    "Total agent sessions created",
    ["agent_id"],
)

echomind_agent_session_messages = Histogram(
    "echomind_agent_session_messages",
    "Messages per session",
    ["agent_id"],
    buckets=(1, 5, 10, 20, 50, 100),
)
```

### 11.4 Metrics Export Strategy

For **ephemeral agent containers**, metrics cannot be scraped by Prometheus. Instead:

1. Use Telemetry SDK's `PeriodicExportingMetricReader` to push metrics via trace
2. Telemetry Collector receives and forwards to Prometheus via `tracehttp/prometheus` exporter
3. Prometheus ingests via its trace receiver (`--web.enable-trace-receiver`, already enabled)

For **long-lived services** (API, MCP servers), continue using `prometheus_client` library with pull-based `/metrics` endpoint.

---

## 12. Implementation Phases

### Phase 1: Telemetry Collector + Basic Agent Tracing

1. Deploy Telemetry Collector in `docker-compose-observability.yml`
2. Add `config/observability/telemetry-collector/config.yaml`
3. Create `src/agent/observability/__init__.py` with `init_agent_telemetry()`
4. Add `ObservabilityMiddleware` (ChatMiddleware) for LLM call spans
5. Add `ToolObservabilityMiddleware` (FunctionMiddleware) for tool call spans
6. Wire into `BasicAgentWrapper.__init__()` middleware chain
7. Pass `TRACEPARENT` + `Telemetry_EXPORTER_trace_ENDPOINT` to sandbox containers
8. Verify traces appear in Langfuse

### Phase 2: MCP Observability + Audit Log

1. Add MCP call tracing wrapper in `MCPManager`
2. Add MCP audit log entries to session JSONL
3. Add MCP Prometheus metrics (via trace push)
4. Create `mcp-servers.json` Grafana dashboard

### Phase 3: Cost Tracking + Per-User Aggregation

1. Implement cost estimation in `invoke_agent` span end hook
2. Add token/cost Prometheus counters
3. Add Langfuse cost_details attributes
4. Create `agent-cost.json` Grafana dashboard

### Phase 4: Full Correlation + Log Integration

1. Add `TraceContextFilter` to agent logging
2. Update Alloy config to parse trace_id from logs
3. Add Tempo datasource to Grafana (or use Langfuse as trace backend)
4. Configure Grafana Loki -> trace correlation
5. Create `agent-runs.json` Grafana dashboard

### Phase 5: Alerting Rules

```yaml
# Prometheus alerting rules
groups:
  - name: echomind-agents
    rules:
      - alert: AgentHighErrorRate
        expr: rate(echomind_agent_runs_total{status="error"}[5m]) / rate(echomind_agent_runs_total[5m]) > 0.1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Agent {{ $labels.agent_id }} error rate above 10%"

      - alert: AgentHighLatency
        expr: histogram_quantile(0.95, rate(echomind_agent_run_duration_seconds_bucket[5m])) > 60
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Agent P95 latency above 60s"

      - alert: MCPServerDisconnected
        expr: echomind_mcp_active_connections == 0
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "MCP server {{ $labels.server_name }} disconnected"

      - alert: AgentDailyCostHigh
        expr: sum(increase(echomind_agent_run_cost_usd_total[24h])) > 50
        for: 1h
        labels:
          severity: warning
        annotations:
          summary: "Agent daily cost exceeds $50"
```

---

## 13. Python Dependencies

### Agent Sandbox Container

```
observability-api==1.39.1
observability-sdk==1.39.1
observability-exporter-trace-proto-http==1.39.1
observability-semantic-conventions==0.50b0
```

### MCP Gateway

```
observability-api==1.39.1
observability-sdk==1.39.1
prometheus-client==0.21.1
```

### API Service (Optional Enhancement)

```
observability-api==1.39.1
observability-sdk==1.39.1
```

No changes needed to the existing `langfuse` SDK dependency or `prometheus-client` in the API service.

---

## 14. Environment Variables

### Telemetry Collector

```bash
LANGFUSE_Telemetry_AUTH=<base64 of pk:sk>
```

### Agent Sandbox Containers

```bash
Telemetry_EXPORTER_trace_ENDPOINT=http://telemetry-collector:4318
Telemetry_SERVICE_NAME=echomind-agent-sandbox
TRACEPARENT=00-{trace_id}-{parent_span_id}-01
AGENT_RUN_ID=<uuid>
AGENT_USER_ID=<user_id>
AGENT_SESSION_ID=<session_id>
```

---

## 15. Detailed Implementation Plan

This section provides a file-by-file implementation plan with complete configurations, code, tests, and deployment instructions. A developer can start coding immediately from this plan.

---

### 15.1 Telemetry Collector Service — Complete Implementation

#### 15.1.1 Config File: `config/observability/telemetry-collector/config.yaml`

This is the complete, production-ready Telemetry Collector configuration. It receives telemetry from ephemeral agent sandbox containers via trace (both gRPC and HTTP), processes it through batching and memory limiting, and fans out to Langfuse (traces) and Prometheus (metrics).

```yaml
# ============================================
# Observability Collector Configuration
# EchoMind Agent Observability
# ============================================
# Receives telemetry from ephemeral agent sandbox containers
# and fans out to Langfuse (traces) and Prometheus (metrics).

receivers:
  trace:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
        max_recv_msg_size_mib: 4
      http:
        endpoint: 0.0.0.0:4318
        cors:
          allowed_origins: []  # Internal only, no CORS needed

processors:
  # Prevent OOM on traffic spikes from many concurrent sandboxes
  memory_limiter:
    check_interval: 5s
    limit_mib: 256
    spike_limit_mib: 64

  # Batch telemetry for efficient export
  batch:
    send_batch_size: 512
    send_batch_max_size: 1024
    timeout: 5s

  # Enrich all telemetry with service namespace
  resource:
    attributes:
      - key: service.namespace
        value: echomind
        action: upsert

  # Add deployment environment from env var
  resource/environment:
    attributes:
      - key: deployment.environment
        value: ${env:DEPLOYMENT_ENVIRONMENT:-development}
        action: upsert

  # Filter out health check spans to reduce noise
  filter/health:
    error_mode: ignore
    traces:
      span:
        - 'attributes["http.target"] == "/healthz"'
        - 'attributes["http.target"] == "/health"'

exporters:
  # Traces -> Langfuse trace endpoint
  # Langfuse v3 accepts trace traces at /api/public/telemetry/v1/traces
  # Auth: Basic base64(public_key:secret_key)
  tracehttp/langfuse:
    endpoint: http://langfuse-web:3000/api/public/telemetry
    headers:
      Authorization: "Basic ${env:LANGFUSE_Telemetry_AUTH}"
    compression: gzip
    retry_on_failure:
      enabled: true
      initial_interval: 5s
      max_interval: 30s
      max_elapsed_time: 300s
    sending_queue:
      enabled: true
      num_consumers: 4
      queue_size: 256

  # Metrics -> Prometheus trace receiver
  # Prometheus v3.5.1 has --web.enable-trace-receiver enabled
  tracehttp/prometheus:
    endpoint: http://prometheus:9090/api/v1/trace
    tls:
      insecure: true

  # Debug exporter for development (set Telemetry_DEBUG=true)
  debug:
    verbosity: basic
    sampling_initial: 5
    sampling_thereafter: 200

extensions:
  health_check:
    endpoint: 0.0.0.0:13133
    path: /health

  # Self-monitoring metrics for Prometheus scrape
  zpages:
    endpoint: 0.0.0.0:55679

service:
  extensions: [health_check, zpages]
  telemetry:
    logs:
      level: info
    metrics:
      address: 0.0.0.0:8888  # Prometheus scrape endpoint for collector self-metrics

  pipelines:
    traces:
      receivers: [trace]
      processors: [memory_limiter, filter/health, resource, resource/environment, batch]
      exporters: [tracehttp/langfuse]

    metrics:
      receivers: [trace]
      processors: [memory_limiter, resource, resource/environment, batch]
      exporters: [tracehttp/prometheus]
```

**Key design decisions:**
- `memory_limiter` is first in the processor chain to prevent OOM during traffic spikes (e.g., 8 concurrent sandboxes flushing at shutdown) [Source: Observability Collector Configuration Best Practices -- Feb 2026](https://observability.io/docs/security/config-best-practices/)
- `filter/health` removes health check spans that would pollute Langfuse traces
- `sending_queue` with 256 entries buffers Langfuse exports during transient failures
- `zpages` extension provides debugging at `http://telemetry-collector:55679/tracez`
- Self-metrics exposed at `:8888` for Prometheus to scrape the collector itself

#### 15.1.2 Docker Compose Service Definition

Add to `deployment/docker-cluster/docker-compose-observability.yml`, before the `volumes:` section:

```yaml
  # ============================================
  # Telemetry COLLECTOR (Agent Telemetry Gateway)
  # Receives trace from ephemeral sandbox containers,
  # fans out to Langfuse (traces) + Prometheus (metrics)
  # ============================================
  telemetry-collector:
    image: telemetry/observability-collector-contrib:0.118.0
    container_name: observability-telemetry-collector
    profiles: ["observability"]
    volumes:
      - ${CONFIG_PATH}/observability/telemetry-collector/config.yaml:/etc/telemetrycol-contrib/config.yaml:ro
    command: ["--config=/etc/telemetrycol-contrib/config.yaml"]
    environment:
      - LANGFUSE_Telemetry_AUTH=${LANGFUSE_Telemetry_AUTH:-}
      - DEPLOYMENT_ENVIRONMENT=${DEPLOYMENT_ENVIRONMENT:-development}
    healthcheck:
      test: ["CMD", "wget", "--spider", "-q", "http://localhost:13133/health"]
      interval: 15s
      timeout: 5s
      retries: 3
      start_period: 10s
    deploy:
      resources:
        limits:
          cpus: "0.5"
          memory: 512M
        reservations:
          cpus: "0.1"
          memory: 128M
    restart: unless-stopped
    networks:
      - backend
      - sandbox
    labels:
      - "traefik.enable=false"
```

**Network configuration:**
- `backend`: Connects to Langfuse (`langfuse-web:3000`) and Prometheus (`prometheus:9090`)
- `sandbox`: Receives telemetry from ephemeral agent containers

**Note:** The `sandbox` network is defined in `docker-compose-sandbox.yml` (Phase 4 deliverable). During Phase 6 (observability), the Telemetry collector is added to both networks.

#### 15.1.3 Prometheus Scrape Addition

Add this job to `config/observability/prometheus/prometheus.yml` under the EchoMind Services section:

```yaml
  # --- Telemetry Collector self-monitoring ---
  - job_name: "telemetry-collector"
    static_configs:
      - targets: ["telemetry-collector:8888"]
        labels:
          service: "telemetry-collector"
```

#### 15.1.4 Environment Variable Generation

Add to `.env.example` (template) and document in deployment config:

```bash
# Telemetry Collector — Langfuse auth (base64 of public_key:secret_key)
# Generate: echo -n "pk-echomind-dev:sk-echomind-dev" | base64
LANGFUSE_Telemetry_AUTH=cGstZWNob21pbmQtZGV2OnNrLWVjaG9taW5kLWRldg==
DEPLOYMENT_ENVIRONMENT=development
```

The `LANGFUSE_Telemetry_AUTH` value must be regenerated whenever Langfuse API keys change. For production, this should be computed in `cluster.sh` startup:

```bash
# In cluster.sh, after loading .env
export LANGFUSE_Telemetry_AUTH=$(echo -n "${LANGFUSE_PUBLIC_KEY}:${LANGFUSE_SECRET_KEY}" | base64)
```

---

### 15.2 Agent Instrumentation — Sandbox Container Code

#### 15.2.1 Module: `src/agent/observability/__init__.py`

```python
"""
Agent observability package.

Provides Observability instrumentation for agent sandbox containers:
- Trace initialization with parent context propagation
- ChatMiddleware for LLM call spans
- FunctionMiddleware for tool call spans
- Metrics collection via Telemetry SDK
- Graceful shutdown with telemetry flush
"""

from .metrics import AgentMetrics, init_agent_metrics
from .middleware import ObservabilityMiddleware, ToolObservabilityMiddleware
from .telemetry import init_agent_telemetry, shutdown_telemetry

__all__ = [
    "AgentMetrics",
    "ObservabilityMiddleware",
    "ToolObservabilityMiddleware",
    "init_agent_metrics",
    "init_agent_telemetry",
    "shutdown_telemetry",
]
```

#### 15.2.2 Module: `src/agent/observability/telemetry.py`

This module handles Telemetry trace provider initialization and W3C Trace Context propagation from the parent API service.

```python
"""
Observability telemetry initialization for agent sandbox containers.

Handles:
- TracerProvider setup with trace HTTP exporter
- W3C Trace Context propagation from TRACEPARENT env var
- Resource attributes for agent identification
- Graceful shutdown with telemetry flush

The TRACEPARENT env var follows the W3C Trace Context specification:
  00-{trace_id_hex_32}-{parent_span_id_hex_16}-{trace_flags_hex_2}
Example:
  00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
"""

from __future__ import annotations

import logging
import os
from typing import Any

from observability import context, trace
from observability.sdk.resources import Resource
from observability.sdk.trace import TracerProvider
from observability.sdk.trace.export import BatchSpanProcessor
from observability.exporter.trace.proto.http.trace_exporter import traceSpanExporter
from observability.trace.propagation.tracecontext import TraceContextTextMapPropagator

logger = logging.getLogger(__name__)

# Module-level state
_provider: TracerProvider | None = None
_parent_context: context.Context | None = None


def init_agent_telemetry() -> tuple[trace.Tracer, context.Context | None]:
    """
    Initialize Observability tracing in an agent sandbox container.

    Reads configuration from environment variables:
    - Telemetry_EXPORTER_trace_ENDPOINT: Collector endpoint (default: http://telemetry-collector:4318)
    - Telemetry_SERVICE_NAME: Service name (default: echomind-agent-sandbox)
    - TRACEPARENT: W3C Trace Context from parent API request
    - AGENT_RUN_ID: Unique identifier for this agent run
    - AGENT_USER_ID: User who initiated the agent run
    - AGENT_SESSION_ID: Chat session identifier

    Returns:
        Tuple of (tracer, parent_context). parent_context is None if no
        TRACEPARENT was provided.

    Raises:
        RuntimeError: If Telemetry SDK packages are not installed.
    """
    global _provider, _parent_context

    endpoint = os.getenv(
        "Telemetry_EXPORTER_trace_ENDPOINT", "http://telemetry-collector:4318"
    )
    service_name = os.getenv("Telemetry_SERVICE_NAME", "echomind-agent-sandbox")

    resource = Resource.create(
        {
            "service.name": service_name,
            "service.version": os.getenv("AGENT_VERSION", "0.1.0"),
            "agent.run.id": os.getenv("AGENT_RUN_ID", ""),
            "agent.user.id": os.getenv("AGENT_USER_ID", ""),
            "agent.session.id": os.getenv("AGENT_SESSION_ID", ""),
        }
    )

    _provider = TracerProvider(resource=resource)

    exporter = traceSpanExporter(
        endpoint=f"{endpoint}/v1/traces",
    )
    _provider.add_span_processor(
        BatchSpanProcessor(
            exporter,
            max_export_batch_size=64,
            schedule_delay_millis=2000,
            max_queue_size=512,
        )
    )

    trace.set_tracer_provider(_provider)

    # Extract parent context from TRACEPARENT env var
    traceparent = os.getenv("TRACEPARENT")
    if traceparent:
        propagator = TraceContextTextMapPropagator()
        _parent_context = propagator.extract({"traceparent": traceparent})
        logger.info(f"🔗 Trace context propagated from parent: {traceparent[:50]}...")
    else:
        _parent_context = None
        logger.info("🔗 No parent trace context (standalone agent run)")

    tracer = trace.get_tracer("echomind.agent", "0.1.0")
    logger.info(f"📡 Telemetry telemetry initialized (endpoint: {endpoint})")

    return tracer, _parent_context


def get_parent_context() -> context.Context | None:
    """
    Get the parent trace context extracted from TRACEPARENT.

    Returns:
        The parent context, or None if no TRACEPARENT was provided.
    """
    return _parent_context


def get_provider() -> TracerProvider | None:
    """
    Get the TracerProvider instance.

    Returns:
        The TracerProvider, or None if not initialized.
    """
    return _provider


def shutdown_telemetry() -> None:
    """
    Flush all pending spans and shut down the TracerProvider.

    MUST be called before the sandbox container exits, ideally in a
    finally block or atexit handler. Uses a 10-second timeout to ensure
    all spans are exported even if the collector is slow.

    This is critical for ephemeral containers -- if not called, pending
    spans in the BatchSpanProcessor queue will be lost.
    """
    global _provider

    if _provider is None:
        return

    try:
        _provider.force_flush(timeout_millis=10_000)
        _provider.shutdown()
        logger.info("📡 Telemetry telemetry flushed and shut down")
    except Exception as e:
        logger.warning(f"⚠️ Telemetry shutdown error (spans may be lost): {e}")
    finally:
        _provider = None
```

#### 15.2.3 Module: `src/agent/observability/middleware.py`

Two middleware classes that integrate into the existing `BasicAgentWrapper` middleware chain alongside `ToolPolicyMiddleware` and `PathRestrictionMiddleware`.

```python
"""
Observability middleware for agent instrumentation.

Provides two middleware classes:
- ObservabilityMiddleware (ChatMiddleware): Records Telemetry spans for each LLM call
- ToolObservabilityMiddleware (FunctionMiddleware): Records Telemetry spans for each tool call

These integrate into the agent_framework middleware chain alongside
ToolPolicyMiddleware and PathRestrictionMiddleware.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from agent_framework import (
    ChatContext,
    ChatMiddleware,
    FunctionInvocationContext,
    FunctionMiddleware,
)
from observability import context, trace
from observability.trace import StatusCode

logger = logging.getLogger(__name__)


class ObservabilityMiddleware(ChatMiddleware):
    """
    Records Telemetry spans for each LLM call in the agent loop.

    Creates a span following Observability GenAI semantic conventions
    for every chat completion request. Captures model, temperature,
    token usage, and finish reason.

    Span name format: "chat {model}" (per GenAI semconv).

    Args:
        tracer: Observability tracer instance.
        parent_context: Optional parent context for trace propagation.
    """

    def __init__(
        self,
        tracer: trace.Tracer,
        parent_context: context.Context | None = None,
    ) -> None:
        """
        Initialize observability middleware.

        Args:
            tracer: Observability tracer instance from init_agent_telemetry().
            parent_context: Parent context from TRACEPARENT propagation.
        """
        self.tracer = tracer
        self.parent_context = parent_context
        self._call_count = 0

    async def process(self, context_: ChatContext, call_next: Any) -> None:
        """
        Wrap each LLM call with an Telemetry span.

        Captures:
        - gen_ai.operation.name: "chat"
        - gen_ai.request.model: model name
        - gen_ai.request.temperature: if set
        - gen_ai.usage.input_tokens: prompt tokens
        - gen_ai.usage.output_tokens: completion tokens
        - gen_ai.response.finish_reasons: completion finish reason

        Args:
            context_: Chat context containing options with model, temperature.
            call_next: Callable to invoke the next middleware or LLM.
        """
        self._call_count += 1
        model = context_.options.get("model", "unknown") if context_.options else "unknown"

        span_context = self.parent_context if self._call_count == 1 else None

        with self.tracer.start_as_current_span(
            f"chat {model}",
            context=span_context,
            attributes={
                "gen_ai.operation.name": "chat",
                "gen_ai.request.model": model,
                "echomind.agent.llm_call_index": self._call_count,
            },
        ) as span:
            # Capture optional request attributes
            if context_.options:
                temperature = context_.options.get("temperature")
                if temperature is not None:
                    span.set_attribute("gen_ai.request.temperature", temperature)
                max_tokens = context_.options.get("max_tokens")
                if max_tokens is not None:
                    span.set_attribute("gen_ai.request.max_tokens", max_tokens)

            start = time.monotonic()

            try:
                await call_next()
            except Exception as e:
                span.set_status(StatusCode.ERROR, str(e))
                span.set_attribute("error.type", type(e).__name__)
                raise
            finally:
                duration = time.monotonic() - start
                span.set_attribute("echomind.llm.duration_ms", int(duration * 1000))

            # Extract usage from response if available
            if hasattr(context_, "response") and context_.response:
                usage = getattr(context_.response, "usage", None)
                if usage:
                    input_tokens = getattr(usage, "prompt_tokens", 0)
                    output_tokens = getattr(usage, "completion_tokens", 0)
                    span.set_attribute("gen_ai.usage.input_tokens", input_tokens)
                    span.set_attribute("gen_ai.usage.output_tokens", output_tokens)

                finish_reason = getattr(context_.response, "finish_reason", None)
                if finish_reason:
                    span.set_attribute(
                        "gen_ai.response.finish_reasons",
                        json.dumps([finish_reason]),
                    )

            span.set_status(StatusCode.OK)


class ToolObservabilityMiddleware(FunctionMiddleware):
    """
    Records Telemetry spans for each tool invocation.

    Creates a span following Observability GenAI semantic conventions
    for every tool call. Captures tool name, duration, result size,
    and source (native vs MCP).

    Span name format: "execute_tool {tool_name}" (per GenAI semconv).

    Args:
        tracer: Observability tracer instance.
    """

    def __init__(self, tracer: trace.Tracer) -> None:
        """
        Initialize tool observability middleware.

        Args:
            tracer: Observability tracer instance from init_agent_telemetry().
        """
        self.tracer = tracer

    async def process(
        self,
        context_: FunctionInvocationContext,
        call_next: Callable[[], Awaitable[None]],
    ) -> None:
        """
        Wrap each tool call with an Telemetry span.

        Captures:
        - gen_ai.operation.name: "execute_tool"
        - gen_ai.tool.name: tool function name
        - gen_ai.tool.type: "function"
        - echomind.tool.duration_ms: execution time
        - echomind.tool.result_length: output size
        - gen_ai.tool.call.result: truncated result (max 1000 chars)

        Args:
            context_: Function invocation context with function name and args.
            call_next: Callable to invoke the next middleware or tool execution.
        """
        tool_name = context_.function.name

        # Determine source: native tool or MCP
        source = "native"
        mcp_server = ""
        if hasattr(context_.function, "metadata"):
            metadata = context_.function.metadata or {}
            source = metadata.get("source", "native")
            mcp_server = metadata.get("mcp_server", "")

        with self.tracer.start_as_current_span(
            f"execute_tool {tool_name}",
            attributes={
                "gen_ai.operation.name": "execute_tool",
                "gen_ai.tool.name": tool_name,
                "gen_ai.tool.type": "function",
                "echomind.tool.source": source,
                "echomind.tool.mcp_server": mcp_server,
            },
        ) as span:
            start = time.monotonic()

            try:
                await call_next()
            except Exception as e:
                span.set_status(StatusCode.ERROR, str(e))
                span.set_attribute("error.type", type(e).__name__)
                raise
            finally:
                duration = time.monotonic() - start
                span.set_attribute(
                    "echomind.tool.duration_ms", int(duration * 1000)
                )

            # Capture result metadata
            if context_.result is not None:
                result_str = str(context_.result)
                span.set_attribute("echomind.tool.result_length", len(result_str))

                # Truncate result for span attribute (safety + size limit)
                if len(result_str) > 1000:
                    result_str = result_str[:1000] + "..."
                span.set_attribute("gen_ai.tool.call.result", result_str)

            span.set_status(StatusCode.OK)
```

#### 15.2.4 Module: `src/agent/observability/metrics.py`

Telemetry SDK metrics for push-based export from ephemeral containers.

```python
"""
Agent metrics collection via Observability SDK.

Ephemeral sandbox containers cannot be scraped by Prometheus, so metrics
are pushed via trace to the Telemetry Collector, which forwards them to
Prometheus via its trace receiver.

For long-lived services (API, MCP gateway), use prometheus_client with
pull-based /metrics endpoint instead.
"""

from __future__ import annotations

import logging
import os

from observability import metrics
from observability.sdk.metrics import MeterProvider
from observability.sdk.metrics.export import PeriodicExportingMetricReader
from observability.exporter.trace.proto.http.metric_exporter import traceMetricExporter
from observability.sdk.resources import Resource

logger = logging.getLogger(__name__)

# Module-level state
_meter_provider: MeterProvider | None = None


class AgentMetrics:
    """
    Container for agent observability metrics.

    All metrics use the `echomind.agent` meter name and are exported
    via trace to the Telemetry Collector.

    Attributes:
        run_duration: Histogram of agent run durations in seconds.
        tool_calls: Counter of tool calls by name and status.
        tool_duration: Histogram of tool call durations in seconds.
        tokens_total: Counter of tokens by model and direction.
        errors: Counter of agent errors by type.
        llm_calls: Counter of LLM calls per agent run.
    """

    def __init__(self, meter: metrics.Meter) -> None:
        """
        Initialize agent metrics instruments.

        Args:
            meter: Observability Meter instance.
        """
        self.run_duration = meter.create_histogram(
            name="echomind.agent.run.duration",
            description="Agent run duration in seconds",
            unit="s",
        )

        self.tool_calls = meter.create_counter(
            name="echomind.agent.tool.calls",
            description="Total tool calls by name and status",
            unit="{call}",
        )

        self.tool_duration = meter.create_histogram(
            name="echomind.agent.tool.duration",
            description="Tool call duration in seconds",
            unit="s",
        )

        self.tokens_total = meter.create_counter(
            name="echomind.agent.tokens",
            description="Total tokens consumed by direction and model",
            unit="{token}",
        )

        self.errors = meter.create_counter(
            name="echomind.agent.errors",
            description="Total agent errors by type",
            unit="{error}",
        )

        self.llm_calls = meter.create_counter(
            name="echomind.agent.llm.calls",
            description="Total LLM calls in agent loop",
            unit="{call}",
        )


def init_agent_metrics() -> AgentMetrics:
    """
    Initialize Telemetry metrics with trace push exporter.

    Reads Telemetry_EXPORTER_trace_ENDPOINT from environment.
    Metrics are exported every 10 seconds to the Telemetry Collector.

    Returns:
        AgentMetrics instance with all metric instruments.
    """
    global _meter_provider

    endpoint = os.getenv(
        "Telemetry_EXPORTER_trace_ENDPOINT", "http://telemetry-collector:4318"
    )

    exporter = traceMetricExporter(
        endpoint=f"{endpoint}/v1/metrics",
    )
    reader = PeriodicExportingMetricReader(
        exporter,
        export_interval_millis=10_000,
    )

    resource = Resource.create(
        {
            "service.name": os.getenv("Telemetry_SERVICE_NAME", "echomind-agent-sandbox"),
            "agent.run.id": os.getenv("AGENT_RUN_ID", ""),
        }
    )

    _meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[reader],
    )
    metrics.set_meter_provider(_meter_provider)

    meter = metrics.get_meter("echomind.agent", "0.1.0")
    logger.info("📊 Telemetry metrics initialized")

    return AgentMetrics(meter)


def shutdown_metrics() -> None:
    """
    Flush pending metrics and shut down the MeterProvider.

    Must be called before container exit to avoid metric loss.
    """
    global _meter_provider

    if _meter_provider is not None:
        try:
            _meter_provider.force_flush(timeout_millis=10_000)
            _meter_provider.shutdown()
            logger.info("📊 Telemetry metrics flushed and shut down")
        except Exception as e:
            logger.warning(f"⚠️ Telemetry metrics shutdown error: {e}")
        finally:
            _meter_provider = None
```

#### 15.2.5 Module: `src/agent/observability/context.py`

Log correlation filter for injecting trace context into structured logs.

```python
"""
Trace context correlation for agent logs.

Injects Telemetry trace_id and span_id into Python log records so that
Alloy (log collector) can correlate logs with traces in Grafana.

Usage:
    from agent.observability.context import TraceContextFilter

    handler = logging.StreamHandler()
    handler.addFilter(TraceContextFilter())
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
"""

from __future__ import annotations

import logging

from observability import trace


class TraceContextFilter(logging.Filter):
    """
    Inject Telemetry trace/span IDs into log records.

    Enables Grafana Loki -> trace correlation: clicking a log line
    opens the corresponding trace in Langfuse or Tempo.

    Adds these fields to every log record:
    - trace_id: 32-char hex string (or zeros if no active span)
    - span_id: 16-char hex string (or zeros if no active span)
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """
        Add trace context fields to the log record.

        Args:
            record: The log record to enrich.

        Returns:
            Always True (never filters out records).
        """
        span = trace.get_current_span()
        ctx = span.get_span_context()

        if ctx and ctx.is_valid:
            record.trace_id = format(ctx.trace_id, "032x")  # type: ignore[attr-defined]
            record.span_id = format(ctx.span_id, "016x")  # type: ignore[attr-defined]
        else:
            record.trace_id = "0" * 32  # type: ignore[attr-defined]
            record.span_id = "0" * 16  # type: ignore[attr-defined]

        return True


# Log format with trace context for agent sandbox containers
LOG_FORMAT = (
    "%(asctime)s - %(levelname)s - %(name)s - "
    "trace_id=%(trace_id)s span_id=%(span_id)s - %(message)s"
)
```

#### 15.2.6 TRACEPARENT Injection in Container Spawner

When the API service creates a sandbox container, it must inject the trace context. This code goes in `src/api/sandbox/manager.py` (Phase 4 deliverable):

```python
# In SandboxManager.assign() or _create_container()
from observability import trace

def _build_container_env(
    self,
    run_id: str,
    user_id: str,
    session_id: str,
    agent_config: dict[str, Any],
) -> dict[str, str]:
    """
    Build environment variables for a sandbox container.

    Includes Telemetry trace context propagation via TRACEPARENT.

    Args:
        run_id: Unique agent run identifier.
        user_id: User who initiated the run.
        session_id: Chat session identifier.
        agent_config: Agent configuration dict.

    Returns:
        Dict of environment variables for the container.
    """
    env = {
        "AGENT_RUN_ID": run_id,
        "AGENT_USER_ID": user_id,
        "AGENT_SESSION_ID": session_id,
        "Telemetry_EXPORTER_trace_ENDPOINT": "http://telemetry-collector:4318",
        "Telemetry_SERVICE_NAME": "echomind-agent-sandbox",
    }

    # Propagate W3C Trace Context
    span = trace.get_current_span()
    ctx = span.get_span_context()
    if ctx.is_valid:
        traceparent = (
            f"00-{format(ctx.trace_id, '032x')}-"
            f"{format(ctx.span_id, '016x')}-01"
        )
        env["TRACEPARENT"] = traceparent

    return env
```

#### 15.2.7 Integration in BasicAgentWrapper

Modify `src/agent/agent.py` `__init__` to wire observability middleware into the middleware chain:

```python
# In BasicAgentWrapper.__init__(), after existing middleware setup:

# Observability middleware (optional, enabled when Telemetry endpoint is set)
if os.getenv("Telemetry_EXPORTER_trace_ENDPOINT"):
    from .observability import (
        init_agent_telemetry,
        ObservabilityMiddleware,
        ToolObservabilityMiddleware,
    )
    tracer, parent_ctx = init_agent_telemetry()
    # Add BEFORE policy middleware so spans capture the full call
    self._chat_middlewares.insert(0, ObservabilityMiddleware(tracer, parent_ctx))
    self._function_middlewares.insert(0, ToolObservabilityMiddleware(tracer))
    logger.info("📡 Observability middleware enabled")
```

#### 15.2.8 Langfuse Attribute Mapping on Root Span

Set Langfuse-specific attributes on the root `invoke_agent` span so traces appear correctly in the Langfuse UI with user/session correlation:

```python
# In the agent run entry point, after creating the root span:
root_span.set_attribute("langfuse.trace.name", f"agent-run:{agent_config.id}")
root_span.set_attribute("langfuse.user.id", user_id)
root_span.set_attribute("langfuse.session.id", session_id)
root_span.set_attribute("langfuse.trace.tags", json.dumps(["agent", agent_config.id]))
```

These attributes map to Langfuse fields via the Telemetry-to-Langfuse property mapping [Source: Langfuse Observability Integration -- 2025](https://langfuse.com/integrations/native/observability):

| Telemetry Attribute | Langfuse Field | Notes |
|----------------|---------------|-------|
| `langfuse.trace.name` | Trace name | Displayed in trace list |
| `langfuse.user.id` | User ID | Enables per-user filtering |
| `langfuse.session.id` | Session ID | Groups traces by session |
| `langfuse.trace.tags` | Tags | JSON array of strings |
| `gen_ai.request.model` | Model | Auto-detects "generation" type |
| `gen_ai.usage.input_tokens` | Input tokens | Token counting |
| `gen_ai.usage.output_tokens` | Output tokens | Token counting |
| `langfuse.observation.cost_details` | Cost breakdown | JSON: `{"input": 0.001, "output": 0.002}` |

---

### 15.3 MCP Gateway Instrumentation

#### 15.3.1 FastMCP Middleware for Tracing

The MCP gateway is a long-lived service, so it uses `prometheus_client` for pull-based metrics (at `/metrics`) and Telemetry spans for traces.

Add to `src/mcp_gateway/middleware/tracing.py`:

```python
"""
Telemetry tracing middleware for FastMCP server.

Wraps every MCP tool call with an Telemetry span, capturing:
- Tool name and server context
- Input/output sizes
- Duration and success/failure status
- Trace context propagation from incoming MCP requests

This middleware is registered as a FastMCP server middleware and
runs on every incoming tool call request.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from observability import trace
from observability.trace import StatusCode

logger = logging.getLogger(__name__)

# Tracer for MCP gateway spans
_tracer: trace.Tracer | None = None


def get_tracer() -> trace.Tracer:
    """
    Get or create the MCP gateway tracer.

    Returns:
        Observability tracer for MCP gateway instrumentation.
    """
    global _tracer
    if _tracer is None:
        _tracer = trace.get_tracer("echomind.mcp_gateway", "0.1.0")
    return _tracer


async def tracing_middleware(
    tool_name: str,
    arguments: dict[str, Any],
    call_next: Any,
) -> Any:
    """
    FastMCP middleware that wraps tool calls with Telemetry spans.

    Creates a span for each MCP tool invocation with GenAI semantic
    convention attributes. Propagates trace context from the incoming
    request headers.

    Args:
        tool_name: Name of the MCP tool being called.
        arguments: Tool call arguments.
        call_next: Next middleware or tool handler.

    Returns:
        Tool call result.

    Raises:
        Exception: Re-raises any exception from the tool handler.
    """
    tracer = get_tracer()

    # Estimate input size for span attributes
    input_size = len(json.dumps(arguments, default=str))

    with tracer.start_as_current_span(
        f"mcp_tool {tool_name}",
        attributes={
            "gen_ai.operation.name": "execute_tool",
            "gen_ai.tool.name": tool_name,
            "gen_ai.tool.type": "function",
            "echomind.tool.source": "mcp",
            "echomind.mcp.input_size_bytes": input_size,
        },
    ) as span:
        start = time.monotonic()

        try:
            result = await call_next()

            # Capture output size
            output_str = str(result) if result is not None else ""
            span.set_attribute(
                "echomind.mcp.output_size_bytes", len(output_str)
            )

            span.set_status(StatusCode.OK)
            return result

        except Exception as e:
            span.set_status(StatusCode.ERROR, str(e))
            span.set_attribute("error.type", type(e).__name__)
            raise

        finally:
            duration = time.monotonic() - start
            span.set_attribute(
                "echomind.tool.duration_ms", int(duration * 1000)
            )
```

#### 15.3.2 MCP Gateway Prometheus Metrics

Add to `src/mcp_gateway/middleware/metrics.py` (pull-based for long-lived service):

```python
"""
Prometheus metrics for MCP gateway.

Exposed at /metrics for Prometheus scrape. These are pull-based metrics
for the long-lived MCP gateway service (not pushed via trace like sandbox metrics).
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

# MCP tool call metrics
mcp_tool_calls_total = Counter(
    "echomind_mcp_tool_calls_total",
    "Total MCP tool calls",
    ["tool_name", "status"],  # status: success/error/denied
)

mcp_tool_call_duration_seconds = Histogram(
    "echomind_mcp_tool_call_duration_seconds",
    "MCP tool call duration in seconds",
    ["tool_name"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)

mcp_active_connections = Gauge(
    "echomind_mcp_active_connections",
    "Currently connected MCP clients",
    ["transport"],  # stdio/http/websocket
)

mcp_request_duration_seconds = Histogram(
    "echomind_mcp_request_duration_seconds",
    "MCP request duration including all middleware",
    ["method"],  # tools/list, tools/call, resources/list, etc.
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 5.0),
)

mcp_skill_executions_total = Counter(
    "echomind_mcp_skill_executions_total",
    "Total skill subprocess executions",
    ["skill_name", "status"],  # status: success/error/timeout
)
```

---

### 15.4 Complete Metrics Definition

#### 15.4.1 Sandbox Container Metrics (trace Push)

These metrics are emitted by ephemeral containers via the Telemetry SDK and pushed to the Telemetry Collector, which forwards them to Prometheus.

| Metric Name | Type | Labels | Description |
|-------------|------|--------|-------------|
| `echomind.agent.run.duration` | Histogram | agent_id, model | Agent run duration in seconds |
| `echomind.agent.tool.calls` | Counter | tool_name, source, status | Tool calls by name, source (native/mcp), status (success/error/denied) |
| `echomind.agent.tool.duration` | Histogram | tool_name, source | Tool call duration in seconds |
| `echomind.agent.tokens` | Counter | model, direction | Tokens consumed (direction: input/output) |
| `echomind.agent.errors` | Counter | error_type | Agent errors by exception type |
| `echomind.agent.llm.calls` | Counter | agent_id, model | LLM calls in agent loop |

#### 15.4.2 API Service Metrics (Prometheus Pull)

Added to `src/api/middleware/metrics.py` alongside existing RAGAS metrics.

| Metric Name | Type | Labels | Description |
|-------------|------|--------|-------------|
| `echomind_agent_runs_total` | Counter | agent_id, model, status | Total agent runs started |
| `echomind_agent_run_duration_seconds` | Histogram | agent_id, model | End-to-end agent run duration |
| `echomind_agent_active_runs` | Gauge | agent_id | Currently executing agent runs |
| `echomind_sandbox_pool_size` | Gauge | state | Sandbox pool by state (warm/assigned/active/draining) |
| `echomind_agent_run_cost_usd_total` | Counter | agent_id, model | Estimated USD cost of agent runs |
| `echomind_agent_run_cost_per_user_usd_total` | Counter | user_id | Estimated USD cost per user |

#### 15.4.3 MCP Gateway Metrics (Prometheus Pull)

Defined in section 15.3.2 above.

| Metric Name | Type | Labels | Description |
|-------------|------|--------|-------------|
| `echomind_mcp_tool_calls_total` | Counter | tool_name, status | Total MCP tool calls |
| `echomind_mcp_tool_call_duration_seconds` | Histogram | tool_name | MCP tool call duration |
| `echomind_mcp_active_connections` | Gauge | transport | Connected MCP clients |
| `echomind_mcp_request_duration_seconds` | Histogram | method | MCP request duration |
| `echomind_mcp_skill_executions_total` | Counter | skill_name, status | Skill subprocess executions |

#### 15.4.4 API Service Metrics Registration Code

Add to `src/api/middleware/metrics.py`:

```python
# ============================================
# Agent Sandbox Metrics (pull-based, API side)
# ============================================

echomind_agent_runs_total = Counter(
    "echomind_agent_runs_total",
    "Total agent runs",
    ["agent_id", "model", "status"],  # status: success/error/cancelled
)

echomind_agent_run_duration_seconds = Histogram(
    "echomind_agent_run_duration_seconds",
    "Agent run duration in seconds",
    ["agent_id", "model"],
    buckets=(0.5, 1, 2, 5, 10, 30, 60, 120, 300),
)

echomind_agent_active_runs = Gauge(
    "echomind_agent_active_runs",
    "Currently active agent runs",
    ["agent_id"],
)

echomind_sandbox_pool_size = Gauge(
    "echomind_sandbox_pool_size",
    "Sandbox container pool size by state",
    ["state"],  # warm/assigned/active/draining
)

echomind_agent_run_tokens_total = Counter(
    "echomind_agent_run_tokens_total",
    "Total tokens consumed by agent runs",
    ["agent_id", "model", "token_type"],  # token_type: input/output
)

echomind_agent_run_cost_usd_total = Counter(
    "echomind_agent_run_cost_usd_total",
    "Estimated USD cost of agent runs",
    ["agent_id", "model"],
)

echomind_agent_run_cost_per_user_usd_total = Counter(
    "echomind_agent_run_cost_per_user_usd_total",
    "Estimated USD cost per user",
    ["user_id"],
)
```

---

### 15.5 Grafana Dashboards — Implementation

All dashboards are provisioned as code via the existing Grafana dashboard provisioning system. Files are placed in `config/observability/grafana/dashboards/` and auto-loaded by Grafana.

#### 15.5.1 Dashboard: Agent Runs Overview

**File:** `config/observability/grafana/dashboards/agent-runs.json`

**PromQL queries for each panel:**

```yaml
panels:
  - title: "Agent Runs Rate"
    type: timeseries
    query: 'sum(rate(echomind_agent_runs_total[5m])) by (agent_id)'
    description: "Agent runs per second, grouped by agent"

  - title: "Agent Run Duration (P50/P95/P99)"
    type: heatmap
    queries:
      - 'histogram_quantile(0.50, sum(rate(echomind_agent_run_duration_seconds_bucket[5m])) by (le))'
      - 'histogram_quantile(0.95, sum(rate(echomind_agent_run_duration_seconds_bucket[5m])) by (le))'
      - 'histogram_quantile(0.99, sum(rate(echomind_agent_run_duration_seconds_bucket[5m])) by (le))'
    description: "Latency distribution heatmap"

  - title: "Active Runs"
    type: gauge
    query: 'sum(echomind_agent_active_runs)'
    description: "Currently executing agent runs"

  - title: "Error Rate"
    type: timeseries
    query: |
      sum(rate(echomind_agent_runs_total{status="error"}[5m]))
      / sum(rate(echomind_agent_runs_total[5m]))
    description: "Error percentage over 5-minute window"

  - title: "Top 10 Tools"
    type: barchart
    query: 'topk(10, sum by (tool_name) (echomind_mcp_tool_calls_total))'
    description: "Most-used tools across all agents"

  - title: "Token Usage Rate"
    type: timeseries
    query: 'sum(rate(echomind_agent_run_tokens_total[5m])) by (token_type)'
    description: "Input vs output token rate"

  - title: "Estimated Daily Cost"
    type: stat
    query: 'sum(increase(echomind_agent_run_cost_usd_total[24h]))'
    unit: "currencyUSD"
    description: "Estimated cost in last 24 hours"

  - title: "Telemetry Collector Health"
    type: stat
    query: 'up{job="telemetry-collector"}'
    description: "Collector scrape target status"
```

#### 15.5.2 Dashboard: Sandbox Health

**File:** `config/observability/grafana/dashboards/sandbox-health.json`

```yaml
panels:
  - title: "Sandbox Pool Distribution"
    type: piechart
    query: 'echomind_sandbox_pool_size'
    description: "Containers by state: warm/assigned/active/draining"

  - title: "Pool Size Over Time"
    type: timeseries
    query: 'echomind_sandbox_pool_size'
    description: "Pool state changes over time"

  - title: "Container CPU Usage"
    type: timeseries
    query: |
      sum(rate(container_cpu_usage_seconds_total{
        name=~"sandbox-.*"
      }[5m])) by (name)
    description: "CPU usage per sandbox container (from cAdvisor)"

  - title: "Container Memory Usage"
    type: timeseries
    query: |
      container_memory_usage_bytes{name=~"sandbox-.*"}
      / container_spec_memory_limit_bytes{name=~"sandbox-.*"}
    description: "Memory usage as % of limit per sandbox"

  - title: "Container Network I/O"
    type: timeseries
    queries:
      - 'sum(rate(container_network_receive_bytes_total{name=~"sandbox-.*"}[5m]))'
      - 'sum(rate(container_network_transmit_bytes_total{name=~"sandbox-.*"}[5m]))'
    description: "Network bytes in/out for sandbox containers"

  - title: "Container Lifecycle Events"
    type: timeseries
    query: |
      sum(rate(echomind_agent_runs_total[5m])) by (status)
    description: "Container creation/destruction rate"
```

#### 15.5.3 Dashboard: Cost Tracking

**File:** `config/observability/grafana/dashboards/agent-cost.json`

```yaml
panels:
  - title: "Daily Cost Trend"
    type: timeseries
    query: 'sum(increase(echomind_agent_run_cost_usd_total[1d]))'
    unit: "currencyUSD"

  - title: "Cost by Model"
    type: barchart
    query: 'sum by (model) (increase(echomind_agent_run_cost_usd_total[1d]))'
    unit: "currencyUSD"

  - title: "Cost by Agent"
    type: barchart
    query: 'sum by (agent_id) (increase(echomind_agent_run_cost_usd_total[1d]))'
    unit: "currencyUSD"

  - title: "Top 20 Users by Spend (30d)"
    type: table
    query: |
      topk(20, sum by (user_id) (
        increase(echomind_agent_run_cost_per_user_usd_total[30d])
      ))
    unit: "currencyUSD"

  - title: "Token Efficiency (Output/Input Ratio)"
    type: stat
    query: |
      sum(rate(echomind_agent_run_tokens_total{token_type="output"}[1h]))
      / sum(rate(echomind_agent_run_tokens_total{token_type="input"}[1h]))

  - title: "30-Day Cost Projection"
    type: stat
    query: 'sum(increase(echomind_agent_run_cost_usd_total[7d])) * 4.3'
    unit: "currencyUSD"
    description: "Extrapolated from last 7 days"
```

#### 15.5.4 Dashboard Provisioning

No changes needed to the existing provisioning config. Dashboards placed in `config/observability/grafana/dashboards/` are auto-loaded by the existing `dashboards.yml` provisioner, which maps the directory to `/var/lib/grafana/dashboards` in the Grafana container.

---

### 15.6 Alerting Rules — Prometheus

#### 15.6.1 Alert Rules File

**File:** `config/observability/prometheus/rules/agent-alerts.yml`

```yaml
# ============================================
# EchoMind Agent Alerting Rules
# ============================================
groups:
  - name: echomind-agent-health
    interval: 30s
    rules:
      # --- Error Rate ---
      - alert: AgentHighErrorRate
        expr: |
          (
            sum(rate(echomind_agent_runs_total{status="error"}[5m]))
            / sum(rate(echomind_agent_runs_total[5m]))
          ) > 0.05
        for: 5m
        labels:
          severity: warning
          team: echomind
        annotations:
          summary: "Agent error rate above 5% for 5 minutes"
          description: |
            Agent error rate is {{ $value | humanizePercentage }}.
            Check Langfuse traces for error details.
          dashboard: "/d/agent-runs/agent-runs-overview"

      # --- Latency Spike ---
      - alert: AgentLatencySpike
        expr: |
          histogram_quantile(0.95,
            sum(rate(echomind_agent_run_duration_seconds_bucket[5m])) by (le)
          ) > 30
        for: 10m
        labels:
          severity: warning
          team: echomind
        annotations:
          summary: "Agent P95 latency above 30 seconds"
          description: |
            P95 agent run duration is {{ $value | humanizeDuration }}.
            May indicate slow LLM responses or tool timeouts.

      # --- Sandbox Pool Exhaustion ---
      - alert: SandboxPoolExhaustion
        expr: echomind_sandbox_pool_size{state="warm"} < 2
        for: 2m
        labels:
          severity: critical
          team: echomind
        annotations:
          summary: "Sandbox warm pool below 2 containers"
          description: |
            Only {{ $value }} warm containers available.
            New agent sessions may experience cold start delays (~1.5s).

      # --- MCP Gateway Disconnection ---
      - alert: MCPGatewayDown
        expr: up{job="echomind-mcp"} == 0
        for: 2m
        labels:
          severity: critical
          team: echomind
        annotations:
          summary: "MCP gateway is unreachable"
          description: |
            The MCP gateway has been down for 2 minutes.
            All agent tool calls will fail.

      # --- Telemetry Collector Down ---
      - alert: TelemetryCollectorDown
        expr: up{job="telemetry-collector"} == 0
        for: 2m
        labels:
          severity: warning
          team: echomind
        annotations:
          summary: "Telemetry Collector is unreachable"
          description: |
            Agent telemetry is not being collected.
            Traces and metrics from sandbox containers will be lost.

      # --- Cost Threshold ---
      - alert: AgentDailyCostHigh
        expr: sum(increase(echomind_agent_run_cost_usd_total[24h])) > 50
        for: 1h
        labels:
          severity: warning
          team: echomind
        annotations:
          summary: "Agent daily cost exceeds $50"
          description: |
            Estimated cost in last 24h: ${{ $value | humanize }}.
            Review cost dashboard for breakdown by model and user.
          dashboard: "/d/agent-cost/agent-cost-analysis"

      # --- High MCP Error Rate ---
      - alert: MCPHighErrorRate
        expr: |
          (
            sum(rate(echomind_mcp_tool_calls_total{status="error"}[5m]))
            / sum(rate(echomind_mcp_tool_calls_total[5m]))
          ) > 0.1
        for: 5m
        labels:
          severity: warning
          team: echomind
        annotations:
          summary: "MCP tool call error rate above 10%"
          description: |
            MCP error rate: {{ $value | humanizePercentage }}.
            Check MCP gateway logs for specific tool failures.
```

#### 15.6.2 Prometheus Configuration Update

Add the rules file reference to `config/observability/prometheus/prometheus.yml`:

```yaml
# Add at the top level, after global:
rule_files:
  - /etc/prometheus/rules/*.yml
```

Update the Docker Compose volume mount for Prometheus to include the rules directory:

```yaml
  prometheus:
    volumes:
      - ${CONFIG_PATH}/observability/prometheus/prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - ${CONFIG_PATH}/observability/prometheus/rules:/etc/prometheus/rules:ro  # NEW
      - prometheus_data:/prometheus
```

#### 15.6.3 Alertmanager Service (Optional)

If alerts should route to Slack/email, add Alertmanager to `docker-compose-observability.yml`:

```yaml
  # ============================================
  # ALERTMANAGER (Optional — for Slack/email routing)
  # ============================================
  alertmanager:
    image: prom/alertmanager:v0.28.1
    container_name: observability-alertmanager
    profiles: ["observability"]
    volumes:
      - ${CONFIG_PATH}/observability/alertmanager/alertmanager.yml:/etc/alertmanager/alertmanager.yml:ro
    command:
      - "--config.file=/etc/alertmanager/alertmanager.yml"
      - "--storage.path=/alertmanager"
    healthcheck:
      test: ["CMD", "wget", "--spider", "-q", "http://localhost:9093/-/healthy"]
      interval: 15s
      timeout: 5s
      retries: 3
    restart: unless-stopped
    networks:
      - backend
    labels:
      - "traefik.enable=false"
```

And add the Alertmanager target to `prometheus.yml`:

```yaml
# Add at the top level, after rule_files:
alerting:
  alertmanagers:
    - static_configs:
        - targets: ["alertmanager:9093"]
```

**Alertmanager config** (`config/observability/alertmanager/alertmanager.yml`):

```yaml
global:
  resolve_timeout: 5m

route:
  receiver: "default"
  group_by: ["alertname", "team"]
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h

  routes:
    - match:
        severity: critical
      receiver: "critical"
      repeat_interval: 1h

receivers:
  - name: "default"
    # Configure webhook, Slack, or email receiver here
    # webhook_configs:
    #   - url: "http://example.com/webhook"

  - name: "critical"
    # Critical alerts with shorter repeat interval
    # slack_configs:
    #   - channel: "#echomind-alerts"
    #     send_resolved: true
```

---

### 15.7 File-by-File Implementation Plan

#### 15.7.1 New Files

| File | Purpose | Key Classes/Functions |
|------|---------|----------------------|
| `config/observability/telemetry-collector/config.yaml` | Telemetry Collector configuration | receivers, processors, exporters, pipelines |
| `config/observability/prometheus/rules/agent-alerts.yml` | Prometheus alerting rules | 7 alert rules |
| `config/observability/alertmanager/alertmanager.yml` | Alertmanager routing config | routes, receivers |
| `src/agent/observability/__init__.py` | Package exports | Re-exports all public symbols |
| `src/agent/observability/telemetry.py` | Telemetry trace provider init | `init_agent_telemetry()`, `shutdown_telemetry()`, `get_provider()` |
| `src/agent/observability/middleware.py` | Agent middleware | `ObservabilityMiddleware`, `ToolObservabilityMiddleware` |
| `src/agent/observability/metrics.py` | Telemetry metrics for sandboxes | `AgentMetrics`, `init_agent_metrics()`, `shutdown_metrics()` |
| `src/agent/observability/context.py` | Log-trace correlation | `TraceContextFilter`, `LOG_FORMAT` |
| `src/mcp_gateway/middleware/tracing.py` | MCP Telemetry tracing | `tracing_middleware()`, `get_tracer()` |
| `src/mcp_gateway/middleware/metrics.py` | MCP Prometheus metrics | 5 metric instruments |
| `config/observability/grafana/dashboards/agent-runs.json` | Agent overview dashboard | 8 panels |
| `config/observability/grafana/dashboards/sandbox-health.json` | Sandbox health dashboard | 6 panels |
| `config/observability/grafana/dashboards/agent-cost.json` | Cost analysis dashboard | 6 panels |
| `tests/unit/agent/observability/test_telemetry.py` | Telemetry init tests | 6 tests |
| `tests/unit/agent/observability/test_middleware.py` | Middleware tests | 10 tests |
| `tests/unit/agent/observability/test_metrics.py` | Metrics tests | 5 tests |
| `tests/unit/agent/observability/test_context.py` | Log correlation tests | 4 tests |
| `tests/unit/mcp_gateway/test_tracing.py` | MCP tracing tests | 5 tests |

#### 15.7.2 Modified Files

| File | Changes |
|------|---------|
| `deployment/docker-cluster/docker-compose-observability.yml` | Add `telemetry-collector` service, update Prometheus volumes for rules dir |
| `config/observability/prometheus/prometheus.yml` | Add `rule_files`, `alerting` section, `telemetry-collector` scrape job |
| `src/agent/agent.py` | Import and wire `ObservabilityMiddleware` + `ToolObservabilityMiddleware` |
| `src/api/middleware/metrics.py` | Add agent/sandbox Prometheus metrics (6 new instruments) |
| `.env.example` | Add `LANGFUSE_Telemetry_AUTH`, `DEPLOYMENT_ENVIRONMENT` |

#### 15.7.3 Dependencies (Pinned Versions)

**Agent sandbox container** (`src/sandbox/requirements.txt`):

```
observability-api==1.39.1
observability-sdk==1.39.1
observability-exporter-trace-proto-http==1.39.1
observability-semantic-conventions==0.50b0
```

**MCP gateway** (`src/mcp_gateway/requirements.txt` -- add to existing):

```
observability-api==1.39.1
observability-sdk==1.39.1
prometheus-client==0.21.1
```

**API service** (`src/api/requirements.txt` -- already has prometheus-client, add):

```
observability-api==1.39.1
observability-sdk==1.39.1
```

[Source: observability-sdk v1.39.1 on PyPI -- Dec 2025](https://pypi.org/project/observability-sdk/)

---

### 15.8 Test Plan

#### 15.8.1 `tests/unit/agent/observability/test_telemetry.py`

```python
"""Tests for agent observability telemetry initialization."""

# Test cases:
# 1. test_init_agent_telemetry_creates_provider
#    - Mock Telemetry SDK, verify TracerProvider created with correct resource attrs
#    - Verify BatchSpanProcessor configured with traceSpanExporter
#
# 2. test_init_agent_telemetry_with_traceparent
#    - Set TRACEPARENT env var, verify parent context extracted correctly
#    - Verify trace_id and span_id parsed from TRACEPARENT format
#
# 3. test_init_agent_telemetry_without_traceparent
#    - No TRACEPARENT env var, verify parent_context is None
#    - Verify standalone tracer still created
#
# 4. test_shutdown_telemetry_flushes_spans
#    - Create provider, call shutdown, verify force_flush called with 10s timeout
#    - Verify provider.shutdown() called
#
# 5. test_shutdown_telemetry_handles_errors
#    - Mock force_flush to raise, verify no exception propagated
#    - Verify warning logged
#
# 6. test_shutdown_telemetry_noop_when_not_initialized
#    - Call shutdown without init, verify no error
```

#### 15.8.2 `tests/unit/agent/observability/test_middleware.py`

```python
"""Tests for observability middleware."""

# Test cases:
# 1. test_observability_middleware_creates_chat_span
#    - Mock tracer, run middleware, verify span created with name "chat {model}"
#    - Verify gen_ai.operation.name = "chat"
#
# 2. test_observability_middleware_captures_token_usage
#    - Mock context.response.usage with prompt_tokens/completion_tokens
#    - Verify gen_ai.usage.input_tokens and output_tokens set
#
# 3. test_observability_middleware_handles_error
#    - Make call_next raise, verify span.set_status(ERROR) called
#    - Verify error.type attribute set
#    - Verify exception re-raised
#
# 4. test_observability_middleware_captures_temperature
#    - Set temperature in context.options, verify attribute set
#
# 5. test_tool_middleware_creates_tool_span
#    - Mock tracer, run middleware, verify span "execute_tool {name}"
#    - Verify gen_ai.tool.name set correctly
#
# 6. test_tool_middleware_captures_duration
#    - Run tool with known delay, verify echomind.tool.duration_ms set
#
# 7. test_tool_middleware_truncates_large_results
#    - Return result > 1000 chars, verify truncated with "..."
#    - Verify echomind.tool.result_length captures full length
#
# 8. test_tool_middleware_handles_mcp_source
#    - Set function.metadata.source = "mcp", verify echomind.tool.source = "mcp"
#
# 9. test_tool_middleware_handles_error
#    - Make call_next raise, verify span error status
#    - Verify exception re-raised
#
# 10. test_middleware_chain_integration
#     - Wire ObservabilityMiddleware + ToolObservabilityMiddleware
#     - Run a simulated agent step, verify parent-child span relationship
```

#### 15.8.3 `tests/unit/agent/observability/test_metrics.py`

```python
"""Tests for agent metrics collection."""

# Test cases:
# 1. test_init_agent_metrics_creates_instruments
#    - Call init_agent_metrics, verify all 6 metric instruments created
#
# 2. test_metrics_record_tool_call
#    - Record a tool call via AgentMetrics.tool_calls counter
#    - Verify counter incremented with correct labels
#
# 3. test_metrics_record_tokens
#    - Record token usage, verify counter incremented
#
# 4. test_shutdown_metrics_flushes
#    - Init metrics, shutdown, verify force_flush called
#
# 5. test_shutdown_metrics_noop_when_not_initialized
#    - Call shutdown without init, verify no error
```

#### 15.8.4 `tests/unit/agent/observability/test_context.py`

```python
"""Tests for trace context log correlation."""

# Test cases:
# 1. test_trace_context_filter_with_active_span
#    - Create a span, apply filter to log record
#    - Verify trace_id and span_id set on record
#
# 2. test_trace_context_filter_without_span
#    - No active span, apply filter
#    - Verify trace_id = "0"*32 and span_id = "0"*16
#
# 3. test_trace_context_filter_always_returns_true
#    - Verify filter never drops records
#
# 4. test_log_format_includes_trace_fields
#    - Format a log record with TraceContextFilter
#    - Verify output contains trace_id= and span_id=
```

#### 15.8.5 `tests/unit/mcp_gateway/test_tracing.py`

```python
"""Tests for MCP gateway tracing middleware."""

# Test cases:
# 1. test_tracing_middleware_creates_span
#    - Mock tracer, call tracing_middleware
#    - Verify span created with "mcp_tool {name}"
#
# 2. test_tracing_middleware_captures_input_output_size
#    - Pass known arguments, verify echomind.mcp.input_size_bytes set
#    - Return known result, verify echomind.mcp.output_size_bytes set
#
# 3. test_tracing_middleware_handles_error
#    - Make call_next raise, verify span error status
#    - Verify exception re-raised
#
# 4. test_tracing_middleware_captures_duration
#    - Run with known delay, verify echomind.tool.duration_ms
#
# 5. test_get_tracer_returns_singleton
#    - Call get_tracer twice, verify same instance returned
```

#### 15.8.6 Telemetry Collector Config Validation

The collector config can be validated without deploying:

```bash
# Pull collector image and validate config
docker run --rm \
  -v $(pwd)/config/observability/telemetry-collector/config.yaml:/etc/telemetrycol-contrib/config.yaml:ro \
  -e LANGFUSE_Telemetry_AUTH=dGVzdDp0ZXN0 \
  -e DEPLOYMENT_ENVIRONMENT=test \
  telemetry/observability-collector-contrib:0.118.0 \
  validate --config=/etc/telemetrycol-contrib/config.yaml
```

---

### 15.9 Alloy Log Correlation Update

To enable Grafana Loki -> trace correlation (click a log line, open the trace), update the Alloy config to parse `trace_id` from agent logs.

**Addition to `config/observability/alloy/config.alloy`:**

```alloy
// 4b. Extract trace context from agent logs
// Format: "... trace_id=<32hex> span_id=<16hex> ..."
stage.regex {
  expression = "trace_id=(?P<trace_id>[0-9a-f]{32}) span_id=(?P<span_id>[0-9a-f]{16})"
}

// Map trace_id to Loki label for Grafana derived fields
stage.labels {
  values = {
    trace_id = "",
  }
}
```

Then add a Grafana datasource derived field to link Loki logs to Langfuse traces. This can be configured in `config/observability/grafana/provisioning/datasources/datasources.yml`:

```yaml
  - name: Loki
    type: loki
    uid: loki
    access: proxy
    orgId: 1
    url: http://loki:3100
    isDefault: false
    editable: false
    version: 1
    jsonData:
      maxLines: 1000
      derivedFields:
        - name: TraceID
          matcherRegex: 'trace_id=(\w+)'
          url: '${LANGFUSE_BASE_URL}/traces/$${__value.raw}'
          datasourceUid: loki
```

---

### 15.10 Implementation Sequence

The implementation follows the phases defined in sections 12.1-12.5 of this document, with this detailed sequencing within Phase 6 (Observability):

| Step | Task | Depends On | Est. Hours |
|------|------|------------|------------|
| 6.1 | Create `config/observability/telemetry-collector/config.yaml` | -- | 1h |
| 6.2 | Add Telemetry Collector to `docker-compose-observability.yml` | 6.1 | 1h |
| 6.3 | Add Prometheus scrape job + rules file | 6.2 | 1h |
| 6.4 | Create `src/agent/observability/telemetry.py` | -- | 2h |
| 6.5 | Create `src/agent/observability/middleware.py` | 6.4 | 3h |
| 6.6 | Create `src/agent/observability/metrics.py` | 6.4 | 2h |
| 6.7 | Create `src/agent/observability/context.py` | 6.4 | 1h |
| 6.8 | Wire middleware into `BasicAgentWrapper` | 6.5 | 1h |
| 6.9 | Create `src/mcp_gateway/middleware/tracing.py` | 6.4 | 2h |
| 6.10 | Create `src/mcp_gateway/middleware/metrics.py` | -- | 1h |
| 6.11 | Add API-side metrics to `src/api/middleware/metrics.py` | -- | 1h |
| 6.12 | Create Grafana dashboards (3 JSON files) | 6.11 | 4h |
| 6.13 | Create alert rules + Alertmanager config | 6.3 | 2h |
| 6.14 | Update Alloy config for log-trace correlation | 6.7 | 1h |
| 6.15 | Write all unit tests (~30 tests) | 6.4-6.10 | 4h |
| 6.16 | Integration test: end-to-end trace validation | All | 2h |
| **Total** | | | **~27h** |

---

## 16. Citations and Sources

| Source | Date | URL |
|--------|------|-----|
| Observability Collector Configuration | Feb 2026 | [observability.io/docs/collector/configuration](https://observability.io/docs/collector/configuration/) |
| Collector Configuration Best Practices | Feb 2026 | [observability.io/docs/security/config-best-practices](https://observability.io/docs/security/config-best-practices/) |
| Observability Collector Architecture | Feb 2026 | [observability.io/docs/collector/architecture](https://observability.io/docs/collector/architecture/) |
| observability-sdk v1.39.1 (PyPI) | Dec 2025 | [pypi.org/project/observability-sdk](https://pypi.org/project/observability-sdk/) |
| observability-api v1.39.1 (PyPI) | Dec 2025 | [pypi.org/project/observability-api](https://pypi.org/project/observability-api/) |
| Observability Python SDK | Feb 2026 | [observability.io/docs/languages/python](https://observability.io/docs/languages/python/) |
| Langfuse Observability Integration | 2025 | [langfuse.com/integrations/native/observability](https://langfuse.com/integrations/native/observability) |
| Langfuse Telemetry-based Python SDK v3 | May 2025 | [langfuse.com/changelog/2025-05-23-telemetry-based-python-sdk](https://langfuse.com/changelog/2025-05-23-telemetry-based-python-sdk) |
| Langfuse Existing Telemetry Setup Guide | 2025 | [langfuse.com/faq/all/existing-telemetry-setup](https://langfuse.com/faq/all/existing-telemetry-setup) |
| W3C Trace Context Specification | 2024 | [w3.org/TR/trace-context](https://www.w3.org/TR/trace-context/) |
| W3C Trace Context Level 2 | 2024 | [w3.org/TR/trace-context-2](https://www.w3.org/TR/trace-context-2/) |
| Prometheus Alertmanager Docker Setup | Feb 2026 | [oneuptime.com/blog/post/2026-02-08-how-to-set-up-docker-container-alerting-with-alertmanager](https://oneuptime.com/blog/post/2026-02-08-how-to-set-up-docker-container-alerting-with-alertmanager/view) |
| Observability GenAI Agent Span Semantic Conventions | 2025 | [observability.io/docs/specs/semconv/gen-ai/gen-ai-agent-spans](https://observability.io/docs/specs/semconv/gen-ai/gen-ai-agent-spans/) |
| AI Agent Observability (Observability Blog) | 2025 | [observability.io/blog/2025/ai-agent-observability](https://observability.io/blog/2025/ai-agent-observability/) |
| Langfuse Observability Tracing Support | Feb 2025 | [langfuse.com/changelog/2025-02-14-observability-tracing](https://langfuse.com/changelog/2025-02-14-observability-tracing) |
| OpenLLMetry -- Open-source GenAI Observability | 2025 | [github.com/traceloop/openllmetry](https://github.com/traceloop/openllmetry) |

---

## 17. Evaluation Scorecard

| Criterion | Score (1-10) | Notes |
|-----------|:---:|-------|
| **Trace Context Propagation** | 9 | W3C TRACEPARENT via env var is simple and reliable; covers API -> sandbox -> MCP. Loses context only if Telemetry_EXPORTER_trace_ENDPOINT is unreachable. |
| **Ephemeral Container Telemetry** | 8 | Telemetry Collector buffers and fans out; BatchSpanProcessor + force_flush(10s) at shutdown covers most cases. Risk: container killed (SIGKILL) before flush completes. |
| **Cost Tracking Accuracy** | 7 | Model pricing is hardcoded and must be updated manually. Does not account for cached tokens, prompt caching, or provider-specific pricing tiers. Good enough for budgeting, not billing. |
| **Dashboard Actionability** | 8 | Three dashboards cover the main operational concerns (health, cost, sandbox). PromQL queries are straightforward. Missing: drill-down from Grafana to specific Langfuse trace. |
| **Alerting Coverage** | 8 | Seven alert rules cover error rate, latency, pool exhaustion, cost, and MCP health. Alertmanager routing is optional/configurable. Missing: per-user cost alerts (would create cardinality issues). |
| **Integration Complexity** | 7 | 17 new files, 5 modified files. Telemetry SDK adds ~4 dependencies per service. Middleware integration is clean (insert at position 0 in chain). Risk: Telemetry SDK version drift across services. |
| **Testability** | 9 | All components are unit-testable with mocked Telemetry SDK. Collector config can be validated offline via Docker. Integration test requires running collector + Langfuse. |

**Overall: 8.0/10** -- Production-ready design with clear implementation path. Main gaps are cost tracking precision and SIGKILL-induced span loss (mitigated by collector buffering).

---

## References

- [Observability GenAI Agent Span Semantic Conventions](https://observability.io/docs/specs/semconv/gen-ai/gen-ai-agent-spans/)
- [Observability GenAI Client Span Semantic Conventions](https://observability.io/docs/specs/semconv/gen-ai/gen-ai-spans/)
- [AI Agent Observability - Evolving Standards and Best Practices (Observability Blog)](https://observability.io/blog/2025/ai-agent-observability/)
- [Langfuse Observability Integration](https://langfuse.com/integrations/native/observability)
- [Langfuse Observability Tracing Support (Feb 2025)](https://langfuse.com/changelog/2025-02-14-observability-tracing)
- [Langfuse Telemetry-based Python SDK v3 (May 2025)](https://langfuse.com/changelog/2025-05-23-telemetry-based-python-sdk)
- [OpenLLMetry - Open-source GenAI Observability](https://github.com/traceloop/openllmetry)
- [AI Agents Observability with Observability (VictoriaMetrics)](https://victoriametrics.com/blog/ai-agents-observability/)
- [Agent Observability: Can the Old Playbook Handle the New Game? (Greptime)](https://www.greptime.com/blogs/2025-12-11-agent-observability)
- [Observability Collector Configuration](https://observability.io/docs/collector/configuration/)
- [Observability Collector Configuration Best Practices](https://observability.io/docs/security/config-best-practices/)
- [W3C Trace Context Specification](https://www.w3.org/TR/trace-context/)
- [observability-sdk v1.39.1 (PyPI)](https://pypi.org/project/observability-sdk/)
- [Prometheus Alertmanager Docker Setup](https://oneuptime.com/blog/post/2026-02-08-how-to-set-up-docker-container-alerting-with-alertmanager/view)
- [Langfuse Existing Telemetry Setup Guide](https://langfuse.com/faq/all/existing-telemetry-setup)
