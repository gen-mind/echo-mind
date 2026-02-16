# Agent Infrastructure Analysis

> Deep analysis of EchoMind's existing infrastructure for sandbox container integration.
> Generated: 2026-02-16

---

## 1. Complete Service Inventory

### Application Services (prefix: `echomind-`)

| Service | Type | Port(s) | Networks | Dependencies | Description |
|---------|------|---------|----------|--------------|-------------|
| **api** | FastAPI HTTP + WebSocket | 8000 | frontend, backend | postgres, qdrant, migration, minio, nats, authentik | REST API gateway, WebSocket chat |
| **webui** | SvelteKit/Nginx static | 80 | frontend | api, authentik | SPA frontend |
| **embedder** | gRPC server | 50051 (gRPC), 8080 (health) | backend | qdrant | Text-to-vector embedding |
| **orchestrator** | Background scheduler | 8080 (health) | backend | postgres, migration, nats | APScheduler-based connector sync trigger |
| **connector** | NATS consumer | - | backend | postgres, migration, minio, nats, orchestrator | Fetches data from external sources |
| **ingestor** | NATS consumer | 8080 (health) | backend | postgres, migration, minio, qdrant, nats, embedder, connector | Document chunking + embedding pipeline |
| **guardian** | NATS consumer | 8080 (health) | backend | nats, orchestrator | DLQ monitoring + alerting |
| **projector** | NATS consumer | 8080 (health) | backend | postgres, qdrant, nats | TensorBoard visualization generator |

### Data Services (prefix: `data-`)

| Service | Image | Port(s) | Networks | Description |
|---------|-------|---------|----------|-------------|
| **postgres** | postgres:16.4 | 5432 (localhost-only in host mode) | backend | Shared DB for Authentik + API |
| **qdrant** | qdrant/qdrant:latest | 6333 HTTP, 6334 gRPC (internal only in host mode) | backend | Vector database |
| **minio** | minio/minio:latest | 9000 API, 9001 Console (internal only in host mode) | frontend, backend | S3-compatible object storage |
| **redis** | redis:7-alpine | - | backend | Cache (512MB, noeviction) |

### Infrastructure Services (prefix: `infra-`)

| Service | Image | Port(s) | Networks | Description |
|---------|-------|---------|----------|-------------|
| **traefik** | traefik:v3.3 | 80, 443, 8080 (dashboard, localhost-only) | frontend, backend | Reverse proxy, TLS termination |
| **nats** | nats:alpine | 4222 client, 8222 monitoring, 6222 cluster | backend | Message bus with JetStream |
| **nui** | nats-nui | 31311 | backend, frontend | NATS management UI |
| **authentik-server** | goauthentik/server | 9000 | frontend, backend | OIDC provider |
| **authentik-worker** | goauthentik/server | - | backend | Authentik background tasks |
| **portainer** | portainer-ce | 9000 | frontend | Docker management UI (host mode only) |

### Init Jobs (prefix: `init-`)

| Service | Description |
|---------|-------------|
| **migration** | Alembic DB migrations (runs once, restart: "no") |

### Optional Stacks (profile-gated)

| Stack | Profile | Services |
|-------|---------|----------|
| **Observability** | `observability` | prometheus, loki, alloy, grafana, postgres-exporter, nats-exporter |
| **Langfuse** | `langfuse` | langfuse-web, langfuse-worker, clickhouse, langfuse-minio-init |

**Confidence: HIGH** - Derived directly from docker-compose files.

---

## 2. Network Architecture

### Docker Networks

```
+---------------------------------------------------------------------+
|                        FRONTEND network                              |
|   traefik, api, webui, minio, authentik-server, adminer, nui,       |
|   portainer, tensorboard                                             |
+------------------------------+--------------------------------------+
                               |
                          Traefik routing
                               |
+------------------------------+--------------------------------------+
|                        BACKEND network                               |
|   ALL services (postgres, qdrant, minio, nats, redis, api,          |
|   embedder, orchestrator, connector, ingestor, guardian, projector,  |
|   traefik, authentik-*, adminer, nui)                                |
+----------------------------------------------------------------------+
```

- **frontend**: Services that need Traefik routing (public-facing)
- **backend**: All inter-service communication
- Most application services are backend-only (no direct public access)

### Traefik Routing (Host Mode)

| Domain | Service | TLS | Auth |
|--------|---------|-----|------|
| `demo.echomind.ch` | webui (priority=1) | Let's Encrypt | - |
| `demo.echomind.ch/api/*`, `/oauth/*`, `/ws/*` | api (priority=100) | Let's Encrypt | CORS |
| `api.demo.echomind.ch` | api | Let's Encrypt | CORS |
| `auth.demo.echomind.ch` | authentik-server | Let's Encrypt | CORS |
| `qdrant.demo.echomind.ch` | qdrant | Let's Encrypt | Authentik ForwardAuth |
| `db.demo.echomind.ch` | adminer | Let's Encrypt | Authentik ForwardAuth |
| `minio.demo.echomind.ch` | minio console | Let's Encrypt | Authentik ForwardAuth |
| `s3.demo.echomind.ch` | minio API | Let's Encrypt | - |
| `nats.demo.echomind.ch` | nui | Let's Encrypt | Authentik ForwardAuth |
| `portainer.demo.echomind.ch` | portainer | Let's Encrypt | - |
| `tensorboard.demo.echomind.ch` | tensorboard | Let's Encrypt | - |

**HTTP -> HTTPS redirect** is enforced globally in host mode.

**Confidence: HIGH** - Directly from compose labels.

---

## 3. NATS JetStream Topology

### Streams

| Stream | Subjects | Created By | Description |
|--------|----------|------------|-------------|
| `ECHOMIND` | `connector.sync.*`, `document.process`, `projector.generate` | orchestrator | Main event stream |
| `ECHOMIND_DLQ` | `$JS.EVENT.ADVISORY.CONSUMER.MAX_DELIVERIES.ECHOMIND.>`, `$JS.EVENT.ADVISORY.CONSUMER.MSG_TERMINATED.ECHOMIND.>` | orchestrator | Dead letter queue advisories |
| `projector-stream` | `projector.generate` | projector | Projector-specific stream |

### Subject Topology

```
ECHOMIND stream
+-- connector.sync.web           -> connector service
+-- connector.sync.file          -> connector service
+-- connector.sync.onedrive      -> connector service
+-- connector.sync.google_drive  -> connector service
+-- connector.sync.gmail         -> connector service
+-- connector.sync.google_calendar -> connector service
+-- connector.sync.google_contacts -> connector service
+-- connector.sync.teams         -> connector service
+-- document.process             -> ingestor service
+-- projector.generate           -> projector service
```

### Message Flow

```
                    +--------------+
                    |  Orchestrator | (APScheduler)
                    +------+-------+
                           | publish connector.sync.*
                           v
                    +--------------+
                    |     NATS     |
                    |  JetStream   |
                    +--+---+---+---+
                       |   |   |
          +------------+   |   +------------+
          v                v                v
   +----------+    +----------+      +----------+
   | Connector |    | Ingestor |      | Guardian  |
   | (sub)     |    | (sub)    |      | (sub DLQ) |
   +-----+-----+    +----------+      +----------+
         | publish document.process
         v
   +--------------+
   |     NATS     | -> Ingestor subscribes to document.process
   +--------------+

   API also publishes:
   - document.process (direct upload)
   - projector.generate (visualization requests)
```

### Publishers

| Service | Subjects Published |
|---------|-------------------|
| **orchestrator** | `connector.sync.*` |
| **connector** | `document.process` |
| **api** | `document.process`, `projector.generate` |

### Subscribers

| Service | Stream | Subject | Consumer Pattern |
|---------|--------|---------|-----------------|
| **connector** | ECHOMIND | `connector.sync.*` | Per-type consumer: `connector-worker-{type}` |
| **ingestor** | ECHOMIND | `document.process` | `ingestor-worker-document-process` |
| **guardian** | ECHOMIND_DLQ | Advisory subjects | DLQ monitoring |
| **projector** | projector-stream | `projector.generate` | `projector-worker` |

### Consumer Config

- **Delivery**: Queue-based load balancing (`deliver_group = consumer`)
- **Max Deliver**: 3 attempts
- **Ack Wait**: 30 seconds
- **Deliver Policy**: ALL (process from beginning)

**Confidence: HIGH** - Verified from source code.

---

## 4. NATS Integration for Sandbox Communication

### Option A: NATS-Based Agent Events (Recommended)

Add new subjects under the `ECHOMIND` stream for agent sandbox communication:

