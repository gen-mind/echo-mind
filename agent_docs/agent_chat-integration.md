# Chat/WebSocket to Sandboxed Agent Integration Design

> **Date**: 2026-02-16
> **Based on**: Direct source code analysis of EchoMind API, WebSocket, ChatService, proto definitions, sandbox architecture docs, and web research
> **Status**: Implementation-ready
> **Confidence**: High (primary sources -- code reads + official docs)

---

## Executive Summary

This document designs the integration layer between EchoMind's existing WebSocket chat system and the new sandboxed agent architecture. The core change: instead of the API service running the RAG pipeline in-process (embed -> search -> stream LLM), the API becomes a **message router** that assigns an ephemeral Docker container (sandbox) to each session and relays messages via NATS JetStream.

### Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Transport: Client to API | WebSocket (existing) | Already implemented, bidirectional, proven |
| Transport: API to Sandbox | NATS JetStream pub/sub | Already deployed, decoupled, supports streaming |
| Transport: Sandbox to MCP | Streamable HTTP | Standard MCP protocol, no auth initially |
| Streaming granularity | Typed content blocks | Industry standard (OpenAI, Anthropic, Google ADK) |
| Session routing | Session-pinned sandbox | Once assigned, all messages for session route to same container |
| Backward compatibility | Mode-based routing | `mode=chat` uses existing RAG; `mode=agent` uses sandbox |

---

## a. Current Architecture Analysis

### How Chat Currently Works

The existing chat system is a synchronous in-process RAG pipeline. The API service handles everything: query embedding, vector search, LLM streaming, and message persistence.

**Key files:**
- `/Users/gp/Developer/echo-mind/src/api/main.py` -- WebSocket endpoint at `/api/v1/ws/chat`
- `/Users/gp/Developer/echo-mind/src/api/websocket/chat_handler.py` -- `ChatHandler` class, message loop
- `/Users/gp/Developer/echo-mind/src/api/websocket/manager.py` -- `ConnectionManager`, user/session tracking
- `/Users/gp/Developer/echo-mind/src/api/logic/chat_service.py` -- `ChatService`, RAG orchestration
- `/Users/gp/Developer/echo-mind/src/api/logic/llm_client.py` -- `LLMClient`, multi-provider streaming
- `/Users/gp/Developer/echo-mind/src/api/logic/embedder_client.py` -- `EmbedderClient`, gRPC to embedder
- `/Users/gp/Developer/echo-mind/src/api/logic/permissions.py` -- `PermissionChecker`, RBAC for collections
- `/Users/gp/Developer/echo-mind/src/api/routes/chat.py` -- REST endpoints for sessions/messages
- `/Users/gp/Developer/echo-mind/src/proto/public/chat.proto` -- Proto definitions for all chat messages

### Current Message Flow

```
User         WebUI         API (:8000)        Embedder     Qdrant      LLM Provider
 |             |               |                  |           |              |
 |--type msg-->|               |                  |           |              |
 |             |--WS: chat.start (session_id, query, mode)-->|              |
 |             |               |                  |           |              |
 |             |               |---1. Validate session (DB)---|              |
 |             |               |                  |           |              |
 |             |<--WS: retrieval.start------------|           |              |
 |             |               |                  |           |              |
 |             |               |---2. embed(query) via gRPC-->|              |
 |             |               |<--vector---------+           |              |
 |             |               |                  |           |              |
 |             |               |---3. search(vector, collections)----------->|
 |             |               |<--sources (chunks + scores)-+              |
 |             |               |                  |           |              |
 |             |<--WS: retrieval.complete (sources)           |              |
 |             |               |                  |           |              |
 |             |               |---4. build prompt (system + context + query)|
 |             |               |                  |           |              |
 |             |               |---5. stream_completion(messages)----------->|
 |             |               |<--token-by-token SSE stream-+              |
 |             |               |                  |           |              |
 |             |<--WS: generation.token (repeated)|           |              |
 |<--render----|               |                  |           |              |
 |             |               |                  |           |              |
 |             |               |---6. save_user_message (DB)--|              |
 |             |               |---7. save_assistant_message + sources (DB)--|
 |             |               |                  |           |              |
 |             |<--WS: generation.complete (message_id, token_count)         |
 |<--done------|               |                  |           |              |
```

**Confidence: High** -- Traced directly from source code.

### Current WebSocket Message Types

Defined in `ChatHandler.MessageType` enum and `chat.proto`:

| Direction | Type | Payload | Purpose |
|-----------|------|---------|---------|
| Client->Server | `chat.start` | `{session_id, query, mode}` | Start chat query |
| Client->Server | `chat.cancel` | `{session_id}` | Cancel active generation |
| Client->Server | `ping` | -- | Keepalive |
| Server->Client | `retrieval.start` | `{session_id, query, rephrased_query}` | Retrieval phase began |
| Server->Client | `retrieval.complete` | `{session_id, sources[]}` | Retrieved sources |
| Server->Client | `generation.token` | `{session_id, token}` | Streaming LLM token |
| Server->Client | `generation.complete` | `{session_id, message_id, token_count}` | Generation done |
| Server->Client | `error` | `{code, message}` | Error occurred |
| Server->Client | `pong` | -- | Keepalive response |

### Session Management (Current)

- `ChatSession` ORM: `id`, `user_id`, `assistant_id`, `title`, `mode` (chat|search), `message_count`, `last_message_at`
- `ChatMessage` ORM: `id`, `chat_session_id`, `role` (user|assistant|system), `content`, `token_count`, `tool_calls` (JSONB), `retrieval_context` (JSONB)
- `ChatMessageDocument`: Links messages to source documents with `relevance_score`
- `ChatMessageFeedback`: User thumbs up/down on messages
- Sessions are created via REST `POST /api/v1/chat/sessions`, then used in WebSocket
- `ConnectionManager` tracks active WebSocket connections per user and per session
- One active generation per user at a time (cancels previous if new `chat.start` arrives)

### Current Streaming Mechanism

The `LLMClient` supports three providers, all yielding tokens via `AsyncIterator[str]`:
1. **OpenAI-compatible** (TGI, vLLM, Ollama, OpenAI): SSE streaming via `httpx.stream()`
2. **Anthropic**: SSE streaming via `httpx.stream()` with Anthropic event format
3. **Anthropic Token** (Claude CLI): Non-streaming, yields complete response at once

Tokens flow: `LLMClient.stream_completion()` -> `ChatService.stream_response()` -> `ChatHandler._process_chat()` -> `ConnectionManager.send_to_user()` -> WebSocket JSON frame.

### Current NATS Usage in API

The API currently uses NATS **only for publishing** events to other services (connector sync triggers, document processing). It does NOT use NATS for receiving messages or for chat. The `JetStreamPublisher` in `echomind_lib/db/nats_publisher.py` is the sole NATS integration point.

