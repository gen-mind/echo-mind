# Agent-to-Chat Integration — Deep Analysis & Plan

> **Date:** 2026-02-16
> **Based on:** Direct source code analysis (EchoMind + Moltbot + Microsoft Agent Framework) + web research
> **Confidence:** High (primary source — code reads + official API docs)
> **Research team:** 5 agents (API, Framework, UI, Moltbot Gateway, Protocol)

---

## Executive Summary

This document analyzes how to integrate EchoMind's agent system (Phases 1-6: config, policy, routing, sessions, 30 tools, MCP) into the existing chat API and WebUI, with streaming of both text responses AND tool execution steps in a collapsible/expandable UI like ChatGPT and Claude.

**Key findings:**
1. The existing chat flow is a hardcoded RAG pipeline (embed → search → stream text). No agent mode exists yet.
2. Microsoft Agent Framework has rich streaming support with 18 content types including `function_call`, `function_result`, `text_reasoning`, and `mcp_server_tool_call`.
3. **CRITICAL BUG**: Our `BasicAgentWrapper.run_stream()` only extracts text — tools never execute in streaming mode because `get_final_response()` is never called.
4. Industry consensus: Use typed content blocks with `start/delta/done` lifecycle for streaming tool execution.
5. The WebUI (separate repo `echo-mind-webui`) needs collapsible step cards for tool visibility.

---

## 1. Current EchoMind Chat Architecture

### 1.1 WebSocket System (Dual Protocol)

| Protocol | Path | Purpose |
|----------|------|---------|
| Native WebSocket | `/api/v1/ws/chat` | Primary chat with JWT auth |
| Socket.IO | `/ws/socket.io` | Open WebUI compatibility (stubs) |

**Key files:**
- `src/api/main.py` — WebSocket endpoint mount
- `src/api/websocket/manager.py` — ConnectionManager (tracks users, sessions, broadcasts)
- `src/api/websocket/chat_handler.py` — ChatHandler (message loop, RAG orchestration)
- `src/api/logic/chat_service.py` — ChatService (retrieval, streaming, persistence)
- `src/api/logic/llm_client.py` — LLMClient (OpenAI/Anthropic/Claude CLI streaming)

### 1.2 Current Message Types

```python
# Client → Server
CHAT_START = "chat.start"       # {session_id, query, mode}
CHAT_CANCEL = "chat.cancel"     # Cancel active generation
PING = "ping"

# Server → Client
RETRIEVAL_START = "retrieval.start"
RETRIEVAL_COMPLETE = "retrieval.complete"   # {sources: [...]}
GENERATION_TOKEN = "generation.token"       # {token: "text chunk"}
GENERATION_COMPLETE = "generation.complete" # {message_id, token_count}
ERROR = "error"
PONG = "pong"
```

### 1.3 Current Chat Flow

```
User → CHAT_START → JWT validation → ChatService.get_session()
  → RETRIEVAL_START → embed query (gRPC) → search Qdrant → RETRIEVAL_COMPLETE
  → LLMClient.stream_completion() → GENERATION_TOKEN (×N) → GENERATION_COMPLETE
  → Save messages to PostgreSQL
```

**Limitations:**
- No tool execution — pure text generation from LLM
- No reasoning/thinking visibility
- No multi-step agent loops
- No agent mode selection (always RAG)
- Token counting is rough word-count estimate

---

## 2. Microsoft Agent Framework Streaming Internals

### 2.1 Content Types (18 types)

From `agent_framework/_types.py`:

```python
ContentType = Literal[
    "text",                          # Standard text output
    "text_reasoning",                # Thinking/reasoning (collapsible)
    "data",                          # Structured data
    "uri",                           # File/URL reference
    "error",                         # Error message
    "function_call",                 # Tool invocation request
    "function_result",               # Tool execution result
    "usage",                         # Token consumption metrics
    "hosted_file",                   # Uploaded file
    "hosted_vector_store",           # Vector store reference
    "code_interpreter_tool_call",    # Code execution request
    "code_interpreter_tool_result",  # Code execution result
    "image_generation_tool_call",    # Image gen request
    "image_generation_tool_result",  # Image gen result
    "mcp_server_tool_call",          # MCP tool invocation
    "mcp_server_tool_result",        # MCP tool result
    "function_approval_request",     # Human-in-the-loop approval
    "function_approval_response",    # Approval decision
]
```

