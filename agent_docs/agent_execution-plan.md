# Sandboxed Agent Architecture — Consolidated Execution Plan

> **Date**: 2026-02-16
> **Based on**: 5 analysis documents (sandbox containers, MCP gateway, skills migration, observability, infrastructure)
> **Status**: Ready for review

---

## Executive Summary

This plan transforms EchoMind's agent system from an in-process library into a **production-grade sandboxed agent platform**. Agents run in ephemeral Docker containers with a custom MCP server as the single gateway for skills, data connectors, and API keys. The 30 native Python tools are replaced with Moltbot-style bash skills, and full observability is provided via OpenTelemetry + Langfuse + Grafana.

### Key Numbers

| Metric | Value |
|--------|-------|
| New services | 3 (sandbox, MCP gateway, OTEL collector) |
| New DB tables | 2 (sandbox_sessions, sandbox_events) |
| Code to delete | ~1,100 LOC (29 of 30 native tools) |
| Code to write | ~3,000-4,000 LOC (across all phases) |
| Moltbot skills portable | 27 of 53 directly, 7 partially |
| Total implementation time | 8-10 weeks |

---

## Architecture Overview

```
                              INTERNET
                                 |
                             [Traefik]
                              /      \
                        [WebUI]    [API :8000]
                                     |
                    +----------------+----------------+
                    |                |                |
                 [NATS]          [Postgres]       [Redis]
                 JetStream       (sandbox          (session
                 (lifecycle)      state DB)         cache)
                    |
       +------------+------------+------------+
       |            |            |            |
  [sandbox-0]  [sandbox-1]  [sandbox-2]  [sandbox-N]
  (ephemeral)  (ephemeral)  (ephemeral)  (ephemeral)
       |            |            |            |
       +-----+------+-----+-----+
             |             |
        [MCP Gateway]   [Internet]
        (shared svc)    (direct access)
        port 8100       - web search
             |          - web crawl
       +-----+-----+   - log shipping
       |     |     |
    [Qdrant][PG] [MinIO]
```

### Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Container lifecycle | Ephemeral per session | Full isolation, no state leaks |
| API-to-sandbox | NATS JetStream | Already deployed, lifecycle events + streaming |
| Sandbox-to-tools | MCP via Streamable HTTP | Standard protocol, no auth initially (zero-trust added later) |
| Tool model | Bash skills (SKILL.md) | 73% of tools are already shell wrappers |
| MCP framework | FastMCP 3.x | Built-in auth, middleware, transport, schema |
| Container pool | Warm pool (pre-created) | ~50ms vs ~1.5s cold start |
| Observability | OTEL Collector → Langfuse + Prometheus | Handles ephemeral container flush |
| Internet access | Direct from sandbox | Agent needs web search, crawling, logs |
| DB access | Blocked (via MCP only) | Zero-trust enforcement at MCP boundary |

---

## Phase 1: MCP Gateway Server (Weeks 1-3)

**Goal**: FastMCP server with search tools and skills, deployed as Docker service. **No auth in this phase** — the MCP server trusts all callers. Auth (JWT, RBAC) is deferred to a later hardening phase.

**Why first**: The MCP gateway is the core integration point. It must exist before sandboxes, because sandboxes need MCP to access data and skills. Building it first validates the FastMCP framework choice and the skill flow.

### Deliverables

1. **`src/mcp_gateway/`** — New service (~600 LOC, simpler without auth)
   ```
   src/mcp_gateway/
     __init__.py
     main.py                  # FastMCP server entrypoint
     config.py                # Pydantic settings (MCP_GATEWAY_ prefix)
     middleware/
       __init__.py
       audit_logger.py         # Structured JSON audit log
     tools/
       __init__.py
       search.py               # search_documents, search_collections, get_document
       skills.py               # skills_list, skills_get_info, skills_execute
     skills/
       __init__.py
       registry.py             # SKILL.md parser and discovery
       executor.py             # Subprocess execution with limits
     backends/
       __init__.py
       search_backend.py       # Qdrant + Embedder integration
     Dockerfile
     requirements.txt
   ```