---

## b. New Architecture: API to Sandbox Communication

### New Message Flow

```
User      WebUI     API (:8000)      NATS JetStream      Sandbox        MCP Server     LLM
 |          |           |                  |                  |               |            |
 |--msg---->|           |                  |                  |               |            |
 |          |--WS: chat.start (session_id, query, mode="agent")              |            |
 |          |           |                  |                  |               |            |
 |          |           |---1. SandboxManager.assign(sid)--->|               |            |
 |          |           |   (get warm container, inject env)  |               |            |
 |          |           |<--sandbox state (container_id)------|               |            |
 |          |           |                  |                  |               |            |
 |          |<--WS: agent.sandbox_assigned |                  |               |            |
 |          |           |                  |                  |               |            |
 |          |           |---2. PUB sandbox.{sid}.input------->|              |            |
 |          |           |   {type: query, query, context}     |              |            |
 |          |           |                  |                  |               |            |
 |          |           |                  |---3. SUB .input->|               |            |
 |          |           |                  |                  |               |            |
 |          |           |                  |                  |--MCP: skills_list()------->|
 |          |           |                  |                  |<-tools list---|            |
 |          |           |                  |                  |               |            |
 |          |           |                  |                  |--LLM: stream(prompt)------>|
 |          |           |                  |                  |<-tokens-------+            |
 |          |           |                  |                  |               |            |
 |          |           |<--4. PUB sandbox.{sid}.stream-------|               |            |
 |          |           |   {type: token, data: "Hello"}      |               |            |
 |          |<--WS: generation.token-------|                  |               |            |
 |<-render--|           |                  |                  |               |            |
 |          |           |                  |                  |               |            |
 |          |           |<--5. PUB .stream {type: tool_call.start, tool, args}|            |
 |          |<--WS: agent.tool_call.start--|                  |               |            |
 |          |           |                  |                  |--MCP: tool()-->|            |
 |          |           |                  |                  |<-result--------|            |
 |          |           |<--6. PUB .stream {type: tool_call.result, result}   |            |
 |          |<--WS: agent.tool_call.result-|                  |               |            |
 |          |           |                  |                  |               |            |
 |          |           |<--7. PUB .stream {type: complete, message_id}       |            |
 |          |<--WS: generation.complete----|                  |               |            |
 |<-done----|           |                  |                  |               |            |
 |          |           |                  |                  |               |            |
 |          |           |---8. save messages to DB------------|               |            |
 |          |           |---9. SandboxManager.release(sid)--->|               |            |
```

**Confidence: High** -- Based on sandbox container design doc + NATS patterns.

### NATS Subject Design

```
# Per-session subjects (ephemeral, exist while sandbox is active)
sandbox.{session_id}.input       # API -> Sandbox: user messages, commands
sandbox.{session_id}.stream      # Sandbox -> API: streaming tokens, tool calls
sandbox.{session_id}.output      # Sandbox -> API: final structured responses
sandbox.{session_id}.control     # API -> Sandbox: cancel, shutdown, config updates
sandbox.{session_id}.health      # Sandbox -> API: heartbeat (every 15s)

# Management subjects (persistent)
sandbox.mgmt.assign              # Request sandbox assignment
sandbox.mgmt.release             # Release sandbox
sandbox.mgmt.status              # Pool status query

# Audit stream (persistent, 7-day retention)
sandbox.audit.>                  # All sandbox lifecycle events
```

`session_id` format: `sess_{uuid_hex[:16]}` -- e.g., `sess_a1b2c3d4e5f6g7h8`. This is distinct from the integer `chat_session_id` in the database. The mapping is stored in `sandbox_sessions.chat_session_id`.

### JetStream Stream Configuration

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
    "storage": "memory",          # Ephemeral -- no disk persistence needed
    "discard": "old",
}

# File-backed stream for audit trail
SANDBOX_AUDIT_STREAM_CONFIG = {
    "name": "sandbox-audit",
    "subjects": ["sandbox.audit.>"],
    "retention": "limits",
    "max_age": 7 * 24 * 3600_000_000_000,  # 7 days
    "storage": "file",
}
```

### Streaming: Token-by-Token Output Flow

The sandbox publishes each event to `sandbox.{session_id}.stream`. The API subscribes to this subject and relays events to the WebSocket client. The relay is a simple async loop:

```python
# In API: relay sandbox stream to WebSocket
sub = await js.subscribe(
    f"sandbox.{session_id}.stream",
    stream="sandbox-stream",
    ordered_consumer=True,  # Guarantees ordering without acks
)

async for msg in sub.messages:
    event = json.loads(msg.data)
    event_type = event["type"]

    if event_type == "token":
        await ws_manager.send_to_user(user_id, {
            "type": "generation.token",
            "session_id": chat_session_id,
            "token": event["data"],
        })
    elif event_type == "tool_call.start":
        await ws_manager.send_to_user(user_id, {
            "type": "agent.tool_call.start",
            "session_id": chat_session_id,
            "tool_name": event["tool_name"],
            "tool_args": event.get("args", {}),
            "call_id": event["call_id"],
        })
    elif event_type == "tool_call.result":
        await ws_manager.send_to_user(user_id, {
            "type": "agent.tool_call.result",
            "session_id": chat_session_id,
            "call_id": event["call_id"],
            "result": event["result"],
            "duration_ms": event.get("duration_ms"),
        })
    elif event_type == "complete":
        await ws_manager.send_to_user(user_id, {
            "type": "generation.complete",
            "session_id": chat_session_id,
            "message_id": event.get("message_id"),
            "token_count": event.get("token_count", 0),
        })
        break
    elif event_type == "error":
        await ws_manager.send_to_user(user_id, {
            "type": "error",
            "code": event.get("code", "SANDBOX_ERROR"),
            "message": event.get("message", "Agent error"),
        })
        break
```

**Confidence: High** -- NATS ordered consumers guarantee message ordering per subject without explicit acking [Source -- NATS docs, 2025].

### Session Lifecycle

```
1. CREATE       Client sends WS: chat.start with mode="agent"
                API creates sandbox session record in DB (status=assigned)

2. ASSIGN       SandboxManager.assign() picks warm container, injects env vars
                Sandbox connects to NATS, publishes health=ready
                API receives ready -> updates DB status=active

3. STREAM       API publishes query to sandbox.{sid}.input
                Sandbox processes (LLM + MCP tools)
                Sandbox publishes tokens/events to sandbox.{sid}.stream
                API relays events to WebSocket client

4. COMPLETE     Sandbox publishes {type: complete} on stream subject
                API saves user + assistant messages to DB
                API sends generation.complete to WebSocket

5. IDLE         Sandbox waits for next message on input subject
                Heartbeat continues every 15s
                If idle > SANDBOX_IDLE_TIMEOUT (300s), API sends shutdown