### 2.2 Streaming Architecture

```python
# Agent.run(stream=True) returns ResponseStream[AgentResponseUpdate, AgentResponse]
stream = agent.run("query", stream=True)

async for update in stream:
    for content in update.contents:
        match content.type:
            case "text":           # Display incrementally
            case "function_call":  # Show tool invocation (name, args)
            case "function_result":# Show tool result
            case "text_reasoning": # Show in collapsible section
            case "usage":          # Track token consumption

# MUST call this to finalize (triggers tool execution in multi-turn loops)
final = await stream.get_final_response()
```

### 2.3 CRITICAL BUG in BasicAgentWrapper.run_stream()

Our current `src/agent/agent.py` `run_stream()` implementation:

```python
async def run_stream(self, input_text, session_key=None):
    stream = self._agent.run(input_text, stream=True, session=session)
    async for chunk in stream:
        for content in chunk.contents:
            if hasattr(content, "text"):
                yield content.text  # ← Only extracts text!
    # ← NEVER calls stream.get_final_response()
    # ← Tools NEVER execute in streaming mode!
```

**Fix required:** Must iterate ALL content types AND call `get_final_response()`.

### 2.4 Middleware Architecture

Three interception levels:
- **AgentMiddleware** — Wraps entire agent run (logging, retry, multi-agent)
- **ChatMiddleware** — Wraps LLM API calls (token counting, prompt modification)
- **FunctionMiddleware** — Wraps tool execution (caching, validation, approval)

All three support streaming via transform/result/cleanup hooks on `ResponseStream`.

---

## 3. Moltbot Gateway Architecture (Reference)

### 3.1 Event System

Moltbot's agent events use 4 streams:
```typescript
type AgentEventPayload = {
  runId: string;          // Unique per agent run
  seq: number;            // Monotonically increasing
  stream: "lifecycle" | "tool" | "assistant" | "error";
  data: Record<string, unknown>;
};
```

### 3.2 Tool Event Lifecycle

```typescript
// Tool start
{ stream: "tool", data: { phase: "start", name: "read", toolCallId: "tc_001", args: {...} } }

// Tool result
{ stream: "tool", data: { phase: "result", toolCallId: "tc_001", result: "..." } }
```

### 3.3 Key Patterns to Adopt

| Pattern | Description | Relevance |
|---------|-------------|-----------|
| **150ms delta throttle** | Rate-limit WebSocket text broadcasts | Prevents flooding |
| **Back-pressure** | Drop deltas for slow consumers | Production stability |
| **Verbose levels** | User-configurable tool event visibility | UX flexibility |
| **Run isolation** | `runId` + `seq` for ordered events | Prevents cross-run interference |
| **Block streaming coalesce** | Buffer tokens, flush on min chars or idle | For messaging channels |
| **Channel plugin architecture** | Adapter pattern for different platforms | Future extensibility |

---

## 4. Streaming Protocol Research

### 4.1 Industry Consensus

| Provider | Transport | Pattern |
|----------|-----------|---------|
| OpenAI Responses API | SSE | 53 event types, `response.output_text.delta` |
| Claude Messages API | SSE | Block-based: `content_block_start/delta/stop` |
| Vercel AI SDK | SSE | `text-start/delta/end`, `tool-input-start/delta` |
| ChatGPT Web UI | WebSocket | Custom JSON frames |
| AG-UI Protocol | SSE/WS | Open standard: `TEXT_MESSAGE_CONTENT`, `TOOL_CALL_START` |

**Key insight:** All providers use the same fundamental pattern — **typed content blocks with start/delta/done lifecycle**.

### 4.2 Protocol Recommendation for EchoMind

**Keep WebSocket** (EchoMind already has it) with **AG-UI-style typed JSON events**:

```json
{
  "type": "text.delta",
  "run_id": "run_abc",
  "seq": 42,
  "data": {"block_id": "blk_001", "delta": "Hello"}
}
```

**Rationale:**
- EchoMind already has WebSocket infrastructure (ConnectionManager, ChatHandler)
- Adding SSE would create two streaming protocols to maintain
- WebSocket supports bidirectional (cancel, presence) natively
- AG-UI event taxonomy is the emerging open standard