2. **MCP Tools — Search namespace**:
   - `search_documents(query, limit, score_threshold)` — Vector search across Qdrant
   - `search_collections()` — List available Qdrant collections
   - `get_document(document_id)` — Document metadata
   - `get_document_chunks(document_id, limit)` — Full document content

3. **MCP Tools — Skills namespace** (the key skill flow):
   - `skills_list()` — Returns all available skills with name, description, and parameters. **The agent reads this list, decides which skill to use based on the user's request, then calls `skills_execute`.**
   - `skills_get_info(skill_name)` — Full skill metadata + instructions body (loaded on demand, like Moltbot's progressive disclosure)
   - `skills_execute(skill_name, command)` — Execute a bash command in the context of a skill. The MCP server runs it in a subprocess with timeout and output limits.

   **Skill flow**:
   ```
   Agent                          MCP Server
     |                               |
     |-- skills_list() ------------->|  Returns [{name, description, params}, ...]
     |<-- list of all skills --------|
     |                               |
     |  (agent decides: "I need      |
     |   the 'github' skill")        |
     |                               |
     |-- skills_get_info("github") ->|  Returns full SKILL.md body
     |<-- instructions + examples ---|  (agent now knows the bash patterns)
     |                               |
     |-- skills_execute("github",  ->|  Runs command in subprocess
     |     "gh pr list --repo X")    |  with timeout + output limits
     |<-- {output, exit_code} -------|
   ```

4. **No auth in this phase**:
   - MCP server is on internal Docker network only (not exposed externally)
   - Network isolation provides sufficient security for now
   - Auth (JWT + RBAC + rate limiting) added in Phase 8

5. **Middleware**:
   - Audit logging: structured JSON for every tool invocation
   - Error handling: domain exceptions → MCP error responses

6. **Docker integration**:
   - Service `echomind-mcp` on port 8100
   - Networks: `backend` + `sandbox`
   - Health check at `/healthz`
   - Added to `docker-compose.yml` and `cluster.sh`

7. **Tests**: Unit tests for search backend, skill registry, skill executor, tool handlers (~30 tests)

### Dependencies

- `fastmcp>=3.0` (install in echomind conda env)
- `echomind_lib` (shared library)
- Existing: `sqlalchemy[asyncio]`, `asyncpg`, `qdrant-client`

### Verification

```bash
# Start gateway locally
PYTHONPATH=src python -m mcp_gateway.main

# Test with MCP client
python -c "
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
async with streamablehttp_client('http://localhost:8100/mcp') as (r,w,_):
    async with ClientSession(r,w) as session:
        tools = await session.list_tools()
        print(f'{len(tools.tools)} tools available')
"
```

---

## Phase 2: Connector & API Proxy Tools (Week 4)

**Goal**: Expose connectors and external API proxying via MCP gateway.

### Deliverables

1. **Connector tools**:
   - `connectors_list()` — List user's data connectors with RBAC
   - `connector_status(connector_id)` — Sync status and stats
   - `connector_sync(connector_id)` — Trigger sync (requires edit permission)

2. **API proxy tools**:
   - `web_search(query, max_results)` — Google Custom Search (agent never sees key)
   - `send_email(to, subject, body)` — Gmail/Outlook via user's OAuth token
   - `calendar_create_event(title, start, end)` — Google Calendar/Outlook

3. **API Key Manager**:
   - Keys loaded from environment at startup
   - Per-service permission requirements
   - OAuth token refresh for per-user connector APIs
   - Agent never receives raw key values

4. **Tests**: ~20 additional tests

---

## Phase 3: Initial Skills & Portability Testing (Week 5)

**Goal**: Create initial skill library and validate Moltbot skill portability through MCP.

Note: The skill engine (registry, executor, MCP tools) is built in Phase 1. This phase focuses on writing SKILL.md files and testing them end-to-end.

### Deliverables

1. **Initial skills directory**:
   ```
   skills/
     github/SKILL.md           # Copied from Moltbot, adapted
     file-edit/SKILL.md        # Structured file editing patterns
     weather/SKILL.md          # Simple test case (curl wttr.in)
     summarize/SKILL.md        # URL/video summarization
     coding-agent/SKILL.md     # Sub-agent orchestration
   ```

2. **Skill portability test**: Copy 5 Moltbot skills, verify they work through MCP gateway. Validate the full flow: `skills_list()` → agent decides → `skills_get_info()` → `skills_execute()`

3. **System prompt engineering**: Teach the agent how to use skills effectively — when to call `skills_list`, when to call `skills_get_info` for detailed instructions, and how to construct bash commands based on skill instructions.

4. **Execution limits** (configurable per skill via SKILL.md metadata):
   - Default: 30s timeout, 64KB output
   - Extended: 120s timeout, 256KB output
   - Long-running: 300s timeout, 1MB output

### Key Insight from Analysis

> 22 of 30 EchoMind tools (73%) are thin shell wrappers — they literally do `subprocess.run("git <cmd>")`. Migration to bash skills is trivial.

**Recommendation**: Keep `edit` as optional native tool (structured params safer than sed). Delete all other 29 native tools.

---

## Phase 4: Sandbox Container Foundation (Weeks 6-7)

**Goal**: Ephemeral Docker containers with warm pool, NATS communication, session routing.

### Deliverables

1. **`src/sandbox/`** — New service (~600 LOC)
   ```
   src/sandbox/
     Dockerfile
     requirements.txt
     __init__.py
     main.py              # Entry point: NATS sub + health server
     config.py            # Pydantic settings (SANDBOX_ prefix)
     agent_runner.py      # Semantic Kernel agent with MCP tools
   ```

2. **SandboxManager** (in API service, ~400 LOC):
   - `src/api/sandbox/manager.py` — Container lifecycle via Docker SDK
   - Warm pool: 3 pre-created containers (configurable)
   - State machine: WARM → ASSIGNED → ACTIVE → DRAINING → DESTROYED
   - Reconciliation loop (30s interval): timeout enforcement, pool replenishment

3. **Database schema** (Alembic migration):
   ```sql
   CREATE TABLE sandbox_sessions (
       id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
       session_id VARCHAR(255) UNIQUE NOT NULL,
       user_id INT NOT NULL REFERENCES users(id),
       chat_session_id INT REFERENCES chat_sessions(id),
       container_id VARCHAR(64) NOT NULL,
       container_name VARCHAR(255) NOT NULL,
       status VARCHAR(20) NOT NULL DEFAULT 'assigned',
       assigned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
       activated_at TIMESTAMPTZ,
       destroyed_at TIMESTAMPTZ,
       agent_config JSONB NOT NULL DEFAULT '{}',
       message_count INT DEFAULT 0,
       tool_calls_count INT DEFAULT 0,
       total_tokens INT DEFAULT 0,
       created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
       updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
   );

   CREATE TABLE sandbox_events (
       id BIGSERIAL PRIMARY KEY,
       sandbox_session_id UUID NOT NULL REFERENCES sandbox_sessions(id),
       event_type VARCHAR(50) NOT NULL,
       event_data JSONB DEFAULT '{}',
       created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
   );
   ```

4. **NATS integration**:
   - New stream `sandbox-stream` (memory storage, 1h retention)
   - Subjects: `sandbox.{session_id}.{input|output|stream|control|health}`
   - Audit stream: `sandbox-audit` (file storage, 7d retention)

5. **Docker Compose overlay** (`docker-compose-sandbox.yml`):
   - `sandbox` Docker network (internet-enabled, isolated from backend)
   - MCP server on `backend` + `sandbox` networks
   - NATS on `backend` + `sandbox` networks
   - API gains Docker socket mount + `sandbox` network

6. **Container security**:
   - Non-root user (uid 1000)
   - Read-only root filesystem
   - All capabilities dropped (+ NET_RAW for DNS)
   - tmpfs /tmp (100MB)
   - Resource limits: 2 CPU, 2GB RAM per sandbox
   - PID limit: 100

7. **`cluster.sh` changes**:
   - `ENABLE_SANDBOX=true` in `.env` activates sandbox overlay
   - `sandbox` added to build services list

### Container Networking

```
Sandbox CAN reach:
  - NATS (agent bus, lifecycle events)
  - MCP server (skills, connectors, keys)
  - Internet (web search, web crawl, log shipping)

Sandbox CANNOT reach:
  - PostgreSQL
  - Qdrant
  - MinIO
  - Redis
  - Embedder
```

### Startup Performance

| Metric | Cold Start | Warm Pool |
|--------|-----------|-----------|
| Time to first message | ~1.5s | ~50ms |
| User-perceived latency | noticeable | imperceptible |
| Resource waste | none | ~20MB per idle container |

---

## Phase 5: Chat Integration (Week 8)

**Goal**: Wire sandbox into existing WebSocket chat flow with per-session toggle.

### Deliverables

1. **Modified ChatHandler** (`src/api/websocket/chat_handler.py`):
   - New code path when sandbox/agent mode enabled
   - Sandbox assignment via `SandboxManager.assign()`
   - Message relay: WebSocket → NATS → Sandbox → NATS → WebSocket

2. **Streaming token relay**:
   - Sandbox publishes tokens to `sandbox.{sid}.stream`
   - API subscribes and forwards to WebSocket client
   - Event types: `token`, `tool_call.start`, `tool_call.result`, `complete`

3. **Session pinning**: Once assigned, all messages route to same sandbox

4. **Graceful shutdown**: 30s drain period, flush pending responses

5. **REST endpoints**:
   - `GET /sandbox/pool` — Pool status (admin only)
   - `POST /sandbox/sessions/{id}/release` — Release sandbox
   - `GET /sandbox/sessions` — User's active sandbox sessions

---

## Phase 6: Observability (Week 9)

**Goal**: End-to-end tracing, metrics, cost tracking, dashboards.

### Deliverables

1. **OTEL Collector** (new Docker service):
   - Receives OTLP from ephemeral containers
   - Fan-out: traces → Langfuse, metrics → Prometheus
   - Config: `config/observability/otel-collector/config.yaml`

2. **Agent tracing middleware**:
   - `ObservabilityMiddleware` (ChatMiddleware) — LLM call spans
   - `ToolObservabilityMiddleware` (FunctionMiddleware) — tool call spans
   - W3C Trace Context propagation via `TRACEPARENT` env var

3. **MCP server tracing**:
   - Span per tool call with server name, transport, duration
   - Audit log entries as OTEL events

4. **Cost tracking**:
   - Token usage per run with model-specific pricing
   - Langfuse cost_details attributes
   - Prometheus counters for per-user aggregation

5. **Grafana dashboards** (3 new):
   - Agent Runs Overview (rate, duration, errors, top tools)
   - MCP Server Health (connections, call rate, latency, denied calls)
   - Agent Cost Analysis (daily cost, by model, by user, projection)

6. **Alerting rules**:
   - Agent error rate > 10%
   - Agent P95 latency > 60s
   - MCP server disconnected
   - Daily cost > $50

---

## Phase 7: Skills Migration (Week 10)

**Goal**: Delete native tools, port remaining Moltbot skills, build EchoMind skills.

### Deliverables

1. **Delete 29 native tools**:
   ```
   DELETE: filesystem.py, directory.py, git.py, git_extended.py,
           system.py, text.py, web.py
   KEEP:   edit.py (optional native), execution.py (bash core),
           registry.py (simplified)
   ```

2. **Port high-value Moltbot skills** (beyond those in Phase 3):
   - `tmux` — Multi-session management
   - `nano-pdf` — PDF processing
   - `1password` — Secrets management
   - `obsidian` — Note management
   - `openai-whisper` — Audio transcription
   - `openai-image-gen` — Image generation

3. **EchoMind-specific skills**:
   - `echomind-search` — RAG search via MCP
   - `echomind-documents` — Document management
   - `echomind-connectors` — Connector management

---

## Phase 8: Auth & Security Hardening (Week 11+)

**Goal**: Add zero-trust authentication between agent and MCP server. This is deferred from Phase 1 to keep initial development fast.

### Deliverables

1. **MCP Gateway auth layer** (`src/mcp_gateway/auth/`):
   - `token.py` — JWT validation, `SessionContext` extraction
   - JWT bearer token on every MCP request (RS256, 15-min TTL)
   - `SessionContext`: session_id, user_id, org_id, groups, permissions
   - Reuses existing `PermissionChecker` from `src/api/logic/permissions.py`

2. **API token generation**:
   - `src/api/logic/mcp_token_service.py` — Generate short-lived JWTs for sandbox sessions
   - Token injected as `MCP_SESSION_TOKEN` env var when sandbox container starts

3. **Rate limiting**:
   - Per-user per-tool sliding window limiter
   - Configurable limits per service/tool
   - Returns 429 with retry-after on breach

4. **RBAC enforcement**:
   - Permission-scoped Qdrant collection access (user/team/org)
   - Connector access checked via existing `PermissionChecker`
   - Skill execution gated by trust level

5. **Security hardening**:
   - NATS per-sandbox authorization (session-scoped subjects)
   - Network firewall rules (iptables)
   - Command analysis in MCP (block dangerous patterns)
   - Penetration testing of sandbox escape vectors

### Why Deferred

- Internal Docker network provides sufficient isolation for development
- Auth adds complexity that slows down iteration on the core skill/sandbox flow
- All the auth infrastructure (JWT, RBAC, PermissionChecker) already exists — wiring it in is mechanical work
- Better to validate the architecture first, then lock it down

---

## Feasibility Assessment

### "Will the MCP gateway work for skills and other connections?"

**Yes.** FastMCP 3.x provides the entire infrastructure:

| Concern | Assessment |
|---------|------------|
| Protocol compliance | FastMCP handles JSON-RPC 2.0, Streamable HTTP |
| Auth | Built-in BearerTokenAuth maps to our JWT model |
| Tool registration | `@mcp.tool` decorator with auto-generated schemas |
| Middleware | Rate limiting, audit logging as composable layers |
| Existing code reuse | PermissionChecker, QdrantDB, EmbedderClient imported directly |
| MCPManager changes | None — HTTP transport + bearer headers already supported |
| Latency | ~10-50ms per MCP call (negligible for most operations) |

### "How hard compared to Moltbot's plain approach?"

| Aspect | Moltbot | EchoMind (MCP) | Overhead |
|--------|---------|----------------|----------|
| Skill loading | Built-in (`loadWorkspaceSkillEntries`) | MCP server reads SKILL.md at startup | +200 LOC |
| Skill execution | Direct `subprocess` | MCP call → subprocess | +10-50ms latency |
| Tool schema | Minimal (bash tool) | Per-skill MCP tool registration | +100 LOC |
| Security | Optional sandbox | Mandatory sandbox + zero-trust | +500 LOC |
| Auth | Per-channel credentials | JWT per session + RBAC | +300 LOC |
| Total extra code | — | ~1,100 LOC over Moltbot's approach | Justified by security |

**Bottom line**: EchoMind's MCP approach adds ~1,100 LOC and ~10-50ms latency over Moltbot's direct approach. The overhead is entirely security-related (JWT auth, RBAC, audit logging, sandbox isolation). The skill format (SKILL.md) and skill execution pattern are identical.

---

## Resource Requirements

### Server (demo.echomind.ch)

| Component | CPU | RAM | Storage |
|-----------|-----|-----|---------|
| Existing services | ~10 cores | ~10 GB | existing |
| MCP gateway (1x) | 1 core | 512 MB | — |
| OTEL collector (1x) | 0.5 cores | 256 MB | — |
| Sandbox pool (3 warm) | 1.5 cores | 1.5 GB | — |
| Sandbox active (8 max) | 16 cores | 16 GB | — |
| **Peak total** | ~29 cores | ~28 GB | — |

Current server (8 CPU, 32GB RAM) can support ~4 concurrent agent sessions. A 32-core/64GB server handles the full 8+3 sandbox target comfortably.

### Development Effort

| Phase | Weeks | LOC | Tests |
|-------|-------|-----|-------|
| 1. MCP Gateway Core | 2 | ~800 | ~30 |
| 2. Connectors & API Proxy | 1 | ~400 | ~20 |
| 3. Skills Engine | 1 | ~350 | ~15 |
| 4. Sandbox Foundation | 2 | ~1,000 | ~25 |
| 5. Chat Integration | 1 | ~400 | ~15 |
| 6. Observability | 1 | ~500 | ~15 |
| 7. Skills Migration | 1 | ~200 (+delete 1,100) | ~10 |
| **Total** | **9** | **~3,650** | **~130** |

---

## Risk Assessment

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| FastMCP 3.x breaking changes | Medium | Low | Pin version, vendor if needed |
| Docker socket access security | High | Medium | Use Docker SDK read-only, rootless Docker |
| Sandbox escape via kernel vuln | High | Low | Read-only FS, no caps, resource limits, gVisor future |
| NATS message ordering | Medium | Low | Per-session subjects ensure ordering |
| Cold start latency | Medium | Medium | Warm pool eliminates for typical load |
| Moltbot skill incompatibility | Low | Medium | Test each skill individually, adapt format |
| Cost overrun from LLM calls | Medium | Medium | Cost tracking, per-user limits, alerting |

---

## Implementation Order Rationale

1. **MCP Gateway first** — It's the trust boundary and the most architecturally novel component. Building it validates FastMCP and the zero-trust model before investing in sandbox infrastructure.

2. **Skills engine before sandbox** — Skills can be tested via MCP without sandboxes (run locally first). Validates the SKILL.md → MCP tool → execution pipeline.

3. **Sandbox after MCP** — The sandbox depends on MCP being operational. By this point, the MCP gateway has been tested with real tools.

4. **Chat integration after sandbox** — Requires both sandbox and MCP to be working. This is integration work, not new architecture.

5. **Observability late** — Can be added incrementally without blocking other work. The OTEL Collector is a standalone service.

6. **Skills migration last** — Deleting native tools is a cleanup step. The new skill-based approach must be proven before removing the old one.

---

## Success Criteria

- [ ] Agent runs in ephemeral Docker container, destroyed after session
- [ ] All tool access goes through MCP gateway with JWT validation
- [ ] User can search their documents via agent (MCP → Qdrant)
- [ ] Skills execute in subprocess with timeout and output limits
- [ ] 27+ Moltbot skills ported and functional
- [ ] End-to-end trace visible in Langfuse: API → sandbox → MCP → tool
- [ ] Grafana dashboards show agent metrics, costs, errors
- [ ] No direct database access from sandbox container
- [ ] Warm pool delivers <100ms assignment time
- [ ] 130+ new tests, all passing

---

## References

- [agent_sandbox-containers.md](agent_sandbox-containers.md) — Container architecture, lifecycle, security
- [agent_mcp-gateway.md](agent_mcp-gateway.md) — MCP server design, FastMCP, zero-trust model
- [agent_skills-migration.md](agent_skills-migration.md) — Tool migration analysis, Moltbot skills
- [agent_observability.md](agent_observability.md) — OTEL, Langfuse, Grafana dashboards
- [agent_infrastructure.md](agent_infrastructure.md) — NATS, Docker Compose, cluster.sh
- [FastMCP 3.x](https://gofastmcp.com) — MCP framework
- [Docker Sandboxes](https://docs.docker.com/ai/sandboxes) — Docker AI sandbox documentation
- [Zero-Trust AI Agents](https://genmind.ch/posts/Securing-AI-Agents-with-Zero-Trust-and-Sandboxing/) — User's blog post
