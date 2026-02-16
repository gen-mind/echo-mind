# Ephemeral Sandboxed Agent Container Architecture

> Design document for running EchoMind agents in ephemeral Docker containers
> with per-session isolation, MCP integration, and NATS-based communication.

---

## 1. Architecture Overview

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
                       JetStream       (sandbox        (sandbox
                       (agent bus)      state DB)       session cache)
                          |
            +-------------+-------------+-------------+
            |             |             |             |
      [sandbox-0]   [sandbox-1]   [sandbox-2]   [sandbox-N]
      (ephemeral)   (ephemeral)   (ephemeral)   (ephemeral)
            |             |             |             |
            +------+------+------+------+
                   |
              [MCP Server]
              (shared, persistent)
              - Skills registry
              - Data connectors
              - API key vault
```

### Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Container lifecycle | Ephemeral per session | Full isolation, no state leaks between users |
| API-to-sandbox comm | NATS JetStream | Already deployed, supports request-reply and streaming |
| Sandbox-to-MCP comm | HTTP/SSE (MCP protocol) | Standard MCP transport, zero-trust per-request auth |
| Container pool | Warm pool (pre-created) | Eliminates cold start (~2s create time) |
| Internet access | Direct outbound | Agent needs web crawling, search, log shipping |
| DB access | Blocked (no backend network) | All data access through MCP server |
| Orchestrator | API service via Docker SDK | No K8s needed, matches existing Docker Compose stack |

---

## 2. Network Topology

```
+------------------------------------------------------------------+
|                        Docker Host                                |
|                                                                   |
|  +---------------------------+  +-----------------------------+   |
|  |     backend network       |  |     frontend network        |   |
|  |                           |  |                             |   |
|  | [postgres] [qdrant]       |  | [traefik] [webui]          |   |
|  | [nats]     [redis]        |  |                             |   |
|  | [minio]    [embedder]     |  |                             |   |
|  | [api]      [mcp-server]   |  | [api]                      |   |
|  |                           |  |                             |   |
|  +---------------------------+  +-----------------------------+   |
|                                                                   |
|  +---------------------------+                                    |
|  |     sandbox network       |  <-- isolated, per-sandbox         |
|  |                           |                                    |
|  | [sandbox-0]  [sandbox-1]  |                                    |
|  |                           |                                    |
|  | CAN reach:               |                                    |
|  |   - nats (agent bus)     |                                    |
|  |   - mcp-server (skills)  |                                    |
|  |   - internet (outbound)  |                                    |
|  |                           |                                    |
|  | CANNOT reach:            |                                    |
|  |   - postgres             |                                    |
|  |   - qdrant               |                                    |
|  |   - minio                |                                    |
|  |   - redis                |                                    |
|  |   - embedder             |                                    |
|  +---------------------------+                                    |
+------------------------------------------------------------------+
```

### Network Implementation

```yaml
# docker-compose-sandbox.yml (additive overlay)
networks:
  sandbox:
    driver: bridge
    internal: false  # allows internet access
    ipam:
      config:
        - subnet: 172.30.0.0/16
```

Sandbox containers connect to TWO networks:
1. **sandbox** -- isolated network with internet access
2. **A restricted bridge to NATS and MCP only** -- via iptables rules

#### Firewall Rules (applied via container labels + startup script)

```bash
# Block sandbox -> backend (postgres, qdrant, minio, redis, embedder)
# Allow sandbox -> nats:4222 (NATS client port)
# Allow sandbox -> mcp-server:8080 (MCP HTTP endpoint)
# Allow sandbox -> internet (0.0.0.0/0 except backend subnet)

iptables -A FORWARD -s 172.30.0.0/16 -d 172.20.0.0/16 -j DROP  # block backend
iptables -A FORWARD -s 172.30.0.0/16 -d 172.20.0.10 -p tcp --dport 4222 -j ACCEPT  # nats
iptables -A FORWARD -s 172.30.0.0/16 -d 172.20.0.20 -p tcp --dport 8080 -j ACCEPT  # mcp
iptables -A FORWARD -s 172.30.0.0/16 -j ACCEPT  # internet
```

---

## 3. Sandbox Container Design

### 3.1 Base Image

```dockerfile
# src/sandbox/Dockerfile
# Multi-stage build for minimal attack surface

# ===============================================
# Stage 1: Builder
# ===============================================
FROM python:3.12.12-slim-bookworm AS builder

WORKDIR /build

COPY sandbox/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ===============================================
# Stage 2: Runtime
# ===============================================
FROM python:3.12.12-slim-bookworm

WORKDIR /app

# Minimal runtime deps: curl for healthcheck, no build tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages
COPY --from=builder /install /usr/local

# Copy application code
COPY sandbox /app/sandbox
COPY echomind_lib /app/echomind_lib

ENV PYTHONPATH="/app"

# Non-root user (CRITICAL for security)
RUN useradd -m -u 1000 -s /bin/false sandboxuser && \
    chown -R sandboxuser:sandboxuser /app

# Resource limits enforced at container level, not in image
# No volumes mounted by default -- ephemeral filesystem only

USER sandboxuser

HEALTHCHECK --interval=10s --timeout=5s --start-period=3s --retries=2 \
    CMD curl -f http://localhost:8080/healthz || exit 1

EXPOSE 8080

CMD ["python", "-m", "sandbox.main"]
```

### 3.2 Requirements

```
# src/sandbox/requirements.txt
nats-py>=2.9.0
httpx>=0.27.0            # MCP client HTTP transport
pydantic>=2.0.0
pydantic-settings>=2.0.0
semantic-kernel>=1.0.0   # Agent framework
openai>=1.0.0            # LLM client
```

### 3.3 Container Resource Limits

```yaml
# Applied programmatically via Docker SDK
deploy:
  resources:
    limits:
      cpus: "2.0"
      memory: 2G
    reservations:
      cpus: "0.5"
      memory: 512M

# Security options
security_opt:
  - no-new-privileges:true
read_only: true           # Read-only root filesystem
tmpfs:
  - /tmp:size=100M        # Writable temp only
cap_drop:
  - ALL                   # Drop all Linux capabilities
cap_add:
  - NET_RAW              # Required for DNS resolution
```

### 3.4 Injected Context (Environment Variables)

Each sandbox container receives session-specific context at creation:

```bash
# Identity
SANDBOX_SESSION_ID=sess_abc123def456
SANDBOX_USER_ID=42
SANDBOX_ORG_ID=org_echomind
SANDBOX_PERMISSIONS=read,search,web_crawl,code_exec

# Communication
SANDBOX_NATS_URL=nats://nats:4222
SANDBOX_NATS_SUBJECT_IN=sandbox.sess_abc123def456.input
SANDBOX_NATS_SUBJECT_OUT=sandbox.sess_abc123def456.output
SANDBOX_NATS_SUBJECT_STREAM=sandbox.sess_abc123def456.stream

# MCP
SANDBOX_MCP_URL=http://mcp-server:8080
SANDBOX_MCP_AUTH_TOKEN=<short-lived JWT, 1h TTL>

# LLM (injected per-session from assistant config)
SANDBOX_LLM_PROVIDER=openai
SANDBOX_LLM_MODEL=gpt-4o
SANDBOX_LLM_API_KEY=<encrypted, decrypted at runtime>
SANDBOX_LLM_ENDPOINT=https://api.openai.com/v1

# Agent behavior
SANDBOX_AGENT_INSTRUCTIONS="You are EchoMind Assistant..."
SANDBOX_AGENT_PROFILE=full
SANDBOX_MAX_TURNS=50
SANDBOX_TIMEOUT_SECONDS=300

# Observability
SANDBOX_LOG_LEVEL=INFO
LANGFUSE_PUBLIC_KEY=<optional>
LANGFUSE_SECRET_KEY=<optional>
LANGFUSE_BASE_URL=http://langfuse-web:3000
```

---

## 4. Lifecycle Management

### 4.1 State Machine

```
                 +----------+
                 |          |
        create   |   WARM   |  pre-created, idle, waiting
        -------->|  (pool)  |  in warm pool
                 |          |
                 +----+-----+
                      |
                      | assign(session_id, user_id)
                      v
                 +----------+
                 |          |
                 | ASSIGNED |  env vars injected, agent booting
                 |          |
                 +----+-----+
                      |
                      | healthcheck passes
                      v
                 +----------+
                 |          |
                 |  ACTIVE  |  processing messages via NATS
                 |          |
                 +----+-----+
                      |
                      | session ends OR timeout OR error
                      v
                 +----------+
                 |          |
                 | DRAINING |  finishing current turn, flushing logs
                 |          |  (30s grace period)
                 +----+-----+
                      |
                      | drained or grace period expired
                      v
                 +----------+
                 |          |
                 | DESTROYED|  container removed, resources freed
                 |          |  new WARM container created to replace
                 +----------+
```

### 4.2 Warm Pool Strategy

The warm pool eliminates cold-start latency. Pre-created containers sit idle
consuming minimal resources (~20MB each) until assigned to a session.

```
Target pool size:  SANDBOX_POOL_SIZE (default: 3)
Max containers:    SANDBOX_MAX_INSTANCES (default: 15)
Idle timeout:      SANDBOX_IDLE_TIMEOUT (default: 300s)
Session timeout:   SANDBOX_SESSION_TIMEOUT (default: 3600s)

Pool replenishment:
  - After each container is assigned, create a replacement
  - Periodic reconciliation loop (every 30s) ensures pool size
  - If pool is exhausted, create on-demand (cold start ~2-3s)
```

### 4.3 Sandbox Manager (runs inside API service)

```python
# src/api/sandbox/manager.py