6. DESTROY      API sends {type: shutdown} on sandbox.{sid}.control
                Sandbox drains NATS connections (30s grace)
                SandboxManager destroys container, updates DB status=destroyed
                Pool replenishment creates replacement warm container
```

---

## c. SandboxManager Design

The `SandboxManager` lives inside the API service. It uses the Docker SDK to manage container lifecycle and maintains an in-memory state map with DB persistence for recovery.

**File**: `src/api/sandbox/manager.py` (already sketched in `agent_sandbox-containers.md`)

### Class Design

```python
# src/api/sandbox/manager.py

class SandboxSettings(BaseSettings):
    """Sandbox manager configuration."""
    pool_size: int = Field(3, description="Warm pool target size")
    max_instances: int = Field(15, description="Max concurrent sandboxes")
    idle_timeout: int = Field(300, description="Seconds before idle sandbox recycled")
    session_timeout: int = Field(3600, description="Max session duration in seconds")
    image: str = Field("gsantopaolo/echomind-sandbox:latest")
    network: str = Field("sandbox")
    cpu_limit: float = Field(2.0)
    memory_limit: str = Field("2g")
    model_config = SettingsConfigDict(env_prefix="SANDBOX_")


class SandboxState(BaseModel):
    """In-memory state for a single sandbox container."""
    container_id: str
    container_name: str
    status: str = "warm"  # warm | assigned | active | draining | destroyed
    session_id: str | None = None
    user_id: int | None = None
    chat_session_id: int | None = None
    assigned_at: datetime | None = None
    created_at: datetime


class SandboxManager:
    """Manages ephemeral sandbox container lifecycle."""

    def __init__(self, settings: SandboxSettings | None = None) -> None: ...

    async def start(self) -> None:
        """Start manager: fill warm pool, start reconciliation loop."""

    async def stop(self) -> None:
        """Stop all sandboxes, cancel background tasks."""

    async def assign(
        self,
        session_id: str,
        user_id: int,
        chat_session_id: int,
        env_vars: dict[str, str],
    ) -> SandboxState:
        """
        Assign a warm sandbox to a session.

        Picks from warm pool (or creates on-demand if pool empty).
        Injects session-specific env vars via NATS init message.
        Records assignment in DB.
        Returns SandboxState with container info.

        Raises:
            RuntimeError: If max instances reached.
        """

    async def release(self, session_id: str) -> None:
        """Release and destroy sandbox for session."""

    async def get_for_session(self, session_id: str) -> SandboxState | None:
        """Look up sandbox by session ID."""

    # Internal methods
    async def _create_sandbox(self, env_vars: dict[str, str] | None = None) -> SandboxState: ...
    async def _destroy_sandbox(self, container_id: str) -> None: ...
    async def _fill_pool(self) -> None: ...
    async def _reconciliation_loop(self) -> None: ...
    async def _monitor_health(self) -> None: ...
```

### Warm Pool Management

- **Target pool size**: `SANDBOX_POOL_SIZE` (default 3)
- **Replenishment**: After each assignment, `asyncio.create_task(self._fill_pool())`
- **Reconciliation**: Every 30s, the loop checks:
  - Active sandboxes past `session_timeout` -> force destroy
  - Warm sandboxes past `idle_timeout * 2` -> recycle (prevent stale images)
  - Pool size below target -> create more

### Container Assignment Flow

```python
async def assign(self, session_id, user_id, chat_session_id, env_vars):
    async with self._lock:
        warm = [s for s in self._sandboxes.values() if s.status == "warm"]
        if warm:
            sandbox = warm[0]
        else:
            if len(self._sandboxes) >= self._settings.max_instances:
                raise RuntimeError("Max sandbox instances reached")
            sandbox = await self._create_sandbox(env_vars)

        sandbox.status = "assigned"
        sandbox.session_id = session_id
        sandbox.user_id = user_id
        sandbox.chat_session_id = chat_session_id
        sandbox.assigned_at = datetime.now(timezone.utc)
        self._session_map[session_id] = sandbox.container_id

    # Send init message via NATS with session-specific config
    await self._nats.publish(
        f"sandbox.{session_id}.control",
        json.dumps({
            "type": "init",
            "session_id": session_id,
            "user_id": user_id,
            **env_vars,
        }).encode(),
    )

    # Persist to DB
    await self._persist_sandbox_session(sandbox)

    # Replenish pool in background
    asyncio.create_task(self._fill_pool())

    return sandbox
```

### Health Monitoring

The sandbox publishes heartbeats every 15s to `sandbox.{session_id}.health`. The API subscribes to `sandbox.*.health` and updates `last_heartbeat_at`. If a heartbeat is missed for 3 intervals (45s), the sandbox is marked unhealthy and destroyed.

### Graceful Shutdown and Timeout Handling

1. **Session ends normally**: API publishes `{type: shutdown}` on `sandbox.{sid}.control`. Sandbox has 30s to drain.
2. **Session timeout**: Reconciliation loop detects `assigned_at + session_timeout < now`. Publishes shutdown, then force-destroys after 30s.
3. **Heartbeat timeout**: 3 missed heartbeats -> force destroy immediately.
4. **API restart**: On startup, `SandboxManager` queries DB for `status != destroyed` records. Any orphaned sandboxes are destroyed via Docker SDK. Pool is re-filled.

**Confidence: High** -- Docker SDK `containers.get()` and `container.stop(timeout=5)` are synchronous but fast [Source -- Docker SDK docs, 2025].

---

## d. NATS Message Protocol

### Message Types (Sandbox Stream)

All messages on `sandbox.{session_id}.stream` (Sandbox -> API) use this envelope:

```python
@dataclass
class SandboxStreamEvent:
    """Base event published by sandbox to stream subject."""
    type: str           # Event type discriminator
    timestamp: str      # ISO 8601 timestamp
    session_id: str     # Session identifier
    sequence: int       # Monotonically increasing per session
    # ... type-specific fields
