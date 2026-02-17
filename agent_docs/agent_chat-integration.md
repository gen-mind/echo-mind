# Phase 5: Chat/WebSocket to Sandboxed Agent Integration — Execution Plan

> **Date**: 2026-02-17
> **Based on**: Direct source code analysis (all API, WebSocket, sandbox, proto files), web research (AG-UI, NATS JetStream, Semantic Kernel streaming), Phases 1-4 implementation
> **Status**: Implementation-ready
> **Confidence**: High (primary sources — code reads + official docs + AG-UI protocol spec)

---

## 1. Executive Summary

Phase 5 wires together all prior work (MCP Gateway, Sandbox Foundation, Agent Framework) so users can **chat with sandboxed agents via WebSocket**. The API service becomes a **message router**: it assigns an ephemeral Docker container to each agent session, relays user messages via NATS JetStream, and streams back agent responses (tokens, tool calls, sources) through the existing WebSocket connection.

### Key Deliverables

| # | Deliverable | Description |
|---|-------------|-------------|
| 1 | **Agent chat routing** | `mode=agent` in `chat.start` routes to sandbox pipeline instead of in-process RAG |
| 2 | **NATS stream relay** | API subscribes to sandbox output stream, relays events to WebSocket in real-time |
| 3 | **Sandbox agent activation** | Semantic Kernel agent initialized inside sandbox with MCP tools, LLM config |
| 4 | **AG-UI event protocol** | Industry-standard typed content blocks with `start/delta/end` lifecycle |
| 5 | **Tool call visualization** | Tool invocations streamed to client with name, args, result, duration |
| 6 | **Graceful degradation** | Fallback to non-sandbox RAG if sandbox pool exhausted |
| 7 | **Database persistence** | Agent messages saved to existing `chat_messages` table by API on completion |
| 8 | **REST sandbox endpoints** | Admin pool status, user session management, cancel generation |

### Key Metrics

| Metric | Target |
|--------|--------|
| Time to first token (warm pool) | <200ms |
| NATS relay overhead per token | <5ms |
| Backward compatibility | 100% — existing `mode=chat` and `mode=search` unchanged |
| New WebSocket event types | 8 agent-specific events |
| New files | 8 production + 6 test files |
| Modified files | 7 existing files |
| Test coverage | 100% for new code (~60 test cases) |

### Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Transport: Client ↔ API | WebSocket (existing) | Already implemented, bidirectional, proven |
| Transport: API ↔ Sandbox | NATS JetStream pub/sub | Already deployed, decoupled, supports streaming |
| Transport: Sandbox ↔ MCP | Streamable HTTP | Standard MCP protocol, no auth initially |
| Streaming granularity | AG-UI typed content blocks | Industry standard (OpenAI, Anthropic, AG-UI protocol) |
| Session routing | Session-pinned sandbox | Once assigned, all messages for session route to same container |
| Backward compatibility | Mode-based routing | `mode=chat` uses existing RAG; `mode=agent` uses sandbox |
| Wire format (NATS) | JSON initially | Proto definitions serve as schema contract; switch to protobuf later if volume warrants it |

---

## 2. Architecture Diagram

```
User      WebUI       API (:8000)          NATS JetStream        Sandbox Container      MCP Gateway     LLM Provider
 |          |              |                     |                      |                    |               |
 |--msg---->|              |                     |                      |                    |               |
 |          |--WS: chat.start (session_id, query, mode="agent")------->|                    |               |
 |          |              |                     |                      |                    |               |
 |          |              |---1. SandboxManager.assign(sid)----------->|                    |               |
 |          |              |   (pop warm container, inject env)         |                    |               |
 |          |              |<--SandboxAssignment (container_id)---------|                    |               |
 |          |              |                     |                      |                    |               |
 |          |<--WS: agent.sandbox_assigned-------|                      |                    |               |
 |          |              |                     |                      |                    |               |
 |          |              |---2. PUB sandbox.{sid}.input-------------->|                    |               |
 |          |              |   {type: query, query, chat_history}       |                    |               |
 |          |              |                     |                      |                    |               |
 |          |              |                     |---3. SUB .input----->|                    |               |
 |          |              |                     |                      |--MCP: list_tools-->|               |
 |          |              |                     |                      |<--tools list-------|               |
 |          |              |                     |                      |                    |               |
 |          |              |                     |                      |--LLM: stream()---->|-------------->|
 |          |              |                     |                      |<--tokens-----------|<--------------|
 |          |              |                     |                      |                    |               |
 |          |              |<--4. PUB .stream {type: text.delta}--------|                    |               |
 |          |<--WS: agent.text.delta-------------|                      |                    |               |
 |<-render--|              |                     |                      |                    |               |
 |          |              |                     |                      |                    |               |
 |          |              |<--5. PUB .stream {type: tool_call.start}---|                    |               |
 |          |<--WS: agent.tool_call.start--------|                      |                    |               |
 |          |              |                     |                      |--MCP: tool()------>|               |
 |          |              |                     |                      |<--result-----------|               |
 |          |              |<--6. PUB .stream {type: tool_call.result}--|                    |               |
 |          |<--WS: agent.tool_call.result-------|                      |                    |               |
 |          |              |                     |                      |                    |               |
 |          |              |<--7. PUB .stream {type: text.delta}--------|                    |               |
 |          |<--WS: agent.text.delta-------------|                      |                    |               |
 |<-render--|              |                     |                      |                    |               |
 |          |              |                     |                      |                    |               |
 |          |              |<--8. PUB .stream {type: response.complete}-|                    |               |
 |          |              |                     |                      |                    |               |
 |          |              |---9. save messages to DB (user + assistant)|                    |               |
 |          |              |                     |                      |                    |               |
 |          |<--WS: generation.complete----------|                      |                    |               |
 |<-done----|              |                     |                      |                    |               |
```

---

## 3. Message Flow (Step-by-Step)

### 3.1 Happy Path

1. **User sends message**: WebUI sends `chat.start` with `mode=agent`, `session_id`, `query` via WebSocket.
2. **API validates**: `ChatHandler._handle_chat_start()` checks session ownership, validates parameters.
3. **Mode routing**: `mode == "agent"` → dispatch to `_process_agent_chat()` (new method). `mode == "chat"` or `mode == "search"` → existing `_process_chat()` (unchanged).
4. **Sandbox assignment**: `SandboxManager.assign()` pops a warm container from pool, injects session env vars via tar file in tmpfs. If pool empty, creates on-demand. If max instances reached, falls back to non-sandbox RAG.
5. **Sandbox notification**: API sends `agent.sandbox_assigned` event to client.
6. **Query publish**: API publishes `{type: "query", query, chat_history, context}` to `sandbox.{session_id}.input`.
7. **User message saved**: API saves user message to `chat_messages` table immediately.
8. **Sandbox processes**: `SandboxAgent._handle_input()` receives message, dispatches to `AgentRunner.process_query()`.
9. **Agent streams**: AgentRunner runs Semantic Kernel agent, which calls LLM and MCP tools. Each event is published to `sandbox.{session_id}.stream`.
10. **API relays**: `NatsStreamRelay.relay_session()` subscribes to stream subject with ordered consumer, maps each event to WebSocket message type, forwards to client.
11. **Completion**: Sandbox publishes `{type: "response.complete"}`. API saves assistant message with sources and tool call metadata. Sends `generation.complete` to client.
12. **Idle**: Sandbox waits for next message on input subject. Heartbeat continues every 15s.