"""
Sandbox Manager -- orchestrates ephemeral agent containers.

Uses Docker SDK to create, assign, monitor, and destroy sandbox containers.
Maintains a warm pool for instant session assignment.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import docker
from docker.models.containers import Container
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class SandboxSettings(BaseSettings):
    """Sandbox manager configuration."""

    pool_size: int = Field(3, description="Warm pool target size")
    max_instances: int = Field(15, description="Maximum concurrent sandboxes")
    idle_timeout: int = Field(300, description="Seconds before idle sandbox is recycled")
    session_timeout: int = Field(3600, description="Max session duration in seconds")
    image: str = Field(
        "gsantopaolo/echomind-sandbox:latest",
        description="Sandbox Docker image",
    )
    network: str = Field("sandbox", description="Docker network for sandboxes")
    cpu_limit: float = Field(2.0, description="CPU cores per sandbox")
    memory_limit: str = Field("2g", description="Memory limit per sandbox")

    model_config = SettingsConfigDict(env_prefix="SANDBOX_")


class SandboxState(BaseModel):
    """Tracks a single sandbox container's state."""

    container_id: str
    container_name: str
    status: str = "warm"  # warm | assigned | active | draining | destroyed
    session_id: str | None = None
    user_id: int | None = None
    assigned_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SandboxManager:
    """
    Manages ephemeral sandbox container lifecycle.

    Responsibilities:
    - Maintain warm pool of pre-created containers
    - Assign containers to sessions on demand
    - Monitor container health and enforce timeouts
    - Destroy containers when sessions end
    - Replenish pool after assignment
    """

    def __init__(self, settings: SandboxSettings | None = None) -> None:
        self._settings = settings or SandboxSettings()
        self._docker = docker.from_env()
        self._sandboxes: dict[str, SandboxState] = {}  # container_id -> state
        self._session_map: dict[str, str] = {}  # session_id -> container_id
        self._lock = asyncio.Lock()
        self._reconcile_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Start the sandbox manager and fill the warm pool."""
        logger.info("🏗️ Starting sandbox manager (pool_size=%d)", self._settings.pool_size)
        await self._fill_pool()
        self._reconcile_task = asyncio.create_task(self._reconciliation_loop())

    async def stop(self) -> None:
        """Stop all sandboxes and clean up."""
        if self._reconcile_task:
            self._reconcile_task.cancel()
        for container_id in list(self._sandboxes.keys()):
            await self._destroy_sandbox(container_id)
        logger.info("🛑 Sandbox manager stopped")

    async def assign(
        self,
        session_id: str,
        user_id: int,
        env_vars: dict[str, str],
    ) -> SandboxState:
        """
        Assign a warm sandbox to a session.

        If no warm containers available, creates one on-demand.

        Args:
            session_id: Unique session identifier.
            user_id: User who owns this session.
            env_vars: Session-specific environment variables.

        Returns:
            SandboxState with assigned container info.

        Raises:
            RuntimeError: If max instances reached.
        """
        async with self._lock:
            # Find a warm container
            warm = [s for s in self._sandboxes.values() if s.status == "warm"]

            if warm:
                sandbox = warm[0]
                container = self._docker.containers.get(sandbox.container_id)
                # Inject env vars by exec-ing a setup script
                # (env vars set at creation for warm pool use generic defaults;
                #  session-specific vars are injected via NATS init message)
            else:
                if len(self._sandboxes) >= self._settings.max_instances:
                    raise RuntimeError("Max sandbox instances reached")
                sandbox = await self._create_sandbox(env_vars)

            sandbox.status = "assigned"
            sandbox.session_id = session_id
            sandbox.user_id = user_id
            sandbox.assigned_at = datetime.now(timezone.utc)
            self._session_map[session_id] = sandbox.container_id

        # Replenish pool in background
        asyncio.create_task(self._fill_pool())

        logger.info(
            "📦 Assigned sandbox %s to session %s (user %d)",
            sandbox.container_name,
            session_id,
            user_id,
        )
        return sandbox

    async def release(self, session_id: str) -> None:
        """
        Release and destroy a sandbox when session ends.

        Args:
            session_id: Session to release.
        """
        container_id = self._session_map.pop(session_id, None)
        if container_id:
            await self._destroy_sandbox(container_id)
            asyncio.create_task(self._fill_pool())

    async def get_for_session(self, session_id: str) -> SandboxState | None:
        """Look up sandbox by session ID."""
        container_id = self._session_map.get(session_id)
        if container_id:
            return self._sandboxes.get(container_id)
        return None

    # -- Internal methods --

    async def _create_sandbox(
        self,
        env_vars: dict[str, str] | None = None,
    ) -> SandboxState:
        """Create a new sandbox container."""
        name = f"sandbox-{uuid4().hex[:8]}"
        container = self._docker.containers.run(
            image=self._settings.image,
            name=name,
            detach=True,
            network=self._settings.network,
            environment=env_vars or {},
            mem_limit=self._settings.memory_limit,
            nano_cpus=int(self._settings.cpu_limit * 1e9),
            security_opt=["no-new-privileges:true"],
            cap_drop=["ALL"],
            cap_add=["NET_RAW"],
            read_only=True,
            tmpfs={"/tmp": "size=100M"},
            labels={
                "echomind.service": "sandbox",
                "echomind.managed": "true",
            },
            auto_remove=True,
        )

        state = SandboxState(
            container_id=container.id,
            container_name=name,
        )
        self._sandboxes[container.id] = state
        logger.info("🔨 Created sandbox %s", name)
        return state

    async def _destroy_sandbox(self, container_id: str) -> None:
        """Force-remove a sandbox container."""
        state = self._sandboxes.pop(container_id, None)
        if not state:
            return
        try:
            container = self._docker.containers.get(container_id)
            container.stop(timeout=5)
            container.remove(force=True)
        except docker.errors.NotFound:
            pass  # Already removed (auto_remove=True)
        except Exception as e:
            logger.warning("⚠️ Failed to destroy sandbox %s: %s", container_id, e)
        logger.info("💀 Destroyed sandbox %s", state.container_name)

    async def _fill_pool(self) -> None:
        """Ensure warm pool has enough containers."""
        async with self._lock:
            warm_count = sum(1 for s in self._sandboxes.values() if s.status == "warm")
            total = len(self._sandboxes)
            needed = min(
                self._settings.pool_size - warm_count,
                self._settings.max_instances - total,
            )

        for _ in range(max(0, needed)):
            try:
                await self._create_sandbox()
            except Exception as e:
                logger.warning("⚠️ Failed to create warm sandbox: %s", e)
                break

    async def _reconciliation_loop(self) -> None:
        """Periodic loop to enforce timeouts and replenish pool."""
        while True:
            try:
                await asyncio.sleep(30)
                now = datetime.now(timezone.utc)

                for container_id, state in list(self._sandboxes.items()):
                    # Enforce session timeout
                    if (
                        state.status == "active"
                        and state.assigned_at
                        and (now - state.assigned_at).total_seconds()
                        > self._settings.session_timeout
                    ):
                        logger.warning(
                            "⏰ Session timeout for sandbox %s (session %s)",
                            state.container_name,
                            state.session_id,
                        )
                        if state.session_id:
                            self._session_map.pop(state.session_id, None)
                        await self._destroy_sandbox(container_id)

                    # Enforce idle timeout for warm containers
                    if (
                        state.status == "warm"
                        and (now - state.created_at).total_seconds()
                        > self._settings.idle_timeout * 2  # 2x idle for warm
                    ):
                        await self._destroy_sandbox(container_id)

                await self._fill_pool()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception("❌ Reconciliation loop error: %s", e)
```

---

## 5. Session Routing

### 5.1 Message Flow

```
User                WebUI              API                NATS               Sandbox
 |                   |                  |                   |                   |
 |--chat.start------>|                  |                   |                   |
 |                   |--WS: chat.start->|                   |                   |
 |                   |                  |                   |                   |
 |                   |                  |--1. lookup/create sandbox----------->|
 |                   |                  |     (SandboxManager.assign)          |
 |                   |                  |                   |                   |
 |                   |                  |--2. PUB sandbox.{sid}.input--------->|
 |                   |                  |     {query, context, sources}        |
 |                   |                  |                   |                   |
 |                   |                  |                   |<--3. SUB sandbox.{sid}.input
 |                   |                  |                   |                   |
 |                   |                  |                   |   [agent runs]    |
 |                   |                  |                   |   [calls MCP]     |
 |                   |                  |                   |   [calls LLM]     |
 |                   |                  |                   |                   |
 |                   |                  |<--4. PUB sandbox.{sid}.stream--------|
 |                   |                  |     {type: token, data: "Hello"}     |
 |                   |<--WS: token------|                   |                   |
 |<--render----------|                  |                   |                   |
 |                   |                  |                   |                   |
 |                   |                  |<--5. PUB sandbox.{sid}.stream--------|
 |                   |                  |     {type: complete, message_id: X}  |
 |                   |<--WS: complete---|                   |                   |
 |<--done------------|                  |                   |                   |
```

### 5.2 NATS Subject Design

```
# Per-session subjects (ephemeral, exist only while sandbox is active)
sandbox.{session_id}.input       # API -> Sandbox: user messages, commands
sandbox.{session_id}.output      # Sandbox -> API: final responses
sandbox.{session_id}.stream      # Sandbox -> API: streaming tokens
sandbox.{session_id}.control     # API -> Sandbox: cancel, shutdown, config
sandbox.{session_id}.health      # Sandbox -> API: heartbeat, status

# Management subjects (persistent, for SandboxManager)
sandbox.mgmt.assign              # Request sandbox assignment
sandbox.mgmt.release             # Release sandbox
sandbox.mgmt.status              # Pool status query

# JetStream stream for durability (agent audit log)
sandbox-audit                    # All sandbox events for replay/debugging
```

### 5.3 NATS Stream Configuration

```python
# Added to existing NATS JetStream setup
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
    "max_age": 3600 * 1_000_000_000,  # 1 hour in nanoseconds
    "storage": "memory",  # Ephemeral -- no need to persist sandbox chatter
    "discard": "old",
}

SANDBOX_AUDIT_STREAM_CONFIG = {
    "name": "sandbox-audit",
    "subjects": ["sandbox.audit.>"],
    "retention": "limits",
    "max_age": 7 * 24 * 3600 * 1_000_000_000,  # 7 days
    "storage": "file",  # Persistent for audit trail
}
```

---

## 6. Database Schema for Sandbox State

### 6.1 sandbox_sessions table

```sql
-- Tracks sandbox container assignments and lifecycle
CREATE TABLE sandbox_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id VARCHAR(255) UNIQUE NOT NULL,       -- Routing key (matches NATS subject)
    user_id INT NOT NULL REFERENCES users(id),
    chat_session_id INT REFERENCES chat_sessions(id),  -- Links to existing chat system

    -- Container info
    container_id VARCHAR(64) NOT NULL,              -- Docker container ID
    container_name VARCHAR(255) NOT NULL,
    container_ip INET,                              -- Sandbox network IP

    -- State machine
    status VARCHAR(20) NOT NULL DEFAULT 'assigned',  -- assigned|active|draining|destroyed
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    activated_at TIMESTAMPTZ,                        -- When healthcheck first passed
    drained_at TIMESTAMPTZ,                          -- When draining started
    destroyed_at TIMESTAMPTZ,                        -- When container was removed

    -- Agent configuration snapshot
    agent_config JSONB NOT NULL DEFAULT '{}',        -- Agent instructions, model, tools
    permissions TEXT[] NOT NULL DEFAULT '{}',         -- User permissions for this session

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
```

### 6.2 sandbox_events table (audit log)

```sql
-- Immutable audit log of all sandbox lifecycle events
CREATE TABLE sandbox_events (
    id BIGSERIAL PRIMARY KEY,
    sandbox_session_id UUID NOT NULL REFERENCES sandbox_sessions(id),
    event_type VARCHAR(50) NOT NULL,    -- created|assigned|activated|message|tool_call|
                                        -- mcp_call|error|timeout|drained|destroyed
    event_data JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_sandbox_events_session ON sandbox_events (sandbox_session_id, created_at);
CREATE INDEX idx_sandbox_events_type ON sandbox_events (event_type, created_at DESC);

-- Partition by month for large deployments
-- CREATE TABLE sandbox_events_2026_02 PARTITION OF sandbox_events
--     FOR VALUES FROM ('2026-02-01') TO ('2026-03-01');
```

### 6.3 sandbox_pool_status (materialized view for monitoring)

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

---

## 7. MCP Integration

### 7.1 Architecture

```
+---------------------+          +---------------------------+
|    Sandbox (N)      |          |    MCP Server (1)         |
|                     |  HTTPS   |                           |
| [Agent Process] ----+--------->| [Skills Registry]         |
|                     |          | [Data Connectors]         |
| Headers:            |          | [API Key Vault]           |
|  X-Session-Id       |          |                           |
|  X-User-Id          |          | Zero-trust validation:    |
|  X-Permissions      |          |  1. Verify JWT token      |
|  Authorization:     |          |  2. Check session_id      |
|  Bearer <JWT>       |          |     exists in DB          |
|                     |          |  3. Check user_id matches |
+---------------------+          |  4. Check permissions     |
                                 |     allow this tool       |
                                 +---------------------------+
                                           |
                                     [backend network]
                                           |
                                 +---------+---------+
                                 |         |         |
                              [Qdrant] [Postgres] [MinIO]
```

### 7.2 MCP Zero-Trust Request Flow

Every MCP request from a sandbox carries:

```http
POST /mcp/v1/tools/call HTTP/1.1
Host: mcp-server:8080
Authorization: Bearer eyJhbGciOiJFUzI1NiJ9...
X-Sandbox-Session-Id: sess_abc123def456
X-Sandbox-User-Id: 42
X-Sandbox-Permissions: read,search,web_crawl
Content-Type: application/json

{
  "tool": "vector_search",
  "arguments": {
    "query": "quarterly revenue Q4",
    "collection": "user_42",
    "limit": 5
  }
}
```

MCP server validates:
1. **JWT signature** -- token was issued by API, not forged
2. **Session exists** -- `sess_abc123def456` is in `sandbox_sessions` with status=active
3. **User matches** -- user_id=42 matches the session's user_id
4. **Permission check** -- `read` permission allows `vector_search` tool
5. **Collection scope** -- user 42 can only access `user_42`, groups they belong to, and `org`

### 7.3 MCP Server Docker Compose

```yaml
# Added to docker-compose.yml
  mcp-server:
    image: gsantopaolo/echomind-mcp:${MCP_VERSION:-0.1.0-beta.1}
    build:
      context: ../../src
      dockerfile: mcp/Dockerfile
    container_name: echomind-mcp
    hostname: mcp-server
    env_file:
      - ${CONFIG_PATH}/mcp/mcp.env
    environment:
      - MCP_DATABASE_URL=postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${API_DB_NAME}
      - MCP_QDRANT_HOST=qdrant
      - MCP_QDRANT_PORT=6333
      - MCP_MINIO_ENDPOINT=minio:9000
      - MCP_MINIO_ACCESS_KEY=${MINIO_ROOT_USER}
      - MCP_MINIO_SECRET_KEY=${MINIO_ROOT_PASSWORD}
      - MCP_NATS_URL=nats://nats:4222
      - MCP_EMBEDDER_HOST=embedder
      - MCP_EMBEDDER_PORT=50051
      - MCP_JWT_SECRET=${MCP_JWT_SECRET}
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/healthz"]
      interval: 30s
      timeout: 10s
      start_period: 15s
      retries: 3
    depends_on:
      postgres:
        condition: service_healthy
      qdrant:
        condition: service_healthy
      nats:
        condition: service_healthy
    restart: unless-stopped
    networks:
      - backend
      - sandbox  # Accessible from sandboxes
    labels:
      - "traefik.enable=false"
```

---

## 8. Sandbox Container Internal Architecture

### 8.1 Process Layout Inside Container

```
sandbox container (1 process, async Python)
|
+-- main.py
    |
    +-- NATS subscriber (input subject)
    |   Receives: user messages, control commands
    |
    +-- Agent Runtime (Semantic Kernel)
    |   |
    |   +-- LLM Client (direct HTTPS to OpenAI/Anthropic)
    |   +-- MCP Client (HTTP to mcp-server:8080)
    |   +-- Tool execution (sandboxed: web_search, web_crawl)
    |
    +-- NATS publisher (stream + output subjects)
    |   Sends: streaming tokens, final responses, status
    |
    +-- Healthcheck HTTP server (:8080/healthz)
    |
    +-- Heartbeat loop (every 15s -> sandbox.{sid}.health)
    |
    +-- Graceful shutdown handler (SIGTERM)
```

### 8.2 Sandbox Main Loop

```python
# src/sandbox/main.py (simplified)

"""
Ephemeral sandbox agent process.

