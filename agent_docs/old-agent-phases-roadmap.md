# Agent System Roadmap: Phases 7-10

> Based on phases 1-6 (config, policy, routing, sessions, 30 tools, MCP).
> Each phase is independently deployable; later phases build on earlier ones.

---

## Phase 7: EchoMind API Gateway Integration

**Goal:** Connect the standalone agent system to EchoMind's existing FastAPI + WebSocket infrastructure, making agents accessible to end users through the chat API.

### Why This Phase First

The agent system currently runs standalone via examples. To deliver value, it must be reachable from the EchoMind web UI via the existing chat/WebSocket layer. This is the bridge between "standalone agent library" and "production agentic RAG."

### Key Design Decisions

1. **Agent as a service within the API process** — The agent system runs in-process with the FastAPI service (no separate microservice yet). This avoids network overhead and simplifies session sharing.
2. **New `/api/v1/agents/` route group** — Separate from existing `/api/v1/chat/` routes. Agents are a distinct interaction model (tool-calling, multi-turn, streaming).
3. **WebSocket channel for agent streaming** — Extend the existing Socket.IO server with an `agent:run` event. Responses stream back via `agent:chunk` / `agent:done` events.
4. **Authentication reuse** — Agents use the same Authentik OIDC auth as the rest of the API. Agent config determines which agent a user gets (via routing).
5. **Session storage migration path** — Phase 7 keeps JSONL sessions. Phase 9 migrates to PostgreSQL.

### Files to Create

| File | Purpose |
|------|---------|
| `src/api/routes/agents.py` | REST endpoints: list agents, run agent, get history |
| `src/api/websocket/agent_handler.py` | Socket.IO handler for streaming agent interactions |
| `src/api/logic/agent_service.py` | Business logic: agent lifecycle, factory caching, request dispatch |
| `src/api/logic/agent_session_bridge.py` | Maps EchoMind chat sessions to agent session keys |
| `tests/unit/api/routes/test_agents.py` | Route tests |
| `tests/unit/api/logic/test_agent_service.py` | Service tests |
| `tests/unit/api/websocket/test_agent_handler.py` | WebSocket handler tests |

### Files to Modify

| File | Change |
|------|--------|
| `src/api/main.py` | Register agent routes and WebSocket handlers |
| `src/api/dependencies.py` | Add agent factory dependency injection |
| `src/api/config.py` | Add agent config path setting |
| `config/agents/config.yaml` | Add EchoMind-specific agent definitions (RAG agent, document agent) |

### Estimated Tests: 35-45

### Dependencies: Phases 1-6 complete

---

## Phase 8: Agent Memory & RAG Tool Integration

**Goal:** Give agents access to EchoMind's core capabilities — vector search (Qdrant), document retrieval, episodic/semantic memory — as first-class tools.

### Why This Phase

The 30 built-in tools are generic (filesystem, git, bash). EchoMind's value proposition is Agentic RAG. Agents need tools that search the knowledge base, retrieve documents, and manage memory.

### Key Design Decisions

1. **RAG tools as a new tool module** — `src/agent/tools/rag.py` with tools like `search_knowledge_base`, `get_document`, `list_collections`. These call into `echomind_lib` services.
2. **Memory tools** — `src/agent/tools/memory.py` with `store_memory`, `recall_memory`, `forget_memory`. Backed by EchoMind's existing memory tables.
3. **Dependency injection for tools** — RAG tools need database sessions, Qdrant clients, embedder gRPC stubs. Introduce a `ToolContext` dataclass that tools receive, replacing direct imports.
4. **Multi-step retrieval** — The RAG agent should support chain-of-thought retrieval: search → refine query → search again → synthesize. This is orchestrated by the LLM's tool-calling loop, not hardcoded.
5. **Collection scoping** — Tools enforce tenant isolation. A user can only search their own collections (user/group/org). The `ToolContext` carries the authenticated user's scoping info.

### Files to Create