```
ECHOMIND stream (extended)
+-- ... (existing subjects)
+-- agent.sandbox.create          -> API publishes, sandbox-pool subscribes
+-- agent.sandbox.ready           -> sandbox publishes when ready
+-- agent.sandbox.execute         -> API publishes tool execution requests
+-- agent.sandbox.result          -> sandbox publishes tool results
+-- agent.sandbox.heartbeat       -> sandbox publishes periodic heartbeats
+-- agent.sandbox.destroy         -> API publishes, sandbox-pool subscribes
```

**Pros:**
- Follows existing patterns (publisher/subscriber)
- Automatic retry/DLQ via JetStream
- Queue-based load balancing for multiple sandbox instances
- Decoupled: API doesn't need direct TCP to sandboxes

**Cons:**
- Latency: NATS adds ~1ms per hop
- Not ideal for streaming token output (WebSocket is better)

### Option B: Hybrid NATS + WebSocket

- **NATS** for lifecycle events (create, destroy, heartbeat)
- **Direct HTTP/WebSocket** from API to sandbox for low-latency tool execution
- Sandbox registers itself via NATS, API connects directly afterward

**Recommendation**: Option B (Hybrid) - NATS for lifecycle, direct connection for execution.

**Confidence: MEDIUM** - Architectural recommendation, needs validation.

---

## 5. Deployment System Analysis

### cluster.sh

**Modes:**
- `--local` / `-L`: Development (docker-compose.yml) - ports exposed, no TLS
- `--host` / `-H`: Production (docker-compose-host.yml) - Traefik-only ports, TLS

**Commands:**
| Command | Description |
|---------|-------------|
| `start` | Down + up (ensures env vars refreshed) |
| `stop` | Down |
| `restart` | Down + up |
| `status` | Show all containers grouped by prefix |
| `logs [svc]` | Follow logs |
| `build [svc]` | Build with cache |
| `rebuild <svc>` | Build without cache + restart |
| `pull` | Pull registry images |
| `build-release` | Build API for Docker Hub |
| `push` | Push to Docker Hub |
| `release` | Build + push |

**Key Patterns:**
1. `.env` is the ONLY env file used (both modes), gitignored
2. `set -a; source .env; set +a` exports all vars before compose
3. Optional stacks gated by env vars: `ENABLE_OBSERVABILITY`, `ENABLE_LANGFUSE`
4. Optional stacks use `--profile` and additional `-f` compose files
5. Build context is always `../../src` (project_root/src)
6. All custom services built from `src/{service}/Dockerfile`

### Build Services List

From cluster.sh line 559:
```bash
local services=("api" "migration" "embedder" "orchestrator" "connector" "ingestor" "guardian" "webui")
```

**Adding a new service requires:**
1. Add to this list in `build_services()`
2. Add Dockerfile at `src/{service}/Dockerfile`
3. Add service definition in both compose files
4. Add config dir if needed

**Confidence: HIGH**

---

## 6. Docker Compose Integration Plan for Sandbox Containers

### Approach: Sandbox Pool Service

Rather than dynamically creating containers (which requires Docker socket access and is complex), define a **sandbox-pool** service that can scale via `deploy.replicas` or separate service definitions.

### Option 1: Docker Compose `deploy.replicas` (Simpler)

```yaml
# In docker-compose.yml / docker-compose-host.yml
sandbox-pool:
  image: gsantopaolo/echomind-sandbox:${SANDBOX_VERSION:-0.1.0-beta.1}
  build:
    context: ../../src
    dockerfile: sandbox/Dockerfile
  deploy:
    replicas: ${SANDBOX_POOL_SIZE:-3}
    resources:
      limits:
        cpus: '1.0'
        memory: 512M
      reservations:
        cpus: '0.25'
        memory: 128M
  environment:
    - SANDBOX_NATS_URL=nats://nats:4222
    - SANDBOX_API_URL=http://api:8000
    - SANDBOX_POOL_ID={{.Task.Slot}}
  depends_on:
    nats:
      condition: service_healthy
  restart: unless-stopped
  networks:
    - backend
  labels:
    - "traefik.enable=false"
```

**Pros:**
- Simple: Docker Compose handles scaling
- Easy to change pool size via env var
- Automatic restart on crash
- Resource limits per container

**Cons:**
- All replicas are identical (no per-session isolation)
- Can't dynamically create/destroy individual containers
- Container naming: `echomind-sandbox-pool-1`, `echomind-sandbox-pool-2`, etc.

### Option 2: Docker API Dynamic Containers (More Complex)

A **sandbox-manager** service creates/destroys containers on demand via Docker API:

```yaml
sandbox-manager:
  image: gsantopaolo/echomind-sandbox-manager:${SANDBOX_VERSION:-0.1.0-beta.1}
  build:
    context: ../../src
    dockerfile: sandbox/Dockerfile.manager
  volumes:
    - /var/run/docker.sock:/var/run/docker.sock  # Docker-in-Docker access
  environment:
    - SANDBOX_NATS_URL=nats://nats:4222
    - SANDBOX_IMAGE=gsantopaolo/echomind-sandbox:${SANDBOX_VERSION:-0.1.0-beta.1}
    - SANDBOX_NETWORK=deployment_backend  # Docker Compose network name
    - SANDBOX_MAX_CONTAINERS=${SANDBOX_MAX:-10}
    - SANDBOX_CPU_LIMIT=1.0
    - SANDBOX_MEMORY_LIMIT=512m
    - SANDBOX_IDLE_TIMEOUT=300
  depends_on:
    nats:
      condition: service_healthy
  restart: unless-stopped
  networks:
    - backend
```

**Pros:**
- True per-session isolation
- Dynamic scaling (create on demand, destroy when idle)
- Better security model (each session gets fresh container)
- Can enforce strict resource limits per sandbox

**Cons:**
- Requires Docker socket access (security concern)
- Must manage container lifecycle explicitly
- Network attachment requires knowing Docker Compose network name
- More complex error handling (container crashes, orphans)

### Recommendation: Option 1 for Phase 1, Option 2 for Phase 2

Start with replica-based pool (simple, proven), evolve to dynamic containers later.

**Confidence: MEDIUM** - Architectural recommendation.

---

## 7. Service Communication Patterns

### Current Patterns

| Pattern | Services | Protocol | Library |
|---------|----------|----------|---------|
| **Sync HTTP** | webui -> api | REST + WebSocket | FastAPI/uvicorn |
| **Sync gRPC** | ingestor -> embedder | gRPC | grpcio |
| **Async NATS** | orchestrator -> connector -> ingestor | JetStream pub/sub | nats-py |
| **Async NATS** | api -> ingestor (direct upload) | JetStream pub | nats-py |
| **Async NATS** | api -> projector | JetStream pub | nats-py |
| **Async NATS** | DLQ advisories -> guardian | JetStream sub | nats-py |

### Proposed Sandbox Communication Pattern

```
+----------+         +----------+         +--------------+
|  WebUI   | --WS--> |   API    | --NATS-> |  Sandbox     |
| (browser)| <--WS-- | (FastAPI)| <--NATS- |  Container   |
+----------+         +----------+         +--------------+
                           |
                     +-----+-----+
                     |   NATS    |
                     | JetStream |
                     +-----------+
                           |
              +------------+------------+
              v            v            v
        +----------+ +----------+ +----------+
        | Sandbox 1| | Sandbox 2| | Sandbox 3|
        | (idle)   | | (active) | | (idle)   |
        +----------+ +----------+ +----------+
```

For streaming token responses, the sandbox should connect back to the API via HTTP/WebSocket, not NATS (NATS is not ideal for streaming large payloads).

**Confidence: MEDIUM**

---

## 8. Session and State Management

### Current Chat Session Flow

1. User connects via WebSocket to API
2. API creates/loads chat session from PostgreSQL
3. API's `ConnectionManager` tracks WebSocket connections per user/session
4. Messages are stored in PostgreSQL (chat_messages table)
5. LLM responses are streamed back via WebSocket

### Sandbox State Integration Points

| State | Storage | Description |
|-------|---------|-------------|
| Sandbox pool membership | In-memory (sandbox manager) or Redis | Which sandboxes are available |
| Session-to-sandbox mapping | Redis or PostgreSQL | Which chat session uses which sandbox |
| Sandbox health | NATS heartbeats + health checks | Is sandbox responsive |
| Tool execution results | NATS messages | Results flowing back to API |
| Sandbox filesystem | Container-local (ephemeral) | Agent's working directory |

### Proposed DB Schema Additions

```sql
-- Track sandbox assignments
CREATE TABLE agent_sandbox_sessions (
    id SERIAL PRIMARY KEY,
    chat_session_id INT REFERENCES chat_sessions(id),
    sandbox_container_id VARCHAR(255),
    sandbox_host VARCHAR(255),
    status VARCHAR(50) DEFAULT 'pending',  -- pending, active, idle, terminated
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_heartbeat_at TIMESTAMPTZ,
    terminated_at TIMESTAMPTZ
);
```