Receives messages via NATS, runs agent, streams responses back.
Designed to run as a single-session, single-user, ephemeral process.
"""

import asyncio
import logging
import signal
import os

import nats
from nats.aio.msg import Msg

logger = logging.getLogger(__name__)


class SandboxAgent:
    """Single-session agent running inside an ephemeral container."""

    def __init__(self) -> None:
        self.session_id = os.environ["SANDBOX_SESSION_ID"]
        self.user_id = int(os.environ["SANDBOX_USER_ID"])
        self.nats_url = os.environ["SANDBOX_NATS_URL"]
        self._nc: nats.NATS | None = None
        self._running = True

    async def start(self) -> None:
        """Connect to NATS and start processing."""
        self._nc = await nats.connect(self.nats_url)
        js = self._nc.jetstream()

        # Subscribe to input messages for this session
        sub = await js.subscribe(
            f"sandbox.{self.session_id}.input",
            stream="sandbox-stream",
        )

        logger.info("🚀 Sandbox agent started for session %s", self.session_id)

        # Publish ready status
        await self._nc.publish(
            f"sandbox.{self.session_id}.health",
            b'{"status": "ready"}',
        )

        # Process messages
        async for msg in sub.messages:
            if not self._running:
                break
            await self._handle_message(msg)

    async def _handle_message(self, msg: Msg) -> None:
        """Process a single input message."""
        import json
        data = json.loads(msg.data)
        msg_type = data.get("type")

        if msg_type == "query":
            await self._handle_query(data)
        elif msg_type == "cancel":
            pass  # Cancel current generation
        elif msg_type == "shutdown":
            self._running = False

        await msg.ack()

    async def _handle_query(self, data: dict) -> None:
        """Run agent on query and stream response."""
        query = data["query"]

        # Stream tokens back via NATS
        async for token in self._run_agent(query):
            await self._nc.publish(
                f"sandbox.{self.session_id}.stream",
                json.dumps({"type": "token", "data": token}).encode(),
            )

        # Send completion
        await self._nc.publish(
            f"sandbox.{self.session_id}.stream",
            json.dumps({"type": "complete"}).encode(),
        )

    async def _run_agent(self, query: str):
        """Execute agent with Semantic Kernel. Yields response tokens."""
        # ... agent execution with MCP tools ...
        pass

    async def stop(self) -> None:
        """Graceful shutdown."""
        self._running = False
        if self._nc:
            await self._nc.drain()
            await self._nc.close()
        logger.info("🛑 Sandbox agent stopped")


async def main() -> None:
    agent = SandboxAgent()

    loop = asyncio.get_event_loop()
    loop.add_signal_handler(signal.SIGTERM, lambda: asyncio.create_task(agent.stop()))

    await agent.start()


if __name__ == "__main__":
    asyncio.run(main())
```

---

## 9. API Integration

### 9.1 Modified Chat Handler

The existing `ChatHandler` in `src/api/websocket/chat_handler.py` gains a new
code path when sandbox mode is enabled:

```python
# Pseudocode for sandbox-aware chat handler

async def _process_chat(self, user, session_id, query, mode):
    if sandbox_enabled:
        # 1. Get or assign sandbox
        sandbox = await sandbox_manager.get_for_session(session_id)
        if not sandbox:
            sandbox = await sandbox_manager.assign(
                session_id=str(session_id),
                user_id=user.id,
                env_vars=self._build_sandbox_env(user, session_id),
            )

        # 2. Publish query to sandbox via NATS
        await nats_client.publish(
            f"sandbox.{session_id}.input",
            json.dumps({"type": "query", "query": query}).encode(),
        )

        # 3. Subscribe to response stream from sandbox
        sub = await nats_client.subscribe(f"sandbox.{session_id}.stream")
        async for msg in sub.messages:
            data = json.loads(msg.data)
            if data["type"] == "token":
                await self.manager.send_to_user(user.id, {
                    "type": "generation.token",
                    "session_id": session_id,
                    "token": data["data"],
                })
            elif data["type"] == "complete":
                await self.manager.send_to_user(user.id, {
                    "type": "generation.complete",
                    "session_id": session_id,
                })
                break
    else:
        # Existing non-sandbox RAG pipeline
        ...
```

### 9.2 REST Endpoints for Sandbox Management

```python
# src/api/routes/sandbox.py

@router.get("/sandbox/pool")
async def get_pool_status(user: AdminUser) -> dict:
    """Get current sandbox pool status (admin only)."""
    ...

@router.post("/sandbox/sessions/{session_id}/release")
async def release_sandbox(session_id: str, user: TokenUser) -> dict:
    """Release a sandbox session (owner or admin)."""
    ...

@router.get("/sandbox/sessions")
async def list_sandbox_sessions(user: TokenUser) -> list[dict]:
    """List user's active sandbox sessions."""
    ...
```

---

## 10. Docker Compose Integration

### 10.1 Sandbox Overlay File

```yaml
# deployment/docker-cluster/docker-compose-sandbox.yml
# Additive overlay for sandbox support

networks:
  sandbox:
    driver: bridge
    # NOT internal: sandboxes need internet access

services:
  # ===============================================
  # MCP Server -- shared tool/skill/connector gateway
  # ===============================================
  mcp-server:
    image: gsantopaolo/echomind-mcp:${MCP_VERSION:-0.1.0-beta.1}
    build:
      context: ../../src
      dockerfile: mcp/Dockerfile
    container_name: echomind-mcp
    hostname: mcp-server
    env_file:
      - ${CONFIG_PATH}/mcp/mcp.env
    environment:
      - MCP_DATABASE_URL=postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${API_DB_NAME}
      - MCP_QDRANT_HOST=qdrant
      - MCP_QDRANT_PORT=6333
      - MCP_MINIO_ENDPOINT=minio:9000
      - MCP_MINIO_ACCESS_KEY=${MINIO_ROOT_USER}
      - MCP_MINIO_SECRET_KEY=${MINIO_ROOT_PASSWORD}
      - MCP_NATS_URL=nats://nats:4222
      - MCP_EMBEDDER_HOST=embedder
      - MCP_EMBEDDER_PORT=50051
      - MCP_JWT_SECRET=${MCP_JWT_SECRET}
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/healthz"]
      interval: 30s
      timeout: 10s
      start_period: 15s
      retries: 3
    depends_on:
      postgres:
        condition: service_healthy
      qdrant:
        condition: service_healthy
    restart: unless-stopped
    networks:
      - backend
      - sandbox
    labels:
      - "traefik.enable=false"

  # ===============================================
  # API gains sandbox network + Docker socket access
  # ===============================================
  api:
    networks:
      - frontend
      - backend
      - sandbox
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro  # For Docker SDK
    environment:
      - SANDBOX_ENABLED=true
      - SANDBOX_POOL_SIZE=${SANDBOX_POOL_SIZE:-3}
      - SANDBOX_MAX_INSTANCES=${SANDBOX_MAX_INSTANCES:-15}
      - SANDBOX_IMAGE=gsantopaolo/echomind-sandbox:${SANDBOX_VERSION:-latest}
      - SANDBOX_NETWORK=sandbox
      - MCP_JWT_SECRET=${MCP_JWT_SECRET}

  # ===============================================
  # NATS gains sandbox network access
  # ===============================================
  nats:
    networks:
      - backend
      - sandbox
```

### 10.2 cluster.sh Changes

```bash
# Read ENABLE_SANDBOX from .env
SANDBOX_PROFILE=""
SANDBOX_FILES=""
_sandbox_enabled=false
if [ -f "$SCRIPT_DIR/.env" ] && grep -q "^[[:space:]]*ENABLE_SANDBOX[[:space:]]*=[[:space:]]*true" "$SCRIPT_DIR/.env" 2>/dev/null; then
    _sandbox_enabled=true
fi
if [ "$_sandbox_enabled" = true ]; then
    SANDBOX_FILES="-f docker-compose-sandbox.yml"
fi

# Add to all docker compose commands:
# docker compose ... $SANDBOX_FILES ...
```

---

## 11. Security Controls

### 11.1 Defense-in-Depth Layers

```
Layer 1: Container Isolation
  - Non-root user (uid 1000)
  - Read-only root filesystem
  - All capabilities dropped
  - no-new-privileges
  - tmpfs for /tmp only (100MB)
  - Memory limit (2GB)
  - CPU limit (2 cores)

Layer 2: Network Isolation
  - Dedicated sandbox network
  - No access to backend network (postgres, qdrant, minio, redis)
  - Only NATS and MCP-server reachable
  - Internet outbound allowed (for web search/crawl)

Layer 3: MCP Zero-Trust
  - Short-lived JWT per session (1h TTL)
  - Every MCP request authenticated + authorized
  - Permission-scoped data access (user/group/org collections)
  - Audit log of all MCP calls

Layer 4: NATS Subject Isolation
  - Each sandbox can only PUB/SUB to its own session subjects
  - NATS authorization rules prevent cross-session access
  - JetStream stream with per-subject message limits

Layer 5: Timeouts and Limits
  - Session timeout (default 1 hour)
  - Max turns per session (default 50)
  - Heartbeat monitoring (15s intervals)
  - Automatic destruction on timeout/crash
```

### 11.2 NATS Authorization (per-sandbox)

```
# nats-server.conf additions for sandbox auth
authorization {
  users = [
    # API service -- full access
    {
      user: "api"
      password: "$API_NATS_PASSWORD"
      permissions: {
        publish: ">"
        subscribe: ">"
      }
    }
    # Sandbox user template -- session-scoped
    # (Created dynamically via NATS account system)
    {
      user: "sandbox_$SESSION_ID"
      password: "$SESSION_NATS_TOKEN"
      permissions: {
        publish: [
          "sandbox.$SESSION_ID.output",
          "sandbox.$SESSION_ID.stream",
          "sandbox.$SESSION_ID.health",
          "sandbox.audit.>"
        ]
        subscribe: [
          "sandbox.$SESSION_ID.input",
          "sandbox.$SESSION_ID.control"
        ]
      }
    }
  ]
}
```

### 11.3 Threat Model

| Threat | Mitigation |
|--------|------------|
| Container escape | Read-only FS, no capabilities, no-new-privileges |
| Cross-session data leak | NATS subject isolation, separate container per session |
| MCP privilege escalation | JWT + permission check on every request |
| Resource exhaustion (fork bomb) | CPU/memory limits, PID limit (pids_limit: 100) |
| Network lateral movement | Sandbox network blocks backend services |
| Leaked API keys | Short-lived JWTs, env vars not persisted |
| Long-running attack | Session timeout + heartbeat monitoring |

---

## 12. Observability

### 12.1 Metrics (Prometheus)

```python
# Sandbox manager exposes these metrics at /metrics
sandbox_pool_size         # gauge: current pool size by status
sandbox_assign_duration   # histogram: time to assign a sandbox
sandbox_session_duration  # histogram: total session lifetime
sandbox_messages_total    # counter: messages processed per sandbox
sandbox_errors_total      # counter: errors by type
sandbox_mcp_calls_total   # counter: MCP calls per session
```

### 12.2 Logging

All sandbox containers ship logs to stdout (captured by Docker logging driver).
In production, configure Docker to forward to Loki:

```yaml
# docker-compose-sandbox.yml logging config
x-sandbox-logging: &sandbox-logging
  logging:
    driver: loki
    options:
      loki-url: "http://loki:3100/loki/api/v1/push"
      loki-external-labels: "service=sandbox,session_id={{.Name}}"