| File | Purpose |
|------|---------|
| `src/agent/tools/rag.py` | `search_knowledge_base`, `get_document`, `get_document_chunks`, `list_collections` |
| `src/agent/tools/memory.py` | `store_memory`, `recall_memory`, `list_memories`, `forget_memory` |
| `src/agent/tools/context.py` | `ToolContext` dataclass for dependency injection into tools |
| `src/agent/tools/connectors.py` | `list_connectors`, `get_connector_status`, `trigger_sync` |
| `tests/unit/agent/tools/test_rag.py` | RAG tool unit tests |
| `tests/unit/agent/tools/test_memory.py` | Memory tool unit tests |
| `tests/unit/agent/tools/test_connectors.py` | Connector tool tests |
| `tests/unit/agent/tools/test_context.py` | ToolContext tests |
| `config/agents/config.yaml` | Add RAG-enabled agent definitions |

### Files to Modify

| File | Change |
|------|--------|
| `src/agent/tools/registry.py` | Register RAG/memory/connector tools, accept `ToolContext` |
| `src/agent/agent.py` | Pass `ToolContext` through `BasicAgentWrapper` |
| `src/agent/config/schema.py` | Add RAG tool config options (default collection, embedding model) |

### Estimated Tests: 40-50

### Dependencies: Phase 7 (API gateway provides auth context for scoping)

---

## Phase 9: Observability, Tracing & Production Hardening

**Goal:** Make the agent system production-ready with structured tracing, metrics, cost tracking, and robust error handling.

### Why This Phase

Before scaling to multiple users, we need visibility into agent behavior: what tools are called, how long LLM calls take, token costs, and failure modes. This phase also hardens session persistence.

### Key Design Decisions

1. **OpenTelemetry tracing** — Each agent run creates a trace span. Tool calls are child spans. This integrates with EchoMind's existing Grafana/Prometheus stack.
2. **Token cost tracking** — Track prompt/completion tokens per request. Store in PostgreSQL for billing/analytics. Expose via API.
3. **PostgreSQL session storage** — Migrate from JSONL files to a `agent_sessions` table. Enables querying, expiration, and multi-instance deployment.
4. **Rate limiting** — Per-user rate limits on agent runs (configurable). Prevents abuse and controls LLM costs.
5. **Circuit breaker for LLM calls** — If the LLM endpoint fails repeatedly, stop sending requests for a cooldown period. Prevents cascading failures.
6. **Structured logging** — All agent operations emit structured JSON logs with correlation IDs (trace_id).

### Files to Create

| File | Purpose |
|------|---------|
| `src/agent/observability/__init__.py` | Package init |
| `src/agent/observability/tracer.py` | OpenTelemetry span management for agent runs |
| `src/agent/observability/metrics.py` | Prometheus metrics: request count, latency, token usage |
| `src/agent/observability/cost.py` | Token cost calculator (per-model pricing table) |
| `src/agent/sessions/pg_manager.py` | PostgreSQL-backed session manager (replaces JSONL) |
| `src/agent/sessions/pg_provider.py` | History provider for PostgreSQL sessions |
| `src/agent/middleware/rate_limiter.py` | Per-user rate limiting middleware |
| `src/agent/middleware/circuit_breaker.py` | Circuit breaker for LLM endpoint failures |
| `src/migration/versions/YYYYMMDD_agent_sessions.py` | Alembic migration for agent_sessions table |
| `src/migration/versions/YYYYMMDD_agent_usage.py` | Alembic migration for agent_usage_log table |
| `tests/unit/agent/observability/test_tracer.py` | Tracer tests |
| `tests/unit/agent/observability/test_metrics.py` | Metrics tests |
| `tests/unit/agent/observability/test_cost.py` | Cost calculator tests |
| `tests/unit/agent/sessions/test_pg_manager.py` | PG session tests |
| `tests/unit/agent/middleware/test_rate_limiter.py` | Rate limiter tests |
| `tests/unit/agent/middleware/test_circuit_breaker.py` | Circuit breaker tests |

### Files to Modify

| File | Change |
|------|--------|
| `src/agent/agent.py` | Inject tracer, emit spans around LLM calls and tool execution |
| `src/agent/config/schema.py` | Add observability config (tracing enabled, cost tracking, rate limits) |
| `src/api/routes/agents.py` | Add usage/cost endpoints, apply rate limiting |
| `docker-compose.yml` | Add OTEL collector sidecar config |

### Estimated Tests: 50-60

### Dependencies: Phase 7 (API gateway), Phase 8 (tools need tracing too)

---

## Phase 10: Multi-Agent Orchestration

**Goal:** Enable multiple agents to collaborate on complex tasks — a coordinator agent delegates subtasks to specialist agents, with structured handoffs and shared context.

