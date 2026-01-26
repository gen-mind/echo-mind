# EchoMind Protocol Buffer Definitions

> **Source of Truth** for all data models across EchoMind services.

---

## Overview

All data models are defined in Protocol Buffers (`.proto` files). The CI pipeline generates:
- **Pydantic models** for Python backend (`echomind_lib/models/`)
- **TypeScript types** for web client (`src/web/src/models/`)

**Never hand-write models.** Edit `.proto` files and run `make gen-proto`.

---

## Directory Structure

```
src/proto/
├── public/              # Client-facing API objects
│   ├── user.proto
│   ├── connector.proto
│   ├── document.proto
│   ├── chat.proto
│   ├── llm.proto
│   ├── embedding_model.proto
│   └── assistant.proto
├── internal/            # Internal service communication
│   ├── scheduler.proto  # Orchestrator messages
│   ├── semantic.proto   # Document processing
│   ├── embedding.proto  # Embedding requests
│   ├── voice.proto      # Audio transcription
│   └── vision.proto     # Image analysis
└── common.proto         # Shared types (pagination, enums)
```

---

## Public Proto Definitions

### ConnectorType

Defines supported data source types.

```protobuf
// src/proto/public/connector.proto

enum ConnectorType {
    CONNECTOR_TYPE_UNSPECIFIED = 0;
    CONNECTOR_TYPE_TEAMS = 1;        // Microsoft Teams
    CONNECTOR_TYPE_GOOGLE_DRIVE = 2; // Google Drive
    CONNECTOR_TYPE_ONEDRIVE = 3;     // Microsoft OneDrive
    CONNECTOR_TYPE_WEB = 4;          // Web URL crawler
    CONNECTOR_TYPE_FILE = 5;         // Direct file upload
}
```

| Type | Service | Behavior |
|------|---------|----------|
| `teams` | echomind-connector | Incremental sync (new messages) |
| `google_drive` | echomind-connector | Delta sync (changed files) |
| `onedrive` | echomind-connector | Delta sync (changed files) |
| `web` | echomind-semantic | Full re-crawl |
| `file` | echomind-semantic | One-time upload, manual only |

---

### ConnectorStatus

Lifecycle states for connectors.

```protobuf
// src/proto/public/connector.proto

enum ConnectorStatus {
    CONNECTOR_STATUS_UNSPECIFIED = 0;
    CONNECTOR_STATUS_PENDING = 1;    // Queued for sync
    CONNECTOR_STATUS_SYNCING = 2;    // Currently processing
    CONNECTOR_STATUS_ACTIVE = 3;     // Ready, sync complete
    CONNECTOR_STATUS_ERROR = 4;      // Failed, can retry
    CONNECTOR_STATUS_DISABLED = 5;   // User disabled
}
```

**Status Flow:**

```
[New] → ACTIVE → PENDING → SYNCING → ACTIVE (success)
                                   → ERROR (failure) → PENDING (retry)
       ACTIVE → DISABLED (user action)
```

| Status | Who Sets | Allows Scheduling |
|--------|----------|-------------------|
| `pending` | Orchestrator | No (already queued) |
| `syncing` | Connector/Semantic | No (in progress) |
| `active` | Semantic (success) | Yes |
| `error` | Any service (failure) | Yes (retry) |
| `disabled` | User | No |

---

### ConnectorScope

Determines which Qdrant collection stores the vectors.

```protobuf
// src/proto/public/connector.proto

enum ConnectorScope {
    CONNECTOR_SCOPE_UNSPECIFIED = 0;
    CONNECTOR_SCOPE_USER = 1;   // Personal: user_{user_id}
    CONNECTOR_SCOPE_GROUP = 2;  // Team: group_{scope_id}
    CONNECTOR_SCOPE_ORG = 3;    // Organization-wide: org
}
```

**Collection Name Resolution:**

```python
def get_collection_name(user_id: int, scope: str, scope_id: str | None) -> str:
    match scope:
        case "user":
            return f"user_{user_id}"
        case "group":
            return f"group_{scope_id}"
        case "org":
            return "org"
```

---

### DocumentStatus

Lifecycle states for documents during ingestion.

```protobuf
// src/proto/public/document.proto

enum DocumentStatus {
    DOCUMENT_STATUS_UNSPECIFIED = 0;
    DOCUMENT_STATUS_PENDING = 1;     // Queued for processing
    DOCUMENT_STATUS_PROCESSING = 2;  // Being extracted/chunked/embedded
    DOCUMENT_STATUS_COMPLETED = 3;   // Successfully indexed
    DOCUMENT_STATUS_FAILED = 4;      // Processing failed
}
```

---

### ChatMode

Determines query handling.

```protobuf
// src/proto/public/chat.proto

enum ChatMode {
    CHAT_MODE_UNSPECIFIED = 0;
    CHAT_MODE_CHAT = 1;    // Full RAG: retrieve + LLM generation
    CHAT_MODE_SEARCH = 2;  // Vector search only, no LLM
}
```