```

### 12.3 Langfuse Integration

Each sandbox session creates a Langfuse trace linked to the user and chat session.
All LLM calls, MCP tool invocations, and retrieval steps are recorded as spans.

---

## 13. Startup Optimization

### 13.1 Image Size Budget

| Layer | Estimated Size |
|-------|---------------|
| python:3.12-slim base | ~120MB |
| pip packages (SK + nats + httpx) | ~200MB |
| echomind_lib + sandbox code | ~5MB |
| **Total** | **~325MB** |

### 13.2 Cold Start Timeline

```
T+0.0s   docker create + start
T+0.3s   Python interpreter boots
T+0.8s   Imports complete
T+1.0s   NATS connection established
T+1.2s   Healthcheck passes -> status=active
T+1.5s   First message processable
```

### 13.3 Warm Pool Benefits

| Metric | Cold Start | Warm Pool |
|--------|-----------|-----------|
| Time to first message | ~1.5s | ~50ms (NATS PUB only) |
| User-perceived latency | noticeable | imperceptible |
| Resource waste | none | ~20MB per idle container |

---

## 14. Scaling Considerations

### 14.1 Single Host (Current: demo.echomind.ch)

```
Server: 8 CPU, 32GB RAM
Budget for sandboxes: 4 CPU, 16GB RAM
Per sandbox: 2 CPU, 2GB RAM max
Concurrent sandboxes: ~8 active + 3 warm = 11 total
Peak throughput: 8 simultaneous agent sessions
```

### 14.2 Multi-Host (Future)

When scaling beyond a single host, the architecture supports:
- **Docker Swarm mode**: SandboxManager uses Swarm API instead of local Docker API
- **NATS cluster**: Already supports clustering (disabled in current single-node config)
- **Redis for state**: Replace in-memory SandboxManager state with Redis for shared state
- **External container orchestrator**: Nomad or K8s for production-grade scheduling

### 14.3 Cost Model

| Scenario | Containers | RAM | CPU | Monthly Cost (cloud) |
|----------|-----------|-----|-----|---------------------|
| Dev | 3 warm + 2 active | 10GB | 5 cores | ~$50 |
| Small team (10 users) | 3 warm + 8 active | 22GB | 11 cores | ~$150 |
| Production (50 users) | 5 warm + 15 active | 40GB | 20 cores | ~$400 |

---

## 15. Implementation Phases

### Phase 1: Foundation (Week 1-2)
- [ ] Create `src/sandbox/` service with Dockerfile
- [ ] Implement SandboxManager in API service
- [ ] Add `sandbox_sessions` and `sandbox_events` tables (Alembic migration)
- [ ] NATS stream configuration for sandbox subjects
- [ ] Basic warm pool with create/assign/destroy lifecycle

### Phase 2: Communication (Week 3)
- [ ] NATS pub/sub integration in sandbox agent
- [ ] Streaming token relay: sandbox -> NATS -> API -> WebSocket -> client
- [ ] Modify ChatHandler for sandbox routing
- [ ] Heartbeat and timeout enforcement

### Phase 3: MCP Server (Week 4-5)
- [ ] Create `src/mcp/` service
- [ ] Implement skills: vector_search, document_fetch, web_search, web_crawl
- [ ] JWT-based zero-trust auth per request
- [ ] Permission-scoped data access

### Phase 4: Security Hardening (Week 6)
- [ ] NATS per-sandbox authorization
- [ ] Network firewall rules (iptables)
- [ ] Resource limits tuning
- [ ] Penetration testing of sandbox escape vectors

### Phase 5: Observability (Week 7)
- [ ] Prometheus metrics for sandbox pool
- [ ] Grafana dashboard for sandbox monitoring
- [ ] Langfuse trace integration
- [ ] Audit log queries and alerting

---

## 16. Detailed Implementation Plan

> This section provides a file-by-file implementation plan for Phase 4 (Sandbox Foundation)
> from the execution plan. A developer should be able to start coding immediately from this spec.

### 16.1 Complete File Tree

```
src/
├── api/
│   ├── sandbox/                          # NEW: Sandbox management subsystem
│   │   ├── __init__.py
│   │   ├── manager.py                    # SandboxManager — container lifecycle
│   │   ├── pool.py                       # SandboxPool — warm pool management
│   │   ├── config.py                     # SandboxSettings — Pydantic settings
│   │   ├── models.py                     # SandboxState, SandboxAssignment Pydantic models
│   │   └── exceptions.py                 # Sandbox-specific domain exceptions
│   ├── routes/
│   │   └── sandbox.py                    # NEW: REST endpoints for sandbox admin
│   └── logic/
│       └── exceptions.py                 # MODIFIED: Add SandboxError base class
│
├── echomind_lib/
│   └── db/
│       └── models/
│           ├── sandbox_session.py        # NEW: SandboxSession ORM model
│           └── sandbox_event.py          # NEW: SandboxEvent ORM model
│
├── sandbox/                              # NEW: Sandbox agent service
│   ├── __init__.py
│   ├── main.py                           # Entry point: NATS sub + health server
│   ├── config.py                         # SandboxAgentSettings (SANDBOX_ prefix)
│   ├── agent_runner.py                   # Semantic Kernel agent with MCP tools
│   ├── Dockerfile
│   └── requirements.txt
│
├── migration/
│   └── migrations/
│       └── versions/
│           └── 20260217_010000_add_sandbox_tables.py  # NEW: Alembic migration
│
└── deployment/
    └── docker-cluster/
        └── docker-compose-sandbox.yml    # NEW: Sandbox overlay
```

### 16.2 File Specifications

---

#### `src/api/sandbox/__init__.py`

**Purpose**: Package marker. Re-exports main classes for convenience.

```python
"""Sandbox management subsystem for ephemeral agent containers."""

from api.sandbox.manager import SandboxManager
from api.sandbox.pool import SandboxPool

__all__ = ["SandboxManager", "SandboxPool"]
```

---

#### `src/api/sandbox/config.py`

**Purpose**: Pydantic settings for sandbox configuration. Loaded from env vars with `SANDBOX_` prefix.

**Dependencies**: `pydantic`, `pydantic-settings`

```python
"""Sandbox configuration using Pydantic Settings."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class SandboxSettings(BaseSettings):
    """Configuration for the sandbox manager and warm pool.

    All settings are loaded from environment variables with the SANDBOX_ prefix.
    """

    model_config = SettingsConfigDict(
        env_prefix="SANDBOX_",
        case_sensitive=False,
    )

    # Feature flag
    enabled: bool = Field(
        default=False,
        description="Enable sandbox container support",
    )

    # Pool sizing
    pool_size: int = Field(
        default=3,
        ge=0,
        le=20,
        description="Number of warm (pre-created) containers to maintain",
    )
    max_instances: int = Field(
        default=15,
        ge=1,
        le=50,
        description="Maximum total concurrent sandbox containers",
    )

    # Timeouts (seconds)
    idle_timeout: int = Field(
        default=300,
        ge=60,
        description="Seconds before an idle warm container is recycled",
    )
    session_timeout: int = Field(
        default=3600,
        ge=60,
        description="Maximum session duration in seconds",
    )
    assignment_timeout: int = Field(
        default=30,
        ge=5,
        description="Seconds to wait for a container to become healthy after assignment",
    )
    drain_timeout: int = Field(
        default=30,
        ge=5,
        description="Grace period in seconds for draining before force-kill",
    )

    # Container image
    image: str = Field(
        default="gsantopaolo/echomind-sandbox:latest",
        description="Docker image for sandbox containers",
    )

    # Networking
    network: str = Field(
        default="sandbox",
        description="Docker network name for sandbox containers",
    )

    # Resource limits per container
    cpu_limit: float = Field(
        default=2.0,
        ge=0.25,
        description="CPU cores limit per sandbox container",
    )
    memory_limit: str = Field(
        default="2g",
        description="Memory limit per sandbox container (Docker format: 512m, 2g)",
    )
    pids_limit: int = Field(
        default=100,
        ge=10,
        description="Maximum number of processes per sandbox container",
    )
    tmpfs_size: str = Field(
        default="100M",
        description="Size of tmpfs mount for /tmp inside sandbox",
    )

    # Reconciliation
    reconcile_interval: int = Field(
        default=30,
        ge=10,
        description="Seconds between reconciliation loop iterations",
    )
    heartbeat_interval: int = Field(
        default=15,
        ge=5,
        description="Expected heartbeat interval from sandbox containers",
    )
    heartbeat_missed_threshold: int = Field(
        default=3,
        ge=2,
        description="Number of missed heartbeats before marking container unhealthy",
    )

    # NATS
    nats_url: str = Field(
        default="nats://nats:4222",
        description="NATS server URL for sandbox communication",
    )
```

---

#### `src/api/sandbox/models.py`

**Purpose**: Pydantic models for sandbox state tracking and API responses.

**Dependencies**: `pydantic`

```python
"""Sandbox state models for lifecycle tracking and API responses."""

from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, Field


class SandboxStatus(StrEnum):
    """Container lifecycle states.

    State machine: WARM -> ASSIGNED -> ACTIVE -> DRAINING -> DESTROYED
    """

    WARM = "warm"
    ASSIGNED = "assigned"
    ACTIVE = "active"
    DRAINING = "draining"
    DESTROYED = "destroyed"


class SandboxState(BaseModel):
    """In-memory state tracker for a single sandbox container.

    Tracks the container's lifecycle from creation through destruction.
    """

    container_id: str = Field(..., description="Docker container ID (64-char hex)")
    container_name: str = Field(..., description="Human-readable container name")
    status: SandboxStatus = Field(
        default=SandboxStatus.WARM,
        description="Current lifecycle state",
    )
    session_id: str | None = Field(
        default=None,
        description="Assigned session ID (None for warm containers)",
    )
    user_id: int | None = Field(
        default=None,
        description="Assigned user ID (None for warm containers)",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When the container was created",
    )
    assigned_at: datetime | None = Field(
        default=None,
        description="When the container was assigned to a session",
    )
    activated_at: datetime | None = Field(
        default=None,
        description="When the container healthcheck first passed",
    )
    last_heartbeat_at: datetime | None = Field(
        default=None,
        description="Last heartbeat received from the container",
    )


class SandboxAssignment(BaseModel):
    """Response model for sandbox assignment requests."""

    container_id: str
    container_name: str
    session_id: str
    nats_subject_in: str
    nats_subject_out: str
    nats_subject_stream: str
    nats_subject_control: str


class SandboxPoolStatus(BaseModel):
    """Response model for pool status queries."""

    warm_count: int = Field(..., description="Containers ready for assignment")
    assigned_count: int = Field(..., description="Containers assigned but not yet active")
    active_count: int = Field(..., description="Containers processing sessions")
    draining_count: int = Field(..., description="Containers shutting down")
    total_count: int = Field(..., description="Total managed containers")
    max_instances: int = Field(..., description="Configured maximum")
    pool_target: int = Field(..., description="Configured warm pool target")
```

---

#### `src/api/sandbox/exceptions.py`

**Purpose**: Domain exceptions for sandbox operations.

**Dependencies**: `api.logic.exceptions.APIError`

```python
"""Sandbox-specific domain exceptions.

Raised by SandboxManager/SandboxPool and converted to HTTP responses
by the error handler middleware.
"""

from fastapi import status

from api.logic.exceptions import APIError


class SandboxError(APIError):
    """Base exception for sandbox operations."""

    def __init__(self, message: str, status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR) -> None:
        super().__init__(
            code="SANDBOX_ERROR",
            message=message,
            status_code=status_code,
        )


class SandboxPoolExhaustedError(SandboxError):
    """Raised when no containers are available and max instances reached."""

    def __init__(self) -> None:
        super().__init__(
            message="Sandbox pool exhausted: maximum concurrent instances reached",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )


class SandboxNotFoundError(SandboxError):
    """Raised when a sandbox for a given session cannot be found."""

    def __init__(self, session_id: str) -> None:
        super().__init__(
            message=f"No sandbox found for session '{session_id}'",
            status_code=status.HTTP_404_NOT_FOUND,
        )


class SandboxAssignmentError(SandboxError):
    """Raised when container assignment fails."""

    def __init__(self, reason: str) -> None:
        super().__init__(
            message=f"Sandbox assignment failed: {reason}",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


class SandboxUnavailableError(SandboxError):
    """Raised when the sandbox subsystem is not ready."""

    def __init__(self) -> None:
        super().__init__(
            message="Sandbox subsystem is not available (Docker or NATS connection failed)",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
```

---

#### `src/api/sandbox/pool.py`

**Purpose**: Warm pool management. Handles pre-creation, replenishment, idle recycling.

**Dependencies**: `docker` (Docker SDK), `asyncio`, `logging`

```python
"""Warm pool manager for pre-created sandbox containers.