### 4.3 Recommended Event Types

```python
class AgentEventType(str, Enum):
    # Response lifecycle
    RESPONSE_START = "response.start"
    RESPONSE_COMPLETE = "response.complete"
    RESPONSE_ERROR = "response.error"
    RESPONSE_CANCELLED = "response.cancelled"

    # Step lifecycle (each LLM call in multi-step agent loop)
    STEP_START = "step.start"
    STEP_COMPLETE = "step.complete"

    # Text generation
    TEXT_DELTA = "text.delta"

    # Reasoning / thinking
    REASONING_START = "reasoning.start"
    REASONING_DELTA = "reasoning.delta"
    REASONING_DONE = "reasoning.done"

    # Tool calls
    TOOL_CALL_START = "tool_call.start"         # {tool_name, tool_call_id}
    TOOL_CALL_ARGS = "tool_call.args"           # {arguments (parsed)}
    TOOL_CALL_EXECUTING = "tool_call.executing"  # Tool is running
    TOOL_CALL_RESULT = "tool_call.result"        # {result, duration_ms}
    TOOL_CALL_ERROR = "tool_call.error"          # {error_message}

    # Approval (human-in-the-loop)
    APPROVAL_REQUEST = "approval.request"
    APPROVAL_RESPONSE = "approval.response"

    # Retrieval (RAG-specific)
    RETRIEVAL_START = "retrieval.start"
    RETRIEVAL_RESULTS = "retrieval.results"      # {chunks: [...]}
    RETRIEVAL_COMPLETE = "retrieval.complete"

    # Sources
    SOURCE_ADDED = "source.added"

    # Keep-alive
    PING = "ping"
```

### 4.4 Complete Stream Example (Agentic RAG Turn)

```
→ response.start     {run_id, session_id}
→ step.start         {step_index: 0, type: "retrieval"}
→ retrieval.start    {query}
→ retrieval.results  {chunks: [{doc_id, score, preview}...]}
→ retrieval.complete {total_chunks, duration_ms}
→ source.added       {source_id, doc_id, title, score}
→ step.complete      {step_index: 0}
→ step.start         {step_index: 1, type: "generation"}
→ text.delta          {delta: "Based on the documents"}
→ text.delta          {delta: " I found, here is"}
→ tool_call.start    {tool_call_id, tool_name: "search_knowledge_base"}
→ tool_call.args     {arguments: {query: "NATS config"}}
→ tool_call.executing {message: "Searching..."}
→ tool_call.result   {result: {...}, duration_ms: 450}
→ text.delta          {delta: "Additionally, "}
→ text.delta          {delta: "the configuration shows..."}
→ step.complete      {step_index: 1}
→ response.complete  {usage: {prompt_tokens, completion_tokens}}
```

---

## 5. WebUI Patterns for Tool Execution Display

### 5.1 Industry Reference

| Product | Tool Display | Collapsible | Source Rendering |
|---------|-------------|-------------|------------------|
| ChatGPT | "Searching the web..." → expandable results | Yes, default collapsed | Inline citation links |
| Claude | "Using tool: X" → collapsible input/output | Yes, default collapsed | Footnote citations |
| Cursor | Step cards with spinner → result preview | Yes, auto-collapse on done | File references |
| Vercel AI SDK | `useChat` hook + custom tool renderers | Configurable | Component-based |
| assistant-ui | `<ToolFallback>` component with status | Yes | Built-in |

### 5.2 Recommended UI Components

```
┌─────────────────────────────────────────────┐
│ 🤖 Agent Response                           │
├─────────────────────────────────────────────┤
│                                             │
│ Based on the documents I found...           │  ← text.delta (streaming)
│                                             │
│ ┌─ 🔍 Searching knowledge base ──────────┐ │  ← tool_call.start (collapsed by default)
│ │  Query: "NATS JetStream config"         │ │  ← tool_call.args
│ │  ✅ Found 3 results (450ms)             │ │  ← tool_call.result
│ │  [▼ Show details]                       │ │  ← expandable
│ └─────────────────────────────────────────┘ │
│                                             │
│ The configuration requires...               │  ← text.delta (continues)
│                                             │
│ ┌─ 💭 Reasoning ──────────────────────────┐ │  ← reasoning.start (collapsed)
│ │  I need to verify the port number...     │ │
│ └─────────────────────────────────────────┘ │
│                                             │
│ Sources:                                    │
│  [1] NATS Setup Guide (0.92)               │  ← source.added
│  [2] Stream Configuration (0.87)            │
│                                             │
├─────────────────────────────────────────────┤
│ 📊 1,200 prompt + 350 completion tokens    │  ← usage (optional footer)
└─────────────────────────────────────────────┘
```

