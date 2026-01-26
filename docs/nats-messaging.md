# EchoMind NATS Messaging

> Complete message flow documentation for NATS JetStream communication.

---

## Overview

EchoMind uses NATS JetStream for asynchronous service communication in the document ingestion pipeline. Messages are persistent and support at-least-once delivery.

**Connection URL:** `nats://nats:4222` (internal) or `NATS_URL` env var

---

## Message Flow Diagram

```mermaid
sequenceDiagram
    participant O as Orchestrator
    participant N as NATS JetStream
    participant DLQ as NATS DLQ
    participant C as Connector
    participant S as Semantic
    participant V as Voice
    participant I as Vision
    participant G as Guardian
    participant E as Embedder (gRPC)
    participant DB as PostgreSQL
    participant Q as Qdrant

    Note over O: Every 60s check for due connectors

    O->>DB: Query connectors (status=active/error)
    O->>DB: Set status = pending
    O->>N: connector.sync.{type}

    alt type = teams/onedrive/gdrive
        N->>C: ConnectorSyncRequest
        C->>DB: Set status = syncing
        C->>C: Fetch from external API
        C->>N: document.process
    else type = web/file
        N->>S: ConnectorSyncRequest
        S->>DB: Set status = syncing
    end

    N->>S: DocumentProcessRequest

    alt Audio file (mp3/wav)
        S->>N: audio.transcribe
        N->>V: AudioTranscribeRequest
        V->>V: Whisper transcription
        V->>N: (callback or direct)
        N->>S: AudioTranscribeResponse
    else Image/Video file
        S->>N: image.analyze
        N->>I: ImageAnalyzeRequest
        I->>I: BLIP + OCR
        I->>N: (callback or direct)
        N->>S: ImageAnalyzeResponse
    end

    S->>S: Extract text (pymupdf4llm, BS4)
    S->>S: Chunk text
    S->>E: EmbedRequest (gRPC)
    E->>E: Generate vectors
    E->>Q: Store vectors
    E-->>S: EmbedResponse

    S->>DB: Set status = active (success)
    S->>DB: Set status = error (failure)

    Note over N,DLQ: On max retry failures
    N-->>DLQ: Move to dlq.{subject}
    DLQ->>G: FailureDetails
    G->>G: Parse headers, send alerts
    G->>DLQ: Acknowledge
```

---

## Streams Configuration

### ECHOMIND Stream

Primary stream for document ingestion.

```bash
# Create stream
nats stream add ECHOMIND \
  --subjects "connector.sync.*,document.process,audio.transcribe,image.analyze" \
  --retention limits \
  --max-msgs-per-subject 10000 \
  --max-age 7d \
  --storage file \
  --replicas 1
```

| Setting | Value | Rationale |
|---------|-------|-----------|
| Retention | limits | Remove old messages after max-age |
| Max Age | 7 days | Keep failed messages for debugging |
| Storage | file | Persist across restarts |
| Replicas | 1 | Single node (increase for HA) |

### ECHOMIND_DLQ Stream

Dead-letter queue for failed messages. Monitored by Guardian service.

```bash
# Create DLQ stream
nats stream add ECHOMIND_DLQ \
  --subjects "dlq.>" \
  --retention limits \
  --max-age 30d \
  --storage file \
  --replicas 1
```

| Setting | Value | Rationale |
|---------|-------|-----------|
| Subjects | `dlq.>` | Wildcard captures all DLQ subjects |
| Retention | limits | Keep for audit/debugging |
| Max Age | 30 days | Long retention for investigation |
| Storage | file | Persist across restarts |

**Consumer:** `echomind-guardian` monitors this stream and sends alerts.

---

## Subjects Reference

### 1. connector.sync.{type}

**Purpose:** Trigger connector sync for a specific data source type.

| Attribute | Value |
|-----------|-------|
| **Publisher** | echomind-orchestrator |
| **Consumer** | echomind-connector (teams, onedrive, gdrive) OR echomind-semantic (web, file) |
| **Payload** | `ConnectorSyncRequest` |
| **Trigger** | APScheduler job (every 60s) |

**Subject Variants:**
- `connector.sync.teams` → Connector Service
- `connector.sync.onedrive` → Connector Service
- `connector.sync.google_drive` → Connector Service
- `connector.sync.web` → Semantic Service
- `connector.sync.file` → Semantic Service