Maintains a target number of idle (warm) containers ready for instant assignment.
Handles creation, idle recycling, and pool replenishment.
"""

import asyncio
import logging
from datetime import datetime, timezone
from uuid import uuid4

import docker
import docker.errors
from docker.models.containers import Container

from api.sandbox.config import SandboxSettings
from api.sandbox.models import SandboxState, SandboxStatus

logger = logging.getLogger(__name__)


class SandboxPool:
    """Manages the warm pool of pre-created sandbox containers.

    Responsibilities:
    - Create containers with security hardening applied
    - Fill pool to target size on startup
    - Replenish pool after containers are claimed
    - Recycle stale warm containers past idle timeout
    - Provide containers for assignment on demand

    Args:
        settings: Sandbox configuration settings.
        docker_client: Docker SDK client instance.
    """

    def __init__(
        self,
        settings: SandboxSettings,
        docker_client: docker.DockerClient,
    ) -> None:
        self._settings = settings
        self._docker = docker_client
        self._containers: dict[str, SandboxState] = {}  # container_id -> state
        self._lock = asyncio.Lock()

    @property
    def warm_count(self) -> int:
        """Number of warm (idle) containers in the pool."""
        return sum(1 for s in self._containers.values() if s.status == SandboxStatus.WARM)

    @property
    def total_count(self) -> int:
        """Total number of managed containers (all states)."""
        return len(self._containers)

    def get_all_states(self) -> dict[str, SandboxState]:
        """Return a copy of all container states.

        Returns:
            Dictionary mapping container_id to SandboxState.
        """
        return dict(self._containers)

    def get_state(self, container_id: str) -> SandboxState | None:
        """Look up a container's state by ID.

        Args:
            container_id: Docker container ID.

        Returns:
            SandboxState if found, None otherwise.
        """
        return self._containers.get(container_id)

    def update_state(self, container_id: str, state: SandboxState) -> None:
        """Update a container's state.

        Args:
            container_id: Docker container ID.
            state: New state to store.
        """
        self._containers[container_id] = state

    def remove_state(self, container_id: str) -> SandboxState | None:
        """Remove and return a container's state.

        Args:
            container_id: Docker container ID.

        Returns:
            The removed SandboxState, or None if not found.
        """
        return self._containers.pop(container_id, None)

    async def fill_pool(self) -> int:
        """Ensure the warm pool has enough containers.

        Creates containers up to the target pool size, respecting the
        max_instances limit.

        Returns:
            Number of containers created.
        """
        async with self._lock:
            warm = self.warm_count
            total = self.total_count
            needed = min(
                self._settings.pool_size - warm,
                self._settings.max_instances - total,
            )

        created = 0
        for _ in range(max(0, needed)):
            try:
                await self.create_container()
                created += 1
            except Exception as e:
                logger.warning("⚠️ Failed to create warm sandbox: %s", e)
                break

        if created > 0:
            logger.info("🏊 Pool replenished: created %d containers (warm=%d)", created, self.warm_count)
        return created

    async def create_container(
        self,
        env_vars: dict[str, str] | None = None,
    ) -> SandboxState:
        """Create a new sandbox container with security hardening.

        Args:
            env_vars: Optional environment variables to inject.

        Returns:
            SandboxState for the newly created container.

        Raises:
            docker.errors.APIError: If container creation fails.
        """
        name = f"sandbox-{uuid4().hex[:8]}"

        container: Container = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: self._docker.containers.run(
                image=self._settings.image,
                name=name,
                detach=True,
                network=self._settings.network,
                environment=env_vars or {},
                mem_limit=self._settings.memory_limit,
                nano_cpus=int(self._settings.cpu_limit * 1e9),
                pids_limit=self._settings.pids_limit,
                security_opt=["no-new-privileges:true"],
                cap_drop=["ALL"],
                cap_add=["NET_RAW"],
                read_only=True,
                tmpfs={"/tmp": f"size={self._settings.tmpfs_size}"},
                labels={
                    "echomind.service": "sandbox",
                    "echomind.managed": "true",
                },
            ),
        )

        state = SandboxState(
            container_id=container.id,
            container_name=name,
            status=SandboxStatus.WARM,
        )
        self._containers[container.id] = state
        logger.info("🔨 Created sandbox container %s (%s)", name, container.short_id)
        return state

    async def destroy_container(self, container_id: str) -> None:
        """Stop and remove a sandbox container.

        Handles NotFound gracefully (container may already be gone).

        Args:
            container_id: Docker container ID to destroy.
        """
        state = self._containers.pop(container_id, None)
        if not state:
            return

        try:
            container = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._docker.containers.get(container_id),
            )
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: container.stop(timeout=5),
            )
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: container.remove(force=True),
            )
        except docker.errors.NotFound:
            pass  # Container already removed
        except Exception as e:
            logger.warning("⚠️ Failed to destroy sandbox %s: %s", state.container_name, e)

        logger.info("💀 Destroyed sandbox %s", state.container_name)

    async def claim_warm_container(self) -> SandboxState | None:
        """Claim the oldest warm container from the pool.

        Returns:
            SandboxState of the claimed container, or None if pool is empty.
        """
        async with self._lock:
            warm = [
                s for s in self._containers.values()
                if s.status == SandboxStatus.WARM
            ]
            if not warm:
                return None
            # Claim the oldest warm container
            warm.sort(key=lambda s: s.created_at)
            claimed = warm[0]
            claimed.status = SandboxStatus.ASSIGNED
            claimed.assigned_at = datetime.now(timezone.utc)
            return claimed

    async def recycle_stale_containers(self) -> int:
        """Destroy warm containers that have exceeded the idle timeout.

        Returns:
            Number of containers recycled.
        """
        now = datetime.now(timezone.utc)
        # Use 2x idle timeout for warm containers to avoid excessive churn
        max_age = self._settings.idle_timeout * 2
        stale = [
            cid for cid, state in self._containers.items()
            if state.status == SandboxStatus.WARM
            and (now - state.created_at).total_seconds() > max_age
        ]
        for container_id in stale:
            await self.destroy_container(container_id)

        if stale:
            logger.info("♻️ Recycled %d stale warm containers", len(stale))
        return len(stale)

    async def destroy_all(self) -> None:
        """Destroy all managed containers. Called on shutdown."""
        container_ids = list(self._containers.keys())
        for container_id in container_ids:
            await self.destroy_container(container_id)
        logger.info("🛑 All sandbox containers destroyed")
```

---

#### `src/api/sandbox/manager.py`

**Purpose**: Top-level orchestrator. Manages lifecycle, assignment, health monitoring, reconciliation loop.

**Dependencies**: `docker`, `nats`, `asyncio`, `api.sandbox.pool`, `api.sandbox.config`, `api.sandbox.models`, `api.sandbox.exceptions`

```python
"""Sandbox Manager — orchestrates ephemeral agent container lifecycle.

Runs inside the API service. Uses Docker SDK to create/destroy containers
and NATS JetStream for API-to-sandbox communication.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone

import docker
import nats
from nats.aio.client import Client as NatsClient

from api.sandbox.config import SandboxSettings
from api.sandbox.exceptions import (
    SandboxAssignmentError,
    SandboxNotFoundError,
    SandboxPoolExhaustedError,
    SandboxUnavailableError,
)
from api.sandbox.models import (
    SandboxAssignment,
    SandboxPoolStatus,
    SandboxState,
    SandboxStatus,
)
from api.sandbox.pool import SandboxPool

logger = logging.getLogger(__name__)


class SandboxManager:
    """Manages the complete sandbox container lifecycle.

    Responsibilities:
    - Start/stop the warm pool
    - Assign containers to user sessions
    - Monitor container health via heartbeats
    - Enforce session and idle timeouts
    - Replenish the pool after assignments
    - Publish lifecycle events to NATS audit stream

    Args:
        settings: Sandbox configuration settings.
    """

    def __init__(self, settings: SandboxSettings | None = None) -> None:
        self._settings = settings or SandboxSettings()
        self._docker: docker.DockerClient | None = None
        self._nats: NatsClient | None = None
        self._pool: SandboxPool | None = None
        self._session_map: dict[str, str] = {}  # session_id -> container_id
        self._reconcile_task: asyncio.Task[None] | None = None
        self._docker_connected = False
        self._nats_connected = False
        self._retry_tasks: list[asyncio.Task[None]] = []

    @property
    def is_ready(self) -> bool:
        """Whether the sandbox subsystem is fully operational."""
        return self._docker_connected and self._nats_connected

    async def start(self) -> None:
        """Initialize Docker client, NATS connection, and fill the warm pool.

        Follows the EchoMind resilience pattern: connection failures are caught
        and retried in the background. The service does not crash on failure.
        """
        logger.info("🏗️ Starting sandbox manager (pool_size=%d, max=%d)",
                     self._settings.pool_size, self._settings.max_instances)

        # Docker SDK connection
        try:
            self._docker = docker.from_env()
            self._docker.ping()
            self._docker_connected = True
            logger.info("🐳 Docker SDK connected")
        except Exception as e:
            logger.warning("⚠️ Docker connection failed: %s", e)
            logger.info("🔄 Will retry Docker connection in background...")
            self._retry_tasks.append(asyncio.create_task(self._retry_docker_connection()))

        # NATS connection
        try:
            self._nats = await nats.connect(
                self._settings.nats_url,
                connect_timeout=10,
                max_reconnect_attempts=3,
            )
            self._nats_connected = True
            logger.info("📡 NATS connected for sandbox communication")
            await self._ensure_jetstream_streams()
        except Exception as e:
            logger.warning("⚠️ NATS connection failed: %s", e)
            logger.info("🔄 Will retry NATS connection in background...")
            self._retry_tasks.append(asyncio.create_task(self._retry_nats_connection()))

        # Initialize pool if Docker is ready
        if self._docker_connected:
            self._pool = SandboxPool(self._settings, self._docker)
            await self._pool.fill_pool()

        # Start reconciliation loop
        self._reconcile_task = asyncio.create_task(self._reconciliation_loop())

    async def stop(self) -> None:
        """Gracefully stop the sandbox manager.

        Cancels the reconciliation loop, destroys all containers, and
        closes NATS connection.
        """
        # Cancel background tasks
        if self._reconcile_task:
            self._reconcile_task.cancel()
        for task in self._retry_tasks:
            task.cancel()

        # Destroy all containers
        if self._pool:
            await self._pool.destroy_all()

        # Close NATS
        if self._nats and self._nats.is_connected:
            await self._nats.drain()
            await self._nats.close()

        logger.info("🛑 Sandbox manager stopped")

    async def assign(
        self,
        session_id: str,
        user_id: int,
        env_vars: dict[str, str],
    ) -> SandboxAssignment:
        """Assign a sandbox container to a session.

        Claims a warm container from the pool (or creates on-demand).
        Injects session-specific environment via NATS init message.
        Triggers pool replenishment in the background.

        Args:
            session_id: Unique session identifier (used in NATS subjects).
            user_id: ID of the user who owns this session.
            env_vars: Session-specific environment variables.

        Returns:
            SandboxAssignment with container info and NATS subjects.

        Raises:
            SandboxUnavailableError: If Docker/NATS not connected.
            SandboxPoolExhaustedError: If max instances reached.
            SandboxAssignmentError: If assignment fails for other reasons.
        """
        if not self.is_ready or not self._pool:
            raise SandboxUnavailableError()

        # Check for existing assignment
        if session_id in self._session_map:
            container_id = self._session_map[session_id]
            state = self._pool.get_state(container_id)
            if state and state.status in (SandboxStatus.ASSIGNED, SandboxStatus.ACTIVE):
                return self._build_assignment(state, session_id)

        # Claim a warm container or create on-demand
        state = await self._pool.claim_warm_container()
        if not state:
            if self._pool.total_count >= self._settings.max_instances:
                raise SandboxPoolExhaustedError()
            try:
                state = await self._pool.create_container(env_vars)
                state.status = SandboxStatus.ASSIGNED
                state.assigned_at = datetime.now(timezone.utc)
            except Exception as e:
                raise SandboxAssignmentError(str(e)) from e

        # Update state with session info
        state.session_id = session_id
        state.user_id = user_id
        self._session_map[session_id] = state.container_id

        # Send init message via NATS with session-specific config
        if self._nats and self._nats.is_connected:
            init_msg = {
                "type": "init",
                "session_id": session_id,
                "user_id": user_id,
                "env": env_vars,
            }
            await self._nats.publish(
                f"sandbox.{session_id}.control",
                json.dumps(init_msg).encode(),
            )

        # Replenish pool in background
        asyncio.create_task(self._pool.fill_pool())

        # Publish audit event
        await self._publish_audit_event(session_id, "assigned", {
            "container_id": state.container_id,
            "container_name": state.container_name,
            "user_id": user_id,
        })

        logger.info(
            "📦 Assigned sandbox %s to session %s (user %d)",
            state.container_name, session_id, user_id,
        )
        return self._build_assignment(state, session_id)

    async def release(self, session_id: str) -> None:
        """Release and destroy a sandbox when a session ends.

        Transitions to DRAINING, publishes shutdown command, waits for
        the drain timeout, then destroys the container.

        Args:
            session_id: Session to release.

        Raises:
            SandboxNotFoundError: If no sandbox exists for this session.
        """
        container_id = self._session_map.pop(session_id, None)
        if not container_id or not self._pool:
            raise SandboxNotFoundError(session_id)

        state = self._pool.get_state(container_id)
        if state:
            state.status = SandboxStatus.DRAINING

        # Send shutdown command via NATS
        if self._nats and self._nats.is_connected:
            await self._nats.publish(
                f"sandbox.{session_id}.control",
                json.dumps({"type": "shutdown"}).encode(),
            )

        # Wait for drain, then destroy
        await asyncio.sleep(self._settings.drain_timeout)
        await self._pool.destroy_container(container_id)

        # Replenish pool
        asyncio.create_task(self._pool.fill_pool())

        await self._publish_audit_event(session_id, "destroyed", {
            "container_id": container_id,
        })
        logger.info("🗑️ Released sandbox for session %s", session_id)

    async def get_for_session(self, session_id: str) -> SandboxState | None:
        """Look up a sandbox by session ID.

        Args:
            session_id: Session to look up.

        Returns:
            SandboxState if found and pool is initialized, None otherwise.
        """
        container_id = self._session_map.get(session_id)
        if container_id and self._pool:
            return self._pool.get_state(container_id)
        return None

    async def mark_active(self, session_id: str) -> None:
        """Mark a sandbox as active (healthcheck passed).

        Args:
            session_id: Session whose sandbox became active.
        """
        container_id = self._session_map.get(session_id)
        if container_id and self._pool:
            state = self._pool.get_state(container_id)
            if state and state.status == SandboxStatus.ASSIGNED:
                state.status = SandboxStatus.ACTIVE
                state.activated_at = datetime.now(timezone.utc)
                logger.info("✅ Sandbox %s is now active (session %s)",
                            state.container_name, session_id)

    async def record_heartbeat(self, session_id: str) -> None:
        """Record a heartbeat from a sandbox container.

        Args:
            session_id: Session that sent the heartbeat.
        """
        container_id = self._session_map.get(session_id)
        if container_id and self._pool:
            state = self._pool.get_state(container_id)
            if state:
                state.last_heartbeat_at = datetime.now(timezone.utc)

    def get_pool_status(self) -> SandboxPoolStatus:
        """Get current pool statistics.

        Returns:
            SandboxPoolStatus with counts by state.
        """
        if not self._pool:
            return SandboxPoolStatus(
                warm_count=0, assigned_count=0, active_count=0,
                draining_count=0, total_count=0,
                max_instances=self._settings.max_instances,
                pool_target=self._settings.pool_size,
            )

        states = self._pool.get_all_states()
        return SandboxPoolStatus(
            warm_count=sum(1 for s in states.values() if s.status == SandboxStatus.WARM),
            assigned_count=sum(1 for s in states.values() if s.status == SandboxStatus.ASSIGNED),
            active_count=sum(1 for s in states.values() if s.status == SandboxStatus.ACTIVE),
            draining_count=sum(1 for s in states.values() if s.status == SandboxStatus.DRAINING),
            total_count=len(states),
            max_instances=self._settings.max_instances,
            pool_target=self._settings.pool_size,
        )

    # -- Internal methods --

    def _build_assignment(self, state: SandboxState, session_id: str) -> SandboxAssignment:
        """Build a SandboxAssignment response from container state.

        Args:
            state: Container state.
            session_id: Session ID for NATS subject generation.

        Returns:
            SandboxAssignment with NATS subjects.
        """
        return SandboxAssignment(
            container_id=state.container_id,
            container_name=state.container_name,
            session_id=session_id,
            nats_subject_in=f"sandbox.{session_id}.input",
            nats_subject_out=f"sandbox.{session_id}.output",
            nats_subject_stream=f"sandbox.{session_id}.stream",
            nats_subject_control=f"sandbox.{session_id}.control",
        )

    async def _ensure_jetstream_streams(self) -> None:
        """Create JetStream streams for sandbox communication if they do not exist."""
        if not self._nats:
            return
        js = self._nats.jetstream()
        try:
            await js.add_stream(
                name="sandbox-stream",
                subjects=[
                    "sandbox.*.input",
                    "sandbox.*.output",
                    "sandbox.*.stream",
                    "sandbox.*.control",
                    "sandbox.*.health",
                ],
                retention="limits",
                max_msgs_per_subject=10000,
                max_age=3600 * 1_000_000_000,  # 1 hour in nanoseconds
                storage="memory",
                discard="old",
            )
            logger.info("📦 JetStream sandbox-stream ensured")
        except Exception as e:
            logger.warning("⚠️ Failed to create sandbox-stream: %s", e)

        try:
            await js.add_stream(
                name="sandbox-audit",
                subjects=["sandbox.audit.>"],
                retention="limits",
                max_age=7 * 24 * 3600 * 1_000_000_000,  # 7 days
                storage="file",
                discard="old",
            )
            logger.info("📦 JetStream sandbox-audit stream ensured")
        except Exception as e:
            logger.warning("⚠️ Failed to create sandbox-audit stream: %s", e)

    async def _publish_audit_event(
        self,
        session_id: str,
        event_type: str,
        data: dict,
    ) -> None:
        """Publish a lifecycle event to the audit stream.

        Args:
            session_id: Session this event belongs to.
            event_type: Event type (assigned, activated, destroyed, etc.).
            data: Event payload.
        """
        if not self._nats or not self._nats.is_connected:
            return
        try:
            event = {
                "session_id": session_id,
                "event_type": event_type,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "data": data,
            }
            await self._nats.publish(
                f"sandbox.audit.{event_type}",
                json.dumps(event).encode(),
            )
        except Exception as e:
            logger.warning("⚠️ Failed to publish audit event: %s", e)

    async def _reconciliation_loop(self) -> None:
        """Periodic loop to enforce timeouts and maintain pool health.

        Runs every reconcile_interval seconds. Handles:
        - Session timeout enforcement (destroy over-age active containers)
        - Heartbeat timeout detection (mark unresponsive containers)
        - Stale warm container recycling
        - Pool replenishment
        """
        while True:
            try:
                await asyncio.sleep(self._settings.reconcile_interval)

                if not self.is_ready or not self._pool:
                    continue

                now = datetime.now(timezone.utc)
                states = self._pool.get_all_states()

                for container_id, state in states.items():
                    # Enforce session timeout on active containers
                    if (
                        state.status == SandboxStatus.ACTIVE
                        and state.assigned_at
                        and (now - state.assigned_at).total_seconds()
                        > self._settings.session_timeout
                    ):
                        logger.warning(
                            "⏰ Session timeout for sandbox %s (session %s)",
                            state.container_name, state.session_id,
                        )
                        if state.session_id:
                            self._session_map.pop(state.session_id, None)
                            await self._publish_audit_event(
                                state.session_id, "timeout",
                                {"reason": "session_timeout"},
                            )
                        await self._pool.destroy_container(container_id)

                    # Detect missed heartbeats
                    if (
                        state.status == SandboxStatus.ACTIVE
                        and state.last_heartbeat_at
                        and (now - state.last_heartbeat_at).total_seconds()
                        > self._settings.heartbeat_interval
                        * self._settings.heartbeat_missed_threshold
                    ):
                        logger.warning(
                            "💔 Heartbeat timeout for sandbox %s (session %s)",
                            state.container_name, state.session_id,
                        )
                        if state.session_id:
                            self._session_map.pop(state.session_id, None)
                        await self._pool.destroy_container(container_id)

                    # Enforce assignment timeout (container not yet active)
                    if (
                        state.status == SandboxStatus.ASSIGNED
                        and state.assigned_at
                        and (now - state.assigned_at).total_seconds()
                        > self._settings.assignment_timeout
                    ):
                        logger.warning(
                            "⏰ Assignment timeout for sandbox %s (session %s)",
                            state.container_name, state.session_id,
                        )
                        if state.session_id:
                            self._session_map.pop(state.session_id, None)
                        await self._pool.destroy_container(container_id)

                # Recycle stale warm containers and replenish
                await self._pool.recycle_stale_containers()
                await self._pool.fill_pool()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception("❌ Reconciliation loop error: %s", e)

    async def _retry_docker_connection(self) -> None:
        """Background retry loop for Docker SDK connection."""
        while not self._docker_connected:
            await asyncio.sleep(30)
            try:
                self._docker = docker.from_env()
                self._docker.ping()
                self._docker_connected = True
                logger.info("🐳 Docker SDK reconnected")
                if not self._pool:
                    self._pool = SandboxPool(self._settings, self._docker)
                    await self._pool.fill_pool()
            except Exception as e:
                logger.warning("⚠️ Docker reconnection attempt failed: %s", e)

    async def _retry_nats_connection(self) -> None:
        """Background retry loop for NATS connection."""
        while not self._nats_connected:
            await asyncio.sleep(30)
            try:
                self._nats = await nats.connect(
                    self._settings.nats_url,
                    connect_timeout=10,
                    max_reconnect_attempts=3,
                )
                self._nats_connected = True
                logger.info("📡 NATS reconnected for sandbox communication")
                await self._ensure_jetstream_streams()
            except Exception as e:
                logger.warning("⚠️ NATS reconnection attempt failed: %s", e)