### 5.3 UI State Machine per Tool Call

```
PENDING → EXECUTING → COMPLETED | FAILED
  │           │           │          │
  │           │           │          └─ Red border, error message, retry button
  │           │           └─ Green check, collapsed result preview
  │           └─ Spinner animation, "Running..." label
  └─ Tool name + arguments shown
```

---

## 6. Architecture Decision: Agent Mode in Chat

### Option A: New Agent Handler (Separate from ChatHandler)

```
/api/v1/ws/chat     → ChatHandler (existing RAG flow)
/api/v1/ws/agent    → AgentHandler (new, agent system)
```

**Pros:** Clean separation, no risk of breaking existing chat
**Cons:** Code duplication (auth, session management), two WebSocket connections

### Option B: Extend ChatHandler with Agent Mode

```
/api/v1/ws/chat     → ChatHandler (routes to RAG or Agent based on session/config)
```

**Pros:** Single connection, shared infrastructure
**Cons:** ChatHandler grows in complexity

### Option C: Unified AgentChatHandler (Replace ChatHandler)

```
/api/v1/ws/chat     → AgentChatHandler (agent-first, RAG is a "tool")
```

**Pros:** RAG becomes a native tool (`search_knowledge_base`), cleanest long-term architecture
**Cons:** Biggest change, requires careful migration

### Recommendation: **Option B for Phase 7, migrate to Option C in Phase 8**

Phase 7: Add `mode: "agent"` to `CHAT_START`. ChatHandler routes to either existing RAG flow or new AgentService. Minimal disruption.

Phase 8: When RAG tools are added (Phase 8 roadmap), the agent can natively call `search_knowledge_base` as a tool, making the RAG flow an agent capability rather than a separate code path.

---

## 7. Implementation Components

### 7.1 Backend (Phase 7 — API Gateway Integration)

| File | Purpose |
|------|---------|
| `src/api/logic/agent_service.py` | AgentService: creates agents, runs with streaming, maps events |
| `src/api/websocket/agent_handler.py` | AgentHandler: WebSocket handler for agent mode |
| `src/api/routes/agents.py` | REST: list agents, agent info, run history |
| `src/agent/agent.py` | **FIX**: `run_stream()` must yield all content types + call `get_final_response()` |

### 7.2 Event Mapping (Agent Framework → WebSocket)

```python
# Map AgentResponseUpdate content types to WebSocket events
CONTENT_TYPE_TO_EVENT = {
    "text": AgentEventType.TEXT_DELTA,
    "text_reasoning": AgentEventType.REASONING_DELTA,
    "function_call": AgentEventType.TOOL_CALL_START,
    "function_result": AgentEventType.TOOL_CALL_RESULT,
    "mcp_server_tool_call": AgentEventType.TOOL_CALL_START,
    "mcp_server_tool_result": AgentEventType.TOOL_CALL_RESULT,
    "function_approval_request": AgentEventType.APPROVAL_REQUEST,
    "error": AgentEventType.RESPONSE_ERROR,
    "usage": None,  # Aggregated into RESPONSE_COMPLETE
}
```

### 7.3 Frontend (WebUI — separate repo)

| Component | Purpose |
|-----------|---------|
| `AgentMessage` | Top-level component for agent responses |
| `ToolCallCard` | Collapsible card showing tool name, args, result |
| `ReasoningBlock` | Collapsible thinking/reasoning section |
| `SourceList` | Citation list with document links |
| `StepIndicator` | Step progress for multi-step agent loops |
| `useAgentStream` | React hook for consuming agent WebSocket events |

---

## 8. Evaluation Scorecard