### 3.2 Cancellation Flow

1. Client sends `chat.cancel` via WebSocket.
2. `ChatHandler._handle_chat_cancel()` cancels the active asyncio task.
3. Inside `_process_agent_chat`, cancelled task publishes `{type: "cancel"}` to `sandbox.{session_id}.input`.
4. Sandbox's `AgentRunner` receives cancel, aborts current LLM stream, publishes `{type: "response.cancelled"}`.
5. API relay loop receives cancelled event, sends `agent.response.cancelled` to client, breaks.

### 3.3 Error Flow

1. Sandbox encounters error (LLM timeout, MCP failure, etc.).
2. Publishes `{type: "error", code, message, recoverable}` to stream subject.
3. API relay forwards as WebSocket `error` event.
4. If `recoverable=false`, relay breaks and sandbox is released.
5. If `recoverable=true`, relay continues (agent may retry internally).

---

## 4. NATS Subject Design

### 4.1 Subject Hierarchy

```
# Per-session subjects (ephemeral, exist while sandbox is active)
sandbox.{session_id}.input       # API → Sandbox: user messages, cancel
sandbox.{session_id}.stream      # Sandbox → API: streaming events (tokens, tool calls, etc.)
sandbox.{session_id}.output      # Sandbox → API: final assembled responses
sandbox.{session_id}.control     # API → Sandbox: lifecycle (init, shutdown, config)
sandbox.{session_id}.health      # Sandbox → API: heartbeat (every 15s)
```

`session_id` format: `sess_{chat_session_id}` — e.g., `sess_42`. Maps directly to the integer `chat_session_id` in the database. The `SandboxAssignment.session_id` stores this string.

### 4.2 JetStream Stream Configuration

```python
# Memory-backed stream for real-time sandbox communication
SANDBOX_STREAM_CONFIG = {
    "name": "sandbox-stream",
    "subjects": [
        "sandbox.*.input",
        "sandbox.*.output",
        "sandbox.*.stream",
        "sandbox.*.control",
        "sandbox.*.health",
    ],
    "retention": "limits",
    "max_msgs_per_subject": 10000,
    "max_age": 3600_000_000_000,  # 1 hour in nanoseconds
    "storage": "memory",          # Ephemeral — no disk persistence needed
    "discard": "old",
}
```

