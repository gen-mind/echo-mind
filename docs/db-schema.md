# EchoMind Database Schema

> PostgreSQL schema definitions for EchoMind.

---

## Overview

EchoMind uses PostgreSQL for relational data (metadata, configuration, audit logs). Vector embeddings are stored in Qdrant.

**Migration Tool:** Alembic (via `echomind-migration` service)

---

## Core Tables

### users

User accounts synced from Authentik (OIDC).

```sql
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    external_id VARCHAR(255) UNIQUE NOT NULL,  -- Authentik UUID
    email VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255),
    groups TEXT[],                              -- From JWT claims
    roles TEXT[],                               -- From JWT claims
    preferences JSONB DEFAULT '{}',
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_users_email ON users (email);
CREATE INDEX idx_users_external_id ON users (external_id);
```

| Column | Type | Description |
|--------|------|-------------|
| `external_id` | VARCHAR | Authentik user UUID |
| `groups` | TEXT[] | Group memberships for scoped access |
| `preferences` | JSONB | UI settings, default assistant, etc. |

---

### connectors

Data source configurations with sync state.

```sql
CREATE TABLE connectors (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    type VARCHAR(50) NOT NULL,                  -- See ConnectorType enum
    status VARCHAR(50) NOT NULL DEFAULT 'active',  -- See ConnectorStatus enum
    scope VARCHAR(50) NOT NULL DEFAULT 'user',  -- See ConnectorScope enum
    scope_id VARCHAR(255),                      -- Group name if scope='group'
    config JSONB NOT NULL DEFAULT '{}',         -- OAuth tokens, folder IDs
    state JSONB NOT NULL DEFAULT '{}',          -- Delta cursors, pagination
    refresh_freq_minutes INT,                   -- NULL = manual only
    last_sync_at TIMESTAMP,
    docs_analyzed INT DEFAULT 0,
    created_by INT NOT NULL REFERENCES users(id),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_connectors_status ON connectors (status);
CREATE INDEX idx_connectors_type ON connectors (type);
CREATE INDEX idx_connectors_created_by ON connectors (created_by);
CREATE INDEX idx_connectors_scope ON connectors (scope, scope_id);
```

| Column | Type | Description |
|--------|------|-------------|
| `type` | VARCHAR | `teams`, `google_drive`, `onedrive`, `web`, `file` |
| `status` | VARCHAR | `pending`, `syncing`, `active`, `error`, `disabled` |
| `scope` | VARCHAR | `user`, `group`, `org` — determines Qdrant collection |
| `config` | JSONB | Encrypted OAuth tokens, folder paths, credentials |
| `state` | JSONB | Sync cursors for delta/incremental updates |
| `refresh_freq_minutes` | INT | Sync interval; NULL for manual-only (file uploads) |