**Payload:** See [Proto Definitions - ConnectorSyncRequest](./proto-definitions.md#connectorsyncrequest)

```json
{
  "connector_id": 123,
  "type": "google_drive",
  "user_id": 42,
  "scope": "group",
  "scope_id": "engineering",
  "config": {"folder_id": "abc123", "access_token": "..."},
  "state": {"delta_cursor": "xyz789"},
  "chunking_session": "uuid-here"
}
```

---

### 2. document.process

**Purpose:** Request document extraction and embedding.

| Attribute | Value |
|-----------|-------|
| **Publisher** | echomind-connector |
| **Consumer** | echomind-semantic |
| **Payload** | `DocumentProcessRequest` |
| **Trigger** | After connector downloads file to MinIO |

**Payload:** See [Proto Definitions - DocumentProcessRequest](./proto-definitions.md#documentprocessrequest)

```json
{
  "document_id": 456,
  "connector_id": 123,
  "url": "minio:documents:abc123.pdf",
  "content_type": "application/pdf",
  "scope": "group",
  "scope_id": "engineering",
  "chunking_session": "uuid-here"
}
```

---

### 3. audio.transcribe

**Purpose:** Request audio transcription via Whisper.

| Attribute | Value |
|-----------|-------|
| **Publisher** | echomind-semantic |
| **Consumer** | echomind-voice |
| **Payload** | `AudioTranscribeRequest` |
| **Trigger** | When semantic service detects audio MIME type |

**Payload:** See [Proto Definitions - AudioTranscribeRequest](./proto-definitions.md#audiotranscriberequest)

```json
{
  "document_id": 789,
  "audio_url": "minio:audio:meeting.mp3",
  "language": "auto",
  "chunking_session": "uuid-here"
}
```

**Response Flow:** Voice service publishes transcript back or writes directly to document record.

---

### 4. image.analyze

**Purpose:** Request image captioning and OCR.

| Attribute | Value |
|-----------|-------|
| **Publisher** | echomind-semantic |
| **Consumer** | echomind-vision |
| **Payload** | `ImageAnalyzeRequest` |
| **Trigger** | When semantic service detects image/video MIME type |

**Payload:** See [Proto Definitions - ImageAnalyzeRequest](./proto-definitions.md#imageanalyzerequest)

```json
{
  "document_id": 101,
  "image_url": "minio:images:diagram.png",
  "extract_text": true,
  "chunking_session": "uuid-here"
}
```

---

### 5. dlq.{original_subject}

**Purpose:** Failed messages that exceeded max retry attempts.

| Attribute | Value |
|-----------|-------|
| **Publisher** | NATS JetStream (automatic) |
| **Consumer** | echomind-guardian |
| **Stream** | ECHOMIND_DLQ |
| **Trigger** | Message exceeds `max_deliver` attempts |

**Headers Added by NATS:**

| Header | Description |
|--------|-------------|
| `Nats-Original-Subject` | Original subject (e.g., `document.process`) |
| `Nats-Original-Stream` | Original stream name |
| `Nats-Original-Sequence` | Sequence number in original stream |
| `Nats-Failure-Description` | Error description |
| `Nats-Num-Delivered` | Number of delivery attempts |

**Guardian Processing:**
1. Parse failure headers
2. Extract failure details
3. Send alerts via configured alerters (Slack, PagerDuty, logging)
4. Acknowledge message

---

## Consumer Groups

Each service uses a durable consumer with queue groups for load balancing.

| Service | Consumer Name | Queue Group | Stream |
|---------|---------------|-------------|--------|
| echomind-connector | `connector-consumer` | `connector-workers` | ECHOMIND |
| echomind-semantic | `semantic-consumer` | `semantic-workers` | ECHOMIND |
| echomind-voice | `voice-consumer` | `voice-workers` | ECHOMIND |
| echomind-vision | `vision-consumer` | `vision-workers` | ECHOMIND |
| echomind-guardian | `guardian-consumer` | `guardian-workers` | ECHOMIND_DLQ |

```python
# Example consumer configuration
subscriber = JetStreamEventSubscriber(
    nats_url="nats://nats:4222",
    stream_name="ECHOMIND",
    subject="document.process",
    durable_name="semantic-consumer",
    queue_group="semantic-workers"
)
```

---

## Message Routing Summary

```
┌─────────────────┐
│  Orchestrator   │
│  (Publisher)    │
└────────┬────────┘
         │
         ▼ connector.sync.{type}
         │
    ┌────┴────┐
    │         │
    ▼         ▼
┌───────┐  ┌──────────┐
│Connector│  │ Semantic │  (web/file go direct)
└────┬───┘  └────┬─────┘
     │           │
     │ document  │
     │ .process  │
     └─────┬─────┘
           │
           ▼
    ┌──────────┐
    │ Semantic │
    └────┬─────┘
         │
    ┌────┼────┐
    │    │    │
    ▼    │    ▼
┌─────┐  │  ┌──────┐
│Voice│  │  │Vision│
└──┬──┘  │  └──┬───┘
   │     │     │
   └─────┼─────┘
         │
         ▼ (text ready)
    ┌──────────┐
    │ Embedder │ (gRPC, not NATS)
    └──────────┘

    ═══════════════════════════════════════
    On failure (max retries exceeded):

    ┌─────────────────┐
    │ Any Consumer    │
    │ (max_deliver)   │
    └────────┬────────┘
             │
             ▼ dlq.{original_subject}
    ┌─────────────────┐
    │  ECHOMIND_DLQ   │
    └────────┬────────┘
             │
             ▼
    ┌─────────────────┐
    │    Guardian     │──► Slack/PagerDuty/Logs
    │  (DLQ Monitor)  │
    └─────────────────┘
```

---

## Error Handling

### Message Acknowledgment

| Outcome | Action | Result |
|---------|--------|--------|
| Success | `msg.ack()` | Message removed from queue |
| Temporary failure | `msg.nak()` | Message redelivered after delay |
| Permanent failure | `msg.term()` | Message moved to dead letter |
| Processing | `msg.in_progress()` | Extend ack deadline |

### Dead Letter Queue

Failed messages after max retries go to the `ECHOMIND_DLQ` stream. The Guardian service monitors this stream for alerting.

See [Streams Configuration - ECHOMIND_DLQ](#echomind_dlq-stream) and [Guardian Service](./services/guardian-service.md).

### Retry Policy

```python
# Consumer configuration
max_deliver = 5          # Max redelivery attempts
ack_wait = "30s"         # Ack deadline
backoff = [              # Delay between retries
    "1s",
    "5s",
    "30s",
    "2m",
    "10m"
]
```

---

## Monitoring

### Key Metrics

| Metric | Description |
|--------|-------------|
| `nats_consumer_pending_msgs` | Messages waiting to be processed |
| `nats_consumer_redelivered_msgs` | Messages that were redelivered |
| `nats_consumer_ack_pending` | Messages awaiting acknowledgment |
| `nats_stream_msgs` | Total messages in stream |

### Health Checks

```bash
# Check stream status
nats stream info ECHOMIND

# Check consumer lag
nats consumer info ECHOMIND semantic-consumer

# View pending messages
nats consumer next ECHOMIND semantic-consumer --peek
```

---

## Configuration

### Environment Variables

```bash
# All services
NATS_URL=nats://nats:4222
NATS_STREAM_NAME=ECHOMIND

# Orchestrator (publisher)
ORCHESTRATOR_NATS_SUBJECT_PREFIX=connector.sync

# Connector
CONNECTOR_NATS_SUBJECTS=connector.sync.teams,connector.sync.onedrive,connector.sync.google_drive
CONNECTOR_PUBLISH_SUBJECT=document.process

# Semantic
SEMANTIC_NATS_SUBJECTS=connector.sync.web,connector.sync.file,document.process
SEMANTIC_PUBLISH_AUDIO=audio.transcribe
SEMANTIC_PUBLISH_IMAGE=image.analyze

# Voice
VOICE_NATS_SUBJECTS=audio.transcribe

# Vision
VISION_NATS_SUBJECTS=image.analyze

# Guardian (DLQ monitoring)
GUARDIAN_NATS_STREAM=ECHOMIND_DLQ
GUARDIAN_NATS_SUBJECTS=dlq.>
GUARDIAN_ALERTERS=logging,slack
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/xxx/yyy/zzz
```

---

## References

- [Proto Definitions](./proto-definitions.md) - Message payload schemas
- [Architecture](./architecture.md) - System overview
- [Guardian Service](./services/guardian-service.md) - DLQ monitoring and alerting
- [NATS JetStream Docs](https://docs.nats.io/nats-concepts/jetstream)
- [NATS JetStream DLQ](https://docs.nats.io/using-nats/developer/develop_jetstream/consumers#dead-letter-queues)
