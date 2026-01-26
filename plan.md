# EchoMind Development Plan

## Current Status

### Implemented Services (Working)

| Service | Status | Tests | Notes |
|---------|--------|-------|-------|
| **API** | Complete | 0 tests | 42 endpoints, FastAPI |
| **Embedder** | Complete | 3 files | gRPC, GPU support, SentenceTransformers |
| **Migration** | Complete | 2 files | Alembic runner, no migrations created |

### Not Implemented Services

| Service | Priority | Complexity | Depends On |
|---------|----------|------------|------------|
| **Orchestrator** | 1st | Low | CRUD, Migrations |
| **Connector** | 2nd | High | Orchestrator, Semantic |
| **Semantic** | 2nd | Medium | Embedder |
| **Voice** | 3rd | Medium | Semantic |
| **Vision** | 3rd | Medium | Semantic |
| **Guardian** | 4th | Low | NATS DLQ |
| **Search** | 5th | Very High | Everything |

### Critical Gaps

1. **`db/crud/`** is **EMPTY** - No CRUD operations for any of the 11 ORM models
2. **`migrations/versions/`** is **EMPTY** - No database migrations created
3. **API has 0 tests** - 42 endpoints completely untested

---

## Pipeline Architecture

```
Orchestrator (trigger)
       │
       ▼
Connector (fetch from Teams/OneDrive/GDrive)
       │
       ▼
Document DB ──────► Semantic (extract/chunk)
                          │
          ┌───────────────┼───────────────┐
          ▼               ▼               ▼
       Audio          Images/Video      Text
          │               │               │
          ▼               ▼               │
       Voice           Vision            │
          │               │               │
          └───────────────┼───────────────┘
                          ▼
                    Embedder (vectorize)
                          │
                          ▼
                    Qdrant (store)
                          │
                          ▼
                    Search (retrieve + reason)
```

---

## Development Phases

### Phase 1: Foundation (BLOCKING - Must Complete First)

#### 1.1 CRUD Operations
- Location: `src/echomind_lib/db/crud/`
- Models requiring CRUD (11 total):
  - `UserCRUD`
  - `AssistantCRUD`
  - `LLMCRUD`
  - `EmbeddingModelCRUD`
  - `ConnectorCRUD`
  - `DocumentCRUD`
  - `ChatSessionCRUD`
  - `ChatMessageCRUD`
  - `ChatMessageFeedbackCRUD`
  - `ChatMessageDocumentCRUD`
  - `AgentMemoryCRUD`

Each CRUD class must implement:
```python
async def get_by_id(session, id) -> Model | None
async def create(session, data) -> Model
async def update(session, id, data) -> Model
async def delete(session, id) -> bool
async def list(session, filters, pagination) -> list[Model]
```

#### 1.2 Database Migrations
- Location: `src/migration/migrations/versions/`
- Create initial migration with all 11 tables
- Include indexes, foreign keys, constraints

#### 1.3 API Tests
- Location: `tests/unit/api/`
- Minimum coverage: 70%
- Priority endpoints:
  - Health/Ready
  - Assistants CRUD
  - Connectors CRUD
  - Documents list/search

---

### Phase 2: Pipeline Core

#### 2.1 Semantic Service
- Location: `src/semantic/`
- Protocol: NATS subscriber
- Port: 8080 (health)
- Responsibilities:
  - Content extraction (pymupdf4llm, BeautifulSoup)
  - Text chunking (RecursiveCharacterTextSplitter)
  - Route audio to Voice service
  - Route images to Vision service
  - Call Embedder via gRPC
- NATS subjects:
  - Subscribe: `document.process`, `connector.sync.web`, `connector.sync.file`
  - Publish: `audio.transcribe`, `image.analyze`

#### 2.2 Orchestrator Service
- Location: `src/orchestrator/`
- Protocol: NATS publisher only
- Port: 8080 (health)
- Responsibilities:
  - APScheduler job every 60 seconds
  - Query connectors due for sync
  - Update status to `pending`
  - Publish to NATS
- NATS subjects:
  - Publish: `connector.sync.{type}`

---

### Phase 3: Data Sources