**Status Values:** See [Proto Definitions](./proto-definitions.md#connectorstatus)

---

### documents

Indexed documents from connectors.

```sql
CREATE TABLE documents (
    id SERIAL PRIMARY KEY,
    connector_id INT NOT NULL REFERENCES connectors(id) ON DELETE CASCADE,
    parent_id INT REFERENCES documents(id),     -- For hierarchical docs
    source_id VARCHAR(255) NOT NULL,            -- External ID (Drive file ID, etc.)
    url VARCHAR(2048) NOT NULL,                 -- MinIO path: minio:bucket:key
    original_url VARCHAR(2048),                 -- Source URL for reference
    title VARCHAR(512),
    content_type VARCHAR(100),                  -- MIME type
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    chunk_count INT DEFAULT 0,
    chunking_session VARCHAR(36),               -- Batch tracking UUID
    error_message TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),

    UNIQUE (connector_id, source_id)
);

CREATE INDEX idx_documents_connector ON documents (connector_id);
CREATE INDEX idx_documents_status ON documents (status);
CREATE INDEX idx_documents_source_id ON documents (source_id);
CREATE INDEX idx_documents_chunking_session ON documents (chunking_session);
```

| Column | Type | Description |
|--------|------|-------------|
| `source_id` | VARCHAR | External system ID (Drive file ID, Teams message ID) |
| `url` | VARCHAR | MinIO storage path: `minio:documents:abc123.pdf` |
| `status` | VARCHAR | `pending`, `processing`, `completed`, `failed` |
| `chunking_session` | VARCHAR | UUID linking all docs from same sync batch |

---

### assistants

AI assistant personas with custom prompts.

```sql
CREATE TABLE assistants (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    llm_id INT REFERENCES llms(id),
    system_prompt TEXT NOT NULL,
    task_prompt TEXT NOT NULL,                  -- Contains {context} and {query} placeholders
    starter_messages TEXT[],
    is_default BOOLEAN DEFAULT FALSE,
    is_visible BOOLEAN DEFAULT TRUE,
    created_by INT REFERENCES users(id),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_assistants_is_default ON assistants (is_default) WHERE is_default = TRUE;
```

| Column | Type | Description |
|--------|------|-------------|
| `system_prompt` | TEXT | Personality and behavior instructions |
| `task_prompt` | TEXT | Template with `{context}` and `{query}` placeholders |
| `starter_messages` | TEXT[] | Suggested conversation starters |

---

### llms

LLM provider configurations.

```sql
CREATE TABLE llms (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    provider VARCHAR(50) NOT NULL,              -- See LLMProvider enum
    model_id VARCHAR(255) NOT NULL,             -- e.g., mistralai/Mistral-7B-Instruct-v0.2
    endpoint VARCHAR(512),                      -- URL for TGI/vLLM/Ollama
    api_key_encrypted BYTEA,                    -- Encrypted API key for cloud providers
    max_tokens INT DEFAULT 4096,
    temperature FLOAT DEFAULT 0.7,
    is_default BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_llms_is_default ON llms (is_default) WHERE is_default = TRUE;
```

| Column | Type | Description |
|--------|------|-------------|
| `provider` | VARCHAR | `tgi`, `vllm`, `openai`, `anthropic`, `ollama` |
| `endpoint` | VARCHAR | Required for private inference (TGI/vLLM/Ollama) |
| `api_key_encrypted` | BYTEA | Encrypted; required for OpenAI/Anthropic |

**Provider Values:** See [Proto Definitions](./proto-definitions.md#llmprovider)

---

### embedding_models

Cluster-wide embedding model configuration.

```sql
CREATE TABLE embedding_models (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    model_id VARCHAR(255) NOT NULL,             -- SentenceTransformer model name
    dimension INT NOT NULL,                     -- Vector dimension (e.g., 768)
    is_active BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Only one active model allowed
CREATE UNIQUE INDEX idx_embedding_models_active ON embedding_models (is_active) WHERE is_active = TRUE;
```

**Warning:** Changing the active embedding model requires re-indexing all documents.

---

### chat_sessions

Conversation threads.

```sql
CREATE TABLE chat_sessions (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    assistant_id INT REFERENCES assistants(id),
    title VARCHAR(255),
    mode VARCHAR(50) NOT NULL DEFAULT 'chat',   -- See ChatMode enum
    message_count INT DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_chat_sessions_user ON chat_sessions (user_id, updated_at DESC);
```

| Column | Type | Description |
|--------|------|-------------|
| `mode` | VARCHAR | `chat` (RAG + LLM) or `search` (vector search only) |

---

### chat_messages

Individual messages within sessions.

```sql
CREATE TABLE chat_messages (
    id SERIAL PRIMARY KEY,
    session_id INT NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL,                  -- See MessageRole enum
    content TEXT NOT NULL,
    rephrased_query TEXT,                       -- Query rewriting for better retrieval
    token_count INT,
    sources JSONB,                              -- Retrieved chunks with scores
    feedback VARCHAR(20),                       -- 'positive', 'negative', NULL
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_chat_messages_session ON chat_messages (session_id, created_at);
```

| Column | Type | Description |
|--------|------|-------------|
| `role` | VARCHAR | `user`, `assistant`, `system` |
| `sources` | JSONB | `[{document_id, chunk_id, score}, ...]` |
| `feedback` | VARCHAR | User thumbs up/down for RLHF |

---

## Scheduler Tables

### apscheduler_jobs

APScheduler job store (auto-created).

```sql
-- Created automatically by APScheduler SQLAlchemyJobStore
CREATE TABLE apscheduler_jobs (
    id VARCHAR(191) PRIMARY KEY,
    next_run_time FLOAT,
    job_state BYTEA NOT NULL
);

CREATE INDEX ix_apscheduler_jobs_next_run_time ON apscheduler_jobs (next_run_time);
```

---

### scheduler_runs

Audit log for scheduler job executions.

```sql
CREATE TABLE scheduler_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_name VARCHAR(100) NOT NULL,
    connector_id INT REFERENCES connectors(id),
    started_at TIMESTAMP NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMP,
    status VARCHAR(20) NOT NULL,                -- 'running', 'completed', 'failed'
    error_message TEXT,
    documents_triggered INT DEFAULT 0
);

CREATE INDEX idx_scheduler_runs_connector ON scheduler_runs (connector_id, started_at DESC);
CREATE INDEX idx_scheduler_runs_status ON scheduler_runs (status);
```

---

## Qdrant Collections

Vector embeddings are stored in Qdrant, not PostgreSQL.

### Collection Naming

| Scope | Collection Name | Example |
|-------|-----------------|---------|
| User | `user_{user_id}` | `user_42` |
| Group | `group_{scope_id}` | `group_engineering` |
| Organization | `org` | `org` |

### Vector Schema

```python
# Qdrant collection configuration
{
    "vectors": {
        "size": 768,  # From embedding model dimension
        "distance": "Cosine"
    }
}

# Point payload structure
{
    "document_id": 123,
    "chunk_index": 0,
    "content": "The quarterly revenue...",
    "title": "Q4 Report.pdf",
    "connector_id": 5,
    "chunking_session": "uuid-here",
    "created_at": "2025-01-20T10:00:00Z"
}
```

---

## Migrations

```bash
# Create new migration
alembic revision --autogenerate -m "Add new table"

# Apply migrations
alembic upgrade head

# Rollback one version
alembic downgrade -1
```

**Service:** `echomind-migration` runs `alembic upgrade head` as a Kubernetes pre-deploy hook.

---

## References

- [Proto Definitions](./proto-definitions.md) - Enum values and message types
- [API Specification](./api-spec.md) - REST/WebSocket endpoints
- [Architecture](./architecture.md) - System overview