---

### MessageRole

Conversation message roles.

```protobuf
// src/proto/public/chat.proto

enum MessageRole {
    MESSAGE_ROLE_UNSPECIFIED = 0;
    MESSAGE_ROLE_USER = 1;
    MESSAGE_ROLE_ASSISTANT = 2;
    MESSAGE_ROLE_SYSTEM = 3;
}
```

---

### LLMProvider

Supported LLM inference backends.

```protobuf
// src/proto/public/llm.proto

enum LLMProvider {
    LLM_PROVIDER_UNSPECIFIED = 0;
    LLM_PROVIDER_TGI = 1;        // Text Generation Inference
    LLM_PROVIDER_VLLM = 2;       // vLLM
    LLM_PROVIDER_OPENAI = 3;     // OpenAI API (cloud)
    LLM_PROVIDER_ANTHROPIC = 4;  // Anthropic API (cloud)
    LLM_PROVIDER_OLLAMA = 5;     // Ollama (local dev)
}
```

---

## Internal Proto Definitions

### ConnectorSyncRequest

Sent by orchestrator to trigger a connector sync.

```protobuf
// src/proto/internal/scheduler.proto

message ConnectorSyncRequest {
    int32 connector_id = 1;
    echomind.public.ConnectorType type = 2;
    int32 user_id = 3;
    echomind.public.ConnectorScope scope = 4;
    optional string scope_id = 5;
    google.protobuf.Struct config = 6;   // Credentials, paths
    google.protobuf.Struct state = 7;    // Cursors, tokens
    string chunking_session = 8;         // Batch tracking ID
}
```

| Field | Purpose |
|-------|---------|
| `connector_id` | Database ID |
| `type` | Routes to connector vs semantic |
| `scope` + `scope_id` | Determines Qdrant collection |
| `config` | OAuth tokens, folder IDs, etc. |
| `state` | Delta sync cursors, pagination |
| `chunking_session` | UUID to track this sync batch |

---

### DocumentProcessRequest

Sent by connector to semantic service for processing.

```protobuf
// src/proto/internal/semantic.proto

message DocumentProcessRequest {
    int32 document_id = 1;
    int32 connector_id = 2;
    string url = 3;                      // MinIO path or original URL
    string content_type = 4;             // MIME type
    echomind.public.ConnectorScope scope = 5;
    optional string scope_id = 6;
    string chunking_session = 7;
}
```

---

### AudioTranscribeRequest

Sent by semantic to voice service.

```protobuf
// src/proto/internal/voice.proto

message AudioTranscribeRequest {
    int32 document_id = 1;
    string audio_url = 2;         // MinIO path
    string language = 3;          // ISO 639-1 code or "auto"
    string chunking_session = 4;
}

message AudioTranscribeResponse {
    int32 document_id = 1;
    string transcript = 2;
    float duration_seconds = 3;
    string detected_language = 4;
}
```

---

### ImageAnalyzeRequest

Sent by semantic to vision service.

```protobuf
// src/proto/internal/vision.proto

message ImageAnalyzeRequest {
    int32 document_id = 1;
    string image_url = 2;         // MinIO path
    bool extract_text = 3;        // Run OCR
    string chunking_session = 4;
}

message ImageAnalyzeResponse {
    int32 document_id = 1;
    string caption = 2;           // BLIP description
    string ocr_text = 3;          // Extracted text (if enabled)
}
```

---

### EmbedRequest / EmbedResponse

gRPC messages for embedder service.

```protobuf
// src/proto/internal/embedding.proto

message EmbedRequest {
    repeated string contents = 1;
    string model = 2;             // SentenceTransformer model name
}

message EmbedResponse {
    repeated Embedding embeddings = 1;
}

message Embedding {
    repeated float values = 1;
}
```

---

## NATS Subjects

| Subject | Publisher | Consumer | Payload Proto |
|---------|-----------|----------|---------------|
| `connector.sync.{type}` | orchestrator | connector | `ConnectorSyncRequest` |
| `document.process` | connector | semantic | `DocumentProcessRequest` |
| `audio.transcribe` | semantic | voice | `AudioTranscribeRequest` |
| `image.analyze` | semantic | vision | `ImageAnalyzeRequest` |

**Note:** `{type}` is one of: `teams`, `google_drive`, `onedrive`, `web`, `file`

---

## Code Generation

```bash
# Generate Python + TypeScript from proto
make gen-proto

# Output locations:
# - Python: src/echomind_lib/models/
# - TypeScript: src/web/src/models/
```

**Never edit generated files directly.** Always modify the `.proto` source.

---

## References

- [Database Schema](./db-schema.md) - PostgreSQL table definitions
- [API Specification](./api-spec.md) - REST/WebSocket endpoints
- [Architecture](./architecture.md) - System overview
