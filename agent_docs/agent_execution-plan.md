# Sandboxed Agent Architecture — Consolidated Execution Plan

> **Date**: 2026-02-16
> **Based on**: 10 analysis documents (see [References](#references) for full list)
> **Status**: Ready for review

---

## Executive Summary

This plan transforms EchoMind's agent system from an in-process library into a **production-grade sandboxed agent platform**. Agents run in ephemeral Docker containers with a custom MCP server as the single gateway for skills, data connectors, and API keys. The 30 native Python tools are replaced with Moltbot-style bash skills (38 portable from Moltbot + 4 EchoMind-native). Full observability is provided via direct Langfuse SDK + Prometheus + Grafana (all internal, no internet needed for log shipping).

### Key Numbers

| Metric | Value |
|--------|-------|
| New services | 2 (sandbox, MCP gateway) |
| New DB tables | 2 (sandbox_sessions, sandbox_events) |
| Code to delete | ~1,100 LOC (29 of 30 native tools) |
| Code to write | ~3,000-4,000 LOC (across all phases) |
| Moltbot skills portable | 27 of 54 directly, 8 adapt, 3 replace (38 total + 4 new EchoMind-native) |
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
       +-----+-----+
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
| Observability | Langfuse SDK (direct) + Prometheus (direct) | Follow existing codebase pattern (`langfuse_helper.py` + `prometheus_client`). |
| Internet access | Direct from sandbox | Agent needs web search and web crawling. Observability (Langfuse, Prometheus) is internal — no internet required for log shipping. |
| DB access | Blocked (via MCP only) | Zero-trust enforcement at MCP boundary |

---

## Phase 1: MCP Gateway Server (Weeks 1-3)

> 📄 Deep dive: [agent_mcp-gateway.md](agent_mcp-gateway.md) — FastMCP design, tool registration, middleware, transport options

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

2. **MCP Tools — Search namespace** (RAG access):
   - `search_documents(query, collection, limit, score_threshold)` — Vector search across Qdrant collections
   - `search_collections()` — List available Qdrant collections (scoped by user/team/org)
   - `get_document(document_id)` — Document metadata from PostgreSQL
   - `get_document_chunks(document_id, limit)` — Full document content (chunks from Qdrant)

   **Search flow** (agent decides which collection to search):
   ```
   Agent                          MCP Server                  Backend
     |                               |                           |
     |-- search_collections() ----->|                           |
     |<-- [{name: "user_42",        |                           |
     |      doc_count: 150},        |                           |
     |     {name: "group_eng",      |                           |
     |      doc_count: 2400}] ------|                           |
     |                               |                           |
     |  (agent decides: search       |                           |
     |   "group_eng" for the query)  |                           |
     |                               |                           |
     |-- search_documents(          |                           |
     |     query="Q4 revenue",      |-- embed query ---------->| Embedder
     |     collection="group_eng",  |<-- vector ----------------|
     |     limit=5) --------------->|-- search Qdrant --------->| Qdrant
     |                               |<-- results ---------------|
     |<-- [{doc_id, title, score,   |                           |
     |      snippet}, ...] ---------|                           |
   ```

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

> 📄 Deep dive: [agent_mcp-gateway.md](agent_mcp-gateway.md) — MCP tool namespaces, API key management, connector proxy design

**Goal**: Expose data connectors and external API proxying via MCP gateway. The MCP server reads active connectors from PostgreSQL and exposes them as tools the agent can query and interact with.

### MCP Tools — Connectors namespace

The agent discovers available connectors, inspects their state, and requests data through MCP — it never touches the database directly.

```
Agent                          MCP Server                  Backend
  |                               |                           |
  |-- connectors_list() -------->|-- SELECT FROM connectors ->| PostgreSQL
  |<-- [{id: 1, name: "GDrive",  |   WHERE user_id=? AND     |
  |      type: "google_drive",   |   status='active'          |
  |      status: "active",       |<-- rows -------------------|
  |      last_sync: "2h ago",    |                           |
  |      docs_analyzed: 150},    |                           |
  |     {id: 3, name: "Gmail",   |                           |
  |      type: "gmail",          |                           |
  |      ...}] ------------------|                           |
  |                               |                           |
  |  (agent decides: "user wants  |                           |
  |   their latest emails")       |                           |
  |                               |                           |
  |-- connector_search(          |                           |
  |     connector_id=3,          |-- search Qdrant ---------->| Qdrant
  |     query="invoice from      |   collection="user_42"    |
  |     supplier") ------------->|   filter: connector_id=3  |
  |                               |<-- matching chunks -------|
  |<-- [{doc_id, title, score,   |                           |
  |      snippet}, ...] ---------|                           |
  |                               |                           |
  |-- connector_sync(id=1) ----->|-- NATS publish ---------->| NATS
  |<-- {status: "sync_started"} -|   connector.sync.gdrive   |
```

### Deliverables

1. **Connector tools** (MCP namespace: `connectors`):
   - `connectors_list()` — List user's active data connectors (from PostgreSQL, scoped by user/team/org via RBAC)
   - `connector_status(connector_id)` — Detailed sync status: last_sync_at, docs_analyzed, status_message, next_scheduled_sync
   - `connector_search(connector_id, query, limit)` — Search documents from a specific connector (Qdrant filtered by connector_id)
   - `connector_sync(connector_id)` — Trigger manual sync via NATS publish (requires edit permission)

2. **Implemented connectors** (available from Day 1):

   | Connector | Type | What it Fetches | Change Detection | Auth |
   |-----------|------|-----------------|------------------|------|
   | **Google Drive** | `google_drive` | Files, folders, Docs/Sheets/Slides (as PDF) | Changes API + md5Checksum | OAuth2 + Service Account |
   | **OneDrive/SharePoint** | `onedrive` | Files, folders, SharePoint sites | Delta API + cTag | MSAL / OAuth2 |
   | **Gmail** | `gmail` | Email threads (as markdown, 1 doc per thread) | History API + historyId | OAuth2 |
   | **Google Calendar** | `google_calendar` | Events (as markdown, 1 doc per event) | syncToken + 410 GONE handling | OAuth2 |
   | **Google Contacts** | `google_contacts` | Contacts (as markdown, 1 doc per contact) | People API syncToken | OAuth2 |

   All 5 connectors share the same pipeline: Connector → MinIO → NATS (`document.process`) → Semantic → Embedder → Qdrant.

3. **Deferred connectors** (planned, not yet implemented):

   | Connector | Type | Status | Notes |
   |-----------|------|--------|-------|
   | **Microsoft Teams** | `teams` | Deferred | Microsoft Graph API, delta query for messages |
   | **Web Scraper** | `web` | Deferred | Puppeteer/Playwright for JS rendering, goes to Semantic directly |
   | **File Upload** | `file` | Partial | Files already in MinIO, bypasses Connector service entirely |

4. **Future connector roadmap** (37+ connectors from `docs/echomind-connectors.md`):

   | Category | Connectors |
   |----------|------------|
   | **Knowledge Base & Wikis** | Confluence, SharePoint, Notion, BookStack, Document360, Discourse, GitBook, Slab, Outline, Google Sites, Guru |
   | **Cloud Storage** | Dropbox, AWS S3, Google Storage, Egnyte, Oracle Storage, Cloudflare R2, Box |
   | **Ticketing & Tasks** | Jira, Zendesk, Airtable, Linear, Freshdesk, Asana, ClickUp, ProductBoard, Monday.com |
   | **ITSM** | ServiceNow, PagerDuty |
   | **Messaging** | Slack, Discord, XenForo, Zulip, Zoom, Intercom |
   | **Sales & CRM** | Salesforce, HubSpot, Gong, Fireflies, Highspot, Microsoft Dynamics 365 |
   | **ERP & Finance** | SAP, Oracle Cloud, NetSuite, Concur |
   | **HR & HCM** | Workday |
   | **Accounting** | QuickBooks, Xero |
   | **BI & Analytics** | Power BI, Tableau, Looker |
   | **Code Repos** | GitHub, GitLab, Bitbucket |
   | **Data Warehouse** | Snowflake |
   | **Other** | Datadog, Okta, DocuSign |

   Adding a new connector requires: (1) implement provider in `src/connector/logic/providers/`, (2) add NATS subject routing, (3) the MCP gateway auto-discovers it from the `connectors` table — no MCP code changes needed.

5. **API proxy tools** (MCP namespace: `api`):
   - `web_search(query, max_results)` — Google Custom Search (agent never sees API key)
   - `send_email(to, subject, body)` — Gmail/Outlook via user's OAuth token
   - `calendar_create_event(title, start, end)` — Google Calendar/Outlook
   - `calendar_list_events(days_ahead)` — Upcoming events

6. **API Key Manager**:
   - Keys loaded from environment at startup
   - Per-service permission requirements
   - OAuth token refresh for per-user connector APIs (tokens in `connectors.config` JSONB)
   - Agent never receives raw key values

7. **Tests**: ~25 additional tests (connector tools, API proxy, key manager)

---

## Phase 3: Initial Skills & Portability Testing (Week 5)

> 📄 Deep dive: [agent_skills-migration.md](agent_skills-migration.md) — SKILL.md format, Moltbot skill engine analysis, migration strategy
> 📄 See also: [echomind-vs-moltbot-comparison.md](echomind-vs-moltbot-comparison.md) — Architecture comparison, skill format differences

**Goal**: Create initial skill library and validate Moltbot skill portability through MCP. Port ALL 55 Moltbot skills (53 core + 2 extensions).

Note: The skill engine (registry, executor, MCP tools) is built in Phase 1. This phase focuses on writing SKILL.md files and testing them end-to-end.

### Deliverables

1. **Initial skills directory** (first batch — validate pipeline):
   ```
   skills/
     github/SKILL.md           # Copied from Moltbot, adapted
     weather/SKILL.md          # Simple test case (curl wttr.in)
     summarize/SKILL.md        # URL/video summarization
     coding-agent/SKILL.md     # Sub-agent orchestration
     file-edit/SKILL.md        # Structured file editing patterns
   ```

2. **Skill portability test**: Copy 5 Moltbot skills, verify they work through MCP gateway. Validate the full flow: `skills_list()` → agent decides → `skills_get_info()` → `skills_execute()`

3. **System prompt engineering**: Teach the agent how to use skills effectively — when to call `skills_list`, when to call `skills_get_info` for detailed instructions, and how to construct bash commands based on skill instructions.

4. **Execution limits** (configurable per skill via SKILL.md metadata):
   - Default: 30s timeout, 64KB output
   - Extended: 120s timeout, 256KB output
   - Long-running: 300s timeout, 1MB output

### Complete Moltbot Skills Portability Assessment (55 skills)

> Source: `sample/moltbot/skills/` (53 core) + `sample/moltbot/extensions/` (2 extensions)

**Portability legend:**
- **Direct** — SKILL.md + CLI binary, works as-is in sandbox container
- **Adapt** — Needs minor changes (different CLI, env vars, Docker path adjustments)
- **Replace** — Moltbot-specific, needs EchoMind-native replacement
- **Skip** — macOS-only or Moltbot-platform-specific, not applicable to server sandbox

#### Core Skills (53)

| # | Skill | Emoji | Description | Install | Portability | Notes |
|---|-------|-------|-------------|---------|-------------|-------|
| 1 | `1password` | 🔐 | 1Password CLI (op) for secrets | brew | **Direct** | Install `op` in sandbox image |
| 2 | `apple-notes` | 📝 | Apple Notes via `memo` CLI | brew | **Skip** | macOS-only, no server equivalent |
| 3 | `apple-reminders` | ⏰ | Apple Reminders via `remindctl` | brew | **Skip** | macOS-only, no server equivalent |
| 4 | `bear-notes` | 🐻 | Bear notes via `grizzly` | go | **Skip** | macOS-only, no server equivalent |
| 5 | `bird` | 🐦 | X/Twitter CLI | brew/npm | **Direct** | Install `bird` in sandbox |
| 6 | `blogwatcher` | 📰 | RSS/Atom feed monitoring | go | **Direct** | Go binary, cross-platform |
| 7 | `blucli` | 🫐 | BluOS speaker control | go | **Skip** | Requires local network speakers |
| 8 | `bluebubbles` | — | BlueBubbles iMessage plugin | N/A | **Skip** | Moltbot extension plugin |
| 9 | `camsnap` | 📸 | RTSP/ONVIF camera capture | brew | **Adapt** | Needs network access to cameras |
| 10 | `canvas` | — | HTML display on Moltbot nodes | N/A | **Skip** | Moltbot-specific UI feature |
| 11 | `clawdhub` | — | ClawdHub skill CLI | npm | **Replace** | Replace with EchoMind skill registry |
| 12 | `coding-agent` | 🧩 | Codex/Claude Code/OpenCode CLI | varies | **Direct** | Install preferred coding agent |
| 13 | `discord` | 🎮 | Discord message control | config | **Direct** | Needs Discord bot token env var |
| 14 | `eightctl` | 🎛️ | Eight Sleep pod control | go | **Skip** | IoT device, needs local network |
| 15 | `food-order` | 🥡 | Foodora reordering | go | **Skip** | Personal service, not enterprise |
| 16 | `gemini` | ♊️ | Google Gemini CLI | brew | **Direct** | Install `gemini` + API key |
| 17 | `gifgrep` | 🧲 | GIF search and download | brew/go | **Direct** | Cross-platform |
| 18 | `github` | 🐙 | GitHub CLI (`gh`) | brew/apt | **Direct** | Pre-install in sandbox image |
| 19 | `gog` | 🎮 | Google Workspace CLI | brew | **Adapt** | Replace with EchoMind connector proxy |
| 20 | `goplaces` | 📍 | Google Places API search | brew | **Direct** | Needs `GOOGLE_PLACES_API_KEY` |
| 21 | `himalaya` | 📧 | Email CLI (IMAP/SMTP) | brew | **Adapt** | Replace with MCP `send_email` tool |
| 22 | `imsg` | 📨 | iMessage/SMS CLI | brew | **Skip** | macOS-only |
| 23 | `local-places` | 📍 | Local Google Places proxy | uv | **Adapt** | Merge with `goplaces` |
| 24 | `mcporter` | 📦 | MCP server management | npm | **Direct** | Useful for MCP debugging |
| 25 | `model-usage` | 📊 | CodexBar cost tracking | brew-cask | **Skip** | macOS-only, replace with Langfuse |
| 26 | `nano-banana-pro` | 🍌 | Gemini image generation | brew | **Direct** | Needs `GEMINI_API_KEY` |
| 27 | `nano-pdf` | 📄 | PDF editing with NL | uv | **Direct** | Install via `uv` |
| 28 | `notion` | 📝 | Notion API integration | N/A | **Direct** | Needs `NOTION_API_KEY` |
| 29 | `obsidian` | 💎 | Obsidian vault automation | brew | **Adapt** | Works on markdown files, no app needed |
| 30 | `openai-image-gen` | 🖼️ | OpenAI image generation | brew | **Direct** | Needs `OPENAI_API_KEY` |
| 31 | `openai-whisper` | 🎙️ | Local speech-to-text | brew | **Adapt** | Heavy model, use API version instead |
| 32 | `openai-whisper-api` | ☁️ | OpenAI Whisper API | curl | **Direct** | Lightweight, just curl + API key |
| 33 | `openhue` | 💡 | Philips Hue light control | brew | **Skip** | Requires local network bridge |
| 34 | `oracle` | 🧿 | Oracle CLI prompt bundling | npm | **Direct** | Cross-platform |
| 35 | `ordercli` | 🛵 | Foodora order tracking | brew/go | **Skip** | Personal service |
| 36 | `peekaboo` | 👀 | macOS UI automation | brew | **Skip** | macOS-only |
| 37 | `sag` | 🗣️ | ElevenLabs TTS | brew | **Direct** | Needs `ELEVENLABS_API_KEY` |
| 38 | `session-logs` | 📜 | Search conversation history | jq/rg | **Replace** | Replace with EchoMind session API |
| 39 | `sherpa-onnx-tts` | 🗣️ | Local offline TTS | download | **Adapt** | Large model download, sandbox storage |
| 40 | `skill-creator` | — | Skill creation guidance | N/A | **Direct** | Documentation-only skill |
| 41 | `slack` | 💬 | Slack message control | config | **Direct** | Needs Slack bot token |
| 42 | `songsee` | 🌊 | Audio spectrogram generation | brew | **Direct** | Cross-platform |
| 43 | `sonoscli` | 🔊 | Sonos speaker control | go | **Skip** | Requires local network speakers |
| 44 | `spotify-player` | 🎵 | Spotify playback | brew | **Skip** | Requires local audio output |
| 45 | `summarize` | 🧾 | URL/podcast summarization | brew | **Direct** | Cross-platform |
| 46 | `things-mac` | ✅ | Things 3 task management | go | **Skip** | macOS-only |
| 47 | `tmux` | 🧵 | Tmux session control | system | **Direct** | Pre-installed in sandbox |
| 48 | `trello` | 📋 | Trello board management | jq | **Direct** | Needs `TRELLO_API_KEY` + `TRELLO_TOKEN` |
| 49 | `video-frames` | 🎞️ | Video frame extraction | brew | **Direct** | Install `ffmpeg` in sandbox |
| 50 | `voice-call` | 📞 | Voice call plugin | config | **Skip** | Moltbot-specific plugin |
| 51 | `wacli` | 📱 | WhatsApp messaging | brew/go | **Adapt** | Needs WhatsApp auth session |
| 52 | `weather` | 🌤️ | Weather forecasts (free) | curl | **Direct** | No setup, just `curl wttr.in` |

#### Extension Skills (2)

| # | Skill | Description | Portability | Notes |
|---|-------|-------------|-------------|-------|
| 53 | `lobster` | Multi-step workflow orchestration with approval gates | **Adapt** | Valuable pattern — adapt for EchoMind approval workflows |
| 54 | `prose` | OpenProse VM multi-agent workflows | **Skip** | External VM, not applicable |

#### EchoMind-Native Skills (new, not from Moltbot)

| # | Skill | Description | Priority |
|---|-------|-------------|----------|
| 55 | `echomind-search` | RAG search via MCP (wraps `search_documents`) | P0 |
| 56 | `echomind-documents` | Document management (list, status, delete) | P0 |
| 57 | `echomind-connectors` | Connector management (list, sync, status) | P0 |
| 58 | `echomind-memory` | Agent long-term memory read/write | P1 |

#### Portability Summary

| Category | Count | Skills |
|----------|-------|--------|
| **Direct** (works as-is) | 27 | 1password, bird, blogwatcher, coding-agent, discord, gemini, gifgrep, github, goplaces, mcporter, nano-banana-pro, nano-pdf, notion, openai-image-gen, openai-whisper-api, oracle, sag, skill-creator, slack, songsee, summarize, tmux, trello, video-frames, weather, nano-pdf, obsidian* |
| **Adapt** (minor changes) | 8 | camsnap, gog, himalaya, local-places, openai-whisper, sherpa-onnx-tts, wacli, lobster |
| **Replace** (EchoMind native) | 3 | clawdhub → skill registry, session-logs → session API, model-usage → Langfuse |
| **Skip** (not applicable) | 16 | apple-notes, apple-reminders, bear-notes, blucli, bluebubbles, canvas, eightctl, food-order, imsg, openhue, ordercli, peekaboo, sonoscli, spotify-player, things-mac, voice-call, prose |

**Total portable: 38 of 54** (27 direct + 8 adapt + 3 replace). Plus 4 new EchoMind-native skills.

### Key Insight from Analysis

> 22 of 30 EchoMind tools (73%) are thin shell wrappers — they literally do `subprocess.run("git <cmd>")`. Migration to bash skills is trivial.

**Recommendation**: Keep `edit` as optional native tool (structured params safer than sed). Delete all other 29 native tools.

---

## Phase 4: Sandbox Container Foundation (Weeks 6-7)

> 📄 Deep dive: [agent_sandbox-containers.md](agent_sandbox-containers.md) — Container lifecycle, warm pool, security hardening, state machine
> 📄 See also: [agent_infrastructure.md](agent_infrastructure.md) — NATS streams, Docker Compose overlays, cluster.sh integration

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

3. **Database schema** — Proto + Migration workflow:

   > **CRITICAL**: Follow EchoMind entity creation rules. ALL new tables MUST:
   > 1. Define proto messages in `src/proto/internal/sandbox.proto` first (Source of Truth)
   > 2. Run `./scripts/generate_proto.sh` to generate Python/TS models
   > 3. Create Alembic migration in `src/migration/migrations/versions/`
   > 4. Migration runs automatically via the **migration init container** on deploy

   **Step 1 — Proto definition** (`src/proto/internal/sandbox.proto`):
   ```protobuf
   syntax = "proto3";
   package echomind.internal;
   option go_package = "echomind/proto/internal";

   import "google/protobuf/timestamp.proto";
   import "google/protobuf/struct.proto";

   enum SandboxStatus {
     SANDBOX_STATUS_UNSPECIFIED = 0;
     SANDBOX_STATUS_WARM = 1;
     SANDBOX_STATUS_ASSIGNED = 2;
     SANDBOX_STATUS_ACTIVE = 3;
     SANDBOX_STATUS_DRAINING = 4;
     SANDBOX_STATUS_DESTROYED = 5;
   }

   enum SandboxEventType {
     SANDBOX_EVENT_TYPE_UNSPECIFIED = 0;
     SANDBOX_EVENT_TYPE_ASSIGNED = 1;
     SANDBOX_EVENT_TYPE_ACTIVATED = 2;
     SANDBOX_EVENT_TYPE_MESSAGE = 3;
     SANDBOX_EVENT_TYPE_TOOL_CALL = 4;
     SANDBOX_EVENT_TYPE_ERROR = 5;
     SANDBOX_EVENT_TYPE_DRAINING = 6;
     SANDBOX_EVENT_TYPE_DESTROYED = 7;
   }

   message SandboxSession {
     string id = 1;                              // UUID
     string session_id = 2;
     int32 user_id = 3;
     optional int32 chat_session_id = 4;
     string container_id = 5;
     string container_name = 6;
     SandboxStatus status = 7;
     google.protobuf.Timestamp assigned_at = 8;
     optional google.protobuf.Timestamp activated_at = 9;
     optional google.protobuf.Timestamp destroyed_at = 10;
     google.protobuf.Struct agent_config = 11;
     int32 message_count = 12;
     int32 tool_calls_count = 13;
     int32 total_tokens = 14;
     google.protobuf.Timestamp created_at = 15;
     google.protobuf.Timestamp updated_at = 16;
   }

   message SandboxEvent {
     int64 id = 1;
     string sandbox_session_id = 2;             // FK → SandboxSession.id
     SandboxEventType event_type = 3;
     google.protobuf.Struct event_data = 4;
     google.protobuf.Timestamp created_at = 5;
   }
   ```

   **Step 2 — Generate models**: `./scripts/generate_proto.sh`

   **Step 3 — Alembic migration** (`src/migration/migrations/versions/YYYYMMDD_HHMMSS_add_sandbox_tables.py`):
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

   **Step 4 — Deploy**: Migration container auto-applies on `./cluster.sh -H` deploy.

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
  - Internet (web search, web crawl)
  - Langfuse + Prometheus (internal, no internet needed)

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

> 📄 Deep dive: [agent_chat-integration.md](agent_chat-integration.md) — WebSocket relay, streaming tokens, session pinning
> 📄 See also: [agent-chat-integration-analysis.md](agent-chat-integration-analysis.md) — Current chat handler analysis, modification points

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

> 📄 Deep dive: [agent_observability.md](agent_observability.md) — Langfuse tracing, Prometheus metrics, Grafana dashboards
> 📄 See also: [anthropic-provider-analysis.md](anthropic-provider-analysis.md) — Provider-specific observability (Langfuse supports both OpenAI + Anthropic natively)

**Goal**: End-to-end tracing, metrics, cost tracking, dashboards.

> **Decision (2026-02-16):** Use direct Langfuse SDK + Prometheus, matching the existing EchoMind pattern (`langfuse_helper.py`, `prometheus_client`).

### Deliverables

1. **Langfuse integration** (direct SDK, no collector):
   - Use existing `echomind_lib.helpers.langfuse_helper` (`create_trace()`, `score_trace()`)
   - Agent service: trace per agent run with `session_id`, `agent_id`, `provider`, `model`
   - MCP gateway: trace per tool call with server name, transport, duration
   - Both services: `init_langfuse()` on startup, `shutdown_langfuse()` on shutdown

2. **Agent tracing middleware**:
   - `ObservabilityMiddleware` (ChatMiddleware) — Langfuse generation per LLM call
   - `ToolObservabilityMiddleware` (FunctionMiddleware) — Langfuse span per tool call
   - All traces linked via `session_id` for conversation-level grouping

3. **Prometheus metrics** (direct, pull-based):
   - Agent service: expose `/metrics` endpoint with `prometheus_client`
   - Counters: agent_runs_total (by agent_id, provider, status), tool_calls_total (by tool, status)
   - Histograms: agent_run_duration_seconds, tool_call_duration_seconds
   - Add scrape target to `config/observability/prometheus/prometheus.yml`

4. **Cost tracking**:
   - Token usage per run with model-specific pricing
   - Langfuse cost_details attributes (Langfuse handles OpenAI + Anthropic pricing natively)
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

> 📄 Deep dive: [agent_skills-migration.md](agent_skills-migration.md) — Native tool deletion plan, SKILL.md authoring guide, sandbox image setup

**Goal**: Delete native tools, port ALL remaining Moltbot skills, build EchoMind-native skills. See [Phase 3](#phase-3-initial-skills--portability-testing-week-5) for the complete 55-skill portability assessment.

### Deliverables

1. **Delete 29 native tools**:
   ```
   DELETE: filesystem.py, directory.py, git.py, git_extended.py,
           system.py, text.py, web.py
   KEEP:   edit.py (optional native), execution.py (bash core),
           registry.py (simplified)
   ```

2. **Port all remaining "Direct" Moltbot skills** (22 skills beyond Phase 3's initial 5):
   - `1password`, `bird`, `blogwatcher`, `discord`, `gemini`, `gifgrep`, `goplaces`
   - `mcporter`, `nano-banana-pro`, `nano-pdf`, `notion`, `openai-image-gen`
   - `openai-whisper-api`, `oracle`, `sag`, `skill-creator`, `slack`, `songsee`
   - `summarize`, `tmux`, `trello`, `video-frames`

3. **Adapt 8 skills** requiring minor changes:
   - `camsnap` — Adjust for Docker network camera access
   - `gog` — Replace with EchoMind Google Workspace connector proxy
   - `himalaya` — Replace with MCP `send_email` / use connector
   - `local-places` — Merge into `goplaces`
   - `openai-whisper` — Use API version (`openai-whisper-api`) to avoid model download
   - `sherpa-onnx-tts` — Configure model path for sandbox volume mount
   - `wacli` — WhatsApp auth session management in sandbox
   - `lobster` — Adapt approval workflow for EchoMind's session model

4. **Build 3 replacement skills**:
   - `clawdhub` → EchoMind skill registry (skills managed by MCP gateway)
   - `session-logs` → EchoMind session history API
   - `model-usage` → Langfuse cost dashboard link

5. **Build 4 EchoMind-native skills**:
   - `echomind-search` — RAG search via MCP
   - `echomind-documents` — Document management
   - `echomind-connectors` — Connector management
   - `echomind-memory` — Agent long-term memory

6. **Sandbox Docker image** — Pre-install high-priority binaries:
   ```dockerfile
   # Phase 7 sandbox image additions
   RUN apt-get install -y jq curl ffmpeg tmux && \
       go install github.com/cli/cli/v2/cmd/gh@latest && \
       pip install nano-pdf
   # API-key-dependent skills are available but require env vars
   ```

---

## Phase 8: Auth & Security Hardening (Week 11+)

> 📄 Deep dive: [agent_mcp-gateway.md](agent_mcp-gateway.md) — JWT auth, RBAC enforcement, rate limiting design
> 📄 See also: [agent_sandbox-containers.md](agent_sandbox-containers.md) — Network isolation, capability dropping, security hardening

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
| Sandbox pool (3 warm) | 1.5 cores | 1.5 GB | — |
| Sandbox active (8 max) | 16 cores | 16 GB | — |
| **Peak total** | ~28.5 cores | ~28 GB | — |

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

5. **Observability late** — Can be added incrementally without blocking other work. Uses direct Langfuse SDK + Prometheus.

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

### Agent Architecture Documents

| Document | Description | Relevant Phases |
|----------|-------------|-----------------|
| [agent_sandbox-containers.md](agent_sandbox-containers.md) | Container architecture, lifecycle, security, warm pool | Phase 4 |
| [agent_mcp-gateway.md](agent_mcp-gateway.md) | MCP server design, FastMCP, zero-trust model | Phase 1, 2, 8 |
| [agent_skills-migration.md](agent_skills-migration.md) | Tool migration analysis, Moltbot skill format | Phase 3, 7 |
| [agent_observability.md](agent_observability.md) | Langfuse, Prometheus, Grafana dashboards | Phase 6 |
| [agent_infrastructure.md](agent_infrastructure.md) | NATS streams, Docker Compose, cluster.sh changes | Phase 4, 5 |
| [agent_chat-integration.md](agent_chat-integration.md) | WebSocket chat flow, sandbox message relay | Phase 5 |
| [agent-chat-integration-analysis.md](agent-chat-integration-analysis.md) | Analysis of current chat handler for agent integration | Phase 5 |
| [anthropic-provider-analysis.md](anthropic-provider-analysis.md) | Anthropic LLM provider support, AnthropicClient, provider detection | All (provider-agnostic) |
| [echomind-vs-moltbot-comparison.md](echomind-vs-moltbot-comparison.md) | Feature comparison, architecture differences | Context |
| [old-agent-phases-roadmap.md](old-agent-phases-roadmap.md) | Previous roadmap (superseded by this document) | Historical |

### External References

- [FastMCP 3.x](https://gofastmcp.com) — MCP framework
- [Docker Sandboxes](https://docs.docker.com/ai/sandboxes) — Docker AI sandbox documentation
- [Zero-Trust AI Agents](https://genmind.ch/posts/Securing-AI-Agents-with-Zero-Trust-and-Sandboxing/) — User's blog post
- [Microsoft Agent Framework](https://github.com/microsoft/agent-framework) — Agent framework (OpenAI + Anthropic clients)