```

| Type | Direction | Payload Fields | Description |
|------|-----------|----------------|-------------|
| `token` | Sandbox->API | `data: str` | Single LLM token |
| `tool_call.start` | Sandbox->API | `call_id: str, tool_name: str, args: dict` | Tool invocation started |
| `tool_call.result` | Sandbox->API | `call_id: str, result: str, duration_ms: int, success: bool` | Tool invocation completed |
| `thinking.start` | Sandbox->API | `call_id: str` | Reasoning/thinking phase started |
| `thinking.token` | Sandbox->API | `call_id: str, data: str` | Reasoning token (if model supports) |
| `thinking.end` | Sandbox->API | `call_id: str` | Reasoning phase ended |
| `sources` | Sandbox->API | `sources: list[{doc_id, chunk_id, score, title}]` | Retrieved documents |
| `complete` | Sandbox->API | `message_id: int, token_count: int, tool_calls_count: int` | Turn complete |
| `error` | Sandbox->API | `code: str, message: str, recoverable: bool` | Error occurred |

Messages on `sandbox.{session_id}.input` (API -> Sandbox):

| Type | Direction | Payload Fields | Description |
|------|-----------|----------------|-------------|
| `query` | API->Sandbox | `query: str, chat_history: list, context: dict` | User's message |
| `cancel` | API->Sandbox | -- | Cancel current generation |
| `shutdown` | API->Sandbox | `grace_period_s: int` | Graceful shutdown request |

Messages on `sandbox.{session_id}.control` (API -> Sandbox):

| Type | Direction | Payload Fields | Description |
|------|-----------|----------------|-------------|
| `init` | API->Sandbox | `session_id, user_id, agent_config: dict, llm_config: dict, permissions: list` | Session initialization |
| `config_update` | API->Sandbox | `agent_config: dict` | Runtime config change |

Messages on `sandbox.{session_id}.health` (Sandbox -> API):

| Type | Direction | Payload Fields | Description |
|------|-----------|----------------|-------------|
| `heartbeat` | Sandbox->API | `status: str, uptime_s: int, memory_mb: int, active_turn: bool` | Health status |

### Subject Naming Convention

```
sandbox.{session_id}.{direction}

Examples:
  sandbox.sess_a1b2c3d4e5f6g7h8.input     # API -> Sandbox
  sandbox.sess_a1b2c3d4e5f6g7h8.stream     # Sandbox -> API (streaming)
  sandbox.sess_a1b2c3d4e5f6g7h8.output     # Sandbox -> API (final)
  sandbox.sess_a1b2c3d4e5f6g7h8.control    # API -> Sandbox (lifecycle)
  sandbox.sess_a1b2c3d4e5f6g7h8.health     # Sandbox -> API (heartbeat)
```

### Protobuf Message Definitions Needed

New proto file `src/proto/internal/sandbox.proto`:

```protobuf
syntax = "proto3";

package echomind.internal;

option go_package = "echomind/proto/internal";

import "google/protobuf/timestamp.proto";
import "google/protobuf/struct.proto";

// ============================================================================
// Sandbox Stream Events (Sandbox -> API)
// ============================================================================

message SandboxStreamEvent {
  string type = 1;
  string session_id = 2;
  int64 sequence = 3;
  google.protobuf.Timestamp timestamp = 4;

  oneof payload {
    TokenEvent token = 10;
    ToolCallStartEvent tool_call_start = 11;
    ToolCallResultEvent tool_call_result = 12;
    ThinkingEvent thinking = 13;
    SourcesEvent sources = 14;
    CompleteEvent complete = 15;
    ErrorEvent error = 16;
  }
}

message TokenEvent {
  string data = 1;
}

message ToolCallStartEvent {
  string call_id = 1;
  string tool_name = 2;
  google.protobuf.Struct args = 3;
}

message ToolCallResultEvent {
  string call_id = 1;
  string result = 2;
  int32 duration_ms = 3;
  bool success = 4;
}

message ThinkingEvent {
  string call_id = 1;
  string phase = 2;  // start | token | end
  optional string data = 3;
}

message SourcesEvent {
  repeated RetrievedSource sources = 1;
}

message RetrievedSource {
  int64 document_id = 1;
  string chunk_id = 2;
  double score = 3;
  string title = 4;
  optional string snippet = 5;
}

message CompleteEvent {
  int64 message_id = 1;
  int32 token_count = 2;
  int32 tool_calls_count = 3;
  int32 total_tokens = 4;
}

message ErrorEvent {
  string code = 1;
  string message = 2;
  bool recoverable = 3;
}

// ============================================================================
// Sandbox Input Events (API -> Sandbox)
// ============================================================================

message SandboxInputEvent {
  string type = 1;
  string session_id = 2;

  oneof payload {
    QueryEvent query = 10;
    CancelEvent cancel = 11;
    ShutdownEvent shutdown = 12;
  }
}

message QueryEvent {
  string query = 1;
  repeated ChatHistoryMessage chat_history = 2;
  google.protobuf.Struct context = 3;
}

message ChatHistoryMessage {
  string role = 1;
  string content = 2;
}

message CancelEvent {}

message ShutdownEvent {
  int32 grace_period_seconds = 1;
}

// ============================================================================
// Sandbox Control Events (API -> Sandbox)
// ============================================================================

message SandboxControlEvent {
  string type = 1;
  string session_id = 2;

  oneof payload {
    InitEvent init = 10;
    ConfigUpdateEvent config_update = 11;
  }
}

message InitEvent {
  int32 user_id = 1;
  int32 org_id = 2;
  google.protobuf.Struct agent_config = 3;
  google.protobuf.Struct llm_config = 4;
  repeated string permissions = 5;
}

message ConfigUpdateEvent {
  google.protobuf.Struct agent_config = 1;
}

// ============================================================================
// Sandbox Health (Sandbox -> API)
// ============================================================================

message SandboxHealthEvent {
  string session_id = 1;
  string status = 2;  // ready | active | draining | error
  int32 uptime_seconds = 3;
  int32 memory_mb = 4;
  bool active_turn = 5;
  google.protobuf.Timestamp timestamp = 6;
}
```

**Note**: For Phase 5 (initial implementation), JSON encoding is acceptable. Protobuf can be adopted later for performance if NATS message volume warrants it. The proto definitions above serve as the schema contract regardless of wire format.

---

## e. API Route Changes

### Changes to WebSocket Handler

**File**: `/Users/gp/Developer/echo-mind/src/api/websocket/chat_handler.py`

The `ChatHandler._handle_chat_start()` method gains a routing decision based on `mode`:

```python
async def _handle_chat_start(self, user: TokenUser, data: dict[str, Any]) -> None:
    """Handle chat.start message -- routes to RAG or sandbox."""
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
        # New: route to sandbox
        task = asyncio.create_task(
            self._process_agent_chat(user, session_id, query)
        )
    else:
        # Existing: in-process RAG pipeline
        task = asyncio.create_task(
            self._process_chat(user, session_id, query, mode)
        )

    self._active_generations[user.id] = task
