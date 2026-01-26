# EchoMind - Agentic RAG Architecture

> Technical specification for EchoMind, a Python-based Agentic Retrieval-Augmented Generation platform.

## Overview

EchoMind is an **Agentic RAG** system that goes beyond traditional retrieve-then-generate patterns. The agent reasons about what information it needs, plans multi-step retrieval strategies, uses external tools, and maintains memory across sessions.

---

## High-Level Architecture

```mermaid
flowchart TB
    subgraph Clients
        WEB[Web App]
        API_CLIENT[API Client]
        BOT[Chat Bot Plugin]
    end

    subgraph EchoMind["EchoMind RAG Cluster"]
        subgraph Auth["Authentication Layer"]
            AUTHENTIK[Authentik<br/>OIDC Provider]
        end

        subgraph Gateway["API Gateway"]
            API[echomind-api<br/>REST + WebSocket]
        end

        subgraph Search["Agentic Search"]
            SEARCH[echomind-search<br/>Semantic Kernel]
        end

        subgraph Ingestion["Document Ingestion"]
            ORCH[echomind-orchestrator<br/>APScheduler]
            CONN[echomind-connector<br/>Teams/Drive/OneDrive]
            SEM[echomind-semantic<br/>Extract + Chunk]
            EMBED[echomind-embedder<br/>Text → Vector]
            VOICE[echomind-voice<br/>Whisper]
            VISION[echomind-vision<br/>BLIP + OCR]
        end

        subgraph Storage["Data Layer"]
            VECTORDB[(Qdrant<br/>Vector DB)]
            RELDB[(PostgreSQL<br/>Metadata)]
            OBJSTORE[(MinIO<br/>File Storage)]
            CACHE[(Redis<br/>Cache + Memory)]
        end

        subgraph Messaging
            NATS[NATS JetStream]
        end
    end

    subgraph Inference["Inference Cluster (Pluggable)"]
        LLM_ROUTER[LLM Router]
        PRIVATE_LLM[Private Inference<br/>TGI/vLLM]
        CLOUD_LLM[Cloud APIs<br/>OpenAI/Anthropic]
    end

    subgraph External["External Data Sources"]
        CONNECTORS_EXT[OneDrive/Teams<br/>GDrive/Web/Files]
    end

    WEB & API_CLIENT & BOT --> AUTHENTIK
    AUTHENTIK -->|JWT Token| API
    API -->|Query| SEARCH
    SEARCH --> VECTORDB
    SEARCH --> LLM_ROUTER
    SEARCH --> CACHE

    ORCH -->|NATS| CONN
    CONN -->|NATS| SEM
    SEM -->|gRPC| EMBED
    SEM -->|NATS| VOICE
    SEM -->|NATS| VISION
    VOICE -->|text| SEM
    VISION -->|text| SEM
    EMBED --> VECTORDB

    CONN --> OBJSTORE
    CONN --> CONNECTORS_EXT
    API --> RELDB

    LLM_ROUTER --> PRIVATE_LLM
    LLM_ROUTER --> CLOUD_LLM
```