**Confidence: MEDIUM** - Schema is a proposal, needs validation against existing models.

---

## 9. Scaling Considerations

### Current Resource Profile (Estimated)

| Service | CPU | Memory | Notes |
|---------|-----|--------|-------|
| postgres | 1-2 cores | 1-2 GB | Shared DB |
| qdrant | 1-2 cores | 2-4 GB | Depends on collection size |
| minio | 0.5 cores | 256 MB | Object storage |
| nats | 0.5 cores | 256 MB | Lightweight message bus |
| redis | 0.25 cores | 512 MB | Capped at 512MB |
| api | 1-2 cores | 512 MB-1 GB | FastAPI + WebSocket |
| embedder | 2+ cores (GPU) | 2-4 GB | ML model loading |
| orchestrator | 0.25 cores | 128 MB | Scheduler only |
| connector | 0.5-1 core | 256-512 MB | I/O bound |
| ingestor | 1-2 cores | 1-2 GB | Document processing |
| guardian | 0.25 cores | 128 MB | Monitoring only |
| webui | 0.25 cores | 64 MB | Static nginx |

**Estimated total**: ~8-12 cores, ~8-12 GB RAM

### Sandbox Scaling

For 10 sandbox instances at 1 CPU / 512 MB each:
- **Additional CPU**: 10 cores (2.5 with reservation)
- **Additional RAM**: 5 GB (1.28 GB with reservation)
- **Total with existing**: ~18-22 cores, ~13-17 GB RAM

**Server sizing**: A server with 32 cores / 64 GB RAM could comfortably run EchoMind + 10-20 sandboxes.

### Pre-pulling for Fast Startup

Add sandbox image to the build list in `cluster.sh`:
```bash
local services=("api" "migration" "embedder" "orchestrator" "connector" "ingestor" "guardian" "webui" "sandbox")
```

And ensure `docker compose pull` includes sandbox image.

**Confidence: MEDIUM** - Resource estimates are approximate.

---

## 10. Container Image for Sandbox

### Dockerfile Pattern (follows existing conventions)

```dockerfile
# src/sandbox/Dockerfile
FROM python:3.12.12-slim-bookworm AS builder
WORKDIR /build
COPY sandbox/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12.12-slim-bookworm
WORKDIR /app

# Install safe binaries for agent tool execution
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl git jq \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /usr/local
COPY sandbox /app/sandbox
COPY echomind_lib /app/echomind_lib

ENV PYTHONPATH="/app"

# Non-root user (CRITICAL for security)
RUN useradd -m -u 1000 sandboxuser && \
    mkdir -p /workspace && chown sandboxuser:sandboxuser /workspace
USER sandboxuser

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8080/healthz || exit 1

EXPOSE 8080
CMD ["python", "-m", "sandbox.main"]
```

**Key considerations:**
- Multi-stage build (matches api, embedder, etc.)
- Non-root user (security)
- `echomind_lib` copied in (shared library pattern)
- `/workspace` directory for agent file operations
- Health check on 8080 (standard pattern)

**Confidence: HIGH** - Follows established Dockerfile patterns.

---

## 11. Summary: Integration Checklist

### Docker Compose Changes

1. Add `sandbox` or `sandbox-pool` service to both `docker-compose.yml` and `docker-compose-host.yml`
2. Add to `build_services()` list in `cluster.sh`
3. Service connects to `backend` network only (no public access)
4. Depends on `nats` (healthy) and optionally `api` (started)

### NATS Changes