```

---

#### `src/api/routes/sandbox.py`

**Purpose**: REST endpoints for sandbox management (admin pool status, session release, session listing).

**Dependencies**: `fastapi`, `api.sandbox.manager`, `api.dependencies`

```python
"""REST API endpoints for sandbox management.

These endpoints allow admins to monitor the pool and users to manage
their sandbox sessions.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends

from api.sandbox.exceptions import SandboxNotFoundError
from api.sandbox.models import SandboxPoolStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sandbox", tags=["sandbox"])


# NOTE: Dependency injection for SandboxManager and auth will use
# the existing patterns from api.dependencies. Shown as placeholders:
#   - get_sandbox_manager: Provides the singleton SandboxManager
#   - AdminUser: Existing admin auth dependency
#   - TokenUser: Existing token-based auth dependency


@router.get(
    "/pool",
    response_model=SandboxPoolStatus,
    summary="Get sandbox pool status",
    description="Returns current pool statistics. Admin only.",
)
async def get_pool_status(
    # user: AdminUser,
    # manager: Annotated[SandboxManager, Depends(get_sandbox_manager)],
) -> SandboxPoolStatus:
    """Get current sandbox pool status (admin only).

    Returns:
        Pool status with counts by container state.
    """
    # return manager.get_pool_status()
    ...


@router.post(
    "/sessions/{session_id}/release",
    summary="Release a sandbox session",
    description="Stops and destroys the sandbox for this session.",
)
async def release_sandbox(
    session_id: str,
    # user: TokenUser,
    # manager: Annotated[SandboxManager, Depends(get_sandbox_manager)],
) -> dict[str, str]:
    """Release a sandbox session (owner or admin).

    Args:
        session_id: Session whose sandbox to release.

    Returns:
        Confirmation message.

    Raises:
        SandboxNotFoundError: If no sandbox exists for this session.
    """
    # TODO: Verify user owns this session or is admin
    # await manager.release(session_id)
    # return {"status": "released", "session_id": session_id}
    ...


@router.get(
    "/sessions",
    summary="List user's active sandbox sessions",
    description="Returns all active sandbox sessions for the authenticated user.",
)
async def list_sandbox_sessions(
    # user: TokenUser,
    # manager: Annotated[SandboxManager, Depends(get_sandbox_manager)],
) -> list[dict]:
    """List user's active sandbox sessions.

    Returns:
        List of active sandbox sessions with container info.
    """
    # pool_states = manager._pool.get_all_states() if manager._pool else {}
    # return [
    #     {
    #         "session_id": state.session_id,
    #         "container_name": state.container_name,
    #         "status": state.status,
    #         "assigned_at": state.assigned_at.isoformat() if state.assigned_at else None,
    #     }
    #     for state in pool_states.values()
    #     if state.user_id == user.id and state.status != SandboxStatus.DESTROYED
    # ]
    ...
```

---

#### `src/echomind_lib/db/models/sandbox_session.py`

**Purpose**: SQLAlchemy ORM model for the `sandbox_sessions` table.

```python
"""SandboxSession ORM model."""

from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import Uuid

from echomind_lib.db.models.base import (
    ARRAY,
    JSONB,
    TIMESTAMP,
    Base,
    ForeignKey,
    Integer,
    Mapped,
    String,
    Text,
    datetime,
    mapped_column,
    relationship,
    utcnow,
)

if TYPE_CHECKING:
    from echomind_lib.db.models.chat_session import ChatSession
    from echomind_lib.db.models.sandbox_event import SandboxEvent
    from echomind_lib.db.models.user import User


class SandboxSession(Base):
    """Tracks sandbox container assignments and lifecycle.

    Maps a chat session to an ephemeral Docker container, recording
    its state transitions, resource usage, and configuration snapshot.
    """

    __tablename__ = "sandbox_sessions"

    id: Mapped[str] = mapped_column(
        Uuid, primary_key=True, default=uuid4,
    )
    session_id: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True,
        comment="Routing key (matches NATS subject)",
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False,
    )
    chat_session_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("chat_sessions.id"),
    )

    # Container info
    container_id: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True,
        comment="Docker container ID",
    )
    container_name: Mapped[str] = mapped_column(
        String(255), nullable=False,
    )
    container_ip: Mapped[str | None] = mapped_column(String(45))

    # State machine
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="assigned",
        comment="assigned|active|draining|destroyed",
    )
    assigned_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, nullable=False, default=utcnow,
    )
    activated_at: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    drained_at: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    destroyed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP)

    # Agent configuration snapshot
    agent_config: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict,
        comment="Agent instructions, model, tools at assignment time",
    )
    permissions: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=list,
    )

    # Metrics
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    tool_calls_count: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    mcp_calls_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)

    # Observability
    langfuse_trace_id: Mapped[str | None] = mapped_column(String(255))
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(TIMESTAMP)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, nullable=False, default=utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, nullable=False, default=utcnow, onupdate=utcnow,
    )

    # Relationships
    user: Mapped["User"] = relationship(foreign_keys=[user_id])
    chat_session: Mapped["ChatSession | None"] = relationship(foreign_keys=[chat_session_id])
    events: Mapped[list["SandboxEvent"]] = relationship(
        back_populates="sandbox_session", cascade="all, delete-orphan",
    )
```

---

#### `src/echomind_lib/db/models/sandbox_event.py`

**Purpose**: SQLAlchemy ORM model for the `sandbox_events` audit log table.

```python
"""SandboxEvent ORM model."""

from typing import TYPE_CHECKING

from sqlalchemy import Uuid

from echomind_lib.db.models.base import (
    JSONB,
    TIMESTAMP,
    BigInteger,
    Base,
    ForeignKey,
    Mapped,
    String,
    datetime,
    mapped_column,
    relationship,
    utcnow,
)

if TYPE_CHECKING:
    from echomind_lib.db.models.sandbox_session import SandboxSession


class SandboxEvent(Base):
    """Immutable audit log of sandbox lifecycle events.

    Records every state transition, message, tool call, MCP call,
    error, and timeout for a sandbox session.
    """

    __tablename__ = "sandbox_events"

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True,
    )
    sandbox_session_id: Mapped[str] = mapped_column(
        Uuid, ForeignKey("sandbox_sessions.id"), nullable=False, index=True,
    )
    event_type: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True,
        comment="created|assigned|activated|message|tool_call|mcp_call|error|timeout|drained|destroyed",
    )
    event_data: Mapped[dict] = mapped_column(
        JSONB, default=dict,
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, nullable=False, default=utcnow,
    )

    # Relationships
    sandbox_session: Mapped["SandboxSession"] = relationship(
        back_populates="events",
    )
```

---

### 16.3 Sandbox Dockerfile

Complete Dockerfile for the agent sandbox container.

```dockerfile
# src/sandbox/Dockerfile
# Ephemeral agent sandbox container for EchoMind
# Multi-stage build for minimal attack surface

# ===============================================
# Stage 1: Builder — install Python dependencies
# ===============================================
FROM python:3.12.12-slim-bookworm AS builder

WORKDIR /build

COPY sandbox/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ===============================================
# Stage 2: Runtime — minimal production image
# ===============================================
FROM python:3.12.12-slim-bookworm

WORKDIR /app

# Minimal runtime dependencies: curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY sandbox /app/sandbox
COPY echomind_lib /app/echomind_lib

ENV PYTHONPATH="/app"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Security: non-root user (CRITICAL)
RUN useradd -m -u 1000 -s /bin/false sandboxuser && \
    chown -R sandboxuser:sandboxuser /app

USER sandboxuser

# Healthcheck — lightweight HTTP ping
HEALTHCHECK --interval=10s --timeout=5s --start-period=3s --retries=2 \
    CMD curl -f http://localhost:8080/healthz || exit 1

EXPOSE 8080

CMD ["python", "-m", "sandbox.main"]
```

**Image size budget**:

| Layer | Estimated Size |
|-------|---------------|
| `python:3.12-slim` base | ~120 MB |
| pip packages (SK + nats-py + httpx + pydantic) | ~200 MB |
| `echomind_lib` + `sandbox/` code | ~5 MB |
| **Total** | **~325 MB** |

---

### 16.4 Docker Compose Overlay

```yaml
# deployment/docker-cluster/docker-compose-sandbox.yml
# Additive overlay for sandbox container support.
# Activated via ENABLE_SANDBOX=true in .env

networks:
  sandbox:
    driver: bridge
    # NOT internal: sandboxes need outbound internet access

services:
  # ===============================================
  # API gains Docker socket + sandbox network
  # ===============================================
  api:
    networks:
      - frontend
      - backend
      - sandbox
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro  # Docker SDK
    environment:
      - SANDBOX_ENABLED=true
      - SANDBOX_POOL_SIZE=${SANDBOX_POOL_SIZE:-3}
      - SANDBOX_MAX_INSTANCES=${SANDBOX_MAX_INSTANCES:-15}
      - SANDBOX_IMAGE=gsantopaolo/echomind-sandbox:${SANDBOX_VERSION:-latest}
      - SANDBOX_NETWORK=sandbox
      - SANDBOX_NATS_URL=nats://nats:4222
      - SANDBOX_CPU_LIMIT=${SANDBOX_CPU_LIMIT:-2.0}
      - SANDBOX_MEMORY_LIMIT=${SANDBOX_MEMORY_LIMIT:-2g}
      - SANDBOX_SESSION_TIMEOUT=${SANDBOX_SESSION_TIMEOUT:-3600}

  # ===============================================
  # NATS gains sandbox network access
  # ===============================================
  nats:
    networks:
      - backend
      - sandbox

  # ===============================================
  # MCP Gateway — shared tool/skill gateway
  # (Listed here for network membership; full service
  #  definition is in docker-compose-mcp.yml or main)
  # ===============================================
  mcp-server:
    networks:
      - backend
      - sandbox
```

**`cluster.sh` changes**:

```bash
# Read ENABLE_SANDBOX from .env
SANDBOX_FILES=""
_sandbox_enabled=false
if [ -f "$SCRIPT_DIR/.env" ] && grep -q "^[[:space:]]*ENABLE_SANDBOX[[:space:]]*=[[:space:]]*true" "$SCRIPT_DIR/.env" 2>/dev/null; then
    _sandbox_enabled=true
fi
if [ "$_sandbox_enabled" = true ]; then
    SANDBOX_FILES="-f docker-compose-sandbox.yml"
fi

# Add to all docker compose commands:
# docker compose -f docker-compose.yml $SANDBOX_FILES ...
```

---

### 16.5 NATS Subject Design

Detailed subject naming for all sandbox communication channels.

#### Per-Session Subjects (ephemeral, exist only while sandbox is active)

| Subject | Direction | Payload | Purpose |
|---------|-----------|---------|---------|
| `sandbox.{session_id}.input` | API -> Sandbox | `{"type": "query", "query": "...", "context": {...}}` | User messages, follow-ups |
| `sandbox.{session_id}.output` | Sandbox -> API | `{"type": "response", "message_id": "...", "content": "..."}` | Final complete responses |
| `sandbox.{session_id}.stream` | Sandbox -> API | `{"type": "token"\|"tool_call.start"\|"tool_call.result"\|"complete", "data": "..."}` | Streaming tokens, tool call events |
| `sandbox.{session_id}.control` | API -> Sandbox | `{"type": "init"\|"cancel"\|"shutdown"\|"config_update", ...}` | Lifecycle commands |
| `sandbox.{session_id}.health` | Sandbox -> API | `{"status": "ready"\|"busy"\|"error", "uptime": 123}` | Heartbeat every 15s |

#### Management Subjects (for SandboxManager internal use)

| Subject | Purpose |
|---------|---------|
| `sandbox.mgmt.assign` | Request sandbox assignment (internal RPC) |
| `sandbox.mgmt.release` | Release sandbox (internal RPC) |
| `sandbox.mgmt.status` | Pool status query (internal RPC) |

#### Audit Stream (persistent, 7-day retention)

| Subject | Payload | Purpose |
|---------|---------|---------|
| `sandbox.audit.assigned` | `{"session_id", "user_id", "container_id"}` | Container assigned to session |
| `sandbox.audit.activated` | `{"session_id", "startup_time_ms"}` | Container healthcheck passed |
| `sandbox.audit.message` | `{"session_id", "direction", "msg_type"}` | Message sent/received |
| `sandbox.audit.tool_call` | `{"session_id", "tool_name", "duration_ms"}` | Tool invocation |
| `sandbox.audit.mcp_call` | `{"session_id", "mcp_tool", "duration_ms"}` | MCP server call |
| `sandbox.audit.error` | `{"session_id", "error_type", "message"}` | Error occurred |
| `sandbox.audit.timeout` | `{"session_id", "timeout_type"}` | Timeout triggered |
| `sandbox.audit.destroyed` | `{"session_id", "reason", "lifetime_seconds"}` | Container destroyed |

#### JetStream Stream Configuration

```python
# sandbox-stream: ephemeral communication (memory storage, 1h retention)
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
    "max_age": 3600 * 1_000_000_000,  # 1 hour in nanoseconds
    "storage": "memory",
    "discard": "old",
}

# sandbox-audit: persistent audit trail (file storage, 7d retention)
SANDBOX_AUDIT_STREAM_CONFIG = {
    "name": "sandbox-audit",
    "subjects": ["sandbox.audit.>"],
    "retention": "limits",
    "max_age": 7 * 24 * 3600 * 1_000_000_000,  # 7 days
    "storage": "file",
    "discard": "old",
}
```

---

### 16.6 Database Schema — Complete Alembic Migration

```python
"""Add sandbox_sessions and sandbox_events tables.