### Why This Phase

Single-agent interactions hit a ceiling for complex workflows (e.g., "research this topic, write a report, then create a presentation"). Multi-agent orchestration enables specialization and parallel execution.

### Key Design Decisions

1. **Coordinator pattern** — A "coordinator" agent receives the user request and delegates to specialist agents via a `delegate_to_agent` tool. The coordinator sees specialist responses and synthesizes the final answer.
2. **Agent-to-agent communication** — Agents communicate through a message bus (in-memory for single-instance, NATS for distributed). Messages are typed: `TaskRequest`, `TaskResult`, `StatusUpdate`.
3. **Shared context** — Agents in an orchestration share a `WorkspaceContext` (read-only scratchpad). The coordinator writes context; specialists read it.
4. **Execution strategies** — Sequential (agent A → agent B → agent C), parallel (agents A+B simultaneously), and conditional (if agent A fails, try agent B).
5. **Sub-agent policy enforcement** — Sub-agents inherit the coordinator's policy constraints plus additional restrictions from `subagentDeniedTools`. This is already supported by the policy engine.
6. **Token budget** — The coordinator has a total token budget. Each sub-agent call deducts from it. Prevents runaway costs in multi-agent loops.

### Files to Create

| File | Purpose |
|------|---------|
| `src/agent/orchestration/__init__.py` | Package init |
| `src/agent/orchestration/coordinator.py` | Coordinator agent that delegates to specialists |
| `src/agent/orchestration/strategies.py` | Sequential, parallel, conditional execution strategies |
| `src/agent/orchestration/workspace.py` | Shared workspace context for multi-agent collaboration |
| `src/agent/orchestration/messages.py` | Inter-agent message types (TaskRequest, TaskResult) |
| `src/agent/orchestration/budget.py` | Token budget tracker for multi-agent runs |
| `src/agent/tools/delegation.py` | `delegate_to_agent`, `ask_agent`, `parallel_agents` tools |
| `src/agent/orchestration/nats_bus.py` | NATS-backed message bus for distributed orchestration |
| `tests/unit/agent/orchestration/test_coordinator.py` | Coordinator tests |
| `tests/unit/agent/orchestration/test_strategies.py` | Strategy tests |
| `tests/unit/agent/orchestration/test_workspace.py` | Workspace tests |
| `tests/unit/agent/orchestration/test_budget.py` | Budget tests |
| `tests/unit/agent/tools/test_delegation.py` | Delegation tool tests |

### Files to Modify

| File | Change |
|------|--------|
| `src/agent/tools/registry.py` | Register delegation tools |
| `src/agent/agent.py` | Support sub-agent spawning from coordinator |
| `src/agent/config/schema.py` | Add orchestration config (max_concurrent_agents, token_budget, strategies) |
| `config/agents/config.yaml` | Add coordinator + specialist agent definitions |
| `src/api/routes/agents.py` | Expose orchestration status in API responses |

### Estimated Tests: 45-55

### Dependencies: Phase 9 (tracing is critical for debugging multi-agent flows)

---

## Summary

| Phase | Title | New Files | Modified Files | Est. Tests | Key Deliverable |
|-------|-------|-----------|---------------|------------|-----------------|
| 7 | API Gateway Integration | 7 | 4 | 35-45 | Agents accessible via REST + WebSocket |
| 8 | Memory & RAG Tools | 9 | 3 | 40-50 | Agents can search knowledge base + manage memory |
| 9 | Observability & Hardening | 16 | 4 | 50-60 | Tracing, metrics, PG sessions, rate limiting |
| 10 | Multi-Agent Orchestration | 13 | 5 | 45-55 | Coordinator delegates to specialist agents |

**Total estimated new tests: 170-210**

### Potential Phase 11+ Ideas (Not Scoped)

- **Agent evaluation framework** — Automated benchmarks for agent quality (tool selection accuracy, response quality, cost efficiency)
- **Agent marketplace** — User-defined agents with custom tool sets, shareable across orgs
- **Voice agent mode** — Integrate with EchoMind's voice/Whisper service for spoken agent interactions
- **Agent plugins** — Hot-reloadable Python plugins that extend agent capabilities without redeployment
- **Autonomous agent loops** — Long-running agents that execute multi-step plans with checkpointing and human-in-the-loop approval gates