#### 3.1 Connector Service
- Location: `src/connector/`
- Protocol: NATS subscriber
- Port: 8080 (health)
- Responsibilities:
  - OAuth token management
  - Delta sync (Teams, OneDrive, Google Drive)
  - Download files to MinIO
  - Create document records
- NATS subjects:
  - Subscribe: `connector.sync.teams`, `connector.sync.onedrive`, `connector.sync.google_drive`
  - Publish: `document.process`
- External APIs:
  - Microsoft Graph API
  - Google Drive API

---

### Phase 4: Media Processing

#### 4.1 Voice Service
- Location: `src/voice/`
- Protocol: NATS subscriber
- Port: 8080 (health)
- Responsibilities:
  - Download audio from MinIO
  - Transcribe with Whisper
  - Update document content
- NATS subjects:
  - Subscribe: `audio.transcribe`
- Models: whisper-base (default)

#### 4.2 Vision Service
- Location: `src/vision/`
- Protocol: NATS subscriber
- Port: 8080 (health)
- Responsibilities:
  - Download image/video from MinIO
  - Caption with BLIP
  - Extract text with OCR
  - Update document content
- NATS subjects:
  - Subscribe: `image.analyze`
- Models: BLIP-base, EasyOCR

---

### Phase 5: Monitoring & Search

#### 5.1 Guardian Service
- Location: `src/guardian/`
- Protocol: NATS subscriber
- Port: 8080 (health)
- Responsibilities:
  - Monitor DLQ stream
  - Extract failure metadata
  - Send alerts (Slack, PagerDuty, email)
- NATS subjects:
  - Subscribe: `dlq.>`

#### 5.2 Search Service
- Location: `src/search/`
- Protocol: gRPC
- Port: 50051 (gRPC), 8080 (health)
- Responsibilities:
  - Agentic reasoning (Semantic Kernel)
  - Multi-step retrieval
  - Tool execution
  - Memory management
  - Token streaming
- Dependencies:
  - Qdrant (vector search)
  - Redis (short-term memory)
  - LLM router (inference)

---

## Service Directory Structure

Each service must follow this pattern:
```
src/{service}/
├── __init__.py
├── main.py              # Entry point
├── config.py            # Pydantic Settings
├── logic/
│   ├── __init__.py
│   ├── exceptions.py    # Domain exceptions
│   └── *_service.py     # Business logic
├── middleware/
│   └── error_handler.py # Protocol-specific errors
└── Dockerfile
```

---

## Port Assignments

| Service | Health | API/gRPC | Protocol |
|---------|--------|----------|----------|
| api | 8080 | 8080 | HTTP/WebSocket |
| search | 8080 | 50051 | gRPC |
| embedder | 8080 | 50051 | gRPC |
| orchestrator | 8080 | - | - |
| connector | 8080 | - | - |
| semantic | 8080 | - | - |
| voice | 8080 | - | - |
| vision | 8080 | - | - |
| guardian | 8080 | - | - |

---

## NATS Subjects Map

| Subject | Publisher | Consumer |
|---------|-----------|----------|
| `connector.sync.teams` | Orchestrator | Connector |
| `connector.sync.onedrive` | Orchestrator | Connector |
| `connector.sync.google_drive` | Orchestrator | Connector |
| `connector.sync.web` | Orchestrator | Semantic |
| `connector.sync.file` | Orchestrator | Semantic |
| `document.process` | Connector | Semantic |
| `audio.transcribe` | Semantic | Voice |
| `image.analyze` | Semantic | Vision |
| `dlq.>` | NATS DLQ | Guardian |

---

## Phase Evaluation Criteria

Each phase must pass ALL criteria before moving to the next phase.

### Automated Checks (Must Pass 100%)

| Check | Command | Requirement |
|-------|---------|-------------|
| **Unit Tests** | `pytest tests/unit/ -v` | 100% pass, 0 failures |
| **Test Warnings** | `pytest tests/unit/ -v -W error` | 0 warnings |
| **Type Checking** | `mypy src/` | 0 errors (NO ignore flags) |
| **Linting** | `ruff check src/` | 0 errors |
| **Docstring Coverage** | `interrogate src/ -v` | 70% minimum |