```

New method `_process_agent_chat`:

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
    """
    trace = create_trace(
        name="agent-chat",
        user_id=str(user.id),
        session_id=str(chat_session_id),
        tags=["agent"],
    )

    try:
        sandbox_mgr = get_sandbox_manager()
        nats_pub = get_nats_publisher()

        # Get or assign sandbox
        session_id = f"sess_{chat_session_id}"
        sandbox = await sandbox_mgr.get_for_session(session_id)

        if not sandbox:
            # Build session-specific env vars
            session = await self._get_session_with_assistant(chat_session_id, user)
            env_vars = self._build_sandbox_env(user, session)

            sandbox = await sandbox_mgr.assign(
                session_id=session_id,
                user_id=user.id,
                chat_session_id=chat_session_id,
                env_vars=env_vars,
            )

            await self.manager.send_to_user(user.id, {
                "type": "agent.sandbox_assigned",
                "session_id": chat_session_id,
            })

        # Load chat history for context
        chat_history = await self._load_chat_history(chat_session_id)

        # Publish query to sandbox
        await nats_pub.publish(
            f"sandbox.{session_id}.input",
            json.dumps({
                "type": "query",
                "query": query,
                "chat_history": chat_history,
                "context": {"chat_session_id": chat_session_id},
            }).encode(),
        )

        # Save user message
        service = ChatService(db=self._db, qdrant=get_qdrant(),
                              embedder=get_embedder_client(), llm=get_llm_client())
        user_message = await service.save_user_message(chat_session_id, query)
        await self._db.commit()

        # Subscribe to sandbox stream and relay to WebSocket
        response_content = ""
        token_count = 0
        tool_calls_count = 0
        sources: list[RetrievedSource] = []

        js = nats_pub.js
        sub = await js.subscribe(
            f"sandbox.{session_id}.stream",
            stream="sandbox-stream",
            ordered_consumer=True,
        )

        async for msg in sub.messages:
            current_task = asyncio.current_task()
            if current_task is not None and current_task.cancelled():
                # Send cancel to sandbox
                await nats_pub.publish(
                    f"sandbox.{session_id}.input",
                    json.dumps({"type": "cancel"}).encode(),
                )
                return

            event = json.loads(msg.data)
            event_type = event["type"]

            if event_type == "token":
                token = event["data"]
                response_content += token
                token_count += 1
                await self.manager.send_to_user(user.id, {
                    "type": "generation.token",
                    "session_id": chat_session_id,
                    "token": token,
                })

            elif event_type == "tool_call.start":
                tool_calls_count += 1
                await self.manager.send_to_user(user.id, {
                    "type": "agent.tool_call.start",
                    "session_id": chat_session_id,
                    "call_id": event["call_id"],
                    "tool_name": event["tool_name"],
                    "args": event.get("args", {}),
                })

            elif event_type == "tool_call.result":
                await self.manager.send_to_user(user.id, {
                    "type": "agent.tool_call.result",
                    "session_id": chat_session_id,
                    "call_id": event["call_id"],
                    "result": event["result"],
                    "success": event.get("success", True),
                    "duration_ms": event.get("duration_ms"),
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
                    "type": "retrieval.complete",
                    "session_id": chat_session_id,
                    "sources": event["sources"],
                })

            elif event_type == "complete":
                # Save assistant message
                assistant_message = await service.save_assistant_message(
                    session_id=chat_session_id,
                    content=response_content,
                    sources=sources,
                    parent_message_id=user_message.id,
                )
                # Update tool_calls JSONB
                if tool_calls_count > 0:
                    assistant_message.tool_calls = {
                        "count": tool_calls_count,
                    }
                await self._db.commit()

                await self.manager.send_to_user(user.id, {
                    "type": "generation.complete",
                    "session_id": chat_session_id,
                    "message_id": assistant_message.id,
                    "token_count": token_count,
                })
                break

            elif event_type == "error":
                await self._send_error(
                    user.id,
                    event.get("code", "SANDBOX_ERROR"),
                    event.get("message", "Agent error"),
                )
                if not event.get("recoverable", False):
                    break

    except asyncio.CancelledError:
        logger.info("Cancelled agent generation for user %d", user.id)
        raise
    except Exception as e:
        logger.exception("Error in agent chat for user %d: %s", user.id, e)
        await self._send_error(user.id, "AGENT_ERROR", str(e))
    finally:
        if user.id in self._active_generations:
            del self._active_generations[user.id]
```

### New WebSocket Message Types

Added to `MessageType` enum:

```python
# Server -> Client (agent-specific)
AGENT_SANDBOX_ASSIGNED = "agent.sandbox_assigned"
AGENT_TOOL_CALL_START = "agent.tool_call.start"
AGENT_TOOL_CALL_RESULT = "agent.tool_call.result"
AGENT_THINKING_START = "agent.thinking.start"
AGENT_THINKING_TOKEN = "agent.thinking.token"
AGENT_THINKING_END = "agent.thinking.end"
```

### New REST Endpoints

**File**: `src/api/routes/sandbox.py` (new)

```python
router = APIRouter()

@router.get("/sandbox/pool", response_model=SandboxPoolStatus)
async def get_pool_status(user: AdminUser) -> SandboxPoolStatus:
    """Get current sandbox pool status (admin only)."""

@router.get("/sandbox/sessions", response_model=list[SandboxSessionInfo])
async def list_sandbox_sessions(user: CurrentUser, db: DbSession) -> list[SandboxSessionInfo]:
    """List user's active sandbox sessions."""

@router.get("/sandbox/sessions/{session_id}", response_model=SandboxSessionDetail)
async def get_sandbox_session(session_id: str, user: CurrentUser, db: DbSession) -> SandboxSessionDetail:
    """Get sandbox session details."""

@router.post("/sandbox/sessions/{session_id}/release")
async def release_sandbox(session_id: str, user: CurrentUser) -> dict[str, str]:
    """Release a sandbox session (owner or admin)."""

@router.post("/sandbox/sessions/{session_id}/cancel")
async def cancel_generation(session_id: str, user: CurrentUser) -> dict[str, str]:
    """Cancel active generation in a sandbox."""
```

### Backward Compatibility

The routing decision is based on `mode` in the `chat.start` WebSocket message:

| Mode | Pipeline | Status |
|------|----------|--------|
| `chat` | Existing RAG (embed->search->LLM) | Unchanged |
| `search` | Existing vector search only | Unchanged |
| `agent` | New sandbox pipeline (NATS->sandbox->MCP) | New |

The `ChatSession.mode` column already supports string values. The proto `ChatMode` enum gains a new value:

```protobuf
enum ChatMode {
  CHAT_MODE_UNSPECIFIED = 0;
  CHAT_MODE_CHAT = 1;
  CHAT_MODE_SEARCH = 2;
  CHAT_MODE_AGENT = 3;  // NEW: sandbox agent mode
}
```

---

## f. Database Schema Changes

### New Table: sandbox_sessions