**Rationale**: Memory storage for minimal latency. 1-hour retention covers longest session timeout. Ordered consumers guarantee message ordering per subject without explicit acking. Source: [NATS JetStream Docs](https://docs.nats.io/nats-concepts/jetstream/consumers).

### 4.3 Consumer Pattern

API uses **ordered push consumers** for each relay session:

```python
sub = await js.subscribe(
    f"sandbox.{session_id}.stream",
    stream="sandbox-stream",
    ordered_consumer=True,  # Guarantees FIFO delivery, no acks needed
)
```

**Why ordered consumers**: They guarantee strictly sequential delivery (no gaps, no redeliveries), which is essential for token-by-token streaming. They are ephemeral (auto-deleted when unsubscribed), matching the session-scoped lifecycle. Source: [NATS Ordered Consumers](https://docs.nats.io/using-nats/developer/develop_jetstream/consumers).

---

## 5. Proto Definitions

### 5.1 Modified: `src/proto/public/chat.proto`

Add `CHAT_MODE_AGENT` to existing ChatMode enum and new WebSocket messages:

```protobuf
// Chat mode — add new value
enum ChatMode {
  CHAT_MODE_UNSPECIFIED = 0;
  CHAT_MODE_CHAT = 1;
  CHAT_MODE_SEARCH = 2;
  CHAT_MODE_AGENT = 3;   // NEW: sandbox agent mode
}

// NEW: Server -> Client: Agent sandbox assigned
message WsAgentSandboxAssigned {
  int32 session_id = 1;
}

// NEW: Server -> Client: Agent text delta (streaming token)
message WsAgentTextDelta {
  int32 session_id = 1;
  string delta = 2;
  string run_id = 3;
}

// NEW: Server -> Client: Agent tool call started
message WsAgentToolCallStart {
  int32 session_id = 1;
  string call_id = 2;
  string tool_name = 3;
  google.protobuf.Struct args = 4;
  string run_id = 5;
}

// NEW: Server -> Client: Agent tool call result
message WsAgentToolCallResult {
  int32 session_id = 1;
  string call_id = 2;
  string result = 3;
  bool success = 4;
  int32 duration_ms = 5;
  string run_id = 6;
}

// NEW: Server -> Client: Agent reasoning (thinking) delta
message WsAgentReasoningDelta {
  int32 session_id = 1;
  string delta = 2;
  string run_id = 3;
}

// NEW: Server -> Client: Agent step lifecycle
message WsAgentStepStart {
  int32 session_id = 1;
  int32 step_index = 2;
  string step_type = 3;  // "retrieval", "generation", "tool_execution"
  string run_id = 4;
}

message WsAgentStepComplete {
  int32 session_id = 1;
  int32 step_index = 2;
  int32 duration_ms = 3;
  string run_id = 4;
}
```

### 5.2 Existing: `src/proto/internal/sandbox.proto`

Already defines `SandboxSession`, `SandboxEvent`, `SandboxStatus`, `SandboxEventType`. No changes needed — these are used for DB persistence and were created in Phase 4.

### 5.3 Proto Generation

After modifying `chat.proto`:

```bash
./scripts/generate_proto.sh
```

This regenerates:
- `src/echomind_lib/models/public/chat_pb2.py` (Python protobuf)
- `src/echomind_lib/models/public/chat_model.py` (Pydantic models)
- `src/web/src/models/public/chat.ts` (TypeScript interfaces — for WebUI)

---

## 6. WebSocket Protocol

### 6.1 Complete Event Types (Including New Agent Events)

| Direction | Type | Payload | Mode | Description |
|-----------|------|---------|------|-------------|
| **Client → Server** | | | | |
| | `chat.start` | `{session_id, query, mode}` | all | Start chat query |
| | `chat.cancel` | `{session_id}` | all | Cancel active generation |
| | `ping` | — | all | Keepalive |
| **Server → Client (existing)** | | | | |
| | `retrieval.start` | `{session_id, query}` | chat | Retrieval phase began |
| | `retrieval.complete` | `{session_id, sources[]}` | chat/agent | Retrieved sources |
| | `generation.token` | `{session_id, token}` | chat | Streaming LLM token (legacy RAG) |
| | `generation.complete` | `{session_id, message_id, token_count}` | all | Generation done |
| | `error` | `{code, message}` | all | Error occurred |
| | `pong` | — | all | Keepalive response |
| **Server → Client (NEW agent events)** | | | | |
| | `agent.sandbox_assigned` | `{session_id}` | agent | Sandbox container assigned |
| | `agent.text.delta` | `{session_id, delta, run_id}` | agent | Streaming text token |
| | `agent.tool_call.start` | `{session_id, call_id, tool_name, args, run_id}` | agent | Tool invocation started |
| | `agent.tool_call.result` | `{session_id, call_id, result, success, duration_ms, run_id}` | agent | Tool invocation completed |
| | `agent.reasoning.delta` | `{session_id, delta, run_id}` | agent | Reasoning/thinking token |
| | `agent.step.start` | `{session_id, step_index, step_type, run_id}` | agent | Agent step started |
| | `agent.step.complete` | `{session_id, step_index, duration_ms, run_id}` | agent | Agent step completed |
| | `agent.response.cancelled` | `{session_id, run_id}` | agent | Generation cancelled |

### 6.2 AG-UI Alignment

These event types map to the [AG-UI Protocol](https://docs.ag-ui.com/) standard:

| EchoMind Event | AG-UI Event | Notes |
|----------------|-------------|-------|
| `agent.text.delta` | `TEXT_MESSAGE_CONTENT` | Content block delta |
| `agent.tool_call.start` | `TOOL_CALL_START` | With toolCallId, name |
| `agent.tool_call.result` | `TOOL_CALL_RESULT` | With result payload |
| `agent.reasoning.delta` | Custom (no AG-UI equiv) | Anthropic-style thinking |
| `agent.step.start` | `STEP_STARTED` | Multi-step agent |
| `agent.step.complete` | `STEP_FINISHED` | Multi-step agent |
| `generation.complete` | `RUN_FINISHED` | Final completion |

### 6.3 Run ID

Every agent response is tagged with a `run_id` (UUID hex, 16 chars). This allows the client to:
- Correlate events within a single agent execution
- Distinguish between multiple concurrent or sequential runs
- Detect stale events from previous cancelled runs

---

## 7. Session Lifecycle

### 7.1 State Machine

```
           ┌────────────┐
           │   CREATED   │  Client sends chat.start with mode=agent
           │  (in API)   │  API creates/reuses ChatSession in DB
           └──────┬──────┘
                  │
                  ▼
           ┌────────────┐
           │  ASSIGNING  │  SandboxManager.assign() picks warm container
           │             │  Injects session env vars via tmpfs
           └──────┬──────┘
                  │
                  ▼
           ┌────────────┐
           │   ACTIVE    │  Sandbox publishes ready on health subject
           │             │  API relays events, saves messages
           └──────┬──────┘
                  │
        ┌─────────┴──────────┐
        │                    │
        ▼                    ▼
 ┌────────────┐      ┌────────────┐
 │    IDLE     │      │  TIMEOUT   │  session_timeout exceeded (3600s)
 │  (waiting)  │      │            │  idle_timeout exceeded (300s)
 └──────┬──────┘      └──────┬─────┘
        │                    │
        │  next message      │  reconciliation loop
        │  arrives           │  detects timeout
        │                    │
        ▼                    ▼
 ┌────────────┐      ┌────────────┐
 │   ACTIVE    │      │  DRAINING  │  API publishes shutdown on control
 │  (resumed)  │      │            │  Sandbox has 30s grace period
 └─────────────┘      └──────┬─────┘
                             │
                             ▼
                      ┌────────────┐
                      │ DESTROYED  │  Container removed, pool replenished
                      └────────────┘
```

### 7.2 Session Reuse

When a user sends multiple messages in the same chat session with `mode=agent`:
- **First message**: Assigns new sandbox, stores mapping `session_id → SandboxAssignment`.
- **Subsequent messages**: Looks up existing assignment via `SandboxManager.get_assignment()`, reuses the same sandbox.
- **After timeout**: Next message triggers new sandbox assignment (transparent to user).

### 7.3 Session Cleanup

The reconciliation loop (every 30s in `SandboxManager._reconciliation_loop()`) handles:
- **Session timeout**: Active sandboxes past `session_timeout` (3600s) → force release.
- **Idle warm timeout**: Warm containers past `idle_timeout` (300s) → destroy and replenish.
- **Orphan detection**: On API restart, `_discover_existing_containers()` finds containers with `echomind.sandbox` label and reconciles.

---

## 8. ChatHandler Modifications

**File**: `src/api/websocket/chat_handler.py`

### 8.1 New MessageType Values

```python
class MessageType(str, Enum):
    # ... existing values ...

    # Server -> Client (agent-specific) — NEW
    AGENT_SANDBOX_ASSIGNED = "agent.sandbox_assigned"
    AGENT_TEXT_DELTA = "agent.text.delta"
    AGENT_TOOL_CALL_START = "agent.tool_call.start"
    AGENT_TOOL_CALL_RESULT = "agent.tool_call.result"
    AGENT_REASONING_DELTA = "agent.reasoning.delta"
    AGENT_STEP_START = "agent.step.start"
    AGENT_STEP_COMPLETE = "agent.step.complete"
    AGENT_RESPONSE_CANCELLED = "agent.response.cancelled"
```

### 8.2 Modified `_handle_chat_start()`

The routing decision happens here:

```python
async def _handle_chat_start(self, user: TokenUser, data: dict[str, Any]) -> None:
    """Handle chat.start message — routes to RAG or sandbox based on mode."""
    session_id = data.get("session_id")
    query = data.get("query")
    mode = data.get("mode", "chat")

    if not session_id or not query:
        await self._send_error(user.id, "INVALID_REQUEST", "session_id and query required")
        return

    # Cancel any existing generation
    if user.id in self._active_generations:
        self._active_generations[user.id].cancel()

    self.manager.subscribe(user.id, session_id)

    if mode == "agent":
        # NEW: route to sandbox agent pipeline
        task = asyncio.create_task(
            self._process_agent_chat(user, session_id, query)
        )
    else:
        # EXISTING: in-process RAG pipeline (unchanged)
        task = asyncio.create_task(
            self._process_chat(user, session_id, query, mode)
        )

    self._active_generations[user.id] = task
```

### 8.3 New `_process_agent_chat()` Method

This is the core new method (~120 LOC). It:

1. Gets or assigns a sandbox for the session.
2. Publishes the query to NATS.
3. Saves user message to DB.
4. Subscribes to sandbox stream and relays events to WebSocket.
5. On completion, saves assistant message with sources and tool calls.
6. On error/cancellation, handles cleanup.

```python
async def _process_agent_chat(
    self,
    user: TokenUser,
    chat_session_id: int,
    query: str,
) -> None:
    """
    Process chat via sandboxed agent.

    1. Get or assign sandbox for this session
    2. Publish query to sandbox via NATS
    3. Subscribe to sandbox stream, relay events to WebSocket
    4. Save messages to DB on completion

    Args:
        user: Authenticated user.
        chat_session_id: Chat session ID.
        query: User's query text.
    """
    trace = create_trace(
        name="agent-chat",
        user_id=str(user.id),
        session_id=str(chat_session_id),
        tags=["agent"],
    )

    try:
        sandbox_mgr = get_sandbox_manager()
        nats_relay = get_nats_relay()

        # Get or assign sandbox
        session_id = f"sess_{chat_session_id}"
        sandbox = await sandbox_mgr.get_assignment(session_id)

        if not sandbox:
            session = await self._get_session_with_assistant(chat_session_id, user)
            env_vars = self._build_sandbox_env(user, session)

            try:
                sandbox = await sandbox_mgr.assign(
                    session_id=session_id,
                    user_id=user.id,
                    chat_session_id=chat_session_id,
                    env_vars=env_vars,
                    db=self._db,
                )
            except RuntimeError:
                # Pool exhausted — fall back to non-sandbox RAG
                logger.warning(
                    "⚠️ Sandbox pool exhausted for user %d, falling back to RAG",
                    user.id,
                )
                await self._process_chat(user, chat_session_id, query, "chat")
                return

            await self.manager.send_to_user(user.id, {
                "type": MessageType.AGENT_SANDBOX_ASSIGNED,
                "session_id": chat_session_id,
            })

        # Load chat history for context
        chat_history = await self._load_chat_history(chat_session_id)

        # Save user message
        service = ChatService(
            db=self._db,
            qdrant=get_qdrant(),
            embedder=get_embedder_client(),
            llm=get_llm_client(),
        )
        user_message = await service.save_user_message(chat_session_id, query)
        await self._db.commit()

        # Publish query to sandbox
        await nats_relay.publish_query(
            session_id=session_id,
            query=query,
            chat_history=chat_history,
            context={"chat_session_id": chat_session_id},
        )

        # Relay sandbox stream to WebSocket
        response_content = ""
        token_count = 0
        tool_calls: list[dict[str, Any]] = []
        sources: list[RetrievedSource] = []

        async for event in nats_relay.relay_session(session_id):
            # Check for cancellation
            current_task = asyncio.current_task()
            if current_task is not None and current_task.cancelled():
                await nats_relay.cancel(session_id)
                return

            event_type = event["type"]

            if event_type == "text.delta":
                delta = event["data"]
                response_content += delta
                token_count += 1
                await self.manager.send_to_user(user.id, {
                    "type": MessageType.AGENT_TEXT_DELTA,
                    "session_id": chat_session_id,
                    "delta": delta,
                    "run_id": event.get("run_id", ""),
                })

            elif event_type == "tool_call.start":
                tool_calls.append({
                    "call_id": event["call_id"],
                    "tool_name": event["tool_name"],
                    "args": event.get("args", {}),
                })
                await self.manager.send_to_user(user.id, {
                    "type": MessageType.AGENT_TOOL_CALL_START,
                    "session_id": chat_session_id,
                    "call_id": event["call_id"],
                    "tool_name": event["tool_name"],
                    "args": event.get("args", {}),
                    "run_id": event.get("run_id", ""),
                })

            elif event_type == "tool_call.result":
                # Update the matching tool call with result
                for tc in tool_calls:
                    if tc["call_id"] == event["call_id"]:
                        tc["result"] = event.get("result", "")
                        tc["success"] = event.get("success", True)
                        tc["duration_ms"] = event.get("duration_ms", 0)
                        break
                await self.manager.send_to_user(user.id, {
                    "type": MessageType.AGENT_TOOL_CALL_RESULT,
                    "session_id": chat_session_id,
                    "call_id": event["call_id"],
                    "result": event.get("result", ""),
                    "success": event.get("success", True),
                    "duration_ms": event.get("duration_ms", 0),
                    "run_id": event.get("run_id", ""),
                })

            elif event_type == "reasoning.delta":
                await self.manager.send_to_user(user.id, {
                    "type": MessageType.AGENT_REASONING_DELTA,
                    "session_id": chat_session_id,
                    "delta": event["data"],
                    "run_id": event.get("run_id", ""),
                })

            elif event_type == "sources":
                sources = [
                    RetrievedSource(
                        document_id=s["document_id"],
                        chunk_id=s["chunk_id"],
                        score=s["score"],
                        title=s.get("title", ""),
                        content=s.get("snippet", ""),
                    )
                    for s in event.get("sources", [])
                ]
                await self.manager.send_to_user(user.id, {
                    "type": MessageType.RETRIEVAL_COMPLETE,
                    "session_id": chat_session_id,
                    "sources": event["sources"],
                })

            elif event_type == "response.complete":
                # Save assistant message
                assistant_message = await service.save_assistant_message(
                    session_id=chat_session_id,
                    content=response_content,
                    sources=sources,
                    parent_message_id=user_message.id,
                )
                if tool_calls:
                    assistant_message.tool_calls = {"calls": tool_calls}
                await self._db.commit()

                await self.manager.send_to_user(user.id, {
                    "type": MessageType.GENERATION_COMPLETE,
                    "session_id": chat_session_id,
                    "message_id": assistant_message.id,
                    "token_count": token_count,
                })

                logger.info(
                    "🏁 Agent chat completed user=%d session=%d tokens=%d tools=%d sources=%d",
                    user.id, chat_session_id, token_count, len(tool_calls), len(sources),
                )
                break

            elif event_type == "error":
                await self._send_error(
                    user.id,
                    event.get("code", "SANDBOX_ERROR"),
                    event.get("message", "Agent error"),
                )
                if not event.get("recoverable", False):
                    break

            elif event_type == "response.cancelled":
                await self.manager.send_to_user(user.id, {
                    "type": MessageType.AGENT_RESPONSE_CANCELLED,
                    "session_id": chat_session_id,
                    "run_id": event.get("run_id", ""),
                })
                break

    except asyncio.CancelledError:
        logger.info("🛑 Cancelled agent generation for user %d", user.id)
        raise
    except Exception as e:
        logger.exception("❌ Error in agent chat for user %d: %s", user.id, e)
        trace.update(metadata={"error": True, "error_message": str(e)})
        await self._send_error(user.id, "AGENT_ERROR", str(e))
    finally:
        if user.id in self._active_generations:
            del self._active_generations[user.id]
```

### 8.4 Helper Methods

```python
async def _get_session_with_assistant(
    self, session_id: int, user: TokenUser,
) -> ChatSessionORM:
    """Load chat session with assistant and LLM eagerly loaded."""
    service = ChatService(
        db=self._db, qdrant=get_qdrant(),
        embedder=get_embedder_client(), llm=get_llm_client(),
    )
    return await service.get_session(session_id, user)

def _build_sandbox_env(
    self, user: TokenUser, session: ChatSessionORM,
) -> dict[str, str]:
    """Build session-specific env vars for sandbox container."""
    assistant = session.assistant
    llm = assistant.llm if assistant else None
    return {
        "SANDBOX_LLM_PROVIDER": llm.provider if llm else "",
        "SANDBOX_LLM_MODEL": llm.model_id if llm else "",
        "SANDBOX_LLM_API_KEY": llm.api_key if llm else "",
        "SANDBOX_LLM_ENDPOINT": llm.endpoint if llm else "",
        "SANDBOX_AGENT_INSTRUCTIONS": assistant.system_prompt if assistant else "",
    }

async def _load_chat_history(
    self, session_id: int, limit: int = 20,
) -> list[dict[str, str]]:
    """Load recent chat history for context."""
    result = await self._db.execute(
        select(ChatMessageORM)
        .where(ChatMessageORM.chat_session_id == session_id)
        .order_by(ChatMessageORM.creation_date.desc())
        .limit(limit)
    )
    messages = list(reversed(result.scalars().all()))
    return [{"role": m.role, "content": m.content} for m in messages]
```

---

## 9. ChatService Modifications

The existing `ChatService` in `src/api/logic/chat_service.py` requires **no modifications**. The agent chat flow reuses:
- `ChatService.get_session()` — for session validation and assistant loading.
- `ChatService.save_user_message()` — for persisting user messages.
- `ChatService.save_assistant_message()` — for persisting agent responses with sources.
- `ChatService.get_document_titles()` — for source display names.

The existing methods handle the data layer identically for both RAG and agent modes. The agent-specific logic lives in `ChatHandler._process_agent_chat()` and `NatsStreamRelay`.

---

## 10. API Route Changes

### 10.1 New REST Endpoints

**File**: `src/api/routes/sandbox.py` (new)

```python
router = APIRouter()

@router.get("/pool", response_model=SandboxPoolStatus)
async def get_pool_status(user: AdminUser) -> SandboxPoolStatus:
    """Get current sandbox pool status (admin only)."""

@router.get("/sessions", response_model=list[SandboxSessionInfo])
async def list_sandbox_sessions(
    user: CurrentUser, db: DbSession,
) -> list[SandboxSessionInfo]:
    """List user's active sandbox sessions."""

@router.get("/sessions/{session_id}", response_model=SandboxSessionDetail)
async def get_sandbox_session(
    session_id: str, user: CurrentUser, db: DbSession,
) -> SandboxSessionDetail:
    """Get sandbox session details."""

@router.post("/sessions/{session_id}/release")
async def release_sandbox(
    session_id: str, user: CurrentUser,
) -> dict[str, str]:
    """Release a sandbox session (owner or admin)."""

@router.post("/sessions/{session_id}/cancel")
async def cancel_generation(
    session_id: str, user: CurrentUser,
) -> dict[str, str]:
    """Cancel active generation in a sandbox."""
```

### 10.2 Pydantic Response Models

**File**: `src/api/sandbox/api_models.py` (new — separate from runtime `models.py`)

```python
class SandboxPoolStatus(BaseModel):
    """Response model for sandbox pool status."""
    warm: int = Field(..., description="Warm containers available")
    assigned: int = Field(..., description="Assigned (pending activation)")
    active: int = Field(..., description="Active processing sessions")
    total: int = Field(..., description="Total managed containers")
    max_instances: int = Field(..., description="Maximum allowed instances")

class SandboxSessionInfo(BaseModel):
    """Summary of a sandbox session."""
    session_id: str
    chat_session_id: int | None
    status: str
    assigned_at: datetime
    message_count: int
    tool_calls_count: int

class SandboxSessionDetail(SandboxSessionInfo):
    """Detailed sandbox session info."""
    container_name: str
    agent_config: dict[str, Any]
    last_heartbeat_at: datetime | None
    total_tokens: int
```

### 10.3 Route Registration

In `src/api/main.py`:

```python
from api.routes import sandbox

app.include_router(
    sandbox.router, prefix="/api/v1/sandbox", tags=["Sandbox"]
)
```

---

## 11. Sandbox Runner Integration

### 11.1 Current State

The `AgentRunner` in `src/sandbox/agent_runner.py` has TODO stubs for Phase 5:
- `initialize()` — stub, needs Semantic Kernel + MCP client setup.
- `_run_agent()` — stub, yields placeholder string.
- `shutdown()` — stub, needs MCP client + kernel cleanup.

### 11.2 Phase 5 Implementation

```python
async def initialize(self) -> None:
    """Initialize Semantic Kernel agent with MCP tools."""
    from semantic_kernel import Kernel
    from semantic_kernel.agents import ChatCompletionAgent
    from semantic_kernel.connectors.ai.open_ai import OpenAIChatCompletion

    # 1. Create SK kernel with LLM service
    self._kernel = Kernel()
    self._kernel.add_service(OpenAIChatCompletion(
        ai_model_id=self._settings.llm_model,
        api_key=self._settings.llm_api_key,
        base_url=self._settings.llm_endpoint,
    ))

    # 2. Connect MCP client to gateway
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    transport = streamablehttp_client(
        self._settings.mcp_url + "/mcp",
        headers={
            "X-Sandbox-Session-Id": self._settings.session_id,
            "X-Sandbox-User-Id": str(self._settings.user_id),
        },
    )
    self._mcp_read, self._mcp_write, _ = await transport.__aenter__()
    self._mcp_session = ClientSession(self._mcp_read, self._mcp_write)
    await self._mcp_session.__aenter__()
    await self._mcp_session.initialize()

    # Register MCP tools as SK plugins
    tools = await self._mcp_session.list_tools()
    # ... register each tool as SK function

    # 3. Create chat agent
    self._agent = ChatCompletionAgent(
        kernel=self._kernel,
        instructions=self._settings.agent_instructions,
    )

    self._initialized = True
```

### 11.3 Streaming with Tool Call Events

The `_run_agent()` method must publish ALL event types to NATS — not just text tokens:

```python
async def _run_agent(self, context: QueryContext) -> AsyncIterator[str]:
    """Execute agent and publish all events to NATS stream."""
    run_id = uuid.uuid4().hex[:16]

    async for chunk in self._agent.invoke_stream(
        messages=context.query,
        thread=self._thread,
        on_intermediate_message=lambda msg: self._handle_intermediate(msg, run_id),
    ):
        for item in chunk.items:
            if hasattr(item, "text") and item.text:
                await self._publish_event("text.delta", {
                    "data": item.text,
                    "run_id": run_id,
                })
                yield item.text

    # Publish sources if RAG search tool was called
    if self._pending_sources:
        await self._publish_event("sources", {
            "sources": self._pending_sources,
        })
        self._pending_sources = []
```

The `_handle_intermediate` callback captures tool calls:

```python
async def _handle_intermediate(self, msg, run_id: str) -> None:
    """Handle intermediate messages (tool calls) during streaming."""
    for item in msg.items:
        if isinstance(item, FunctionCallContent):
            self.metrics.tool_calls_count += 1
            await self._publish_event("tool_call.start", {
                "call_id": item.id,
                "tool_name": item.name,
                "args": json.loads(item.arguments) if item.arguments else {},
                "run_id": run_id,
            })
        elif isinstance(item, FunctionResultContent):
            await self._publish_event("tool_call.result", {
                "call_id": item.call_id,
                "result": str(item.result)[:10000],  # Truncate large results
                "success": True,
                "duration_ms": 0,  # TODO: track per-call timing
                "run_id": run_id,
            })
```

---

## 12. Streaming Implementation Detail

### 12.1 Token-by-Token Flow

```
LLM Provider
    │
    │ SSE: data: {"choices":[{"delta":{"content":"Hello"}}]}
    ▼
AgentRunner._run_agent()
    │
    │ yield "Hello"
    ▼
AgentRunner._publish_event("text.delta", {"data": "Hello"})
    │
    │ NATS publish: sandbox.sess_42.stream
    │   payload: {"type": "text.delta", "data": "Hello", "run_id": "abc123", "seq": 1}
    ▼
NatsStreamRelay.relay_session()
    │
    │ ordered consumer receives message
    │ maps to WebSocket event
    ▼
ConnectionManager.send_to_user()
    │
    │ WebSocket JSON: {"type": "agent.text.delta", "session_id": 42, "delta": "Hello"}
    ▼
WebUI renders token
```

### 12.2 Backpressure Handling

**150ms Delta Throttle** (from Moltbot pattern, recommended by production research):

The `NatsStreamRelay` coalesces rapid text deltas to prevent WebSocket flooding:

```python
class NatsStreamRelay:
    THROTTLE_MS = 150  # Minimum ms between WebSocket text sends

    async def relay_session(self, session_id: str) -> AsyncIterator[dict[str, Any]]:
        """Relay sandbox stream events, throttling text deltas."""
        text_buffer = ""
        last_text_send = 0

        async for msg in self._subscription.messages:
            event = json.loads(msg.data)

            if event["type"] == "text.delta":
                text_buffer += event["data"]
                now_ms = time.monotonic() * 1000
                if now_ms - last_text_send >= self.THROTTLE_MS or len(text_buffer) > 100:
                    yield {"type": "text.delta", "data": text_buffer, **event}
                    text_buffer = ""
                    last_text_send = now_ms
            else:
                # Non-text events: flush buffer first, then yield
                if text_buffer:
                    yield {"type": "text.delta", "data": text_buffer}
                    text_buffer = ""
                    last_text_send = time.monotonic() * 1000
                yield event

            if event["type"] in ("response.complete", "error", "response.cancelled"):
                if text_buffer:
                    yield {"type": "text.delta", "data": text_buffer}
                break
```

---

## 13. Tool Call Visualization

### 13.1 Event Sequence for a Tool Call

```
→ agent.tool_call.start    {call_id: "tc_001", tool_name: "search_documents",
                            args: {query: "revenue Q4", collection: "group_eng"}}

→ agent.tool_call.result   {call_id: "tc_001", result: "[{doc_id: 42, score: 0.92, ...}]",
                            success: true, duration_ms: 450}
```

### 13.2 Recommended UI Rendering

```
┌─ 🔍 search_documents ────────────────────┐
│  Query: "revenue Q4"                      │  ← tool_call.start (args)
│  Collection: group_eng                    │
│  ✅ Found 3 results (450ms)              │  ← tool_call.result
│  [▼ Show details]                         │  ← expandable
└───────────────────────────────────────────┘
```

The WebUI (separate repo) will render these as collapsible cards:
- **Pending**: Spinner + tool name + args
- **Completed**: Green check + summary + expandable details
- **Failed**: Red X + error message + retry hint

### 13.3 Tool Result Truncation

Large tool results (e.g., search results, file contents) are truncated to 10KB in the NATS event. The full result is available via the REST API if needed. This prevents WebSocket message size issues.

---

## 14. Error Handling

### 14.1 Error Categories

| Error | Where | Recovery | User Impact |
|-------|-------|----------|-------------|
| **Sandbox pool exhausted** | `SandboxManager.assign()` | Fall back to non-sandbox RAG | Transparent — uses existing RAG |
| **Sandbox container crash** | Health monitor | Auto-release, assign new sandbox on next msg | Error message, then auto-recovery |
| **NATS disconnect** | `NatsStreamRelay` | Reconnect via nats-py auto-reconnect | Brief delay, then resumes |
| **LLM provider error** | `AgentRunner` | Publish `{type: "error", recoverable: true}` | Error shown, can retry |
| **LLM timeout** | `AgentRunner` | Publish `{type: "error", recoverable: false}` | Error shown, generation stops |
| **MCP tool failure** | `AgentRunner` | Publish `tool_call.result` with `success: false` | Tool shows as failed in UI |
| **Session timeout** | Reconciliation loop | Release sandbox, replenish pool | Session ends cleanly |
| **WebSocket disconnect** | `ChatHandler` | Cancel active task, cleanup | Normal disconnect handling |
| **DB persistence failure** | `ChatHandler` | Log error, continue (degraded mode) | Messages not saved |

### 14.2 Resilience Pattern Compliance

Per `.claude/rules/resilience.md`, the new components follow:

```python
# In API lifespan (src/api/main.py)
try:
    sandbox_mgr = SandboxManager(backend, settings, nats)
    await sandbox_mgr.start()
    logger.info("🏗️ SandboxManager started")
except Exception as e:
    logger.warning(f"⚠️ SandboxManager startup failed: {e}")
    logger.info("🔄 Will retry SandboxManager in background...")
    # Agent mode degrades to RAG fallback
```

Every external connection (NATS subscribe, Docker SDK) uses try/except with background retry.

---

## 15. Graceful Degradation

When sandbox infrastructure is unavailable, the system degrades gracefully:

| Scenario | Behavior |
|----------|----------|
| **SandboxManager not started** | `mode=agent` falls back to `mode=chat` (in-process RAG) |
| **Warm pool empty + max instances reached** | Falls back to `mode=chat` with warning log |
| **NATS not connected** | SandboxManager runs in degraded mode (no lifecycle events published) |
| **Sandbox container unhealthy** | Release and reassign on next message |
| **MCP Gateway unreachable** | Agent runs without tools, text-only responses |

The fallback is seamless: `_process_agent_chat()` catches `RuntimeError` from `assign()` and calls `_process_chat()` instead.

---

## 16. Database Schema

### 16.1 Existing Tables (No Changes)

The `sandbox_sessions` and `sandbox_events` tables were already created in Phase 4:
- `src/proto/internal/sandbox.proto` — defines the schema (Source of Truth).
- `src/migration/migrations/versions/` — Alembic migration already exists.

### 16.2 New: ChatMode Enum Extension

```python
# Alembic migration: add 'agent' value to ChatMode enum
def upgrade() -> None:
    op.execute("ALTER TYPE chatmode ADD VALUE IF NOT EXISTS 'agent'")
```

**File**: `src/migration/migrations/versions/YYYYMMDD_HHMMSS_add_agent_chat_mode.py`

### 16.3 Existing Table Usage

The `chat_messages` table already has:
- `tool_calls JSONB` — stores agent tool call metadata (populated by `_process_agent_chat`).
- `retrieval_context JSONB` — stores source count (populated by `save_assistant_message`).

No schema changes needed for the chat_messages table.

---

## 17. Docker Compose Changes

### 17.1 NATS Stream Creation

Add JetStream stream creation to NATS startup. In `docker-compose.yml`, add a NATS init script:

```yaml
nats:
  volumes:
    - ./config/nats/nats.conf:/nats.conf
    # Add JetStream storage
    - nats-data:/data
  command: ["--config", "/nats.conf", "--jetstream", "--store_dir", "/data"]
```

The `sandbox-stream` JetStream stream is created programmatically by `SandboxManager.start()` on API startup (idempotent — uses `add_stream` which is a no-op if stream exists).

### 17.2 API Service Changes

```yaml
# docker-compose-host.yml additions for API
echomind-api:
  environment:
    # Sandbox settings (passed from .env)
    - SANDBOX_POOL_SIZE=${SANDBOX_POOL_SIZE:-3}
    - SANDBOX_MAX_INSTANCES=${SANDBOX_MAX_INSTANCES:-15}
    - SANDBOX_IMAGE=${SANDBOX_IMAGE:-gsantopaolo/echomind-agent-sandbox:0.1.0-beta.1}
    - SANDBOX_NATS_URL=${SANDBOX_NATS_URL:-nats://nats:4222}
    - SANDBOX_MCP_URL=${SANDBOX_MCP_URL:-http://mcp-gateway:8100}
  volumes:
    # Docker socket for container management
    - /var/run/docker.sock:/var/run/docker.sock:ro
  networks:
    - backend
    - sandbox  # API needs sandbox network to create containers on it
```

---

## 18. Files to Create/Modify

### 18.1 New Files

| # | File | Purpose | LOC Est. |
|---|------|---------|----------|
| 1 | `src/api/sandbox/nats_relay.py` | NATS stream-to-WebSocket relay with throttling | 180 |
| 2 | `src/api/sandbox/api_models.py` | Pydantic response models for REST endpoints | 60 |
| 3 | `src/api/routes/sandbox.py` | REST endpoints for sandbox management | 120 |
| 4 | `src/migration/migrations/versions/XXXXXX_add_agent_chat_mode.py` | ChatMode enum extension | 20 |
| 5 | `tests/unit/api/sandbox/test_nats_relay.py` | NatsStreamRelay unit tests | 200 |
| 6 | `tests/unit/api/routes/test_sandbox_routes.py` | REST endpoint tests | 150 |
| 7 | `tests/unit/api/websocket/test_agent_chat.py` | Agent chat handler tests | 250 |
| 8 | `tests/unit/sandbox/test_agent_runner_phase5.py` | AgentRunner SK integration tests | 200 |

### 18.2 Modified Files

| # | File | Changes | Details |
|---|------|---------|---------|
| 1 | `src/api/websocket/chat_handler.py` | Add `_process_agent_chat()`, new MessageType values, helper methods | ~150 LOC added |
| 2 | `src/api/main.py` | Add SandboxManager + NatsStreamRelay to lifespan, register sandbox routes | ~30 LOC added |
| 3 | `src/proto/public/chat.proto` | Add `CHAT_MODE_AGENT`, new WsAgent* messages | ~50 LOC added |
| 4 | `src/sandbox/agent_runner.py` | Implement SK agent, MCP client, tool call events | ~200 LOC replacing stubs |
| 5 | `src/sandbox/main.py` | Wire `_handle_control` cancel/config_update | ~30 LOC |
| 6 | `src/api/sandbox/manager.py` | Add JetStream stream creation in `start()` | ~20 LOC |
| 7 | `src/api/dependencies.py` | Add `get_sandbox_manager()`, `get_nats_relay()` DI functions | ~30 LOC |

---

## 19. Dependencies

### 19.1 New Python Packages

| Package | Version | Service | Purpose |
|---------|---------|---------|---------|
| `semantic-kernel` | `>=1.20.0` | sandbox | Agent framework (SK agent, LLM connectors) |
| `mcp` | `>=1.9.0` | sandbox | MCP client for connecting to gateway |

### 19.2 Already Installed (No Changes)

| Package | Service | Used For |
|---------|---------|----------|
| `nats-py` | API, sandbox | JetStream pub/sub |
| `docker` | API | Container management (via `docker_backend.py`) |
| `pydantic` / `pydantic-settings` | all | Configuration and models |
| `sqlalchemy[asyncio]` | API | Database ORM |

---

## 20. Unit Test Plan

### 20.1 Test Structure

```
tests/unit/
├── api/
│   ├── sandbox/
│   │   ├── test_nats_relay.py          # NatsStreamRelay tests
│   │   └── __init__.py
│   ├── routes/
│   │   └── test_sandbox_routes.py      # REST endpoint tests
│   └── websocket/
│       └── test_agent_chat.py          # ChatHandler agent tests
└── sandbox/
    └── test_agent_runner_phase5.py     # AgentRunner SK tests
```

### 20.2 Test Cases

#### `test_nats_relay.py` (~15 tests)

| Test | What's Tested |
|------|---------------|
| `test_relay_text_delta_events` | Text delta events forwarded correctly |
| `test_relay_tool_call_events` | tool_call.start and tool_call.result forwarded |
| `test_relay_sources_event` | Sources event mapped to RetrievedSource |
| `test_relay_reasoning_delta` | Reasoning events forwarded |
| `test_relay_complete_breaks_loop` | response.complete stops iteration |
| `test_relay_error_unrecoverable_breaks` | Non-recoverable error breaks loop |
| `test_relay_error_recoverable_continues` | Recoverable error does not break |
| `test_relay_cancelled_breaks` | response.cancelled stops iteration |
| `test_cancel_publishes_to_input` | Cancel sends message on input subject |
| `test_publish_query_format` | Query published with correct JSON format |
| `test_throttle_coalesces_rapid_deltas` | Text buffer coalesces within 150ms |
| `test_throttle_flushes_on_non_text` | Buffer flushed before tool events |
| `test_throttle_flushes_on_complete` | Buffer flushed on completion |
| `test_handles_nats_disconnect` | Graceful handling of NATS disconnect |
| `test_handles_malformed_json` | Skips invalid JSON messages |

#### `test_agent_chat.py` (~20 tests)

| Test | What's Tested |
|------|---------------|
| `test_agent_mode_routes_to_sandbox` | mode=agent dispatches to _process_agent_chat |
| `test_chat_mode_uses_existing_rag` | mode=chat uses existing _process_chat |
| `test_search_mode_unchanged` | mode=search still works |
| `test_sandbox_assignment_on_first_message` | First message triggers assign |
| `test_subsequent_messages_reuse_sandbox` | Second message uses existing sandbox |
| `test_sandbox_assigned_event_sent` | client receives agent.sandbox_assigned |
| `test_text_delta_relayed_to_websocket` | text.delta events reach client |
| `test_tool_call_events_relayed` | tool_call events reach client |
| `test_sources_event_relayed` | sources forwarded as retrieval.complete |
| `test_generation_complete_saves_messages` | Messages saved to DB on completion |
| `test_tool_calls_saved_in_jsonb` | tool_calls JSONB populated |
| `test_cancel_forwards_to_sandbox` | chat.cancel sends NATS cancel |
| `test_websocket_disconnect_during_relay` | Clean handling of WS disconnect |
| `test_sandbox_error_forwarded_to_client` | Error events reach WebSocket |
| `test_pool_exhausted_falls_back_to_rag` | RuntimeError → fallback to chat mode |
| `test_chat_history_loaded` | Recent messages sent to sandbox |
| `test_build_sandbox_env` | Correct env vars built from session |
| `test_run_id_present_in_events` | All agent events include run_id |
| `test_user_message_saved_before_relay` | User message saved before NATS publish |
| `test_concurrent_users_independent` | Two users don't interfere |

#### `test_sandbox_routes.py` (~10 tests)

| Test | What's Tested |
|------|---------------|
| `test_get_pool_status_admin_only` | Non-admin gets 403 |
| `test_get_pool_status_returns_counts` | Correct warm/active/total |
| `test_list_sessions_filters_by_user` | Users see only their sessions |
| `test_get_session_detail` | Full session info returned |
| `test_get_session_not_found` | 404 for non-existent session |
| `test_release_sandbox_owner_only` | Non-owner gets 403 |
| `test_release_sandbox_success` | Sandbox released correctly |
| `test_cancel_generation_success` | Cancel publishes NATS message |
| `test_cancel_non_existent_session` | 404 for bad session_id |
| `test_admin_can_release_any` | Admin can release other users' sessions |

#### `test_agent_runner_phase5.py` (~15 tests)

| Test | What's Tested |
|------|---------------|
| `test_initialize_creates_kernel` | SK kernel created with LLM service |
| `test_initialize_connects_mcp` | MCP client connects to gateway URL |
| `test_process_query_publishes_tokens` | Tokens published to stream subject |
| `test_process_query_publishes_complete` | Complete event published on finish |
| `test_process_query_publishes_error` | Error event published on failure |
| `test_tool_call_events_published` | tool_call.start/result events emitted |
| `test_metrics_incremented` | message_count, tool_calls_count tracked |
| `test_run_id_unique_per_query` | Each query gets distinct run_id |
| `test_large_result_truncated` | Tool results >10KB truncated |
| `test_shutdown_closes_mcp` | MCP session closed on shutdown |
| `test_shutdown_clears_initialized` | _initialized set to False |
| `test_not_initialized_raises` | RuntimeError if process_query before init |
| `test_conversation_history_passed` | History included in agent invocation |
| `test_sources_collected_from_search_tool` | RAG tool results become sources |
| `test_cancellation_aborts_stream` | Cancelled flag stops agent iteration |

### 20.3 Mocking Strategy

| Dependency | Mock | Pattern |
|------------|------|---------|
| Docker SDK | `unittest.mock.AsyncMock` | Mock `SandboxBackend` interface |
| NATS client | `unittest.mock.AsyncMock` | Mock `NATSClient.publish()`, `JetStreamContext.subscribe()` |
| NATS subscription | `AsyncMock` with `messages` as `AsyncIterator` | Yield test messages |
| Database | `AsyncMock(AsyncSession)` | Mock execute/flush/commit |
| Semantic Kernel | `AsyncMock(ChatCompletionAgent)` | Mock `invoke_stream()` |
| MCP client | `AsyncMock(ClientSession)` | Mock `list_tools()`, `call_tool()` |
| WebSocket | `AsyncMock` | Mock `ConnectionManager.send_to_user()` |

---

## 21. Implementation Order

Each step depends on the previous ones. Steps within a group can be partially parallelized.

```
Step 1: Proto + Migration (0.5 day)
  ├─ src/proto/public/chat.proto (add CHAT_MODE_AGENT + WsAgent* messages)
  ├─ Run ./scripts/generate_proto.sh
  └─ src/migration/migrations/versions/XXXXXX_add_agent_chat_mode.py

Step 2: NATS Relay (1 day)
  ├─ src/api/sandbox/nats_relay.py (NatsStreamRelay class)
  ├─ src/api/sandbox/api_models.py (response Pydantic models)
  └─ tests/unit/api/sandbox/test_nats_relay.py

Step 3: ChatHandler Integration (1.5 days)
  ├─ src/api/websocket/chat_handler.py (add _process_agent_chat + helpers)
  ├─ src/api/dependencies.py (add get_sandbox_manager, get_nats_relay)
  └─ tests/unit/api/websocket/test_agent_chat.py

Step 4: REST Endpoints + API Wiring (0.5 day)
  ├─ src/api/routes/sandbox.py (REST endpoints)
  ├─ src/api/main.py (SandboxManager + NatsRelay in lifespan, route registration)
  └─ tests/unit/api/routes/test_sandbox_routes.py

Step 5: Sandbox AgentRunner (1.5 days)
  ├─ src/sandbox/agent_runner.py (implement SK agent, MCP client, tool events)
  ├─ src/sandbox/main.py (wire cancel/config_update in _handle_control)
  └─ tests/unit/sandbox/test_agent_runner_phase5.py

Step 6: Integration Testing (1 day)
  ├─ Manual: start sandbox, send query via WebSocket, verify streaming
  ├─ Manual: verify tool call events appear in WebSocket stream
  ├─ Manual: verify mode=chat still works unchanged
  ├─ Manual: verify pool exhaustion falls back to RAG
  └─ Manual: verify cancel stops generation
```

**Total: ~6 days of implementation**

---

## 22. Evaluation Scorecard

| # | Criterion | Score (1-10) | Justification |
|---|-----------|:---:|---------------|
| 1 | **Backward Compatibility** | 9 | Mode-based routing keeps existing chat/search paths 100% untouched. Only risk is proto regeneration for new ChatMode enum value — mitigated by `IF NOT EXISTS` in migration. |
| 2 | **Streaming Latency** | 8 | NATS adds ~1-2ms per message hop. 150ms throttle for text deltas prevents WebSocket flooding. Total added latency <5ms per token vs current in-process path (excluding throttle buffer). Source: [NATS JetStream Docs](https://docs.nats.io/nats-concepts/jetstream). |
| 3 | **Fault Tolerance** | 8 | Heartbeat monitoring + reconciliation loop handle container crashes. Pool exhaustion gracefully degrades to RAG. NATS ordered consumers auto-replay on reconnect. Edge case: API crash during relay loses in-flight tokens (memory-backed stream). |
| 4 | **Security** | 7 | Network isolation + NATS subject scoping per session. MCP trusts all callers on internal network. JWT auth deferred to Phase 8 (Auth Hardening). |
| 5 | **Protocol Alignment** | 9 | AG-UI event types adopted for tool calls and streaming. Industry-standard typed content blocks with start/delta/end lifecycle. Compatible with OpenAI, Anthropic, and Vercel AI SDK patterns. Source: [AG-UI Protocol](https://docs.ag-ui.com/). |
| 6 | **Testability** | 9 | All components mockable via interfaces. Docker SDK mocked via `SandboxBackend` abstract class. NATS mocked via fake publisher/subscriber. ~60 unit tests with 100% coverage target. |
| 7 | **Operational Readiness** | 7 | Health checks, heartbeat monitoring, pool status REST endpoint. Missing: Grafana dashboard for sandbox pool (deferred to Phase 6 Observability). Missing: automatic capacity scaling (single-host limitation). |

---

## Citations and Sources

### Primary Sources (Code Analysis)
- `src/api/websocket/chat_handler.py` — Current WebSocket handler, message types, RAG pipeline
- `src/api/logic/chat_service.py` — ChatService retrieval, streaming, persistence
- `src/api/sandbox/manager.py` — SandboxManager state machine, pool management
- `src/api/sandbox/docker_backend.py` — Docker SDK container lifecycle
- `src/sandbox/main.py` — SandboxAgent NATS integration, warm/active modes
- `src/sandbox/agent_runner.py` — AgentRunner stubs (Phase 5 TODOs)
- `src/api/main.py` — API lifespan, connection resilience pattern
- `src/proto/public/chat.proto` — ChatMode enum, WebSocket messages
- `src/proto/internal/sandbox.proto` — SandboxSession, SandboxEvent

### External References
- [AG-UI Protocol — Agent User Interaction Protocol](https://docs.ag-ui.com/) — Event types, transport, state management
- [Master the 17 AG-UI Event Types — CopilotKit, 2025](https://www.copilotkit.ai/blog/master-the-17-ag-ui-event-types-for-building-agents-the-right-way)
- [NATS JetStream Consumers — NATS.io, 2025](https://docs.nats.io/nats-concepts/jetstream/consumers) — Ordered consumers, ephemeral consumers
- [NATS Message Ordering Guarantee — GitHub Discussion #5180](https://github.com/nats-io/nats-server/discussions/5180)
- [Semantic Kernel Agent Streaming — Microsoft Learn, 2025](https://learn.microsoft.com/en-us/semantic-kernel/frameworks/agent/agent-streaming)
- [Backpressure in WebSocket Streams — Skyline Codes, 2025](https://skylinecodes.substack.com/p/backpressure-in-websocket-streams)
- [Streaming AI Responses: WebSockets, SSE, and gRPC — Medium, 2025](https://medium.com/@pranavprakash4777/streaming-ai-responses-with-websockets-sse-and-grpc-which-one-wins-a481cab403d3)
- [Docker SDK for Python — Docker, 2025](https://docker-py.readthedocs.io/en/stable/)
- [FastAPI WebSockets — FastAPI, 2025](https://fastapi.tiangolo.com/advanced/websockets/)
- [Production-Grade Agentic Apps with AG-UI — DataDrivenInvestor, 2026](https://medium.datadriveninvestor.com/production-grade-agentic-apps-with-ag-ui-real-time-streaming-guide-2026-5331c452684a)