Revision ID: 20260217_010000
Revises: 20260210_033000
Create Date: 2026-02-17 01:00:00.000000

Creates tables for tracking ephemeral sandbox container lifecycle
and an immutable audit log of all sandbox events.
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "20260217_010000"
down_revision = "20260210_033000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create sandbox_sessions and sandbox_events tables."""
    # ---- sandbox_sessions ----
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS sandbox_sessions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            session_id VARCHAR(255) UNIQUE NOT NULL,
            user_id INT NOT NULL REFERENCES users(id),
            chat_session_id INT REFERENCES chat_sessions(id),

            -- Container info
            container_id VARCHAR(64) NOT NULL,
            container_name VARCHAR(255) NOT NULL,
            container_ip VARCHAR(45),

            -- State machine
            status VARCHAR(20) NOT NULL DEFAULT 'assigned',
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

            -- Timestamps
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    # Indexes
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_sandbox_sessions_user
        ON sandbox_sessions (user_id, created_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_sandbox_sessions_status
        ON sandbox_sessions (status) WHERE status != 'destroyed'
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_sandbox_sessions_container
        ON sandbox_sessions (container_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_sandbox_sessions_session
        ON sandbox_sessions (session_id)
        """
    )

    # ---- sandbox_events ----
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS sandbox_events (
            id BIGSERIAL PRIMARY KEY,
            sandbox_session_id UUID NOT NULL REFERENCES sandbox_sessions(id),
            event_type VARCHAR(50) NOT NULL,
            event_data JSONB DEFAULT '{}',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_sandbox_events_session
        ON sandbox_events (sandbox_session_id, created_at)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_sandbox_events_type
        ON sandbox_events (event_type, created_at DESC)
        """
    )

    # ---- Monitoring view ----
    op.execute(
        """
        CREATE OR REPLACE VIEW sandbox_pool_status AS
        SELECT
            status,
            COUNT(*) as count,
            AVG(EXTRACT(EPOCH FROM (NOW() - assigned_at))) as avg_age_seconds
        FROM sandbox_sessions
        WHERE status != 'destroyed'
        GROUP BY status
        """
    )


def downgrade() -> None:
    """Drop sandbox tables and view."""
    op.execute("DROP VIEW IF EXISTS sandbox_pool_status")
    op.execute("DROP TABLE IF EXISTS sandbox_events")
    op.execute("DROP TABLE IF EXISTS sandbox_sessions")
```

---

### 16.7 Container Lifecycle State Machine

Detailed state transitions with timeout handling and error recovery.

```
                 +----------+
                 |          |
        create   |   WARM   |  pre-created, idle, waiting in pool
        -------->|          |  Timeout: idle_timeout * 2 -> recycled
                 +----+-----+  Error: creation fails -> log, skip
                      |
                      | assign(session_id, user_id)
                      | Send NATS: sandbox.{sid}.control {"type": "init"}
                      v
                 +----------+
                 |          |
                 | ASSIGNED |  env vars sent via NATS, agent booting
                 |          |  Timeout: assignment_timeout (30s) -> DESTROYED
                 +----+-----+  Error: container crashes -> DESTROYED, replenish
                      |
                      | sandbox publishes: {"status": "ready"} on .health
                      | mark_active(session_id) called
                      v
                 +----------+
                 |          |
                 |  ACTIVE  |  processing messages via NATS pub/sub
                 |          |  Heartbeat: every 15s on .health subject
                 +----+-----+  Timeout: session_timeout (3600s) -> DRAINING
                      |        Heartbeat miss: 3x -> DESTROYED
                      |
                      | session ends (user disconnect, explicit release)
                      | OR timeout triggered
                      v
                 +----------+
                 |          |
                 | DRAINING |  finishing current turn, flushing logs
                 |          |  NATS: send {"type": "shutdown"} on .control
                 +----+-----+  Timeout: drain_timeout (30s) -> force kill
                      |
                      | agent acknowledges OR grace period expires
                      v
                 +----------+
                 |          |
                 | DESTROYED|  container.stop() + container.remove(force=True)
                 |          |  DB record updated (destroyed_at timestamp)
                 +----------+  Pool: create replacement warm container
```

**Error recovery at each state**:

| State | Error Scenario | Recovery |
|-------|---------------|----------|
| WARM | Container crashes silently | Reconciliation loop detects missing container, removes state, replenishes pool |
| WARM | Docker daemon unreachable | Resilience pattern: retry every 30s in background, mark `_docker_connected=False` |
| ASSIGNED | Container fails healthcheck | Assignment timeout (30s) destroys container, returns error to user |
| ASSIGNED | NATS publish fails | Retry once, then destroy container and return `SandboxAssignmentError` |
| ACTIVE | Container OOM killed | Docker removes container (auto_remove), reconciliation loop cleans up state |
| ACTIVE | NATS disconnects | Container has its own reconnect logic; manager detects via missed heartbeats |
| DRAINING | Container ignores shutdown | Force kill after drain_timeout expires |
| DESTROYED | `container.remove()` fails | Catch `docker.errors.NotFound` (already gone), log warning for other errors |

---

### 16.8 Network Topology

Which Docker networks the sandbox joins and the resulting access matrix.

```
+------------------------------------------------------------------+
|                        Docker Host                                |
|                                                                   |
|  +---------------------------+  +-----------------------------+   |
|  |     backend network       |  |     frontend network        |   |
|  |     (172.20.0.0/16)       |  |     (172.21.0.0/16)        |   |
|  |                           |  |                             |   |
|  | [postgres :5432]          |  | [traefik :80/:443]         |   |
|  | [qdrant :6333]            |  | [webui :8080]              |   |
|  | [minio :9000]             |  |                             |   |
|  | [redis :6379]             |  | [api :8000]                |   |
|  | [embedder :50051]         |  |                             |   |
|  | [nats :4222]  *           |  +-----------------------------+   |
|  | [api :8000]               |                                    |
|  | [mcp-server :8100]  *     |                                    |
|  +---------------------------+                                    |
|          * also on sandbox network                                |
|                                                                   |
|  +---------------------------+                                    |
|  |     sandbox network       |                                    |
|  |     (172.30.0.0/16)       |                                    |
|  |                           |                                    |
|  | [sandbox-0]  [sandbox-1]  |                                    |
|  | [sandbox-2]  ...          |                                    |
|  |                           |                                    |
|  | [nats :4222]  *           |                                    |
|  | [mcp-server :8100]  *     |                                    |
|  +---------------------------+                                    |
|          * bridged from backend                                   |
+------------------------------------------------------------------+
```

**Access matrix from sandbox containers**:

| Target | Port | Allowed | Mechanism |
|--------|------|---------|-----------|
| NATS | 4222 | YES | NATS on sandbox network |
| MCP Gateway | 8100 | YES | MCP server on sandbox network |
| Internet | 80/443 | YES | sandbox network not `internal` |
| PostgreSQL | 5432 | NO | Not on sandbox network |
| Qdrant | 6333 | NO | Not on sandbox network |
| MinIO | 9000 | NO | Not on sandbox network |
| Redis | 6379 | NO | Not on sandbox network |
| Embedder | 50051 | NO | Not on sandbox network |
| API | 8000 | NO | API on sandbox net but sandbox communicates via NATS only |

**Future hardening** (Phase 8): iptables rules to explicitly block `172.20.0.0/16` from sandbox network even if misconfiguration bridges them.

---

### 16.9 Test Plan

#### Unit Tests — SandboxManager (mocked Docker SDK + NATS)

| Test Case | File | Description |
|-----------|------|-------------|
| `test_start_fills_pool` | `tests/unit/api/sandbox/test_manager.py` | Manager.start() creates `pool_size` warm containers |
| `test_start_docker_failure_retries` | same | Docker connection fails -> background retry, no crash |
| `test_start_nats_failure_retries` | same | NATS connection fails -> background retry, no crash |
| `test_assign_from_warm_pool` | same | Claims warm container, sets status=assigned |
| `test_assign_creates_on_demand` | same | Empty pool creates container on-demand |
| `test_assign_pool_exhausted` | same | Max instances reached -> SandboxPoolExhaustedError |
| `test_assign_existing_session` | same | Re-assign returns existing sandbox |
| `test_assign_publishes_nats_init` | same | Init message published to `.control` subject |
| `test_release_drains_and_destroys` | same | Status transitions through DRAINING, container destroyed |
| `test_release_unknown_session` | same | SandboxNotFoundError raised |
| `test_release_replenishes_pool` | same | Pool refilled after release |
| `test_mark_active` | same | Status changes ASSIGNED -> ACTIVE |
| `test_record_heartbeat` | same | last_heartbeat_at updated |
| `test_get_pool_status` | same | Returns correct counts by state |
| `test_reconciliation_session_timeout` | same | Active container past timeout destroyed |
| `test_reconciliation_heartbeat_timeout` | same | Missing heartbeats -> container destroyed |
| `test_reconciliation_assignment_timeout` | same | Assigned but not active -> destroyed |
| `test_stop_destroys_all` | same | All containers destroyed, NATS drained |

#### Unit Tests — SandboxPool (mocked Docker SDK)

| Test Case | File | Description |
|-----------|------|-------------|
| `test_create_container_params` | `tests/unit/api/sandbox/test_pool.py` | Docker SDK called with correct security opts |
| `test_create_container_resource_limits` | same | CPU, memory, PID limits passed correctly |
| `test_fill_pool_respects_max` | same | Never exceeds max_instances |
| `test_claim_warm_container_fifo` | same | Oldest warm container claimed first |
| `test_claim_empty_pool` | same | Returns None when no warm containers |
| `test_recycle_stale_containers` | same | Containers past 2x idle_timeout destroyed |
| `test_destroy_container_not_found` | same | NotFound handled gracefully |
| `test_destroy_all` | same | All containers stopped and removed |

#### Unit Tests — Models and Config

| Test Case | File | Description |
|-----------|------|-------------|
| `test_sandbox_settings_defaults` | `tests/unit/api/sandbox/test_config.py` | Default values correct |
| `test_sandbox_settings_from_env` | same | Env var override with SANDBOX_ prefix |
| `test_sandbox_status_transitions` | `tests/unit/api/sandbox/test_models.py` | Enum values match expected strings |
| `test_sandbox_pool_status_model` | same | Serialization/deserialization correct |

#### Unit Tests — Exceptions

| Test Case | File | Description |
|-----------|------|-------------|
| `test_pool_exhausted_503` | `tests/unit/api/sandbox/test_exceptions.py` | Status code 503 |
| `test_not_found_404` | same | Status code 404, includes session_id |
| `test_unavailable_503` | same | Status code 503 |

#### Integration Tests (optional, marked `@pytest.mark.slow`)

| Test Case | File | Description |
|-----------|------|-------------|
| `test_create_real_container` | `tests/integration/sandbox/test_docker.py` | Creates/destroys real Docker container |
| `test_warm_pool_lifecycle` | same | Full warm pool fill, claim, replenish cycle |
| `test_nats_sandbox_communication` | `tests/integration/sandbox/test_nats.py` | Publish/subscribe on sandbox subjects |
| `test_full_assignment_flow` | same | Assign -> init message -> health -> active -> release |

**Total estimated tests**: ~35 unit + 4 integration = ~39 tests

---

### 16.10 Dependencies

All Python packages with pinned versions for the sandbox subsystem.

#### API Service additions (`src/api/requirements.txt`)

```
docker==7.1.0               # Docker SDK for Python (container management)
```

#### Sandbox Container (`src/sandbox/requirements.txt`)

```
nats-py==2.9.0              # NATS JetStream client
httpx==0.28.1               # HTTP client for MCP communication
pydantic==2.10.6            # Data validation
pydantic-settings==2.7.1    # Settings from environment variables
semantic-kernel==1.21.0     # Agent framework
openai==1.61.1              # LLM client (OpenAI-compatible)
anthropic==0.45.2           # LLM client (Anthropic)
```

> **Note**: Exact versions should be aligned with `echomind_lib/pyproject.toml` as the source of truth for shared dependencies. The versions above are current as of February 2026.

---

### 16.11 Citations and Sources

| Source | Topic | Date |
|--------|-------|------|
| [Docker SDK for Python — Containers API](https://docker-py.readthedocs.io/en/stable/containers.html) | `containers.run()` parameters: `mem_limit`, `nano_cpus`, `pids_limit`, `security_opt`, `cap_drop`, `cap_add`, `read_only`, `tmpfs`, `network`, `auto_remove` | 2025 |
| [Docker SDK for Python — Networks API](https://docker-py.readthedocs.io/en/stable/networks.html) | `NetworkCollection.create()`, `network.connect()`, `network.disconnect()` | 2025 |
| [Docker Resource Constraints](https://docs.docker.com/engine/containers/resource_constraints/) | CPU, memory, PID limits for containers | 2026 |
| [Agent Sandbox Pre-Warming Pool](https://pacoxu.wordpress.com/2025/12/02/agent-sandbox-pre-warming-pool-makes-secure-containers-cold-start-lightning-fast/) | Warm pool pattern achieving sub-second startup latency via pre-warmed pods | 2025-12 |
| [Kubernetes Agent Sandbox](https://github.com/kubernetes-sigs/agent-sandbox) | SandboxWarmPool CRD for managing pre-warmed sandbox pods | 2025 |
| [Docker Blog: A New Approach for Coding Agent Safety](https://www.docker.com/blog/docker-sandboxes-a-new-approach-for-coding-agent-safety/) | Docker Sandboxes wrapping agents in containers with strict boundaries | 2025 |
| [Docker Blog: Secure AI Agents at Runtime](https://www.docker.com/blog/secure-ai-agents-runtime-security/) | Runtime security for AI agent containers | 2025 |
| [Northflank: How to Sandbox AI Agents in 2026](https://northflank.com/blog/how-to-sandbox-ai-agents) | MicroVMs, gVisor, isolation strategies for AI agent sandboxes | 2026 |
| [Docker Security Best Practices 2026](https://thelinuxcode.com/docker-security-best-practices-2026-hardening-the-host-images-and-runtime-without-slowing-teams-down/) | Seccomp, AppArmor, read-only rootfs, no-new-privileges, PID limits, user namespaces | 2026 |
| [OWASP Docker Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Docker_Security_Cheat_Sheet.html) | Defense-in-depth container security | 2025 |
| [Docker Seccomp Profiles](https://docs.docker.com/engine/security/seccomp/) | Default seccomp profile disables ~44 syscalls | 2025 |
| [Docker AppArmor Profiles](https://docs.docker.com/engine/security/apparmor/) | docker-default AppArmor profile | 2025 |
| [nats-py — Python NATS Client](https://github.com/nats-io/nats.py) | Async client for NATS with JetStream support | 2025 |
| [nats-py API Modules](https://nats-io.github.io/nats.py/modules.html) | `JetStreamContext.publish()`, `subscribe()`, `pull_subscribe()`, `Msg.ack()` | 2025 |
| [NATS JetStream Publishing](https://docs.nats.io/using-nats/developer/develop_jetstream/publish) | JetStream publish with acknowledgment | 2025 |
| [Docker + E2B Partnership](https://www.docker.com/blog/docker-e2b-building-the-future-of-trusted-ai/) | E2B cloud sandboxes for AI agents | 2025 |
| [Shipyard: Sandboxing Agentic Workflows](https://shipyard.build/blog/sandboxing-agentic-workflows/) | Ephemeral environments for agent sandbox isolation | 2025 |
| [Koyeb: Top Sandbox Platforms for AI 2026](https://www.koyeb.com/blog/top-sandbox-code-execution-platforms-for-ai-code-execution-2026) | Comparison of sandbox platforms | 2026 |
| [Custom Containerized Sandboxes for AI Agents](https://medium.com/@rafaelbenari/custom-containerized-sandboxes-for-ai-agents-dd2cd2603b3b) | Custom Docker sandbox patterns | 2025-12 |

---

### 16.12 Evaluation Scorecard

| # | Criterion | Score (1-10) | Notes |
|---|-----------|:------------:|-------|
| 1 | **Security Isolation** | 9 | Read-only rootfs, all caps dropped, non-root user, no-new-privileges, PID limit, network isolation. Only missing gVisor/microVM (future). |
| 2 | **Cold Start Latency** | 8 | Warm pool eliminates cold start for typical load (~50ms). On-demand fallback adds ~1.5s. Sub-second matches K8s Agent Sandbox benchmarks. |
| 3 | **Operational Simplicity** | 7 | Pure Docker Compose, no K8s dependency. Docker socket mount is a trade-off (needed for SDK but increases attack surface). |
| 4 | **Resilience** | 8 | Follows EchoMind resilience pattern: Docker/NATS failures retried in background, reconciliation loop self-heals state drift. |
| 5 | **Scalability** | 6 | Single-host limit of ~8 concurrent sessions on current hardware. Multi-host requires Docker Swarm or Redis for shared state (future work). |
| 6 | **Observability** | 8 | NATS audit stream, DB event log, heartbeat monitoring, Langfuse trace integration, Prometheus-ready metrics. |
| 7 | **Test Coverage** | 8 | 39 planned tests covering manager, pool, models, config, exceptions. Full mock coverage for Docker SDK and NATS. Integration tests marked slow. |

**Overall**: 7.7 / 10 — Production-viable for single-tenant deployment. Primary gaps are multi-host scaling and gVisor-level isolation (both planned for future phases).

---

## References

- [Docker Sandboxes Documentation](https://docs.docker.com/ai/sandboxes)
- [Docker Blog: A New Approach for Coding Agent Safety](https://www.docker.com/blog/docker-sandboxes-a-new-approach-for-coding-agent-safety/)
- [Docker Blog: Secure AI Agents at Runtime](https://www.docker.com/blog/secure-ai-agents-runtime-security/)
- [Docker + E2B: Building the Future of Trusted AI](https://www.docker.com/blog/docker-e2b-building-the-future-of-trusted-ai/)
- [Northflank: How to Sandbox AI Agents in 2026](https://northflank.com/blog/how-to-sandbox-ai-agents)
- [Northflank: Best Code Execution Sandbox for AI Agents](https://northflank.com/blog/best-code-execution-sandbox-for-ai-agents)
- [Docker SDK for Python — Containers](https://docker-py.readthedocs.io/en/stable/containers.html)
- [Docker SDK for Python — Networks](https://docker-py.readthedocs.io/en/stable/networks.html)
- [Docker Resource Constraints](https://docs.docker.com/engine/containers/resource_constraints/)
- [Docker Security Best Practices 2026](https://thelinuxcode.com/docker-security-best-practices-2026-hardening-the-host-images-and-runtime-without-slowing-teams-down/)
- [OWASP Docker Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Docker_Security_Cheat_Sheet.html)
- [Docker Seccomp Profiles](https://docs.docker.com/engine/security/seccomp/)
- [Docker AppArmor Profiles](https://docs.docker.com/engine/security/apparmor/)
- [NATS JetStream Documentation](https://docs.nats.io/using-nats/developer/develop_jetstream)
- [NATS Request-Reply Semantics](https://docs.nats.io/using-nats/developer/sending/request_reply)
- [nats-py GitHub (Python NATS Client)](https://github.com/nats-io/nats.py)
- [nats-py API Modules](https://nats-io.github.io/nats.py/modules.html)
- [Kubernetes Agent Sandbox](https://github.com/kubernetes-sigs/agent-sandbox)
- [Agent Sandbox Pre-Warming Pool](https://pacoxu.wordpress.com/2025/12/02/agent-sandbox-pre-warming-pool-makes-secure-containers-cold-start-lightning-fast/)
- [Custom Containerized Sandboxes for AI Agents](https://medium.com/@rafaelbenari/custom-containerized-sandboxes-for-ai-agents-dd2cd2603b3b)
- [Shipyard: Sandboxing Agentic Workflows](https://shipyard.build/blog/sandboxing-agentic-workflows/)
- [Koyeb: Top Sandbox Platforms for AI 2026](https://www.koyeb.com/blog/top-sandbox-code-execution-platforms-for-ai-code-execution-2026)
- [Azure Container Apps Dynamic Sessions](https://samcogan.com/sandboxed-environments-with-container-apps-dynamic-sessions/)
- [A Field Guide to Sandboxes for AI](https://www.luiscardoso.dev/blog/sandboxes-for-ai)