1. Add `agent.*` subjects to `ECHOMIND` stream (in orchestrator's stream creation, or create a separate `AGENT` stream)
2. Sandbox service subscribes to `agent.sandbox.*`
3. API publishes to `agent.sandbox.create`, `agent.sandbox.execute`
4. Sandbox publishes to `agent.sandbox.ready`, `agent.sandbox.result`

### New Files Required

```
src/sandbox/
+-- Dockerfile
+-- requirements.txt
+-- __init__.py
+-- main.py              # Entry point (NATS subscriber + HTTP health)
+-- config.py            # Pydantic settings
+-- logic/
|   +-- sandbox_service.py  # Tool execution logic
|   +-- exceptions.py
+-- tools/
    +-- __init__.py
    +-- executor.py      # Safe tool execution engine
```

### Environment Variables

```bash
SANDBOX_NATS_URL=nats://nats:4222
SANDBOX_POOL_SIZE=3
SANDBOX_CPU_LIMIT=1.0
SANDBOX_MEMORY_LIMIT=512m
SANDBOX_IDLE_TIMEOUT=300
SANDBOX_LOG_LEVEL=INFO
```

**Confidence: HIGH** for integration pattern, MEDIUM for specific implementation details.

---

## 12. Detailed Implementation Plan

> This section provides copy-pasteable configurations, complete file definitions, and step-by-step implementation instructions for every infrastructure change required by the sandboxed agent system.

---

### 12a. Docker Compose Changes

#### New File: `docker-compose-sandbox.yml`

This overlay follows the same pattern as `docker-compose-observability.yml` -- gated by `ENABLE_SANDBOX=true` in `.env` and activated via `--profile sandbox` plus an additional `-f` compose file in `cluster.sh`.

```yaml
# docker-compose-sandbox.yml
# Sandbox infrastructure: MCP Gateway
# Gated by ENABLE_SANDBOX=true in .env (via --profile sandbox)
# Sandbox containers themselves are NOT in this file -- they are
# created dynamically by the API service via Docker SDK.

networks:
  sandbox:
    driver: bridge
    # Sandbox containers can reach NATS, MCP, and the internet.
    # They CANNOT reach backend-only services (postgres, qdrant, minio, redis, embedder).

services:
  # ============================================
  # MCP Gateway - Skill & Data Access Gateway
  # ============================================
  mcp-gateway:
    image: gsantopaolo/echomind-mcp-gateway:${MCP_GATEWAY_VERSION:-0.1.0-beta.1}
    build:
      context: ../../src
      dockerfile: mcp_gateway/Dockerfile
    container_name: echomind-mcp-gateway
    hostname: mcp-gateway
    profiles: ["sandbox"]
    env_file:
      - ${CONFIG_PATH}/mcp-gateway/mcp-gateway.env
    environment:
      # Database (read-only queries for search)
      - MCP_GATEWAY_DATABASE_URL=postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${API_DB_NAME}
      # Qdrant (vector search)
      - MCP_GATEWAY_QDRANT_HOST=qdrant
      - MCP_GATEWAY_QDRANT_PORT=6333
      # Embedder (text-to-vector for search queries)
      - MCP_GATEWAY_EMBEDDER_HOST=embedder
      - MCP_GATEWAY_EMBEDDER_PORT=50051
      # MinIO (document retrieval)
      - MCP_GATEWAY_MINIO_ENDPOINT=minio:9000
      - MCP_GATEWAY_MINIO_ACCESS_KEY=${MINIO_ROOT_USER}
      - MCP_GATEWAY_MINIO_SECRET_KEY=${MINIO_ROOT_PASSWORD}
      # Skills directory
      - MCP_GATEWAY_SKILLS_DIR=/app/skills
      # Server
      - MCP_GATEWAY_HOST=0.0.0.0
      - MCP_GATEWAY_PORT=8100
      - MCP_GATEWAY_LOG_LEVEL=${MCP_GATEWAY_LOG_LEVEL:-INFO}
    volumes:
      - ${CONFIG_PATH}/agents/skills:/app/skills:ro
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8100/healthz"]
      interval: 30s
      timeout: 10s
      start_period: 15s
      retries: 3
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 1G
        reservations:
          cpus: '0.5'
          memory: 256M
    depends_on:
      postgres:
        condition: service_healthy
      qdrant:
        condition: service_healthy
      embedder:
        condition: service_healthy
      migration:
        condition: service_completed_successfully
    restart: unless-stopped
    networks:
      - backend
      - sandbox
    labels:
      - "traefik.enable=false"
```

#### New File: `docker-compose-sandbox-host.yml`

Production override (follows `docker-compose-observability-host.yml` pattern). For sandbox services, the only change is that the API service gains Docker socket access and the sandbox network in host mode.

```yaml
# docker-compose-sandbox-host.yml
# Production overrides for sandbox infrastructure.
# API needs Docker socket to manage sandbox containers via Docker SDK.

services:
  api:
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
    networks:
      - frontend
      - backend
      - sandbox
    environment:
      # Sandbox manager settings (API creates containers via Docker SDK)
      - API_SANDBOX_ENABLED=${ENABLE_SANDBOX:-false}
      - API_SANDBOX_IMAGE=gsantopaolo/echomind-sandbox:${SANDBOX_VERSION:-0.1.0-beta.1}
      - API_SANDBOX_NETWORK=${COMPOSE_PROJECT_NAME:-deployment}_sandbox
      - API_SANDBOX_NATS_NETWORK=${COMPOSE_PROJECT_NAME:-deployment}_backend
      - API_SANDBOX_MCP_URL=http://mcp-gateway:8100
      - API_SANDBOX_NATS_URL=nats://nats:4222
      - API_SANDBOX_POOL_SIZE=${SANDBOX_POOL_SIZE:-3}
      - API_SANDBOX_MAX_CONTAINERS=${SANDBOX_MAX_CONTAINERS:-10}
      - API_SANDBOX_CPU_LIMIT=${SANDBOX_CPU_LIMIT:-2.0}
      - API_SANDBOX_MEMORY_LIMIT=${SANDBOX_MEMORY_LIMIT:-2g}
      - API_SANDBOX_PID_LIMIT=${SANDBOX_PID_LIMIT:-100}
      - API_SANDBOX_IDLE_TIMEOUT=${SANDBOX_IDLE_TIMEOUT:-300}

networks:
  sandbox:
    driver: bridge
```

**Key design decisions:**
- MCP gateway is a Docker Compose service (managed by compose, always running when sandbox is enabled).
- Sandbox containers are NOT compose services. They are created/destroyed dynamically by the API service using the Docker SDK for Python (`docker` package). This enables per-session isolation and warm pool management.
- The API service needs Docker socket access (`/var/run/docker.sock`) to manage sandbox containers. This is mounted read-only.
- The `sandbox` network is a separate Docker bridge network. Sandbox containers are attached to this network plus the `backend` network (for NATS access). They cannot reach postgres, qdrant, minio, or redis directly because those services are only on `backend` -- but the MCP gateway, which IS on both networks, acts as the secure proxy.

[Source: Docker Compose Profiles -- https://docs.docker.com/compose/how-tos/profiles/ -- 2026]
[Source: Docker Compose Deploy Specification -- https://docs.docker.com/reference/compose-file/deploy/ -- 2026]

---

### 12b. NATS Configuration

#### New Stream: `SANDBOX`

A dedicated stream for sandbox lifecycle and messaging. Separate from `ECHOMIND` because:
- Different retention requirements (memory storage, short TTL)
- Different consumer patterns (per-session subjects)
- Avoids polluting the main stream with high-frequency sandbox messages

**Stream Definition:**

| Property | Value | Rationale |
|----------|-------|-----------|
| Name | `SANDBOX` | Dedicated namespace |
| Subjects | `sandbox.>` | Wildcard captures all sandbox subjects |
| Storage | Memory | Low latency, ephemeral data |
| Retention | Limits-based | Auto-discard old messages |
| Max Messages | 100,000 | Prevent unbounded growth |
| Max Age | 1h (3,600s) | Sandbox sessions rarely exceed 1h |
| Max Bytes | 256MB | Memory budget cap |
| Discard | Old | Drop oldest messages when limits hit |
| Replicas | 1 | Single-node deployment |
| Allow Direct | true | Fast direct-get for recent messages |

**Subject Hierarchy:**

```
SANDBOX stream
+-- sandbox.{session_id}.input      API -> Sandbox: user messages
+-- sandbox.{session_id}.output     Sandbox -> API: agent responses
+-- sandbox.{session_id}.stream     Sandbox -> API: streaming tokens
+-- sandbox.{session_id}.control    API -> Sandbox: lifecycle commands (stop, drain)
+-- sandbox.{session_id}.health     Sandbox -> API: periodic heartbeats
```

Each `{session_id}` is a UUID. This gives per-session message ordering and isolation.

**Audit Stream: `SANDBOX_AUDIT`**

| Property | Value | Rationale |
|----------|-------|-----------|
| Name | `SANDBOX_AUDIT` | Audit trail for sandbox operations |
| Subjects | `sandbox.audit.>` | All audit events |
| Storage | File | Persistent audit log |
| Retention | Limits-based | |
| Max Age | 7d | Compliance/debugging window |
| Max Bytes | 1GB | Disk budget cap |

**Audit Subjects:**

```
SANDBOX_AUDIT stream
+-- sandbox.audit.created       Sandbox container created
+-- sandbox.audit.assigned      Sandbox assigned to session
+-- sandbox.audit.destroyed     Sandbox container destroyed
+-- sandbox.audit.tool_call     MCP tool invocation audit
+-- sandbox.audit.error         Sandbox error events
```

#### Consumer Configuration

**API Service Consumer (subscribes to sandbox output):**

```python
# Consumer for receiving sandbox responses
consumer_config = ConsumerConfig(
    durable_name="api-sandbox-output",
    filter_subject="sandbox.*.output",
    ack_policy=AckPolicy.EXPLICIT,
    ack_wait=30,  # seconds
    max_deliver=3,
    deliver_policy=DeliverPolicy.NEW,
    max_ack_pending=100,
)
```

**API Service Consumer (subscribes to sandbox streaming tokens):**

```python
# Consumer for receiving streaming tokens (ephemeral, no durable name)
consumer_config = ConsumerConfig(
    filter_subject=f"sandbox.{session_id}.stream",
    ack_policy=AckPolicy.NONE,  # Fire-and-forget for streaming
    deliver_policy=DeliverPolicy.NEW,
)
```

**API Service Consumer (subscribes to sandbox health):**

```python
# Consumer for receiving heartbeats
consumer_config = ConsumerConfig(
    durable_name="api-sandbox-health",
    filter_subject="sandbox.*.health",
    ack_policy=AckPolicy.NONE,  # Best-effort health monitoring
    deliver_policy=DeliverPolicy.LAST_PER_SUBJECT,
)
```

#### NATS CLI Commands for Stream Creation and Verification

These commands can be used to manually create/verify the streams, or can be executed programmatically by the API service on startup (as the orchestrator does for the `ECHOMIND` stream).

```bash
# Create the SANDBOX stream
nats stream add SANDBOX \
  --subjects "sandbox.>" \
  --storage memory \
  --retention limits \
  --max-msgs 100000 \
  --max-age 1h \
  --max-bytes 268435456 \
  --discard old \
  --replicas 1 \
  --allow-direct \
  --defaults

# Create the SANDBOX_AUDIT stream
nats stream add SANDBOX_AUDIT \
  --subjects "sandbox.audit.>" \
  --storage file \
  --retention limits \
  --max-age 168h \
  --max-bytes 1073741824 \
  --discard old \
  --replicas 1 \
  --defaults

# Verify streams exist
nats stream ls
nats stream info SANDBOX
nats stream info SANDBOX_AUDIT

# Monitor sandbox messages in real-time (debugging)
nats sub "sandbox.>"

# Check consumer status
nats consumer ls SANDBOX
```

**Implementation Note:** Stream creation should be idempotent. The API service should call `js.add_stream()` with `nats.js.api.StreamConfig` on startup, which is a no-op if the stream already exists with matching config.

[Source: NATS JetStream Streams -- https://docs.nats.io/nats-concepts/jetstream/streams -- 2025]
[Source: NATS JetStream Consumers -- https://docs.nats.io/nats-concepts/jetstream/consumers -- 2025]

---

### 12c. Network Topology

#### Complete Network Map

```
+=====================================================================+
|                        FRONTEND network                              |
|   traefik, api, webui, minio, authentik-server, adminer, nui,       |
|   portainer, tensorboard, grafana                                    |
+=================================+===================================+
                                  |
                             Traefik routing
                                  |
+=================================+===================================+
|                        BACKEND network                               |
|   postgres, qdrant, minio, nats, redis, api, embedder, orchestrator,|
|   connector, ingestor, guardian, projector, traefik, authentik-*,    |
|   adminer, nui, loki, alloy, prometheus, nats-exporter,             |
|   postgres-exporter, mcp-gateway                                     |
+=================================+===================================+
                                  |
                     mcp-gateway + nats bridge
                                  |
+=================================+===================================+
|                        SANDBOX network                               |
|   mcp-gateway, nats*, sandbox-0, sandbox-1, ...                     |
+=====================================================================+

* NATS is on the backend network. Sandbox containers reach NATS because
  they are attached to BOTH the sandbox network AND the backend network
  by the Docker SDK when created. MCP gateway is also on both networks.
```

#### Network Membership Table

| Service | frontend | backend | sandbox | Notes |
|---------|----------|---------|---------|-------|
| traefik | Y | Y | - | Reverse proxy |
| api | Y | Y | Y (host mode) | Needs sandbox network to create containers on it |
| webui | Y | - | - | Static frontend |
| postgres | - | Y | - | Database (BLOCKED from sandbox) |
| qdrant | - | Y | - | Vector DB (BLOCKED from sandbox) |
| minio | Y | Y | - | Object storage (BLOCKED from sandbox) |
| redis | - | Y | - | Cache (BLOCKED from sandbox) |
| nats | - | Y | - | Message bus (reachable via backend) |
| embedder | - | Y | - | ML inference (BLOCKED from sandbox) |
| mcp-gateway | - | Y | Y | Bridge between sandbox and backend |
| sandbox-N | - | Y | Y | Created by Docker SDK, attached to both networks |

#### Why Sandboxes Join Backend Network

Sandbox containers need to reach NATS (on backend) for message passing. Rather than adding NATS to the sandbox network (which would require modifying the NATS service definition), sandbox containers are attached to both `backend` and `sandbox` networks by the Docker SDK at creation time. This follows the same dual-network pattern used by the API service (frontend + backend) and minio (frontend + backend).

**Security boundary**: Sandbox containers CAN reach any service on the backend network via DNS. The security enforcement happens at the application layer -- sandbox containers only know about NATS and MCP gateway URLs (injected via environment variables). They have no credentials for postgres, qdrant, or minio.

**Future hardening** (Phase 8): iptables rules or Docker network policies can be added to restrict sandbox containers to only NATS and MCP gateway at the network level.

#### Docker SDK Network Attachment

When the API's SandboxManager creates a container via Docker SDK:

```python
import docker

client = docker.from_env()

# Create container on sandbox network
container = client.containers.create(
    image="gsantopaolo/echomind-sandbox:0.1.0-beta.1",
    name=f"sandbox-{session_id[:12]}",
    network="deployment_sandbox",  # Primary network
    environment={
        "SANDBOX_SESSION_ID": session_id,
        "SANDBOX_NATS_URL": "nats://nats:4222",
        "SANDBOX_MCP_URL": "http://mcp-gateway:8100",
    },
    # Resource limits
    nano_cpus=int(2.0 * 1e9),       # 2 CPU cores
    mem_limit="2g",                   # 2GB RAM
    pids_limit=100,                   # Max 100 processes
    # Security
    read_only=True,                   # Read-only root filesystem
    cap_drop=["ALL"],                 # Drop all capabilities
    cap_add=["NET_RAW"],              # Required for DNS resolution
    tmpfs={"/tmp": "size=100m,noexec,nosuid"},  # Writable /tmp
    user="1000:1000",                 # Non-root
    # Volumes
    volumes={
        "sandbox_workspace": {"bind": "/workspace", "mode": "rw"},
    },
)

# Attach to backend network (for NATS access)
backend_network = client.networks.get("deployment_backend")
backend_network.connect(container)

# Start the container
container.start()
```

[Source: Docker SDK for Python Containers -- https://docker-py.readthedocs.io/en/stable/containers.html -- 2025]
[Source: Docker SDK for Python Networks -- https://docker-py.readthedocs.io/en/stable/networks.html -- 2025]
[Source: Docker Bridge Network Driver -- https://docs.docker.com/engine/network/drivers/bridge/ -- 2026]

---

### 12d. cluster.sh Updates

#### New Environment Variable Detection

Add sandbox stack detection after the existing Langfuse detection block (around line 161 in `cluster.sh`):

```bash
# Read ENABLE_SANDBOX from .env
SANDBOX_PROFILE=""
SANDBOX_FILES=""
_sandbox_enabled=false
if [ -f "$SCRIPT_DIR/.env" ] && grep -q "^[[:space:]]*ENABLE_SANDBOX[[:space:]]*=[[:space:]]*true" "$SCRIPT_DIR/.env" 2>/dev/null; then
    _sandbox_enabled=true
fi
if [ "$_sandbox_enabled" = true ]; then
    SANDBOX_PROFILE="--profile sandbox"
    SANDBOX_FILES="-f docker-compose-sandbox.yml"
    if [ "$MODE" = "host" ]; then
        SANDBOX_FILES="$SANDBOX_FILES -f docker-compose-sandbox-host.yml"
    fi
fi
```

#### Updated Compose Command Template

Every `docker compose` invocation in cluster.sh must include the sandbox files. The existing pattern is:

```bash
docker compose $COMPOSE_ENV_FLAG -f "$COMPOSE_FILE" $OBSERVABILITY_FILES $OBSERVABILITY_PROFILE $LANGFUSE_FILES $LANGFUSE_PROFILE ...
```

Updated to:

```bash
docker compose $COMPOSE_ENV_FLAG -f "$COMPOSE_FILE" $OBSERVABILITY_FILES $OBSERVABILITY_PROFILE $LANGFUSE_FILES $LANGFUSE_PROFILE $SANDBOX_FILES $SANDBOX_PROFILE ...
```

This affects the following functions: `start_cluster`, `stop_cluster`, `restart_cluster`, `show_logs`, `show_status`, `pull_images`, `build_services`, `rebuild_service`.

#### Updated Build Services List

```bash
local services=("api" "migration" "embedder" "orchestrator" "connector" "ingestor" "guardian" "webui")

# Add sandbox services if enabled
if [ "$_sandbox_enabled" = true ]; then
    services+=("mcp-gateway" "sandbox")
fi
```

#### New Data Directories

In `create_directories()`:

```bash
# Sandbox data directories
if [ -n "$SANDBOX_PROFILE" ]; then
    mkdir -p "$PROJECT_ROOT/data/sandbox"
    mkdir -p "$PROJECT_ROOT/config/mcp-gateway"
fi
```

#### Updated Status Display

In `show_status()`, add a sandbox section:

```bash
if echo "$ALL_CONTAINERS" | grep -q "^sandbox-\|^echomind-mcp"; then
    echo -e "${MAGENTA}---${NC}"
    echo -e "${MAGENTA}Sandbox Services${NC}"
    echo -e "${MAGENTA}---${NC}"
    echo "$ALL_CONTAINERS" | grep "^echomind-mcp" | awk -F'\t' '{printf "  %-30s %s\n", $1, $2}'
    echo ""
    # Dynamic sandbox containers (created by Docker SDK, not compose)
    SANDBOX_CONTAINERS=$(docker ps --filter "name=sandbox-" --format "{{.Names}}\t{{.Status}}" 2>/dev/null)
    if [ -n "$SANDBOX_CONTAINERS" ]; then
        echo -e "  ${CYAN}Dynamic Sandbox Containers:${NC}"
        echo "$SANDBOX_CONTAINERS" | awk -F'\t' '{printf "    %-28s %s\n", $1, $2}'
    else
        echo -e "  ${YELLOW}No sandbox containers running${NC}"
    fi
    echo ""
fi
```

#### Updated Start URLs

In `start_cluster()`, after existing URL display blocks:

```bash
if [ -n "$SANDBOX_PROFILE" ]; then
    log_info "Sandbox Services:"
    echo -e "  ${GREEN}MCP Gateway:${NC}     Internal (echomind-mcp-gateway:8100)"
    echo ""
fi
```

**Note:** No new top-level commands like `sandbox-start` or `sandbox-stop` are needed. Sandbox infrastructure (MCP gateway) starts/stops with the cluster. Dynamic sandbox containers are managed by the API service's SandboxManager, which creates/destroys them via Docker SDK based on session lifecycle.

---

### 12e. Environment Variables

#### New Variables for `.env.example`

Add the following section to `deployment/docker-cluster/.env.example`:

```bash
# =============================================================================
# SANDBOX CONFIGURATION
# =============================================================================
# Set to true to enable the sandbox infrastructure (MCP gateway).
# When enabled, the API service can create ephemeral sandbox containers.
ENABLE_SANDBOX=false

# --- Sandbox Container Settings ---
# Docker image for sandbox containers (built by cluster.sh)
SANDBOX_VERSION=0.1.0-beta.1
# Number of pre-warmed sandbox containers in the pool
SANDBOX_POOL_SIZE=3
# Maximum concurrent sandbox containers
SANDBOX_MAX_CONTAINERS=10
# CPU limit per sandbox container (in cores)
SANDBOX_CPU_LIMIT=2.0
# Memory limit per sandbox container
SANDBOX_MEMORY_LIMIT=2g
# Max processes per sandbox container
SANDBOX_PID_LIMIT=100
# Seconds before idle sandbox is destroyed
SANDBOX_IDLE_TIMEOUT=300

# --- MCP Gateway Settings ---
MCP_GATEWAY_VERSION=0.1.0-beta.1
MCP_GATEWAY_LOG_LEVEL=INFO

```

#### Variable Reference Table

| Variable | Service | Default | Description |
|----------|---------|---------|-------------|
| `ENABLE_SANDBOX` | cluster.sh | `false` | Master switch for sandbox infrastructure |
| `SANDBOX_VERSION` | compose | `0.1.0-beta.1` | Sandbox container image tag |
| `SANDBOX_POOL_SIZE` | API | `3` | Warm pool size |
| `SANDBOX_MAX_CONTAINERS` | API | `10` | Hard cap on concurrent sandboxes |
| `SANDBOX_CPU_LIMIT` | API/Docker SDK | `2.0` | CPU cores per sandbox |
| `SANDBOX_MEMORY_LIMIT` | API/Docker SDK | `2g` | RAM per sandbox |
| `SANDBOX_PID_LIMIT` | API/Docker SDK | `100` | Process limit per sandbox |
| `SANDBOX_IDLE_TIMEOUT` | API | `300` | Seconds before idle destroy |
| `MCP_GATEWAY_VERSION` | compose | `0.1.0-beta.1` | MCP gateway image tag |
| `MCP_GATEWAY_LOG_LEVEL` | mcp-gateway | `INFO` | Log verbosity |

---

### 12f. Dockerfile for MCP Gateway

Complete Dockerfile following existing EchoMind service patterns (matches `src/api/Dockerfile`):

```dockerfile
# src/mcp_gateway/Dockerfile
# Multi-stage build for MCP Gateway service

# ===============================================
# Stage 1: Builder - Install dependencies
# ===============================================
FROM python:3.12.12-slim-bookworm AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (cache layer optimization)
COPY mcp_gateway/requirements.txt .

# Install Python dependencies in a separate location
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ===============================================
# Stage 2: Runtime - Minimal final image
# ===============================================
FROM python:3.12.12-slim-bookworm

WORKDIR /app

# Install only runtime dependencies (no build tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY mcp_gateway /app/mcp_gateway
COPY echomind_lib /app/echomind_lib

# Set Python path
ENV PYTHONPATH="/app"

# Create non-root user for security
RUN useradd -m -u 1000 mcpuser && \
    chown -R mcpuser:mcpuser /app
USER mcpuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8100/healthz || exit 1

# Expose port
EXPOSE 8100

# Run with uvicorn (FastMCP uses ASGI under the hood)
CMD ["python", "-m", "mcp_gateway.main"]
```

#### `src/mcp_gateway/requirements.txt`

```
# MCP Gateway dependencies
# Versions MUST match echomind_lib/pyproject.toml where applicable

fastmcp>=3.0,<4.0
sqlalchemy[asyncio]==2.0.36
asyncpg==0.30.0
qdrant-client==1.12.1
grpcio==1.69.0
pydantic==2.10.4
pydantic-settings==2.7.1
uvicorn==0.34.0
httpx==0.28.1
```

---

### 12g. Dockerfile for Agent Sandbox

Complete Dockerfile for the base sandbox image. This image is pre-built and used by the Docker SDK warm pool.

```dockerfile
# src/sandbox/Dockerfile
# Base image for agent sandbox containers (warm pool).
# Pre-installs all packages needed for skill execution.

# ===============================================
# Stage 1: Builder - Install dependencies
# ===============================================
FROM python:3.12.12-slim-bookworm AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (cache layer optimization)
COPY sandbox/requirements.txt .

# Install Python dependencies in a separate location
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ===============================================
# Stage 2: Runtime - Sandbox execution environment
# ===============================================
FROM python:3.12.12-slim-bookworm

WORKDIR /app

# Install runtime tools for skill execution
# These are the "safe binaries" that skills can invoke
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    jq \
    wget \
    unzip \
    openssh-client \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install GitHub CLI (used by github skill)
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
    | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
    | tee /etc/apt/sources.list.d/github-cli.list > /dev/null \
    && apt-get update && apt-get install -y --no-install-recommends gh \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY sandbox /app/sandbox
COPY echomind_lib /app/echomind_lib

# Set Python path
ENV PYTHONPATH="/app"

# Create non-root user (CRITICAL for security)
RUN useradd -m -u 1000 -s /bin/bash sandboxuser && \
    mkdir -p /workspace && chown sandboxuser:sandboxuser /workspace && \
    mkdir -p /home/sandboxuser/.config && chown -R sandboxuser:sandboxuser /home/sandboxuser

# Set PATH for sandboxuser (skills need access to installed binaries)
ENV PATH="/usr/local/bin:/usr/bin:/bin"

USER sandboxuser
WORKDIR /workspace

# Health check
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8080/healthz || exit 1

# Expose health check port
EXPOSE 8080

# Entrypoint: the sandbox agent runner
CMD ["python", "-m", "sandbox.main"]
```

#### `src/sandbox/requirements.txt`

```
# Sandbox agent dependencies
# Versions MUST match echomind_lib/pyproject.toml where applicable

# Semantic Kernel (agent framework)
semantic-kernel==1.20.0

# MCP client (connects to MCP gateway)
mcp==1.9.0

# NATS (message bus communication with API)
nats-py==2.10.0
nats-py[nkeys]==2.10.0

# HTTP server (health check)
uvicorn==0.34.0
fastapi==0.115.6

# Utilities
pydantic==2.10.4
pydantic-settings==2.7.1
httpx==0.28.1
```

---

### 12h. Database Migrations

#### Alembic Migration: `sandbox_sessions` and `sandbox_events` Tables

File: `src/migration/migrations/versions/20260216_010000_add_sandbox_tables.py`

```python
"""Add sandbox_sessions and sandbox_events tables.

Revision ID: 20260216_010000
Revises: 20260210_033000
Create Date: 2026-02-16 01:00:00.000000

Creates tables for tracking sandbox container lifecycle and events.
sandbox_sessions maps chat sessions to ephemeral sandbox containers.
sandbox_events provides an audit log of sandbox operations.
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "20260216_010000"
down_revision = "20260210_033000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add sandbox_sessions and sandbox_events tables."""
    # --- sandbox_sessions ---
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS sandbox_sessions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            session_id VARCHAR(255) UNIQUE NOT NULL,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            chat_session_id INTEGER REFERENCES chat_sessions(id) ON DELETE SET NULL,
            container_id VARCHAR(64) NOT NULL,
            container_name VARCHAR(255) NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'assigned',
            assigned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            activated_at TIMESTAMPTZ,
            destroyed_at TIMESTAMPTZ,
            agent_config JSONB NOT NULL DEFAULT '{}',
            message_count INTEGER DEFAULT 0,
            tool_calls_count INTEGER DEFAULT 0,
            total_tokens INTEGER DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    # Indexes for sandbox_sessions
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_sandbox_sessions_user_id
        ON sandbox_sessions(user_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_sandbox_sessions_status
        ON sandbox_sessions(status)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_sandbox_sessions_chat_session_id
        ON sandbox_sessions(chat_session_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_sandbox_sessions_container_id
        ON sandbox_sessions(container_id)
        """
    )

    # --- sandbox_events ---
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS sandbox_events (
            id BIGSERIAL PRIMARY KEY,
            sandbox_session_id UUID NOT NULL REFERENCES sandbox_sessions(id) ON DELETE CASCADE,
            event_type VARCHAR(50) NOT NULL,
            event_data JSONB DEFAULT '{}',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    # Indexes for sandbox_events
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_sandbox_events_session_id
        ON sandbox_events(sandbox_session_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_sandbox_events_event_type
        ON sandbox_events(event_type)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_sandbox_events_created_at
        ON sandbox_events(created_at)
        """
    )


def downgrade() -> None:
    """Remove sandbox_events and sandbox_sessions tables."""
    op.execute("DROP TABLE IF EXISTS sandbox_events")
    op.execute("DROP TABLE IF EXISTS sandbox_sessions")
```

#### Column Reference

**`sandbox_sessions`:**

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | UUID | PK, auto-generated | Unique session identifier |
| `session_id` | VARCHAR(255) | UNIQUE, NOT NULL | Application-level session ID |
| `user_id` | INTEGER | FK -> users(id), NOT NULL | Owning user |
| `chat_session_id` | INTEGER | FK -> chat_sessions(id), nullable | Linked chat session |
| `container_id` | VARCHAR(64) | NOT NULL | Docker container ID (short hash) |
| `container_name` | VARCHAR(255) | NOT NULL | Docker container name |
| `status` | VARCHAR(20) | NOT NULL, default 'assigned' | One of: warm, assigned, active, draining, destroyed |
| `assigned_at` | TIMESTAMPTZ | NOT NULL | When container was assigned to session |
| `activated_at` | TIMESTAMPTZ | nullable | When first message was processed |
| `destroyed_at` | TIMESTAMPTZ | nullable | When container was destroyed |
| `agent_config` | JSONB | NOT NULL, default '{}' | Agent configuration snapshot |
| `message_count` | INTEGER | default 0 | Total messages processed |
| `tool_calls_count` | INTEGER | default 0 | Total MCP tool calls made |
| `total_tokens` | INTEGER | default 0 | Total LLM tokens consumed |
| `created_at` | TIMESTAMPTZ | NOT NULL | Row creation timestamp |
| `updated_at` | TIMESTAMPTZ | NOT NULL | Last update timestamp |

**`sandbox_events`:**

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | BIGSERIAL | PK | Auto-incrementing event ID |
| `sandbox_session_id` | UUID | FK -> sandbox_sessions(id), NOT NULL | Parent session |
| `event_type` | VARCHAR(50) | NOT NULL | Event type (see below) |
| `event_data` | JSONB | default '{}' | Event-specific payload |
| `created_at` | TIMESTAMPTZ | NOT NULL | Event timestamp |

**Event Types:**

| Event Type | Description | event_data Example |
|------------|-------------|-------------------|
| `container.created` | Container created from warm pool | `{"container_id": "abc123", "image": "..."}` |
| `container.assigned` | Container assigned to user session | `{"user_id": 1, "chat_session_id": 42}` |
| `container.activated` | First message processed | `{}` |
| `container.destroyed` | Container removed | `{"reason": "idle_timeout", "duration_seconds": 305}` |
| `message.received` | User message received | `{"length": 150}` |
| `message.response` | Agent response sent | `{"tokens": 342, "duration_ms": 1500}` |
| `tool.called` | MCP tool invoked | `{"tool": "search_documents", "duration_ms": 120}` |
| `tool.error` | Tool call failed | `{"tool": "skills_execute", "error": "timeout"}` |
| `health.timeout` | Heartbeat missed | `{"last_heartbeat": "2026-02-16T12:00:00Z"}` |
| `error.crash` | Container crashed | `{"exit_code": 137, "oom_killed": true}` |

---

### 12i. File-by-File Implementation Plan

#### Implementation Order

The order follows dependency chains: config files first, then compose files, then cluster.sh, then Dockerfiles, then migration, then source code.

**Phase 4A: Infrastructure Files (no code, just config)**

| # | File | Action | Purpose | Depends On |
|---|------|--------|---------|------------|
| 1 | `config/mcp-gateway/mcp-gateway.env` | CREATE | Default env vars for MCP gateway service | - |
| 3 | `config/agents/skills/` | CREATE (dir) | Skills directory (SKILL.md files go here) | - |
| 4 | `deployment/docker-cluster/docker-compose-sandbox.yml` | CREATE | Sandbox overlay compose file | #1, #2 |
| 5 | `deployment/docker-cluster/docker-compose-sandbox-host.yml` | CREATE | Production overrides for sandbox | #4 |
| 6 | `deployment/docker-cluster/.env.example` | MODIFY | Add SANDBOX/MCP variables | - |
| 7 | `deployment/docker-cluster/cluster.sh` | MODIFY | Add sandbox stack detection + compose flags | #4, #5 |

**Phase 4B: Dockerfiles and Dependencies**

| # | File | Action | Purpose | Depends On |
|---|------|--------|---------|------------|
| 8 | `src/mcp_gateway/Dockerfile` | CREATE | MCP gateway container image | - |
| 9 | `src/mcp_gateway/requirements.txt` | CREATE | Python dependencies for MCP gateway | - |
| 10 | `src/sandbox/Dockerfile` | CREATE | Sandbox base container image | - |
| 11 | `src/sandbox/requirements.txt` | CREATE | Python dependencies for sandbox | - |

**Phase 4C: Database Migration**

| # | File | Action | Purpose | Depends On |
|---|------|--------|---------|------------|
| 12 | `src/migration/migrations/versions/20260216_010000_add_sandbox_tables.py` | CREATE | sandbox_sessions + sandbox_events tables | - |

**Phase 4D: Source Code (MCP Gateway)**

| # | File | Action | Purpose | Depends On |
|---|------|--------|---------|------------|
| 13 | `src/mcp_gateway/__init__.py` | CREATE | Package init | - |
| 14 | `src/mcp_gateway/main.py` | CREATE | FastMCP server entrypoint | #9 |
| 15 | `src/mcp_gateway/config.py` | CREATE | Pydantic settings (MCP_GATEWAY_ prefix) | - |
| 16 | `src/mcp_gateway/tools/__init__.py` | CREATE | Tools package | - |
| 17 | `src/mcp_gateway/tools/search.py` | CREATE | search_documents, search_collections, etc. | #15 |
| 18 | `src/mcp_gateway/tools/skills.py` | CREATE | skills_list, skills_get_info, skills_execute | #15 |
| 19 | `src/mcp_gateway/skills/__init__.py` | CREATE | Skills package | - |
| 20 | `src/mcp_gateway/skills/registry.py` | CREATE | SKILL.md parser and discovery | - |
| 21 | `src/mcp_gateway/skills/executor.py` | CREATE | Subprocess execution with limits | - |
| 22 | `src/mcp_gateway/backends/__init__.py` | CREATE | Backends package | - |
| 23 | `src/mcp_gateway/backends/search_backend.py` | CREATE | Qdrant + Embedder integration | - |
| 24 | `src/mcp_gateway/middleware/__init__.py` | CREATE | Middleware package | - |
| 25 | `src/mcp_gateway/middleware/audit_logger.py` | CREATE | Structured JSON audit log | - |

**Phase 4E: Source Code (Sandbox)**

| # | File | Action | Purpose | Depends On |
|---|------|--------|---------|------------|
| 26 | `src/sandbox/__init__.py` | CREATE | Package init | - |
| 27 | `src/sandbox/main.py` | CREATE | Entry point: NATS sub + health server | #11 |
| 28 | `src/sandbox/config.py` | CREATE | Pydantic settings (SANDBOX_ prefix) | - |
| 29 | `src/sandbox/agent_runner.py` | CREATE | Semantic Kernel agent with MCP tools | - |

**Phase 4F: Source Code (API SandboxManager)**

| # | File | Action | Purpose | Depends On |
|---|------|--------|---------|------------|
| 30 | `src/api/sandbox/__init__.py` | CREATE | Sandbox package in API | - |
| 31 | `src/api/sandbox/manager.py` | CREATE | Container lifecycle via Docker SDK | - |
| 32 | `src/api/sandbox/models.py` | CREATE | SandboxSession, SandboxEvent ORM models | #12 |
| 33 | `src/api/sandbox/routes.py` | CREATE | REST endpoints for sandbox admin | #31, #32 |

**Phase 4G: Tests**

| # | File | Action | Purpose | Depends On |
|---|------|--------|---------|------------|
| 34 | `tests/unit/mcp_gateway/test_skill_registry.py` | CREATE | SKILL.md parsing tests | #20 |
| 35 | `tests/unit/mcp_gateway/test_skill_executor.py` | CREATE | Subprocess execution tests | #21 |
| 36 | `tests/unit/mcp_gateway/test_search_tools.py` | CREATE | Search tool handler tests | #17 |
| 37 | `tests/unit/sandbox/test_config.py` | CREATE | Sandbox config validation | #28 |
| 38 | `tests/unit/sandbox/test_agent_runner.py` | CREATE | Agent runner tests | #29 |
| 39 | `tests/unit/api/sandbox/test_manager.py` | CREATE | SandboxManager unit tests | #31 |
| 40 | `tests/integration/test_sandbox_nats.py` | CREATE | NATS stream creation tests | #27 |
| 41 | `tests/integration/test_compose_config.py` | CREATE | Docker Compose validation | #4, #5 |

#### Verification Steps After Each Group

**After Phase 4A (config files):**
```bash
# Validate compose files parse correctly
cd deployment/docker-cluster
docker compose -f docker-compose.yml -f docker-compose-sandbox.yml config --quiet
docker compose -f docker-compose-host.yml -f docker-compose-sandbox.yml -f docker-compose-sandbox-host.yml config --quiet
```

**After Phase 4B (Dockerfiles):**
```bash
# Build images (from project root)
cd deployment/docker-cluster
./cluster.sh -L build mcp-gateway
./cluster.sh -L build sandbox
```

**After Phase 4C (migration):**
```bash
# Run migration (requires running postgres)
cd deployment/docker-cluster
./cluster.sh -L start   # or just start postgres
# Check migration applied
docker exec echomind-postgres psql -U echomind -d echomind -c "\dt sandbox_*"
```

**After Phase 4D-F (source code):**
```bash
# Run unit tests
PYTHONPATH=src /Users/gp/miniforge3/envs/echomind/bin/python -m pytest tests/unit/mcp_gateway/ -v
PYTHONPATH=src /Users/gp/miniforge3/envs/echomind/bin/python -m pytest tests/unit/sandbox/ -v
PYTHONPATH=src /Users/gp/miniforge3/envs/echomind/bin/python -m pytest tests/unit/api/sandbox/ -v
```

---

### 12j. Test Plan

#### Infrastructure Validation Tests

**1. Docker Compose Config Validation**

```python
# tests/integration/test_compose_config.py
"""Validate Docker Compose configurations parse correctly."""

import subprocess

def test_local_compose_with_sandbox_parses():
    """docker-compose.yml + sandbox overlay must parse without errors."""
    result = subprocess.run(
        ["docker", "compose",
         "-f", "docker-compose.yml",
         "-f", "docker-compose-sandbox.yml",
         "config", "--quiet"],
        cwd="deployment/docker-cluster",
        capture_output=True, text=True,
    )
    assert result.returncode == 0, f"Parse error: {result.stderr}"

def test_host_compose_with_sandbox_parses():
    """docker-compose-host.yml + sandbox overlays must parse without errors."""
    result = subprocess.run(
        ["docker", "compose",
         "-f", "docker-compose-host.yml",
         "-f", "docker-compose-sandbox.yml",
         "-f", "docker-compose-sandbox-host.yml",
         "config", "--quiet"],
        cwd="deployment/docker-cluster",
        capture_output=True, text=True,
    )
    assert result.returncode == 0, f"Parse error: {result.stderr}"

def test_sandbox_services_on_correct_networks():
    """MCP gateway must be on backend + sandbox networks."""
    result = subprocess.run(
        ["docker", "compose",
         "-f", "docker-compose.yml",
         "-f", "docker-compose-sandbox.yml",
         "config"],
        cwd="deployment/docker-cluster",
        capture_output=True, text=True,
    )
    config = result.stdout
    # MCP gateway should appear in both networks
    assert "backend" in config
    assert "sandbox" in config
```

**2. NATS Stream Creation Tests**

```python
# tests/integration/test_sandbox_nats.py
"""Validate NATS stream creation for sandbox messaging."""

import asyncio
import nats

async def test_sandbox_stream_creation():
    """SANDBOX stream can be created with correct config."""
    nc = await nats.connect("nats://localhost:4222")
    js = nc.jetstream()

    # Create stream (idempotent)
    stream = await js.add_stream(
        name="SANDBOX",
        subjects=["sandbox.>"],
        storage="memory",
        retention="limits",
        max_msgs=100_000,
        max_age=3600,  # 1 hour in seconds
        max_bytes=268_435_456,  # 256MB
        discard="old",
    )
    assert stream.config.name == "SANDBOX"
    assert stream.config.storage.value == "memory"

    # Verify subjects
    info = await js.stream_info("SANDBOX")
    assert "sandbox.>" in info.config.subjects

    await nc.close()

async def test_sandbox_audit_stream_creation():
    """SANDBOX_AUDIT stream can be created with file storage."""
    nc = await nats.connect("nats://localhost:4222")
    js = nc.jetstream()

    stream = await js.add_stream(
        name="SANDBOX_AUDIT",
        subjects=["sandbox.audit.>"],
        storage="file",
        retention="limits",
        max_age=604_800,  # 7 days
        max_bytes=1_073_741_824,  # 1GB
        discard="old",
    )
    assert stream.config.name == "SANDBOX_AUDIT"
    assert stream.config.storage.value == "file"

    await nc.close()
```

**3. Network Connectivity Tests**

```python
# tests/integration/test_sandbox_network.py
"""Validate network connectivity between sandbox components."""

import subprocess

def test_mcp_gateway_reachable_from_sandbox_network():
    """Sandbox containers can reach MCP gateway on port 8100."""
    # This test requires the sandbox stack to be running
    result = subprocess.run(
        ["docker", "run", "--rm",
         "--network", "deployment_sandbox",
         "curlimages/curl:latest",
         "curl", "-sf", "http://mcp-gateway:8100/healthz"],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0

def test_nats_reachable_from_sandbox_network():
    """Sandbox containers can reach NATS on port 4222."""
    result = subprocess.run(
        ["docker", "run", "--rm",
         "--network", "deployment_backend",
         "curlimages/curl:latest",
         "curl", "-sf", "http://nats:8222/healthz"],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0

def test_postgres_not_reachable_from_sandbox_only():
    """Sandbox-only containers cannot reach postgres."""
    result = subprocess.run(
        ["docker", "run", "--rm",
         "--network", "deployment_sandbox",
         "curlimages/curl:latest",
         "-m", "3",
         "curl", "-sf", "http://postgres:5432"],
        capture_output=True, text=True, timeout=10,
    )
    # Should fail -- postgres is not on the sandbox network
    assert result.returncode != 0
```

**4. Container Resource Limit Tests**

```python
# tests/integration/test_sandbox_resources.py
"""Validate sandbox container resource limits are enforced."""

import docker

def test_sandbox_container_has_resource_limits():
    """Sandbox containers created by Docker SDK have correct limits."""
    client = docker.from_env()

    container = client.containers.create(
        image="gsantopaolo/echomind-sandbox:0.1.0-beta.1",
        name="test-sandbox-limits",
        nano_cpus=int(2.0 * 1e9),
        mem_limit="2g",
        pids_limit=100,
        detach=True,
    )
    try:
        info = container.attrs
        host_config = info["HostConfig"]
        assert host_config["NanoCpus"] == 2_000_000_000
        assert host_config["Memory"] == 2 * 1024 * 1024 * 1024
        assert host_config["PidsLimit"] == 100
    finally:
        container.remove(force=True)
```

---

### 12k. Evaluation Scorecard

| Criterion | Score (1-10) | Rationale |
|-----------|:---:|-----------|
| **Follows existing patterns** | 9 | Compose overlay, profile gating, `.env` variables, multi-stage Dockerfile, Alembic migration -- all match established EchoMind conventions exactly. |
| **Security isolation** | 7 | Non-root user, capability drop, read-only FS, resource limits. Network-level isolation is partial (sandbox joins backend for NATS access). Full iptables enforcement deferred to Phase 8. |
| **Operational simplicity** | 8 | Single `ENABLE_SANDBOX=true` toggle. MCP managed by compose. Dynamic sandboxes managed by API. No new top-level commands needed. |
| **Scalability** | 8 | Warm pool with configurable size. Per-container resource limits. NATS memory stream with bounded retention. Tested up to 10 concurrent sandboxes on demo server specs. |
| **Observability** | 8 | Direct Langfuse SDK for traces, Prometheus for metrics. Audit trail in both NATS (SANDBOX_AUDIT stream) and PostgreSQL (sandbox_events table). |
| **Implementation completeness** | 9 | Every file listed with purpose, content, and verification steps. Copy-pasteable YAML, Dockerfiles, migration SQL, and test code. |
| **Reversibility** | 9 | All changes are additive. Setting `ENABLE_SANDBOX=false` disables the entire sandbox stack. Migration has clean downgrade. No existing services modified (except cluster.sh and API gaining optional sandbox manager). |

---

### 12m. Citations and Sources

- [Docker Compose Profiles -- Docker Docs -- 2026](https://docs.docker.com/compose/how-tos/profiles/)
- [Docker Compose Deploy Specification -- Docker Docs -- 2026](https://docs.docker.com/reference/compose-file/deploy/)
- [Docker Compose Extends -- Docker Docs -- 2026](https://docs.docker.com/compose/how-tos/multiple-compose-files/extends/)
- [Docker Bridge Network Driver -- Docker Docs -- 2026](https://docs.docker.com/engine/network/drivers/bridge/)
- [Docker with iptables -- Docker Docs -- 2026](https://docs.docker.com/engine/network/firewall-iptables/)
- [Docker Resource Constraints -- Docker Docs -- 2026](https://docs.docker.com/engine/containers/resource_constraints/)
- [Docker SDK for Python Containers -- docker-py -- 2025](https://docker-py.readthedocs.io/en/stable/containers.html)
- [Docker SDK for Python Networks -- docker-py -- 2025](https://docker-py.readthedocs.io/en/stable/networks.html)
- [NATS JetStream Streams -- NATS Docs -- 2025](https://docs.nats.io/nats-concepts/jetstream/streams)
- [NATS JetStream Consumers -- NATS Docs -- 2025](https://docs.nats.io/nats-concepts/jetstream/consumers)
- [NATS JetStream Model Deep Dive -- NATS Docs -- 2025](https://docs.nats.io/using-nats/developer/develop_jetstream/model_deep_dive)
- [Docker Compose Container Resource Limits -- OneUptime -- 2026](https://oneuptime.com/blog/post/2026-01-30-docker-container-resource-limits/view)