```sql
CREATE TABLE sandbox_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id VARCHAR(255) UNIQUE NOT NULL,          -- NATS routing key (sess_xxxx)
    user_id INT NOT NULL REFERENCES users(id),
    chat_session_id INT REFERENCES chat_sessions(id), -- Links to existing chat system

    -- Container info
    container_id VARCHAR(64) NOT NULL,
    container_name VARCHAR(255) NOT NULL,
    container_ip INET,

    -- State machine
    status VARCHAR(20) NOT NULL DEFAULT 'assigned',   -- assigned|active|draining|destroyed
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    activated_at TIMESTAMPTZ,
    drained_at TIMESTAMPTZ,
    destroyed_at TIMESTAMPTZ,

    -- Agent configuration snapshot
    agent_config JSONB NOT NULL DEFAULT '{}',
    permissions TEXT[] NOT NULL DEFAULT '{}',

    -- Metrics
    message_count INT DEFAULT 0,
    tool_calls_count INT DEFAULT 0,
    total_tokens INT DEFAULT 0,
    mcp_calls_count INT DEFAULT 0,
    error_count INT DEFAULT 0,

    -- Observability
    langfuse_trace_id VARCHAR(255),
    last_heartbeat_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_sandbox_sessions_user ON sandbox_sessions (user_id, created_at DESC);
CREATE INDEX idx_sandbox_sessions_status ON sandbox_sessions (status) WHERE status != 'destroyed';
CREATE INDEX idx_sandbox_sessions_container ON sandbox_sessions (container_id);
CREATE INDEX idx_sandbox_sessions_session ON sandbox_sessions (session_id);
CREATE INDEX idx_sandbox_sessions_chat ON sandbox_sessions (chat_session_id);
```

### New Table: sandbox_events

```sql
CREATE TABLE sandbox_events (
    id BIGSERIAL PRIMARY KEY,
    sandbox_session_id UUID NOT NULL REFERENCES sandbox_sessions(id),
    event_type VARCHAR(50) NOT NULL,  -- created|assigned|activated|message|tool_call|
                                       -- mcp_call|error|timeout|drained|destroyed
    event_data JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_sandbox_events_session ON sandbox_events (sandbox_session_id, created_at);
CREATE INDEX idx_sandbox_events_type ON sandbox_events (event_type, created_at DESC);
```

### Monitoring View

```sql
CREATE VIEW sandbox_pool_status AS
SELECT
    status,
    COUNT(*) as count,
    AVG(EXTRACT(EPOCH FROM (NOW() - assigned_at))) as avg_age_seconds
FROM sandbox_sessions
WHERE status != 'destroyed'
GROUP BY status;
```

### Relationship to Existing Tables

```
chat_sessions (existing)
    |
    | 1:N  (a chat session can have multiple sandbox sessions
    |        over time if sandbox is recycled)
    v
sandbox_sessions (new)
    |
    | 1:N  (audit log of lifecycle events)
    v
sandbox_events (new)
```

The `chat_messages` table remains unchanged. Messages are still saved by the API (not by the sandbox) when the sandbox publishes `complete` events. This keeps the sandbox stateless and the API as the single writer to the database.

### Alembic Migration Plan

**File**: `src/migration/versions/YYYYMMDD_HHMMSS_add_sandbox_tables.py`

```python
"""Add sandbox_sessions and sandbox_events tables.

Revision ID: auto-generated
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB, INET, ARRAY

def upgrade() -> None:
    # ChatMode enum extension
    op.execute("ALTER TYPE chatmode ADD VALUE IF NOT EXISTS 'agent'")

    # sandbox_sessions table
    op.create_table(
        "sandbox_sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("session_id", sa.String(255), unique=True, nullable=False),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("chat_session_id", sa.Integer,
                  sa.ForeignKey("chat_sessions.id"), nullable=True),
        sa.Column("container_id", sa.String(64), nullable=False),
        sa.Column("container_name", sa.String(255), nullable=False),
        sa.Column("container_ip", INET, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="assigned"),
        sa.Column("assigned_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("activated_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("drained_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("destroyed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("agent_config", JSONB, nullable=False, server_default="{}"),
        sa.Column("permissions", ARRAY(sa.Text), nullable=False, server_default="{}"),
        sa.Column("message_count", sa.Integer, server_default="0"),
        sa.Column("tool_calls_count", sa.Integer, server_default="0"),
        sa.Column("total_tokens", sa.Integer, server_default="0"),
        sa.Column("mcp_calls_count", sa.Integer, server_default="0"),
        sa.Column("error_count", sa.Integer, server_default="0"),
        sa.Column("langfuse_trace_id", sa.String(255), nullable=True),
        sa.Column("last_heartbeat_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
    )

    op.create_index("idx_sandbox_sessions_user", "sandbox_sessions",
                    ["user_id", sa.text("created_at DESC")])
    op.create_index("idx_sandbox_sessions_status", "sandbox_sessions",
                    ["status"], postgresql_where=sa.text("status != 'destroyed'"))
    op.create_index("idx_sandbox_sessions_container", "sandbox_sessions",
                    ["container_id"])
    op.create_index("idx_sandbox_sessions_session", "sandbox_sessions",
                    ["session_id"])
    op.create_index("idx_sandbox_sessions_chat", "sandbox_sessions",
                    ["chat_session_id"])

    # sandbox_events table
    op.create_table(
        "sandbox_events",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("sandbox_session_id", UUID(as_uuid=True),
                  sa.ForeignKey("sandbox_sessions.id"), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("event_data", JSONB, server_default="{}"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
    )

    op.create_index("idx_sandbox_events_session", "sandbox_events",
                    ["sandbox_session_id", "created_at"])
    op.create_index("idx_sandbox_events_type", "sandbox_events",
                    ["event_type", sa.text("created_at DESC")])

    # Monitoring view
    op.execute("""
        CREATE VIEW sandbox_pool_status AS
        SELECT
            status,
            COUNT(*) as count,
            AVG(EXTRACT(EPOCH FROM (NOW() - assigned_at))) as avg_age_seconds
        FROM sandbox_sessions
        WHERE status != 'destroyed'
        GROUP BY status
    """)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS sandbox_pool_status")
    op.drop_table("sandbox_events")
    op.drop_table("sandbox_sessions")
```

---

## g. Detailed Implementation Plan

### File-by-File Listing

#### New Files