### 8.1 Architecture Readiness

| Dimension | Score | Notes |
|-----------|:-----:|-------|
| Agent Framework streaming support | 9/10 | Rich content types, ResponseStream, middleware hooks |
| Existing WebSocket infrastructure | 7/10 | Good foundation, needs agent event types |
| Agent system (Phases 1-6) | 8/10 | Config, policy, tools, MCP ready. Streaming bug needs fix |
| Chat persistence layer | 6/10 | Works for text-only. Needs schema for tool calls |
| WebUI readiness | 3/10 | No agent support yet. Needs new components |

### 8.2 Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| `run_stream()` bug (tools don't execute) | **Critical** | Fix before any integration |
| WebSocket message size (large tool results) | Medium | Truncate results, offer "show full" |
| Multi-step agent loops (token cost) | Medium | Token budget limits per run |
| LLM provider differences | Low | Agent Framework abstracts this |
| WebUI separate repo coordination | Medium | Define event contract first |

### 8.3 Effort Estimate

| Component | Complexity | Dependencies |
|-----------|:----------:|--------------|
| Fix `run_stream()` bug | Low | None |
| AgentService + event mapping | Medium | Agent Phases 1-6 |
| AgentHandler (WebSocket) | Medium | AgentService |
| REST endpoints | Low | AgentService |
| WebUI agent components | High | Event contract |
| Tool call persistence schema | Medium | Alembic migration |
| E2E testing | High | All above |

---

## 9. Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Transport** | Extend existing WebSocket | Single connection, shared auth/session, no protocol fragmentation |
| **Agent mode activation** | Per-session toggle | User explicitly picks "Agent mode" in the UI when starting a session |
| **Session storage** | Keep JSONL for Phase 7 | Simpler initial integration. Migrate to PostgreSQL in Phase 9 |
| **Backward compatibility** | Keep both flows | Existing RAG flow unchanged. Agent mode is additive. Zero risk |

### Remaining Open Questions

1. **Tool approval UX**: When a tool requires approval (`always_require`), should the UI show a confirmation dialog? Or auto-approve in chat context?
2. **WebUI coordination**: Backend-first (define event contract) or plan both repos simultaneously?

---

## Sources

### Primary Sources (Code Analysis)
- **EchoMind API**: `src/api/websocket/chat_handler.py`, `src/api/logic/chat_service.py`, `src/api/logic/llm_client.py`
- **Agent System**: `src/agent/agent.py`, `src/agent/mcp/manager.py`, `src/agent/config/schema.py`
- **Agent Framework**: `agent_framework/_types.py` (content types), `_agents.py` (streaming), `_tools.py` (FunctionInvocationLayer), `_middleware.py`
- **Moltbot**: `sample/moltbot/src/gateway/server-chat.ts`, `server-channels.ts`, `protocol/schema/`, `channels/plugins/types*.ts`

### Web Research Sources
- [OpenAI Responses API Streaming](https://platform.openai.com/docs/api-reference/responses-streaming) — 53 event types
- [Claude Streaming Messages](https://platform.claude.com/docs/en/build-with-claude/streaming) — Content block model
- [Vercel AI SDK Stream Protocol](https://ai-sdk.dev/docs/ai-sdk-ui/stream-protocol) — Data stream types
- [AG-UI Protocol](https://ai.pydantic.dev/ui/ag-ui/) — Open standard for agent-UI streaming
- [Microsoft AG-UI Backend Tool Rendering](https://learn.microsoft.com/en-us/agent-framework/integrations/ag-ui/backend-tool-rendering)
- [AI Agent Chat: WebSocket vs SSE](https://www.karls.io/ai-agent-progress-chat-websocket-server-sent-events/) — Protocol comparison
- [SSE vs WebSockets for LLM Apps](https://compute.hivenet.com/post/llm-streaming-sse-websockets) — Scaling analysis
- [Streaming at Scale](https://learnwithparam.com/blog/streaming-at-scale-sse-websockets-real-time-ai-apis) — Production patterns
- [Qdrant MCP Server](https://github.com/qdrant/mcp-server-qdrant) — Priority MCP integration
- [PulseMCP Directory](https://www.pulsemcp.com/servers) — 8,230+ MCP servers