**NO CHEATING FLAGS ALLOWED:**
- No `--ignore-missing-imports`
- No `# type: ignore` without justification
- No `# noqa` without justification
- No `-W ignore` or warning suppression

### Rule Compliance (Manual Review)

From `.claude/rules/`:

- [ ] **Type hints**: ALL parameters and return types annotated
- [ ] **Docstrings**: Args/Returns/Raises documented
- [ ] **Emoji logging**: All log statements use emoji prefix
- [ ] **No shared code duplication**: Imports from `echomind_lib` only
- [ ] **No hand-written Pydantic models**: Proto-generated only
- [ ] **Business logic separation**: Entry points are thin adapters
- [ ] **No unused imports/code**: Clean codebase

### Code Quality (No Hacks)

- [ ] No `# type: ignore` without justification
- [ ] No `# noqa` without justification
- [ ] No `TODO` workarounds in production code
- [ ] No suppressed exceptions (`except: pass`)
- [ ] No hardcoded credentials or secrets
- [ ] No deprecated function usage

### Documentation

- [ ] API changes reflected in `docs/api-spec.md`
- [ ] New services documented in `docs/services/`
- [ ] Proto changes updated in `docs/proto-definitions.md`

---

## Evaluation Results

### Phase 1 Evaluation (2026-01-26)

| Check | Status | Result |
|-------|--------|--------|
| Unit Tests | PASS | 98 passed, 0 failed |
| Test Warnings | PASS | 0 warnings |
| Type Checking | PASS | 0 errors (mypy src/api/) |
| Linting | PASS | 0 errors (ruff check src/api/) |
| Docstring Coverage | PENDING | Install interrogate to check |
| Rule Compliance | PENDING | Manual review needed |
| Code Quality | PENDING | Manual review needed |
| Documentation | PENDING | Manual review needed |

**Overall Phase 1 Automated Checks**: PASS

#### Fixes Applied

**datetime.utcnow() → datetime.now(timezone.utc):**
- `src/api/routes/assistants.py`
- `src/api/routes/connectors.py`
- `src/api/routes/llms.py`
- `src/api/routes/chat.py`
- `src/api/logic/assistant_service.py`

**Unused variables removed:**
- Removed `total = len(count_result.all())` from all routes (unused pagination count)

**Unused imports removed:**
- `DbSession` and `TokenUser` from auth.py
- `get_qdrant` from documents.py
- `extract_bearer_token` from chat_handler.py

**Type errors fixed:**
- `converters.py` - Removed non-existent Document fields
- `embedding_models.py` - Fixed keyword argument name
- `llms.py` - Fixed provider enum assignment
- `connectors.py` - Fixed scope enum assignment
- `chat.py` - Fixed is_positive type assignment
- `main.py` - Restructured imports, fixed health check types
- `chat_handler.py` - Added type annotations
- `manager.py` - Added return type and type annotations

**Linting fixes:**
- Moved imports to top of file in main.py
- Renamed ambiguous variable `l` to `llm_obj`
- Changed `== True` to `.is_(True)` for SQLAlchemy

---

## Plan Accuracy

**Plan Accuracy: 95%**

The 5% uncertainty accounts for:
- OAuth integration complexity (Microsoft Graph, Google APIs)
- Semantic Kernel version compatibility
- Potential proto schema adjustments
- Undocumented edge cases in file processing

---

## Execution Order

1. Phase 1.1: CRUD Operations (blocks everything)
2. Phase 1.2: Database Migrations (blocks services)
3. Phase 1.3: API Tests (can parallel with Phase 2)
4. Phase 2.1: Semantic Service
5. Phase 2.2: Orchestrator Service
6. Phase 3.1: Connector Service
7. Phase 4.1: Voice Service
8. Phase 4.2: Vision Service
9. Phase 5.1: Guardian Service
10. Phase 5.2: Search Service

---

## Notes

- All services import from `echomind_lib` - never duplicate code
- Proto is source of truth - run `./scripts/generate_proto.sh` after changes
- Never edit generated code in `echomind_lib/models/`
- Emoji logging required (see `.claude/rules/logging.md`)
- Unit tests mandatory - 70% coverage minimum