| # | File | Purpose | LOC Est. | Dependencies |
|---|------|---------|----------|--------------|
| 1 | `src/api/sandbox/__init__.py` | Package init | 5 | -- |
| 2 | `src/api/sandbox/manager.py` | SandboxManager class | 300 | docker, nats-py, pydantic-settings |
| 3 | `src/api/sandbox/nats_relay.py` | NATS stream-to-WebSocket relay | 150 | nats-py |
| 4 | `src/api/sandbox/models.py` | Pydantic models for sandbox state | 80 | pydantic |
| 5 | `src/api/routes/sandbox.py` | REST endpoints for sandbox mgmt | 120 | fastapi |
| 6 | `src/proto/internal/sandbox.proto` | Protobuf definitions | 120 | google.protobuf |
| 7 | `src/echomind_lib/db/models/sandbox_session.py` | SandboxSession ORM | 60 | sqlalchemy |
| 8 | `src/echomind_lib/db/models/sandbox_event.py` | SandboxEvent ORM | 30 | sqlalchemy |
| 9 | `src/migration/versions/XXXXXX_add_sandbox_tables.py` | Alembic migration | 80 | alembic |
| 10 | `tests/unit/api/sandbox/test_manager.py` | SandboxManager unit tests | 200 | pytest, unittest.mock |
| 11 | `tests/unit/api/sandbox/test_nats_relay.py` | NATS relay unit tests | 150 | pytest, unittest.mock |
| 12 | `tests/unit/api/sandbox/test_models.py` | Pydantic model tests | 50 | pytest |
| 13 | `tests/unit/api/routes/test_sandbox.py` | REST endpoint tests | 120 | pytest, httpx |
| 14 | `tests/unit/api/websocket/test_agent_chat.py` | Agent chat handler tests | 180 | pytest, unittest.mock |

#### Modified Files

| # | File | Changes | Details |
|---|------|---------|---------|
| 1 | `src/api/websocket/chat_handler.py` | Add `_process_agent_chat()`, modify `_handle_chat_start()` | Route to sandbox when mode=agent |
| 2 | `src/api/main.py` | Import SandboxManager, add to lifespan start/stop | Initialize/cleanup sandbox manager |
| 3 | `src/api/config.py` | Add `sandbox_enabled`, `sandbox_*` settings | Configuration for sandbox feature |
| 4 | `src/proto/public/chat.proto` | Add `CHAT_MODE_AGENT = 3` to ChatMode enum | New chat mode |
| 5 | `src/echomind_lib/db/models/__init__.py` | Export SandboxSession, SandboxEvent | Register new ORM models |
| 6 | `src/echomind_lib/db/nats_publisher.py` | Add `subscribe()` method for stream subscription | API needs to subscribe to sandbox streams |
| 7 | `src/api/requirements.txt` | Add `docker>=7.0.0`, `aiodocker>=0.22.0` (optional) | Docker SDK dependency |

### Class/Function Signatures

```python
# src/api/sandbox/manager.py
class SandboxManager:
    def __init__(self, settings: SandboxSettings | None = None) -> None: ...
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def assign(self, session_id: str, user_id: int,
                     chat_session_id: int, env_vars: dict[str, str]) -> SandboxState: ...
    async def release(self, session_id: str) -> None: ...
    async def get_for_session(self, session_id: str) -> SandboxState | None: ...
    async def get_pool_status(self) -> dict[str, int]: ...

# src/api/sandbox/nats_relay.py
class NatsStreamRelay:
    def __init__(self, js: JetStreamContext, ws_manager: ConnectionManager) -> None: ...
    async def relay_session(self, session_id: str, user_id: int,
                            chat_session_id: int) -> AsyncIterator[dict[str, Any]]: ...
    async def cancel(self, session_id: str) -> None: ...

# src/api/sandbox/models.py
class SandboxPoolStatus(BaseModel):
    warm: int
    assigned: int
    active: int
    draining: int
    total: int
    max_instances: int

class SandboxSessionInfo(BaseModel):
    session_id: str
    chat_session_id: int | None
    status: str
    assigned_at: datetime
    message_count: int
    tool_calls_count: int

class SandboxSessionDetail(SandboxSessionInfo):
    container_name: str
    agent_config: dict[str, Any]
    permissions: list[str]
    last_heartbeat_at: datetime | None
    langfuse_trace_id: str | None

# src/echomind_lib/db/models/sandbox_session.py
class SandboxSession(Base):
    __tablename__ = "sandbox_sessions"
    id: Mapped[uuid.UUID]
    session_id: Mapped[str]
    user_id: Mapped[int]
    chat_session_id: Mapped[int | None]
    container_id: Mapped[str]
    container_name: Mapped[str]
    status: Mapped[str]
    # ... (all columns from schema above)

# src/echomind_lib/db/models/sandbox_event.py
class SandboxEvent(Base):
    __tablename__ = "sandbox_events"
    id: Mapped[int]
    sandbox_session_id: Mapped[uuid.UUID]
    event_type: Mapped[str]
    event_data: Mapped[dict[str, Any] | None]
    created_at: Mapped[datetime]
```

### Dependencies and Versions

| Package | Version | Purpose |
|---------|---------|---------|
| `docker` | `>=7.0.0` | Docker SDK for container lifecycle |
| `nats-py` | `>=2.9.0` | Already in API requirements; used for subscribe |
| `pydantic` | `>=2.0.0` | Already in API requirements |
| `pydantic-settings` | `>=2.0.0` | Already in API requirements |
| `sqlalchemy[asyncio]` | existing | ORM models for sandbox tables |

**Note**: `aiodocker` (async Docker SDK) is an alternative to `docker` (sync). The sync SDK is sufficient because container create/destroy operations are infrequent and can be run in a thread pool executor. If latency becomes an issue, switch to `aiodocker`.

### Test Plan

| Test File | Test Cases | What's Tested |
|-----------|------------|---------------|
| `test_manager.py` | `test_start_fills_warm_pool` | Pool initialization creates N containers |
| | `test_assign_picks_warm_container` | Assignment picks from pool, not creates new |
| | `test_assign_creates_on_demand_when_pool_empty` | Fallback creation when no warm containers |
| | `test_assign_raises_when_max_reached` | RuntimeError at max instances |
| | `test_release_destroys_and_replenishes` | Release removes container, pool refills |
| | `test_reconciliation_enforces_timeout` | Session timeout triggers destroy |
| | `test_reconciliation_recycles_stale_warm` | Old warm containers are replaced |
| | `test_stop_destroys_all` | Clean shutdown removes all containers |
| | `test_recovery_on_restart` | Orphaned containers detected and cleaned |
| `test_nats_relay.py` | `test_relay_token_events` | Token events forwarded to WebSocket |
| | `test_relay_tool_call_events` | Tool call start/result forwarded |
| | `test_relay_complete_breaks_loop` | Complete event stops relay |
| | `test_relay_error_stops_on_unrecoverable` | Non-recoverable error breaks loop |
| | `test_cancel_publishes_to_input` | Cancel sends message on input subject |
| | `test_relay_handles_disconnect` | WebSocket disconnect during relay |
| `test_models.py` | `test_sandbox_pool_status_validation` | Pydantic model validation |
| | `test_sandbox_session_info_serialization` | JSON serialization |
| `test_sandbox.py` (routes) | `test_get_pool_status_admin_only` | Non-admin gets 403 |
| | `test_list_sandbox_sessions_filters_by_user` | Users see only their sessions |
| | `test_release_sandbox_owner_only` | Non-owner gets 403 |
| | `test_cancel_generation` | Cancel sends NATS message |
| `test_agent_chat.py` | `test_agent_mode_routes_to_sandbox` | mode=agent uses sandbox path |
| | `test_chat_mode_uses_existing_rag` | mode=chat uses existing path |
| | `test_sandbox_assignment_on_first_message` | First message triggers assignment |
| | `test_subsequent_messages_reuse_sandbox` | Second message uses existing sandbox |
| | `test_cancel_sends_nats_cancel` | Chat cancel forwards to sandbox |
| | `test_websocket_disconnect_during_relay` | Clean handling of disconnect |
| | `test_sandbox_error_forwarded_to_client` | Error events reach WebSocket |