> **Authentication Flow**: Clients authenticate with Authentik (OIDC) first, receive a JWT token, then include it in requests to the API Gateway. The gateway validates the token before forwarding to backend services. This follows the [OAuth 2.0 Resource Server pattern](https://www.solo.io/topics/api-gateway/api-gateway-authentication).

---

## Agentic RAG Flow

The key differentiator from traditional RAG: **the agent decides what to retrieve, when, and whether to retrieve at all**. The `echomind-search` service implements this using Semantic Kernel.

```mermaid
sequenceDiagram
    participant U as User
    participant API as echomind-api
    participant S as echomind-search<br/>(Semantic Kernel)
    participant Q as Qdrant
    participant R as Redis
    participant L as LLM Router

    U->>API: User Query (HTTP/WebSocket)
    API->>S: Forward query (gRPC)

    S->>R: Load conversation context
    R-->>S: Short-term + Long-term memory

    S->>S: Think: What info do I need?

    alt Needs retrieval
        S->>Q: Execute retrieval strategy
        Q-->>S: Retrieved chunks + scores
        S->>S: Evaluate: sufficient?

        opt Needs more context
            S->>Q: Refined query
            Q-->>S: Additional chunks
        end
    end

    alt Needs tool execution
        S->>S: Execute tool (calculator, web, etc)
    end

    S->>L: Generate response with context
    L-->>S: Streamed tokens
    S->>R: Update memory
    S-->>API: Stream response
    API-->>U: Stream to client
```

---

## Agent Planning Loop

```mermaid
flowchart LR
    subgraph Planning["Agent Planning"]
        THINK[Think:<br/>What do I need?]
        ACT[Act:<br/>Retrieve/Tool/Generate]
        OBSERVE[Observe:<br/>Evaluate results]
        REFLECT[Reflect:<br/>Is this sufficient?]
    end

    THINK --> ACT
    ACT --> OBSERVE
    OBSERVE --> REFLECT
    REFLECT -->|No, need more| THINK
    REFLECT -->|Yes, respond| RESPOND[Generate Final Response]
```

---

## Data Ingestion Pipeline

```mermaid
flowchart LR
    subgraph Sources["Data Sources"]
        FILE[File Upload]
        URL[Web URL]
        DRIVE[OneDrive/GDrive]
        TEAMS[Teams/Slack]
        AUDIO[Audio Files]
        IMAGE[Images/Videos]
    end

    subgraph Trigger["Scheduling"]
        ORCH[echomind-orchestrator]
    end

    subgraph Fetch["Data Fetching"]
        CONN[echomind-connector]
    end

    subgraph Processing["Content Processing"]
        SEM[echomind-semantic<br/>Extract + Chunk]
        VOICE[echomind-voice<br/>Whisper]
        VISION[echomind-vision<br/>BLIP + OCR]
        EMBED[echomind-embedder]
    end

    subgraph Storage["Storage"]
        MINIO[(MinIO)]
        QDRANT[(Qdrant)]
        PG[(PostgreSQL)]
    end

    FILE & URL & DRIVE & TEAMS --> ORCH
    ORCH -->|NATS| CONN
    CONN --> MINIO
    CONN -->|NATS| SEM

    AUDIO --> VOICE
    IMAGE --> VISION
    VOICE -->|transcript| SEM
    VISION -->|description| SEM

    SEM -->|gRPC| EMBED
    EMBED --> QDRANT
    CONN --> PG

    style SEM fill:#f96,stroke:#333
    style EMBED fill:#f96,stroke:#333
    style VOICE fill:#e1f5fe,stroke:#333
    style VISION fill:#e1f5fe,stroke:#333
```

### File Type Routing

| File Type | Route | Processing |
|-----------|-------|------------|
| PDF, DOCX, XLS, MD | Semantic | pymupdf4llm → Markdown → Chunk → Embed |
| URL | Semantic | BS4/Selenium → Text → Chunk → Embed |
| YouTube | Semantic | youtube_transcript_api → Text → Chunk → Embed |
| MP3, WAV, MP4 (audio) | Voice → Semantic | Whisper → Transcript → Chunk → Embed |
| JPEG, PNG (standalone) | Vision → Semantic | BLIP + OCR → Description → Chunk → Embed |
| Video (MP4, etc.) | Vision → Semantic | Frame extraction → BLIP → Description → Chunk → Embed |
| Images in PDF/DOCX | Semantic (LLM) | Handled natively by vision-capable LLM (TBD) |

### Document Processing States

```mermaid
stateDiagram-v2
    [*] --> Pending: Document received
    Pending --> Downloading: Connector fetches
    Downloading --> Extracting: Content extraction
    Extracting --> Chunking: Semantic split
    Chunking --> Embedding: Generate vectors
    Embedding --> Complete: Stored in Qdrant

    Downloading --> Failed: Download error
    Extracting --> Failed: Parse error
    Chunking --> Failed: Split error
    Embedding --> Failed: Embed error

    Failed --> Pending: Retry
```

---

## Vector Collection Strategy

Per-user, per-group, and per-org collections enable scoped retrieval. See [Proto Definitions - ConnectorScope](./proto-definitions.md#connectorscope) for scope values.

```mermaid
flowchart TB
    subgraph Collections["Qdrant Collections"]
        ORG[org]
        GRP1[group_engineering]
        GRP2[group_sales]
        USR1[user_42]
        USR2[user_99]
    end

    subgraph Query["Query Scope"]
        Q[User Query]
    end

    Q -->|Personal docs| USR1
    Q -->|Team docs| GRP1
    Q -->|Company docs| ORG

    style ORG fill:#e1f5fe
    style GRP1 fill:#fff3e0
    style GRP2 fill:#fff3e0
    style USR1 fill:#e8f5e9
    style USR2 fill:#e8f5e9
```

| Scope | Collection Pattern | Example |
|-------|-------------------|---------|
| `user` | `user_{user_id}` | `user_42` |
| `group` | `group_{scope_id}` | `group_engineering` |
| `org` | `org` | `org` |

---

## Memory Architecture

```mermaid
flowchart TB
    subgraph Memory["Agent Memory"]
        subgraph ShortTerm["Short-Term Memory"]
            CONV[Conversation Buffer]
            WORKING[Working Memory<br/>Current task context]
        end

        subgraph LongTerm["Long-Term Memory"]
            EPISODIC[Episodic Memory<br/>Past interactions]
            SEMANTIC[Semantic Memory<br/>Learned facts]
            PROCEDURAL[Procedural Memory<br/>Successful patterns]
        end
    end

    subgraph Storage
        REDIS[(Redis)]
        PG[(PostgreSQL)]
        QDRANT[(Qdrant)]
    end

    CONV --> REDIS
    WORKING --> REDIS
    EPISODIC --> PG
    SEMANTIC --> QDRANT
    PROCEDURAL --> PG
```

---

## Tool System

The agent can invoke tools during reasoning:

```mermaid
flowchart LR
    subgraph Tools["Available Tools"]
        SEARCH[Vector Search]
        WEB[Web Search]
        CODE[Code Executor]
        API[External APIs]
        CALC[Calculator]
        FILE[File Operations]
    end

    AGENT[Agent] --> ROUTER[Tool Router]
    ROUTER --> SEARCH & WEB & CODE & API & CALC & FILE

    SEARCH --> RESULT[Tool Result]
    WEB --> RESULT
    CODE --> RESULT
    API --> RESULT
    CALC --> RESULT
    FILE --> RESULT

    RESULT --> AGENT
```

---

## Service Architecture

```mermaid
flowchart TB
    subgraph Query["Query Path (Synchronous)"]
        API_SVC[echomind-api<br/>FastAPI + WebSocket]
        SEARCH_SVC[echomind-search<br/>Semantic Kernel + gRPC]
    end

    subgraph Ingestion["Ingestion Path (Asynchronous)"]
        ORCH_SVC[echomind-orchestrator<br/>APScheduler]
        CONN_SVC[echomind-connector<br/>NATS Consumer]
        SEM_SVC[echomind-semantic<br/>NATS Consumer]
        EMBED_SVC[echomind-embedder<br/>gRPC]
        VOICE_SVC[echomind-voice<br/>NATS Consumer]
        VISION_SVC[echomind-vision<br/>NATS Consumer]
    end

    subgraph Infra["Infrastructure"]
        NATS[NATS JetStream]
        PG[(PostgreSQL)]
        QDRANT[(Qdrant)]
        REDIS[(Redis)]
        MINIO[(MinIO)]
    end

    API_SVC -->|gRPC| SEARCH_SVC
    SEARCH_SVC --> QDRANT
    SEARCH_SVC --> REDIS

    ORCH_SVC -->|NATS pub| NATS
    NATS -->|NATS sub| CONN_SVC
    CONN_SVC -->|NATS pub| NATS
    NATS -->|NATS sub| SEM_SVC
    SEM_SVC -->|gRPC| EMBED_SVC
    SEM_SVC -->|NATS pub| NATS
    NATS -->|NATS sub| VOICE_SVC
    NATS -->|NATS sub| VISION_SVC

    EMBED_SVC --> QDRANT
    CONN_SVC --> MINIO
    CONN_SVC --> PG
    API_SVC --> PG
    ORCH_SVC --> PG
```

### Services Reference

| Service | Protocol | Port | Purpose |
|---------|----------|------|---------|
| **echomind-api** | HTTP/WebSocket | 8080 | REST API gateway, WebSocket streaming, serves web client |
| **echomind-search** | gRPC | 50051 | Agentic search powered by Semantic Kernel. Handles query planning, multi-step retrieval, tool execution, memory management, and LLM response generation. **Note:** Reranker may become a separate service in the future. |
| **echomind-orchestrator** | NATS (pub) | 8080 | APScheduler-based service that monitors connectors and triggers sync jobs via NATS. See [orchestrator-service.md](./services/orchestrator-service.md). |
| **echomind-connector** | NATS (sub) | 8080 | Fetches data from external sources (Teams, OneDrive, Google Drive). Handles OAuth, delta sync, and file download to MinIO. |
| **echomind-semantic** | NATS (sub) | 8080 | Content extraction and text chunking. Uses pymupdf4llm for PDFs, BS4/Selenium for URLs. Supports configurable chunking strategies (character-based or semantic). |
| **echomind-embedder** | gRPC | 50051 | Generates vector embeddings using SentenceTransformers. Supports model caching. |
| **echomind-voice** | NATS (sub) | 8080 | Whisper-based audio transcription for audio files (MP3, WAV). Outputs transcript to semantic service. |
| **echomind-vision** | NATS (sub) | 8080 | BLIP image captioning + OCR for standalone images and video frame extraction. Outputs descriptions to semantic service. |
| **echomind-migration** | Batch job | - | Alembic-based database schema versioning. Runs before service startup. |

### NATS Subjects

| Subject | Publisher | Consumer | Payload |
|---------|-----------|----------|---------|
| `connector.sync.{type}` | orchestrator | connector | `ConnectorSyncRequest` |
| `document.process` | connector | semantic | `DocumentProcessRequest` |
| `audio.transcribe` | semantic | voice | `AudioTranscribeRequest` |
| `image.analyze` | semantic | vision | `ImageAnalyzeRequest` |

**Proto Messages:** See [Proto Definitions](./proto-definitions.md#internal-proto-definitions) for payload schemas.

---

## Tech Stack

| Layer | Technology | Rationale |
|-------|------------|-----------|
| **API** | FastAPI + WebSocket | Async, streaming, OpenAPI docs |
| **Agent Framework** | Semantic Kernel | Microsoft's AI orchestration SDK, air-gap compatible, Python native |
| **Embeddings** | SentenceTransformers | Local, configurable per cluster |
| **Vector DB** | Qdrant | High-performance, HNSW indexes, rich filtering, Rust-based |
| **Relational DB** | PostgreSQL | Reliable, JSONB support |
| **Cache/Memory** | Redis | Fast, pub/sub, streams |
| **Object Storage** | MinIO ⚠️ | S3-compatible, self-hosted (see warning below) |
| **Message Queue** | NATS JetStream | Lightweight, persistent |
| **LLM Private** | TGI / vLLM | Production-grade inference, GPU optimized |
| **LLM Cloud** | OpenAI / Anthropic | Optional, for connected deployments |
| **Auth** | Authentik | SSO, OIDC, self-hosted, inside cluster |
| **Observability** | OpenTelemetry + Grafana | Traces, metrics, logs |

### ⚠️ Object Storage Warning: MinIO

> **Warning**: MinIO is currently under maintenance mode and is not accepting new changes. This may impact long-term support and security updates.

**Recommended Alternative**: [RustFS](https://github.com/rustfs/rustfs) - A high-performance, S3-compatible object storage written in Rust. Benefits:
- Active development
- Rust-based (memory safe, high performance)
- S3-compatible API
- Better suited for air-gapped deployments

**Decision**: Evaluate RustFS as primary object storage. If not mature enough for v1, use MinIO with migration path to RustFS planned.

---

### Flexible Deployment: Cloud, Hybrid, or Air-Gapped

EchoMind is designed to run anywhere—from public cloud to the most restricted environments. Whether you're deploying in AWS/Azure/GCP, a private data center, or a fully air-gapped SCIF facility, EchoMind adapts to your security requirements.

| Deployment Mode | Description |
|-----------------|-------------|
| **Cloud** | Full SaaS experience with cloud LLMs (OpenAI, Anthropic) and managed services |
| **Hybrid** | Private RAG cluster with optional cloud LLM fallback |
| **Air-Gapped** | Fully disconnected, meets SCIF standards, zero external dependencies |

#### Air-Gapped Compliance

For classified networks and air-gapped data centers, EchoMind provides:

| Requirement | Solution |
|-------------|----------|
| No internet access | All dependencies pre-packaged, offline container images |
| No telemetry/phone-home | Semantic Kernel runs fully offline, no hidden network calls |
| Private LLM inference | TGI/vLLM with pre-downloaded models |
| Local embeddings | SentenceTransformers with cached models |
| Self-contained auth | Authentik inside cluster, LDAP/AD integration |
| Audit compliance | Full request/response logging, no data exfiltration |

### Why Semantic Kernel

[Semantic Kernel](https://github.com/microsoft/semantic-kernel) is Microsoft's open-source AI orchestration SDK:

- **Air-gap compatible**: No telemetry, no phone-home, works fully offline
- **Python native**: First-class Python support alongside C# and Java
- **Pluggable connectors**: Easy to swap LLM providers (local or cloud)
- **Memory & planning**: Built-in support for agent memory and multi-step planning
- **Enterprise-ready**: Backed by Microsoft, used in production at scale
- **Auditable**: Clean dependency tree, no hidden LangChain-style network calls

### Embedding Model Configuration

Embedding model is **cluster-wide** and configured via environment variables:

```bash
# .env or ConfigMap
ECHOMIND_EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-mpnet-base-v2
ECHOMIND_EMBEDDING_DIMENSION=768
```

**Important**: Changing the embedding model requires:
1. Delete all vectors from Qdrant
2. Mark all documents as `pending`
3. Re-scan all data sources
4. Re-embed all documents

This is enforced at startup: if model config changes, system blocks until admin confirms re-indexing.

### Chunking Configuration (Semantic Service)

The semantic service supports configurable chunking strategies:

```bash
# .env or ConfigMap
SEMANTIC_CHUNK_STRATEGY=character          # character | semantic
SEMANTIC_CHUNK_SIZE=1000                   # Characters per chunk
SEMANTIC_CHUNK_OVERLAP=200                 # Overlap between chunks
SEMANTIC_CHUNK_MODEL=sentence-transformers/all-MiniLM-L6-v2  # For semantic chunking
```

| Strategy | Description | Use Case |
|----------|-------------|----------|
| **character** | RecursiveCharacterTextSplitter, splits on paragraph/sentence boundaries | Default, fast, predictable |
| **semantic** | ML-based, uses embedding similarity to find natural breakpoints | Better coherence, higher compute cost |

---

## Deployment Modes

### Single Container (Development)

```mermaid
flowchart LR
    subgraph Container["echomind:latest"]
        ALL[All Services<br/>+ Embedded DBs]
    end

    USER[User] --> Container
```

### Docker Compose (Small Scale)

```mermaid
flowchart TB
    subgraph Compose["docker-compose.yml"]
        subgraph Services["Application Services"]
            API[echomind-api]
            SEARCH[echomind-search]
            ORCH[echomind-orchestrator]
            CONN[echomind-connector]
            SEM[echomind-semantic]
            EMBED[echomind-embedder]
            VOICE[echomind-voice]
            VISION[echomind-vision]
        end

        subgraph Infra["Infrastructure"]
            PG[postgres]
            QDRANT[qdrant]
            REDIS[redis]
            MINIO[minio]
            NATS[nats]
        end
    end
```

### Kubernetes (Production)

```mermaid
flowchart TB
    subgraph K8s["Kubernetes Cluster"]
        subgraph Deployments["Deployments (Stateless)"]
            API[echomind-api<br/>HPA enabled]
            SEARCH[echomind-search<br/>HPA enabled]
            ORCH[echomind-orchestrator<br/>Single replica]
            CONN[echomind-connector]
            SEM[echomind-semantic]
            EMBED[echomind-embedder<br/>GPU node]
            VOICE[echomind-voice<br/>GPU node]
            VISION[echomind-vision<br/>GPU node]
        end

        subgraph StatefulSets["StatefulSets (Persistent)"]
            PG[PostgreSQL]
            QDRANT[Qdrant]
            REDIS[Redis]
            MINIO[MinIO]
            NATS[NATS]
        end

        subgraph Jobs["Jobs"]
            MIG[echomind-migration<br/>Pre-deploy hook]
        end

        subgraph Ingress
            ING[Traefik Ingress<br/>Rate Limiting]
        end
    end

    ING --> API
    MIG -.->|"runs before"| Deployments
```

---

## Directory Structure

```
echomind/
├── docs/                    # Documentation
│   ├── architecture.md      # This file
│   └── services/            # Service-specific docs
├── src/
│   ├── api/                 # FastAPI REST + WebSocket gateway
│   │   ├── routes/
│   │   ├── middleware/
│   │   └── websocket/
│   ├── services/            # Background services
│   │   ├── search/          # Agentic search (Semantic Kernel, gRPC)
│   │   │   ├── logic/       # SK plugins, tools, memory
│   │   │   └── main.py
│   │   ├── orchestrator/    # Scheduler service (APScheduler, NATS pub)
│   │   │   ├── logic/
│   │   │   │   └── jobs/    # connector_sync.py, cleanup.py
│   │   │   └── main.py
│   │   ├── connector/       # Data source connector (NATS sub)
│   │   │   ├── logic/
│   │   │   │   └── providers/  # onedrive.py, teams.py, gdrive.py
│   │   │   └── main.py
│   │   ├── semantic/        # Content extraction + chunking (NATS sub)
│   │   │   ├── logic/
│   │   │   │   ├── extractors/  # pdf.py, url.py, youtube.py
│   │   │   │   └── chunkers/    # character.py, semantic.py
│   │   │   └── main.py
│   │   ├── embedder/        # Text → Vector (gRPC)
│   │   │   ├── logic/
│   │   │   └── main.py
│   │   ├── voice/           # Whisper transcription (NATS sub)
│   │   │   ├── logic/
│   │   │   └── main.py
│   │   ├── vision/          # BLIP + OCR (NATS sub)
│   │   │   ├── logic/
│   │   │   └── main.py
│   │   └── migration/       # Alembic migrations (batch job)
│   │       └── versions/
│   ├── proto/               # Protocol Buffer definitions (source of truth)
│   │   ├── public/          # Client-facing API objects
│   │   └── internal/        # Internal service objects
│   ├── echomind_lib/        # SHARED LIBRARY
│   │   ├── db/              # Database clients
│   │   │   ├── models/      # SQLAlchemy ORM models
│   │   │   ├── postgres.py
│   │   │   ├── qdrant.py
│   │   │   └── nats_*.py
│   │   ├── helpers/         # Utility code
│   │   └── models/          # AUTO-GENERATED (from proto)
│   └── web/                 # React client
├── deployment/
│   ├── docker/
│   │   ├── Dockerfile.*     # Per-service Dockerfiles
│   │   └── docker-compose.yml
│   └── k8s/
│       ├── base/            # Kustomize base
│       └── overlays/        # dev, staging, prod
├── config/                  # Configuration files
├── tests/
└── scripts/
```

---

## Next Steps

1. **Phase 1**: Core infrastructure (API, DB connections, auth)
2. **Phase 2**: Document ingestion pipeline (connectors, chunking, embedding)
3. **Phase 3**: Basic RAG (search, retrieval, generation)
4. **Phase 4**: Agent capabilities (planning, memory, tools)
5. **Phase 5**: Production hardening (observability, scaling)

---

## Future Vision

### Agentic Ingestion Pipeline

Future enhancement: use an LLM to reason about documents during ingestion, not just retrieval.

```mermaid
flowchart LR
    DOC[Document] --> AGENT_INGEST[Ingestion Agent]
    AGENT_INGEST --> CLASSIFY[Classify content type]
    AGENT_INGEST --> EXTRACT[Extract entities & relationships]
    AGENT_INGEST --> SUMMARIZE[Generate summaries]
    AGENT_INGEST --> LINK[Link to existing knowledge]
    CLASSIFY & EXTRACT & SUMMARIZE & LINK --> STORE[Store enriched chunks]
```

Benefits:
- Automatic document classification and tagging
- Entity extraction and knowledge graph building
- Multi-level summaries (document, section, paragraph)
- Cross-document relationship discovery

### Real-Time Voice (Future)

Current scope: audio file transcription (batch processing).

Future scope: real-time voice streaming for live conversations:
- WebSocket audio streaming to voice service
- Live transcription with speaker diarization
- Real-time agent responses via voice synthesis
- Use case: voice-enabled AI assistant in Teams calls

### Reranker Service (TBD)

May extract reranking into a separate service if:
- Cross-encoder models prove computationally expensive
- Need to A/B test different reranking strategies
- Want to cache reranking results independently

Current approach: reranking logic lives in `echomind-search` service.

---

## Decisions Made

- [x] **Agent framework**: Semantic Kernel (Microsoft's AI orchestration SDK, air-gap compatible)
- [x] **Vector database**: Qdrant (high-performance, HNSW, rich filtering)
- [x] **Embedding model**: Cluster-wide config via env vars, requires re-index on change
- [x] **Deployment targets**: Single container, Docker Compose, Kubernetes
- [x] **Deployment modes**: Cloud, Hybrid, or Air-Gapped (SCIF compliant)
- [x] **LLM strategy**: Private inference (TGI/vLLM), cloud optional for connected envs
- [x] **Auth**: Authentik (self-hosted, OIDC/LDAP, inside RAG cluster)
- [x] **Tenancy**: Single-tenant with per-user/group/org vector collections

## Open Questions

- [ ] Memory persistence strategy (how long to retain episodic memory?) — **TBD**
- [ ] Reranker: Keep in `echomind-search` or extract to separate `echomind-reranker` service? — **TBD, see Future Vision**
- [ ] Object storage selection: MinIO (maintenance mode) vs [RustFS](https://github.com/rustfs/rustfs) — **Evaluate**
- [ ] Stuck connector handling: Should orchestrator reset connectors stuck in PENDING/SYNCING? — **TBD, see [orchestrator-service.md](./services/orchestrator-service.md)**
- [ ] Video audio extraction: Process in vision service or route to voice service? — **TBD, depends on model**

## Resolved

- [x] **Offline dependency bundling**: Docker images from authorized container registries, deployable to [Iron Bank (Platform One)](https://p1.dso.mil/iron-bank)
- [x] **Connector priority for v1**: Microsoft Teams, Google Drive

---

## References

- [Proto Definitions](./proto-definitions.md) - Enum values, message schemas, NATS payloads
- [DB Schema](./db-schema.md) - PostgreSQL table definitions
- [API Specification](./api-spec.md) - REST/WebSocket endpoints
- [Orchestrator Service](./services/orchestrator-service.md) - Scheduler service details