### Implementation Order

The implementation order follows dependency chains. Each step depends on the previous ones.

```
Step 1: Database foundation
  - src/echomind_lib/db/models/sandbox_session.py
  - src/echomind_lib/db/models/sandbox_event.py
  - src/echomind_lib/db/models/__init__.py (update exports)
  - src/migration/versions/XXXXXX_add_sandbox_tables.py
  - tests/unit/api/sandbox/test_models.py

Step 2: Proto definitions
  - src/proto/internal/sandbox.proto
  - src/proto/public/chat.proto (add CHAT_MODE_AGENT)
  - Run ./scripts/generate_proto.sh

Step 3: SandboxManager core
  - src/api/sandbox/__init__.py
  - src/api/sandbox/models.py
  - src/api/sandbox/manager.py
  - tests/unit/api/sandbox/test_manager.py

Step 4: NATS relay
  - src/echomind_lib/db/nats_publisher.py (add subscribe capability)
  - src/api/sandbox/nats_relay.py
  - tests/unit/api/sandbox/test_nats_relay.py

Step 5: Chat handler integration
  - src/api/websocket/chat_handler.py (add _process_agent_chat)
  - src/api/config.py (add sandbox settings)
  - tests/unit/api/websocket/test_agent_chat.py

Step 6: REST endpoints + API wiring
  - src/api/routes/sandbox.py
  - src/api/main.py (add SandboxManager to lifespan)
  - src/api/requirements.txt (add docker)
  - tests/unit/api/routes/test_sandbox.py

Step 7: Integration testing
  - Manual test: start sandbox, send query, verify streaming
  - Verify backward compatibility: mode=chat still works unchanged
```

---

## h. Citations and Sources

- [Deploy Streaming Agent APIs with FastAPI & WebSockets -- Decoding AI, 2025](https://www.decodingai.com/p/deploying-agents-as-real-time-apis)
- [Integrating AutoGen Agents into Your Web Application -- Victor Dibia, 2025](https://newsletter.victordibia.com/p/integrating-autogen-agents-into-your)
- [NATS JetStream Documentation -- NATS.io, 2025](https://docs.nats.io/nats-concepts/jetstream)
- [NATS Request-Reply Semantics -- NATS.io, 2025](https://docs.nats.io/using-nats/developer/sending/request_reply)
- [NATS JetStream Model Deep Dive -- NATS.io, 2025](https://docs.nats.io/using-nats/developer/develop_jetstream/model_deep_dive)
- [Docker SDK for Python -- Docker, 2025](https://docker-py.readthedocs.io/en/stable/)
- [aiodocker -- Async Docker API client -- GitHub, 2025](https://github.com/aio-libs/aiodocker)
- [How to Use Python Docker SDK for Automation -- OneUptime, 2026](https://oneuptime.com/blog/post/2026-02-08-how-to-use-python-docker-sdk-docker-py-for-automation/view)
- [Containers API -- Docker SDK for Python 7.1.0 -- Docker, 2025](https://docker-py.readthedocs.io/en/stable/containers.html)
- [Streaming AI Responses: WebSockets, SSE, and gRPC -- Pranav Prakash, 2025](https://medium.com/@pranavprakash4777/streaming-ai-responses-with-websockets-sse-and-grpc-which-one-wins-a481cab403d3)
- [AI Agent Chat: Choosing Between WebSockets and SSE -- Karl's Blog, 2025](https://www.karls.io/ai-agent-progress-chat-websocket-server-sent-events/)
- [SSE's Comeback: Why 2025 is the Year of Server-Sent Events -- portalZINE, 2025](https://portalzine.de/sses-glorious-comeback-why-2025-is-the-year-of-server-sent-events/)
- [Why SSE Beat WebSockets for 95% of Real-Time Cloud Apps -- CodeToDeploy, 2026](https://medium.com/codetodeploy/why-server-sent-events-beat-websockets-for-95-of-real-time-cloud-applications-830eff5a1d7c)
- [Docker Sandboxes Documentation -- Docker, 2025](https://docs.docker.com/ai/sandboxes)
- [Docker Blog: Secure AI Agents at Runtime -- Docker, 2025](https://www.docker.com/blog/secure-ai-agents-runtime-security/)
- [FastAPI WebSockets Documentation -- FastAPI, 2025](https://fastapi.tiangolo.com/advanced/websockets/)
- [Part 1: Intro to Streaming -- Google Agent Development Kit, 2025](https://google.github.io/adk-docs/streaming/dev-guide/part1/)
- [Jetstream with Request-Reply Discussion -- nats-io/nats.py #221, 2025](https://github.com/nats-io/nats.py/discussions/221)

---

## Evaluation Scorecard

| # | Criterion | Score (1-10) | Notes |
|---|-----------|:---:|-------|
| 1 | **Backward Compatibility** | 9 | Mode-based routing keeps existing chat/search paths untouched. Only risk is proto regeneration for new ChatMode enum value. |
| 2 | **Streaming Latency** | 8 | NATS adds ~1-2ms per message hop. Ordered consumers avoid ack overhead. WebSocket relay is negligible. Total added latency <5ms per token vs current in-process path. |
| 3 | **Fault Tolerance** | 7 | Heartbeat monitoring + reconciliation loop handle most failures. Edge case: API crash during relay loses in-flight tokens (NATS JetStream memory storage). Mitigation: replay from stream on reconnect. |
| 4 | **Security** | 7 | Network isolation + NATS subject scoping provide baseline. JWT auth for MCP deferred to Phase 8. During Phases 4-7, MCP server trusts all callers on internal network. |
| 5 | **Implementation Complexity** | 6 | Moderate complexity. SandboxManager introduces Docker SDK dependency and async container management. NATS relay pattern is straightforward but adds a new message bus to debug. |
| 6 | **Testability** | 8 | All components are mockable. Docker SDK mocked in unit tests. NATS interactions mocked via fake publisher/subscriber. WebSocket handler tested via existing patterns. |
| 7 | **Operational Readiness** | 7 | Health checks, metrics, audit log provide visibility. Missing: Grafana dashboard for sandbox pool (added in Phase 6). Missing: automatic capacity scaling (single-host limitation). |
